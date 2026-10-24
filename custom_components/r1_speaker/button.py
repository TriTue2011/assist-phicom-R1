"""Nút «Khởi động lại loa»: gửi lệnh reboot qua ADB (dùng chung kết nối với đèn và bộ cài ứng dụng)."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb_client import AdbError
from .const import DOMAIN
from .coordinator import R1ConfigEntry
from .entity import preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "button", f"{entry.entry_id}_reboot", "r1_khoi_dong_lai")
    preregister(hass, entry, "button", f"{entry.entry_id}_chuan_bi", "r1_chuan_bi_loa")
    async_add_entities([R1RebootButton(entry), R1PrepareButton(entry)])


class R1PrepareButton(ButtonEntity):
    """«Chuẩn bị loa»: ẩn các ứng dụng gốc gây nhiễu (đảo được), giữ ijetty/netctl. Dùng cho loa mới reset trước khi cài «APK mic bộ đàm»."""
    _attr_has_entity_name = True
    _attr_translation_key = "chuan_bi"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: R1ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_chuan_bi"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        kq = await self._entry.runtime_data.apps.chuan_bi_loa()
        if not kq.ok:
            raise HomeAssistantError(kq.thong_bao)


class R1RebootButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, entry: R1ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        try:
            await self._entry.runtime_data.apps.dev.reboot()
        except (AdbError, OSError, TimeoutError) as exc:
            raise HomeAssistantError(f"Không khởi động lại được loa qua ADB: {exc or type(exc).__name__}") from exc
