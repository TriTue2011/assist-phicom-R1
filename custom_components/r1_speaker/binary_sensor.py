"""Binary sensor: kênh phát về loa của bộ đàm (``binary_sensor.r1_bo_dam``)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import R1ConfigEntry
from .entity import R1MicEntity, preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "binary_sensor", f"{entry.entry_id}_intercom", "r1_bo_dam")
    preregister(hass, entry, "binary_sensor", f"{entry.entry_id}_wake", "r1_tu_danh_thuc")
    async_add_entities([R1IntercomLink(entry), R1WakeTrigger(entry)])


class R1IntercomLink(R1MicEntity, BinarySensorEntity):
    """Bật = lần phát về loa gần nhất thành công; tắt = lần gần nhất hỏng (loa không nhận);
    chưa từng thử = trạng thái chưa biết. Unavailable = chưa cấu hình ``play_port`` (bộ đàm
    tắt). Phía loa nhận PCM CHƯA có nên hiện chưa thể bật."""

    _attr_translation_key = "intercom"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "intercom")

    @property
    def _playback(self):
        return self._entry.runtime_data.playback

    @property
    def available(self) -> bool:
        return self._playback.configured

    @property
    def is_on(self) -> bool | None:
        return self._playback.ok

    @property
    def extra_state_attributes(self) -> dict:
        talk = self._entry.runtime_data.intercom
        return {"talking": talk.talking, "mic_held": self._entry.runtime_data.mic.holding}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._playback.add_state_listener(self.async_write_ha_state))


class R1WakeTrigger(R1MicEntity, BinarySensorEntity):
    """Trigger từ đánh thức do LOA báo (``POST /api/r1_speaker/wake/<entry>``): bật vài giây
    sau mỗi lần nghe từ gọi, kèm sự kiện ``r1_speaker_wake`` cho tự động hoá.

    **PHÍA LOA CHƯA CÓ (CHỜ)**: thuộc tính ``phia_loa`` là ``CHO_PHIA_LOA`` cho tới khi loa
    gọi vào lần đầu. Từ đánh thức chạy TRÊN LOA, HA chỉ nhận luồng mic sau trigger này."""

    _attr_translation_key = "wake"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "wake")

    @property
    def _talk(self):
        return self._entry.runtime_data.talk

    @property
    def is_on(self) -> bool:
        return self._talk.wake_pulse

    @property
    def extra_state_attributes(self) -> dict:
        t = self._talk
        return {"che_do": t.wake_mode, "phia_loa": "da_ket_noi" if t.last_alive else "CHO_PHIA_LOA",
                "lan_cuoi": t.last_wake.isoformat() if t.last_wake else None,
                "tu": t.last_wake_word}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._talk.add_listener(self.async_write_ha_state))
