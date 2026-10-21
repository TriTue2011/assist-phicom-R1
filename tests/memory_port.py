"""Bản trong bộ nhớ của hai giao diện âm thanh (``audio_port``), một renderer DLNA giả dạng thực
thể ``media_player`` thật, và một "tay lái" Assist giả. KHÔNG TCP, KHÔNG chạm loa.

Các bản giả này thể hiện HỢP ĐỒNG: bất kỳ đường mic thật nào sau này (chưa có) cũng phải
thoả ``PcmSource``/``PcmSink`` giống hệt chúng."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import timedelta

from homeassistant.components.media_player import (MediaPlayerEntity, MediaPlayerEntityFeature,
                                                   MediaPlayerState)
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockEntityPlatform

from custom_components.r1_speaker.audio_port import check_frame


class MemorySource:
    """Mic giả. ``on_demand``: chỉ «nối» khi có bên xin (``want``) — như mic của loa chờ từ
    đánh thức. ``auto_connect=False`` để mô phỏng nối không được."""

    def __init__(self, configured=True, on_demand=False, auto_connect=True):
        self.configured, self.on_demand, self.auto_connect = configured, on_demand, auto_connect
        self.muted = False
        self.gain_db = 0.0
        self.wants = 0
        self._connected = False
        self._holds = 0
        self._chunks: list[Callable] = []
        self._states: list[Callable] = []
        self._links: list[Callable] = []
        self.sent = 0                      # số khung đã «rời loa» (tới người nghe)
        if not on_demand and auto_connect:
            self._connected = True

    @property
    def connected(self): return self._connected
    @property
    def holding(self): return self._holds > 0
    @property
    def available(self): return self.configured and (self.muted or self._connected or self.on_demand)

    def _add(self, lst, cb):
        lst.append(cb)
        return lambda: lst.remove(cb)

    def add_chunk_listener(self, cb): return self._add(self._chunks, cb)
    def add_state_listener(self, cb): return self._add(self._states, cb)
    def add_link_listener(self, cb): return self._add(self._links, cb)

    def _fire(self, lst):
        for cb in list(lst):
            cb()

    def set_connected(self, value: bool):
        if value != self._connected:
            self._connected = value
            self._fire(self._links)

    def set_muted(self, muted: bool):
        self.muted = muted
        if muted:
            self.set_connected(False)
        self._fire(self._states)
        self._fire(self._links)

    def want(self):
        self.wants += 1
        if self.on_demand and self.auto_connect and not self.muted:
            self.set_connected(True)
        done = False

        def release():
            nonlocal done
            if done:
                return
            done = True
            self.wants -= 1
            if self.on_demand and self.wants == 0:
                self.set_connected(False)

        return release

    def hold(self):
        self._holds += 1
        self._fire(self._links)
        done = False

        def release():
            nonlocal done
            if not done:
                done = True
                self._holds -= 1
                self._fire(self._links)

        return release

    def push(self, frame: bytes) -> bool:
        """Loa đẩy một khung. Trả True nếu khung tới người nghe."""
        check_frame(frame)
        if not self._connected or self.holding or self.muted:
            return False
        self.sent += 1
        for cb in list(self._chunks):
            cb(frame)
        return True


class MemorySink:
    configured = True

    def __init__(self):
        self.played = bytearray()
        self._states: list[Callable] = []

    def add_state_listener(self, cb):
        self._states.append(cb)
        return lambda: self._states.remove(cb)

    async def async_play(self, source: AsyncIterator[bytes]) -> float:
        async for f in source:
            self.played += check_frame(f)
        return len(self.played) / 32000


class FakeDriver:
    """Tay lái Assist giả: ghi lại lời gọi."""

    def __init__(self):
        self.began = 0
        self.cut = 0

    def begin_session(self): self.began += 1
    def cut_turn(self): self.cut += 1


class FakeDmrPlayer(MediaPlayerEntity):
    """Renderer DLNA giả là thực thể media_player THẬT của HA (dịch vụ pause/play/play_media/
    seek đi qua đúng đường dịch vụ). ``log`` ghi mọi lệnh theo thứ tự."""

    _attr_should_poll = False
    _attr_supported_features = (MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.PAUSE
                                | MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.STOP
                                | MediaPlayerEntityFeature.SEEK)

    def __init__(self, entity_id="media_player.dmr_gia"):
        self.entity_id = entity_id
        self._attr_unique_id = "fake-dmr-1"
        self._attr_name = "DMR giả"
        self.log: list[tuple] = []
        self._cid = None
        self._ctype = None
        self._st = MediaPlayerState.IDLE
        self._pos = None
        self._pos_at = None

    @property
    def state(self): return self._st
    @property
    def media_content_id(self): return self._cid
    @property
    def media_content_type(self): return self._ctype
    @property
    def media_position(self): return self._pos
    @property
    def media_position_updated_at(self): return self._pos_at

    def start_music(self, url, position=None, ago=0.0):
        """Đặt sẵn: đang phát ``url`` (như người dùng bật nhạc trước đó)."""
        self._cid, self._ctype, self._st = url, "audio/mpeg", MediaPlayerState.PLAYING
        self._pos = position
        self._pos_at = dt_util.utcnow() - timedelta(seconds=ago) if position is not None else None
        self.async_write_ha_state()

    def finish(self):
        """Hết bài / hết tin."""
        self._st = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_media_pause(self):
        self.log.append(("pause",))
        self._st = MediaPlayerState.PAUSED
        self.async_write_ha_state()

    async def async_media_play(self):
        self.log.append(("play",))
        self._st = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    async def async_media_stop(self):
        self.log.append(("stop",))
        self._st = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_play_media(self, media_type, media_id, **kwargs):
        self.log.append(("play_media", media_id))
        self._cid, self._ctype, self._st = media_id, str(media_type), MediaPlayerState.PLAYING
        self._pos = self._pos_at = None
        self.async_write_ha_state()

    async def async_media_seek(self, position):
        self.log.append(("seek", position))

    def urls(self):
        return [e[1] for e in self.log if e[0] == "play_media"]


async def them_dmr_gia(hass) -> FakeDmrPlayer:
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, "media_player", {})
    ent = FakeDmrPlayer()
    plat = MockEntityPlatform(hass, domain="media_player", platform_name="fake_dmr")
    await plat.async_add_entities([ent])
    await hass.async_block_till_done()
    return ent
