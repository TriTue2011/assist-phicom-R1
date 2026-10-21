"""Phiên đàm thoại của loa R1: MỘT phiên một lúc, giữ nhạc, trạng thái mic, trigger từ loa.

Thiết kế theo R1 (không chép camera): loa không có go2rtc, không có kênh nói riêng; tiếng
vào/ra đi qua hai giao diện trừu tượng ``audio_port.PcmSource`` / ``PcmSink`` (đường phần
cứng thật CHƯA có), HA làm máy chủ Assist (pipeline chọn ở ``select.r1_tro_ly``).

* **Phiên**: nút đàm thoại, trigger từ đánh thức của loa, câu thoại mở bằng từ gọi của HA, và
  bộ đàm đều xin CÙNG một chỗ. Phiên thứ hai khi phiên một chưa đóng bị TỪ CHỐI ngay bằng
  ``R1SessionBusy`` (thông báo nêu rõ nguồn và tuổi phiên đang mở) + sự kiện
  ``r1_speaker_session_refused`` — không xếp hàng, không treo. Mỗi phiên có đồng hồ canh:
  quá ``SESSION_MAX_S`` hoặc mic không nối được sau ``SESSION_MIC_WAIT_S`` thì tự đóng.
* **Nhạc**: mở phiên → ``MusicKeeper.hold()`` (tạm dừng); đóng phiên → nhả (phát lại).
* **Trạng thái mic** (``mic_status``): ``tat`` / ``nghe`` / ``gui`` — xem ``const.MIC_*``.
  ``gui`` chỉ khi byte mic THẬT đang về HA; ``nghe`` chỉ ở chế độ từ đánh thức trên loa, khi
  loa đã báo còn sống gần đây (chưa có phía loa → không bao giờ ``nghe``, không nói dối).
* **Từ đánh thức trên loa** (``wake_mode = speaker``): HA chỉ nhận luồng sau trigger.
  PHÍA LOA CHƯA CÓ: ``trigger()`` / ``alive()`` là điểm đấu nối cho đường POST của loa.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from . import const
from .audio_port import PcmSource
from .giu_nhac import Hold, MusicKeeper

_LOGGER = logging.getLogger(__name__)


class R1SessionBusy(HomeAssistantError):
    """Đang có một phiên khác — phiên mới bị từ chối."""


class SessionDriver(Protocol):
    """Bên chạy pipeline Assist (``assist_satellite.R1Satellite``)."""

    def begin_session(self) -> None: ...
    def cut_turn(self) -> None: ...


@dataclass
class Session:
    kind: str                                   # button | wake | wake_ha | assist | bo_dam
    started: float = field(default_factory=time.monotonic)
    music: Hold | None = None
    release_mic: Callable[[], None] | None = None
    setup: asyncio.Task | None = None
    watchdog: asyncio.Task | None = None
    ended: str | None = None


class R1Talk:
    def __init__(self, hass: HomeAssistant, mic: PcmSource, music: MusicKeeper,
                 wake_mode: str = const.DEFAULT_WAKE_MODE) -> None:
        self.hass, self.mic, self.music, self.wake_mode = hass, mic, music, wake_mode
        self.driver: SessionDriver | None = None
        self.session: Session | None = None
        self.refused = 0
        self.last_refusal: str | None = None
        self.last_end: str | None = None
        self.last_wake: datetime | None = None
        self.last_wake_word: str | None = None
        self.last_alive: datetime | None = None
        self.wake_pulse = False
        self._timers: dict[str, Callable[[], None]] = {}
        self._pending: set[asyncio.Task] = set()
        self._on_change: list[Callable[[], None]] = []
        #: Hộp theo dõi «đã có TTS nào xong chưa» (vệ tinh dùng để khỏi chờ nhầm nhạc vừa phát lại).
        self.announce_seq = 0
        self._unsub = [mic.add_link_listener(self._notify), mic.add_state_listener(self._notify)]

    # ── Trạng thái ────────────────────────────────────────────────────────────

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._on_change.append(cb)
        return lambda: self._on_change.remove(cb)

    @callback
    def _notify(self) -> None:
        for cb in list(self._on_change):
            try:
                cb()
            except Exception:  # noqa: BLE001 — thực thể hỏng không được phá phiên
                _LOGGER.exception("R1 talk: listener failed")

    @property
    def wake_on_speaker(self) -> bool:
        return self.wake_mode == const.WAKE_SPEAKER

    @property
    def speaker_alive(self) -> bool:
        """Loa đã báo còn sống (trigger / nhịp tim) trong ``WAKE_ALIVE_S`` giây gần đây."""
        if self.last_alive is None:
            return False
        return (dt_util.utcnow() - self.last_alive).total_seconds() <= const.WAKE_ALIVE_S

    @property
    def mic_status(self) -> str:
        m = self.mic
        if not m.configured or m.muted:
            return const.MIC_TAT
        if m.connected:
            return const.MIC_GUI
        if self.wake_on_speaker:
            return const.MIC_NGHE if self.speaker_alive else const.MIC_TAT
        # Đầu nhận NV244 đang mở cổng chờ loa nối vào = «nghe» (chưa có byte nào về HA).
        return const.MIC_NGHE if getattr(m, "listening", False) else const.MIC_TAT

    @property
    def session_kind(self) -> str | None:
        return self.session.kind if self.session else None

    # ── Mở / đóng phiên ───────────────────────────────────────────────────────

    def _refuse(self, kind: str) -> R1SessionBusy:
        cur = self.session
        assert cur is not None
        tuoi = time.monotonic() - cur.started
        msg = (f"Loa R1 đang có phiên đàm thoại (nguồn: {cur.kind}, đã mở {tuoi:.0f} giây): "
               f"phiên «{kind}» bị từ chối. Chờ phiên đó kết thúc (tối đa "
               f"{const.SESSION_MAX_S:.0f} giây) hoặc tắt mic để đóng ngay.")
        self.refused += 1
        self.last_refusal = msg
        _LOGGER.warning(msg)
        self.hass.bus.async_fire(const.EVENT_SESSION_REFUSED, {
            "ban": cur.kind, "bi_tu_choi": kind, "tuoi_giay": round(tuoi, 1)})
        self._notify()
        return R1SessionBusy(msg)

    def _check_mic(self) -> None:
        m = self.mic
        if not m.configured:
            raise HomeAssistantError(
                "Chưa cấu hình mic của loa (mic_host trong tuỳ chọn): chưa mở được phiên.")
        if m.muted:
            raise HomeAssistantError("Mic đang tắt (switch.r1_tat_mic): bật mic rồi thử lại.")
        if not m.available:
            raise HomeAssistantError("Luồng mic của loa chưa nối được: chưa mở được phiên.")

    def _open(self, kind: str) -> Session:
        """Phần ĐỒNG BỘ của mở phiên: chiếm chỗ ngay (trước mọi await) nên hai lời xin gần
        nhau không thể cùng thắng."""
        if self.session is not None:
            raise self._refuse(kind)
        self._check_mic()
        s = self.session = Session(kind)
        s.release_mic = self.mic.want()
        s.watchdog = self.hass.async_create_background_task(
            self._canh(s), "r1_speaker session watchdog")
        self._notify()
        return s

    async def _setup(self, s: Session) -> None:
        s.music = await self.music.hold()

    async def async_start(self, kind: str) -> Session:
        """Mở phiên và bắt đầu nghe ngay (bỏ qua bước từ gọi). Từ chối → ``R1SessionBusy``."""
        s = self._open(kind)
        s.setup = self.hass.async_create_task(self._setup(s))
        try:
            await s.setup
            if self.driver is None:
                raise HomeAssistantError("Vệ tinh Assist của loa chưa sẵn sàng.")
            self.driver.begin_session()
        except BaseException:
            self.end(s, "loi", cut=False)
            raise
        return s

    @callback
    def adopt(self, kind: str) -> Session | None:
        """Từ gọi do pipeline HA dò vừa khớp (chế độ ``ha``): coi như mở phiên để giữ nhạc.
        Có phiên rồi thì trả None. Không raise."""
        if self.session is not None:
            return None
        try:
            s = self._open(kind)
        except HomeAssistantError as exc:
            _LOGGER.debug("không nhận phiên %s: %s", kind, exc)
            return None
        s.setup = self.hass.async_create_task(self._setup(s))
        return s

    @callback
    def claim(self, kind: str) -> Callable[[], None]:
        """Chiếm chỗ phiên mà KHÔNG nghe, KHÔNG giữ nhạc (bộ đàm). Hàm trả về nhả chỗ."""
        if self.session is not None:
            raise self._refuse(kind)
        s = self.session = Session(kind)
        self._notify()
        return lambda: self.end(s, "xong", cut=False)

    @callback
    def end(self, s: Session | None, reason: str, *, cut: bool = True) -> asyncio.Task | None:
        """Đóng phiên ``s`` (bỏ qua nếu đã đóng / không còn là phiên hiện tại). Phần chậm
        (phát lại nhạc) chạy NỀN; trả về tác vụ đó để ai cần thì chờ."""
        if s is None or s is not self.session:
            return None
        self.session = None
        s.ended = self.last_end = reason
        if s.watchdog is not None and s.watchdog is not asyncio.current_task():
            s.watchdog.cancel()
        if s.release_mic is not None:
            s.release_mic()
        if cut and self.driver is not None:
            self.driver.cut_turn()
        self._notify()
        if s.music is None and s.setup is None:
            return None
        task = self.hass.async_create_background_task(
            self._nha_nhac(s), "r1_speaker session release")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def _nha_nhac(self, s: Session) -> None:
        if s.setup is not None:
            try:
                await s.setup
            except BaseException:  # noqa: BLE001 — chụp nhạc hỏng thì không có gì để nhả
                return
        if s.music is not None:
            await s.music.release()

    async def async_settle(self) -> None:
        """Chờ mọi việc nhả nhạc đang chạy nền (test, tắt tích hợp)."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    async def _canh(self, s: Session) -> None:
        """Đồng hồ canh: mic không nối được / phiên quá dài thì đóng, không treo."""
        try:
            await asyncio.sleep(const.SESSION_MIC_WAIT_S)
            if self.session is s and not self.mic.connected:
                _LOGGER.warning("phiên %s: luồng mic không nối được sau %.0f giây — đóng phiên",
                                s.kind, const.SESSION_MIC_WAIT_S)
                self.end(s, "mic_khong_noi_duoc")
                return
            await asyncio.sleep(max(0.0, const.SESSION_MAX_S - const.SESSION_MIC_WAIT_S))
            if self.session is s:
                _LOGGER.warning("phiên %s: quá %.0f giây — đóng phiên", s.kind,
                                const.SESSION_MAX_S)
                self.end(s, "het_gio")
        except asyncio.CancelledError:
            raise

    def touch(self, s: Session | None) -> None:
        """Hội thoại nối tiếp: tính lại hạn của phiên."""
        if s is None or s is not self.session or s.watchdog is None:
            return
        if s.watchdog is not asyncio.current_task():
            s.watchdog.cancel()
        s.watchdog = self.hass.async_create_background_task(
            self._canh(s), "r1_speaker session watchdog")

    def turn_finished(self, s: Session | None, continue_conversation: bool) -> None:
        """Vệ tinh báo một lượt pipeline của phiên ``s`` đã xong."""
        if s is None or s is not self.session:
            return
        if continue_conversation:
            self.touch(s)
        else:
            self.end(s, "xong", cut=False)

    # ── Trigger / nhịp tim từ loa (PHÍA LOA CHƯA CÓ) ──────────────────────────

    def alive(self) -> None:
        """Loa báo còn sống (nhịp tim hoặc trigger)."""
        self.last_alive = dt_util.utcnow()
        self._schedule("alive", const.WAKE_ALIVE_S + 0.5, self._notify)
        self._notify()

    async def trigger(self, word: str | None = None) -> Session:
        """Loa báo đã nghe từ đánh thức → mở phiên. Bận → ``R1SessionBusy``."""
        self.alive()
        self.last_wake = dt_util.utcnow()
        self.last_wake_word = word
        self.wake_pulse = True
        self._schedule("pulse", const.WAKE_PULSE_S, self._tat_xung)
        self.hass.bus.async_fire(const.EVENT_WAKE, {"tu": word})
        self._notify()
        return await self.async_start("wake")

    @callback
    def _tat_xung(self) -> None:
        self.wake_pulse = False
        self._notify()

    def _schedule(self, name: str, delay: float, cb: Callable[[], None]) -> None:
        """Một đồng hồ cho mỗi tên: đặt lại thì thay cái cũ (nhịp tim đều không dồn đồng hồ)."""
        if (old := self._timers.pop(name, None)) is not None:
            old()
        self._timers[name] = async_call_later(self.hass, delay, lambda _now: cb())

    # ── Báo tin (TTS) ─────────────────────────────────────────────────────────

    def announce_done(self) -> None:
        self.announce_seq += 1

    # ── Tắt ───────────────────────────────────────────────────────────────────

    async def async_close(self) -> None:
        for u in self._unsub:
            u()
        self._unsub = []
        for cancel in self._timers.values():
            cancel()
        self._timers = {}
        self.end(self.session, "tat_tich_hop")
        await self.async_settle()

    def as_attributes(self) -> dict[str, Any]:
        return {
            "phien": self.session_kind, "che_do_tu_danh_thuc": self.wake_mode,
            "bo_tieng": self.mic.holding, "luong_ve_ha": self.mic.connected,
            "dau_nhan_mic": ("nhan" if self.mic.connected else
                             "nghe" if getattr(self.mic, "listening", False) else "tat"),
            "loa_bao_con_song": self.speaker_alive,
            "phia_loa": "da_ket_noi" if self.last_alive else "CHO_PHIA_LOA",
            "ket_thuc_gan_nhat": self.last_end, "so_lan_tu_choi": self.refused,
            "tu_choi_gan_nhat": self.last_refusal,
        }
