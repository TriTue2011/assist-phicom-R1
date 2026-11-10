"""NV302 — các cài đặt hay dùng thành THỰC THỂ chuẩn (``switch`` / ``select`` / ``number`` / ``time``) để thẻ Cài đặt chỉnh được ngay.

MỘT nguồn lưu duy nhất: ``entry.options`` — chính nơi hộp tuỳ chọn của HA đọc và ghi. Thực thể KHÔNG giữ giá trị riêng: ``đọc`` đi qua
cùng hàm đọc tuỳ chọn mà phần còn lại của tích hợp dùng (``settings.py``), ``ghi`` cập nhật ``entry.options`` (giá trị bằng mặc định thì
bỏ khoá, như hộp tuỳ chọn). Đổi ở đâu cũng thấy ở kia: hộp tuỳ chọn lưu xong HA nạp lại mục và thực thể đọc lại; thực thể ghi xong thì
hộp tuỳ chọn mở lần sau đọc đúng giá trị mới. Các tuỳ chọn này đều được đọc tại chỗ mỗi lần dùng nên đổi có hiệu lực NGAY, không nạp lại mục
(mic không phải nối lại).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import const, settings
from .coordinator import R1ConfigEntry
from .entity import device_info, preregister


def luu_tuy_chon(hass: HomeAssistant, entry: R1ConfigEntry, khoa: str, gia_tri: Any, mac_dinh: Any) -> None:
    """Ghi MỘT tuỳ chọn vào ``entry.options``; bằng mặc định thì bỏ khoá."""
    tuy_chon = dict(entry.options)
    if gia_tri == mac_dinh:
        tuy_chon.pop(khoa, None)
    else:
        tuy_chon[khoa] = gia_tri
    if tuy_chon != dict(entry.options):
        hass.config_entries.async_update_entry(entry, options=tuy_chon)
        ap_dung_tuy_chon(entry)


def ap_dung_tuy_chon(entry: R1ConfigEntry) -> None:
    """Áp lại TẠI CHỖ cài đặt mic (khử tạp/AGC/hạn đỉnh), bộ đàm và song công sau khi thực thể đổi tuỳ chọn.

    Thực thể chỉ ghi entry.options, còn ba đối tượng đang chạy giữ BẢN CHỤP cài đặt lúc khởi động: trước đây đặt
    «Động cơ xử lý âm thanh» = nang_cao mà phiên song công vẫn chạy «nlms» cho tới khi tải lại tích hợp (đo 10/11/2026).
    Không dùng update listener: hộp tuỳ chọn (bánh răng) là OptionsFlowWithReload nên HA cấm listener, và nó tự tải lại.
    Phiên song công đang mở giữ bộ khử vọng đã dựng; phiên mở SAU dùng cài đặt mới."""
    c = getattr(entry, "runtime_data", None)
    if c is None or getattr(c, "duplex", None) is None:
        return
    c.mic.set_dsp(settings.noise_settings(entry), settings.agc_settings(entry), settings.limiter_settings(entry))
    c.intercom.set_settings(settings.TalkSettings.from_entry(entry))
    c.duplex.set_settings(settings.DuplexSettings.from_entry(entry))


class _TuyChon:
    """Phần chung: định danh, nhóm «Cấu hình», đọc/ghi qua ``entry.options``."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: R1ConfigEntry, key: str, conf_key: str, mac_dinh: Any, doc: Callable[[Any], Any]) -> None:
        self._entry, self._conf_key, self._mac_dinh, self._doc = entry, conf_key, mac_dinh, doc
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device_info(entry)

    def _ghi(self, gia_tri: Any) -> None:
        luu_tuy_chon(self.hass, self._entry, self._conf_key, gia_tri, self._mac_dinh)
        self.async_write_ha_state()


class R1TuyChonSwitch(_TuyChon, SwitchEntity):
    def __init__(self, entry: R1ConfigEntry, key: str, conf_key: str, mac_dinh: bool, doc: Callable[[Any], bool]) -> None:
        super().__init__(entry, key, conf_key, mac_dinh, doc)

    @property
    def is_on(self) -> bool:
        return self._doc(self._entry)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._ghi(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._ghi(False)


class R1NgaySwitch(_TuyChon, SwitchEntity):
    """Một thứ trong tuần của lịch khởi động lại (``t2``…``cn``): bật = loa được khởi động lại vào thứ đó."""

    def __init__(self, entry: R1ConfigEntry, ma: str) -> None:
        super().__init__(entry, f"kdl_ngay_{ma}", const.CONF_KDL_NGAY, list(const.DEFAULT_KDL_NGAY), settings.khoi_dong_lai_ngay)
        self._ma = ma

    @property
    def is_on(self) -> bool:
        return self._ma in self._doc(self._entry)

    def _dat(self, bat: bool) -> None:
        chon = set(self._doc(self._entry))
        chon.add(self._ma) if bat else chon.discard(self._ma)
        self._ghi([m for m in const.KDL_NGAY_MA if m in chon])

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._dat(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._dat(False)


class R1DuongPhatSelect(_TuyChon, SelectEntity):
    _attr_options = list(const.DUONG_PHAT_GIA_TRI)

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "duong_phat", const.CONF_DUONG_PHAT, const.DEFAULT_DUONG_PHAT, settings.duong_phat)

    @property
    def current_option(self) -> str:
        return self._doc(self._entry)

    async def async_select_option(self, option: str) -> None:
        if option not in const.DUONG_PHAT_GIA_TRI:
            raise HomeAssistantError(f"Đường phát «{option}» không có")
        self._ghi(option)


class R1DspSelect(_TuyChon, SelectEntity):
    """Động cơ xử lý âm thanh mic: bộ có sẵn hay «nâng cao» (khử tạp Speex + khử vọng miền tần số; không cài thêm gì)."""

    _attr_options = list(const.DSP_DONG_CO_GIA_TRI)

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "dsp_dong_co", const.CONF_DSP_DONG_CO, const.DEFAULT_DSP_DONG_CO, settings.dsp_dong_co)

    @property
    def current_option(self) -> str:
        return self._doc(self._entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Thư viện có sẵn không: ``khu_on_co_san`` (pyspeex_noise), ``khu_vong_co_san`` (numpy). False nghĩa là phần đó dùng bộ có sẵn."""
        from . import xu_ly_nang_cao
        return {"khu_on_co_san": xu_ly_nang_cao.co_san_khu_on(), "khu_vong_co_san": xu_ly_nang_cao.co_san_khu_vong()}

    async def async_select_option(self, option: str) -> None:
        if option not in const.DSP_DONG_CO_GIA_TRI:
            raise HomeAssistantError(f"Động cơ «{option}» không có")
        self._ghi(option)


class R1NacHaNhacNumber(_TuyChon, NumberEntity):
    _attr_native_min_value, _attr_native_max_value, _attr_native_step = 1, 14, 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "ha_nhac_nac", const.CONF_HA_NHAC_NAC, const.DEFAULT_HA_NHAC_NAC, settings.ha_nhac_nac)

    @property
    def native_value(self) -> float:
        return self._doc(self._entry)

    async def async_set_native_value(self, value: float) -> None:
        self._ghi(int(round(value)))


class R1AmLuongMediaNumber(_TuyChon, NumberEntity):
    """Âm lượng MEDIA (phần mềm, %) cho nhạc phát qua AirPlay: giảm nhạc mà không đổi âm lượng loa nên tin báo/TTS vẫn nghe như cũ."""

    _attr_native_min_value, _attr_native_max_value, _attr_native_step = 0, 100, 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "am_luong_media", const.CONF_AM_LUONG_MEDIA, const.DEFAULT_AM_LUONG_MEDIA,
                         lambda e: round(settings.am_luong_media(e) * 100))

    @property
    def native_value(self) -> float:
        return self._doc(self._entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"ap_dung": "airplay"}          # chỉ nhạc đi đường AirPlay; DLNA do loa tự tải URL nên không áp được

    async def async_set_native_value(self, value: float) -> None:
        self._ghi(int(round(min(max(value, 0), 100))))


class R1AmLuongTinNumber(_TuyChon, NumberEntity):
    """Âm lượng LOA dùng cho tin báo / TTS (0–15; 0 = không đổi). Đặt trước khi tin phát, trả mức cũ khi tin xong (nhạc phát tiếp ở mức cũ).
    Mỗi lần gọi ``tts.speak`` / ``media_player.play_media`` cũng ghi đè được bằng ``extra: {volume: 0.0–1.0}``."""

    _attr_native_min_value, _attr_native_max_value, _attr_native_step = 0, const.VOL_MAX, 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "am_luong_tin", const.CONF_AM_LUONG_TIN, const.DEFAULT_AM_LUONG_TIN, settings.am_luong_tin)

    @property
    def native_value(self) -> float:
        return self._doc(self._entry)

    async def async_set_native_value(self, value: float) -> None:
        self._ghi(int(round(min(max(value, 0), const.VOL_MAX))))


class R1CongAirplayNumber(_TuyChon, NumberEntity):
    """Cổng AirPlay (RAOP) của loa, cùng tuỳ chọn ``airplay_port``; đổi nếu AirPlay không nối được sau khi loa khởi động lại."""

    _attr_native_min_value, _attr_native_max_value, _attr_native_step = 1, 65535, 1
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "cong_airplay", const.CONF_AIRPLAY_PORT, const.DEFAULT_AIRPLAY_PORT, settings.airplay_port)

    @property
    def native_value(self) -> float:
        return self._doc(self._entry)

    async def async_set_native_value(self, value: float) -> None:
        self._ghi(int(round(value)))


class R1GioKhoiDongLaiTime(_TuyChon, TimeEntity):
    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "kdl_gio", const.CONF_KDL_GIO, const.DEFAULT_KDL_GIO, settings.khoi_dong_lai_gio)

    @property
    def native_value(self) -> time:
        return self._doc(self._entry)

    async def async_set_value(self, value: time) -> None:
        self._ghi(value.strftime("%H:%M"))


#: Tên thực thể gợi ý (``<domain>.<tên>``) theo khoá dịch; khoá nào không có ở đây thì dùng ``r1_<khoá>``.
_TEN_GOI_Y = {"am_luong_media": "r1_am_luong_media", "am_luong_tin": "r1_am_luong_tin", "khu_on": "r1_khu_on_mic", "khu_vong": "r1_khu_vong_song_cong", "dsp_dong_co": "r1_dong_co_xu_ly_am_thanh",
              "tin_nguoc_nhac": "r1_tin_bao_nguoc_nhac", "kdl_bat": "r1_khoi_dong_lai_lich", "kdl_khi_treo": "r1_khoi_dong_lai_khi_treo",
              "kdl_gio": "r1_gio_khoi_dong_lai", **{f"kdl_ngay_{m}": f"r1_khoi_dong_lai_{m}" for m in const.KDL_NGAY_MA}}


def _dang_ky(hass: HomeAssistant, entry: R1ConfigEntry, domain: str, ds: list) -> list:
    for e in ds:
        khoa = e._attr_translation_key
        preregister(hass, entry, domain, e._attr_unique_id, _TEN_GOI_Y.get(khoa, "r1_" + khoa))
    return ds


def switches(hass: HomeAssistant, entry: R1ConfigEntry) -> list:
    return _dang_ky(hass, entry, "switch", [
        R1TuyChonSwitch(entry, "tin_nguoc_nhac", const.CONF_TTS_SONG_SONG, const.DEFAULT_TTS_SONG_SONG, settings.tts_song_song_airplay),
        R1TuyChonSwitch(entry, "ha_nhac_xuong", const.CONF_HA_NHAC_XUONG, const.DEFAULT_HA_NHAC_XUONG, settings.ha_nhac_xuong),
        R1TuyChonSwitch(entry, "khu_on", const.CONF_NOISE_ENABLE, const.DEFAULT_NOISE_ENABLE, lambda e: settings.noise_settings(e).enabled),
        R1TuyChonSwitch(entry, "khu_vong", const.CONF_DUPLEX_AEC, const.DEFAULT_DUPLEX_AEC, lambda e: settings.DuplexSettings.from_entry(e).aec),
        R1TuyChonSwitch(entry, "kdl_bat", const.CONF_KDL_BAT, const.DEFAULT_KDL_BAT, settings.khoi_dong_lai_bat),
        R1TuyChonSwitch(entry, "kdl_khi_treo", const.CONF_KDL_TU_PHUC_HOI, const.DEFAULT_KDL_TU_PHUC_HOI, settings.khoi_dong_lai_khi_treo),
        *(R1NgaySwitch(entry, ma) for ma in const.KDL_NGAY_MA)])


def selects(hass: HomeAssistant, entry: R1ConfigEntry) -> list:
    return _dang_ky(hass, entry, "select", [R1DuongPhatSelect(entry), R1DspSelect(entry)])


def numbers(hass: HomeAssistant, entry: R1ConfigEntry) -> list:
    return _dang_ky(hass, entry, "number", [R1NacHaNhacNumber(entry), R1CongAirplayNumber(entry), R1AmLuongMediaNumber(entry), R1AmLuongTinNumber(entry)])


def times(hass: HomeAssistant, entry: R1ConfigEntry) -> list:
    return _dang_ky(hass, entry, "time", [R1GioKhoiDongLaiTime(entry)])
