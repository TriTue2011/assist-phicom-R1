"""Giữ nhạc khi loa phải nói: tạm dừng nhạc đang phát, rồi phát lại khi hết việc.

MỘT cơ chế duy nhất cho cả ba đường — nút đàm thoại / phiên Assist, ``tts.speak`` /
``media_player.play_media`` có ``announce``, và câu trả lời của Assist. ``hold()`` đếm lồng
nhau (kiểu ``R1Mic.hold``): bên đầu tiên chụp nhanh trạng thái rồi tạm dừng, bên cuối cùng nhả
thì mới khôi phục. Nhờ vậy phiên đàm thoại giữ nhạc im suốt cả phiên, câu TTS chen giữa phiên
không phát lại nhạc giữa chừng.

Vì sao không chỉ ``media_play`` lại: DLNA KHÔNG có chế độ «hạ nhạc khi báo tin». TTS phát bằng
``play_media`` nên THAY URI đang phát của renderer; ``Play`` sau đó không đưa nhạc cũ về. Khôi
phục đúng là: nếu renderer vẫn tạm dừng đúng URI cũ → ``media_play``; còn nếu URI đã bị thay
(TTS) → đặt lại đúng URI đã chụp bằng ``play_media``, rồi tua về vị trí đã chụp (nếu có).

CHƯA ĐO: luồng proxy của YouTube có thể hết hạn khi đặt lại URI (khi đó ``play_media`` báo lỗi
→ ghi log, nhạc không tự phát lại); renderer của loa có chấp nhận ``media_seek`` hay không.
Renderer không phát gì lúc ``hold`` thì không có gì để khôi phục.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import const

_LOGGER = logging.getLogger(__name__)

PLAYING = frozenset({"playing", "buffering"})
POLL = 0.05


@dataclass(frozen=True)
class Snapshot:
    entity_id: str
    content_id: str | None
    content_type: str
    position: float | None


class Hold:
    """Một lần giữ nhạc. ``await hold.release()`` gọi lại lần nữa không có tác dụng."""

    def __init__(self, keeper: "MusicKeeper") -> None:
        self._keeper = keeper
        self._done = False

    async def release(self) -> None:
        if self._done:
            return
        self._done = True
        await self._keeper._release()


class MusicKeeper:
    def __init__(self, hass: HomeAssistant, resolve: Callable[[], str | None]) -> None:
        self.hass = hass
        self._resolve = resolve            # thực thể dlna_dmr của loa (tìm lúc cần)
        self._n = 0
        self._snap: Snapshot | None = None
        self._lock = asyncio.Lock()

    @property
    def holds(self) -> int:
        return self._n

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snap

    async def hold(self) -> Hold:
        async with self._lock:
            self._n += 1
            if self._n == 1:
                self._snap = await self._snapshot_and_pause()
        return Hold(self)

    async def _release(self) -> None:
        async with self._lock:
            self._n -= 1
            if self._n == 0 and self._snap is not None:
                snap, self._snap = self._snap, None
                await self._restore(snap)

    # ── tạm dừng ──────────────────────────────────────────────────────────────

    async def _snapshot_and_pause(self) -> Snapshot | None:
        eid = self._resolve()
        st = self.hass.states.get(eid) if eid else None
        if st is None or st.state not in PLAYING:
            return None
        a = st.attributes
        position = a.get("media_position")
        updated = a.get("media_position_updated_at")
        if position is not None and st.state == "playing" and isinstance(updated, datetime):
            position = float(position) + (dt_util.utcnow() - updated).total_seconds()
        snap = Snapshot(eid, a.get("media_content_id"), a.get("media_content_type") or "music",
                        None if position is None else float(position))
        try:
            await self.hass.services.async_call(
                "media_player", "media_pause", {"entity_id": eid}, blocking=True)
        except HomeAssistantError as exc:
            _LOGGER.warning("không tạm dừng được nhạc %s: %s", eid, exc)
            return None
        # Trạng thái của renderer có thể trễ sau lệnh tạm dừng: chờ nó thôi «đang phát», nếu
        # không thì bên theo dõi TTS sẽ thấy «đang phát» của nhạc cũ và tưởng TTS đã xong.
        try:
            async with asyncio.timeout(const.PAUSE_CONFIRM_S):
                while (cur := self.hass.states.get(eid)) is not None and cur.state in PLAYING:
                    await asyncio.sleep(POLL)
        except TimeoutError:
            _LOGGER.debug("%s vẫn báo đang phát sau lệnh tạm dừng", eid)
        return snap

    # ── khôi phục ─────────────────────────────────────────────────────────────

    async def _restore(self, snap: Snapshot) -> None:
        eid = snap.entity_id
        st = self.hass.states.get(eid)
        if st is None or st.state in ("unavailable", "unknown"):
            _LOGGER.warning("không khôi phục được nhạc: %s không sẵn sàng", eid)
            return
        if st.state in PLAYING:
            return                         # đã có gì đó phát (người dùng tự bật): không đụng
        cur_id = st.attributes.get("media_content_id")
        if st.state == "paused" and (snap.content_id is None or cur_id in (None, snap.content_id)):
            await self._call("media_play", {"entity_id": eid})
            return
        if not snap.content_id:
            _LOGGER.warning("không khôi phục được nhạc %s: không biết URI cũ", eid)
            return
        # URI đã bị thay (TTS) hoặc renderer đã dừng: đặt lại đúng URI cũ.
        if not await self._call("play_media", {
                "entity_id": eid, "media_content_id": snap.content_id,
                "media_content_type": snap.content_type}):
            return
        if snap.position is not None and snap.position >= 1.0:
            await self._wait_playing(eid)
            await self._call("media_seek", {"entity_id": eid, "seek_position": snap.position})

    async def _call(self, service: str, data: dict[str, Any]) -> bool:
        try:
            await self.hass.services.async_call("media_player", service, data, blocking=True)
        except HomeAssistantError as exc:
            _LOGGER.warning("khôi phục nhạc: %s lỗi: %s", service, exc)
            return False
        return True

    async def _wait_playing(self, eid: str) -> None:
        try:
            async with asyncio.timeout(const.RESTORE_WAIT):
                while (st := self.hass.states.get(eid)) is None or st.state not in PLAYING:
                    await asyncio.sleep(POLL)
        except TimeoutError:
            _LOGGER.debug("%s chưa phát lại sau %.0f giây, vẫn thử tua", eid, const.RESTORE_WAIT)
