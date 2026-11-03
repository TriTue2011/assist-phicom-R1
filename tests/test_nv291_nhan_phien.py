"""NV291 — lỗi «loa đang bận» nêu AI đang giữ phiên (không chỉ loại phiên).

Nhãn đến từ CẤU TRÚC kết nối: tên máy khách khai báo khi mở (``?nhan=`` của WebSocket / POST, do thẻ gửi), người dùng HA của kết nối
hoặc của cuộc gọi dịch vụ, và loại phiên khi chính loa / từ gọi mở. Không đoán theo IP, không danh sách tên. Nhãn là dữ liệu cá nhân:
cắt độ dài, bỏ ký tự điều khiển, không vào nhật ký. Mở phiên đi qua cổng thật (WebSocket thật, dịch vụ thật, ``R1Talk`` công khai)."""

import asyncio
import json
import logging

import pytest
from aiohttp import WSMsgType
from homeassistant.core import Context

from custom_components.r1_speaker import const
from custom_components.r1_speaker.dam_thoai import NHAN_KHONG_RO, NHAN_TOI_DA, R1SessionBusy, lam_sach_nhan

from .test_dam_thoai import MemorySource, make_talk
from .test_dam_thoai import _nhanh  # noqa: F401 — tăng tốc đồng hồ giữ nhạc
from .test_dam_thoai_ws import URL
from .test_den_nhac import _noi_apk, _them_co_dau_nhan
from .test_mic_server import cho


# ── Cổng R1Talk (công khai) ─────────────────────────────────────────────────────

async def test_phien_thu_hai_nhan_loi_co_nhan_cua_phien_thu_nhat(hass, caplog):
    caplog.set_level(logging.DEBUG)
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    su_kien = []
    hass.bus.async_listen(const.EVENT_SESSION_REFUSED, su_kien.append)
    s1 = await talk.async_start("button", "Điện thoại của Lan")
    with pytest.raises(R1SessionBusy) as exc:
        await talk.async_start("button", "iPad bếp")
    msg = str(exc.value)
    assert msg.startswith("Loa R1 đang được dùng bởi Điện thoại của Lan (phiên button")      # mở đầu bằng điều người dùng cần biết
    assert "iPad bếp" in msg and "bị từ chối" in msg
    await hass.async_block_till_done()
    assert su_kien[0].data["ban_boi"] == "Điện thoại của Lan" and su_kien[0].data["bi_tu_choi_boi"] == "iPad bếp"
    thuoc_tinh = talk.as_attributes()
    assert thuoc_tinh["phien_dang_giu_boi"] == "Điện thoại của Lan"
    assert thuoc_tinh["tu_choi_gan_nhat_nhan"] == {"ban_boi": "Điện thoại của Lan", "bi_tu_choi_boi": "iPad bếp"}
    assert "Lan" not in caplog.text and "iPad" not in caplog.text                              # nhãn không ra nhật ký
    assert "bị từ chối" in caplog.text
    talk.end(s1, "xong")
    assert talk.as_attributes()["phien_dang_giu_boi"] is None


async def test_khong_truyen_nhan_thi_noi_khong_xac_dinh_khong_bia(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    s1 = await talk.async_start("button")                       # cuộc gọi cũ không truyền nhãn
    with pytest.raises(R1SessionBusy) as exc:
        await talk.async_start("button")
    assert NHAN_KHONG_RO in str(exc.value) and str(exc.value).count(NHAN_KHONG_RO) == 2
    talk.end(s1, "xong")
    nha = talk.claim("bo_dam")
    with pytest.raises(R1SessionBusy, match="một thiết bị không xác định"):
        await talk.async_start("button")
    nha()


async def test_phien_do_loa_hoac_tu_goi_mo_thi_noi_dung_nguon(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    s1 = await talk.async_start("wake")                          # loa tự mở
    with pytest.raises(R1SessionBusy, match="đang được dùng bởi chính loa"):
        await talk.async_start("button", "Lan")
    talk.end(s1, "xong")
    s2 = await talk.async_start("assist")                        # Assist bằng từ gọi
    with pytest.raises(R1SessionBusy, match="đang được dùng bởi từ gọi"):
        await talk.async_start("button", "Lan")
    talk.end(s2, "xong")


@pytest.mark.parametrize("tho, mong", [
    ("  Điện  thoại\tcủa\nLan ", "Điện thoại của Lan"),
    ("Lan\x00\x07\x1b[31m", "Lan[31m"),                     # ký tự điều khiển bị bỏ
    ("a‮b​c", "abc"),                              # ký tự định dạng / đảo chiều bị bỏ
    ("x" * 200, "x" * NHAN_TOI_DA),
    ("   ", None), ("", None), (None, None), (123, None), (["a"], None),
])
def test_lam_sach_nhan(tho, mong):
    assert lam_sach_nhan(tho) == mong


async def test_nhan_xau_khong_lot_vao_cau_loi(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    s1 = await talk.async_start("button", "Lan\x00\x1b" + "y" * 300)
    with pytest.raises(R1SessionBusy) as exc:
        await talk.async_start("button", "ai\x07đó")
    msg = str(exc.value)
    assert "\x00" not in msg and "\x1b" not in msg and "\x07" not in msg and "y" * (NHAN_TOI_DA + 1) not in msg and "aiđó" in msg
    talk.end(s1, "xong")


# ── WebSocket thật: hai điện thoại ──────────────────────────────────────────────

async def test_hai_dien_thoai_cai_thu_hai_nghe_ten_cai_thu_nhat(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    client = await hass_client()
    ws1 = await client.ws_connect(URL + "?nhan=Điện thoại của Lan")
    await cho(lambda: d.downlink_busy)
    ws2 = await client.ws_connect(URL + "?nhan=iPad bếp")
    msg = await ws2.receive(timeout=2)
    loi = json.loads(msg.data)["loi"]
    assert msg.type == WSMsgType.TEXT and loi.startswith("Loa R1 đang được dùng bởi Điện thoại của Lan") and "iPad bếp" in loi
    assert (await ws2.receive(timeout=2)).type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED)
    assert ws2.close_code == 4409 and d.active
    st = hass.states.get("sensor.r1_trang_thai_mic")
    assert st.attributes["tu_choi_gan_nhat_nhan"]["ban_boi"] == "Điện thoại của Lan"
    await ws1.close()
    await cho(lambda: not d.downlink_busy and d.downlink_nhan is None)
    writer.close()


async def test_khong_khai_nhan_thi_dung_nguoi_dung_ha_cua_ket_noi(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    ten = next(u.name for u in await hass.auth.async_get_users() if not u.system_generated and u.name)
    client = await hass_client()
    ws1 = await client.ws_connect(URL)
    await cho(lambda: d.downlink_busy)
    ws2 = await client.ws_connect(URL)
    loi = json.loads((await ws2.receive(timeout=2)).data)["loi"]
    assert f"đang được dùng bởi {ten}" in loi and f"của {ten} bị từ chối" in loi            # nhãn lấy từ người dùng HA của kết nối
    await ws1.close()
    writer.close()


async def test_post_duplex_co_khoa_khong_nhan_thi_khong_xac_dinh(hass, r1, hass_client_no_auth):
    from custom_components.r1_speaker.const import CONF_INTERCOM_KEY
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    d.downlink_busy = True                                       # có bên khác đang bơm xuống loa
    d.downlink_nhan = "Máy go2rtc phòng khách"
    client = await hass_client_no_auth()
    r = await client.post(f"/api/r1_speaker/duplex/{e.entry_id}?k={e.data[CONF_INTERCOM_KEY]}", data=b"")
    assert r.status == 409 and "đang được dùng bởi Máy go2rtc phòng khách" in await r.text()
    d.downlink_busy, d.downlink_nhan = False, None
    writer.close()


# ── Dịch vụ HA: người dùng của cuộc gọi ─────────────────────────────────────────

async def test_dich_vu_start_duplex_mang_ten_nguoi_dung_cua_cuoc_goi(hass, r1, hass_client):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    await hass_client()                                          # tạo người dùng thử nghiệm
    nguoi = next(u for u in await hass.auth.async_get_users() if not u.system_generated and u.name)
    await hass.services.async_call("r1_speaker", "start_duplex", {"entity_id": "sensor.r1_trang_thai_mic"}, blocking=True,
                                   context=Context(user_id=nguoi.id))
    assert d.active
    with pytest.raises(R1SessionBusy) as exc:                    # phiên đàm thoại khác (nút) xin trong lúc phiên song công còn mở
        await e.runtime_data.talk.async_start("button", "iPad bếp")
    assert f"đang được dùng bởi {nguoi.name}" in str(exc.value) and "iPad bếp" in str(exc.value)
    d.end("nguoi_dung_ket_thuc")
    writer.close()
