"""Điều khiển nhạc qua WebSocket CÓ SẴN của firmware loa (cổng 8082, khoá ``"action"``).

Không cần mã nào chạy trên loa. Danh sách lệnh lấy từ bộ dịch ngược ``onMessage`` của
``info.dourok.voicebot`` (``network/a.java``). Chỉ bọc những lệnh mà mã cho thấy tên và tham số:

* phát: ``play_song`` (``video_id`` YouTube), ``play_zing`` (``song_id`` hoặc ``song_name`` +
  ``artist_name``);
* tìm: ``search_songs`` (YouTube), ``search_zing`` (``query``);
* điều khiển: ``pause``, ``resume``, ``stop``, ``next``, ``previous``, ``seek`` (``position``, ms),
  ``toggle_repeat``, ``toggle_auto_next``;
* danh sách phát: ``playlist_list/create/delete/add_song/remove_song/get_songs/play``.

KHÔNG có trên cổng 8082 (đã đối chiếu mã): ``volume_up``, ``volume_down``, ``get_playback_state``
(âm lượng là ``set_vol`` ở cổng 8080, đã có thực thể ``number``). Kiểu trả lời của từng lệnh
CHƯA kiểm trên loa thật; vì vậy chờ trả lời có hạn và coi "không thấy trả lời" là đã gửi.
Cổng 8082 không có xác thực (theo tài liệu dịch ngược): chỉ nối tới địa chỉ người dùng đã khai.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import aiohttp

from .client import R1Error

MUSIC_PORT = 8082
ACK_TIMEOUT = 3.0
SEARCH_TIMEOUT = 20.0

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
MAX_TEXT = 200

#: Lệnh điều khiển không tham số → kiểu phản hồi thường gặp (chỉ để thoát chờ sớm).
CONTROL_COMMANDS: dict[str, set[str]] = {
    "pause": {"player_state"}, "resume": {"player_state"}, "stop": {"player_state"},
    "next": {"player_state"}, "previous": {"player_state"},
    "toggle_repeat": {"repeat_state"}, "toggle_auto_next": {"auto_next_state"},
}
PLAYLIST_COMMANDS = ("playlist_list", "playlist_create", "playlist_delete", "playlist_add_song",
                     "playlist_remove_song", "playlist_get_songs", "playlist_play")
#: Nguồn tìm → (action, kiểu trả lời).
SEARCH_SOURCES = {"youtube": ("search_songs", "search_result"),
                  "zing": ("search_zing", "zing_result")}


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise R1Error(f"{name} phải là chuỗi không rỗng, tối đa {MAX_TEXT} ký tự")
    return value.strip()


def _params(params: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in (params or {}).items():
        if not isinstance(key, str) or key in ("action",) or len(key) > 40:
            raise R1Error(f"tham số không hợp lệ: {key!r}")
        if isinstance(val, str):
            if len(val) > MAX_TEXT:
                raise R1Error(f"{key} quá dài")
        elif not isinstance(val, (int, float, bool)):
            raise R1Error(f"{key} phải là chuỗi/số/boolean")
        out[key] = val
    return out


class R1Music:
    def __init__(self, session: aiohttp.ClientSession, host: str,
                 port: int | None = None) -> None:
        self._session, self.host = session, host
        self.port = MUSIC_PORT if port is None else port

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def call(self, action: str, params: dict[str, Any] | None = None, *,
                   expect: set[str] | None = None, timeout: float = ACK_TIMEOUT,
                   must_reply: bool = False) -> dict | None:
        """Gửi ``{"action": action, ...}``; trả tin đầu tiên có ``type`` thuộc ``expect``.

        Loa trả ``{"type":"error","message":...}`` → ``R1Error`` mang đúng lời đó. Hết giờ mà
        không thấy trả lời: trả ``None`` (lệnh đã gửi), trừ khi ``must_reply`` (tìm kiếm)."""
        payload = json.dumps({"action": action, **_params(params)})
        try:
            ws = await self._session.ws_connect(
                self.url, timeout=aiohttp.ClientWSTimeout(ws_close=ACK_TIMEOUT))
            try:
                await ws.send_str(payload)
                try:
                    async with asyncio.timeout(timeout):
                        while True:
                            raw = await ws.receive()
                            if raw.type != aiohttp.WSMsgType.TEXT:
                                break
                            try:
                                msg = json.loads(raw.data)
                            except ValueError:
                                continue
                            kind = msg.get("type") if isinstance(msg, dict) else None
                            if kind == "error":
                                raise R1Error(f"loa từ chối {action}: {msg.get('message', '?')}")
                            if expect and kind in expect:
                                return msg
                except TimeoutError:
                    pass
            finally:
                await ws.close()
        except R1Error:
            raise
        except (aiohttp.ClientError, OSError, TimeoutError) as exc:
            raise R1Error(f"{self.url}: {exc!r}") from exc
        if must_reply:
            raise R1Error(f"loa không trả lời {action} trong {timeout:.0f} giây")
        return None

    # ── phát ──────────────────────────────────────────────────────────────────

    async def play_youtube(self, video_id: str) -> None:
        if not isinstance(video_id, str) or not VIDEO_ID.match(video_id):
            raise R1Error("video_id YouTube không hợp lệ")
        await self.call("play_song", {"video_id": video_id}, expect={"play_song_result"})

    async def play_zing(self, song_id: str | None = None, song_name: str | None = None,
                        artist_name: str | None = None) -> None:
        if song_id:
            params: dict[str, Any] = {"song_id": _text(song_id, "song_id")}
        else:
            params = {"song_name": _text(song_name, "song_name")}
            if artist_name:
                params["artist_name"] = _text(artist_name, "artist_name")
        await self.call("play_zing", params, expect={"play_zing_result"})

    async def search(self, source: str, query: str) -> dict:
        if source not in SEARCH_SOURCES:
            raise R1Error(f"nguồn tìm không hỗ trợ: {source!r}")
        action, reply = SEARCH_SOURCES[source]
        res = await self.call(action, {"query": _text(query, "query")}, expect={reply},
                              timeout=SEARCH_TIMEOUT, must_reply=True)
        assert res is not None
        return res

    # ── điều khiển ────────────────────────────────────────────────────────────

    async def control(self, command: str) -> None:
        if command not in CONTROL_COMMANDS:
            raise R1Error(f"lệnh điều khiển không hỗ trợ: {command!r}")
        await self.call(command, expect=CONTROL_COMMANDS[command])

    async def seek(self, position_ms: int) -> None:
        if isinstance(position_ms, bool) or not isinstance(position_ms, int) or position_ms < 0:
            raise R1Error("position phải là số nguyên mili-giây ≥ 0")
        await self.call("seek", {"position": position_ms}, expect={"seek_result"})

    async def playlist(self, command: str, params: dict[str, Any] | None = None) -> dict | None:
        """Lệnh danh sách phát. Tên tham số (id, name, source…) lấy theo mã dịch ngược, CHƯA
        kiểm trên loa thật; chuyển nguyên cho loa sau khi kiểm kiểu giá trị."""
        if command not in PLAYLIST_COMMANDS:
            raise R1Error(f"lệnh danh sách phát không hỗ trợ: {command!r}")
        return await self.call(command, params, expect=_PLAYLIST_REPLIES[command])

_PLAYLIST_REPLIES = {
    "playlist_list": {"playlist_list_result"},
    "playlist_create": {"playlist_created"},
    "playlist_delete": {"playlist_deleted"},
    "playlist_add_song": {"playlist_song_added"},
    "playlist_remove_song": {"playlist_song_removed"},
    "playlist_get_songs": {"playlist_songs_result"},
    "playlist_play": {"playlist_play_started"},
}
