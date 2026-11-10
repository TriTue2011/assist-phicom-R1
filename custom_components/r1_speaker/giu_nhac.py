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

NV287 — ducking (``hold(duck=True)``): khi tin báo đi đường KHÁC (AirPlay song song,
không đụng DLNA) thì không cần tạm dừng nữa — nhạc vẫn phát nhưng nhỏ đi ``nac`` nấc
trong lúc tin phát, rồi trả đúng mức cũ khi bên cuối cùng nhả (kể cả khi tin lỗi,
vì nhả luôn chạy trong ``finally`` của bên theo dõi tin). Hạ âm lượng dùng đúng
đường âm lượng của thực thể (``volume_level``/``volume_set`` → APK ``setStreamVolume``);
không đọc được mức cũ thì về đường tạm dừng cũ (an toàn hơn là hạ mù rồi không
trả được). Ducking chỉ có ý nghĩa khi tin không thay URI nhạc: tin đi đường
thường mà hạ nhạc thì nhạc đã im rồi, hạ thêm cũng vô nghĩa — bên gọi phải chỉ
bật duck khi tin đi song song.

CHƯA ĐO: luồng proxy của YouTube có thể hết hạn khi đặt lại URI (khi đó ``play_media`` báo lỗi
→ ghi log, nhạc không tự phát lại); renderer của loa có chấp nhận ``media_seek`` hay không.
Renderer không phát gì lúc ``hold`` thì không có gì để khôi phục.
CHƯA ĐO (NV287): loa Android có trộn được DLNA + RAOP cùng lúc hay không, và RAOP
có dùng luồng âm lượng riêng với STREAM_MUSIC hay không — nếu RAOP cũng đi
STREAM_MUSIC thì hạ nhạc cũng hạ luôn tin, ducking vô nghĩa và phải tắt cờ.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
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
    def __init__(self, hass: HomeAssistant, resolve: Callable[[], str | None],
                 refresh: Callable[[], Awaitable[None]] | None = None,
                 *, am_luong: tuple[Callable[[], Awaitable[float | None]],
                                     Callable[[float], Awaitable[None]]] | None = None) -> None:
        self.hass = hass
        self._resolve = resolve            # thực thể media_player của loa (tìm lúc cần)
        self._refresh = refresh            # đọc trạng thái renderer MỚI trước khi chụp (ta không hỏi nền lúc idle)
        self._am_luong = am_luong          # (đọc mức 0..1, đặt mức 0..1) — mặc định: trạng thái/dịch vụ của thực thể
        self._n = 0
        self._snap: Snapshot | None = None
        self._che_do: str | None = None    # "pause" | "duck" của lần giữ ngoài cùng
        self._muc_cu: float | None = None  # mức trước khi duck (để trả đúng mức cũ)
        self._da_ha = False
        self._lock = asyncio.Lock()

    @property
    def holds(self) -> int:
        return self._n

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snap

    @property
    def se_phat_lai(self) -> bool:
        """True đúng khi nhả cuối cùng sẽ PHÁT LẠI nhạc đã chụp (đã tạm dừng nhạc thật). Lúc đó renderer về idle là của tin báo, không phải
        bài hết. Không có gì được chụp (không có nhạc), hoặc mới chỉ hạ nhỏ (nhạc vẫn phát, nhả chỉ trả âm lượng) thì idle là idle thật."""
        return self._snap is not None and self._che_do == "pause"

    async def hold(self, *, duck: bool = False, nac: int = 5) -> Hold:
        async with self._lock:
            self._n += 1
            try:
                if self._n == 1:
                    self._da_ha, self._muc_cu = False, None
                    if duck:
                        # _snapshot_and_duck tự về tạm dừng khi không hạ được mức.
                        self._snap = await self._snapshot_and_duck(nac)
                    else:
                        self._snap = await self._snapshot_and_pause()
                    if self._snap is None:
                        self._che_do = None
                    elif duck and self._da_ha:
                        self._che_do = "duck"
                    else:
                        self._che_do = "pause"
                elif not duck and self._che_do == "duck" and self._snap is not None:
                    # NV287: đang hạ nhạc cho tin song song mà có bên cần nhạc IM (phiên đàm thoại mở mic): hạ nhỏ vẫn lọt
                    # vào mic, nên tạm dừng nốt. Nhả cuối cùng sẽ trả mức rồi phát lại như đường tạm dừng.
                    # Chụp lại để vị trí là của LÚC NÀY (nhạc đã phát tiếp suốt lúc hạ nhỏ), rồi mới tạm dừng.
                    moi = await self._chup()
                    if moi is not None and await self._tam_dung(moi.entity_id):
                        self._snap, self._che_do = moi, "pause"
            except BaseException:
                # Lỗi/huỷ giữa chừng thì lượt này không tồn tại: không để bộ đếm kẹt ở n>0 và không để nhạc nhỏ mãi.
                self._n -= 1
                if self._n == 0:
                    self._snap, self._che_do = None, None
                    eid = self._resolve()
                    if eid:
                        await self._tra_muc(eid)
                raise
        return Hold(self)

    async def _release(self) -> None:
        async with self._lock:
            self._n -= 1
            if self._n == 0 and self._snap is not None:
                snap, che_do = self._snap, self._che_do
                try:
                    await self._tra_muc(snap.entity_id)    # chỉ có việc khi từng hạ nhạc (duck, hoặc duck rồi nâng lên tạm dừng)
                    if che_do != "duck":
                        await self._restore(snap)
                finally:
                    # Xoá SAU khi khôi phục xong: trong lúc phát lại, ``se_phat_lai`` còn đúng nên idle thoáng qua không thành «hết bài».
                    self._snap, self._che_do = None, None

    # ── chụp ──────────────────────────────────────────────────────────────────

    async def _chup(self) -> Snapshot | None:
        if self._refresh is not None:
            try:
                async with asyncio.timeout(const.REFRESH_TOI_DA):
                    await self._refresh()
            except (TimeoutError, HomeAssistantError, OSError) as exc:
                _LOGGER.debug("không đọc lại được trạng thái nhạc trước khi chụp: %s", type(exc).__name__)
        eid = self._resolve()
        st = self.hass.states.get(eid) if eid else None
        if st is None or st.state not in PLAYING:
            return None
        a = st.attributes
        position = a.get("media_position")
        updated = a.get("media_position_updated_at")
        if position is not None and st.state == "playing" and isinstance(updated, datetime):
            position = float(position) + (dt_util.utcnow() - updated).total_seconds()
        return Snapshot(eid, a.get("media_content_id"), a.get("media_content_type") or "music",
                        None if position is None else float(position))

    # ── tạm dừng ──────────────────────────────────────────────────────────────

    async def _snapshot_and_pause(self) -> Snapshot | None:
        snap = await self._chup()
        if snap is None:
            return None
        return snap if await self._tam_dung(snap.entity_id) else None

    async def _tam_dung(self, eid: str) -> bool:
        try:
            await self.hass.services.async_call(
                "media_player", "media_pause", {"entity_id": eid}, blocking=True)
        except HomeAssistantError as exc:
            _LOGGER.warning("không tạm dừng được nhạc %s: %s", eid, exc)
            return False
        # Trạng thái của renderer có thể trễ sau lệnh tạm dừng: chờ nó thôi «đang phát», nếu
        # không thì bên theo dõi TTS sẽ thấy «đang phát» của nhạc cũ và tưởng TTS đã xong.
        try:
            async with asyncio.timeout(const.PAUSE_CONFIRM_S):
                while (cur := self.hass.states.get(eid)) is not None and cur.state in PLAYING:
                    await asyncio.sleep(POLL)
        except TimeoutError:
            _LOGGER.debug("%s vẫn báo đang phát sau lệnh tạm dừng", eid)
        return True

    # ── ducking (NV287) ───────────────────────────────────────────────────────

    async def _lay_muc(self, eid: str) -> float | None:
        if self._am_luong is not None:
            try:
                muc = await self._am_luong[0]()
            except Exception as exc:  # noqa: BLE001 — âm lượng là phần phụ: hỏng thì về tạm dừng, không phá tin
                _LOGGER.debug("không đọc được âm lượng %s: %s", eid, type(exc).__name__)
                return None
            return muc if isinstance(muc, (int, float)) and 0.0 <= float(muc) <= 1.0 else None
        st = self.hass.states.get(eid)
        muc = st.attributes.get("volume_level") if st is not None else None
        return muc if isinstance(muc, (int, float)) and 0.0 <= float(muc) <= 1.0 else None

    async def _dat_muc(self, eid: str, muc: float) -> bool:
        try:
            if self._am_luong is not None:
                await self._am_luong[1](muc)
            else:
                await self.hass.services.async_call(
                    "media_player", "volume_set", {"entity_id": eid, "volume_level": muc}, blocking=True)
        except Exception as exc:  # noqa: BLE001 — như trên: hỏng thì về tạm dừng / ghi log, không phá tin
            _LOGGER.debug("không đặt được âm lượng %s: %s", eid, type(exc).__name__)
            return False
        return True

    async def _snapshot_and_duck(self, nac: int) -> Snapshot | None:
        """Chụp nhưng KHÔNG tạm dừng: hạ nhạc ``nac`` nấc (thang 0–15 của loa).
        Không đọc/đặt được mức → về tạm dừng như cũ (an toàn hơn hạ mù)."""
        snap = await self._chup()
        if snap is None:
            return None
        eid = snap.entity_id
        if nac <= 0:
            # Không hạ nhạc (tin song song, ducking tắt): khỏi cần đọc/đặt âm lượng — nhạc phát tiếp ở mức đầy đủ.
            self._da_ha = True
            return snap
        muc_cu = await self._lay_muc(eid)
        if muc_cu is None:
            _LOGGER.info("ducking: không đọc được mức âm lượng cũ của %s (APK chưa nối?), về tạm dừng", eid)
            return await self._snapshot_and_pause()
        nac = max(0, int(nac))
        muc_moi = max(const.VOL_MIN, round(float(muc_cu) * const.VOL_MAX) - nac) / const.VOL_MAX
        # Ghi mức cũ TRƯỚC khi hạ: bị huỷ giữa lúc đặt mức thì bên gọi (hold) vẫn trả được đúng mức cũ.
        self._muc_cu, self._da_ha = float(muc_cu), True
        if muc_moi < float(muc_cu) and not await self._dat_muc(eid, muc_moi):
            self._muc_cu, self._da_ha = None, False
            _LOGGER.warning("ducking: không hạ được mức của %s, về tạm dừng", eid)
            return await self._snapshot_and_pause()
        # Đã vào chế độ duck (kể cả khi mức đã ở 0, không còn gì để hạ):
        # nhả chỉ trả mức, không bao giờ phát lại nhạc như đường tạm dừng.
        return snap

    async def _tra_muc(self, eid: str) -> None:
        if self._da_ha and self._muc_cu is not None and not await self._dat_muc(eid, self._muc_cu):
            _LOGGER.warning("ducking: không trả được mức âm lượng cũ của %s — nhạc có thể còn nhỏ", eid)
        self._da_ha, self._muc_cu = False, None

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
        # ``paused`` mà ``idle_reason`` = dang_giu là TRẠNG THÁI GIẢ của loa (renderer thật đã idle sau tin báo, URI nhạc đã bị tin thay): không phải
        # «đang tạm dừng đúng bài cũ». Phải đặt lại URI, không chỉ ``media_play`` (xem ``R1Player.state``).
        gia_tam_dung = st.attributes.get("idle_reason") == "dang_giu"
        if st.state == "paused" and not gia_tam_dung and (snap.content_id is None or cur_id in (None, snap.content_id)):
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
