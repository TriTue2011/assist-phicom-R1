"""Cài đặt chi tiết (cổng thoại, khử tạp, AGC, hạn đỉnh, song công) chỉnh TRỰC TIẾP ở thẻ Cài đặt.

Nguồn sự thật duy nhất của khoảng giá trị: bảng ``BANG``; form tuỳ chọn (bước «nâng cao») và dịch vụ
``r1_speaker.set_advanced_option`` dùng chung phạm vi này. Mọi số mặc định CHƯA đo trên loa R1. Giá trị bằng
mặc định thì KHÔNG lưu (mặc định đổi sau khi đo thì mục chưa chỉnh tay tự theo)."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from . import const as c
from .const import DOMAIN
from .settings import conf

# (nhóm, khoá, kiểu, nhỏ nhất, lớn nhất, bước, mặc định)
BANG: tuple[tuple[str, str, str, float, float, float, Any], ...] = (
    ("thoai", c.CONF_TALK_THRESHOLD_DB, "so", -90, -5, 1, c.DEFAULT_TALK_THRESHOLD_DB),
    ("thoai", c.CONF_TALK_SILENCE, "so", 0.2, 10, 0.1, c.DEFAULT_TALK_SILENCE),
    ("thoai", c.CONF_TALK_PREROLL, "so", 0, 2, 0.1, c.DEFAULT_TALK_PREROLL),
    ("thoai", c.CONF_TALK_TAIL, "so", 0, 5, 0.1, c.DEFAULT_TALK_TAIL),
    ("khu_tap", c.CONF_NOISE_ENABLE, "bat", 0, 1, 1, c.DEFAULT_NOISE_ENABLE),
    ("khu_tap", c.CONF_NOISE_STRENGTH_DB, "so", 0, 40, 1, c.DEFAULT_NOISE_STRENGTH_DB),
    ("khu_tap", c.CONF_NOISE_VOICE_DB, "so", 0.5, 12, 0.5, c.DEFAULT_NOISE_VOICE_DB),
    ("agc", c.CONF_AGC_ENABLE, "bat", 0, 1, 1, c.DEFAULT_AGC_ENABLE),
    ("agc", c.CONF_AGC_TARGET_DB, "so", -50, -3, 1, c.DEFAULT_AGC_TARGET_DB),
    ("agc", c.CONF_AGC_MAX_GAIN_DB, "so", 0, 40, 1, c.DEFAULT_AGC_MAX_GAIN_DB),
    ("agc", c.CONF_AGC_SILENCE_DB, "so", -90, -20, 1, c.DEFAULT_AGC_SILENCE_DB),
    ("han_dinh", c.CONF_LIMITER_ENABLE, "bat", 0, 1, 1, c.DEFAULT_LIMITER_ENABLE),
    ("han_dinh", c.CONF_LIMITER_CEILING, "so", 0.1, 1.0, 0.01, c.DEFAULT_LIMITER_CEILING),
    ("song_cong", c.CONF_DUPLEX_VAD_THRESHOLD, "so", 0, 0.95, 0.05, c.DEFAULT_DUPLEX_VAD_THRESHOLD),
    ("song_cong", c.CONF_DUPLEX_PREROLL, "so", 0, 2, 0.1, c.DEFAULT_DUPLEX_PREROLL),
    ("song_cong", c.CONF_DUPLEX_HANGOVER, "so", 0, 5, 0.1, c.DEFAULT_DUPLEX_HANGOVER),
    ("song_cong", c.CONF_DUPLEX_MAX_S, "so", 60, 86400, 60, c.DEFAULT_DUPLEX_MAX_S),
    ("song_cong", c.CONF_DUPLEX_DUCK, "bat", 0, 1, 1, c.DEFAULT_DUPLEX_DUCK),
    ("song_cong", c.CONF_DUPLEX_DUCK_DB, "so", -90, -5, 1, c.DEFAULT_DUPLEX_DUCK_DB),
)
_THEO_KHOA = {b[1]: b for b in BANG}


def thuoc_tinh(entry) -> list[dict]:
    """Danh sách cho thẻ: khoá, nhóm, kiểu, khoảng, giá trị hiện tại và mặc định."""
    ra = []
    for nhom, khoa, kieu, lo, hi, buoc, mac_dinh in BANG:
        v = conf(entry, khoa, mac_dinh)
        ra.append({"k": khoa, "nhom": nhom, "kieu": kieu, "min": lo, "max": hi, "buoc": buoc,
                   "v": bool(v) if kieu == "bat" else float(v), "mac_dinh": bool(mac_dinh) if kieu == "bat" else float(mac_dinh)})
    return ra


def kiem_tra(khoa: str, gia_tri: Any) -> Any:
    """Giá trị hợp lệ (đã ép kiểu) hoặc ném ``ServiceValidationError``."""
    b = _THEO_KHOA.get(khoa)
    if b is None:
        raise ServiceValidationError(f"không có cài đặt «{khoa}»")
    _nhom, _k, kieu, lo, hi, _buoc, _mac = b
    if kieu == "bat":
        if not isinstance(gia_tri, bool):
            raise ServiceValidationError(f"«{khoa}» là công tắc: giá trị phải đúng/sai")
        return gia_tri
    if isinstance(gia_tri, bool) or not isinstance(gia_tri, (int, float)):
        raise ServiceValidationError(f"«{khoa}» phải là số")
    if not lo <= gia_tri <= hi:
        raise ServiceValidationError(f"«{khoa}» phải trong khoảng {lo}…{hi}")
    return float(gia_tri)


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _dat(call: ServiceCall) -> None:
        rec = er.async_get(hass).async_get(call.data["entity_id"])
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"{call.data['entity_id']} không phải thực thể của r1_speaker")
        khoa, gia_tri = call.data["key"], kiem_tra(call.data["key"], call.data["value"])
        mac_dinh = _THEO_KHOA[khoa][6]
        tuy_chon = dict(entry.options)
        if gia_tri == (bool(mac_dinh) if _THEO_KHOA[khoa][2] == "bat" else float(mac_dinh)):
            tuy_chon.pop(khoa, None)
        else:
            tuy_chon[khoa] = gia_tri
        if tuy_chon == dict(entry.options):
            return
        hass.config_entries.async_update_entry(entry, options=tuy_chon)
        # Các số này đọc lúc nạp tích hợp: nạp lại để áp dụng (mic nối lại sau vài giây).
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    import voluptuous as vol
    from homeassistant.helpers import config_validation as cv
    hass.services.async_register(DOMAIN, "set_advanced_option", _dat, schema=vol.Schema({
        vol.Required("entity_id"): cv.entity_id, vol.Required("key"): cv.string,
        vol.Required("value"): vol.Any(bool, vol.Coerce(float))}))
