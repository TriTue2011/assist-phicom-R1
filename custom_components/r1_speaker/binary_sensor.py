"""Binary sensor: kênh phát về loa của bộ đàm (``binary_sensor.r1_bo_dam``)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import const
from .coordinator import R1ConfigEntry
from .phan_hoi import CHUA_BIET, PHAN_HOI
from .entity import R1MicEntity, preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "binary_sensor", f"{entry.entry_id}_intercom", "r1_bo_dam")
    preregister(hass, entry, "binary_sensor", f"{entry.entry_id}_wake", "r1_tu_danh_thuc")
    preregister(hass, entry, "binary_sensor", f"{entry.entry_id}_light_service", "r1_dich_vu_den")
    preregister(hass, entry, "binary_sensor", f"{entry.entry_id}_phan_hoi", "r1_loa_phan_hoi")
    async_add_entities([R1IntercomLink(entry), R1WakeTrigger(entry), R1LightService(entry), R1PhanHoi(entry)])


class R1PhanHoi(R1MicEntity, BinarySensorEntity):
    """«Loa phản hồi» (NV288): bật = ít nhất một tín hiệu ứng dụng (get_info, nhịp tim APK) còn tươi; tắt = loa im, thuộc tính ``ly_do`` nói rõ
    ``treo`` (mạng còn thông, ứng dụng im) hay ``mat_mang`` (không trả lời ở tầng TCP) hay ``dang_khoi_dong``; chưa biết (HA mới chạy) thì không
    có trạng thái. Thuộc tính ``lan_cuoi`` là lần cuối từng tín hiệu còn sống — số liệu thô để căn ngưỡng sau lần treo thật đầu tiên.
    Luôn khả dụng: chính lúc loa im mới là lúc cần đọc nó."""

    _attr_translation_key = "phan_hoi"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"lan_cuoi", "nguong_im_giay"})

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "phan_hoi")

    @property
    def _ph(self):
        return self._entry.runtime_data.phan_hoi

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool | None:
        return None if self._ph.ly_do == CHUA_BIET else self._ph.ly_do == PHAN_HOI

    @property
    def extra_state_attributes(self) -> dict:
        ph = self._ph
        return {"ly_do": ph.ly_do, "treo_tu": ph.treo_tu.isoformat() if ph.treo_tu else None,
                "lan_cuoi": {k: v.isoformat() if v else None for k, v in ph.lan_cuoi.items()},
                "nguong_im_giay": const.PHAN_HOI_NGUONG_IM_GIAY}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._ph.add_listener(self.async_write_ha_state))


class R1IntercomLink(R1MicEntity, BinarySensorEntity):
    """Kênh phát về loa của bộ đàm. Unavailable = chưa có kênh (APK loa chưa nối về HA và chưa cấu
    hình ``play_port``). Có kênh thì: bật = lần phát gần nhất thành công; tắt = lần gần nhất hỏng;
    chưa từng phát = chưa biết. Tự cập nhật khi APK loa nối hoặc đứt kết nối."""

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


class R1LightService(R1MicEntity, BinarySensorEntity):
    """Đường ADB tới loa (chạy hiệu ứng đèn) dùng được không: bật khi đã nối thành công và lần áp đèn gần nhất
    không lỗi. Thuộc tính ``duong_adb`` cho biết đang đi qua adb-server (``server``) hay nối thẳng (``direct``)."""

    _attr_translation_key = "light_service"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "light_service")

    @property
    def _lights(self):
        return self._entry.runtime_data.lights

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool | None:
        """ADB tới loa đang dùng được: đã nối thành công (qua adb-server hoặc nối thẳng) và lần áp đèn gần nhất không lỗi."""
        dev = getattr(self._lights.sink, "dev", None)
        if dev is None:
            return None
        if self._lights.last_error is not None:
            return False
        return True if dev.duong else None

    @property
    def extra_state_attributes(self) -> dict:
        dev = getattr(self._lights.sink, "dev", None)
        return {"duong_adb": getattr(dev, "duong", None), "che_do_adb": getattr(dev, "mode", None),
                "loi": self._lights.last_error}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._lights.add_listener(self.async_write_ha_state))


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
