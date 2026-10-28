"""Nút «Khởi động lại loa»: gửi lệnh reboot qua ADB (dùng chung kết nối với đèn và bộ cài ứng dụng); ADB hỏng thì qua cổng 8080."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb_client import AdbError
from .client import R1Error
from .const import DOMAIN
from .coordinator import R1ConfigEntry
from .entity import preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "button", f"{entry.entry_id}_reboot", "r1_khoi_dong_lai")
    preregister(hass, entry, "button", f"{entry.entry_id}_chuan_bi", "r1_chuan_bi_loa")
    preregister(hass, entry, "button", f"{entry.entry_id}_dung_nhac", "r1_dung_nhac")
    preregister(hass, entry, "button", f"{entry.entry_id}_dong_adb", "r1_dong_adb")
    preregister(hass, entry, "button", f"{entry.entry_id}_tat_bao_thuc", "r1_tat_bao_thuc")
    async_add_entities([R1RebootButton(entry), R1PrepareButton(entry), R1StopButton(entry), R1CloseAdbButton(entry), R1DismissAlarmButton(entry)])


class R1DismissAlarmButton(ButtonEntity):
    """«Tắt báo thức»: im báo thức hoặc nhắc nhở đang kêu (cùng việc với dịch vụ ``bao_thuc_tat`` và hành động phím ``bao_thuc_dung``)."""

    _attr_has_entity_name = True
    _attr_translation_key = "tat_bao_thuc"

    def __init__(self, entry: R1ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_tat_bao_thuc"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        await self._entry.runtime_data.bao_thuc.tat()


class R1CloseAdbButton(ButtonEntity):
    """«Đóng ADB mạng»: loa thôi nghe cổng 5555 cho tới lần khởi động lại sau (rút điện cắm lại là mở lại). ADB mở không xác thực là
    cửa vào cho botnet cùng mạng (chủ máy 28/10/2026). Sau khi đóng, mọi việc cần ADB (đèn tự do, cài ứng dụng, khởi động lại, đọc thông
    tin hệ thống, công tắc Bluetooth) ngừng chạy cho tới khi mở lại; mic, âm lượng, phát nhạc, nút Dừng/Tắt tiếng vẫn dùng bình thường."""

    _attr_has_entity_name = True
    _attr_translation_key = "dong_adb"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: R1ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_dong_adb"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        try:
            await self._entry.runtime_data.apps.dev.dong_adb_mang()
        except (AdbError, OSError, TimeoutError) as exc:
            raise HomeAssistantError(f"Chưa đóng được ADB mạng của loa: {exc or type(exc).__name__}") from exc
        persistent_notification.async_create(
            self.hass,
            "Đã đóng ADB mạng của loa R1: không máy nào trong mạng nối được cổng 5555 nữa. Các việc cần ADB (đèn tự do, cài ứng dụng, "
            "khởi động lại từ HA, thông tin hệ thống, công tắc Bluetooth) tạm ngừng. **Mở lại: rút điện loa rồi cắm lại.**",
            title="R1: đã đóng ADB mạng", notification_id=f"{DOMAIN}_{self._entry.entry_id}_dong_adb")


class R1StopButton(ButtonEntity):
    """«Dừng nhạc»: nút Stop ở trang thiết bị. Hộp điều khiển chuẩn của Home Assistant chỉ hiện Stop khi loa KHÔNG hỗ trợ Tạm dừng, nên
    không đặt được cạnh nút Phát/Tạm dừng (chủ máy 28/10/2026: «cho stop và mute vào đây được không»); nút riêng này gọi đúng
    ``media_player.media_stop`` của loa (có kiểm loa đã dừng và tự gửi lại)."""

    _attr_has_entity_name = True
    _attr_translation_key = "dung_nhac"

    def __init__(self, entry: R1ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_dung_nhac"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_press(self) -> None:
        loa = er.async_get(self.hass).async_get_entity_id("media_player", DOMAIN, f"{self._entry.entry_id}_speaker")
        if loa is None:
            raise HomeAssistantError("Chưa có thực thể loa để dừng nhạc")
        await self.hass.services.async_call("media_player", "media_stop", {"entity_id": loa}, blocking=True)


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
            return
        except (AdbError, OSError, TimeoutError) as exc:
            loi_adb = exc or type(exc).__name__
        try:                                                        # ADB mạng đóng/hỏng: đi đường cổng 8080
            await self._entry.runtime_data.client.reboot_shell()
        except R1Error as exc:
            raise HomeAssistantError(f"Không khởi động lại được loa (ADB: {loi_adb}; cổng 8080: {exc})") from exc
