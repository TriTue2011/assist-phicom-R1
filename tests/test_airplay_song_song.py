"""``media_player.r1_loa`` với hai đường phát DLNA và AirPlay «song song bù trừ nhau» (chủ máy 29/10/2026).

Loa DLNA giả (``FakeDMR``) và loa AirPlay giả (``FakeRaop``) cùng ở 127.0.0.1; nguồn tiếng là bộ phát giả thay cho ffmpeg
(``tao_nguon`` bị thay) nên không cần ffmpeg. Mỗi test khẳng định cả HAI phía: đường được chọn có phát, đường kia không bị đụng."""

import array
import asyncio
import socket
from unittest import mock

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import airplay as ap_mod
from custom_components.r1_speaker import dmr as dmr_mod
from custom_components.r1_speaker import media_player as r1_mp
from custom_components.r1_speaker.const import DOMAIN

from .fake_dmr import FakeDMR
from .fake_raop import FakeRaop

URL = "http://stream.example/bai.mp3"
URL2 = "http://stream.example/bai2.mp3"
TIN = "http://stream.example/tin.mp3"
LOA = "media_player.r1_loa"


def pcm(so_goi: int) -> bytes:
    return array.array("h", [1] * (ap_mod.KHUNG_MOI_GOI * 2 * so_goi)).tobytes()


class Nguon:
    """Thay ``tao_nguon``: ghi lại (url, bắt đầu) và trả bộ phát giả; số gói theo từng URL (mặc định 400 ≈ 3,2 giây)."""

    def __init__(self):
        self.goi: list[tuple[str, float]] = []
        self.so_goi = {}
        self.hong: set[str] = set()

    def __call__(self, url, bat_dau=0.0, ffmpeg=None):
        self.goi.append((url, bat_dau))

        async def gen():
            if url in self.hong:
                raise ap_mod.LoiAirPlay("ffmpeg thoát mã 1 (giả)")
            yield pcm(self.so_goi.get(url, 400))
        return gen


@pytest.fixture
async def dmr(r1):
    d = FakeDMR(lambda: any(m.get("open") is True for m in r1.commands("Set_DLNA_Open")))
    await d.start()

    async def ssdp(host, **kw):
        return d.location if d.enabled() else None

    with mock.patch.object(dmr_mod, "tim_mo_ta", new=ssdp):
        yield d
    await d.stop()


@pytest.fixture
async def raop():
    f = FakeRaop(do_tre=2205)
    await f.start()
    yield f
    await f.stop()


@pytest.fixture
def nguon():
    n = Nguon()
    with mock.patch.object(r1_mp, "tao_nguon", new=n):
        yield n


@pytest.fixture(autouse=True)
def _nhanh_hon():
    with mock.patch.object(r1_mp, "CHAM_NHAC", 0.05), mock.patch.object(r1_mp, "CHAM_TIN", 0.05):
        yield


async def them(hass, r1, raop, che_do, *, dlna_san=False):
    if not dlna_san:
        r1.state["dlna_open"] = False                              # renderer giả chỉ lên sau khi loa nhận Set_DLNA_Open
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port}, unique_id=f"127.0.0.1:{r1.port}",
                        options={"duong_phat": che_do, "airplay_port": raop.port})
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


def thuc_the(hass):
    return hass.data["entity_components"]["media_player"].get_entity(LOA)


async def phat(hass, url=URL, **extra):
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": LOA, "media_content_id": url, "media_content_type": "music", **extra}, blocking=True)


async def dich_vu(hass, ten):
    await hass.services.async_call("media_player", ten, {"entity_id": LOA}, blocking=True)


async def cho_state(hass, mong_doi, han=5.0):
    async with asyncio.timeout(han):
        while hass.states.get(LOA).state != mong_doi:
            await asyncio.sleep(0.02)


def thuoc_tinh(hass):
    return hass.states.get(LOA).attributes


# ── mặc định: hành vi cũ, AirPlay không bị đụng ─────────────────────────────

async def test_mac_dinh_chi_dlna_khong_dung_airplay(hass, r1, dmr, raop, nguon):
    r1.state["dlna_open"] = False
    await them(hass, r1, raop, "dlna")
    await phat(hass)
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL] and len(dmr.called("Play")) == 1
    assert raop.yeu_cau == [] and nguon.goi == [] and r1.commands("Set_AirPlay_Open") == []
    assert thuoc_tinh(hass)["duong_phat"] == "dlna"


async def test_tuy_chon_la_roi_ve_mac_dinh(hass, r1, raop):
    from custom_components.r1_speaker import settings
    e = MockConfigEntry(domain=DOMAIN, data={"host": "x"}, options={"duong_phat": "khac", "airplay_port": "abc"})
    assert settings.duong_phat(e) == "dlna" and settings.airplay_port(e) == 5012
    e2 = MockConfigEntry(domain=DOMAIN, data={"host": "x"}, options={"duong_phat": "airplay_truoc", "airplay_port": 99999})
    assert settings.duong_phat(e2) == "airplay_truoc" and settings.airplay_port(e2) == 5012


# ── chỉ AirPlay ──────────────────────────────────────────────────────────────

async def test_chi_airplay_phat_dung_tieng_bat_airplay_va_khong_dung_dlna(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = False
    await them(hass, r1, raop, "airplay")
    await phat(hass, extra={"title": "Bài thử"})
    assert [m["open"] for m in r1.commands("Set_AirPlay_Open")] == [True]
    assert raop.phuong_thuc()[:4] == ["OPTIONS", "ANNOUNCE", "SETUP", "RECORD"] and raop.audio
    assert nguon.goi == [(URL, 0.0)]
    assert dmr.actions == []                                      # DLNA không bị gọi lần nào
    st = hass.states.get(LOA)
    assert st.state == "playing" and st.attributes["duong_phat"] == "airplay"
    assert st.attributes["media_title"] == "Bài thử" and st.attributes["media_content_id"] == URL
    assert "idle_reason" not in st.attributes
    await dich_vu(hass, "media_stop")


async def test_chi_airplay_hong_thi_bao_loi_goc_va_khong_thu_dlna(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    nguon.hong.add(URL)
    await them(hass, r1, raop, "airplay")
    with pytest.raises(HomeAssistantError, match="ffmpeg thoát mã 1"):
        await phat(hass)
    assert dmr.actions == [] and hass.states.get(LOA).state == "idle"


# ── DLNA trước, AirPlay bù ───────────────────────────────────────────────────

async def test_dlna_tu_choi_lenh_thi_airplay_phat(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    dmr.tu_choi.add("SetAVTransportURI")
    await them(hass, r1, raop, "dlna_truoc")
    await phat(hass)
    names = [n for n, _ in dmr.actions]
    assert "SetAVTransportURI" in names and "Play" not in names   # renderer đang idle, lệnh bị từ chối: không có gì để dừng
    assert raop.audio and hass.states.get(LOA).state == "playing" and thuoc_tinh(hass)["duong_phat"] == "airplay"
    await dich_vu(hass, "media_stop")


async def test_dlna_dang_phat_bai_cu_lenh_moi_bi_tu_choi_thi_dung_dlna_truoc_khi_airplay(hass, r1, dmr, raop, nguon):
    """Bài cũ vẫn đang phát bằng DLNA; bài mới bị từ chối. Nếu AirPlay bắt đầu mà bài cũ chưa dừng thì loa phát hai nơi."""
    r1.state["airplay_open"] = True
    await them(hass, r1, raop, "dlna_truoc")
    await phat(hass)
    assert dmr.transport_state == "PLAYING"
    dmr.tu_choi.add("SetAVTransportURI")
    await phat(hass, URL2)
    assert dmr.transport_state == "STOPPED" and raop.audio
    assert thuoc_tinh(hass)["duong_phat"] == "airplay"
    await dich_vu(hass, "media_stop")


async def test_dlna_bao_loi_phat_thi_airplay_bu(hass, r1, dmr, raop, nguon):
    """Play thành công nhưng renderer báo ERROR_OCCURRED: tín hiệu chắc chắn thứ hai ngoài lỗi SOAP."""
    r1.state["airplay_open"] = True
    dmr.transport_status = "ERROR_OCCURRED"
    dmr.play_cham = True
    await them(hass, r1, raop, "dlna_truoc")
    await phat(hass)
    assert raop.audio and thuoc_tinh(hass)["duong_phat"] == "airplay"
    assert "Stop" in [n for n, _ in dmr.actions]
    await dich_vu(hass, "media_stop")


async def test_dlna_chi_cham_khong_bi_coi_la_hong(hass, r1, dmr, raop, nguon):
    """Renderer nhận lệnh nhưng còn idle (nạp luồng chậm), KHÔNG báo lỗi: không được chuyển sang AirPlay (sẽ phát hai nơi)."""
    r1.state["airplay_open"] = True
    dmr.play_cham = True
    await them(hass, r1, raop, "dlna_truoc")
    with mock.patch.object(r1_mp, "CHAM_NHAC", 0.05):
        await phat(hass)
    assert raop.yeu_cau == [] and nguon.goi == []
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL]
    dmr.transport_state = "PLAYING"                               # rồi loa nạp xong và phát
    await thuc_the(hass).async_lam_moi()                          # idle thì không hỏi nền: đây là lần hỏi theo chu kỳ coordinator
    await cho_state(hass, "playing")
    assert thuoc_tinh(hass)["duong_phat"] == "dlna"


# ── AirPlay trước, DLNA bù ───────────────────────────────────────────────────

async def test_airplay_bi_loa_tu_choi_thi_dlna_bu(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    raop.tra_ma["ANNOUNCE"] = 453
    await them(hass, r1, raop, "airplay_truoc")
    await phat(hass)
    assert raop.audio == [] and "ANNOUNCE" in raop.phuong_thuc()
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL] and len(dmr.called("Play")) == 1
    assert hass.states.get(LOA).state == "playing" and thuoc_tinh(hass)["duong_phat"] == "dlna"


async def test_airplay_ffmpeg_hong_thi_dlna_bu(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    nguon.hong.add(URL)
    await them(hass, r1, raop, "airplay_truoc")
    await phat(hass)
    assert raop.audio == [] and len(dmr.called("Play")) == 1 and thuoc_tinh(hass)["duong_phat"] == "dlna"


async def test_airplay_qua_han_chua_co_tieng_thi_dlna_bu_va_phien_duoc_don(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True

    async def treo():
        await asyncio.sleep(30)
        yield b""

    nguon_treo = mock.Mock(side_effect=lambda url, bat_dau=0.0, ffmpeg=None: treo)
    await them(hass, r1, raop, "airplay_truoc")
    with mock.patch.object(r1_mp, "tao_nguon", new=nguon_treo), mock.patch.object(r1_mp, "AIRPLAY_BAT_DAU_TOI_DA", 0.4):
        await phat(hass)
    assert raop.audio == [] and len(dmr.called("Play")) == 1
    assert raop.phuong_thuc()[-1] == "TEARDOWN"                   # phiên chờ quá hạn đã đóng, không treo ở loa


async def test_ca_hai_hong_bao_loi_co_ten_ca_hai(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    dmr.tu_choi.add("SetAVTransportURI")
    raop.tra_ma["ANNOUNCE"] = 453
    await them(hass, r1, raop, "airplay_truoc")
    with pytest.raises(HomeAssistantError) as e:
        await phat(hass)
    assert "AirPlay:" in str(e.value) and "DLNA:" in str(e.value) and "Cả hai" in str(e.value)
    assert hass.states.get(LOA).state == "idle"


# ── trạng thái, điều khiển ───────────────────────────────────────────────────

async def test_het_bai_tren_airplay_idle_finished(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    nguon.so_goi[URL] = 30
    await them(hass, r1, raop, "airplay")
    await phat(hass)
    await cho_state(hass, "idle")
    a = thuoc_tinh(hass)
    assert a["idle_reason"] == "finished" and "duong_phat" not in a
    assert raop.phuong_thuc()[-1] == "TEARDOWN"


async def test_dung_tren_airplay_idle_stopped_va_ngat_tieng(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    await them(hass, r1, raop, "airplay")
    await phat(hass)
    await dich_vu(hass, "media_stop")
    assert hass.states.get(LOA).state == "idle" and thuoc_tinh(hass)["idle_reason"] == "stopped"
    assert raop.phuong_thuc()[-1] == "TEARDOWN"
    await asyncio.sleep(0.05)
    n = len(raop.audio)
    await asyncio.sleep(0.2)
    assert len(raop.audio) == n and dmr.actions == []


async def test_bai_moi_thay_bai_cu_tren_airplay(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    await them(hass, r1, raop, "airplay")
    await phat(hass)
    await phat(hass, URL2)
    assert raop.phuong_thuc().count("ANNOUNCE") == 2 and raop.phuong_thuc().count("TEARDOWN") >= 1
    assert [u for u, _ in nguon.goi] == [URL, URL2]
    st = hass.states.get(LOA)
    assert st.state == "playing" and st.attributes["media_content_id"] == URL2 and "idle_reason" not in st.attributes
    await dich_vu(hass, "media_stop")


async def test_tam_dung_va_tiep_tren_airplay(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    await them(hass, r1, raop, "airplay")
    await phat(hass)
    await dich_vu(hass, "media_pause")
    assert hass.states.get(LOA).state == "paused" and "FLUSH" in raop.phuong_thuc()
    await asyncio.sleep(0.1)
    n = len(raop.audio)
    await asyncio.sleep(0.2)
    assert len(raop.audio) == n                                   # tạm dừng thật: không gửi thêm gói
    await dich_vu(hass, "media_play")
    assert hass.states.get(LOA).state == "playing"
    await dich_vu(hass, "media_stop")


async def test_tua_tren_airplay_phat_lai_tu_vi_tri_do(hass, r1, dmr, raop, nguon):
    r1.state["airplay_open"] = True
    await them(hass, r1, raop, "airplay")
    await phat(hass)
    await hass.services.async_call("media_player", "media_seek", {"entity_id": LOA, "seek_position": 42.5}, blocking=True)
    assert nguon.goi == [(URL, 0.0), (URL, 42.5)]
    st = hass.states.get(LOA)
    assert st.state == "playing" and 42.5 <= st.attributes["media_position"] < 44
    await dich_vu(hass, "media_stop")


async def test_ket_qua_hoi_dlna_bi_bo_qua_khi_airplay_dang_phat(hass, r1, dmr, raop, nguon):
    """DLNA của loa đang STOPPED; nếu kết quả hỏi DLNA được ghi thì thực thể sẽ tụt về idle dù AirPlay đang ra tiếng."""
    r1.state["airplay_open"] = True
    r1.state["dlna_open"] = True
    r1.received.append({"type": "Set_DLNA_Open", "open": True})
    await them(hass, r1, raop, "airplay", dlna_san=True)
    await phat(hass)
    dmr.transport_state = "STOPPED"
    await thuc_the(hass).async_lam_moi()
    await asyncio.sleep(0.2)
    assert hass.states.get(LOA).state == "playing" and thuoc_tinh(hass)["duong_phat"] == "airplay"
    assert dmr.called("GetTransportInfo") == []                   # thậm chí không hỏi
    await dich_vu(hass, "media_stop")


async def test_dlna_bi_dung_khi_chuyen_sang_airplay_giua_bai(hass, r1, dmr, raop, nguon):
    """Đang phát bằng DLNA, người dùng đổi sang chế độ AirPlay rồi phát bài mới: DLNA phải được Stop (không phát hai nơi)."""
    r1.state["airplay_open"] = True
    e = await them(hass, r1, raop, "dlna")
    await phat(hass)
    assert dmr.transport_state == "PLAYING"
    hass.config_entries.async_update_entry(e, options={**e.options, "duong_phat": "airplay"})
    await phat(hass, URL2)
    assert dmr.transport_state == "STOPPED" and "Stop" in [n for n, _ in dmr.actions]
    assert raop.audio and thuoc_tinh(hass)["duong_phat"] == "airplay"
    await dich_vu(hass, "media_stop")


async def test_tin_bao_tren_airplay_tam_dung_nhac_roi_phat_lai(hass, r1, dmr, raop, nguon):
    """Báo tin (announce) khi nhạc đang chạy qua AirPlay: nhạc tạm dừng, tin phát hết, nhạc được đặt lại (giu_nhac)."""
    r1.state["airplay_open"] = True
    nguon.so_goi[TIN] = 20
    await them(hass, r1, raop, "airplay")
    await phat(hass)
    await phat(hass, TIN, announce=True)
    async with asyncio.timeout(10):
        while [u for u, _ in nguon.goi].count(URL) < 2:
            await asyncio.sleep(0.05)
    assert [u for u, _ in nguon.goi][:3] == [URL, TIN, URL]
    await dich_vu(hass, "media_stop")


async def test_loa_vua_bat_airplay_cong_len_cham_thi_thu_lai(hass, r1, dmr, nguon):
    """Loa vừa nhận Set_AirPlay_Open, cổng RAOP lên sau ~0,8 giây: phải thử lại chứ không bỏ cuộc ngay (rồi mới sang DLNA)."""
    with socket.socket() as k:
        k.bind(("127.0.0.1", 0))
        cong = k.getsockname()[1]
    r1.state["airplay_open"] = False
    f = FakeRaop()
    gia = mock.Mock(port=cong)
    await them(hass, r1, gia, "airplay_truoc")
    tac = asyncio.create_task(phat(hass))
    await asyncio.sleep(0.8)
    await f.start(cong_tcp=cong)
    try:
        await asyncio.wait_for(tac, 10)
        assert f.audio and dmr.actions == [] and thuoc_tinh(hass)["duong_phat"] == "airplay"
        await dich_vu(hass, "media_stop")
    finally:
        await f.stop()


async def test_airplay_da_mo_san_ma_cong_dong_thi_khong_thu_lai_het_gio(hass, r1, dmr, nguon):
    """AirPlay đã bật từ trước mà cổng đóng = lỗi thật, không đợi 2,5 giây: sang DLNA ngay."""
    with socket.socket() as k:
        k.bind(("127.0.0.1", 0))
        cong = k.getsockname()[1]
    r1.state["airplay_open"] = True
    await them(hass, r1, mock.Mock(port=cong), "airplay_truoc")
    t0 = asyncio.get_running_loop().time()
    await phat(hass)
    assert asyncio.get_running_loop().time() - t0 < 2.0
    assert thuoc_tinh(hass)["duong_phat"] == "dlna"


async def test_bai_moi_di_dlna_thi_phien_airplay_cu_bi_dong(hass, r1, dmr, raop, nguon):
    """Đang phát bằng AirPlay, đổi chế độ sang DLNA rồi phát bài mới: AirPlay phải tắt tiếng (không phát hai nơi) và trạng thái là của DLNA."""
    r1.state["airplay_open"] = True
    e = await them(hass, r1, raop, "airplay")
    await phat(hass)
    assert thuoc_tinh(hass)["duong_phat"] == "airplay"
    hass.config_entries.async_update_entry(e, options={**e.options, "duong_phat": "dlna"})
    await phat(hass, URL2)
    assert raop.phuong_thuc()[-1] == "TEARDOWN"
    await asyncio.sleep(0.05)
    n = len(raop.audio)
    await asyncio.sleep(0.2)
    assert len(raop.audio) == n                                   # AirPlay im hẳn
    assert dmr.transport_state == "PLAYING" and thuoc_tinh(hass)["duong_phat"] == "dlna"
    assert hass.states.get(LOA).state == "playing"
