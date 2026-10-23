"""Đèn CHÍNH (RGB) của loa qua WebSocket cổng 8080: ``send_message`` với ``what=4``.

Chế độ (``arg1=68``): 0 mặc định, 1 xoay vòng (cầu vồng — đã test), 2/4/5/6/8–16 các kiểu khác của firmware
(chưa gán tên: nhận diện bằng mắt, xem tài liệu). Độ sáng ``arg1=65`` (1–200), tốc độ ``arg1=66`` (1–100).
Bật/tắt ``arg1=64`` (1/0). Chưa biết chắc tốc độ/độ sáng lớn là nhanh/sáng hơn — kiểm trên loa.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

WHAT = 4
BAT_TAT, CHE_DO, DO_SANG, TOC_DO = 64, 68, 65, 66
CHE_DO_HOP_LE = (0, 1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16)
#: Tên hiển thị: chỉ mode 1 đã xác nhận là cầu vồng; còn lại để trống chờ quan sát.
TEN_CHE_DO = {0: "Mặc định", 1: "Cầu vồng (xoay vòng)", 3: "Đơn sắc"}


def khung(arg1: int, arg2: int) -> str:
    """Khung đúng định dạng của integration (cả tham số phẳng lẫn ``data``)."""
    import json
    p = {"what": WHAT, "arg1": arg1, "arg2": arg2}
    return json.dumps({"type": "send_message", **p, "data": p})


async def dat_den_chinh(client, *, bat: bool | None = None, che_do: int | None = None,
                        sang: int | None = None, toc_do: int | None = None) -> None:
    """Gửi từng lệnh đã chọn (một khung mỗi thông số). Không có thông số nào thì không gửi gì."""
    if bat is not None:
        await client.async_send("send_message", {"what": WHAT, "arg1": BAT_TAT, "arg2": 1 if bat else 0})
    if che_do is not None:
        await client.async_send("send_message", {"what": WHAT, "arg1": CHE_DO, "arg2": che_do})
    if sang is not None:
        await client.async_send("send_message", {"what": WHAT, "arg1": DO_SANG, "arg2": sang})
    if toc_do is not None:
        await client.async_send("send_message", {"what": WHAT, "arg1": TOC_DO, "arg2": toc_do})


SET_MAIN_LIGHT_SCHEMA = vol.Schema({
    vol.Required("entity_id"): str,
    vol.Optional("bat"): bool,
    vol.Optional("che_do"): vol.In(list(CHE_DO_HOP_LE)),
    vol.Optional("sang"): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
    vol.Optional("toc_do"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
})


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _dat(call: ServiceCall) -> None:
        d = dict(call.data)
        rec = er.async_get(hass).async_get(d.pop("entity_id"))
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN or getattr(entry, "runtime_data", None) is None:
            raise ServiceValidationError("không phải thực thể của r1_speaker")
        await dat_den_chinh(entry.runtime_data.client, **d)

    hass.services.async_register(DOMAIN, "set_main_light", _dat, schema=SET_MAIN_LIGHT_SCHEMA)
