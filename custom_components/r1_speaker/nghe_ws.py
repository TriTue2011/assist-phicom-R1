"""Nghe tiếng trong nhà qua mic loa: WebSocket MỘT CHIỀU loa → điện thoại, chỉ cho QUẢN TRỊ VIÊN.

Khác kênh đàm thoại (``dam_thoai_ws``): không mở phiên song công, không phát gì ra loa, không cần mic điện thoại
(nên chạy cả khi mở HA bằng http trong nhà), và KHÔNG lọc tiếng người: nghe được cả tiếng động xung quanh. Vì
loa không có đèn báo khi đang bị nghe nên: chỉ quản trị viên, đường dẫn đã ký của HA (``auth/sign_path``), một ghi
nhận trong nhật ký mỗi lần bắt đầu/kết thúc, và thẻ hiện rõ «Đang nghe». Tắt mic (``switch.r1_tat_mic``) thì không
có gì để nghe: kết nối bị đóng.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .dam_thoai_ws import GOP_S, TRAN_DEM, _tim_coordinator

_LOGGER = logging.getLogger(__name__)

MA_CAM = 4403          # không phải quản trị viên
MA_KHONG_CO_TIENG = 4404   # mic tắt / loa chưa nối: không có gì để nghe
MA_MIC_TAT = 4405      # đang nghe thì mic bị tắt


class NgheWsView(HomeAssistantView):
    url = "/api/r1_speaker/nghe/{entity_id}/ws"
    name = "api:r1_speaker:nghe_ws"
    requires_auth = True

    async def get(self, request: web.Request, entity_id: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            return web.Response(status=403, text="chỉ quản trị viên được nghe mic loa")
        coordinator = _tim_coordinator(hass, entity_id)
        if coordinator is None:
            return web.Response(status=404, text="không phải thực thể của r1_speaker")
        mic = coordinator.mic
        ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=1 << 10)
        await ws.prepare(request)
        if mic.muted or not coordinator.mic_server.receiving:
            await ws.send_json({"loi": "Mic loa đang tắt hoặc loa chưa nối về HA: không có gì để nghe."})
            await ws.close(code=MA_KHONG_CO_TIENG)
            return ws

        dem = bytearray()

        def tu_mic(khuc: bytes) -> None:
            dem.extend(khuc)
            if len(dem) > TRAN_DEM:
                del dem[: len(dem) - TRAN_DEM]       # điện thoại chậm: bỏ phần cũ nhất

        huy = mic.add_chunk_listener(tu_mic)

        async def gui_di() -> None:
            while not ws.closed:
                await asyncio.sleep(GOP_S)
                if mic.muted:
                    await ws.send_json({"loi": "Mic loa vừa bị tắt."})
                    await ws.close(code=MA_MIC_TAT)
                    return
                if dem:
                    khuc = bytes(dem)
                    dem.clear()
                    await ws.send_bytes(khuc)

        _LOGGER.info("R1: %s bắt đầu nghe mic loa", user.name)
        gui = hass.async_create_background_task(gui_di(), "r1_speaker nghe ws gui")
        try:
            async for _msg in ws:                      # điện thoại không gửi gì lên; chỉ chờ đóng
                pass
        finally:
            gui.cancel()
            with contextlib.suppress(asyncio.CancelledError, ConnectionError):
                await gui
            huy()
            _LOGGER.info("R1: %s thôi nghe mic loa", user.name)
        return ws
