"""Sensor: trạng thái thiết bị (get_info), trạng thái mic, tóm tắt cài đặt."""

from __future__ import annotations

from homeassistant.components.sensor import (SensorDeviceClass, SensorEntity, SensorEntityDescription,
                                             SensorStateClass)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, MIC_STATUSES
from .coordinator import R1ConfigEntry, R1Coordinator
from .cai_dat import R1Settings
from .entity import R1Entity, R1MicEntity, preregister

SENSORS = (
    SensorEntityDescription(key="device_state", translation_key="device_state",
                            entity_category=EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(R1Sensor(entry.runtime_data, d) for d in SENSORS)
    preregister(hass, entry, "sensor", f"{entry.entry_id}_mic_status", "r1_trang_thai_mic")
    preregister(hass, entry, "sensor", f"{entry.entry_id}_settings", "r1_cai_dat")
    async_add_entities([R1MicStatus(entry), R1Settings(entry)])
    ht = entry.runtime_data.he_thong
    for khoa, obj in (("cpu", "r1_cpu"), ("ram", "r1_ram"), ("bo_nho", "r1_bo_nho"), ("wifi", "r1_song_wifi"),
                      ("thoi_gian_chay", "r1_thoi_gian_chay")):
        preregister(hass, entry, "sensor", f"{entry.entry_id}_{khoa}", obj)
    async_add_entities(R1HeThongSensor(entry, ht, d) for d in HE_THONG)
    entry.async_create_background_task(hass, ht.async_refresh(), "r1 he thong lan dau")


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
        attrs = self._talk.as_attributes()
        duplex = getattr(self._entry.runtime_data, "duplex", None)
        if duplex is not None:
            attrs.update(duplex.as_attributes())
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._talk.add_listener(self.async_write_ha_state))
        duplex = getattr(self._entry.runtime_data, "duplex", None)
        if duplex is not None:
            self.async_on_remove(duplex.add_listener(self.async_write_ha_state))


#: (khoá, hàm lấy giá trị, hàm thuộc tính, mô tả). Chu kỳ 60 giây; chỉ chạy khi có thực thể bật.
def _cpu_attr(h):
    return {"so_nhan": h.so_nhan, "tan_so_mhz": h.tan_so_mhz,
            "tai_1_phut": h.tai[0] if h.tai else None, "tai_5_phut": h.tai[1] if h.tai else None,
            "tai_15_phut": h.tai[2] if h.tai else None, "tien_trinh_nang_nhat": h.top}


HE_THONG = (
    (SensorEntityDescription(key="cpu", translation_key="cpu", native_unit_of_measurement=PERCENTAGE,
                             state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
                             icon="mdi:cpu-32-bit", entity_category=EntityCategory.DIAGNOSTIC),
     lambda h: h.cpu_pct, _cpu_attr),
    (SensorEntityDescription(key="ram", translation_key="ram", native_unit_of_measurement=PERCENTAGE,
                             state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
                             icon="mdi:memory", entity_category=EntityCategory.DIAGNOSTIC),
     lambda h: h.ram_pct, lambda h: dict(h.ram)),
    (SensorEntityDescription(key="bo_nho", translation_key="bo_nho", native_unit_of_measurement=PERCENTAGE,
                             state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
                             icon="mdi:harddisk", entity_category=EntityCategory.DIAGNOSTIC),
     lambda h: h.bo_nho_pct, lambda h: dict(h.bo_nho)),
    (SensorEntityDescription(key="wifi", translation_key="wifi", device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                             native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                             state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC),
     lambda h: h.wifi_dbm, lambda h: {"ten_wifi": h.wifi_ssid, "toc_do_mbps": h.wifi_mbps, "tan_so_mhz": h.wifi_tan_so_mhz}),
    (SensorEntityDescription(key="thoi_gian_chay", translation_key="thoi_gian_chay", device_class=SensorDeviceClass.DURATION,
                             native_unit_of_measurement=UnitOfTime.SECONDS, suggested_unit_of_measurement=UnitOfTime.HOURS,
                             suggested_display_precision=1, entity_category=EntityCategory.DIAGNOSTIC),
     lambda h: h.chay_s, lambda h: {}),
)


class R1HeThongSensor(CoordinatorEntity, SensorEntity):
    """CPU, RAM, bộ nhớ trong, WiFi, thời gian chạy của loa (ADB, 60 giây một lần)."""

    _attr_has_entity_name = True

    def __init__(self, entry: R1ConfigEntry, coordinator, mo) -> None:
        super().__init__(coordinator)
        self.entity_description, self._lay, self._thuoc_tinh = mo[0], mo[1], mo[2]
        self._attr_unique_id = f"{entry.entry_id}_{mo[0].key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def native_value(self):
        return self._lay(self.coordinator.data) if self.coordinator.data is not None else None

    @property
    def extra_state_attributes(self) -> dict | None:
        return self._thuoc_tinh(self.coordinator.data) if self.coordinator.data is not None else None
