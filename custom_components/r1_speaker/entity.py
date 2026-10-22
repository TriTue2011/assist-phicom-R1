from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import with_overrides
from .const import CONFIRMED_COMMANDS, DOMAIN
from .coordinator import R1ConfigEntry, R1Coordinator
from .mic import R1Mic
from .settings import speaker_host


class R1Entity(CoordinatorEntity[R1Coordinator]):
    _attr_has_entity_name = True
    #: Tên lệnh ghi lên loa mà thực thể này gửi (None = chỉ đọc). Thẻ Lovelace dựa vào thuộc
    #: tính ``confirmed`` để gắn nhãn «chưa xác nhận» (xem const.CONFIRMED_COMMANDS).
    command: str | None = None

    def __init__(self, coordinator: R1Coordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Phicomm R1",
            manufacturer="Phicomm", model="R1",
            configuration_url=None)
        self._host = speaker_host(entry)

    def _value(self):
        """Giá trị trường tương ứng trong R1State (None = loa không báo)."""
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None \
            and self._value() is not None

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.command is None:
            return None
        return {"command": self.command, "confirmed": self.command in CONFIRMED_COMMANDS}


class R1MusicLightEntity(R1Entity):
    """Đèn theo nhạc CỦA FIRMWARE: ĐỌC từ ``get_info`` (vòng hỏi), GHI qua APK loa (khung điều khiển
    trên kết nối mic, xem ``mic_server.set_music_light``) nên chỉ dùng được khi APK đang nối về HA."""

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.mic_server.receiving

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.mic_server.add_state_listener(self.async_write_ha_state))

    async def _dat(self, ma: int, gia_tri: int, **expected) -> None:
        try:
            await self.coordinator.mic_server.set_music_light(ma, gia_tri)
        except (ConnectionError, OSError, TimeoutError) as exc:
            raise HomeAssistantError(
                "Loa chưa nối về HA (APK mic): chưa đổi được đèn nhạc") from exc
        if self.coordinator.data is not None:
            self.coordinator.async_set_updated_data(
                with_overrides(self.coordinator.data, **expected))


def preregister(hass: HomeAssistant, entry: R1ConfigEntry, domain: str, unique_id: str,
                object_id: str) -> None:
    """Đặt tên thực thể gợi ý (``<domain>.<object_id>``) trước lần đăng ký đầu; đã có thì giữ."""
    registry = er.async_get(hass)
    if registry.async_get_entity_id(domain, DOMAIN, unique_id) is None:
        registry.async_get_or_create(domain, DOMAIN, unique_id, config_entry=entry,
                                     suggested_object_id=object_id)


def device_info(entry: R1ConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Phicomm R1",
                      manufacturer="Phicomm", model="R1", configuration_url=None)


class R1MicEntity(Entity):
    """Thực thể về phần nghe: không phụ thuộc coordinator của loa (mic có luồng riêng)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: R1ConfigEntry, key: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    @property
    def mic(self) -> R1Mic:
        return self._entry.runtime_data.mic
