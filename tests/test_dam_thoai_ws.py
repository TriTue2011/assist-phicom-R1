"""Đàm thoại bằng micro điện thoại: WebSocket ``/api/r1_speaker/dam_thoai/<thực thể>/ws`` (cách bộ đàm camera c2a).

APK loa giả nối thật vào đầu nhận mic; điện thoại giả là ứng dụng khách WebSocket đã đăng nhập HA."""

import asyncio
import json
import struct

from aiohttp import WSMsgType

from .test_den_nhac import DAM_THOAI, _goi, _khung_xuong, _noi_apk, _st, _them_co_dau_nhan
from .test_mic_server import cho, khung
from .test_song_cong import VadGia

THUC_THE = "sensor.r1_trang_thai_mic"
URL = f"/api/r1_speaker/dam_thoai/{THUC_THE}/ws"


def _pcm(gia_tri: int, so_mau: int) -> bytes:
    return struct.pack("<h", gia_tri) * so_mau


async def _doc_tieng_den(reader, so_byte: int) -> bytes:
    """Đọc các khung PCM APK nhận từ HA cho tới khi đủ ``so_byte``."""
    tong = b""
    while len(tong) < so_byte:
        tong += await _khung_xuong(reader)
    return tong


async def test_phai_dang_nhap_moi_vao_duoc(hass, r1, hass_client_no_auth):
    await _them_co_dau_nhan(hass, r1)
    client = await hass_client_no_auth()
    assert (await client.get(URL)).status == 401
    assert (await client.get("/api/r1_speaker/dam_thoai/sensor.khong_phai_cua_r1/ws")).status in (401, 404)


async def test_thuc_the_khong_phai_cua_r1_la_404(hass, r1, hass_client):
    await _them_co_dau_nhan(hass, r1)
    client = await hass_client()
    assert (await client.get("/api/r1_speaker/dam_thoai/sensor.khong_phai_cua_r1/ws")).status == 404


async def test_mic_dien_thoai_ra_loa_va_dong_ws_thi_dong_phien(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    ws = await (await hass_client()).ws_connect(URL)
    await cho(lambda: d.active)
    assert d.downlink_busy and not d.luon
    tieng = _pcm(1234, 400) + _pcm(-900, 400)              # 1600 byte PCM16 = 0,05 giây
    await ws.send_bytes(tieng)
    assert await asyncio.wait_for(_doc_tieng_den(reader, len(tieng)), 3) == tieng   # ra loa nguyên vẹn
    await ws.send_str("het")                                # thôi nói: chỉ ghi nhận, phiên vẫn mở để nghe lại
    await asyncio.sleep(0.1)
    assert d.active
    await ws.close()
    await cho(lambda: not d.active)                         # đóng kết nối = đóng phiên do chính nó mở
    assert not d.downlink_busy
    writer.close()


async def test_tieng_loa_ve_dien_thoai(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    d._vad_factory = VadGia             # VAD giả: mẫu to = tiếng người (microVAD thật không nhận âm đơn giản)
    reader, writer = await _noi_apk(e, port)
    ws = await (await hass_client()).ws_connect(URL)
    await cho(lambda: d.active)
    for _ in range(60):                                     # 0,6 giây tiếng loa to
        writer.write(khung(_pcm(6000, 160)))
    await writer.drain()
    nhan = b""
    han = asyncio.get_running_loop().time() + 3
    while len(nhan) < 3200 and asyncio.get_running_loop().time() < han:
        msg = await ws.receive(timeout=1)
        if msg.type == WSMsgType.BINARY:
            nhan += msg.data
    assert len(nhan) >= 3200
    mau = struct.unpack(f"<{len(nhan) // 2}h", nhan[: len(nhan) // 2 * 2])
    assert max(abs(x) for x in mau) > 1000                  # đúng tiếng loa, không phải khung điều khiển
    await ws.close()
    writer.close()


async def test_giu_mo_bang_cong_tac_thi_dong_ws_khong_dong_phien(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    await _goi(hass, "switch", "turn_on", DAM_THOAI)        # «Bật mic luôn» trên HA
    assert d.active and d.luon
    ws = await (await hass_client()).ws_connect(URL)
    await ws.send_bytes(_pcm(500, 160))
    await asyncio.sleep(0.2)
    await ws.close()
    await asyncio.sleep(0.3)
    assert d.active and d.luon and not d.downlink_busy      # phiên do công tắc giữ: không bị đóng theo
    writer.close()


async def test_hai_dien_thoai_mot_loa_thi_cai_thu_hai_bi_tu_choi(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    client = await hass_client()
    ws1 = await client.ws_connect(URL)
    await cho(lambda: d.downlink_busy)
    ws2 = await client.ws_connect(URL)
    msg = await ws2.receive(timeout=2)
    assert msg.type == WSMsgType.TEXT and "kênh phát khác" in json.loads(msg.data)["loi"]
    assert (await ws2.receive(timeout=2)).type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED)
    assert ws2.close_code == 4409
    assert d.active                                          # kênh thứ nhất không bị ảnh hưởng
    await ws1.close()
    writer.close()


async def test_chua_co_loa_noi_thi_bao_loi_ro_rang(hass, r1, hass_client):
    await _them_co_dau_nhan(hass, r1)                        # APK chưa nối
    ws = await (await hass_client()).ws_connect(URL)
    msg = await ws.receive(timeout=2)
    assert msg.type == WSMsgType.TEXT and "kênh phát" in json.loads(msg.data)["loi"]
    await ws.receive(timeout=2)
    assert ws.close_code == 4400


async def test_phien_dong_tu_ben_ngoai_thi_dong_ws(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    ws = await (await hass_client()).ws_connect(URL)
    await cho(lambda: d.active)
    d.end("het_gio")                                        # hết giờ / tắt mic: phiên đóng
    msg = await ws.receive(timeout=3)
    assert msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED)
    assert ws.close_code == 4001
    writer.close()
