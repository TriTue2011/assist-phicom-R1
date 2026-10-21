"""Công tắc: DLNA, AirPlay, EQ, Bass, Loudness."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .client import R1Client
from .coordinator import R1ConfigEntry, R1Coordinator
from .entity import R1Entity, R1MicEntity, preregister


@dataclass(frozen=True, kw_only=True)
class R1SwitchDescription(SwitchEntityDescription):
    field: str
    command: str
    setter: Callable[[R1Client, bool], Awaitable[None]]


SWITCHES = (
    R1SwitchDescription(key="dlna", translation_key="dlna", field="dlna_open", command="Set_DLNA_Open",
                        entity_category=EntityCategory.CONFIG,
                        setter=lambda c, on: c.set_dlna_open(on)),
    R1SwitchDescription(key="airplay", translation_key="airplay", field="airplay_open", command="Set_AirPlay_Open",
                        entity_category=EntityCategory.CONFIG,
                        setter=lambda c, on: c.set_airplay_open(on)),
    R1SwitchDescription(key="eq_enable", translation_key="eq_enable", field="eq_enable", command="set_eq_enable",
                        setter=lambda c, on: c.set_eq_enable(on)),
    R1SwitchDescription(key="bass", translation_key="bass", field="bass_enable", command="set_bass_enable",
                        setter=lambda c, on: c.set_bass_enable(on)),
    R1SwitchDescription(key="loudness", translation_key="loudness",
                        field="loudness_enable", command="set_loudness_enable",
                        setter=lambda c, on: c.set_loudness_enable(on)),
)


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(R1Switch(entry.runtime_data, d) for d in SWITCHES)
    preregister(hass, entry, "switch", f"{entry.entry_id}_mute", "r1_tat_mic")
    async_add_entities([R1MuteSwitch(entry)])


class R1Switch(R1Entity, SwitchEntity):
    entity_description: R1SwitchDescription

    def __init__(self, coordinator: R1Coordinator, description: R1SwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self.command = description.command

    def _value(self):
        return getattr(self.coordinator.data, self.entity_description.field)

    @property
    def is_on(self) -> bool | None:
        return self._value() if self.coordinator.data is not None else None

    async def _set(self, on: bool) -> None:
        d = self.entity_description
        await self.coordinator.async_command(
            lambda: d.setter(self.coordinator.client, on), **{d.field: on})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class R1MuteSwitch(R1MicEntity, SwitchEntity, RestoreEntity):
    """Bật = tắt nghe: đóng luồng mic, không nhận byte nào. Nhớ trạng thái qua lần khởi động."""

    _attr_translation_key = "mute"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "mute")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        cu = await self.async_get_last_state()
        self.mic.set_muted(cu is not None and cu.state == STATE_ON)

    @property
    def is_on(self) -> bool:
        return self.mic.muted

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.mic.set_muted(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.mic.set_muted(False)
        self.async_write_ha_state()
