"""Đàm thoại bằng MICRO ĐIỆN THOẠI trong thẻ, theo cách bộ đàm camera của c2a: MỘT WebSocket hai chiều.

* điện thoại → HA: khung nhị phân PCM16 16 kHz mono (mic điện thoại) → ``duplex.feed_playback`` → loa;
  khung chữ ``het`` = người dùng thôi nói (chỉ ghi nhận);
* HA → điện thoại: tiếng người từ mic loa (đã qua VAD, ``duplex.add_audio_listener``) gộp ~0,1 giây một
  khung nhị phân; lỗi gửi dạng JSON ``{"loi": "..."}``.

Xác thực bằng ĐƯỜNG DẪN ĐÃ KÝ của HA (thẻ gọi ``auth/sign_path``): không để khoá nào trong trình duyệt, và chỉ
người đã đăng nhập HA mới xin được. Kết nối mở thì mở phiên song công (nếu chưa mở); đóng thì đóng phiên NẾU
chính kết nối này đã mở nó và không có ai giữ phiên mở («Bật mic luôn»). Mỗi loa một điện thoại một lúc."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiohttp import WSMsgType, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .dam_thoai import R1SessionBusy

_LOGGER = logging.getLogger(__name__)

#: Gộp khung mic loa thành ngần này giây một khung gửi đi (khung gốc 10 ms: quá nhỏ cho mạng).
GOP_S = 0.05
#: Trần dồn tiếng chờ gửi (byte): điện thoại chậm thì bỏ phần cũ, không dồn bộ nhớ.
TRAN_DEM = 64 * 1024

# Mã đóng riêng (4000–4999): thẻ hiển thị lý do bằng tiếng Việt theo mã.
MA_BAN = 4409          # loa đang có điện thoại / kênh phát khác
MA_LOI_MO = 4400       # không mở được phiên song công
MA_PHIEN_DONG = 4001   # phiên song công đã đóng (hết giờ, tắt mic…)


def _tim_coordinator(hass: HomeAssistant, entity_id: str):
    rec = er.async_get(hass).async_get(entity_id)
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    if entry is None or entry.domain != DOMAIN or getattr(entry, "runtime_data", None) is None:
        return None
    return entry.runtime_data


class DamThoaiWsView(HomeAssistantView):
    url = "/api/r1_speaker/dam_thoai/{entity_id}/ws"
    name = "api:r1_speaker:dam_thoai_ws"
    requires_auth = True        # đường dẫn đã ký (``auth/sign_path``) hoặc token HA

    async def get(self, request: web.Request, entity_id: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _tim_coordinator(hass, entity_id)
        if coordinator is None:
            return web.Response(status=404, text="không phải thực thể của r1_speaker")
        duplex = coordinator.duplex
        ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=1 << 16)
        await ws.prepare(request)

        if duplex.downlink_busy:
            await ws.send_json({"loi": "Loa đang có kênh phát khác (điện thoại khác hoặc POST /duplex)."})
            await ws.close(code=MA_BAN)
            return ws
        tu_mo = False
        try:
            if not duplex.active:
                await duplex.async_start()
                tu_mo = True
        except (R1SessionBusy, HomeAssistantError) as exc:
            await ws.send_json({"loi": str(exc)})
            await ws.close(code=MA_LOI_MO)
            return ws

        duplex.downlink_busy = True
        dem = bytearray()

        def tu_loa(khuc: bytes) -> None:
            dem.extend(khuc)
            if len(dem) > TRAN_DEM:
                del dem[: len(dem) - TRAN_DEM]       # điện thoại chậm: bỏ phần cũ nhất

        huy_nghe = duplex.add_audio_listener(tu_loa)

        def phien_doi() -> None:
            if not duplex.active and not ws.closed:
                hass.async_create_task(ws.close(code=MA_PHIEN_DONG))

        huy_doi = duplex.add_listener(phien_doi)

        async def gui_di() -> None:
            while not ws.closed:
                await asyncio.sleep(GOP_S)
                if dem:
                    khuc = bytes(dem)
                    dem.clear()
                    await ws.send_bytes(khuc)

        gui = hass.async_create_background_task(gui_di(), "r1_speaker dam thoai ws gui")
        ly_do = "dong_dien_thoai"
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    if msg.data and len(msg.data) % 2 == 0 and duplex.active:
                        duplex.feed_playback(msg.data)
                elif msg.type == WSMsgType.TEXT:
                    if msg.data == "noi":                  # điện thoại bắt đầu GIỮ nút nói
                        duplex.phone_noi(True)
                    elif msg.data == "het":                # thả nút
                        duplex.phone_noi(False)
                elif msg.type == WSMsgType.ERROR:
                    ly_do = "mat_ket_noi"
                    break
        finally:
            gui.cancel()
            with contextlib.suppress(asyncio.CancelledError, ConnectionError):
                await gui
            duplex.phone_noi(False)
            huy_nghe()
            huy_doi()
            duplex.downlink_busy = False
            if tu_mo and not duplex.luon:
                duplex.end(ly_do)
        return ws
