"""Nghe tiếng trong nhà qua mic loa (một chiều, chỉ quản trị viên)."""

import asyncio
import struct

from aiohttp import WSMsgType

from .test_den_nhac import _goi, _noi_apk, _them_co_dau_nhan
from .test_mic_server import cho, khung

URL = "/api/r1_speaker/nghe/sensor.r1_trang_thai_mic/ws"
TAT_MIC = "switch.r1_tat_mic"


def _pcm(v: int, n: int) -> bytes:
    return struct.pack("<h", v) * n


async def test_quan_tri_nghe_duoc_tieng_tu_mic_loa_khong_loc_vad(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    ws = await (await hass_client()).ws_connect(URL)
    await asyncio.sleep(0.1)
    for _ in range(40):
        writer.write(khung(_pcm(120, 160)))                  # tiếng RẤT nhỏ: VAD sẽ lọc, kênh nghe thì không
    await writer.drain()
    nhan = b""
    han = asyncio.get_running_loop().time() + 3
    while len(nhan) < 4000 and asyncio.get_running_loop().time() < han:
        msg = await ws.receive(timeout=1)
        if msg.type == WSMsgType.BINARY:
            nhan += msg.data
    assert len(nhan) >= 4000 and set(struct.unpack(f"<{len(nhan)//2}h", nhan[:len(nhan)//2*2])) == {120}
    assert not e.runtime_data.duplex.active                    # nghe KHÔNG mở phiên song công
    assert not e.runtime_data.duplex.downlink_busy             # và không chiếm kênh phát
    await ws.close()
    writer.close()


async def test_nguoi_dung_thuong_bi_cam(hass, r1, hass_client, hass_admin_user):
    await _them_co_dau_nhan(hass, r1)
    hass_admin_user.groups = []                                # hạ xuống người dùng thường
    client = await hass_client()
    assert (await client.get(URL)).status == 403


async def test_chua_ky_duong_dan_thi_401(hass, r1, hass_client_no_auth):
    await _them_co_dau_nhan(hass, r1)
    assert (await (await hass_client_no_auth()).get(URL)).status == 401


async def test_thuc_the_la_404(hass, r1, hass_client):
    await _them_co_dau_nhan(hass, r1)
    assert (await (await hass_client()).get("/api/r1_speaker/nghe/sensor.khac/ws")).status == 404


async def test_mic_tat_hoac_loa_chua_noi_thi_bao_ro_va_dong(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)                # APK chưa nối
    ws = await (await hass_client()).ws_connect(URL)
    m = await ws.receive(timeout=2)
    assert m.type == WSMsgType.TEXT and "không có gì để nghe" in m.json()["loi"]
    await ws.receive(timeout=2)
    assert ws.close_code == 4404


async def test_dang_nghe_ma_mic_bi_tat_thi_dong(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    ws = await (await hass_client()).ws_connect(URL)
    await asyncio.sleep(0.15)
    await _goi(hass, "switch", "turn_on", TAT_MIC)
    msgs = []
    for _ in range(6):
        m = await ws.receive(timeout=2)
        msgs.append(m.type)
        if m.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            break
    assert ws.close_code == 4405
    writer.close()
