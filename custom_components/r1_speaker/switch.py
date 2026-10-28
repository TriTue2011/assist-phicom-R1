"""Công tắc: DLNA, AirPlay, Bluetooth, EQ, Bass, Loudness, tắt mic, Assist, đàm thoại, mic loa song song, đèn nhạc."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import R1Client, R1Error
from .const import BT_DOI_DOC_LAI, MUSIC_LIGHT_ENABLE
from .coordinator import R1ConfigEntry, R1Coordinator
from .entity import R1Entity, R1MicEntity, R1MusicLightEntity, preregister


@dataclass(frozen=True, kw_only=True)
class R1SwitchDescription(SwitchEntityDescription):
    field: str
    command: str
    setter: Callable[[R1Client, bool], Awaitable[None]]


SWITCHES = (
    # DLNA / AirPlay / Bluetooth KHÔNG còn ẩn ở mục «Cấu hình» (chủ máy 28/10/2026: «thêm nút bật tắt … để phán đoán dễ hơn»): hiện ở
    # thẻ R1 để bật/tắt từng kết nối khi dò lỗi phát nhạc.
    R1SwitchDescription(key="dlna", translation_key="dlna", field="dlna_open", command="Set_DLNA_Open",
                        setter=lambda c, on: c.set_dlna_open(on)),
    R1SwitchDescription(key="airplay", translation_key="airplay", field="airplay_open", command="Set_AirPlay_Open",
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
    preregister(hass, entry, "switch", f"{entry.entry_id}_intercom_open", "r1_dam_thoai")
    preregister(hass, entry, "switch", f"{entry.entry_id}_song_song", "r1_mic_loa_song_song")
    preregister(hass, entry, "switch", f"{entry.entry_id}_music_light", "r1_den_nhac")
    async_add_entities([R1MuteSwitch(entry), R1AssistSwitch(entry), R1IntercomSwitch(entry),
                        R1ParallelSwitch(entry),
                        R1MusicLightSwitch(entry.runtime_data),
                        R1BluetoothSwitch(entry.runtime_data)])


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

    @property
    def extra_state_attributes(self) -> dict | None:
        """Công tắc DLNA khai thêm chẩn đoán: tích hợp đã tìm được renderer chưa, bằng đường nào, hoặc đã thử những đường nào mà hỏng."""
        base = super().extra_state_attributes
        if self.entity_description.key != "dlna":
            return base
        dmr = getattr(self.coordinator, "dmr", None)
        if dmr is None:
            return base
        if dmr.da_noi:
            ten = f"đã nối ({dmr.cach_tim})"
        elif dmr.chan_doan:
            ten = "chưa tìm được: " + "; ".join(dmr.chan_doan)
        else:
            ten = "chưa thử"
        return {**(base or {}), "renderer": ten}

    async def _set(self, on: bool) -> None:
        d = self.entity_description
        await self.coordinator.async_command(
            lambda: d.setter(self.coordinator.client, on), **{d.field: on})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class R1BluetoothSwitch(R1Entity, SwitchEntity):
    """Bluetooth của loa. **Đường chính là APK** (khả năng ``bluetooth``, 0.8.0): lệnh đi qua kết nối mic tới APK, APK gọi API Android chuẩn
    ``BluetoothAdapter.enable/disable`` rồi báo lại trạng thái THẬT (``bluetooth_trang_thai``), nên chạy cả khi đóng ADB. Theo mã firmware,
    nhóm tin 64 mà đường cũ dùng chỉ là «báo trạng thái Bluetooth» chứ không phải lệnh bật/tắt. APK cũ (không có khả năng này) thì rơi về
    đường cũ: lệnh WebSocket ``send_message`` what=64 + đọc lại qua ADB (``settings get global bluetooth_on``), CHƯA kiểm trên loa thật; công tắc
    luôn phản ánh trạng thái đọc lại, không tin lạc quan."""

    _attr_translation_key = "bluetooth"

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "bluetooth")
        self.command = "send_message(64)"

    def _he_thong(self):
        return getattr(self.coordinator, "he_thong", None)

    def _apk(self) -> bool:
        may = self.coordinator.mic_server
        return bool(may.receiving and "bluetooth" in may.apk_kha_nang)

    def _value(self):
        if self.coordinator.mic_server.bluetooth is not None:          # APK báo: trạng thái THẬT, đi cả khi đóng ADB
            return self.coordinator.mic_server.bluetooth
        he = self._he_thong()
        return None if he is None or he.data is None else he.data.bluetooth

    @property
    def available(self) -> bool:
        # Chưa đọc được trạng thái (ADB chưa nối) vẫn cho bấm lệnh; chỉ phụ thuộc kết nối chính tới loa.
        return CoordinatorEntity.available.fget(self)

    @property
    def is_on(self) -> bool | None:
        return self._value()

    @property
    def extra_state_attributes(self) -> dict:
        apk = self._apk()
        return {"nguon_trang_thai": "apk" if self.coordinator.mic_server.bluetooth is not None else "adb",
                "duong_lenh": "apk" if apk else "websocket_what_64", "da_kiem_lenh_tren_loa": False,
                "ghi_chu": ("Lệnh và trạng thái qua APK (API Bluetooth chuẩn của Android), chưa thử trên loa thật" if apk else
                            "APK chưa hỗ trợ Bluetooth (cần APK 1.3): trạng thái đọc qua ADB, lệnh bật/tắt chưa kiểm trên loa thật")
                + ("" if self._value() is not None else " (chưa đọc được trạng thái)")}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        he = self._he_thong()
        if he is not None:
            self.async_on_remove(he.async_add_listener(self.async_write_ha_state))
        self.async_on_remove(self.coordinator.mic_server.add_state_listener(self.async_write_ha_state))

    async def _dat(self, on: bool) -> None:
        if self._apk():
            try:
                await self.coordinator.mic_server.gui_bluetooth(on)
            except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
                raise HomeAssistantError(f"Loa chưa nối về HA (APK): chưa đổi được Bluetooth: {exc}") from exc
            return                                          # APK tự báo lại trạng thái thật sau ~2 giây
        try:
            await self.coordinator.client.set_bluetooth(on)
        except R1Error as exc:
            raise HomeAssistantError(f"Loa R1 không nhận lệnh Bluetooth: {exc}") from exc
        he = self._he_thong()
        if he is not None:
            await asyncio.sleep(BT_DOI_DOC_LAI)            # cho loa kịp đổi trạng thái rồi đọc lại qua ADB
            await he.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._dat(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._dat(False)


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


class R1AssistSwitch(R1MicEntity, SwitchEntity, RestoreEntity):
    """Bật = Assist hoạt động (nghe từ đánh thức, trả lời). Tắt = vệ tinh không nghe.
    Đàm thoại song công không bị ảnh hưởng. Nhớ trạng thái qua lần khởi động (mặc định bật)."""

    _attr_translation_key = "assist"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "assist")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        cu = await self.async_get_last_state()
        self.mic.set_assist(cu is None or cu.state != STATE_OFF)

    @property
    def is_on(self) -> bool:
        return self.mic.assist_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.mic.set_assist(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.mic.set_assist(False)
        self.async_write_ha_state()


class R1IntercomSwitch(R1MicEntity, SwitchEntity):
    """Đàm thoại: bật = mở phiên song công và GIỮ mở (mic mở liên tục; nghe-nói cùng lúc hay luân
    phiên theo «Chế độ đàm thoại»), tắt = đóng. «Giữ để nói» trên thẻ mở/đóng phiên bằng dịch vụ
    ``start_duplex``/``stop_duplex`` nên không đặt ``giu_mo``. Không nhớ qua lần khởi động lại: HA
    khởi động lại thì phiên đóng, mic không tự mở."""

    _attr_translation_key = "intercom_open"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "intercom_open")

    @property
    def _duplex(self):
        return self._entry.runtime_data.duplex

    @property
    def available(self) -> bool:
        return self.mic.available           # mic chưa nối / chưa cấu hình thì không đàm thoại được

    @property
    def is_on(self) -> bool:
        return self._duplex.active

    @property
    def extra_state_attributes(self) -> dict:
        return {"giu_mo": self._duplex.luon, "huong": self._duplex.huong if self._duplex.active else None}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._duplex.add_listener(self.async_write_ha_state))
        self.async_on_remove(self.mic.add_state_listener(self.async_write_ha_state))

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._duplex.active:
            await self._duplex.async_start()
        self._duplex.luon = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._duplex.end("nguoi_dung_ket_thuc")     # end() cũng xoá ``giu_mo``
        self.async_write_ha_state()


class R1ParallelSwitch(R1MicEntity, SwitchEntity, RestoreEntity):
    """«Mic loa song song»: bật = mic và loa chạy SONG SONG (nghe và nói cùng lúc, có khử vọng);
    tắt = NỬA CÔNG (mic và loa luân phiên, không tự nghe vọng). Chỉ chọn kiểu đàm thoại; «Giữ để nói»
    và «Bật mic luôn» (công tắc «Đàm thoại») là cách thao tác mic, không liên quan. Nhớ qua lần khởi
    động HA (mặc định bật)."""

    _attr_translation_key = "song_song"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "song_song")

    @property
    def _duplex(self):
        return self._entry.runtime_data.duplex

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        cu = await self.async_get_last_state()
        self._duplex.half_duplex = cu is not None and cu.state == STATE_OFF

    @property
    def is_on(self) -> bool:
        return not self._duplex.half_duplex

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._duplex.half_duplex = False
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._duplex.half_duplex = True
        self.async_write_ha_state()


class R1MusicLightSwitch(R1MusicLightEntity, SwitchEntity):
    """Bật/tắt đèn theo nhạc CỦA FIRMWARE (đọc ``music_light_enable``, ghi qua APK loa)."""

    _attr_translation_key = "music_light"

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "music_light")

    def _value(self):
        return self.coordinator.data.music_light_enable

    @property
    def is_on(self) -> bool | None:
        return self._value() if self.coordinator.data is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._dat(MUSIC_LIGHT_ENABLE, 1, music_light_enable=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._dat(MUSIC_LIGHT_ENABLE, 0, music_light_enable=False)
