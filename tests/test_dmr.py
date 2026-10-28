"""Lõi DLNA tự điều khiển (``dmr.R1Dmr``): tìm renderer bằng SSDP unicast rồi nói UPnP AV với renderer giả ở 127.0.0.1."""

import asyncio
from unittest import mock

import pytest

from custom_components.r1_speaker import dmr as dmr_mod
from custom_components.r1_speaker.dmr import R1Dmr, R1DmrError, tim_mo_ta

from .fake_dmr import FakeDMR


class Ssdp(asyncio.DatagramProtocol):
    """Máy chủ SSDP giả: trả LOCATION đã định cho mọi M-SEARCH."""

    def __init__(self, location):
        self.location, self.nhan = location, []

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.nhan.append(data.decode())
        self.transport.sendto(f"HTTP/1.1 200 OK\r\nLOCATION: {self.location}\r\nST: x\r\n\r\n".encode(), addr)


async def _ssdp(location):
    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(
        lambda: Ssdp(location), local_addr=("127.0.0.1", 0))
    return transport, proto, transport.get_extra_info("sockname")[1]


async def test_tim_mo_ta_tra_dung_dia_chi_cua_chinh_loa():
    transport, proto, cong = await _ssdp("http://127.0.0.1:1590/")
    try:
        assert await tim_mo_ta("127.0.0.1", cong=cong, cho=1.0) == "http://127.0.0.1:1590/"
        assert "MediaRenderer:1" in proto.nhan[0] and "ssdp:discover" in proto.nhan[0]
    finally:
        transport.close()


async def test_tim_mo_ta_tu_choi_dia_chi_cua_thiet_bi_khac():
    """Thiết bị lạ trong mạng không được dẫn ta tới một địa chỉ khác loa (chống giả mạo LOCATION)."""
    transport, _, cong = await _ssdp("http://192.0.2.50:1590/")
    try:
        assert await tim_mo_ta("127.0.0.1", cong=cong, cho=0.4) is None
    finally:
        transport.close()


async def test_tim_mo_ta_loa_khong_tra_loi_thi_none_va_dong_o_cam():
    # cổng không ai nghe: không treo, trả None sau hạn chờ
    assert await tim_mo_ta("127.0.0.1", cong=9, cho=0.3) is None


@pytest.fixture
async def fake():
    d = FakeDMR(lambda: True)
    await d.start()
    yield d
    await d.stop()


@pytest.fixture
def dmr(hass, fake):
    with mock.patch.object(dmr_mod, "tim_mo_ta", new=mock.AsyncMock(return_value=fake.location)):
        yield R1Dmr(hass, "127.0.0.1")


async def test_phat_dat_uri_roi_play_va_doc_duoc_trang_thai(dmr, fake):
    await dmr.async_phat("http://ha/a.mp3", "Bài thử")
    names = [n for n, _ in fake.actions]
    assert names.index("SetAVTransportURI") < names.index("Play")
    assert fake.called("SetAVTransportURI")[0]["CurrentURI"] == "http://ha/a.mp3"
    tt = await dmr.async_doc()
    assert tt.state == "playing" and tt.duration == 180 and tt.position == 5 and tt.uri == "http://ha/a.mp3"


async def test_tam_dung_tiep_dung(dmr, fake):
    await dmr.async_phat("http://ha/a.mp3", "x")
    await dmr.async_tam_dung()
    assert (await dmr.async_doc()).state == "paused"
    await dmr.async_tiep()
    assert (await dmr.async_doc()).state == "playing"
    await dmr.async_dung()
    assert (await dmr.async_doc()).state == "idle"


async def test_renderer_bao_loi_truyen_tai_thi_loi_true(dmr, fake):
    await dmr.async_phat("http://ha/a.mp3", "x")
    fake.transport_state, fake.transport_status = "STOPPED", "ERROR_OCCURRED"
    tt = await dmr.async_doc()
    assert tt.state == "idle" and tt.loi is True


async def test_renderer_chet_thi_bao_loi_va_tim_lai_o_lan_sau(hass, fake):
    tim = mock.AsyncMock(return_value=fake.location)
    with mock.patch.object(dmr_mod, "tim_mo_ta", new=tim):
        d = R1Dmr(hass, "127.0.0.1")
        await d.async_phat("http://ha/a.mp3", "x")
        assert d.da_noi and tim.await_count == 1
        fake.enabled = lambda: False                       # loa tắt DLNA / khởi động lại
        with pytest.raises(R1DmrError):
            await d.async_doc()
        assert not d.da_noi                                # bỏ thiết bị cũ: cổng có thể đã đổi
        fake.enabled = lambda: True
        await d.async_doc()
        assert tim.await_count == 2                        # tìm lại bằng SSDP


async def test_khong_tra_loi_ssdp_thi_bao_loi_ro(hass):
    with mock.patch.object(dmr_mod, "tim_mo_ta", new=mock.AsyncMock(return_value=None)):
        d = R1Dmr(hass, "127.0.0.1")
        with pytest.raises(R1DmrError, match="SSDP"):
            await d.async_doc()
        with pytest.raises(R1DmrError, match="chưa lên"):
            await d.async_san_sang(0.3)
