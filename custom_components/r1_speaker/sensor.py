"""Sensor: thông tin từ get_info (trạng thái thiết bị, thông số đèn nhạc)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MIC_STATUSES
from .coordinator import R1ConfigEntry, R1Coordinator
from .cai_dat import R1Settings
from .entity import R1Entity, R1MicEntity, preregister

SENSORS = (
    SensorEntityDescription(key="device_state", translation_key="device_state",
                            entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key="music_light_luma", translation_key="music_light_luma",
                            entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key="music_light_chroma",
                            translation_key="music_light_chroma",
                            entity_category=EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(R1Sensor(entry.runtime_data, d) for d in SENSORS)
    preregister(hass, entry, "sensor", f"{entry.entry_id}_mic_status", "r1_trang_thai_mic")
    preregister(hass, entry, "sensor", f"{entry.entry_id}_settings", "r1_cai_dat")
    async_add_entities([R1MicStatus(entry), R1Settings(entry)])


class R1Sensor(R1Entity, SensorEntity):
    def __init__(self, coordinator: R1Coordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _value(self):
        return getattr(self.coordinator.data, self.entity_description.key)

    @property
    def native_value(self):
        return self._value() if self.coordinator.data is not None else None


class R1MicStatus(R1MicEntity, SensorEntity):
    """``sensor.r1_trang_thai_mic``: tắt / nghe / gửi — người dùng luôn thấy mic đang làm gì.

    * ``tat``: không nghe (mic tắt, chưa cấu hình, hoặc chưa có luồng).
    * ``nghe``: từ đánh thức chạy trên loa, loa còn sống, CHƯA gửi byte nào về HA.
    * ``gui``: byte mic đang về HA (chế độ ``ha`` luôn như vậy khi luồng nối; chế độ ``speaker``
      chỉ trong phiên đàm thoại).
    Thuộc tính cho thẻ: phiên đang mở, nguồn, bỏ tiếng, lần từ chối gần nhất…"""

    _attr_translation_key = "mic_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(MIC_STATUSES)

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "mic_status")

    @property
    def _talk(self):
        return self._entry.runtime_data.talk

    @property
    def native_value(self) -> str:
        return self._talk.mic_status

    @property
    def extra_state_attributes(self) -> dict:
        return self._talk.as_attributes()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._talk.add_listener(self.async_write_ha_state))
