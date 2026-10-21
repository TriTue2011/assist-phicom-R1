"""NV244 — đầu NHẬN mic (R1MicServer): client TCP giả trên localhost theo ĐÚNG khung
NV243 (mọi khung = 4 byte độ dài big-endian + payload; hello/end là JSON, PCM là PCM16
thô). KHÔNG chạm loa thật, KHÔNG cần HA đầy đủ cho phần giao thức (R1Mic + server trực
tiếp); trạng thái sensor kiểm qua ``R1Talk.mic_status`` với hass giả tối thiểu."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from custom_components.r1_speaker.const import MIC_GUI, MIC_NGHE, MIC_TAT
from custom_components.r1_speaker.dam_thoai import R1Talk
from custom_components.r1_speaker.mic import R1Mic
from custom_components.r1_speaker.mic_server import R1MicServer
from custom_components.r1_speaker.settings import mic_listen

KHOA = "khoa-test-khong-phai-khoa-that"
IP_LOA = "127.0.0.1"


def khung(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


def khung_json(obj: dict) -> bytes:
    return khung(json.dumps(obj).encode())


def hello(khoa: str = KHOA) -> bytes:
    return khung_json({"type": "hello", "version": 1, "key": khoa})


def pcm(bat_dau: int, so_mau: int = 512) -> bytes:
    return b"".join((bat_dau + i).to_bytes(2, "little", signed=True)
                    for i in range(so_mau))


async def cho(fn, timeout: float = 3.0) -> None:
    """Chờ điều kiện đúng (poll ngắn), hết giờ thì AssertionError."""
    loop = asyncio.get_running_loop()
    han = loop.time() + timeout
    while loop.time() < han:
        if fn():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("hết giờ chờ điều kiện")


@pytest.fixture
async def dau_nhan():
    """(mic, server, cac_khuc_da_nhan) — server nghe cổng ephemeral, IP loa = 127.0.0.1."""
    mic = R1Mic(IP_LOA, 8765)
    khuc: list[bytes] = []
    mic.add_chunk_listener(khuc.append)
    server = R1MicServer(mic, 0, KHOA, IP_LOA)
    await server.start()
    yield mic, server, khuc
    await server.async_close()


async def noi(port: int):
    return await asyncio.open_connection("127.0.0.1", port)


async def test_hello_dung_khoa_pcm_toi_listener_va_end_ve_chua_ket_noi(dau_nhan):
    mic, server, khuc = dau_nhan
    assert server.listening and mic.listening
    assert server.state == "nghe"
    reader, writer = await noi(server.port)
    writer.write(hello())
    await writer.drain()
    await cho(lambda: server.receiving)
    assert mic.connected                      # trạng thái «đang nhận»
    mot, hai = pcm(100), pcm(5000)
    writer.write(khung(mot) + khung(hai))
    await writer.drain()
    await cho(lambda: len(khuc) == 2)
    assert khuc == [mot, hai]                 # nguyên vẹn tới listener của R1Mic
    writer.write(khung_json({"type": "end"}))
    await writer.drain()
    await cho(lambda: not server.receiving)
    assert not mic.connected                  # end → về chưa kết nối
    assert server.state == "nghe"             # vẫn đang nghe cho lần nối sau
    writer.close()
    await server.async_close()
    assert server.state == "tat" and not mic.listening


async def test_khoa_sai_dong_ngay(dau_nhan):
    mic, server, khuc = dau_nhan
    reader, writer = await noi(server.port)
    writer.write(hello("khoa-sai"))
    await writer.drain()
    assert await asyncio.wait_for(reader.read(), 3) == b""   # server đóng ngay
    assert not server.receiving and not mic.connected and khuc == []
    writer.close()


async def test_ip_khac_mic_host_dong_ngay():
    mic = R1Mic(IP_LOA, 8765)
    server = R1MicServer(mic, 0, KHOA, "192.0.2.55")   # IP loa cấu hình ≠ 127.0.0.1
    await server.start()
    try:
        reader, writer = await noi(server.port)
        assert await asyncio.wait_for(reader.read(), 3) == b""
        assert not server.receiving and not mic.connected
        writer.close()
    finally:
        await server.async_close()


async def test_mat_ket_noi_giua_chung_khong_sap_va_nhan_lai_duoc(dau_nhan):
    mic, server, khuc = dau_nhan
    reader, writer = await noi(server.port)
    writer.write(hello() + khung(pcm(7)))
    await writer.drain()
    await cho(lambda: len(khuc) == 1)
    writer.transport.abort()                  # đứt đột ngột, không khung end
    await cho(lambda: not server.receiving)
    assert not mic.connected and server.listening
    reader2, writer2 = await noi(server.port)  # loa nối lại được
    writer2.write(hello() + khung(pcm(9)))
    await writer2.drain()
    await cho(lambda: len(khuc) == 2)
    assert khuc[1] == pcm(9)
    writer2.close()


async def test_hai_luong_cung_luc_luong_hai_bi_tu_choi(dau_nhan):
    mic, server, khuc = dau_nhan
    _r1, w1 = await noi(server.port)
    w1.write(hello())
    await w1.drain()
    await cho(lambda: server.receiving)
    r2, w2 = await noi(server.port)
    w2.write(hello())
    await w2.drain()
    try:
        dong = await asyncio.wait_for(r2.read(), 3) == b""
    except ConnectionResetError:              # đóng khi còn hello chưa đọc → RST, vẫn là bị từ chối
        dong = True
    assert dong                               # luồng hai bị đóng ngay
    w1.write(khung(pcm(3)))                                   # luồng một vẫn chạy
    await w1.drain()
    await cho(lambda: len(khuc) == 1)
    w1.close()
    w2.close()


async def test_khong_khoa_hoac_khong_ip_thi_khong_mo_cong():
    mic = R1Mic(IP_LOA, 8765)
    for server in (R1MicServer(mic, 0, "", IP_LOA), R1MicServer(mic, 0, KHOA, "")):
        await server.start()
        assert not server.listening and server.state == "tat"
        await server.async_close()


async def test_giu_mic_nua_cong_bo_khung_den_tu_dau_nhan(dau_nhan):
    mic, server, khuc = dau_nhan
    _r, w = await noi(server.port)
    w.write(hello())
    await w.drain()
    await cho(lambda: server.receiving)
    nha = mic.hold()                          # bộ đàm đang phát ra loa → bỏ tiếng mic
    w.write(khung(pcm(1)))
    await w.drain()
    await asyncio.sleep(0.2)
    assert khuc == []
    nha()
    w.write(khung(pcm(2)))
    await w.drain()
    await cho(lambda: len(khuc) == 1)
    w.close()


def test_trang_thai_sensor_theo_dau_nhan():
    """sensor.r1_trang_thai_mic (qua R1Talk.mic_status): nghe → gui → nghe/tat."""
    mic = R1Mic(IP_LOA, 8765)
    talk = R1Talk(SimpleNamespace(), mic, None)
    assert talk.mic_status == MIC_TAT
    mic.note_listening(True)
    assert talk.mic_status == MIC_NGHE        # đang nghe (cổng mở, chưa có tiếng)
    assert talk.as_attributes()["dau_nhan_mic"] == "nghe"
    mic.note_inbound(True)
    assert talk.mic_status == MIC_GUI         # đang nhận tiếng
    assert talk.as_attributes()["dau_nhan_mic"] == "nhan"
    mic.note_inbound(False)
    assert talk.mic_status == MIC_NGHE        # loa ngắt → còn «nghe», không kẹt «gui»
    mic.note_listening(False)
    assert talk.mic_status == MIC_TAT


def test_cai_dat_mic_listen_doc_tu_options():
    entry = SimpleNamespace(
        data={}, options={"mic_listen_port": 19001, "mic_listen_key": "abc"})
    assert mic_listen(entry) == (19001, "abc")
    mac_dinh = SimpleNamespace(data={}, options={})
    port, khoa = mic_listen(mac_dinh)
    assert port > 0 and khoa == ""            # chưa đặt khoá → đầu nhận không mở


# ── Ca biên bổ sung (đóng gói R1): tắt mic giữa phiên, khung lẻ/rỗng, hello hỏng ────────

async def test_tat_mic_giua_phien_dong_ket_noi_va_tu_choi_noi_lai(dau_nhan):
    """switch.r1_tat_mic = ĐÓNG luồng: loa phải bị ngắt (không chỉ bỏ khung), nối lại bị từ chối
    cho tới khi bật mic; bật lại thì loa nối lại được."""
    mic, server, khuc = dau_nhan
    reader, writer = await noi(server.port)
    writer.write(hello() + khung(pcm(1)))
    await writer.drain()
    await cho(lambda: len(khuc) == 1)
    mic.set_muted(True)
    try:
        dong = await asyncio.wait_for(reader.read(), 3) == b""
    except ConnectionResetError:
        dong = True
    assert dong, "tắt mic mà HA vẫn giữ kết nối cho loa gửi tiếp"
    await cho(lambda: not server.receiving)
    r2, w2 = await noi(server.port)                   # đang tắt mic → từ chối
    w2.write(hello() + khung(pcm(2)))
    try:
        await w2.drain()
        dong2 = await asyncio.wait_for(r2.read(), 3) == b""
    except ConnectionError:
        dong2 = True
    assert dong2 and len(khuc) == 1
    w2.close()
    mic.set_muted(False)
    r3, w3 = await noi(server.port)
    w3.write(hello() + khung(pcm(3)))
    await w3.drain()
    await cho(lambda: len(khuc) == 2)
    assert khuc[1] == pcm(3)
    w3.close()


async def test_khung_rong_va_le_byte_khong_lam_lech_pcm(dau_nhan):
    """Khung rỗng bỏ qua; byte lẻ cuối khung được dồn sang khung sau → listener luôn nhận
    số byte chẵn, mẫu PCM16 không bị lệch."""
    mic, server, khuc = dau_nhan
    _r, w = await noi(server.port)
    w.write(hello() + khung(b"") + khung(b"\x01\x02\x03") + khung(b"\x04\x05"))
    await w.drain()
    await cho(lambda: len(khuc) == 2)
    assert khuc == [b"\x01\x02", b"\x03\x04"]
    assert all(len(k) % 2 == 0 for k in khuc)
    w.close()


async def test_hello_sai_phien_ban_hoac_khong_phai_json_dong_ngay(dau_nhan):
    mic, server, khuc = dau_nhan
    for bad in (khung_json({"type": "hello", "version": 2, "key": KHOA}),
                khung(b"day-khong-phai-json"),
                khung_json({"type": "end"})):
        reader, writer = await noi(server.port)
        writer.write(bad + khung(pcm(1)))
        await writer.drain()
        try:
            dong = await asyncio.wait_for(reader.read(), 3) == b""
        except ConnectionResetError:
            dong = True
        assert dong and not server.receiving
        writer.close()
    assert khuc == []


async def test_khung_qua_lon_dong_phien_nhung_may_chu_van_nghe(dau_nhan):
    mic, server, khuc = dau_nhan
    reader, writer = await noi(server.port)
    writer.write(hello() + (2 << 20).to_bytes(4, "big"))     # khai báo 2 MiB > trần 1 MiB
    await writer.drain()
    try:
        dong = await asyncio.wait_for(reader.read(), 3) == b""
    except ConnectionResetError:
        dong = True
    assert dong
    await cho(lambda: not server.receiving)
    assert server.listening
    r2, w2 = await noi(server.port)
    w2.write(hello() + khung(pcm(4)))
    await w2.drain()
    await cho(lambda: len(khuc) == 1)
    w2.close()
    writer.close()


async def test_hello_im_lang_het_gio_thi_dong(dau_nhan, monkeypatch):
    from custom_components.r1_speaker import mic_server
    monkeypatch.setattr(mic_server, "HELLO_TIMEOUT", 0.2)
    mic, server, khuc = dau_nhan
    reader, writer = await noi(server.port)                  # nối rồi im
    assert await asyncio.wait_for(reader.read(), 3) == b""
    assert not server.receiving
    writer.close()
