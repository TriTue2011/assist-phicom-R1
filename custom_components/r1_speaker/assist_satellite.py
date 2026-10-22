"""``assist_satellite.r1``: loa R1 thành vệ tinh Assist gốc của HA.

Luồng nghe: dịch vụ mic trên loa (CHƯA có) → TCP PCM16 mono 16 kHz → ``R1Mic`` (khuếch đại) →
hàng đợi → ``async_accept_pipeline_from_satellite`` bắt đầu từ bước từ gọi; từ gọi do pipeline
của HA quyết (openWakeWord… cấu hình ở HA), vệ tinh không tự bắt.

Trả lời: TTS của pipeline phát qua ``media_player.r1_loa`` (``media_player.play_media``, giống
``tts.speak``); lúc đó bỏ tiếng mic để loa khỏi tự nghe mình. Hội thoại nối tiếp khi bước hiểu
lệnh báo ``continue_conversation``: lượt sau nghe thẳng, không cần từ gọi.

Phiên (``dam_thoai.R1Talk``): nút đàm thoại / trigger từ loa gọi ``begin_session`` → lượt kế
tiếp bắt đầu thẳng từ bước STT (bỏ bước từ gọi), nhạc tạm dừng suốt phiên; lượt xong mà không có
``continue_conversation`` thì phiên đóng, nhạc phát lại. Chế độ từ đánh thức trên loa
(``wake_mode = speaker``): KHÔNG có lượt nào chạy khi chưa có phiên — loa chưa gửi byte nào.
Khuôn: ``dahua_talk/assist_satellite.py`` (cùng cách làm hàng đợi, vòng nghe, sự kiện pipeline).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from homeassistant.components import tts
from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType, PipelineStage
from homeassistant.components.assist_satellite import (
    AssistSatelliteAnnouncement,
    AssistSatelliteConfiguration,
    AssistSatelliteEntity,
    AssistSatelliteEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import den
from .const import DOMAIN, MIC_QUEUE_CHUNKS
from .coordinator import R1ConfigEntry
from .entity import R1MicEntity, preregister
from .media_player import dlna_entity_id
from .settings import speaker_host

_LOGGER = logging.getLogger(__name__)

#: Khi vòng nghe chưa sẵn sàng (mic tắt / unavailable) kiểm tra lại sau ngần này giây.
RECHECK = 1.0
#: Sau ``play_media``, chờ dlna_dmr bắt đầu phát tối đa ngần này giây (không thấy → coi như
#: xong ngay) rồi chờ phát xong tối đa ``PLAY_MAX`` giây.
PLAY_START_WAIT = 3.0
PLAY_MAX = 120.0
POLL = 0.2
#: Hết tiếng loa còn vang: giữ bỏ mic thêm ngần này giây.
TAIL = 0.5
_PLAYING = {"playing", "buffering"}


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    preregister(hass, entry, "assist_satellite", f"{entry.entry_id}_satellite", "r1")
    async_add_entities([R1Satellite(entry)])


class R1Satellite(R1MicEntity, AssistSatelliteEntity):
    _attr_name = None
    _attr_supported_features = (AssistSatelliteEntityFeature.ANNOUNCE
                                | AssistSatelliteEntityFeature.START_CONVERSATION)

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "satellite")
        self._hang: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MIC_QUEUE_CHUNKS + 1)
        self._dang_noi = False       # đang phát ra loa: bỏ tiếng mic
        self._tts_xong = asyncio.Event()
        self._co_tts = False
        self._tiep = False           # lượt sau nghe thẳng, không cần từ gọi
        self._vong: asyncio.Task | None = None
        self._cut = 0                        # đếm số lần cắt lượt (xem _cat_luot)
        self._co_phien = asyncio.Event()     # có phiên chờ chạy (chế độ từ đánh thức trên loa)
        self._phien_luot = None              # phiên mà lượt pipeline đang chạy thuộc về
        self._cut_luot = 0                   # giá trị ``_cut`` lúc lượt hiện tại bắt đầu (đèn «lỗi»)

    @property
    def talk(self):
        return self._entry.runtime_data.talk

    # ── Giao diện cho R1Talk (SessionDriver) ──────────────────────────────────

    @callback
    def begin_session(self) -> None:
        """Phiên vừa mở: lượt kế tiếp nghe thẳng (bỏ bước từ gọi), cắt lượt từ gọi đang chạy."""
        self._tiep = True
        self._cat_luot()
        self._co_phien.set()

    @callback
    def cut_turn(self) -> None:
        """Phiên bị đóng giữa chừng (hết giờ, mic tắt…): kết thúc lượt đang chạy."""
        self._tiep = False
        self._cat_luot()

    # ── Cấu hình HA đòi ───────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self.mic.available

    @property
    def pipeline_entity_id(self) -> str | None:
        return er.async_get(self.hass).async_get_entity_id(
            "select", DOMAIN, f"{self._entry.entry_id}-pipeline")

    @callback
    def async_get_configuration(self) -> AssistSatelliteConfiguration:
        # Từ gọi do pipeline quyết (bắt ở HA), vệ tinh không tự bắt.
        raise NotImplementedError

    async def async_set_configuration(self, config: AssistSatelliteConfiguration) -> None:
        raise NotImplementedError

    # ── Vòng đời ──────────────────────────────────────────────────────────────

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.mic.add_chunk_listener(self._khi_co_tieng))
        self.async_on_remove(self.mic.add_state_listener(self._khi_doi_trang_thai))
        self.talk.driver = self
        self._vong = self._entry.async_create_background_task(
            self.hass, self._chay(), f"{self.entity_id} listen")

    async def async_will_remove_from_hass(self) -> None:
        if self.talk.driver is self:
            self.talk.driver = None
        if self._vong is not None:
            self._vong.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._vong
        await super().async_will_remove_from_hass()

    @callback
    def _khi_doi_trang_thai(self) -> None:
        if not self.mic.available or self.mic.muted or not self.mic.assist_on:
            # luồng đứt/tắt/Assist tắt: phiên đóng (nhạc phát lại), lượt đang chạy phải kết thúc
            self.talk.end(self.talk.session, "mic_tat_hoac_dut", cut=False)
            self._tiep = False
            self._cat_luot()
        self.async_write_ha_state()

    @callback
    def _khi_co_tieng(self, khuc: bytes) -> None:
        if self._dang_noi:
            return
        if self.talk.session_kind == "song_cong":
            return        # đàm thoại đang bật: Assist tạm nghỉ chờ từ đánh thức, mic dành cho cuộc gọi
        if self._hang.full():
            self._hang.get_nowait()   # tụt hậu thì bỏ khúc cũ nhất
        self._hang.put_nowait(khuc)

    @callback
    def _cat_luot(self) -> None:
        """Kết thúc luồng tiếng của lượt đang chạy để vòng nghe mở lượt mới. Đếm lần cắt để một
        lượt vừa tạo mà chưa kịp chạy (``_luong_stt`` xả hàng đợi lúc bắt đầu) vẫn bị cắt — nếu
        không, tiếng mic cứ chảy vào pipeline sau khi phiên đã đóng."""
        self._cut += 1
        while not self._hang.empty():
            self._hang.get_nowait()
        self._hang.put_nowait(None)

    # ── Tai ───────────────────────────────────────────────────────────────────

    async def _chay(self) -> None:
        while True:
            if not self.mic.available or self.mic.muted or not self.mic.assist_on:
                await asyncio.sleep(RECHECK)
                continue
            if self.talk.wake_on_speaker and not self._tiep and self.talk.session is None:
                # Từ đánh thức chạy trên loa: không có phiên thì không có lượt, không có byte.
                self._co_phien.clear()
                await self._co_phien.wait()
                continue
            bat_dau = PipelineStage.STT if self._tiep else PipelineStage.WAKE_WORD
            self._tiep = False
            self._co_tts = False
            self._tts_xong.clear()
            self._phien_luot = self.talk.session
            self._cut_luot = self._cut
            try:
                await self.async_accept_pipeline_from_satellite(
                    audio_stream=self._luong_stt(), start_stage=bat_dau)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — một lượt hỏng không được làm điếc vệ tinh
                _LOGGER.exception("%s: pipeline failed", self.entity_id)
                self.talk.end(self._phien_luot, "loi_pipeline", cut=False)
                await asyncio.sleep(2)
                continue
            if self._co_tts:
                await self._tts_xong.wait()
            self.talk.turn_finished(self._phien_luot, self._tiep)
            self._phien_luot = None

    def _luong_stt(self):
        """Tiếng mic cho MỘT lượt pipeline. Ghi nhớ số lần cắt NGAY lúc tạo (không đợi lần lặp
        đầu) để mọi cú cắt sau thời điểm này đều kết thúc lượt."""
        return self._luong(self._cut)

    async def _luong(self, mine: int):
        while not self._hang.empty():     # bỏ tiếng tồn từ lượt trước
            self._hang.get_nowait()
        while self._cut == mine:
            khuc = await self._hang.get()
            if khuc is None or self._cut != mine:
                return
            yield khuc

    # ── Miệng ─────────────────────────────────────────────────────────────────

    def on_pipeline_event(self, event: PipelineEvent) -> None:
        if event.type is PipelineEventType.STT_START and self._phien_luot is None:
            # Từ gọi do pipeline HA dò vừa khớp (chế độ ``ha``): coi như mở phiên → giữ nhạc.
            self._phien_luot = self.talk.adopt("wake_ha")
        elif event.type is PipelineEventType.INTENT_END:
            ra = (event.data or {}).get("intent_output") or {}
            self._tiep = bool(ra.get("continue_conversation"))
        elif event.type is PipelineEventType.TTS_END:
            ra = (event.data or {}).get("tts_output") or {}
            luong = tts.async_get_stream(self.hass, ra["token"]) if ra.get("token") else None
            if luong is None:
                self._tts_xong.set()
                return
            self._co_tts = True
            self._entry.async_create_background_task(
                self.hass, self._phat(luong.media_source_id, tts_pipeline=True),
                f"{self.entity_id} tts")
        elif event.type is PipelineEventType.ERROR:
            _LOGGER.debug("%s: pipeline error %s", self.entity_id, event.data)
            # Đèn «lỗi» (den.py), trừ khi lượt do CHÍNH ta cắt (bấm kết thúc, hết phiên…) hoặc lỗi
            # chỉ là «không nghe thấy gì» (HA cũng báo ERROR cho việc đó).
            if self._cut == self._cut_luot and den.la_loi_that((event.data or {}).get("code")):
                self._entry.runtime_data.lights.bao_loi()
            self._tts_xong.set()

    def _loa_entity_id(self) -> str | None:
        return er.async_get(self.hass).async_get_entity_id(
            "media_player", DOMAIN, f"{self._entry.entry_id}_speaker")

    async def _phat(self, media_id: str, *, tts_pipeline: bool = False) -> None:
        """Phát qua ``media_player.r1_loa`` rồi chờ phát xong. Lỗi chỉ ghi log."""
        self._dang_noi = True
        seq0 = self.talk.announce_seq
        try:
            loa = self._loa_entity_id()
            if loa is None:
                raise HomeAssistantError("media_player của loa R1 chưa có")
            await self.hass.services.async_call(
                "media_player", "play_media",
                {"entity_id": loa, "media_content_type": "music",
                 "media_content_id": media_id, "announce": True}, blocking=True)
            await self._cho_phat_xong(seq0)
        except (HomeAssistantError, OSError, TimeoutError) as exc:
            _LOGGER.warning("%s: cannot play reply: %s", self.entity_id, exc)
        finally:
            await asyncio.sleep(TAIL)
            self._dang_noi = False
            if tts_pipeline:
                self.tts_response_finished()
                self._tts_xong.set()

    async def _cho_phat_xong(self, seq0: int | None = None) -> None:
        """Chờ thực thể dlna_dmr của loa đi từ phát → không phát. Không có/không thấy phát
        trong ``PLAY_START_WAIT`` giây thì coi như đã xong."""
        dmr = dlna_entity_id(self.hass, speaker_host(self._entry))
        if dmr is None:
            return
        # Tin do ``R1Player`` phát đã có bên theo dõi riêng (và sẽ phát lại nhạc ngay khi tin
        # xong): kết thúc theo tín hiệu đó, đừng nhầm nhạc vừa phát lại với tin chưa xong.
        if seq0 is None:
            seq0 = self.talk.announce_seq

        def dang_phat() -> bool:
            st = self.hass.states.get(dmr)
            return st is not None and st.state in _PLAYING

        async with asyncio.timeout(PLAY_START_WAIT + PLAY_MAX):
            for _ in range(int(PLAY_START_WAIT / POLL) + 1):
                if dang_phat() or self.talk.announce_seq != seq0:
                    break
                await asyncio.sleep(POLL)
            else:
                return
            while dang_phat() and self.talk.announce_seq == seq0:
                await asyncio.sleep(POLL)

    async def async_announce(self, announcement: AssistSatelliteAnnouncement) -> None:
        await self._phat(announcement.media_id)

    async def async_start_conversation(self, start_announcement: AssistSatelliteAnnouncement
                                       ) -> None:
        """Nói trước rồi nghe câu trả lời ngay (không cần từ gọi)."""
        await self.async_announce(start_announcement)
        if self.talk.session is not None:
            self.begin_session()            # đang trong phiên: nghe tiếp ngay
        else:
            await self.talk.async_start("assist")
