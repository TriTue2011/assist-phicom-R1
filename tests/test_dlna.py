"""Phát qua ``media_player.r1_loa`` → Set_DLNA_Open → renderer của loa (tự điều khiển, không cần ``dlna_dmr``). Renderer giả ở
127.0.0.1; SSDP được thay bằng hàm trả địa chỉ renderer giả khi nó đang «bật»."""

import asyncio
from unittest import mock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.r1_speaker import dmr as dmr_mod
from custom_components.r1_speaker import media_player as r1_mp

from .fake_dmr import FakeDMR
from .test_r1 import _them

URL = "http://stream.example/tts.mp3"
LOA = "media_player.r1_loa"


@pytest.fixture
async def dmr(r1):
    """Renderer giả, chỉ lên khi loa giả đã nhận Set_DLNA_Open(open=true)."""
    d = FakeDMR(lambda: any(m.get("open") is True for m in r1.commands("Set_DLNA_Open")))
    await d.start()

    async def ssdp(host, **kw):
        return d.location if d.enabled() else None

    with mock.patch.object(dmr_mod, "tim_mo_ta", new=ssdp):
        yield d
    await d.stop()


@pytest.fixture(autouse=True)
def _nhanh_hon():
    with mock.patch.object(r1_mp, "CHAM_NHAC", 0.05), mock.patch.object(r1_mp, "CHAM_TIN", 0.05):
        yield


async def _phat(hass, **extra):
    await hass.services.async_call(
        "media_player", "play_media",
        {"entity_id": LOA, "media_content_id": URL, "media_content_type": "music", **extra}, blocking=True)


async def _cho_state(hass, mong_doi, han=3.0):
    async with asyncio.timeout(han):
        while hass.states.get(LOA).state != mong_doi:
            await asyncio.sleep(0.02)


async def test_ten_thuc_the_theo_mau_camera(hass, r1):
    await _them(hass, r1)
    assert hass.states.get(LOA) is not None
    assert hass.states.get("media_player.phicomm_r1_loa") is None


async def test_dlna_tat_bat_roi_phat(hass, r1, dmr):
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass)
    assert [m["open"] for m in r1.commands("Set_DLNA_Open")] == [True]
    # đúng thứ tự: bật DLNA trước, rồi SetAVTransportURI với đúng URL, rồi Play
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL]
    assert len(dmr.called("Play")) == 1
    names = [n for n, _ in dmr.actions]
    assert names.index("SetAVTransportURI") < names.index("Play")
    assert hass.states.get(LOA).state == "playing"


async def test_dlna_dang_bat_khong_gui_lai_set_dlna_open(hass, r1, dmr):
    r1.state["dlna_open"] = True
    r1.received.append({"type": "Set_DLNA_Open", "open": True})  # renderer giả coi là đã bật
    await _them(hass, r1)
    n = len(r1.commands("Set_DLNA_Open"))
    await _phat(hass)
    assert len(r1.commands("Set_DLNA_Open")) == n
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL]


async def test_dlna_khong_len_het_gio_bao_loi(hass, r1, dmr):
    r1.state["dlna_open"] = False
    dmr.enabled = lambda: False  # loa nhận lệnh bật nhưng renderer không lên
    await _them(hass, r1)
    with mock.patch.object(r1_mp, "DLNA_READY_TIMEOUT", 0.6), pytest.raises(HomeAssistantError, match="chưa lên"):
        await _phat(hass)
    assert dmr.called("SetAVTransportURI") == []


async def test_nhac_youtube_di_qua_dlna_cua_loa(hass, r1, dmr):
    """Nhạc YouTube: tích hợp YouTube gọi ``media_player.play_media`` với ``stream_url`` http(s) và kiểu ``audio/*``. URL đó phải tới
    ``SetAVTransportURI`` của renderer rồi ``Play`` — KHÔNG đi cổng 8082 (AI box đã gỡ)."""
    yt = "http://ha.example:8123/api/tritue_youtube_player/proxy/TOKEN-GIA-123"
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": LOA, "media_content_id": yt, "media_content_type": "audio/mpeg"}, blocking=True)
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [yt]
    assert len(dmr.called("Play")) == 1
    assert [m["open"] for m in r1.commands("Set_DLNA_Open")] == [True]
    assert not hass.services.has_service("r1_speaker", "music_play")


async def test_trang_thai_tien_do_thoi_luong_hien_tren_thuc_the(hass, r1, dmr):
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass, extra={"title": "Bài thử"})
    st = hass.states.get(LOA)
    assert st.state == "playing" and st.attributes["media_title"] == "Bài thử"
    assert st.attributes["media_content_id"] == URL
    await _cho_state(hass, "playing")
    await asyncio.sleep(0.2)
    st = hass.states.get(LOA)
    assert st.attributes.get("media_duration") == 180 and 5 <= st.attributes.get("media_position") < 6   # ước trong khoảng nguyên giây đọc được
    assert "idle_reason" not in st.attributes


async def test_idle_reason_het_bai_dung_loi_va_bi_thay(hass, r1, dmr):
    """Loa khai vì sao idle: hết bài / người dùng dừng / lỗi (chủ máy 28/10/2026: phân biệt Stop với hết bài bằng tín hiệu thật)."""
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    # hết bài: renderer tự về STOPPED
    await _phat(hass)
    dmr.transport_state = "STOPPED"
    await _cho_state(hass, "idle")
    assert hass.states.get(LOA).attributes["idle_reason"] == "finished"
    # người dùng bấm dừng trong Home Assistant
    await _phat(hass)
    await hass.services.async_call("media_player", "media_stop", {"entity_id": LOA}, blocking=True)
    assert hass.states.get(LOA).state == "idle" and hass.states.get(LOA).attributes["idle_reason"] == "stopped"
    # lỗi phát: renderer báo ERROR_OCCURRED
    await _phat(hass)
    dmr.transport_state, dmr.transport_status = "STOPPED", "ERROR_OCCURRED"
    await _cho_state(hass, "idle")
    assert hass.states.get(LOA).attributes["idle_reason"] == "error"


async def test_tam_dung_va_phat_tiep_qua_dich_vu(hass, r1, dmr):
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass)
    await hass.services.async_call("media_player", "media_pause", {"entity_id": LOA}, blocking=True)
    assert hass.states.get(LOA).state == "paused"
    await hass.services.async_call("media_player", "media_play", {"entity_id": LOA}, blocking=True)
    assert hass.states.get(LOA).state == "playing"


async def test_khong_hoi_nen_khi_idle_hoac_tam_dung(hass, r1, dmr):
    """Quy tắc tài nguyên: vòng hỏi lại chỉ chạy khi đang phát; dừng rồi thì im."""
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass)
    await hass.services.async_call("media_player", "media_stop", {"entity_id": LOA}, blocking=True)
    cho = len(dmr.called("GetTransportInfo"))
    await asyncio.sleep(0.4)                                        # nhiều chu kỳ 0,05 giây
    assert len(dmr.called("GetTransportInfo")) == cho


async def test_phat_lai_sau_khi_dung_van_hoi_lai_trang_thai(hass, r1, dmr):
    """Bẫy: huỷ vòng hỏi khi dừng mà giữ tham chiếu → lần phát sau không có vòng hỏi, thẻ đứng ở «đang phát» mãi."""
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass)
    await hass.services.async_call("media_player", "media_stop", {"entity_id": LOA}, blocking=True)
    await _phat(hass)
    dmr.transport_state = "STOPPED"                                 # hết bài lần hai
    await _cho_state(hass, "idle")
    assert hass.states.get(LOA).attributes["idle_reason"] == "finished"


async def test_bat_lai_vong_hoi_ngay_sau_khi_huy_khong_cho_tac_vu_cu_xong(hass, r1, dmr):
    """Tái hiện đúng chuỗi không có khoảng chờ: dừng (huỷ vòng hỏi) rồi phát lại ngay. Tác vụ đã huỷ chưa «xong» cho tới vòng lặp
    kế; vòng hỏi mới vẫn phải được bật (trước đây giữ tham chiếu cũ nên không bao giờ bật)."""
    from homeassistant.components.media_player import DATA_COMPONENT

    from custom_components.r1_speaker.dmr import TrangThaiDmr

    r1.state["dlna_open"] = False
    await _them(hass, r1)
    ent = hass.data[DATA_COMPONENT].get_entity(LOA)
    ent._ap_dung(TrangThaiDmr(state="playing"))
    ent._bat_dau_cham()
    cu = ent._cham
    ent._ap_dung(TrangThaiDmr(state="idle"))               # huỷ vòng hỏi
    ent._ap_dung(TrangThaiDmr(state="playing"))
    ent._bat_dau_cham()                                    # phát lại ngay, chưa có lượt chờ nào xen vào
    assert ent._cham is not cu and ent._cham.cancelling() == 0
    ent._huy_cham()


async def test_stop_renderer_bo_qua_lenh_dau_thi_tu_gui_lai(hass, r1, dmr):
    """Chủ máy 28/10/2026: «Stop không được ngay, phải stop lần 2, 2–3 lần». Renderer bỏ qua Stop khi đang nạp luồng: thực thể phải tự gửi lại."""
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass)
    so_stop = {"n": 0}
    goc = dmr._ctrl_handler

    def bo_qua_hai_lan_dau(svc):
        h = goc(svc)

        async def handler(request):
            if request.headers.get("SOAPAction", "").strip('"').endswith("#Stop"):
                so_stop["n"] += 1
                if so_stop["n"] <= 2:                                  # nhận nhưng KHÔNG dừng (vẫn PLAYING)
                    return await h_phat_dung_yen(request)
            return await h(request)
        return handler

    async def h_phat_dung_yen(request):
        from aiohttp import web
        return web.Response(text=('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                                  's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:StopResponse '
                                  'xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:StopResponse></s:Body></s:Envelope>'),
                            content_type="text/xml")

    # chèn bộ xử lý lỗi vào các tuyến điều khiển của renderer giả
    for tuyen in dmr._runner.app.router.routes():
        if tuyen.method == "POST" and tuyen.resource.canonical.endswith("/avt/ctrl"):
            tuyen._handler = bo_qua_hai_lan_dau("AVT")
    with mock.patch.object(r1_mp, "STOP_CHO_XAC_NHAN", 0.3):
        await hass.services.async_call("media_player", "media_stop", {"entity_id": LOA}, blocking=True)
    assert so_stop["n"] == 3, "phải tự gửi lại Stop tới khi renderer dừng"
    assert hass.states.get(LOA).state == "idle"


async def test_hoi_trang_thai_hong_thoang_qua_khong_bao_da_dung(hass, r1, dmr):
    """«Đang phát lại dừng» (chủ máy 28/10/2026): loa R1 yếu trả lời trễ một lần thì thực thể báo «lỗi, đã dừng» dù nhạc vẫn chạy. Phải hỏng 3 lần
    LIÊN TIẾP mới coi là lỗi; một lần hỏng rồi hỏi lại được thì vẫn «đang phát», không có idle_reason."""
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _phat(hass)
    ent = hass.data[__import__("homeassistant.components.media_player", fromlist=["DATA_COMPONENT"]).DATA_COMPONENT].get_entity(LOA)
    hien = dmr.enabled
    dmr.enabled = lambda: False                                    # renderer không trả lời
    await ent._doc()
    await ent._doc()
    assert hass.states.get(LOA).state == "playing" and "idle_reason" not in hass.states.get(LOA).attributes
    dmr.enabled = hien                                             # hồi lại trước lần hỏng thứ ba
    await ent._doc()
    assert ent._loi_doc == 0 and hass.states.get(LOA).state == "playing"
    dmr.enabled = lambda: False                                    # hỏng liên tiếp đủ 3 lần thì mới báo lỗi
    for _ in range(3):
        await ent._doc()
    assert hass.states.get(LOA).state == "idle" and hass.states.get(LOA).attributes["idle_reason"] == "error"
