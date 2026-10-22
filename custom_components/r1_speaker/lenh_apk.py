"""Lệnh cấu hình APK trên loa, ĐÃ KÈM khoá nghe mic, chỉ trả cho quản trị viên HA (WebSocket).

Khoá không nằm trong trạng thái thực thể (ai đăng nhập cũng đọc được, lại bị ghi vào lịch sử): thẻ «Kết nối»
hỏi lệnh này khi quản trị viên bấm «Hiện lệnh cài APK» và chỉ hiển thị trên màn hình đó."""

from __future__ import annotations

from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import DOMAIN
from .settings import ha_url, mic_listen, speaker_host


def _host_ha(hass: HomeAssistant, entry) -> str:
    """IP/tên HA mà loa nối tới: ``ha_url`` đã đặt, không thì địa chỉ nội bộ HA tự biết."""
    url = ha_url(entry)
    if not url:
        try:
            url = get_url(hass, allow_external=False, prefer_external=False)
        except NoURLAvailableError:
            return "<IP-của-HA>"
    return urlsplit(url).hostname or "<IP-của-HA>"


@callback
def dang_ky(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, _lenh_apk)


@websocket_api.websocket_command({vol.Required("type"): "r1_speaker/apk_lenh",
                                  vol.Required("entity_id"): str})
@websocket_api.require_admin
@callback
def _lenh_apk(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    rec = er.async_get(hass).async_get(msg["entity_id"])
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "không phải thực thể của r1_speaker")
        return
    cong, khoa = mic_listen(entry)
    if not khoa:
        connection.send_error(msg["id"], "no_key", "loa này chưa có khoá nghe mic")
        return
    connection.send_result(msg["id"], {
        "loa": speaker_host(entry),
        "lenh": ("adb connect {loa}:5555 && adb -s {loa}:5555 shell /system/bin/am start "
                 "-n vn.r1.bodam/.ManHinhChinh --es host {ha} --ei port {cong} --es khoa {khoa} --ez bat true"
                 ).format(loa=speaker_host(entry), ha=_host_ha(hass, entry), cong=cong, khoa=khoa)})
