"""Time: giờ khởi động lại loa theo lịch (NV288/NV302)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import thuc_the_tuy_chon
from .coordinator import R1ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(thuc_the_tuy_chon.times(hass, entry))
