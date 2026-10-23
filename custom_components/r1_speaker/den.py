"""Đèn LED của loa R1 theo CHỨC NĂNG: cài đặt, chọn chức năng đang hiệu lực, áp xuống sink.

Tám chức năng (``FUNCTIONS``). Mỗi chức năng có: bật/tắt, và HAI VÙNG độc lập — ``day`` (15 đèn RGB) và ``vien``
(24 đèn chỉ trắng) — mỗi vùng một hiệu ứng kèm bộ thông số RIÊNG của hiệu ứng đó (danh mục ở ``den_hieu_ung.py``, thẻ
cài đặt vẽ form từ danh mục). Chức năng đang hiệu lực chọn theo ``UU_TIEN`` (đứng trước thắng):

1. ``tat_mic`` — mic đang tắt (luôn thắng: người dùng phải thấy mic không nghe);
2. ``loi`` — phiên đóng vì lỗi / pipeline báo lỗi, giữ ``LIGHT_ERROR_HOLD_S`` giây;
3. ``phan_hoi`` / ``nghi`` / ``nghe`` — theo trạng thái ``assist_satellite.r1``
   (responding / processing / listening; HA đặt STT_START → listening, INTENT_START → processing,
   TTS_START → responding);
4. ``dam_thoai`` — có phiên đàm thoại mở mà vệ tinh đang rảnh (giữa hai lượt);
5. ``phat_nhac`` — ``media_player.r1_loa`` đang phát (chỉ khi chức năng này BẬT);
6. ``cho`` — chờ từ đánh thức (vệ tinh rảnh, không phiên, không nhạc).

Chức năng đang TẮT (``enabled = False``) nghĩa là «lúc đó không có đèn»: tắt cả hai vùng (riêng ``phat_nhac`` tắt thì
xem như không có nhạc).

**Thử** (``thu``) là MỤC RIÊNG, không nằm trong cài đặt chức năng: phủ một hiệu ứng tạm lên một vùng trong vài giây
rồi tự trả về trạng thái thật; không lưu gì. Mọi ghi đèn đều qua ``_ap_dung`` đã khoá và đánh số thế hệ: bản mới đến
thì bản cũ bỏ.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
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
from .den_hieu_ung import EFFECTS, TAT, VUNG, VUNG_DAY, VUNG_VIEN, chuan_hoa, danh_muc, loc_hop_le
from .den_port import LightsError, LightsSink, NullLights

_LOGGER = logging.getLogger(__name__)

#: Thứ tự CỐ ĐỊNH để hiện ra giao diện.
FUNCTIONS = ("cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi", "tat_mic")
#: Ai đứng trước thắng khi nhiều chức năng cùng đúng.
UU_TIEN = ("tat_mic", "loi", "phan_hoi", "nghi", "nghe", "dam_thoai", "phat_nhac", "cho")
#: Sau lỗi ADB, thử áp lại đèn sau ngần này giây.
THU_LAI_S = 15.0

#: Lý do ``R1Talk.end`` coi là lỗi (xem dam_thoai.py): đèn «lỗi» nháy một lúc.
LY_DO_LOI = frozenset({"loi", "loi_pipeline", "mic_khong_noi_duoc", "het_gio"})

#: Mã ERROR của pipeline HA nghĩa là «không nghe thấy gì», không phải hỏng: người dùng im lặng hoặc
#: lượt bị cắt. Không làm đèn «lỗi» nháy.
KHONG_PHAI_LOI_HONG = frozenset({"stt-no-text-recognized", "wake-word-timeout"})


def la_loi_that(code: Any) -> bool:
    """Sự kiện ERROR của pipeline có phải hỏng thật (STT/hiểu lệnh/TTS lỗi…) không."""
    return code not in KHONG_PHAI_LOI_HONG




@dataclass(frozen=True)
class Zone:
    """Một vùng đèn: ``effect`` (``tat`` hoặc id trong danh mục của vùng) + bộ thông số ĐẦY ĐỦ của hiệu ứng đó."""

    effect: str = TAT
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"effect": self.effect, "params": dict(self.params)}


def tao_vung(vung: str, effect: str, params: Any = None) -> Zone:
    """Vùng hợp lệ; ``ValueError`` nếu hiệu ứng không có trong danh mục của vùng."""
    return Zone(effect, chuan_hoa(vung, effect, params))


def vung_tu_dict(vung: str, d: Any, base: Zone) -> Zone:
    """Đọc từ dữ liệu đã lưu / gọi dịch vụ. Chỉ ``params`` đổi: giữ hiệu ứng, trộn vào thông số hiện có.
    Hỏng thì rơi về ``base`` (không bỏ cả cấu hình)."""
    if not isinstance(d, dict):
        return base
    effect = d.get("effect", base.effect)
    if effect != TAT and effect not in EFFECTS[vung]:
        return base
    goc = base.params if effect == base.effect else {}
    return tao_vung(vung, effect, {**goc, **loc_hop_le(vung, effect, d.get("params"))})


@dataclass(frozen=True)
class FunctionLight:
    enabled: bool
    day: Zone
    vien: Zone

    def zone(self, vung: str) -> Zone:
        return self.day if vung == VUNG_DAY else self.vien

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "day": self.day.to_dict(), "vien": self.vien.to_dict()}

    @classmethod
    def from_dict(cls, d: Any, base: "FunctionLight") -> "FunctionLight":
        """Giá trị hỏng rơi về ``base`` TỪNG TRƯỜNG."""
        if not isinstance(d, dict):
            return base
        return cls(
            enabled=d["enabled"] if isinstance(d.get("enabled"), bool) else base.enabled,
            day=vung_tu_dict(VUNG_DAY, d.get("day"), base.day),
            vien=vung_tu_dict(VUNG_VIEN, d.get("vien"), base.vien))


def _z(vung: str, effect: str, **p: Any) -> Zone:
    return tao_vung(vung, effect, p)


#: MẶC ĐỊNH (đề xuất, chủ máy chỉnh được): «chờ» và «phát nhạc» tắt; các chức năng khác sáng đáy một màu + viền trắng.
DEFAULTS: dict[str, FunctionLight] = {
    "cho":       FunctionLight(False, _z(VUNG_DAY, "co_dinh", mau="#0000ff", do_sang=20), Zone()),
    "nghe":      FunctionLight(True, _z(VUNG_DAY, "co_dinh", mau="#0000ff", do_sang=60), _z(VUNG_VIEN, "sang", do_sang=60)),
    "nghi":      FunctionLight(True, _z(VUNG_DAY, "tho", mau="#0000ff", do_sang=60), Zone()),
    "phan_hoi":  FunctionLight(True, _z(VUNG_DAY, "co_dinh", mau="#00ff00", do_sang=60), _z(VUNG_VIEN, "sang", do_sang=60)),
    "dam_thoai": FunctionLight(True, _z(VUNG_DAY, "tho", mau="#00ff00", do_sang=50), _z(VUNG_VIEN, "sang", do_sang=50)),
    "phat_nhac": FunctionLight(False, _z(VUNG_DAY, "cau_vong", do_sang=40), Zone()),
    "loi":       FunctionLight(True, _z(VUNG_DAY, "nhap_nhay", mau="#ff0000", do_sang=80), _z(VUNG_VIEN, "sang", do_sang=80)),
    "tat_mic":   FunctionLight(True, _z(VUNG_DAY, "co_dinh", mau="#ff0000", do_sang=25), _z(VUNG_VIEN, "sang", do_sang=25)),
}

#: Mặc định của BẢN LƯU CŨ (mô hình phẳng: rim/color/effect/brightness/rim_kieu/toc_do) — chỉ để chuyển cài đặt cũ.
_CU_MAC_DINH = {
    "cho": (False, False, "#0000ff", "none", 20), "nghe": (True, True, "#0000ff", "none", 60),
    "nghi": (True, False, "#0000ff", "tho", 60), "phan_hoi": (True, True, "#00ff00", "none", 60),
    "dam_thoai": (True, True, "#00ff00", "tho", 50), "phat_nhac": (False, False, "#00ff00", "cau_vong", 40),
    "loi": (True, True, "#ff0000", "nhap_nhay", 80), "tat_mic": (True, True, "#ff0000", "none", 25),
}


def tu_ban_luu_cu(fn: str, d: dict[str, Any]) -> FunctionLight:
    """Chuyển cài đặt phẳng đã lưu (chỉ chứa trường khác mặc định cũ) sang mô hình hai vùng."""
    en, rim, mau, eff, sang = _CU_MAC_DINH[fn]
    en = d["enabled"] if isinstance(d.get("enabled"), bool) else en
    rim = d["rim"] if isinstance(d.get("rim"), bool) else rim
    mau = d.get("color") or mau
    eff = d.get("effect") or eff
    b = d.get("brightness")
    sang = b if isinstance(b, int) and not isinstance(b, bool) and 0 <= b <= 100 else sang
    toc = d.get("toc_do") if isinstance(d.get("toc_do"), int) else 100
    kieu = d.get("rim_kieu") if isinstance(d.get("rim_kieu"), int) else 0
    if eff == "none":
        day = tao_vung(VUNG_DAY, "co_dinh", {"mau": mau, "do_sang": sang}) if sang > 0 else Zone()
    elif eff in EFFECTS[VUNG_DAY]:
        day = tao_vung(VUNG_DAY, eff, {"mau": mau, "do_sang": sang, "toc_do": toc})
    else:
        day = Zone()
    if kieu:
        vien = tao_vung(VUNG_VIEN, "chay_duoi", {"do_sang": sang, "toc_do": toc})
    elif rim:
        vien = tao_vung(VUNG_VIEN, "sang", {"do_sang": sang})
    else:
        vien = Zone()
    return FunctionLight(en, day, vien)


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
        #: Độ sáng chung 0–100 (%), nhân vào độ sáng của MỌI hiệu ứng khi ghi xuống đèn.
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
        #: Hiệu ứng THỬ đang phủ lên từng vùng: ``{vùng: Zone}`` (mục riêng, không lưu).
        self._thu: dict[str, Zone] = {}
        self._thu_huy = None
        self._thu_lai_huy = None
        self._phien_truoc = None
        self._dong = False

    # ── Lưu / nạp ────────────────────────────────────────────────

    async def async_load(self) -> None:
        data = await self._store.async_load()
        m = (data or {}).get("master") if isinstance(data, dict) else None
        if isinstance(m, int) and not isinstance(m, bool) and 0 <= m <= 100:
            self.master = m
        saved = (data or {}).get("functions") if isinstance(data, dict) else None
        if isinstance(saved, dict):
            for fn in FUNCTIONS:
                d = saved.get(fn)
                if not isinstance(d, dict):
                    continue
                if "day" in d or "vien" in d:
                    self.profiles[fn] = FunctionLight.from_dict(d, DEFAULTS[fn])
                else:                                              # bản lưu cũ (mô hình phẳng)
                    self.profiles[fn] = tu_ban_luu_cu(fn, d)

    def _du_lieu(self) -> dict:
        """Chỉ lưu chức năng KHÁC mặc định: mặc định đổi sau này thì mục chưa chỉnh tay tự theo."""
        ra = {fn: p.to_dict() for fn, p in self.profiles.items() if p != DEFAULTS[fn]}
        return {"functions": ra, **({"master": self.master} if self.master != 100 else {})}

    # ── Sink ──────────────────────────────────────────────────�

    @property
    def sink(self) -> LightsSink:
        return self._sink

    @property
    def sink_state(self) -> str:
        if isinstance(self._sink, NullLights):
            return "CHO_PHIA_LOA"
        return "san_sang" if self.last_error is None else "loi_adb"

    def set_sink(self, sink: LightsSink | None) -> None:
        """Đổi sink (None = về ``NullLights``) và áp lại đèn hiện tại."""
        self._sink = sink or NullLights()
        self._key = None
        self.evaluate()

    # ── Vòng đời ────────────────────────────────────────────────

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
        """Tắt theo dõi, dừng hiệu ứng và tắt đèn."""
        self._dong = True
        for u in self._unsub:
            u()
        self._unsub = []
        for huy in (self._loi_huy, self._thu_huy, self._thu_lai_huy):
            if huy is not None:
                huy()
        self._loi_huy = self._thu_huy = self._thu_lai_huy = None
        self._gen += 1
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        async with self._lock:
            try:
                await self._sink.tat()
                await self._sink.dung()
            except LightsError as exc:
                _LOGGER.debug("tắt đèn khi đóng: %s", exc)

    def add_listener(self, cb) -> Any:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    # ── Đọc trạng thái → chức năng ───────────────────────────────────────�

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
        return chon_chuc_nang(self._tin_hieu(), self.profiles)

    def _viec_can_lam(self, fn: str) -> dict[str, Zone]:
        """Hiệu ứng mỗi vùng NÊN chạy: chức năng (hoặc tắt) rồi mục Thử phủ lên."""
        p = self.profiles[fn]
        ra = {v: (p.zone(v) if p.enabled else Zone()) for v in VUNG}
        ra.update(self._thu)
        return ra

    @callback
    def evaluate(self) -> None:
        """Tính lại chức năng đang hiệu lực; đổi (hoặc cài đặt của nó đổi) thì áp xuống sink."""
        if self._dong:
            return
        fn = self.chuc_nang_hien_tai()
        viec = self._viec_can_lam(fn)
        key = (fn, tuple((v, z.effect, tuple(sorted(z.params.items()))) for v, z in viec.items()), self.master)
        if key == self._key:
            return
        self._key = key
        self.current = fn
        self._gen += 1
        gen = self._gen
        t = self.hass.async_create_task(self._ap_dung(gen, viec))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        self._notify()

    # ── Lỗi / thử ───────────────────────────────────────────────�

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
    def thu(self, vung: str, effect: str, params: Any = None, seconds: float = LIGHT_PREVIEW_S) -> None:
        """THỬ một hiệu ứng ở ``vung`` ``seconds`` giây (mục Thử của thẻ), rồi tự trả về trạng thái thật. Không lưu."""
        if vung not in VUNG:
            raise ServiceValidationError(f"vùng đèn phải là {', '.join(VUNG)}")
        try:
            z = tao_vung(vung, effect, params)
        except ValueError as exc:
            raise ServiceValidationError(str(exc)) from exc
        if self._thu_huy is not None:
            self._thu_huy()
        self._thu[vung] = z
        self._thu_huy = async_call_later(self.hass, min(max(seconds, 1.0), LIGHT_PREVIEW_MAX_S), self._het_thu)
        self.evaluate()
        self._notify()

    @callback
    def dung_thu(self) -> None:
        self._het_thu()

    @callback
    def _het_thu(self, _now=None) -> None:
        if self._thu_huy is not None:
            self._thu_huy()
        self._thu, self._thu_huy = {}, None
        self.evaluate()
        self._notify()

    # ── Cài đặt ────────────────────────────────────────────────�

    async def async_set_function(self, fn: str, *, enabled: Any = None, day: Any = None, vien: Any = None) -> FunctionLight:
        """Đổi ``enabled`` và/hoặc một vùng của chức năng ``fn``. Mỗi vùng là ``{"effect": ..., "params": {...}}``;
        đổi hiệu ứng thì thông số về mặc định của hiệu ứng mới (trừ phần gửi kèm); giá trị sai ném ``ServiceValidationError``."""
        if fn not in self.profiles:
            raise ServiceValidationError(f"không có chức năng đèn «{fn}»")
        cu = self.profiles[fn]
        if enabled is not None and not isinstance(enabled, bool):
            raise ServiceValidationError("enabled phải là đúng/sai")
        zones = {}
        for vung, d in ((VUNG_DAY, day), (VUNG_VIEN, vien)):
            if d is None:
                continue
            if not isinstance(d, dict):
                raise ServiceValidationError(f"{vung} phải là {{effect, params}}")
            eff = d.get("effect", cu.zone(vung).effect)
            if eff != TAT and eff not in EFFECTS[vung]:
                raise ServiceValidationError(f"hiệu ứng «{eff}» không có ở vùng {vung}")
            zones[vung] = vung_tu_dict(vung, d, cu.zone(vung))
        self.profiles[fn] = FunctionLight(cu.enabled if enabled is None else enabled,
                                          zones.get(VUNG_DAY, cu.day), zones.get(VUNG_VIEN, cu.vien))
        await self._store.async_save(self._du_lieu())
        self.evaluate()
        self._notify()
        return self.profiles[fn]

    @callback
    def ap_dung_lai(self) -> None:
        """Áp lại đèn hiện tại (loa vừa nối / ADB vừa nối lại)."""
        self._key = None
        self.evaluate()

    async def async_set_master(self, level: int) -> None:
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 100:
            raise ServiceValidationError("độ sáng chung phải là số nguyên 0–100")
        self.master = level
        await self._store.async_save(self._du_lieu())
        self.evaluate()
        self._notify()

    # ── Áp xuống sink ──────────────────────────────────────────────�

    async def _ap_dung(self, gen: int, viec: dict[str, Zone]) -> None:
        async with self._lock:
            if gen != self._gen or self._dong:
                return
            sink = self._sink
            if not sink.available:
                return
            try:
                for vung in VUNG:
                    z = viec[vung]
                    await sink.ap_dung(vung, z.effect, z.params, self.master)
                self.last_error = None
                if self._thu_lai_huy is not None:
                    self._thu_lai_huy()
                    self._thu_lai_huy = None
            except LightsError as exc:
                # Ghi một lần mỗi lần ĐỔI lỗi, không ngập log khi loa mất kết nối; tự thử lại sau ``THU_LAI_S``.
                if str(exc) != self.last_error:
                    _LOGGER.warning("đèn loa R1: %s", exc)
                self.last_error = str(exc)
                if self._thu_lai_huy is None and not self._dong:
                    self._thu_lai_huy = async_call_later(self.hass, THU_LAI_S, self._thu_lai)
            self._notify()

    @callback
    def _thu_lai(self, _now=None) -> None:
        self._thu_lai_huy = None
        self.ap_dung_lai()

    # ── Thuộc tính cho sensor / thẻ ─────────────────────────────────────────�

    def attributes(self) -> dict[str, Any]:
        d = getattr(self.entry.runtime_data, "data", None)
        dev = getattr(self._sink, "dev", None)
        return {
            "chuc_nang": {fn: {**p.to_dict(), "mac_dinh": p == DEFAULTS[fn]} for fn, p in self.profiles.items()},
            "thu_tu_uu_tien": list(UU_TIEN),
            "dang_ap_dung": self.current,
            "danh_muc": danh_muc(),
            "dich_vu_den": self.sink_state,
            "duong_adb": getattr(dev, "duong", None),
            "che_do_adb": getattr(dev, "mode", None),
            "thu": {v: z.to_dict() for v, z in self._thu.items()},
            "do_sang_chung": self.master,
            "loi_dich_vu": self.last_error,
            # Đèn theo nhạc CỦA FIRMWARE (khác hiệu ứng ở trên): đọc ở đây; điều khiển bằng các thực thể ``r1_*_den_nhac``.
            "den_nhac_firmware": {
                "bat": getattr(d, "music_light_enable", None),
                "luma": getattr(d, "music_light_luma", None),
                "chroma": getattr(d, "music_light_chroma", None),
                "dieu_khien": "qua_apk_msgcenter"},
        }


# ── Dịch vụ ─────────────────────────────────────────────────�

def _lights_cua(hass: HomeAssistant, entity_id: str) -> R1Lights:
    rec = er.async_get(hass).async_get(entity_id)
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker")
    lights = getattr(getattr(entry, "runtime_data", None), "lights", None)
    if lights is None:
        raise ServiceValidationError(f"{entity_id}: loa chưa nạp xong")
    return lights


_ZONE = vol.Schema({vol.Optional("effect"): str, vol.Optional("params"): dict})

SET_FUNCTION_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Required("function"): vol.In(list(FUNCTIONS)),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("day"): _ZONE,
    vol.Optional("vien"): _ZONE,
})
PREVIEW_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Required("zone"): vol.In(list(VUNG)),
    vol.Required("effect"): str,
    vol.Optional("params"): dict,
    vol.Optional("seconds"): vol.All(vol.Coerce(float), vol.Range(min=1, max=LIGHT_PREVIEW_MAX_S)),
})
STOP_PREVIEW_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_id})


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _dat_chuc_nang(call: ServiceCall) -> None:
        d = dict(call.data)
        lights = _lights_cua(hass, d.pop("entity_id"))
        await lights.async_set_function(d.pop("function"), **d)

    async def _thu_den(call: ServiceCall) -> None:
        d = call.data
        _lights_cua(hass, d["entity_id"]).thu(d["zone"], d["effect"], d.get("params"),
                                              d.get("seconds", LIGHT_PREVIEW_S))

    async def _dung_thu(call: ServiceCall) -> None:
        _lights_cua(hass, call.data["entity_id"]).dung_thu()

    hass.services.async_register(DOMAIN, "set_light_function", _dat_chuc_nang, schema=SET_FUNCTION_SCHEMA)
    hass.services.async_register(DOMAIN, "preview_light", _thu_den, schema=PREVIEW_SCHEMA)
    hass.services.async_register(DOMAIN, "stop_preview_light", _dung_thu, schema=STOP_PREVIEW_SCHEMA)
