from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
