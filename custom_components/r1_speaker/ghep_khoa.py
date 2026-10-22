"""Ghép khoá nghe mic TỰ ĐỘNG: người dùng không phải copy khoá nào sang loa.

Khi HA tự sinh khoá cho một loa (``mic_chua_ghep`` = True trong dữ liệu mục), APK trên loa — bị từ chối vì khoá
cũ/trống — gọi ``POST /api/r1_speaker/ghep`` (không cần đăng nhập). HA chỉ trao khoá khi
  * địa chỉ nguồn của kết nối đúng IP loa của một mục ĐANG chờ ghép, và
  * khoá CHƯA từng được trao (trao đúng MỘT lần, rồi mục chuyển sang «đã ghép»: lần sau 409).
Muốn ghép lại (thay loa, cài lại APK): tuỳ chọn «Ghép lại APK» sinh khoá mới và mở lại cửa ghép.
Mục mang khoá người dùng tự đặt (không do HA sinh) KHÔNG bao giờ có cửa ghép."""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import CONF_MIC_CHUA_GHEP, DOMAIN
from .settings import mic_listen, speaker_host

_LOGGER = logging.getLogger(__name__)


class GhepKhoaView(HomeAssistantView):
    url = "/api/r1_speaker/ghep"
    name = "api:r1_speaker:ghep"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        ip = request.remote or ""
        entry = next((e for e in hass.config_entries.async_entries(DOMAIN)
                      if speaker_host(e) == ip and getattr(e, "runtime_data", None) is not None), None)
        if entry is None:
            return web.json_response({"loi": "không có loa nào mang địa chỉ này"}, status=404)
        if not entry.data.get(CONF_MIC_CHUA_GHEP):
            return web.json_response({"loi": "loa này đã ghép; muốn ghép lại: Tuỳ chọn → Ghép lại APK"}, status=409)
        cong, khoa = mic_listen(entry)
        if not khoa:
            return web.json_response({"loi": "chưa có khoá"}, status=409)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MIC_CHUA_GHEP: False})
        _LOGGER.info("R1: đã trao khoá nghe mic cho loa %s (một lần)", entry.title)
        return web.json_response({"port": cong, "key": khoa})
