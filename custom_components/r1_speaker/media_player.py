"""``media_player.r1_loa``: phát tiếng của HA ra loa R1 qua DLNA của firmware.

Không tự nói giao thức DLNA. Loa đã có DLNA renderer; tích hợp ``dlna_dmr`` có sẵn của HA
lo phần UPnP. Lớp này chỉ thêm phần dlna_dmr không biết làm: **bật DLNA trên loa trước**
(``Set_DLNA_Open``) rồi mới chuyển lệnh phát sang thực thể dlna_dmr của chính loa này.

Hợp đồng ``play_media`` (``tts.speak`` cũng đi đường này):
 - Tìm mục dlna_dmr có địa chỉ máy trùng với loa; không có → ``HomeAssistantError`` nói rõ
   phải thêm dlna_dmr (không im lặng).
 - DLNA đang tắt → gửi ``Set_DLNA_Open``, rồi chờ thực thể dlna_dmr sẵn sàng tối đa
   ``DLNA_READY_TIMEOUT`` giây; hết giờ → ``HomeAssistantError``.
 - Chuyển nguyên ``media_type``/``media_id``/tham số sang ``media_player.play_media`` của
   thực thể dlna_dmr (nó tự xử lý media_source, URL tương đối, metadata DIDL).
Ngoài phạm vi: trạng thái phát/tạm dừng/dừng (dùng thẳng thực thể dlna_dmr), âm lượng (dùng
``number`` đã có).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from .const import DLNA_READY_TIMEOUT, DOMAIN
from .coordinator import R1ConfigEntry, R1Coordinator
from .client import R1Error
from .entity import R1Entity
from .music import CONTROL_COMMANDS, PLAYLIST_COMMANDS, SEARCH_SOURCES, R1Music

_LOGGER = logging.getLogger(__name__)

DLNA_DMR_DOMAIN = "dlna_dmr"
#: Tên thực thể theo mẫu camera (``media_player.<camera>_loa``). Tên thiết bị "Phicomm R1"
#: sẽ cho ``media_player.phicomm_r1_loa``, nên đặt sẵn tên gợi ý khi đăng ký lần đầu.
SUGGESTED_OBJECT_ID = "r1_loa"
READY_POLL = 1.0
#: False: AI box đã gỡ → cổng nhạc 8082 không còn → không đăng ký dịch vụ nhạc.
MUSIC_SERVICES = False


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    unique_id = f"{entry.entry_id}_speaker"
    registry = er.async_get(hass)
    if registry.async_get_entity_id("media_player", DOMAIN, unique_id) is None:
        registry.async_get_or_create("media_player", DOMAIN, unique_id,
                                     config_entry=entry,
                                     suggested_object_id=SUGGESTED_OBJECT_ID)
    async_add_entities([R1Player(coordinator)])
    # Dịch vụ nhạc (cổng 8082 của AI box) KHÔNG đăng ký: AI box đã gỡ khỏi loa nên cổng không
    # còn. Mã giữ nguyên (music.py + các phương thức async_music_*) để dùng lại nếu cổng quay
    # lại; bật bằng MUSIC_SERVICES = True.
    if MUSIC_SERVICES:
        _register_music_services(entity_platform.async_get_current_platform())


def _register_music_services(platform) -> None:
    platform.async_register_entity_service(
        "music_play", cv.make_entity_service_schema({
            vol.Required("source"): vol.In(["youtube", "zing"]),
            vol.Optional("video_id"): cv.string, vol.Optional("song_id"): cv.string,
            vol.Optional("song_name"): cv.string, vol.Optional("artist_name"): cv.string,
        }), "async_music_play")
    platform.async_register_entity_service(
        "music_search", cv.make_entity_service_schema({
            vol.Required("source"): vol.In(list(SEARCH_SOURCES)),
            vol.Required("query"): cv.string}),
        "async_music_search", supports_response=SupportsResponse.ONLY)
    platform.async_register_entity_service(
        "music_control", cv.make_entity_service_schema({
            vol.Required("command"): vol.In(list(CONTROL_COMMANDS)
                                            + ["seek"]),
            vol.Optional("position_ms"): vol.All(int, vol.Range(min=0))}),
        "async_music_control")
    platform.async_register_entity_service(
        "music_playlist", cv.make_entity_service_schema({
            vol.Required("command"): vol.In(list(PLAYLIST_COMMANDS)),
            vol.Optional("params"): dict}),
        "async_music_playlist", supports_response=SupportsResponse.OPTIONAL)


def dlna_entity_id(hass: HomeAssistant, host: str) -> str | None:
    """Thực thể dlna_dmr cùng địa chỉ máy với loa."""
    registry = er.async_get(hass)
    for cfg in hass.config_entries.async_entries(DLNA_DMR_DOMAIN):
        if urlparse(cfg.data.get("url", "")).hostname != host:
            continue
        for ent in er.async_entries_for_config_entry(registry, cfg.entry_id):
            if ent.domain == "media_player":
                return ent.entity_id
    return None


_STATES = {"playing": MediaPlayerState.PLAYING, "paused": MediaPlayerState.PAUSED,
           "buffering": MediaPlayerState.BUFFERING, "idle": MediaPlayerState.IDLE}


def is_announcement(media_id: str, kwargs: dict[str, Any]) -> bool:
    """Phát để BÁO TIN (TTS / thông báo), không phải nhạc: ``tts.speak`` và trả lời của Assist
    đều gọi ``play_media`` với ``announce`` hoặc nguồn ``media-source://tts``."""
    return bool(kwargs.get("announce")) or str(media_id).startswith("media-source://tts")


class R1Player(R1Entity, MediaPlayerEntity):
    """Loa R1. Phát/tạm dừng/dừng và trạng thái là của thực thể dlna_dmr cùng địa chỉ máy; thực
    thể này chuyển lệnh sang đó, soi trạng thái của nó và (việc dlna_dmr không biết làm) bật
    DLNA của loa trước khi phát. Báo tin (TTS) tạm dừng nhạc rồi phát lại sau (``giu_nhac``)."""

    _attr_translation_key = "speaker"
    _attr_supported_features = (MediaPlayerEntityFeature.PLAY_MEDIA
                                | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
                                | MediaPlayerEntityFeature.PAUSE
                                | MediaPlayerEntityFeature.PLAY
                                | MediaPlayerEntityFeature.STOP)

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "speaker")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._khi_dmr_doi, event_filter=self._la_dmr))

    @callback
    def _la_dmr(self, data: dict[str, Any]) -> bool:
        eid = data.get("entity_id", "")
        return eid.startswith("media_player.") and eid == self._dlna_entity_id()

    @callback
    def _khi_dmr_doi(self, _event: Event) -> None:
        self.async_write_ha_state()

    def _dmr_state(self):
        eid = self._dlna_entity_id()
        return self.hass.states.get(eid) if eid else None

    @property
    def state(self) -> MediaPlayerState:
        st = self._dmr_state()
        return _STATES.get(st.state, MediaPlayerState.IDLE) if st is not None \
            else MediaPlayerState.IDLE

    @property
    def media_title(self) -> str | None:
        st = self._dmr_state()
        return st.attributes.get("media_title") if st is not None else None

    @property
    def media_content_id(self) -> str | None:
        st = self._dmr_state()
        return st.attributes.get("media_content_id") if st is not None else None

    @property
    def available(self) -> bool:
        # Khác các thực thể khác: DLNA tắt (dlna_open False/None) vẫn phát được vì ta bật nó.
        return CoordinatorEntity.available.fget(self)

    def _dlna_entity_id(self) -> str | None:
        return dlna_entity_id(self.hass, self._host)

    async def _wait_ready(self, entity_id: str) -> None:
        """Chờ thực thể dlna_dmr có trạng thái dùng được. Cứ ~1 giây ép nó thử nối lại:
        với "poll availability" bật (luồng thêm tay) đó là cách nó nối được ngay khi DLNA
        của loa vừa lên; không bật thì nó chỉ nối khi nghe SSDP alive từ loa."""
        async with asyncio.timeout(DLNA_READY_TIMEOUT):
            while (st := self.hass.states.get(entity_id)) is None \
                    or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                await self.hass.services.async_call(
                    "homeassistant", "update_entity", {"entity_id": entity_id},
                    blocking=True)
                await asyncio.sleep(READY_POLL)

    async def _dlna_goi(self, service: str) -> None:
        target = self._dlna_entity_id()
        if target is None:
            raise HomeAssistantError(
                f"Chưa có tích hợp dlna_dmr cho loa {self._host}: thêm DLNA Digital Media "
                "Renderer (Cài đặt → Thiết bị) rồi thử lại.")
        await self.hass.services.async_call(
            "media_player", service, {"entity_id": target}, blocking=True)

    async def async_media_pause(self) -> None:
        await self._dlna_goi("media_pause")

    async def async_media_play(self) -> None:
        await self._dlna_goi("media_play")

    async def async_media_stop(self) -> None:
        await self._dlna_goi("media_stop")

    async def async_play_media(self, media_type: MediaType | str, media_id: str,
                               **kwargs: Any) -> None:
        """Nhạc: chuyển thẳng sang dlna_dmr. Báo tin (TTS / announce): tạm dừng nhạc trước,
        phát tin, rồi NỀN theo dõi tin phát xong và khôi phục nhạc — lệnh này trả về ngay sau
        khi đã gửi tin đi, không chờ hết tin (``tts.speak`` khỏi bị treo)."""
        if not is_announcement(media_id, kwargs):
            await self._phat_toi_dlna(media_type, media_id, **kwargs)
            return
        talk = self.coordinator.talk
        giu = await talk.music.hold()
        try:
            await self._phat_toi_dlna(media_type, media_id, **kwargs)
        except BaseException:
            await giu.release()
            raise
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self._theo_doi_tin(giu), f"{self.entity_id} announce")

    async def _theo_doi_tin(self, giu) -> None:
        """Chờ tin bắt đầu rồi kết thúc (theo trạng thái dlna_dmr), báo vệ tinh, nhả nhạc."""
        talk = self.coordinator.talk
        try:
            eid = self._dlna_entity_id()

            def dang_phat() -> bool:
                st = self.hass.states.get(eid) if eid else None
                return st is not None and st.state in ("playing", "buffering")

            async with asyncio.timeout(const.ANNOUNCE_START_WAIT + const.ANNOUNCE_MAX):
                for _ in range(int(const.ANNOUNCE_START_WAIT / 0.05) + 1):
                    if dang_phat():
                        break
                    await asyncio.sleep(0.05)
                else:
                    return
                while dang_phat():
                    await asyncio.sleep(0.05)
        except TimeoutError:
            _LOGGER.warning("tin trên %s chưa xong sau %.0f giây — khôi phục nhạc",
                            self.entity_id, const.ANNOUNCE_MAX)
        finally:
            talk.announce_done()
            await giu.release()

    async def _phat_toi_dlna(self, media_type: MediaType | str, media_id: str,
                             **kwargs: Any) -> None:
        target = self._dlna_entity_id()
        if target is None:
            raise HomeAssistantError(
                f"Chưa có tích hợp dlna_dmr cho loa {self._host}: thêm "
                "DLNA Digital Media Renderer (Cài đặt → Thiết bị) rồi thử lại.")
        data = self.coordinator.data
        if data is None or not data.dlna_open:
            await self.coordinator.async_command(
                lambda: self.coordinator.client.set_dlna_open(True), dlna_open=True)
        try:
            await self._wait_ready(target)
        except TimeoutError:
            raise HomeAssistantError(
                f"{target} chưa sẵn sàng sau {DLNA_READY_TIMEOUT:.0f} giây "
                "(DLNA của loa chưa lên?).") from None
        service_data = {"entity_id": target, "media_content_type": media_type,
                        "media_content_id": media_id}
        for key in ("announce", "enqueue", "extra"):
            if kwargs.get(key) is not None:
                service_data[key] = kwargs[key]
        await self.hass.services.async_call("media_player", "play_media", service_data,
                                            blocking=True)

    # ── nhạc qua cổng 8082 (firmware có sẵn) ────────────────────────────────────

    @property
    def _music(self) -> R1Music:
        return R1Music(async_get_clientsession(self.hass), self._host)

    @staticmethod
    def _wrap(exc: R1Error) -> HomeAssistantError:
        return HomeAssistantError(f"Loa R1: {exc}")

    async def async_music_play(self, source: str, video_id: str | None = None,
                               song_id: str | None = None, song_name: str | None = None,
                               artist_name: str | None = None) -> None:
        try:
            if source == "youtube":
                await self._music.play_youtube(video_id or "")
            else:
                await self._music.play_zing(song_id, song_name, artist_name)
        except R1Error as exc:
            raise self._wrap(exc) from exc

    async def async_music_search(self, source: str, query: str) -> ServiceResponse:
        try:
            return {"result": await self._music.search(source, query)}
        except R1Error as exc:
            raise self._wrap(exc) from exc

    async def async_music_control(self, command: str, position_ms: int | None = None) -> None:
        try:
            if command == "seek":
                if position_ms is None:
                    raise R1Error("seek cần position_ms")
                await self._music.seek(position_ms)
            else:
                await self._music.control(command)
        except R1Error as exc:
            raise self._wrap(exc) from exc

    async def async_music_playlist(self, command: str,
                                   params: dict[str, Any] | None = None) -> ServiceResponse:
        try:
            return {"result": await self._music.playlist(command, params)}
        except R1Error as exc:
            raise self._wrap(exc) from exc
