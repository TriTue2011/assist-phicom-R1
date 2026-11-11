"""Phím trên loa R1: cử chỉ (nhấn đơn / đúp / ba / giữ) → hành động do người dùng chọn, và thêm hành động mới chỉ bằng một hàm.

Nguồn cử chỉ: APK 1.3 báo phím THÔ (``phim``: mã phím, nhấn/nhả) qua dịch vụ trợ năng của nó; HA tự nhận diện cử chỉ bằng ``NhanDien``
(khoảng nhấn nhiều lần, ngưỡng giữ). Đo thật 28/10/2026 trên loa (``getevent``): nút giữa là /dev/input/event0, mã 0xC3 = 195; nhấn đơn ~0,2 giây, các lần
nhấn nhanh cách nhau ~0,2 giây, giữ ~1,65 giây. Bộ nhận diện cử chỉ của firmware (``userdefkeyservice``, ``msgcenter`` nhóm 256) đăng ký được
nhưng KHÔNG gửi gì khi ứng dụng gốc đã bị ẩn («Chuẩn bị loa»), nên không dùng.

Mỗi cử chỉ luôn phát sự kiện ``event.r1_phim`` (để dùng trong tự động hoá). Hành động tích hợp chỉ chạy với mã phím trong tuỳ chọn ``phim_ma``
(mặc định 195 = nút giữa) để thanh cảm ứng hay phím nguồn không vô tình chạy lệnh.

**Thêm hành động mới:** viết một hàm ``async def ten(ctx: PhimCtx) -> None`` rồi gắn ``@hanh_dong("ten", vi="…", en="…")``; hành động tự xuất hiện trong
bốn ô chọn (``select.r1_phim_*``), không phải sửa chỗ nào khác."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, SU_KIEN_PHIM

_LOGGER = logging.getLogger(__name__)

#: Bốn cử chỉ gán được hành động; ``nhan_ngan`` (firmware báo thêm) chỉ phát sự kiện.
CU_CHI = ("don", "doi", "ba", "giu")
CU_CHI_SU_KIEN = CU_CHI + ("nhan_ngan",)
MA_NUT_GIUA = 195
#: Đường thô: trong khoảng này (ms) sau lần nhả, nhấn tiếp thì tính cùng một cử chỉ nhiều lần; giữ quá ngưỡng này (ms) là «giữ».
KHOANG_NHAN_MS = 450
NGUONG_GIU_MS = 800


@dataclass
class PhimCtx:
    """Ngữ cảnh một lần chạy hành động."""

    hass: HomeAssistant
    entry: Any
    coordinator: Any
    ma: int
    cu_chi: str

    def thuc_the(self, domain: str, khoa: str) -> str | None:
        """entity_id của thực thể do tích hợp này tạo (theo unique_id ``<entry_id>_<khoá>``)."""
        return er.async_get(self.hass).async_get_entity_id(domain, DOMAIN, f"{self.entry.entry_id}_{khoa}")

    async def goi(self, domain: str, dich_vu: str, **data: Any) -> None:
        await self.hass.services.async_call(domain, dich_vu, data, blocking=True)


@dataclass(frozen=True)
class HanhDong:
    ten: str
    vi: str
    en: str
    ham: Callable[[PhimCtx], Awaitable[None]]


_DANG_KY: dict[str, HanhDong] = {}


def hanh_dong(ten: str, *, vi: str, en: str):
    """Đăng ký một hành động cho phím. Tên là định danh ổn định (lưu trong ô chọn), không đổi sau khi phát hành."""
    def gan(ham):
        if ten in _DANG_KY:
            raise ValueError(f"hành động phím trùng tên: {ten}")
        _DANG_KY[ten] = HanhDong(ten, vi, en, ham)
        return ham
    return gan


def danh_sach() -> list[str]:
    return list(_DANG_KY)


def nhan(ten: str, ngon_ngu: str = "vi") -> str:
    h = _DANG_KY.get(ten)
    return ten if h is None else (h.vi if ngon_ngu == "vi" else h.en)


# ── Hành động tích hợp ────────────────────────────────────────────────

@hanh_dong("khong_lam_gi", vi="Không làm gì (chỉ phát sự kiện)", en="Do nothing (event only)")
async def _khong_lam_gi(ctx: PhimCtx) -> None:
    return None


async def _doi_cong_tat(ctx: PhimCtx, khoa: str) -> None:
    ent = ctx.thuc_the("switch", khoa)
    if ent is None:
        raise RuntimeError(f"chưa có công tắc {khoa}")
    await ctx.goi("switch", "toggle", entity_id=ent)


@hanh_dong("bat_tat_mic", vi="Bật/tắt mic (Tắt mic)", en="Toggle mic (Mute mic)")
async def _bat_tat_mic(ctx: PhimCtx) -> None:
    await _doi_cong_tat(ctx, "mute")


@hanh_dong("bat_tat_bluetooth", vi="Bật/tắt Bluetooth", en="Toggle Bluetooth")
async def _bat_tat_bluetooth(ctx: PhimCtx) -> None:
    await _doi_cong_tat(ctx, "bluetooth")


@hanh_dong("bat_tat_dam_thoai", vi="Bật/tắt đàm thoại (bộ đàm)", en="Toggle intercom")
async def _bat_tat_dam_thoai(ctx: PhimCtx) -> None:
    await _doi_cong_tat(ctx, "intercom_open")


@hanh_dong("bat_tat_assist", vi="Bật/tắt Assist (từ đánh thức)", en="Toggle Assist (wake word)")
async def _bat_tat_assist(ctx: PhimCtx) -> None:
    await _doi_cong_tat(ctx, "assist")


@hanh_dong("bat_tat_den_nhac", vi="Bật/tắt đèn theo nhạc", en="Toggle music light")
async def _bat_tat_den_nhac(ctx: PhimCtx) -> None:
    await _doi_cong_tat(ctx, "music_light")


@hanh_dong("bao_thuc_hoac_dam_thoai", vi="Tắt báo thức đang kêu; không có thì bật/tắt đàm thoại", en="Dismiss ringing alarm, else toggle intercom")
async def _bao_thuc_hoac_dam_thoai(ctx: PhimCtx) -> None:
    bt = getattr(ctx.coordinator, "bao_thuc", None)
    if bt is not None and bt.dang_keu is not None:
        await bt.tat()
        return
    await _doi_cong_tat(ctx, "intercom_open")


async def _loa(ctx: PhimCtx) -> str:
    ent = ctx.thuc_the("media_player", "speaker")
    if ent is None:
        raise RuntimeError("chưa có thực thể loa")
    return ent


#: Loại thực thể mà phím được phép kích hoạt → (miền dịch vụ, tên dịch vụ, dữ liệu thêm). Cố ý là danh sách đóng: phím trên loa
#: không được gọi tuỳ ý dịch vụ nào của HA (khoá cửa, báo động…) — muốn làm việc đó thì viết một script rồi chọn script.
KICH_HOAT = {
    "script": ("script", "turn_on", {}),
    "automation": ("automation", "trigger", {"skip_condition": True}),
    "scene": ("scene", "turn_on", {}),
    "button": ("button", "press", {}),
    "input_button": ("input_button", "press", {}),
}


def kich_hoat(entity_id: str) -> tuple[str, str, dict[str, Any]] | None:
    """(miền, dịch vụ, dữ liệu) để kích hoạt thực thể ``entity_id``, hoặc None nếu loại này không được phép."""
    return KICH_HOAT.get(entity_id.split(".", 1)[0]) if "." in entity_id else None


@hanh_dong("chay_thuc_the", vi="Chạy script / tự động hoá / cảnh / nút đã chọn", en="Run the chosen script / automation / scene / button")
async def _chay_thuc_the(ctx: PhimCtx) -> None:
    dich = ctx.coordinator.phim.dich.get(ctx.cu_chi, "")
    if not dich:
        raise RuntimeError(f"chưa chọn thực thể cho cử chỉ «{ctx.cu_chi}»")
    cach = kich_hoat(dich)
    if cach is None:
        raise RuntimeError(f"{dich}: loại này không được phím kích hoạt")
    domain, dich_vu, them = cach
    if ctx.hass.states.get(dich) is None:
        raise RuntimeError(f"{dich} không còn trong HA")
    # Không chờ (blocking=False): script dài (gọi nhóm loa, gọi thoại) không được giữ bộ nhận diện phím.
    await ctx.hass.services.async_call(domain, dich_vu, {"entity_id": dich, **them}, blocking=False)


@hanh_dong("phat_tam_dung", vi="Phát / tạm dừng nhạc", en="Play / pause")
async def _phat_tam_dung(ctx: PhimCtx) -> None:
    await ctx.goi("media_player", "media_play_pause", entity_id=await _loa(ctx))


@hanh_dong("dung_nhac", vi="Dừng nhạc", en="Stop music")
async def _dung_nhac(ctx: PhimCtx) -> None:
    await ctx.goi("media_player", "media_stop", entity_id=await _loa(ctx))


@hanh_dong("bai_ke", vi="Bài kế tiếp", en="Next track")
async def _bai_ke(ctx: PhimCtx) -> None:
    await ctx.goi("media_player", "media_next_track", entity_id=await _loa(ctx))


@hanh_dong("bai_truoc", vi="Bài trước", en="Previous track")
async def _bai_truoc(ctx: PhimCtx) -> None:
    await ctx.goi("media_player", "media_previous_track", entity_id=await _loa(ctx))


@hanh_dong("tang_am_luong", vi="Tăng âm lượng", en="Volume up")
async def _tang_am_luong(ctx: PhimCtx) -> None:
    await ctx.goi("media_player", "volume_up", entity_id=await _loa(ctx))


@hanh_dong("giam_am_luong", vi="Giảm âm lượng", en="Volume down")
async def _giam_am_luong(ctx: PhimCtx) -> None:
    await ctx.goi("media_player", "volume_down", entity_id=await _loa(ctx))


@hanh_dong("tat_tieng_loa", vi="Tắt/bật tiếng loa", en="Mute / unmute speaker")
async def _tat_tieng_loa(ctx: PhimCtx) -> None:
    ent = await _loa(ctx)
    st = ctx.hass.states.get(ent)
    dang_tat = bool(st and st.attributes.get("is_volume_muted"))
    await ctx.goi("media_player", "volume_mute", entity_id=ent, is_volume_muted=not dang_tat)


@hanh_dong("bao_thuc_dung", vi="Tắt báo thức đang kêu", en="Dismiss ringing alarm")
async def _bao_thuc_dung(ctx: PhimCtx) -> None:
    bt = getattr(ctx.coordinator, "bao_thuc", None)
    if bt is not None:
        await bt.tat()


@hanh_dong("bao_thuc_hoan", vi="Báo thức: hoãn (báo lại sau)", en="Alarm: snooze")
async def _bao_thuc_hoan(ctx: PhimCtx) -> None:
    bt = getattr(ctx.coordinator, "bao_thuc", None)
    if bt is not None:
        await bt.hoan()


@hanh_dong("hen_gio_tat_nhac_30", vi="Hẹn giờ tắt nhạc 30 phút (nhỏ dần)", en="Sleep timer 30 min (fade out)")
async def _hen_gio_30(ctx: PhimCtx) -> None:
    bt = getattr(ctx.coordinator, "bao_thuc", None)
    if bt is not None:
        await bt.hen_gio_tat_nhac(30)


# ── Nhận diện cử chỉ từ phím thô ─────────────────────────────────────

class NhanDien:
    """Từ chuỗi nhấn/nhả thô của một mã phím ra cử chỉ: đơn, đúp, ba (nhấn nhiều lần trong ``khoang_ms``), giữ (giữ quá ``giu_ms``).

    Bộ hẹn giờ được tiêm vào (``hen(giay, hàm) -> hàm_huỷ``) nên kiểm được bằng đồng hồ giả."""

    def __init__(self, tren_cu_chi: Callable[[int, str], None], hen: Callable[[float, Callable[[], None]], Callable[[], None]],
                 *, khoang_ms: int = KHOANG_NHAN_MS, giu_ms: int = NGUONG_GIU_MS) -> None:
        self._ra, self._hen = tren_cu_chi, hen
        self._khoang, self._giu = khoang_ms / 1000, giu_ms / 1000
        self._tt: dict[int, dict] = {}

    def _t(self, ma: int) -> dict:
        return self._tt.setdefault(ma, {"dem": 0, "da_giu": False, "huy_giu": None, "huy_nhan": None})

    @staticmethod
    def _huy(t: dict, khoa: str) -> None:
        h, t[khoa] = t[khoa], None
        if h is not None:
            h()

    def xuong(self, ma: int) -> None:
        t = self._t(ma)
        self._huy(t, "huy_nhan")                          # nhấn tiếp trong khoảng: cử chỉ nhiều lần đang gom
        self._huy(t, "huy_giu")
        t["da_giu"] = False
        t["huy_giu"] = self._hen(self._giu, lambda: self._giu_xong(ma))

    def _giu_xong(self, ma: int) -> None:
        t = self._t(ma)
        t["huy_giu"] = None
        t["da_giu"], t["dem"] = True, 0
        self._ra(ma, "giu")

    def len(self, ma: int) -> None:
        t = self._t(ma)
        self._huy(t, "huy_giu")
        if t["da_giu"]:
            t["da_giu"] = False                             # nhả sau «giữ»: không tính thêm một lần nhấn
            return
        t["dem"] += 1
        if t["dem"] >= 3:
            self._huy(t, "huy_nhan")
            self._ket_thuc(ma)
            return
        self._huy(t, "huy_nhan")
        t["huy_nhan"] = self._hen(self._khoang, lambda: self._ket_thuc(ma))

    def _ket_thuc(self, ma: int) -> None:
        t = self._t(ma)
        t["huy_nhan"] = None
        n, t["dem"] = t["dem"], 0
        if n:
            self._ra(ma, "don" if n == 1 else ("doi" if n == 2 else "ba"))


# ── Dịch vụ dò phím ──────────────────────────────────────────────────

#: Hành động cũ của nút giữa nay là dịch vụ (xem dang_ky_dich_vu). Tên là định danh ổn định.
DICH_VU_HANH_DONG = ("bat_tat_mic", "bat_tat_bluetooth", "bat_tat_dam_thoai", "bat_tat_assist", "bat_tat_den_nhac", "bao_thuc_hoac_dam_thoai", "phat_tam_dung",
                     "dung_nhac", "bai_ke", "bai_truoc", "tang_am_luong", "giam_am_luong", "tat_tieng_loa", "hen_gio_tat_nhac_30")


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    """``r1_speaker.phim_do``: một lúc báo MỌI phím về HA (qua dịch vụ trợ năng của APK, không nuốt phím) để biết mã phím của nút/thanh cảm ứng;
    mỗi phím phát sự kiện bus ``r1_speaker_phim_do``. Hết giờ tự trả về cấu hình thường."""
    import voluptuous as vol
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import config_validation as cv

    async def _do(call) -> None:
        rec = er.async_get(hass).async_get(call.data["entity_id"])
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        phim = getattr(getattr(entry, "runtime_data", None), "phim", None) if entry is not None and entry.domain == DOMAIN else None
        if phim is None:
            raise ServiceValidationError("Không phải thực thể của r1_speaker, hoặc loa chưa nạp xong")
        await phim.do(call.data.get("giay", 60))

    hass.services.async_register(DOMAIN, "phim_do", _do, schema=vol.Schema(
        {vol.Required("entity_id"): cv.entity_id, vol.Optional("giay"): vol.All(vol.Coerce(int), vol.Range(min=5, max=300))}))

    # Từ 0.17.0 nút giữa không còn hành động gắn sẵn; mỗi hành động cũ thành MỘT DỊCH VỤ để tự động hoá (gán vào cử chỉ của nút) gọi:
    # ``r1_speaker.<tên hành động>`` với ``entity_id`` = thực thể bất kỳ của loa. Hành động trùng tên dịch vụ có sẵn (bao_thuc_hoan) hoặc đã có
    # dịch vụ riêng (bao_thuc_dung -> bao_thuc_tat) thì bỏ qua.
    for ten in DICH_VU_HANH_DONG:
        if hass.services.has_service(DOMAIN, ten):
            continue

        async def _chay(call, ten=ten) -> None:
            rec = er.async_get(hass).async_get(call.data["entity_id"])
            entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
            phim = getattr(getattr(entry, "runtime_data", None), "phim", None) if entry is not None and entry.domain == DOMAIN else None
            if phim is None:
                raise ServiceValidationError("Không phải thực thể của r1_speaker, hoặc loa chưa nạp xong")
            await _DANG_KY[ten].ham(PhimCtx(hass, entry, phim.coordinator, MA_NUT_GIUA, "don"))
        hass.services.async_register(DOMAIN, ten, _chay, schema=vol.Schema({vol.Required("entity_id"): cv.entity_id}))


# ── Bộ điều phối theo mục cấu hình ───────────────────────────────────

class Phim:
    """Gắn nguồn cử chỉ (kết nối mic) với sự kiện của MỘT loa. Không có hành động gắn sẵn: cử chỉ chỉ bắn trigger thiết bị và sự kiện,
    việc làm gì do tự động hoá quyết định."""

    def __init__(self, hass: HomeAssistant, entry, coordinator, ma_hanh_dong: Callable[[], set[int]]) -> None:
        self.hass, self.entry, self.coordinator = hass, entry, coordinator
        self._ma = ma_hanh_dong
        self.tren_su_kien: list[Callable[[str, int], None]] = []      # (cử chỉ, mã phím): thực thể sự kiện nghe
        self.nhat_ky: list[tuple[int, str]] = []
        self._nd = NhanDien(self._cu_chi_that, self._hen)

    def _hen(self, giay: float, ham: Callable[[], None]) -> Callable[[], None]:
        return self.hass.loop.call_later(giay, ham).cancel

    def noi(self, mic_server) -> list[Callable[[], None]]:
        """Nghe kết nối mic: trả các hàm gỡ nghe."""
        return [mic_server.add_phim_tho_listener(self.tu_tho)]

    def tu_tho(self, ma: int, xuong: bool) -> None:
        """Phím thô (nhấn/nhả) từ APK (trợ năng) hoặc từ ADB (``phim_adb``): HA nhận diện cử chỉ rồi chạy hành động."""
        self.hass.bus.async_fire("r1_speaker_phim_do", {"entry_id": self.entry.entry_id, "phim": ma, "xuong": xuong})   # dò phím: luôn báo thô
        (self._nd.xuong if xuong else self._nd.len)(ma)

    def gia_lap(self, cu_chi: str) -> None:
        """Mô phỏng một cử chỉ của nút giữa (nút ảo ``button.*``): đi đúng đường của phím thật - bắn trigger thiết bị, cập nhật ``event.r1_phim`` và chạy
        hành động đang chọn cho cử chỉ đó. Dùng mã phím hành động (mặc định 195) để hành động chạy như phím thật."""
        if cu_chi not in CU_CHI_SU_KIEN:
            raise ValueError(f"cử chỉ không hợp lệ: {cu_chi}")
        ma_hd = self._ma()
        self._cu_chi_that(MA_NUT_GIUA if MA_NUT_GIUA in ma_hd or not ma_hd else min(ma_hd), cu_chi)

    def _device_id(self) -> str | None:
        dev = dr.async_get(self.hass).async_get_device(identifiers={(DOMAIN, self.entry.entry_id)})
        return None if dev is None else dev.id

    def _cu_chi_that(self, ma: int, cu_chi: str) -> None:
        self.nhat_ky = (self.nhat_ky + [(ma, cu_chi)])[-20:]
        self.hass.bus.async_fire(SU_KIEN_PHIM, {"device_id": self._device_id(), "entry_id": self.entry.entry_id, "type": cu_chi, "phim": ma})
        for cb in list(self.tren_su_kien):
            try:
                cb(cu_chi, ma)
            except Exception:  # noqa: BLE001 — người nghe hỏng không được chặn hành động
                _LOGGER.exception("phím: người nghe sự kiện lỗi")

    async def do(self, giay: int = 60) -> None:
        """Bật chế độ dò phím ``giay`` giây rồi tự tắt."""
        mic = self.coordinator.mic_server
        if not mic.receiving:
            raise RuntimeError("APK chưa nối về HA")
        await mic.gui_phim_cau_hinh(sorted(self._ma()), True)
        self._huy_do = getattr(self, "_huy_do", None)
        if self._huy_do is not None:
            self._huy_do()

        def xong() -> None:
            self._huy_do = None
            self.hass.async_create_task(mic.gui_phim_cau_hinh(sorted(self._ma()), False))
        self._huy_do = self.hass.loop.call_later(giay, xong).cancel
