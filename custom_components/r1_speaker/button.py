"""Nút: ``button.r1_dam_thoai`` (mở phiên đàm thoại) và ``button.r1_ket_thuc_dam_thoai``.

Bấm «đàm thoại»: tạm dừng nhạc đang phát trên loa, mở MỘT phiên Assist (HA làm máy chủ:
pipeline chọn ở ``select.r1_tro_ly`` lo STT / hiểu lệnh / TTS); phiên đóng thì nhạc phát lại.
Đang có phiên khác thì nút KHÔNG làm gì ngoài việc báo lỗi rõ cho người bấm (xem
``dam_thoai.R1SessionBusy``) — không xếp hàng, không treo.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import R1ConfigEntry
from .entity import R1MicEntity, preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "button", f"{entry.entry_id}_talk", "r1_dam_thoai")
    preregister(hass, entry, "button", f"{entry.entry_id}_end_talk", "r1_ket_thuc_dam_thoai")
    async_add_entities([R1TalkButton(entry), R1EndTalkButton(entry)])


class _TalkEntity(R1MicEntity, ButtonEntity):
    @property
    def talk(self):
        return self._entry.runtime_data.talk

    @property
    def available(self) -> bool:
        return self.mic.available

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.talk.add_listener(self.async_write_ha_state))


class R1TalkButton(_TalkEntity):
    _attr_translation_key = "talk"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "talk")

    async def async_press(self) -> None:
        await self.talk.async_start("button")


class R1EndTalkButton(_TalkEntity):
    _attr_translation_key = "end_talk"

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "end_talk")

    async def async_press(self) -> None:
        talk = self.talk
        talk.end(talk.session, "nguoi_dung_ket_thuc")
        await talk.async_settle()
