"""Loa R1 giả: máy chủ WebSocket thật (RFC 6455) chạy ở 127.0.0.1, KHÔNG chạm loa thật.

Mọi khoá, token, địa chỉ trong thư mục tests là CHUỖI GIẢ dùng cho test (địa chỉ ví dụ dùng
dải 192.0.2.0/24 của RFC 5737 hoặc 127.0.0.1); không có bí mật thật."""

import json

import pytest
from aiohttp import WSMsgType, web

from .du_lieu_that import GET_EQ_CONFIG_MSG


class FakeR1:
    def __init__(self):
        self.state = {"vol": 7, "dlna_open": True, "airplay_open": False, "device_state": 1,
                      "music_light_enable": True, "music_light_luma": 50,
                      "music_light_chroma": 60}
        #: get_eq_config THẬT (data là chuỗi JSON), không phải dữ liệu tự nghĩ.
        self.eq = GET_EQ_CONFIG_MSG
        self.received: list[dict] = []
        #: ok | garbage_info | bad_eq | silent | drop
        self.mode = "ok"
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
            if self.mode == "drop":
                await ws.close()
                break
            if self.mode == "silent":
                continue
            await ws.send_str(json.dumps({"type": "broadcast", "x": 1}))  # tiếng ồn
            if msg["type"] == "get_info":
                if self.mode == "garbage_info":
                    await ws.send_str(json.dumps({"type": "get_info", "data": "{không phải json"}))
                else:  # như web của loa: data là CHUỖI JSON
                    await ws.send_str(json.dumps(
                        {"type": "get_info", "data": json.dumps(self.state)}))
            elif msg["type"] == "get_eq_config":
                if self.mode == "bad_eq":
                    await ws.send_str(json.dumps({"type": "get_eq_config", "data": [1, 2]}))
                else:
                    await ws.send_str(json.dumps(self.eq))
        return ws

    async def start(self):
        app = web.Application()
        app.router.add_get("/", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    def commands(self, msg_type):
        return [m for m in self.received if m["type"] == msg_type]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def _socket(socket_enabled):
    yield


@pytest.fixture(autouse=True)
async def _homeassistant(hass):
    """Tích hợp phụ thuộc assist_pipeline → conversation đòi component ``homeassistant``."""
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture(autouse=True)
def _gain_don_vi(request):
    """Các ca cũ khẳng định tiếng đi qua NGUYÊN VẸN (khuếch đại 0 dB). Mặc định thật của
    ``number.r1_tang_mic`` là +12 dB (``DEFAULT_MIC_GAIN_DB``); ca nào muốn đo mặc định thật
    đánh dấu ``@pytest.mark.gain_mac_dinh``."""
    if request.node.get_closest_marker("gain_mac_dinh"):
        yield
        return
    from unittest import mock
    with mock.patch("custom_components.r1_speaker.number.DEFAULT_MIC_GAIN_DB", 0.0):
        yield


@pytest.fixture
async def r1():
    f = FakeR1()
    await f.start()
    yield f
    await f.stop()
