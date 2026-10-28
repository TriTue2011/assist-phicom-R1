"""Thực thể sự kiện ``event.r1_phim``: mỗi cử chỉ phím trên loa (đơn, đúp, ba, giữ, nhấn ngắn) phát một sự kiện, dùng làm điều kiện kích hoạt trong tự động hoá."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import R1ConfigEntry
from .entity import preregister
from .phim import CU_CHI_SU_KIEN


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "event", f"{entry.entry_id}_phim", "r1_phim")
    async_add_entities([R1PhimEvent(entry)])


class R1PhimEvent(EventEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "phim"
    _attr_event_types = list(CU_CHI_SU_KIEN)

    def __init__(self, entry: R1ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_phim"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        phim = self._entry.runtime_data.phim
        phim.tren_su_kien.append(self._tren)
        self.async_on_remove(lambda: phim.tren_su_kien.remove(self._tren))

    def _tren(self, cu_chi: str, ma: int) -> None:
        self._trigger_event(cu_chi, {"phim": ma})
        self.async_write_ha_state()
