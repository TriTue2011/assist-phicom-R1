"""``media_player.r1_loa``: phát tiếng của HA ra loa R1 qua DLNA có sẵn của firmware, TỰ ĐIỀU KHIỂN (không cần ``dlna_dmr``).

Chủ máy 28/10/2026: «trên R1 custom không cần thêm DLNA hay AirPlay riêng». Lớp ``dmr.R1Dmr`` tự tìm renderer (SSDP unicast tới loa)
và nói UPnP AV bằng ``async_upnp_client`` sẵn có của Home Assistant; thực thể này tự giữ trạng thái, tiến độ, thời lượng và lý do idle.

Hợp đồng ``play_media`` (``tts.speak`` cũng đi đường này):
 - DLNA của loa đang tắt → gửi ``Set_DLNA_Open``, rồi chờ renderer lên tối đa ``DLNA_READY_TIMEOUT`` giây; hết giờ → ``HomeAssistantError``.
 - ``media-source://`` được giải ra URL, URL tương đối được đổi thành địa chỉ HA tới được từ loa.
 - Báo tin (TTS / ``announce``): tạm dừng nhạc, phát tin, rồi nền theo dõi tin xong và khôi phục nhạc (``giu_nhac``).
Trạng thái chỉ được hỏi lại có chu kỳ KHI ĐANG PHÁT (2,9 giây; 1 giây khi đang báo tin) và sau mỗi lệnh; idle/tạm dừng thì không hỏi nền.
``idle_reason`` (``finished`` / ``stopped`` / ``interrupted`` / ``error``) khai khi idle để tích hợp phát nhạc phân biệt Stop với hết bài.
Âm lượng dùng đường APK có sẵn (``number``).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from dataclasses import replace
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components import media_source
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const
from .const import DLNA_READY_TIMEOUT, DOMAIN
from .dmr import R1Dmr, R1DmrError, TrangThaiDmr, UocViTri
from .coordinator import R1ConfigEntry, R1Coordinator
from .client import R1Error
from .entity import R1Entity
from .music import CONTROL_COMMANDS, PLAYLIST_COMMANDS, SEARCH_SOURCES, R1Music

_LOGGER = logging.getLogger(__name__)

#: Tên thực thể theo mẫu camera (``media_player.<camera>_loa``). Tên thiết bị "Phicomm R1"
#: sẽ cho ``media_player.phicomm_r1_loa``, nên đặt sẵn tên gợi ý khi đăng ký lần đầu.
SUGGESTED_OBJECT_ID = "r1_loa"
#: Hỏi lại trạng thái renderer khi đang phát nhạc / khi đang báo tin (giây).
# KHÔNG đặt chu kỳ là số nguyên giây: RelTime báo nguyên giây, hỏi đúng bội số nguyên thì luôn ở cùng một pha và ``UocViTri`` không co lại
# được (sai kẹt ~0,3 giây); chu kỳ lẻ làm pha đổi dần nên ước chính xác dần.
CHAM_NHAC = 2.9
CHAM_TIN = 1.0
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


_STATES = {"playing": MediaPlayerState.PLAYING, "paused": MediaPlayerState.PAUSED,
           "buffering": MediaPlayerState.BUFFERING, "idle": MediaPlayerState.IDLE}


def is_announcement(media_id: str, kwargs: dict[str, Any]) -> bool:
    """Phát để BÁO TIN (TTS / thông báo), không phải nhạc: ``tts.speak`` và trả lời của Assist
    đều gọi ``play_media`` với ``announce`` hoặc nguồn ``media-source://tts``."""
    return bool(kwargs.get("announce")) or str(media_id).startswith("media-source://tts")


class R1Player(R1Entity, MediaPlayerEntity):
    """Loa R1: tự điều khiển renderer DLNA của loa (``dmr.R1Dmr``), giữ trạng thái/tiến độ/thời lượng/lý do idle. Báo tin (TTS)
    tạm dừng nhạc rồi phát lại sau (``giu_nhac``)."""

    _attr_translation_key = "speaker"
    _attr_supported_features = (MediaPlayerEntityFeature.PLAY_MEDIA
                                | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
                                | MediaPlayerEntityFeature.PAUSE
                                | MediaPlayerEntityFeature.PLAY
                                | MediaPlayerEntityFeature.STOP
                                | MediaPlayerEntityFeature.SEEK
                                | MediaPlayerEntityFeature.VOLUME_SET
                                | MediaPlayerEntityFeature.VOLUME_STEP)

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "speaker")
        self._tt = TrangThaiDmr(state="idle")
        self._tt_utc = None                  # lúc đọc trạng thái (để ngoại suy vị trí)
        self._uri: str | None = None         # media_id gốc đã phát (để giu_nhac đặt lại đúng bài)
        self._tieu_de: str | None = None
        self._ly_do: str | None = None       # idle_reason
        self._nhanh = False                  # đang báo tin: hỏi lại trạng thái dày hơn
        self._cham: asyncio.Task | None = None
        self._dang_dong_bo = False           # một lượt đọc theo chu kỳ coordinator đang chạy
        self._uoc = UocViTri()               # vị trí chính xác hơn 1 giây từ RelTime nguyên giây
        self._ghi_luc = 0.0                  # lúc (đồng hồ đơn điệu) ghi trạng thái gần nhất

    @property
    def _dmr(self) -> R1Dmr:
        return self.coordinator.dmr

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Âm lượng là của APK (mức nhạc): đổi ở loa/ở số → cập nhật thanh trượt của thẻ YouTube.
        self.async_on_remove(self.coordinator.mic_server.add_state_listener(self.async_write_ha_state))
        # Bên giữ nhạc cần trạng thái MỚI trước khi chụp (nhạc có thể do thiết bị khác bật, ta không hỏi nền lúc idle).
        self.coordinator.lam_moi_loa = functools.partial(self.async_lam_moi, chi_khi_da_noi=True)
        self.async_on_remove(self._huy_cham)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Mỗi chu kỳ coordinator (10 giây) mà DLNA của loa đang bật và ta không có vòng hỏi nào: đọc lại trạng thái renderer, để
        thẻ thấy cả nhạc do thiết bị khác bật (điện thoại, DLNA controller). Không thêm bộ hẹn giờ mới."""
        super()._handle_coordinator_update()
        data = self.coordinator.data
        if (data is not None and data.dlna_open and not self._dang_dong_bo
                and (self._cham is None or self._cham.done())):
            self._dang_dong_bo = True
            self.coordinator.config_entry.async_create_background_task(
                self.hass, self._dong_bo_nen(), f"{self.entity_id} dmr sync")

    async def _dong_bo_nen(self) -> None:
        try:
            await self.async_lam_moi()
        finally:
            self._dang_dong_bo = False

    @callback
    def _huy_cham(self) -> None:
        self.coordinator.lam_moi_loa = None
        if self._cham is not None and not self._cham.done():
            self._cham.cancel()

    # Âm lượng nhạc qua APK (cùng đường với ``number.r1_am_luong``): thẻ YouTube chỉnh âm lượng loa bằng ``volume_set``.
    @property
    def volume_level(self) -> float | None:
        am = self.coordinator.mic_server.am_luong
        return round(am[0] / am[1], 4) if am else None

    @property
    def volume_step(self) -> float:
        am = self.coordinator.mic_server.am_luong
        return 1 / am[1] if am else 1 / const.VOL_MAX

    async def async_set_volume_level(self, volume: float) -> None:
        am = self.coordinator.mic_server.am_luong
        toi_da = am[1] if am else const.VOL_MAX
        muc = min(max(round(volume * toi_da), 0), toi_da)
        try:
            await self.coordinator.mic_server.gui_am_luong(muc)
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            raise HomeAssistantError("Loa chưa nối về HA (APK mic): chưa đổi được âm lượng") from exc

    # ── trạng thái ─────────────────────────────────────────────────────────────

    @property
    def state(self) -> MediaPlayerState:
        return _STATES.get(self._tt.state, MediaPlayerState.IDLE)

    @property
    def media_title(self) -> str | None:
        return self._tieu_de if self._tt.state != "idle" else None

    @property
    def media_content_id(self) -> str | None:
        return (self._uri or self._tt.uri) if self._tt.state != "idle" else None

    @property
    def media_position(self) -> float | None:
        return None if self._tt.position is None else round(self._tt.position, 1)

    @property
    def media_position_updated_at(self):
        return self._tt_utc if self._tt.position is not None else None

    @property
    def media_duration(self) -> int | None:
        return None if not self._tt.duration else int(self._tt.duration)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """``idle_reason``: vì sao loa đang idle (``finished`` hết bài / ``stopped`` người dùng dừng / ``interrupted`` bị bài mới
        thay / ``error`` lỗi phát). Chỉ có khi idle; tích hợp phát nhạc (YouTube) đọc nó thay vì đoán bằng thời lượng bài."""
        if self._tt.state == "idle" and self._ly_do:
            return {"idle_reason": self._ly_do}
        return None

    @property
    def available(self) -> bool:
        # Khác các thực thể khác: DLNA tắt (dlna_open False/None) vẫn phát được vì ta bật nó.
        return CoordinatorEntity.available.fget(self)

    @callback
    def _ap_dung(self, tt: TrangThaiDmr) -> None:
        cu = self._tt
        if tt.state == "idle":
            if self._ly_do is None and cu.state in ("playing", "buffering"):
                self._ly_do = "error" if tt.loi else "finished"        # renderer tự dừng: không do lệnh của ta
        else:
            self._ly_do = None
        now_m = time.monotonic()
        now_u = dt_util.utcnow()
        # Vị trí: RelTime chỉ có số NGUYÊN giây (cắt xuống) → ước chính xác hơn bằng giao các ràng buộc (UocViTri). Chỉ khi đang phát;
        # tạm dừng/dừng/đổi trạng thái thì ước bắt đầu lại (đồng hồ không còn chạy cùng nhịp với vị trí).
        if tt.state == "playing" and tt.position is not None and cu.state == "playing" and cu.uri == tt.uri:
            uoc = self._uoc.them(tt.position, now_m)
        else:
            self._uoc.reset()
            uoc = self._uoc.them(tt.position, now_m) if tt.state == "playing" and tt.position is not None else None
        if uoc is not None:
            tt = replace(tt, position=uoc)
        du_kien = None
        if cu.position is not None and cu.state == "playing" and self._tt_utc is not None:
            du_kien = cu.position + (now_u - self._tt_utc).total_seconds()
        # Ghi lại khi vị trí đã lệch khỏi lời khai cũ (ngoại suy) quá 0,3 giây, hoặc đã 15 giây chưa làm mới: để người đọc
        # (youtube đồng bộ nhiều loa) luôn có cặp (vị trí, thời điểm) mới — trước đây chỉ ghi khi nhảy 2,5 giây nên cặp cũ dần sai.
        nhay = tt.position is not None and (du_kien is None or abs(tt.position - du_kien) > 0.3
                                            or now_m - self._ghi_luc >= 15.0)
        thay = (tt.state, tt.uri, tt.duration) != (cu.state, cu.uri, cu.duration)
        if thay or nhay:
            self._tt, self._tt_utc, self._ghi_luc = tt, now_u, now_m
        else:
            self._tt = replace(tt, position=cu.position)             # giữ cặp (vị trí, thời điểm) đã khai: không ghi
        if tt.state not in ("playing", "buffering") and self._cham is not None and self._cham is not asyncio.current_task():
            # Không còn phát: vòng hỏi lại thôi ngay, không thức thêm lượt. Bỏ tham chiếu NGAY: tác vụ đã huỷ chưa «xong» cho tới
            # vòng lặp kế, nên giữ lại thì ``_bat_dau_cham`` tưởng nó còn sống và không bật vòng mới khi nhạc phát lại.
            cham, self._cham = self._cham, None
            cham.cancel()
        if thay or nhay:
            self.async_write_ha_state()

    async def _doc(self) -> TrangThaiDmr | None:
        """Hỏi trạng thái renderer; không trả lời được thì coi như dừng vì lỗi (ghi một dòng nhật ký)."""
        try:
            tt = await self._dmr.async_doc()
        except R1DmrError as exc:
            if self._tt.state != "idle":
                _LOGGER.warning("%s: %s", self.entity_id, exc)
                self._ly_do = "error"
                self._ap_dung(TrangThaiDmr(state="idle", loi=True))
            return None
        self._ap_dung(tt)
        return tt

    async def async_lam_moi(self, *, chi_khi_da_noi: bool = False) -> None:
        """Đọc trạng thái ngay; đang phát thì bật vòng hỏi lại có chu kỳ. DLNA của loa đang tắt thì không có renderer để hỏi.
        ``chi_khi_da_noi``: bên giữ nhạc gọi mỗi lần mở phiên đàm thoại — chưa nối renderer thì bỏ qua (đừng chờ SSDP làm chậm
        việc mở phiên; vòng đọc theo chu kỳ coordinator sẽ nối trong nền)."""
        data = self.coordinator.data
        if data is None or not data.dlna_open or (chi_khi_da_noi and not self._dmr.da_noi):
            return
        tt = await self._doc()
        if tt is not None and tt.state in ("playing", "buffering"):
            self._bat_dau_cham()

    def _bat_dau_cham(self) -> None:
        if self._cham is None or self._cham.done():
            self._cham = self.coordinator.config_entry.async_create_background_task(
                self.hass, self._cham_vong(), f"{self.entity_id} dmr poll")

    async def _cham_vong(self) -> None:
        """Chỉ chạy khi đang phát; idle/tạm dừng/lỗi thì dừng (không hỏi nền)."""
        while True:
            await asyncio.sleep(CHAM_TIN if self._nhanh else CHAM_NHAC)
            tt = await self._doc()
            if tt is None or tt.state not in ("playing", "buffering"):
                return

    async def _cho_trang_thai(self, mong_doi: set[str], toi_da: float = 3.0) -> None:
        """Sau một lệnh, đọc lại cho tới khi renderer đổi sang trạng thái mong đợi (loa trả lời trễ vài trăm mili giây)."""
        han = time.monotonic() + toi_da
        while True:
            tt = await self._doc()
            if tt is None or tt.state in mong_doi or time.monotonic() >= han:
                break
            await asyncio.sleep(0.25)
        if self._tt.state in ("playing", "buffering"):
            self._bat_dau_cham()

    # ── lệnh ───────────────────────────────────────────────────────────────────

    async def _lenh(self, viec, mong_doi: set[str]) -> None:
        try:
            await viec()
        except R1DmrError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await self._cho_trang_thai(mong_doi)

    async def async_media_pause(self) -> None:
        await self._lenh(self._dmr.async_tam_dung, {"paused", "idle"})

    async def async_media_play(self) -> None:
        await self._lenh(self._dmr.async_tiep, {"playing", "buffering"})

    async def async_media_stop(self) -> None:
        self._ly_do = "stopped"
        await self._lenh(self._dmr.async_dung, {"idle"})

    async def async_media_seek(self, position: float) -> None:
        await self._lenh(lambda: self._dmr.async_tua(position), {"playing", "buffering", "paused"})

    async def async_play_media(self, media_type: MediaType | str, media_id: str,
                               **kwargs: Any) -> None:
        """Nhạc: phát thẳng qua renderer. Báo tin (TTS / announce): tạm dừng nhạc trước, phát tin, rồi NỀN theo dõi tin phát
        xong và khôi phục nhạc — lệnh này trả về ngay sau khi đã gửi tin đi, không chờ hết tin (``tts.speak`` khỏi bị treo)."""
        if not is_announcement(media_id, kwargs):
            await self._phat_dmr(media_type, media_id, **kwargs)
            return
        talk = self.coordinator.talk
        giu = await talk.music.hold()
        try:
            self._nhanh = True
            await self._phat_dmr(media_type, media_id, **kwargs)
        except BaseException:
            self._nhanh = False
            await giu.release()
            raise
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self._theo_doi_tin(giu), f"{self.entity_id} announce")

    async def _theo_doi_tin(self, giu) -> None:
        """Chờ tin bắt đầu rồi kết thúc (theo trạng thái renderer), báo vệ tinh, nhả nhạc."""
        talk = self.coordinator.talk
        try:
            def dang_phat() -> bool:
                return self._tt.state in ("playing", "buffering")

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
            self._nhanh = False
            talk.announce_done()
            await giu.release()

    async def _phat_dmr(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> None:
        data = self.coordinator.data
        if data is None or not data.dlna_open:
            await self.coordinator.async_command(
                lambda: self.coordinator.client.set_dlna_open(True), dlna_open=True)
        try:
            await self._dmr.async_san_sang(DLNA_READY_TIMEOUT)
        except R1DmrError as exc:
            raise HomeAssistantError(str(exc)) from exc
        url = media_id
        if media_source.is_media_source_id(media_id):
            url = (await media_source.async_resolve_media(self.hass, media_id, self.entity_id)).url
        url = async_process_play_media_url(self.hass, url)
        tieu_de = str((kwargs.get("extra") or {}).get("title") or "Home Assistant")
        self._ly_do, self._uri, self._tieu_de = "interrupted", media_id, tieu_de
        try:
            await self._dmr.async_phat(url, tieu_de)
        except R1DmrError as exc:
            self._ly_do = "error"
            raise HomeAssistantError(str(exc)) from exc
        await self._cho_trang_thai({"playing", "buffering"})

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
