"""Điều khiển nhạc qua WebSocket "action" (cổng 8082 của firmware) với loa giả cục bộ."""

import json
from unittest import mock

import pytest
from aiohttp import WSMsgType, web
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from custom_components.r1_speaker import media_player as mp_mod
from custom_components.r1_speaker import music

from .test_r1 import _them

LOA = "media_player.r1_loa"


class FakeMusic:
    """Máy chủ WS giả của cổng nhạc; trả lời theo bảng ``replies`` (action → danh sách tin)."""

    def __init__(self):
        self.received: list[dict] = []
        self.replies: dict[str, list[dict]] = {}
        self.port = 0
        self._runner = None

    async def _handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                continue
            msg = json.loads(m.data)
            self.received.append(msg)
            await ws.send_str(json.dumps({"type": "chat_message", "x": 1}))  # tiếng ồn
            for r in self.replies.get(msg["action"], []):
                await ws.send_str(json.dumps(r))
        return ws

    async def start(self):
        app = web.Application()
        app.router.add_get("/", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]

    async def stop(self):
        await self._runner.cleanup()


@pytest.fixture
async def nhac(r1):
    f = FakeMusic()
    await f.start()
    # Dịch vụ nhạc mặc định KHÔNG đăng ký (AI box đã gỡ); các ca dưới kiểm riêng mã nhạc nên
    # bật cờ tại đây. Ca "mặc định không đăng ký" nằm ở tests/test_bo_dam.py.
    with mock.patch.object(mp_mod, "MUSIC_SERVICES", True), \
            mock.patch.object(music, "MUSIC_PORT", f.port), \
            mock.patch.object(music, "ACK_TIMEOUT", 0.3), \
            mock.patch.object(music, "SEARCH_TIMEOUT", 1.0):
        yield f
    await f.stop()


async def _goi(hass, name, data, **kw):
    return await hass.services.async_call(
        "r1_speaker", name, {"entity_id": LOA, **data}, blocking=True, **kw)


async def test_phat_youtube(hass, r1, nhac):
    await _them(hass, r1)
    nhac.replies["play_song"] = [{"type": "play_song_result", "success": True}]
    await _goi(hass, "music_play", {"source": "youtube", "video_id": "dQw4w9WgXcQ"})
    assert nhac.received == [{"action": "play_song", "video_id": "dQw4w9WgXcQ"}]


@pytest.mark.parametrize("vid", ["", "a b c d e f", "../../etc", "x" * 40, "ab"])
async def test_video_id_xau_bi_tu_choi_khong_gui(hass, r1, nhac, vid):
    await _them(hass, r1)
    with pytest.raises(HomeAssistantError):
        await _goi(hass, "music_play", {"source": "youtube", "video_id": vid})
    assert nhac.received == []


async def test_phat_zing_theo_ten(hass, r1, nhac):
    await _them(hass, r1)
    await _goi(hass, "music_play", {"source": "zing", "song_name": "Bài A", "artist_name": "B"})
    assert nhac.received == [{"action": "play_zing", "song_name": "Bài A", "artist_name": "B"}]


async def test_phat_zing_thieu_ten_loi(hass, r1, nhac):
    await _them(hass, r1)
    with pytest.raises(HomeAssistantError):
        await _goi(hass, "music_play", {"source": "zing"})
    assert nhac.received == []


@pytest.mark.parametrize("cmd", ["pause", "resume", "stop", "next", "previous",
                                 "toggle_repeat", "toggle_auto_next"])
async def test_dieu_khien(hass, r1, nhac, cmd):
    await _them(hass, r1)
    await _goi(hass, "music_control", {"command": cmd})
    assert nhac.received == [{"action": cmd}]


async def test_seek_va_seek_thieu_vi_tri(hass, r1, nhac):
    await _them(hass, r1)
    await _goi(hass, "music_control", {"command": "seek", "position_ms": 30000})
    assert nhac.received == [{"action": "seek", "position": 30000}]
    with pytest.raises(HomeAssistantError):
        await _goi(hass, "music_control", {"command": "seek"})


async def test_lenh_khong_co_tren_firmware_bi_chan_o_schema(hass, r1, nhac):
    await _them(hass, r1)
    for cmd in ("volume_up", "volume_down", "get_playback_state"):
        with pytest.raises(vol.Invalid):
            await _goi(hass, "music_control", {"command": cmd})
    assert nhac.received == []


async def test_tim_nhac_tra_ket_qua(hass, r1, nhac):
    await _them(hass, r1)
    ket_qua = {"type": "search_result", "success": True, "count": 1,
               "songs": [{"video_id": "abc12345678", "title": "T"}]}
    nhac.replies["search_songs"] = [ket_qua]
    res = await _goi(hass, "music_search", {"source": "youtube", "query": "nhạc"},
                     return_response=True)
    assert res[LOA]["result"] == ket_qua
    assert nhac.received == [{"action": "search_songs", "query": "nhạc"}]


async def test_tim_nhac_loa_bao_loi_hoac_im(hass, r1, nhac):
    await _them(hass, r1)
    nhac.replies["search_zing"] = [{"type": "error", "success": False, "message": "hỏng"}]
    with pytest.raises(HomeAssistantError, match="hỏng"):
        await _goi(hass, "music_search", {"source": "zing", "query": "x"},
                   return_response=True)
    nhac.replies.clear()
    with pytest.raises(HomeAssistantError, match="không trả lời"):
        await _goi(hass, "music_search", {"source": "youtube", "query": "x"},
                   return_response=True)


async def test_loa_bao_loi_khi_phat(hass, r1, nhac):
    await _them(hass, r1)
    nhac.replies["pause"] = [{"type": "error", "success": False, "message": "no player"}]
    with pytest.raises(HomeAssistantError, match="no player"):
        await _goi(hass, "music_control", {"command": "pause"})


async def test_playlist_chi_nhan_lenh_trong_danh_sach(hass, r1, nhac):
    await _them(hass, r1)
    nhac.replies["playlist_list"] = [{"type": "playlist_list_result", "playlists": []}]
    res = await _goi(hass, "music_playlist", {"command": "playlist_list"},
                     return_response=True)
    assert res[LOA]["result"]["playlists"] == []
    with pytest.raises(vol.Invalid):
        await _goi(hass, "music_playlist", {"command": "shell"})
    with pytest.raises(HomeAssistantError):
        await _goi(hass, "music_playlist", {"command": "playlist_play",
                                            "params": {"x": {"lồng": 1}}})
    assert [m["action"] for m in nhac.received] == ["playlist_list"]


async def test_loa_tat_bao_loi_sach(hass, r1, nhac):
    await _them(hass, r1)
    await nhac.stop()
    nhac._runner = mock.AsyncMock()  # fixture sẽ dọn lại
    with pytest.raises(HomeAssistantError):
        await _goi(hass, "music_control", {"command": "pause"})
