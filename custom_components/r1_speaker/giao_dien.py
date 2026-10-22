"""Tự đăng ký thẻ Lovelace khi cài tích hợp: MỘT thẻ duy nhất ``r1-card`` (tự nạp ba thẻ con: đàm thoại, EQ, cài đặt).

Cách làm giống tích hợp YouTube: thêm tài nguyên ``/r1_speaker/r1-card.js?v=<phiên bản>`` vào danh sách tài nguyên
Lovelace (chế độ lưu trữ), đổi ``?v=`` mỗi lần tăng phiên bản trong ``manifest.json`` để trình duyệt/ứng dụng HA bỏ
bản cũ. KHÔNG dùng ``add_extra_js_url``: module phụ chạy quá sớm, trước khi giao diện HA cài xong bộ đăng ký phần tử
riêng, nên HA báo «Custom element not found» dù tệp đúng (đo 22/10/2026). Danh sách tài nguyên ở chế độ YAML là
chỉ-đọc: khi đó chỉ ghi log hướng dẫn thêm tay, không đổi gì.

Ba thẻ con trước đây có thể đã được thêm tay làm tài nguyên riêng; nay chúng nạp qua ``r1-card`` nên tài nguyên riêng của
CHÍNH tích hợp này (đúng ba đường dẫn của nó) bị gỡ để trong bộ chọn thẻ chỉ còn một thẻ.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_GOP_URL, CARD_URL, DOMAIN, SETTINGS_CARD_URL, TALK_CARD_URL

_LOGGER = logging.getLogger(__name__)

#: Đường dẫn thẻ con cũ (đã gộp vào ``r1-card``): gỡ nếu còn là tài nguyên riêng.
THE_CON_CU = (CARD_URL, TALK_CARD_URL, SETTINGS_CARD_URL)


def _bo_query(url: Any) -> str:
    return str(url or "").split("?", 1)[0]


async def dang_ky_tai_nguyen(hass: HomeAssistant) -> None:
    """Đăng ký (hoặc cập nhật) tài nguyên thẻ gộp sau khi HA khởi động xong."""
    integration = await async_get_integration(hass, DOMAIN)
    url_phien_ban = f"{CARD_GOP_URL}?v={integration.version}"

    async def _lam(_event: Any = None) -> None:
        await _dang_ky(hass, url_phien_ban)

    # Đăng ký lúc đang khởi động có thể ghi đè danh sách tài nguyên chưa nạp: chờ HA chạy xong.
    if hass.state is CoreState.running:
        await _lam()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _lam)


async def _dang_ky(hass: HomeAssistant, url_phien_ban: str) -> None:
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.info("Danh sách tài nguyên Lovelace chỉ-đọc (chế độ YAML): thêm tay %s (Mô-đun JavaScript)", url_phien_ban)
        return
    try:
        # Nạp danh sách từ kho trước khi đọc/ghi, để không bao giờ ghi lên một danh sách rỗng chưa nạp.
        if hasattr(resources, "async_get_info"):
            await resources.async_get_info()
        elif hasattr(resources, "async_load"):
            await resources.async_load()
        items = list(resources.async_items())
        da_co = next((i for i in items if _bo_query(i.get("url")) == CARD_GOP_URL), None)
        if da_co is None:
            await resources.async_create_item({"res_type": "module", "url": url_phien_ban})
            _LOGGER.info("Đã tự đăng ký thẻ R1: %s", url_phien_ban)
        elif da_co.get("url") != url_phien_ban:
            await resources.async_update_item(da_co["id"], {"res_type": "module", "url": url_phien_ban})
            _LOGGER.info("Đã cập nhật thẻ R1 lên %s", url_phien_ban)
        for item in items:
            if _bo_query(item.get("url")) in THE_CON_CU and hasattr(resources, "async_delete_item"):
                await resources.async_delete_item(item["id"])
                _LOGGER.info("Đã gỡ tài nguyên thẻ con cũ %s (thẻ gộp r1-card tự nạp)", item.get("url"))
    except Exception as error:  # noqa: BLE001 — không bao giờ làm hỏng việc cài tích hợp vì thẻ
        _LOGGER.warning("Không tự đăng ký được thẻ R1 (thêm tay %s): %s", url_phien_ban, error)
