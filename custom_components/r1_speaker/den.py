"""Đèn LED của loa R1 theo CHỨC NĂNG: cài đặt, chọn chức năng đang hiệu lực, áp xuống sink.

Phần cứng và giới hạn: xem ``den_port.py`` (đèn viền chỉ trắng, đèn đáy RGB, KHÔNG có đường từ HA
tới đèn loa — cần một dịch vụ trên loa, chưa có). Mặc định ``R1Lights`` dùng ``NullLights``: lưu
cài đặt, tính chức năng đang hiệu lực, hiện ở ``sensor.r1_cai_dat``, nhưng không gửi gì đi.
Cắm sink thật sau này: ``coordinator.lights.set_sink(sink)`` (sink thoả ``den_port.LightsSink``).

Tám chức năng (``FUNCTIONS``); mỗi chức năng có năm số: bật/tắt, dùng đèn viền (trắng), màu đèn
đáy, hiệu ứng (``hieu_ung.HIEU_UNG`` hoặc ``none``), độ sáng 0–100. Chức năng đang hiệu lực chọn
theo ``UU_TIEN`` (đứng trước thắng):

1. ``tat_mic`` — mic đang tắt (luôn thắng: người dùng phải thấy mic không nghe);
2. ``loi`` — phiên đóng vì lỗi / pipeline báo lỗi, giữ ``LIGHT_ERROR_HOLD_S`` giây;
3. ``phan_hoi`` / ``nghi`` / ``nghe`` — theo trạng thái ``assist_satellite.r1``
   (responding / processing / listening; HA đặt STT_START → listening, INTENT_START → processing,
   TTS_START → responding);
4. ``dam_thoai`` — có phiên đàm thoại mở mà vệ tinh đang rảnh (giữa hai lượt);
5. ``phat_nhac`` — ``media_player.r1_loa`` đang phát (chỉ khi chức năng này BẬT; tắt thì coi như
   không có nhạc và rơi xuống mục kế);
6. ``cho`` — chờ từ đánh thức (vệ tinh rảnh, không phiên, không nhạc).

Chức năng đang TẮT (``enabled = False``) nghĩa là «lúc đó không có đèn»: tắt cả viền lẫn đáy
(riêng ``phat_nhac`` tắt thì xem như không có nhạc). Mọi ghi đèn đều qua ``_ap_dung`` đã khoá và
đánh số thế hệ: bản mới đến thì bản cũ bỏ, hiệu ứng cũ bị ``stop_effect`` TRƯỚC khi ghi lại.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import asdict, dataclass, replace
from typing import Any

import voluptuous as vol
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store

from .coordinator import R1ConfigEntry
from .const import DOMAIN, LIGHT_ERROR_HOLD_S, LIGHT_PREVIEW_MAX_S, LIGHT_PREVIEW_S
from . import den_firmware as fw
from .den_port import RGB, LightsError, LightsSink, NullLights
from .hieu_ung import HIEU_UNG, KHONG, TOC_DO_MAX, TOC_DO_MIN, dung, sang_rgb, sang_vien

_LOGGER = logging.getLogger(__name__)

#: Thứ tự CỐ ĐỊNH để hiện ra giao diện.
FUNCTIONS = ("cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi", "tat_mic")
#: Ai đứng trước thắng khi nhiều chức năng cùng đúng.
UU_TIEN = ("tat_mic", "loi", "phan_hoi", "nghi", "nghe", "dam_thoai", "phat_nhac", "cho")

#: Lý do ``R1Talk.end`` coi là lỗi (xem dam_thoai.py): đèn «lỗi» nháy một lúc.
LY_DO_LOI = frozenset({"loi", "loi_pipeline", "mic_khong_noi_duoc", "het_gio"})

#: Mã ERROR của pipeline HA nghĩa là «không nghe thấy gì», không phải hỏng: người dùng im lặng hoặc
#: lượt bị cắt. Không làm đèn «lỗi» nháy.
KHONG_PHAI_LOI_HONG = frozenset({"stt-no-text-recognized", "wake-word-timeout"})


def la_loi_that(code: Any) -> bool:
    """Sự kiện ERROR của pipeline có phải hỏng thật (STT/hiểu lệnh/TTS lỗi…) không."""
    return code not in KHONG_PHAI_LOI_HONG


_MAU = re.compile(r"^#?([0-9a-fA-F]{6})$")


def chuan_mau(value: Any) -> str | None:
    """``"#RRGGBB"`` chữ thường, hoặc None nếu không phải 6 số hex."""
    m = _MAU.match(str(value or "").strip())
    return f"#{m.group(1).lower()}" if m else None


def mau_rgb(color: str) -> RGB:
    c = chuan_mau(color) or "#000000"
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))


@dataclass(frozen=True)
class FunctionLight:
    enabled: bool
    rim: bool          # có dùng đèn viền (TRẮNG, cùng độ sáng) không — viền không đổi màu được
    color: str         # màu đèn đáy "#rrggbb"
    effect: str        # ``none`` hoặc id trong ``HIEU_UNG``
    brightness: int    # 0–100
    rim_kieu: int = 0  # kiểu viền chạy đuổi firmware: 0 = không, 1–24 = ID viền (thay hiệu ứng đáy khi bật)
    toc_do: int = 100  # % tốc độ hiệu ứng đổi màu (25–400, 100 = như đề xuất); hiệu ứng gốc của firmware có chu kỳ cố định

    @classmethod
    def from_dict(cls, d: Any, base: "FunctionLight") -> "FunctionLight":
        """Đọc từ dữ liệu đã lưu, giá trị hỏng rơi về ``base`` TỪNG TRƯỜNG (không bỏ cả cấu hình)."""
        if not isinstance(d, dict):
            return base
        bright = d.get("brightness", base.brightness)
        return cls(
            enabled=d["enabled"] if isinstance(d.get("enabled"), bool) else base.enabled,
            rim=d["rim"] if isinstance(d.get("rim"), bool) else base.rim,
            color=chuan_mau(d.get("color")) or base.color,
            effect=d["effect"] if d.get("effect") in (KHONG, *HIEU_UNG) else base.effect,
            brightness=bright if isinstance(bright, int) and not isinstance(bright, bool)
            and 0 <= bright <= 100 else base.brightness,
            rim_kieu=(d["rim_kieu"] if isinstance(d.get("rim_kieu"), int) and not isinstance(d.get("rim_kieu"), bool)
                      and 0 <= d["rim_kieu"] <= 24 else base.rim_kieu),
            toc_do=(d["toc_do"] if isinstance(d.get("toc_do"), int) and not isinstance(d.get("toc_do"), bool)
                    and TOC_DO_MIN <= d["toc_do"] <= TOC_DO_MAX else base.toc_do))


#: MẶC ĐỊNH — ĐỀ XUẤT, CHƯA ĐO (không số nào được nghe/nhìn thử trên loa thật):
#:  * chỉ dùng xanh lá ``00ff00`` / xanh dương ``0000ff`` (hai màu đã xác nhận); ĐỎ (lỗi, tắt mic)
#:    chưa chắc hiện đúng → «lỗi» và «tắt mic» luôn kèm đèn viền trắng để vẫn thấy được;
#:  * «chờ» TẮT (đèn thường trực dễ gây phiền ban đêm), «phát nhạc» TẮT (firmware có đèn nhạc
#:    riêng, lệnh chưa rõ — bật cả hai có thể chồng nhau);
#:  * độ sáng 60 ≈ viền ``99999`` (trắng 0x99); 25 → viền ``404040`` = mức «mờ rõ» đã thấy.
DEFAULTS: dict[str, FunctionLight] = {
    "cho":       FunctionLight(False, False, "#0000ff", KHONG, 20),
    "nghe":      FunctionLight(True, True, "#0000ff", KHONG, 60),
    "nghi":      FunctionLight(True, False, "#0000ff", "tho", 60),
    "phan_hoi":  FunctionLight(True, True, "#00ff00", KHONG, 60),
    "dam_thoai": FunctionLight(True, True, "#00ff00", "tho", 50),
    "phat_nhac": FunctionLight(False, False, "#00ff00", "cau_vong", 40),
    "loi":       FunctionLight(True, True, "#ff0000", "nhap_nhay", 80),
    "tat_mic":   FunctionLight(True, True, "#ff0000", KHONG, 25),
}


@dataclass(frozen=True)
class Signals:
    """Mọi thứ cần để chọn chức năng, đã rút từ trạng thái HA."""

    tat_mic: bool = False
    loi: bool = False
    ve_tinh: str | None = None      # idle | listening | processing | responding | None (chưa có)
    phien: bool = False
    dang_phat: bool = False


def chon_chuc_nang(tin: Signals, profiles: dict[str, FunctionLight]) -> str:
    """Hàm thuần: tín hiệu → chức năng đang hiệu lực (xem ``UU_TIEN``)."""
    if tin.tat_mic:
        return "tat_mic"
    if tin.loi:
        return "loi"
    muc = {"responding": "phan_hoi", "processing": "nghi", "listening": "nghe"}.get(tin.ve_tinh or "")
    if muc:
        return muc
    if tin.phien:
        return "dam_thoai"
    if tin.dang_phat and profiles["phat_nhac"].enabled:
        return "phat_nhac"
    return "cho"


class R1Lights:
    """Bộ điều khiển đèn của MỘT loa (xem docstring module)."""

    def __init__(self, hass: HomeAssistant, entry: R1ConfigEntry, sink: LightsSink | None = None,
                 rng: random.Random | None = None) -> None:
        self.hass, self.entry = hass, entry
        self._sink: LightsSink = sink or NullLights()
        self._rng = rng
        self.profiles: dict[str, FunctionLight] = dict(DEFAULTS)
        #: Độ sáng chung 0–100 (%), nhân vào độ sáng của MỌI chức năng khi ghi xuống đèn.
        self.master = 100
        self.current: str | None = None
        self.last_error: str | None = None
        self._store: Store = Store(hass, 1, f"{DOMAIN}.lights.{entry.entry_id}")
        self._lock = asyncio.Lock()
        self._gen = 0
        self._key: tuple | None = None
        self._tasks: set[asyncio.Task] = set()
        self._unsub: list = []
        self._listeners: list = []
        self._loi = False
        self._loi_huy = None
        self._preview: str | None = None
        self._preview_huy = None
        self._phien_truoc = None
        self._dong = False

    # ── Lưu / nạp ─────────────────────────────────────────────────────────────

    async def async_load(self) -> None:
        data = await self._store.async_load()
        m = (data or {}).get("master") if isinstance(data, dict) else None
        if isinstance(m, int) and not isinstance(m, bool) and 0 <= m <= 100:
            self.master = m
        saved = (data or {}).get("functions") if isinstance(data, dict) else None
        if isinstance(saved, dict):
            for fn in FUNCTIONS:
                if fn in saved:
                    self.profiles[fn] = FunctionLight.from_dict(saved[fn], DEFAULTS[fn])

    def _du_lieu(self) -> dict:
        """Chỉ lưu trường KHÁC mặc định: mặc định đổi sau khi đo thì mục chưa chỉnh tay tự theo."""
        ra = {}
        for fn, p in self.profiles.items():
            diff = {k: v for k, v in asdict(p).items() if v != getattr(DEFAULTS[fn], k)}
            if diff:
                ra[fn] = diff
        return {"functions": ra, **({"master": self.master} if self.master != 100 else {})}

    # ── Sink ──────────────────────────────────────────────────────────────────

    @property
    def sink(self) -> LightsSink:
        return self._sink

    @property
    def sink_state(self) -> str:
        if self._sink.available:
            return "san_sang"
        if isinstance(self._sink, NullLights):
            return "CHO_PHIA_LOA"
        return getattr(self._sink, "ly_do", "mat_ket_noi")

    def set_sink(self, sink: LightsSink | None) -> None:
        """Đổi sink (None = về ``NullLights``) và áp lại đèn hiện tại."""
        self._sink = sink or NullLights()
        self._key = None
        self.evaluate()

    # ── Vòng đời ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Bắt đầu theo dõi vệ tinh, nhạc, phiên, mic. Gọi SAU khi các nền tảng đã đăng ký thực thể."""
        reg = er.async_get(self.hass)
        eid = self.entry.entry_id
        ids = [i for i in (
            reg.async_get_entity_id("assist_satellite", DOMAIN, f"{eid}_satellite"),
            reg.async_get_entity_id("media_player", DOMAIN, f"{eid}_speaker")) if i]
        if ids:
            self._unsub.append(async_track_state_change_event(self.hass, ids, self._khi_doi_trang_thai))
        self._unsub.append(self.entry.runtime_data.talk.add_listener(self._khi_doi_phien))
        self.evaluate()

    async def async_close(self) -> None:
        """Tắt theo dõi, dừng hiệu ứng và tắt đèn (nếu có sink)."""
        self._dong = True
        for u in self._unsub:
            u()
        self._unsub = []
        for huy in (self._loi_huy, self._preview_huy):
            if huy is not None:
                huy()
        self._loi_huy = self._preview_huy = None
        self._gen += 1
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        async with self._lock:
            if self._sink.available:
                try:
                    await self._sink.stop_effect()
                    await self._tat(self._sink)
                except LightsError as exc:
                    _LOGGER.debug("tắt đèn khi đóng: %s", exc)

    def add_listener(self, cb) -> Any:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ── Đọc trạng thái → chức năng ───────────────────────────────────────────

    @callback
    def _khi_doi_trang_thai(self, _event: Event) -> None:
        self.evaluate()

    @callback
    def _khi_doi_phien(self) -> None:
        talk = self.entry.runtime_data.talk
        if self._phien_truoc is not None and talk.session is None and talk.last_end in LY_DO_LOI:
            self.bao_loi()
        self._phien_truoc = talk.session
        self.evaluate()

    def _tin_hieu(self) -> Signals:
        c = self.entry.runtime_data
        reg = er.async_get(self.hass)
        eid = self.entry.entry_id
        sat = reg.async_get_entity_id("assist_satellite", DOMAIN, f"{eid}_satellite")
        mp = reg.async_get_entity_id("media_player", DOMAIN, f"{eid}_speaker")
        st_sat = self.hass.states.get(sat) if sat else None
        st_mp = self.hass.states.get(mp) if mp else None
        return Signals(
            tat_mic=bool(c.mic.muted), loi=self._loi,
            ve_tinh=st_sat.state if st_sat is not None else None,
            phien=c.talk.session is not None,
            dang_phat=st_mp is not None and st_mp.state in ("playing", "buffering"))

    def chuc_nang_hien_tai(self) -> str:
        if self._preview:
            return self._preview
        return chon_chuc_nang(self._tin_hieu(), self.profiles)

    @callback
    def evaluate(self) -> None:
        """Tính lại chức năng đang hiệu lực; đổi (hoặc cài đặt của nó đổi) thì áp xuống sink."""
        if self._dong:
            return
        fn = self.chuc_nang_hien_tai()
        key = (fn, self.profiles[fn], self.master)
        if key == self._key:
            return
        self._key = key
        self.current = fn
        self._gen += 1
        gen = self._gen
        t = self.hass.async_create_task(self._ap_dung(gen, fn))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        self._notify()

    # ── Lỗi / thử ─────────────────────────────────────────────────────────────

    @callback
    def bao_loi(self) -> None:
        """Có lỗi: chức năng «lỗi» sáng ``LIGHT_ERROR_HOLD_S`` giây."""
        if self._loi_huy is not None:
            self._loi_huy()
        self._loi = True
        self._loi_huy = async_call_later(self.hass, LIGHT_ERROR_HOLD_S, self._het_loi)
        self.evaluate()

    @callback
    def _het_loi(self, _now=None) -> None:
        self._loi, self._loi_huy = False, None
        self.evaluate()

    @callback
    def preview(self, fn: str, seconds: float = LIGHT_PREVIEW_S) -> None:
        """Thử chức năng ``fn`` ``seconds`` giây (thẻ cài đặt), rồi trả về trạng thái thật."""
        if fn not in FUNCTIONS:
            raise ServiceValidationError(f"không có chức năng đèn «{fn}»")
        if self._preview_huy is not None:
            self._preview_huy()
        self._preview = fn
        self._preview_huy = async_call_later(
            self.hass, min(max(seconds, 1.0), LIGHT_PREVIEW_MAX_S), self._het_thu)
        self.evaluate()

    @callback
    def _het_thu(self, _now=None) -> None:
        self._preview, self._preview_huy = None, None
        self.evaluate()

    # ── Cài đặt ───────────────────────────────────────────────────────────────

    async def async_set_function(self, fn: str, **fields: Any) -> FunctionLight:
        """Đổi một vài trường của chức năng ``fn``; giá trị sai ném ``ServiceValidationError``."""
        if fn not in self.profiles:
            raise ServiceValidationError(f"không có chức năng đèn «{fn}»")
        new = dict(fields)
        if "color" in new:
            mau = chuan_mau(new["color"])
            if mau is None:
                raise ServiceValidationError("màu phải dạng #rrggbb")
            new["color"] = mau
        if "effect" in new and new["effect"] not in (KHONG, *HIEU_UNG):
            raise ServiceValidationError(f"hiệu ứng «{new['effect']}» không có trong danh mục")
        if "brightness" in new:
            b = new["brightness"]
            if isinstance(b, bool) or not isinstance(b, int) or not 0 <= b <= 100:
                raise ServiceValidationError("độ sáng phải là số nguyên 0–100")
        if "rim_kieu" in new:
            v = new["rim_kieu"]
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 24:
                raise ServiceValidationError("kiểu viền phải là 0 (không) hoặc 1–24")
        if "toc_do" in new:
            v = new["toc_do"]
            if isinstance(v, bool) or not isinstance(v, int) or not TOC_DO_MIN <= v <= TOC_DO_MAX:
                raise ServiceValidationError(f"tốc độ phải là số nguyên {TOC_DO_MIN}–{TOC_DO_MAX} (%)")
        for k in ("enabled", "rim"):
            if k in new and not isinstance(new[k], bool):
                raise ServiceValidationError(f"{k} phải là đúng/sai")
        self.profiles[fn] = replace(self.profiles[fn], **new)
        await self._store.async_save(self._du_lieu())
        self.evaluate()
        self._notify()
        return self.profiles[fn]

    @callback
    def ap_dung_lai(self) -> None:
        """Áp lại đèn hiện tại (loa vừa nối / máy chủ đèn vừa sẵn sàng)."""
        self._key = None
        self.evaluate()

    async def async_set_master(self, level: int) -> None:
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 100:
            raise ServiceValidationError("độ sáng chung phải là số nguyên 0–100")
        self.master = level
        await self._store.async_save(self._du_lieu())
        self.evaluate()
        self._notify()

    async def async_set_music(self, *, enabled: bool | None = None, effect: str | None = None,
                              brightness: int | None = None) -> FunctionLight:
        """Hiệu ứng khi phát nhạc = hồ sơ chức năng ``phat_nhac`` (bật/tắt, hiệu ứng, sáng).

        KHÁC «đèn theo nhạc» CỦA FIRMWARE (``music_light_enable/luma/chroma`` ở get_info): cái đó điều
        khiển bằng ``number.r1_do_sang_den_nhac`` / ``switch.r1_den_nhac`` (qua APK loa). Phần này
        của HA chỉ chạy hiệu ứng khi có dịch vụ đèn trên loa, và chưa đo xem nó có chồng lên đèn nhạc
        firmware hay không."""
        f = {k: v for k, v in (("enabled", enabled), ("effect", effect),
                               ("brightness", brightness)) if v is not None}
        return await self.async_set_function("phat_nhac", **f)

    # ── Áp xuống sink ─────────────────────────────────────────────────────────

    async def _tat(self, sink: LightsSink) -> None:
        if getattr(sink, "firmware", False):
            await sink.tat()
            return
        await sink.set_rim(0)
        await sink.set_base((0, 0, 0))

    async def _ap_dung(self, gen: int, fn: str) -> None:
        async with self._lock:
            if gen != self._gen or self._dong:
                return
            sink, p = self._sink, self.profiles[fn]
            if not sink.available:
                return
            sang = round(p.brightness * self.master / 100)
            try:
                await sink.stop_effect()          # KHÔNG bao giờ để hai nơi cùng ghi đèn
                if not p.enabled:
                    await self._tat(sink)
                elif getattr(sink, "firmware", False) and p.rim_kieu and sang > 0:
                    # Hiệu ứng viền riêng (ID 1–24). Firmware chỉ chạy MỘT hiệu ứng: viền chạy thì đáy của chức năng này tạm nhường.
                    await sink.ap_dung_ham(rim=True, color=mau_rgb(p.color), effect=f"vien_{p.rim_kieu}", sang=sang)
                elif getattr(sink, "firmware", False) and p.effect in getattr(sink, "hieu_ung_goc", ()):
                    # Hiệu ứng GỐC của firmware (một ID): màu gần nhất trong bảng; sáng cố định / thở / nháy; viền trắng.
                    await sink.ap_dung_ham(rim=p.rim, color=mau_rgb(p.color), effect=p.effect, sang=sang)
                elif p.effect != KHONG:
                    await sink.play_effect(
                        dung(p.effect, mau_rgb(p.color), sang, p.rim, self._rng, p.toc_do),
                        repeat=HIEU_UNG[p.effect].lap)
                else:
                    await sink.set_rim(sang_vien(sang) if p.rim else 0)
                    await sink.set_base(sang_rgb(mau_rgb(p.color), sang))
                self.last_error = None
            except LightsError as exc:
                # Ghi một lần mỗi lần ĐỔI lỗi, không ngập log khi loa mất kết nối.
                if str(exc) != self.last_error:
                    _LOGGER.warning("đèn loa R1 (%s): %s", fn, exc)
                self.last_error = str(exc)
            self._notify()

    # ── Thuộc tính cho sensor / thẻ ──────────────────────────────────────────

    def attributes(self) -> dict[str, Any]:
        d = getattr(self.entry.runtime_data, "data", None)
        return {
            "chuc_nang": {fn: {**asdict(p), "mac_dinh": p == DEFAULTS[fn]}
                          for fn, p in self.profiles.items()},
            "thu_tu_uu_tien": list(UU_TIEN),
            "dang_ap_dung": self.current,
            "hieu_ung": [{"id": h.id, "ten": h.ten, "ten_en": h.ten_en, "mo_ta": h.mo_ta,
                          "vien": h.vien, "nguon": h.nguon} for h in HIEU_UNG.values()],
            "dich_vu_den": self.sink_state,
            # Đèn firmware chỉ làm được tập màu/hiệu ứng cố định (None = làm được mọi thứ như sink phần mềm).
            "den_firmware": bool(getattr(self._sink, "firmware", False)),
            "hieu_ung_ho_tro": list(getattr(self._sink, "hieu_ung_ho_tro", None) or []) or None,
            "hieu_ung_goc": list(getattr(self._sink, "hieu_ung_goc", None) or []) or None,
            # Hiệu ứng chỉnh được tốc độ: mọi hiệu ứng HA tự đổi màu theo nhịp; hiệu ứng gốc của firmware (thở/nháy) có chu kỳ cố định.
            "hieu_ung_co_toc_do": [h for h in HIEU_UNG
                                   if h not in (getattr(self._sink, "hieu_ung_goc", None) or ())],
            "toc_do": {"min": TOC_DO_MIN, "max": TOC_DO_MAX, "mac_dinh": 100},
            "bang_mau_firmware": [{"ten": m.ten, "ten_en": m.ten_en, "rgb": "#%02x%02x%02x" % m.rgb,
                                   "tho": m.tho is not None} for m in fw.MAU.values()],
            "do_sang_chung": self.master,
            "loi_dich_vu": self.last_error,
            # Đèn theo nhạc CỦA FIRMWARE: đọc ở đây; điều khiển bằng các thực thể ``r1_*_den_nhac`` (qua APK).
            "den_nhac_firmware": {
                "bat": getattr(d, "music_light_enable", None),
                "luma": getattr(d, "music_light_luma", None),
                "chroma": getattr(d, "music_light_chroma", None),
                "dieu_khien": "qua_apk_msgcenter"},
        }


# ── Dịch vụ ───────────────────────────────────────────────────────────────────

def _lights_cua(hass: HomeAssistant, entity_id: str) -> R1Lights:
    rec = er.async_get(hass).async_get(entity_id)
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker")
    lights = getattr(getattr(entry, "runtime_data", None), "lights", None)
    if lights is None:
        raise ServiceValidationError(f"{entity_id}: loa chưa nạp xong")
    return lights


_EFFECTS = [KHONG, *HIEU_UNG]
_BRIGHT = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
_TOC_DO = vol.All(vol.Coerce(int), vol.Range(min=TOC_DO_MIN, max=TOC_DO_MAX))
_COLOR = vol.All(str, vol.Match(_MAU, msg="màu phải dạng #rrggbb"))

SET_FUNCTION_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Required("function"): vol.In(list(FUNCTIONS)),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("rim"): cv.boolean,
    vol.Optional("color"): _COLOR,
    vol.Optional("effect"): vol.In(_EFFECTS),
    vol.Optional("brightness"): _BRIGHT,
    vol.Optional("toc_do"): _TOC_DO,
    vol.Optional("rim_kieu"): vol.All(vol.Coerce(int), vol.Range(min=0, max=24)),
})
SET_MUSIC_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("effect"): vol.In(_EFFECTS),
    vol.Optional("brightness"): _BRIGHT,
})
PREVIEW_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Required("function"): vol.In(list(FUNCTIONS)),
    vol.Optional("seconds"): vol.All(vol.Coerce(float), vol.Range(min=1, max=LIGHT_PREVIEW_MAX_S)),
})


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _dat_chuc_nang(call: ServiceCall) -> None:
        d = dict(call.data)
        lights = _lights_cua(hass, d.pop("entity_id"))
        await lights.async_set_function(d.pop("function"), **d)

    async def _dat_den_nhac(call: ServiceCall) -> None:
        d = dict(call.data)
        await _lights_cua(hass, d.pop("entity_id")).async_set_music(**d)

    async def _thu_den(call: ServiceCall) -> None:
        _lights_cua(hass, call.data["entity_id"]).preview(
            call.data["function"], call.data.get("seconds", LIGHT_PREVIEW_S))

    hass.services.async_register(DOMAIN, "set_light_function", _dat_chuc_nang,
                                 schema=SET_FUNCTION_SCHEMA)
    hass.services.async_register(DOMAIN, "set_music_light", _dat_den_nhac, schema=SET_MUSIC_SCHEMA)
    hass.services.async_register(DOMAIN, "preview_light", _thu_den, schema=PREVIEW_SCHEMA)
