"""Coordinator: hỏi loa theo chu kỳ; lỗi → UpdateFailed (thực thể unavailable), tự thử lại."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import R1Client, R1Error, R1State, with_overrides
from .const import DOMAIN, SCAN_INTERVAL
from .dam_thoai import R1Talk
from .giu_nhac import MusicKeeper
from .intercom import R1Intercom
from .mic import R1Mic
from .mic_server import R1MicServer
from .playback import R1Playback
from .song_cong import R1Duplex

if TYPE_CHECKING:
    from .den import R1Lights

_LOGGER = logging.getLogger(__name__)

type R1ConfigEntry = ConfigEntry[R1Coordinator]


class R1Coordinator(DataUpdateCoordinator[R1State]):
    # Gán trong async_setup_entry (cần hass + entry đã sẵn sàng).
    mic: R1Mic
    mic_server: R1MicServer
    playback: R1Playback
    intercom: R1Intercom
    duplex: R1Duplex
    music: MusicKeeper
    talk: R1Talk
    lights: "R1Lights"
    apps: "BoCai"
    he_thong: "HeThongLoa"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: R1Client) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=SCAN_INTERVAL)
        self.client = client

    async def _async_update_data(self) -> R1State:
        try:
            return await self.client.async_fetch()
        except R1Error as exc:
            # Chỉ log lần đầu mất kết nối: DataUpdateCoordinator tự log khi hồi phục.
            if self.last_update_success:
                _LOGGER.warning("Loa R1 %s không đọc được: %s", self.client.host, exc)
            raise UpdateFailed(str(exc)) from exc

    async def async_command(self, send: Callable[[], Awaitable[None]],
                            **expected: Any) -> None:
        """Gửi lệnh rồi cập nhật lạc quan. Gửi hỏng → HomeAssistantError cho người gọi
        dịch vụ (vòng cập nhật không bị ảnh hưởng)."""
        try:
            await send()
        except R1Error as exc:
            _LOGGER.warning("Loa R1 %s không nhận lệnh: %s", self.client.host, exc)
            raise HomeAssistantError(f"Loa R1 không nhận lệnh: {exc}") from exc
        if self.data is not None:
            self.async_set_updated_data(with_overrides(self.data, **expected))
