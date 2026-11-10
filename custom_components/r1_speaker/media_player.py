"""``media_player.r1_loa``: phát tiếng của HA ra loa R1 qua DLNA có sẵn của firmware, TỰ ĐIỀU KHIỂN (không cần ``dlna_dmr``).

Chủ máy 28/10/2026: «trên R1 custom không cần thêm DLNA hay AirPlay riêng». Lớp ``dmr.R1Dmr`` tự tìm renderer (SSDP unicast tới loa)
và nói UPnP AV bằng ``async_upnp_client`` sẵn có của Home Assistant; thực thể này tự giữ trạng thái, tiến độ, thời lượng và lý do idle.

Hợp đồng ``play_media`` (``tts.speak`` cũng đi đường này):
 - DLNA của loa đang tắt → gửi ``Set_DLNA_Open``, rồi chờ renderer lên tối đa ``DLNA_READY_TIMEOUT`` giây; hết giờ → ``HomeAssistantError``.
 - ``media-source://`` được giải ra URL, URL tương đối được đổi thành địa chỉ HA tới được từ loa.
 - Báo tin (TTS / ``announce``): tạm dừng nhạc, phát tin, rồi nền theo dõi tin xong và khôi phục nhạc (``giu_nhac``).
Trạng thái chỉ được hỏi lại có chu kỳ KHI ĐANG PHÁT (2,9 giây; 1 giây khi đang báo tin) và sau mỗi lệnh; idle/tạm dừng thì không hỏi nền.
``idle_reason`` (``finished`` / ``stopped`` / ``interrupted`` / ``error`` / ``dang_giu``) khai khi idle để tích hợp phát nhạc phân biệt Stop với hết bài.
Âm lượng dùng đường APK có sẵn (``number``).

Đường phát thứ hai, AirPlay (chủ máy 29/10/2026: «song song bù trừ nhau», «tích hợp riêng, không phụ thuộc bên khác»): tuỳ chọn ``duong_phat``
chọn ``dlna`` (mặc định, như trước) / ``dlna_truoc`` / ``airplay_truoc`` / ``airplay``. Hai đường BÙ TRỪ nhau: đường đầu hỏng thì thử đường kia, và
đường bị bỏ luôn được DỪNG trước để loa không bao giờ phát hai nơi. «Hỏng» chỉ tính theo tín hiệu chắc chắn: DLNA = lệnh SOAP bị từ chối hoặc
renderer báo ``ERROR_OCCURRED``; AirPlay = chưa có gói tiếng đầu sau ``AIRPLAY_BAT_DAU_TOI_DA`` giây hoặc bộ gửi báo lỗi. Một luồng chỉ chậm KHÔNG
bị coi là hỏng. Khi AirPlay đang phát, mọi kết quả hỏi DLNA bị bỏ qua tại MỘT cổng (``_doc``) nên không ghi đè trạng thái. AirPlay do ``airplay.py``
gửi thẳng (RAOP/PCM), giải mã bằng ffmpeg của máy chạy HA; không biết thời lượng bài; tua = phát lại từ vị trí đó.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from dataclasses import replace
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components import media_source
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.helpers.network import NoURLAvailableError, get_url, is_hass_url
import yarl
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import const
from .const import AIRPLAY_BAT_DAU_TOI_DA, DLNA_READY_TIMEOUT, DOMAIN
from .settings import am_luong_media, am_luong_tin, airplay_port, ha_url, duong_phat, tts_song_song_airplay, ha_nhac_xuong, ha_nhac_nac
from .dmr import R1Dmr, R1DmrError, TrangThaiDmr, UocViTri
from .coordinator import R1ConfigEntry, R1Coordinator
from .client import R1Error
from .airplay import LoiAirPlay, LoiKhongNoi, NguonChung, PhienAirPlay, tao_nguon
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
#: NV303 — nhạc ở AirPlay, tin báo đi DLNA song song: chờ renderer DLNA lên (DLNA của loa có thể đang tắt) tối đa ngần này giây rồi về đường
#: thường (đừng chờ cả ``DLNA_READY_TIMEOUT`` mà để người dùng nghe im lặng); hỏi tiến độ tin mỗi ``CHAM_TIN_NGUOC`` giây.
DLNA_TIN_NGUOC_SAN_SANG = 4.0
CHAM_TIN_NGUOC = 0.5
#: Stop: chờ renderer về idle tối đa ngần này giây mỗi lần; còn phát thì gửi lại (thêm tối đa ngần này lần).
STOP_CHO_XAC_NHAN = 1.5
STOP_GUI_LAI = 2
#: ``idle_reason`` khi renderer về idle trong lúc loa đang GIỮ nhạc cho tin báo / phiên đàm thoại (NV287). Xem ``_ap_dung``.
IDLE_DANG_GIU = "dang_giu"
#: Hỏi trạng thái renderer hỏng ngần này lần LIÊN TIẾP mới coi là loa mất/lỗi (một lần trễ thoáng qua của loa yếu không được báo «đã dừng»).
LOI_DOC_TOI_DA = 3
#: False: AI box đã gỡ → cổng nhạc 8082 không còn → không đăng ký dịch vụ nhạc.
MUSIC_SERVICES = False


#: Khoá trong ``hass.data[DOMAIN]``: các ``R1Player`` đang có mặt, theo entity_id.
HOA_LOA = "media_players"
SERVICE_PLAY_GROUP = "play_group"


def _dang_ky_phat_nhom(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_PLAY_GROUP):
        return

    async def _phat_nhom(call: ServiceCall) -> None:
        loa = hass.data.get(DOMAIN, {}).get(HOA_LOA, {})
        ids = list(dict.fromkeys(call.data["entity_id"]))
        thieu = [e for e in ids if e not in loa]
        if thieu:
            raise ServiceValidationError(f"Không phải loa R1 đang chạy: {', '.join(thieu)}")
        mid = call.data["media_content_id"]
        await loa[ids[0]].async_phat_nhom([loa[e] for e in ids], mid, str(call.data.get("title") or "Home Assistant"))

    hass.services.async_register(DOMAIN, SERVICE_PLAY_GROUP, _phat_nhom, schema=vol.Schema({
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("media_content_id"): cv.string,
        vol.Optional("title"): cv.string,
    }))


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    _dang_ky_phat_nhom(hass)
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
    # Giao diện HA (``computeMediaControls``) chỉ vẽ MỘT nút phát/tạm dừng/dừng khi thực thể hỗ trợ Tạm dừng, nên hộp media không có Stop. Với
    # ``assumed_state`` nó vẽ riêng Phát, Tạm dừng và Dừng (đã đối chiếu mã nguồn frontend, 28/10/2026; chủ máy: «không có nút stop nhỉ»).
    _attr_assumed_state = True
    _attr_supported_features = (MediaPlayerEntityFeature.PLAY_MEDIA
                                | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
                                | MediaPlayerEntityFeature.PAUSE
                                | MediaPlayerEntityFeature.PLAY
                                | MediaPlayerEntityFeature.STOP
                                | MediaPlayerEntityFeature.SEEK
                                | MediaPlayerEntityFeature.VOLUME_SET
                                | MediaPlayerEntityFeature.VOLUME_MUTE
                                | MediaPlayerEntityFeature.VOLUME_STEP
                                # Trang «Phương tiện» của HA chỉ liệt kê loa có BROWSE_MEDIA (hộp «Media sources»); thiếu nó thì không chọn được loa
                                # từ giao diện để phát VOV, thư viện nội bộ, TTS thử (chủ máy 28/10/2026), dù gọi bằng action vẫn phát được.
                                | MediaPlayerEntityFeature.BROWSE_MEDIA)

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
        self._loi_doc = 0                    # số lần hỏi trạng thái hỏng LIÊN TIẾP
        self._muc_truoc_tat: int | None = None   # mức âm lượng trước khi tắt tiếng (để bật lại đúng mức)
        self._uoc = UocViTri()               # vị trí chính xác hơn 1 giây từ RelTime nguyên giây
        self._ghi_luc = 0.0                  # lúc (đồng hồ đơn điệu) ghi trạng thái gần nhất
        self._duong: str | None = None       # "dlna" | "airplay" | None: đường đang giữ trạng thái phát (cổng ở ``_doc``)
        self._ap: PhienAirPlay | None = None  # phiên AirPlay hiện tại (chưa chắc đã bắt đầu phát)
        self._ap_tac: asyncio.Task | None = None
        self._ap_tin: PhienAirPlay | None = None  # NV287: phiên AirPlay SONG SONG chỉ để phát tin (không giữ trạng thái)
        self._ap_tin_tac: asyncio.Task | None = None
        self._tin_dlna_tac: asyncio.Task | None = None   # NV303: tác vụ theo dõi tin DLNA song song (nhạc đang ở AirPlay)
        self._tin_dlna_dang = False          # NV303: tin DLNA song song đang chạy trên renderer: kết quả hỏi renderer KHÔNG phải của nhạc (cổng ``_doc``)
        self._ap_goc = 0.0                   # giây của bài mà phiên AirPlay hiện tại bắt đầu (sau khi tua)
        self._ap_url: str | None = None      # địa chỉ đã giải ra, để tua = phát lại từ vị trí đó

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
        self.async_on_remove(self._huy_airplay)
        loa = self.hass.data.setdefault(DOMAIN, {}).setdefault(HOA_LOA, {})        # để dịch vụ ``play_group`` tìm thực thể theo entity_id
        loa[self.entity_id] = self
        self.async_on_remove(lambda: loa.pop(self.entity_id, None))

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
    def _huy_airplay(self) -> None:
        if self._ap_tac is not None and not self._ap_tac.done():
            self._ap_tac.cancel()
        if self._ap_tin_tac is not None and not self._ap_tin_tac.done():
            self._ap_tin_tac.cancel()
        if self._tin_dlna_tac is not None and not self._tin_dlna_tac.done():
            self._tin_dlna_tac.cancel()

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

    @property
    def is_volume_muted(self) -> bool | None:
        """Tắt tiếng LOA (âm lượng nhạc = 0), khác «Tắt mic»: đúng khi ta đã tắt tiếng hoặc loa/người dùng đưa âm lượng về 0."""
        am = self.coordinator.mic_server.am_luong
        if am is None:
            return None
        return am[0] == 0

    async def async_mute_volume(self, mute: bool) -> None:
        """Tắt/bật tiếng loa bằng đúng đường âm lượng APK đã kiểm (``gui_am_luong``): tắt = nhớ mức hiện tại rồi đặt 0; bật = trả về mức đã nhớ
        (chưa nhớ thì lấy nửa thang) — không dùng lệnh mute riêng của DLNA (chưa kiểm trên loa thật)."""
        am = self.coordinator.mic_server.am_luong
        toi_da = am[1] if am else const.VOL_MAX
        if mute:
            if am is not None and am[0] > 0:
                self._muc_truoc_tat = am[0]
            muc = 0
        else:
            muc = self._muc_truoc_tat or max(1, round(toi_da * 0.5))
            if am is not None and am[0] > 0:
                muc = am[0]                                   # đã có tiếng (người dùng tự chỉnh lên): giữ nguyên
        try:
            await self.coordinator.mic_server.gui_am_luong(muc)
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            raise HomeAssistantError("Loa chưa nối về HA (APK mic): chưa tắt/bật tiếng được") from exc
        if not mute:
            self._muc_truoc_tat = None

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
        # Đang GIỮ nhạc (tin báo / phiên đàm thoại) và renderer về idle: idle này là của tin, nhạc sẽ phát lại. Báo ``paused`` chứ KHÔNG báo ``idle``:
        # bộ phát nhạc nào không đọc ``idle_reason`` (Music Assistant, nhóm loa, danh sách phát tự viết…) thấy playing→idle là «hết bài» rồi nhảy bài
        # kế hoặc kết thúc (lỗi chủ máy/người dùng báo 10/11/2026: «phát TTS xong nhạc không phát tiếp mà next bài/end bài»). ``idle_reason`` vẫn
        # là ``dang_giu`` nên bộ điều khiển đã vá chạy như cũ.
        if self._tt.state == "idle" and self._ly_do == IDLE_DANG_GIU:
            return MediaPlayerState.PAUSED
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
        thay / ``error`` lỗi phát / ``dang_giu`` idle của tin báo trong lúc loa giữ nhạc, nhạc sẽ phát lại). Chỉ có khi idle; tích hợp phát nhạc (YouTube) đọc nó thay vì đoán bằng thời lượng bài."""
        a: dict[str, Any] = {}
        if self._duong and self._tt.state != "idle":
            a["duong_phat"] = self._duong                       # dlna | airplay: đường đang thực sự ra tiếng
        if self._tt.state == "idle" and self._ly_do:
            a["idle_reason"] = self._ly_do
        return a or None

    @property
    def available(self) -> bool:
        # Khác các thực thể khác: DLNA tắt (dlna_open False/None) vẫn phát được vì ta bật nó.
        return CoordinatorEntity.available.fget(self)

    def _dang_giu_nhac(self) -> bool:
        """NV287: loa đang tạm dừng nhạc và SẼ phát lại nó (phiên đàm thoại / tin báo) không? Dùng để phân biệt «hết bài» thật với
        «bị tin chen ngang»: lúc đó renderer về idle là do tin, không phải bài đã hết. Lượt giữ không chụp được gì (không có nhạc) hoặc
        chỉ hạ nhỏ nhạc (nhạc vẫn phát) thì KHÔNG tính — bài hết trong lúc ấy là hết thật."""
        try:
            return bool(self.coordinator.talk.music.se_phat_lai)
        except (AttributeError, TypeError):
            return False

    @callback
    def _ap_dung(self, tt: TrangThaiDmr) -> None:
        cu = self._tt
        if tt.state == "idle":
            if self._dang_giu_nhac() and self._ly_do != "stopped":
                # NV287: đang GIỮ nhạc (tin báo / phiên đàm thoại) mà renderer về idle: idle này là của tin báo, không phải của bài.
                # Khai «dang_giu», KHÔNG khai «finished» (bộ điều khiển danh sách phát đọc finished là sang bài kế — đúng triệu
                # chứng NV287; trước đây _ly_do bị xoá ở nhánh playing bên dưới nên tin dứt lại thành finished) và cũng KHÔNG khai
                # «interrupted» (tritue_youtube_player coi interrupted là bị bài khác đè và GỠ LOA khỏi phiên). Giá trị lạ với bộ
                # điều khiển chưa vá thì nó rơi về đoán bằng thời lượng bài, vị trí đã đóng băng lúc tạm dừng → không nhảy bài.
                # Người dùng bấm Stop («stopped») vẫn được giữ nguyên.
                self._ly_do = IDLE_DANG_GIU
            elif self._ly_do is None and cu.state in ("playing", "buffering"):
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
        """Hỏi trạng thái renderer; không trả lời được thì coi như dừng vì lỗi (ghi một dòng nhật ký).

        CỔNG DUY NHẤT giữa hai đường: AirPlay đang phát thì không hỏi DLNA (kết quả của nó là của lần phát CŨ, ghi vào sẽ đè trạng thái thật);
        NV303: tin DLNA song song đang chạy trên renderer thì cũng không hỏi (trạng thái renderer lúc đó là của TIN, không phải của nhạc);
        ``async_lam_moi``, ``_cham_vong``, ``_cho_trang_thai`` đều đi qua đây nên không chỗ nào phải tự kiểm."""
        if self._duong == "airplay" or self._tin_dlna_dang:
            return None
        try:
            tt = await self._dmr.async_doc()
        except R1DmrError as exc:
            self._loi_doc += 1
            if self._tt.state != "idle" and self._loi_doc >= LOI_DOC_TOI_DA:
                _LOGGER.warning("%s: %s (hỏng %d lần liên tiếp)", self.entity_id, exc, self._loi_doc)
                self._ly_do = "error"
                self._ap_dung(TrangThaiDmr(state="idle", loi=True))
            elif self._tt.state != "idle":
                _LOGGER.debug("%s: hỏi trạng thái hỏng lần %d/%d: %s", self.entity_id, self._loi_doc, LOI_DOC_TOI_DA, exc)
            return None
        self._loi_doc = 0
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
            if tt is None and self._loi_doc and self._tt.state in ("playing", "buffering"):
                continue                                    # lỗi thoáng qua: hỏi lại ở chu kỳ sau, chưa kết luận loa dừng
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

    async def _lenh(self, viec, mong_doi: set[str], toi_da: float = 3.0) -> None:
        try:
            await viec()
        except R1DmrError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await self._cho_trang_thai(mong_doi, toi_da)

    @property
    def _la_airplay(self) -> bool:
        """AirPlay đang giữ loa: đã phát (``_duong``) hoặc phiên đang khởi động (``_ap``, chưa có gói tiếng đầu). Lệnh Dừng bấm đúng lúc khởi động
        mà chỉ nhìn ``_duong`` sẽ đi sang DLNA (không có gì để dừng ở đó) và bỏ sót phiên AirPlay."""
        return self._duong == "airplay" or self._ap is not None

    async def _ap_lenh(self, ten: str) -> None:
        ap = self._ap
        if ap is None:
            return
        try:
            await getattr(ap, ten)()
        except (LoiAirPlay, OSError, TimeoutError, asyncio.IncompleteReadError) as exc:
            raise HomeAssistantError(f"AirPlay: {exc}") from exc

    async def async_media_pause(self) -> None:
        if self._la_airplay:
            await self._ap_lenh("tam_dung")
            return
        await self._lenh(self._dmr.async_tam_dung, {"paused", "idle"})

    async def async_media_play(self) -> None:
        if self._la_airplay:
            await self._ap_lenh("tiep")
            return
        await self._lenh(self._dmr.async_tiep, {"playing", "buffering"})

    async def async_media_stop(self) -> None:
        """Dừng hẳn. Renderer có thể bỏ qua Stop khi đang nạp luồng (TRANSITIONING) nên một lệnh không đủ — người dùng phải bấm Stop 2–3
        lần (chủ máy 28/10/2026): kiểm loa đã idle chưa, chưa thì gửi lại (tối đa ``STOP_GUI_LAI`` lần thêm)."""
        self._ly_do = "stopped"
        await self._dung_tin_song_song()                  # tin song song cũng phải im khi người dùng Stop
        if self._la_airplay:
            await self._dung_airplay()
            self._ghi_idle()
            return
        for lan in range(STOP_GUI_LAI + 1):
            await self._lenh(self._dmr.async_dung, {"idle"}, toi_da=STOP_CHO_XAC_NHAN)
            if self._tt.state == "idle":
                return
            _LOGGER.warning("%s: renderer vẫn %s sau lệnh Stop (lần %d/%d) — gửi lại",
                            self.entity_id, self._tt.state, lan + 1, STOP_GUI_LAI + 1)

    async def async_media_seek(self, position: float) -> None:
        if self._la_airplay:
            if self._ap_url is None:
                raise HomeAssistantError("AirPlay: không biết nguồn đang phát để tua")
            await self._phat_airplay(self._ap_url, self._uri or self._ap_url, self._tieu_de or "Home Assistant", bat_dau=max(0.0, float(position)))
            return
        await self._lenh(lambda: self._dmr.async_tua(position), {"playing", "buffering", "paused"})

    async def async_browse_media(self, media_content_type: MediaType | str | None = None,
                                 media_content_id: str | None = None) -> BrowseMedia:
        """Duyệt nguồn phương tiện của HA (media source: thư viện nội bộ, đài, TTS...) và chỉ lọc ra âm thanh, như ``dlna_dmr``."""
        return await media_source.async_browse_media(
            self.hass, media_content_id, content_filter=lambda item: item.media_content_type.startswith("audio/"))

    async def async_play_media(self, media_type: MediaType | str, media_id: str,
                               **kwargs: Any) -> None:
        """Nhạc: phát thẳng qua renderer. Báo tin (TTS / announce): tạm dừng nhạc trước, phát tin, rồi NỀN theo dõi tin phát
        xong và khôi phục nhạc — lệnh này trả về ngay sau khi đã gửi tin đi, không chờ hết tin (``tts.speak`` khỏi bị treo).
        NV287: nếu bật ``tts_song_song_airplay`` và nhạc đang ở DLNA thì tin đi AirPlay SONG SONG (không thay URI DLNA,
        không tạm dừng: tắt ducking nghĩa là nhạc phát tiếp ở mức đầy đủ, bật ducking thì nhạc nhỏ đi rồi trả mức cũ;
        chỉ khi không đọc được mức cũ mới về tạm dừng); nhạc hết tin vẫn ở đúng bài, đúng vị trí mà không cần khôi phục."""
        if not is_announcement(media_id, kwargs):
            await self._phat(media_type, media_id, **kwargs)
            return
        talk = self.coordinator.talk
        entry = self.coordinator.config_entry
        if tts_song_song_airplay(entry) and self._tin_co_the_song_song():
            # Song song = KHÔNG tạm dừng bao giờ: duck tắt thì nac=0 (nhạc phát tiếp
            # ở mức đầy đủ), duck bật thì hạ nac nấc rồi trả mức cũ. Chỉ khi không
            # đọc được mức cũ, _snapshot_and_duck mới tự về tạm dừng như cũ.
            giu = await talk.music.hold(
                duck=True, nac=ha_nhac_nac(entry) if ha_nhac_xuong(entry) else 0)
            try:
                if await self._bat_dau_tin_song_song(media_type, media_id, **kwargs):
                    self.coordinator.config_entry.async_create_background_task(
                        self.hass, self._theo_doi_tin_song_song(giu), f"{self.entity_id} announce song song")
                    return
                # Không mở được phiên song song: nhả lượt giữ duck rồi giữ lại
                # kiểu tạm dừng thường — nếu giữ nguyên lượt duck thì lúc nhả
                # chỉ trả mức mà không phát lại nhạc (nhạc đã bị tin thay URI).
                _LOGGER.warning("%s: không mở được tin song song qua AirPlay, về đường tin thường", self.entity_id)
                await giu.release()
                giu = await talk.music.hold()
                self._nhanh = True
                await self._phat(media_type, media_id, **kwargs)
            except BaseException:
                self._nhanh = False
                await giu.release()
                raise
            self.coordinator.config_entry.async_create_background_task(
                self.hass, self._theo_doi_tin(giu), f"{self.entity_id} announce")
            return
        if tts_song_song_airplay(entry) and self._tin_co_the_nguoc_dlna() and await self._tin_dlna_song_song(media_type, media_id, **kwargs):
            return                                      # NV303: tin đã đi DLNA song song, nhạc AirPlay không bị đụng
        giu = await talk.music.hold()
        muc_cu = await self._dat_am_luong_tin(kwargs)
        try:
            self._nhanh = True
            await self._phat(media_type, media_id, **kwargs)
        except BaseException:
            self._nhanh = False
            await self._tra_am_luong_tin(muc_cu)
            await giu.release()
            raise
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self._theo_doi_tin(giu, muc_cu), f"{self.entity_id} announce")

    async def _dat_am_luong_tin(self, kwargs: dict[str, Any]) -> int | None:
        """Đặt âm lượng LOA cho tin báo / TTS. Trả mức CŨ để trả lại khi tin xong, hoặc ``None`` nếu không đổi gì. Thứ tự: ``extra.volume``
        (0.0–1.0, mỗi lần gọi) > tuỳ chọn «Âm lượng tin báo» (0–15; 0 = không đổi). Không đọc/đặt được thì để nguyên (tin vẫn phát)."""
        am = self.coordinator.mic_server.am_luong
        if am is None:
            return None
        extra = kwargs.get("extra") if isinstance(kwargs.get("extra"), dict) else {}
        muc = None
        try:
            if extra.get("volume") is not None:
                muc = min(max(round(float(extra["volume"]) * am[1]), 0), am[1])
            elif am_luong_tin(self.coordinator.config_entry) > 0:
                muc = min(am_luong_tin(self.coordinator.config_entry), am[1])
        except (TypeError, ValueError):
            _LOGGER.warning("%s: extra.volume không phải số 0–1, bỏ qua", self.entity_id)
        if muc is None or muc == am[0]:
            return None
        try:
            await self.coordinator.mic_server.gui_am_luong(muc)
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            _LOGGER.warning("%s: không đặt được âm lượng tin báo (%s)", self.entity_id, type(exc).__name__)
            return None
        return am[0]

    async def _tra_am_luong_tin(self, muc_cu: int | None) -> None:
        if muc_cu is None:
            return
        try:
            await self.coordinator.mic_server.gui_am_luong(muc_cu)
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            _LOGGER.warning("%s: không trả được âm lượng cũ %s sau tin báo (%s)", self.entity_id, muc_cu, type(exc).__name__)

    async def _theo_doi_tin(self, giu, muc_cu: int | None = None) -> None:
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
            await self._tra_am_luong_tin(muc_cu)             # trả âm lượng TRƯỚC khi nhạc phát lại
            await giu.release()

    # ── NV287: tin song song qua AirPlay ────────────────────────────────────────
    # Khác đường AirPlay thường ở đúng một điểm: KHÔNG dừng DLNA, KHÔNG đổi
    # ``_duong``/``_uri``/``_ly_do``/trạng thái của thực thể. Nhạc DLNA vì vậy vẫn
    # là «bài đang phát» suốt lúc tin nói; khi tin xong không có gì để khôi phục
    # nên cũng không có cửa cho «hết bài» giả. Chỉ dùng khi nhạc đang ở DLNA;
    # nhạc ở AirPlay, hoặc không có nhạc, thì đường thường rẻ hơn và đúng hơn.

    def _tin_co_the_song_song(self) -> bool:
        """Nhạc đang phát qua DLNA (không phải AirPlay) thì tin mới đi song song được."""
        return self._tt.state in ("playing", "buffering") and not self._la_airplay

    async def _bat_dau_tin_song_song(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> bool:
        """Giải địa chỉ tin rồi mở phiên AirPlay song song; True = tin đã bắt đầu
        phát (phiên chạy nền, bên theo dõi sẽ chờ nó xong). False = không mở được
        (bên gọi về đường tin thường); phiên hỏng đã được dọn sạch."""
        url = media_id
        if media_source.is_media_source_id(media_id):
            url = (await media_source.async_resolve_media(self.hass, media_id, self.entity_id)).url
        url = self._url_cho_loa(url)
        await self._dung_tin_song_song()                    # tin mới thay tin cũ: không bao giờ hai phiên RAOP cùng nói với loa
        data = self.coordinator.data
        vua_bat = data is None or not data.airplay_open
        if vua_bat:
            try:
                await self.coordinator.async_command(
                    lambda: self.coordinator.client.set_airplay_open(True), airplay_open=True)
            except Exception as exc:  # noqa: BLE001 — bật AirPlay hỏng thì về đường thường, không phá tin
                _LOGGER.debug("%s: không bật được AirPlay cho tin song song: %s", self.entity_id, type(exc).__name__)
                return False
        for lan in range(6 if vua_bat else 1):              # loa vừa bật AirPlay: cổng RAOP lên chậm, thử lại như _phat_airplay
            if lan:
                await asyncio.sleep(0.5)
            loi = await self._mo_tin_airplay(url)
            if loi is None:
                return True
            if not isinstance(loi, LoiKhongNoi):
                break
        return False

    async def _mo_tin_airplay(self, url: str) -> LoiAirPlay | None:
        """Mở một phiên AirPlay SONG SONG và chờ gói tiếng đầu. None = đã phát;
        còn lại là lỗi (phiên đã dọn). Không đụng ``_ap``/``_duong``/trạng thái."""
        entry = self.coordinator.config_entry
        ap = PhienAirPlay(self._host, airplay_port(entry), tao_nguon(url, 0.0), tren_doi=None)
        tac = entry.async_create_background_task(self.hass, ap.chay(), f"{self.entity_id} tin airplay")
        self._ap_tin, self._ap_tin_tac = ap, tac
        bd = asyncio.ensure_future(ap.da_bat_dau.wait())
        try:
            xong, _ = await asyncio.wait({tac, bd}, timeout=AIRPLAY_BAT_DAU_TOI_DA, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            tac.cancel()                                    # bị huỷ giữa lúc mở: phiên không có chủ thì không được để nó nói tiếp
            self._ap_tin = self._ap_tin_tac = None
            raise
        finally:
            bd.cancel()
        if ap.da_bat_dau.is_set():
            return None
        self._ap_tin = self._ap_tin_tac = None
        if tac in xong:
            try:
                ket_qua = tac.result()
            except LoiAirPlay as exc:
                return exc
            except Exception as exc:  # noqa: BLE001 — lỗi không ngờ của bộ gửi: báo thành lỗi AirPlay
                return LoiAirPlay(f"lỗi không ngờ: {type(exc).__name__}")
            return ket_qua if isinstance(ket_qua, LoiAirPlay) else LoiAirPlay("phiên AirPlay kết thúc mà chưa phát được")
        tac.cancel()
        await asyncio.wait({tac})
        return LoiAirPlay(f"AirPlay chưa phát được sau {AIRPLAY_BAT_DAU_TOI_DA:.0f} giây")

    async def _theo_doi_tin_song_song(self, giu) -> None:
        """Chờ phiên AirPlay song song xong (hoặc hết hạn), rồi báo vệ tinh, nhả nhạc.
        Không đọc trạng thái renderer: renderer vẫn đang phát nhạc, đọc nó sẽ tưởng
        tin chưa bắt đầu / đã xong sai."""
        talk = self.coordinator.talk
        tac = self._ap_tin_tac
        try:
            if tac is not None:
                xong, _ = await asyncio.wait({tac}, timeout=const.ANNOUNCE_MAX)
                if not xong:
                    _LOGGER.warning("tin song song trên %s chưa xong sau %.0f giây — dừng phiên",
                                    self.entity_id, const.ANNOUNCE_MAX)
                    tac.cancel()
                    await asyncio.wait({tac})
                elif not tac.cancelled() and tac.exception() is not None:   # phiên bị dừng chủ ý (Stop / tin mới) thì không phải lỗi
                    _LOGGER.warning("tin song song trên %s lỗi: %s", self.entity_id, type(tac.exception()).__name__)
        finally:
            if tac is not None and self._ap_tin_tac is tac:                  # đừng xoá phiên của tin mới hơn
                self._ap_tin = self._ap_tin_tac = None
            talk.announce_done()
            await giu.release()

    async def _dung_tin_song_song(self) -> None:
        """Dừng phiên tin song song (nếu có) — dùng khi người dùng Stop hoặc khi
        đường phát chính đổi (không để hai phiên AirPlay cùng nói với loa)."""
        tac = self._ap_tin_tac
        self._ap_tin = self._ap_tin_tac = None
        if tac is not None and not tac.done():
            tac.cancel()
            await asyncio.wait({tac})
        tin_dlna, self._tin_dlna_tac = self._tin_dlna_tac, None            # NV303: tin DLNA song song cũng phải im (tự dừng renderer khi bị huỷ)
        if tin_dlna is not None and not tin_dlna.done():
            tin_dlna.cancel()
            await asyncio.wait({tin_dlna})

    # ── NV303: tin báo đi đường NGƯỢC với nhạc — nhạc AirPlay thì tin DLNA ──────────────────
    # Chủ máy 03/11/2026: «TTS khi dùng AirPlay trước thì TTS qua DLNA, vì AirPlay chạy đồng bộ tốt hơn». Cùng công tắc ``tts_song_song_airplay``:
    # nhạc DLNA ⇒ tin AirPlay (NV287, ở trên); nhạc AirPlay ⇒ tin DLNA (đây). Phiên AirPlay của nhạc KHÔNG bị đụng: không Pause/Flush/Teardown, không
    # đổi ``_ap`` / ``_duong`` / ``_uri`` / ``_ly_do`` / trạng thái thực thể. Tin được theo dõi bằng cách hỏi THẲNG renderer (``_dmr.async_doc``),
    # không qua ``_doc`` — cổng đó cố ý bỏ qua renderer lúc AirPlay giữ nhạc (và lúc tin DLNA đang chạy), nên ``idle_reason`` không bao giờ thấy
    # trạng thái của tin (không ``finished`` → sang bài, không ``interrupted`` → gỡ loa). CHƯA ĐO trên loa thật xem loa có trộn được DLNA + RAOP.

    def _tin_co_the_nguoc_dlna(self) -> bool:
        """Nhạc đang phát qua AirPlay (đã có gói tiếng) thì tin mới đi DLNA song song được."""
        return self._duong == "airplay" and self._ap is not None and self._tt.state in ("playing", "buffering")

    async def _tin_dlna_song_song(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> bool:
        """True = tin đã bắt đầu phát qua DLNA (tác vụ nền theo dõi và nhả nhạc). False = không làm được, đã dọn sạch: bên gọi về đường thường
        (tạm dừng nhạc, phát tin, khôi phục). Hạ nhạc nền (``ha_nhac_xuong``) áp cho chiều này như chiều kia, trả đúng mức cũ kể cả khi tin lỗi."""
        talk = self.coordinator.talk
        entry = self.coordinator.config_entry
        duck = ha_nhac_xuong(entry)
        if duck and self.coordinator.mic_server.am_luong is None:
            _LOGGER.info("%s: muốn hạ nhạc nền nhưng chưa đọc được âm lượng (APK chưa nối): tin về đường thường", self.entity_id)
            return False                                   # hạ mù không an toàn; hold(duck) sẽ phải TẠM DỪNG phiên AirPlay, trái với «không đụng nhạc»
        giu = await talk.music.hold(duck=True, nac=ha_nhac_nac(entry) if duck else 0)
        try:
            if talk.music.se_phat_lai:                      # không hạ được mức nên hold đã tạm dừng nhạc: không còn là «song song»
                await giu.release()
                return False
            if not await self._bat_dau_tin_dlna(media_id):
                await giu.release()
                return False
        except BaseException:
            await giu.release()
            raise
        self._tin_dlna_tac = entry.async_create_background_task(
            self.hass, self._theo_doi_tin_dlna(giu), f"{self.entity_id} announce dlna song song")
        return True

    async def _bat_dau_tin_dlna(self, media_id: str) -> bool:
        """Đưa tin tới renderer DLNA và chờ nó thật sự phát. False = hỏng (renderer chưa lên / từ chối / không phát / báo lỗi); renderer đã được dừng."""
        url = media_id
        if media_source.is_media_source_id(media_id):
            url = (await media_source.async_resolve_media(self.hass, media_id, self.entity_id)).url
        url = self._url_cho_loa(url)
        await self._dung_tin_song_song()                    # tin mới thay tin cũ
        self._tin_dlna_dang = True
        try:
            data = self.coordinator.data
            if data is None or not data.dlna_open:
                await self.coordinator.async_command(lambda: self.coordinator.client.set_dlna_open(True), dlna_open=True)
            await self._dmr.async_san_sang(DLNA_TIN_NGUOC_SAN_SANG)
            await self._dmr.async_phat(url, "Tin báo")
            han = time.monotonic() + const.ANNOUNCE_START_WAIT
            while True:
                tt = await self._dmr.async_doc()
                if tt.state in ("playing", "buffering"):
                    return True
                if tt.loi or time.monotonic() >= han:
                    raise R1DmrError("renderer không phát tin" + (" (báo lỗi)" if tt.loi else f" sau {const.ANNOUNCE_START_WAIT:.0f} giây"))
                await asyncio.sleep(CHAM_TIN_NGUOC / 5)
        except (R1DmrError, HomeAssistantError) as exc:
            _LOGGER.warning("%s: tin song song qua DLNA không được (%s), về đường tin thường", self.entity_id, exc)
        except BaseException:
            await self._tat_tin_dlna()
            raise
        await self._tat_tin_dlna()
        return False

    async def _tat_tin_dlna(self) -> None:
        """Dừng tin trên renderer DLNA và trả cổng ``_doc`` về cho nhạc. Lỗi dừng chỉ ghi nhật ký (renderer có thể đã tắt)."""
        try:
            await self._dmr.async_dung()
        except R1DmrError as exc:
            _LOGGER.debug("%s: dừng tin DLNA lỗi: %s", self.entity_id, exc)
        finally:
            self._tin_dlna_dang = False

    async def _theo_doi_tin_dlna(self, giu) -> None:
        """Chờ tin DLNA xong (hỏi thẳng renderer) hoặc hết hạn, báo vệ tinh, nhả nhạc (trả mức nếu có hạ). Bị huỷ (Stop / tin mới) thì dừng tin."""
        talk = self.coordinator.talk
        loi_lien_tiep = 0
        dung_tin = True
        try:
            async with asyncio.timeout(const.ANNOUNCE_MAX):
                while True:
                    await asyncio.sleep(CHAM_TIN_NGUOC)
                    try:
                        tt = await self._dmr.async_doc()
                    except R1DmrError:
                        loi_lien_tiep += 1
                        if loi_lien_tiep >= LOI_DOC_TOI_DA:
                            _LOGGER.warning("%s: không hỏi được renderer DLNA khi theo dõi tin (%d lần liên tiếp): coi như tin đã xong", self.entity_id, loi_lien_tiep)
                            break
                        continue
                    loi_lien_tiep = 0
                    if tt.state not in ("playing", "buffering"):
                        dung_tin = False                    # renderer tự về idle: tin đã hết, không cần gửi Stop
                        break
        except TimeoutError:
            _LOGGER.warning("tin DLNA song song trên %s chưa xong sau %.0f giây — dừng tin", self.entity_id, const.ANNOUNCE_MAX)
        finally:
            if dung_tin:
                await self._tat_tin_dlna()
            self._tin_dlna_dang = False
            if self._tin_dlna_tac is asyncio.current_task():
                self._tin_dlna_tac = None
            talk.announce_done()
            await giu.release()

    #: Thứ tự thử các đường theo tuỳ chọn ``duong_phat``.
    _THU_TU = {"dlna": ("dlna",), "dlna_truoc": ("dlna", "airplay"), "airplay_truoc": ("airplay", "dlna"), "airplay": ("airplay",)}
    _TEN_DUONG = {"dlna": "DLNA", "airplay": "AirPlay"}

    async def async_phat_nhom(self, nhom_loa: list[R1Player], media_id: str, tieu_de: str) -> None:
        """Phát NHÓM chỉ qua AirPlay (đường đồng bộ): một bộ giải mã, mọi loa neo cùng một mốc (``NguonChung``). Loa nào hỏng thì nhóm vẫn phát,
        nhưng cuối cùng báo lỗi nêu tên loa hỏng (không im lặng)."""
        url = media_id
        if media_source.is_media_source_id(media_id):
            url = (await media_source.async_resolve_media(self.hass, media_id, self.entity_id)).url
        url = self._url_cho_loa(url)
        nhom = NguonChung(url, [p.entity_id for p in nhom_loa])
        nhom.bat_dau()
        kq = await asyncio.gather(*(p._phat_airplay(url, media_id, tieu_de, nhom=nhom) for p in nhom_loa), return_exceptions=True)
        loi = [f"{p.entity_id}: {r}" for p, r in zip(nhom_loa, kq) if isinstance(r, BaseException)]
        for p, r in zip(nhom_loa, kq):
            if isinstance(r, BaseException) and not isinstance(r, HomeAssistantError):
                raise r
        if loi:
            raise HomeAssistantError(("Cả nhóm không phát được: " if len(loi) == len(nhom_loa) else "Một số loa trong nhóm không phát được (các loa còn lại vẫn phát): ")
                                     + "; ".join(loi))

    def _url_cho_loa(self, url: str) -> str:
        """URL mà LOA tải được. Mục của HA (đường dẫn tương đối hoặc địa chỉ HA tuyệt đối) được KÝ rồi gắn địa chỉ gốc là ``ha_url`` đã đặt, không thì
        địa chỉ NỘI BỘ của HA (http). KHÔNG dùng ``get_url(hass)`` mặc định của ``async_process_play_media_url``: nó ưu tiên địa chỉ NGOÀI (https, tên miền,
        Nabu Casa) khi HA bật SSL hoặc theo địa chỉ trình duyệt của người bấm — loa R1 không tải được những địa chỉ đó nên chọn mục trong media browser
        «không phát được» còn tự động hoá thì phát (người dùng báo 10/11/2026). URL ngoài HA (đài, YouTube…) giữ nguyên."""
        p = yarl.URL(url)
        if p.scheme and p.scheme not in ("http", "https"):
            return url
        if p.is_absolute():
            if not is_hass_url(self.hass, url):
                return url
            tuong_doi = p.raw_path_qs
        elif url.startswith("/"):
            tuong_doi = url
        else:
            return url
        da_ky = async_process_play_media_url(self.hass, tuong_doi, allow_relative_url=True)
        goc = ha_url(self.coordinator.config_entry)
        if not goc:
            try:
                goc = get_url(self.hass, allow_external=False, allow_cloud=False, prefer_external=False, allow_ip=True)   # allow_ip: HA bật SSL thì mặc định KHÔNG cấp địa chỉ IP
            except NoURLAvailableError as exc:
                raise HomeAssistantError(
                    "Chưa biết địa chỉ NỘI BỘ của HA để loa tải nhạc: đặt «Địa chỉ HA mà loa nối tới» trong tuỳ chọn tích hợp R1 "
                    "(hoặc Cài đặt → Hệ thống → Mạng → URL nội bộ).") from exc
        return goc.rstrip("/") + da_ky

    async def _phat(self, media_type: MediaType | str, media_id: str, **kwargs: Any) -> None:
        """Giải địa chỉ rồi thử lần lượt các đường theo ``duong_phat``. Đường hỏng được DỪNG trước khi thử đường kế (loa không phát hai nơi)."""
        url = media_id
        if media_source.is_media_source_id(media_id):
            url = (await media_source.async_resolve_media(self.hass, media_id, self.entity_id)).url
        url = self._url_cho_loa(url)
        tieu_de = str((kwargs.get("extra") or {}).get("title") or "Home Assistant")
        thu_tu = self._THU_TU[duong_phat(self.coordinator.config_entry)]
        loi: list[str] = []
        for duong in thu_tu:
            try:
                if duong == "dlna":
                    await self._phat_dlna(url, media_id, tieu_de)
                else:
                    await self._phat_airplay(url, media_id, tieu_de)
                return
            except HomeAssistantError as exc:
                if len(thu_tu) == 1:
                    raise
                loi.append(f"{self._TEN_DUONG[duong]}: {exc}")
                _LOGGER.warning("%s: phát qua %s hỏng (%s)%s", self.entity_id, self._TEN_DUONG[duong], exc,
                                "" if duong == thu_tu[-1] else " — thử đường còn lại")
                await self._don_duong(duong)
        raise HomeAssistantError("Cả hai đường phát đều hỏng — " + "; ".join(loi))

    async def _phat_dlna(self, url: str, media_id: str, tieu_de: str) -> None:
        await self._dung_airplay()                          # bài mới thay phiên AirPlay cũ (nếu có)
        self._duong = "dlna"
        data = self.coordinator.data
        if data is None or not data.dlna_open:
            await self.coordinator.async_command(
                lambda: self.coordinator.client.set_dlna_open(True), dlna_open=True)
        try:
            await self._dmr.async_san_sang(DLNA_READY_TIMEOUT)
        except R1DmrError as exc:
            raise HomeAssistantError(str(exc)) from exc
        self._ly_do, self._uri, self._tieu_de = "interrupted", media_id, tieu_de
        self._tt = replace(self._tt, loi=False)             # cờ lỗi của lần phát trước không được tính cho lần này
        try:
            await self._dmr.async_phat(url, tieu_de)
        except R1DmrError as exc:
            self._ly_do = "error"
            raise HomeAssistantError(str(exc)) from exc
        await self._cho_trang_thai({"playing", "buffering"})
        if self._tt.state == "idle" and self._tt.loi:       # tín hiệu chắc chắn duy nhất ngoài lỗi SOAP; idle thường (chậm) KHÔNG tính
            self._ly_do = "error"
            raise HomeAssistantError("renderer của loa báo lỗi khi phát (ERROR_OCCURRED)")

    # ── AirPlay ───────────────────────────────────────────────────────────────

    async def _phat_airplay(self, url: str, media_id: str, tieu_de: str, bat_dau: float = 0.0, nhom: NguonChung | None = None) -> None:
        await self._dung_airplay()
        if self._duong == "dlna" or self._tt.state in ("playing", "buffering", "paused"):
            await self._don_duong("dlna")                   # DLNA còn phát thì dừng trước: không để hai nơi cùng ra tiếng
        data = self.coordinator.data
        vua_bat = data is None or not data.airplay_open
        if vua_bat:
            await self.coordinator.async_command(
                lambda: self.coordinator.client.set_airplay_open(True), airplay_open=True)
        self._ly_do, self._uri, self._tieu_de = "interrupted", media_id, tieu_de
        loi: LoiAirPlay | None = None
        for lan in range(6 if vua_bat else 1):              # loa vừa bật AirPlay: cổng RAOP lên chậm, thử lại tới ~2,5 giây
            if lan:
                await asyncio.sleep(0.5)
            loi = await self._mo_airplay(url, bat_dau, nhom)
            if loi is None:
                return
            if not isinstance(loi, LoiKhongNoi):
                break
        self._ly_do = "error"
        if nhom is not None:
            nhom.bo(self.entity_id)                         # loa hỏng không giữ cả nhóm chờ
        raise HomeAssistantError(str(loi))

    async def _mo_airplay(self, url: str, bat_dau: float, nhom: NguonChung | None = None) -> LoiAirPlay | None:
        """Mở một phiên và chờ gói tiếng đầu. Trả ``None`` nếu đã phát; còn lại trả lỗi (phiên đã được dọn)."""
        entry = self.coordinator.config_entry
        ap = PhienAirPlay(self._host, airplay_port(entry),
                          tao_nguon(url, bat_dau) if nhom is None else nhom.nguon(self.entity_id),
                          tren_doi=lambda tt: self._ap_doi(ap, tt), he_so=lambda: am_luong_media(entry),   # NHẠC: có âm lượng media; tin báo thì không
                          cho_dong_bo=None if nhom is None else (lambda: nhom.san_sang(self.entity_id)))
        tac = entry.async_create_background_task(self.hass, self._chay_ap(ap), f"{self.entity_id} airplay")
        self._ap, self._ap_tac, self._ap_goc, self._ap_url = ap, tac, bat_dau, url
        bd = asyncio.ensure_future(ap.da_bat_dau.wait())
        try:
            xong, _ = await asyncio.wait({tac, bd}, timeout=AIRPLAY_BAT_DAU_TOI_DA, return_when=asyncio.FIRST_COMPLETED)
        finally:
            bd.cancel()
        if ap.da_bat_dau.is_set():
            return None
        self._ap = self._ap_tac = None
        if tac in xong:
            return tac.result() or LoiAirPlay("phiên AirPlay kết thúc mà chưa phát được")
        tac.cancel()
        await asyncio.wait({tac})
        return LoiAirPlay(f"AirPlay chưa phát được sau {AIRPLAY_BAT_DAU_TOI_DA:.0f} giây")

    async def _chay_ap(self, ap: PhienAirPlay) -> LoiAirPlay | None:
        """Chạy phiên tới hết. Trả lỗi nếu hỏng (bên mở phiên đọc kết quả khi chưa bắt đầu phát). Bị huỷ thì KHÔNG đụng trạng thái: bên huỷ lo."""
        loi: LoiAirPlay | None = None
        try:
            await ap.chay()
        except LoiAirPlay as exc:
            loi = exc
        except Exception as exc:  # noqa: BLE001 — lỗi không ngờ của bộ gửi: ghi đủ vết, báo thành lỗi AirPlay
            _LOGGER.exception("%s: bộ gửi AirPlay lỗi không ngờ", self.entity_id)
            loi = LoiAirPlay(f"lỗi không ngờ: {type(exc).__name__}")
        if self._ap is not ap or not ap.da_bat_dau.is_set():
            return loi
        self._ap = self._ap_tac = None                      # đã phát rồi mới hết/hỏng: tự kết thúc
        if loi is not None:
            _LOGGER.warning("%s: AirPlay dừng giữa chừng: %s", self.entity_id, loi)
        # NV287: phiên AirPlay này là tin báo trong lúc giữ nhạc thì hết cũng là
        # «dang_giu», không phải «finished» (xem _ap_dung).
        self._ly_do = "error" if loi is not None else (IDLE_DANG_GIU if self._dang_giu_nhac() else "finished")
        self._ghi_idle()
        return loi

    @callback
    def _ap_doi(self, ap: PhienAirPlay, tt: str) -> None:
        if self._ap is not ap:
            return
        if tt == "phat":
            self._ghi_ap("playing")
        elif tt == "tam_dung":
            self._ghi_ap("paused")

    def _dung_cham(self) -> None:
        cham, self._cham = self._cham, None
        if cham is not None and cham is not asyncio.current_task():
            cham.cancel()

    def _ghi_ap(self, state: str) -> None:
        ap = self._ap
        self._duong = "airplay"
        self._ly_do = None
        self._uoc.reset()
        self._tt = TrangThaiDmr(state=state, position=self._ap_goc + (ap.vi_tri if ap else 0.0), duration=None, uri=self._ap_url)
        self._tt_utc, self._ghi_luc = dt_util.utcnow(), time.monotonic()
        self._dung_cham()
        self.async_write_ha_state()

    def _ghi_idle(self) -> None:
        self._duong = None
        self._tt = TrangThaiDmr(state="idle")
        self._tt_utc, self._ghi_luc = dt_util.utcnow(), time.monotonic()
        self.async_write_ha_state()

    async def _dung_airplay(self) -> None:
        """Dừng phiên AirPlay đang có (nếu có) mà KHÔNG ghi trạng thái: bên gọi quyết định trạng thái kế tiếp.
        Kể cả phiên tin song song: hai phiên RAOP không được cùng nói với loa."""
        tac = self._ap_tac
        self._ap = self._ap_tac = None
        if tac is not None and not tac.done():
            tac.cancel()
            await asyncio.wait({tac})
        await self._dung_tin_song_song()

    async def _don_duong(self, duong: str) -> None:
        """Dừng một đường vừa hỏng (hoặc sắp bị thay) để loa không phát hai nơi."""
        if duong == "airplay":
            await self._dung_airplay()
            return
        # ``R1Dmr`` bỏ thiết bị đã nhớ sau MỌI lỗi (``da_noi`` thành False) trong khi bài trước có thể còn đang phát: nên dừng cả khi trạng thái
        # đã biết cho thấy loa có thể đang phát. Loa idle và chưa nối thì không có gì để dừng (khỏi tốn một lượt dò SSDP).
        if self._dmr.da_noi or self._tt.state in ("playing", "buffering", "paused"):
            try:
                await self._dmr.async_dung()
            except R1DmrError as exc:
                _LOGGER.debug("%s: không dừng được DLNA trước khi đổi đường: %s", self.entity_id, exc)

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
