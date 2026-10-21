"""Phicomm R1 Speaker — điều khiển loa R1 qua WebSocket trong mạng LAN, không cần add-on.

Gồm: thực thể điều khiển (EQ, âm lượng, DLNA, AirPlay), vệ tinh Assist (``assist_satellite.r1``),
bộ đàm nửa công (``intercom.py``) và thẻ Lovelace chỉnh EQ (``www/r1-eq-card.js``).
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from . import media_player
from .client import R1Client
from .const import (CARD_URL, CONF_INTERCOM_KEY, DOMAIN, SETTINGS_CARD_URL, TALK_CARD_URL,
                    WAKE_SPEAKER)
from .cong_vao import PingView, WakeView
from .den import R1Lights, dang_ky_dich_vu as dang_ky_dich_vu_den
from .dam_thoai import R1Talk
from .giu_nhac import MusicKeeper
from .coordinator import R1ConfigEntry, R1Coordinator
from .intercom import IntercomView, MicView, R1Intercom, go2rtc_source, wake_endpoint
from .mic import R1Mic
from .mic_server import R1MicServer
from .playback import R1Playback
from .settings import (TalkSettings, agc_settings, limiter_settings, noise_settings, ha_url, mic_address, mic_listen, play_address, speaker_host,
                       speaker_port, wake_mode)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.ASSIST_SATELLITE, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.MEDIA_PLAYER,
             Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]

_WWW = Path(__file__).parent / "www"
_CARDS = ((CARD_URL, _WWW / "r1-eq-card.js"), (TALK_CARD_URL, _WWW / "r1-talk-card.js"),
          (SETTINGS_CARD_URL, _WWW / "r1-settings-card.js"))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.http.register_view(IntercomView())
    hass.http.register_view(MicView())
    hass.http.register_view(WakeView())
    hass.http.register_view(PingView())
    await _register_card(hass)
    dang_ky_dich_vu_den(hass)

    def _entry_va_goc(call: ServiceCall):
        entity_id = call.data["entity_id"]
        rec = er.async_get(hass).async_get(entity_id)
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker")
        # Thứ tự: tham số dịch vụ → ha_url đã kiểm ở tuỳ chọn → đoán (127.0.0.1 chỉ đúng khi
        # bên gọi chạy CÙNG máy với HA).
        goc = call.data.get("ha_url", "").strip() or ha_url(entry)
        if not goc:
            http = getattr(hass, "http", None)
            cong = getattr(http, "server_port", None) or 8123
            kieu = "https" if getattr(http, "ssl_certificate", None) else "http"
            goc = f"{kieu}://127.0.0.1:{cong}"
        return entry, goc

    async def _nguon_bo_dam(call: ServiceCall) -> ServiceResponse:
        entry, goc = _entry_va_goc(call)
        return go2rtc_source(goc, entry.entry_id, entry.data[CONF_INTERCOM_KEY])

    async def _diem_cuoi_wake(call: ServiceCall) -> ServiceResponse:
        entry, goc = _entry_va_goc(call)
        return wake_endpoint(goc, entry.entry_id, entry.data[CONF_INTERCOM_KEY])

    schema = vol.Schema({
        vol.Required("entity_id"): cv.entity_id,
        # Địa chỉ HA mà loa / máy chạy go2rtc gọi tới được; bỏ trống thì dùng ``ha_url`` của
        # tuỳ chọn (nếu đã đặt), rồi mới đoán.
        vol.Optional("ha_url"): vol.All(str, vol.Match(
            r"^https?://[^\s#]+$",
            msg="ha_url phải dạng http(s)://địa-chỉ:cổng, không dấu cách hay #")),
    })
    hass.services.async_register(DOMAIN, "get_intercom_source", _nguon_bo_dam, schema=schema,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "get_wake_endpoint", _diem_cuoi_wake, schema=schema,
                                 supports_response=SupportsResponse.ONLY)
    return True


async def _register_card(hass: HomeAssistant) -> None:
    """Phục vụ hai thẻ (EQ, đàm thoại) và nạp chúng vào mọi bảng điều khiển (không cần thêm
    tài nguyên Lovelace tay). Không có ``frontend`` (HA tối giản) thì chỉ phục vụ tệp."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(url, str(path), cache_headers=False) for url, path in _CARDS])
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url
    for url, _path in _CARDS:
        if DATA_EXTRA_MODULE_URL in hass.data:
            add_extra_js_url(hass, url)
        else:
            _LOGGER.warning("frontend chưa sẵn sàng: thêm %s vào tài nguyên Lovelace bằng tay",
                            url)


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry) -> bool:
    if not entry.data.get(CONF_INTERCOM_KEY):
        # Khoá bộ đàm riêng loa này, sinh một lần rồi giữ: dòng đã dán vào go2rtc.yaml phải
        # còn đúng sau mỗi lần khởi động lại HA.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_INTERCOM_KEY: secrets.token_urlsafe(24)})
    client = R1Client(async_get_clientsession(hass), speaker_host(entry), speaker_port(entry))
    coordinator = R1Coordinator(hass, entry, client)
    # Loa tắt lúc khởi động HA vẫn được thêm: thực thể unavailable, tự hồi phục sau.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    # Nguồn mic: host trống (mặc định) thì không nối gì, thực thể assist_satellite unavailable.
    modo = wake_mode(entry)
    # Từ đánh thức trên loa: mic chỉ nối khi có phiên (on_demand). Chế độ ``ha``: nối liên tục.
    coordinator.mic = R1Mic(*mic_address(entry), on_demand=modo == WAKE_SPEAKER)
    coordinator.mic.set_dsp(noise_settings(entry), agc_settings(entry), limiter_settings(entry))
    # Đầu nhận mic NV244: APK trên loa nối VÀO HA (mic.py là chiều ngược). Chỉ mở khi đã
    # đặt khoá + IP loa; start() không ném lỗi ra ngoài.
    listen_port, listen_key = mic_listen(entry)
    coordinator.mic_server = R1MicServer(
        coordinator.mic, listen_port, listen_key, mic_address(entry)[0])
    await coordinator.mic_server.start()
    coordinator.playback = R1Playback(*play_address(entry))
    coordinator.music = MusicKeeper(
        hass, lambda: media_player.dlna_entity_id(hass, speaker_host(entry)))
    coordinator.talk = R1Talk(hass, coordinator.mic, coordinator.music, modo)
    coordinator.intercom = R1Intercom(hass, coordinator.playback, coordinator.mic,
                                      TalkSettings.from_entry(entry))
    entry.async_create_background_task(hass, coordinator.mic.run(), "r1_speaker mic")
    # Đèn: mặc định CHƯA có dịch vụ đèn trên loa (NullLights) — chỉ lưu cài đặt, không gửi gì.
    coordinator.lights = R1Lights(hass, entry)
    await coordinator.lights.async_load()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.lights.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: R1ConfigEntry) -> bool:
    coordinator = entry.runtime_data
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await coordinator.lights.async_close()
        await coordinator.mic_server.async_close()
        await coordinator.intercom.async_close()
        await coordinator.talk.async_close()
    return ok
