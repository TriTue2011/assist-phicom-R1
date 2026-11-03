"""NV287 — nhạc không nhảy bài sau TTS, hạ nhạc nền khi loa nói.

ĐỎ-TRƯỚC-XANH trên mã cũ: ``MusicKeeper.hold`` cũ không có chế độ ducking,
``R1Player`` cũ gắn ``idle_reason=finished`` cho cả tin báo (TTS), nên bộ điều khiển
danh sách phát đọc «hết bài» là nhảy bài kế.

Hai tầng test:
- Tầng giữ nhạc (bộ nhớ, ``FakeDmrPlayer``): ducking bằng âm lượng, lồng nhau,
  lỗi giữa chừng vẫn trả mức cũ, không đọc được mức thì về tạm dừng như cũ.
- Tầng thực thể (renderer DLNA giả + RAOP giả): tin báo không được phát sinh
  «hết bài», nhạc phát lại đúng URI/vị trí; chế độ tin song song qua AirPlay
  không đụng tới DLNA đang phát.
"""

import asyncio
from unittest import mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import const, giu_nhac
from custom_components.r1_speaker import dmr as dmr_mod
from custom_components.r1_speaker import media_player as r1_mp
from custom_components.r1_speaker.const import DOMAIN
from custom_components.r1_speaker.giu_nhac import MusicKeeper

from .fake_dmr import FakeDMR
from .fake_raop import FakeRaop
from .memory_port import them_dmr_gia

MUSIC = "http://nhac.example/bai.mp3"
TTS = "http://ha.example/api/tts_proxy/x.mp3"
LOA = "media_player.r1_loa"


@pytest.fixture(autouse=True)
def _nhanh():
    with mock.patch.object(giu_nhac, "POLL", 0.01), \
            mock.patch.object(const, "PAUSE_CONFIRM_S", 0.3), \
            mock.patch.object(const, "RESTORE_WAIT", 0.3):
        yield


# ── Tầng giữ nhạc: ducking ───────────────────────────────────────────────────

class AmLuongGia:
    """Âm lượng giả theo thang 0–15 của loa: đọc ra mức, ghi lại mọi lần đặt."""

    def __init__(self, muc=10):
        self.muc = muc
        self.dat: list[int] = []

    async def doc(self):
        return self.muc / 15.0

    async def dat_muc(self, muc_float):
        self.muc = round(muc_float * 15)
        self.dat.append(self.muc)


def keeper_duck(hass, dmr, am):
    return MusicKeeper(hass, lambda: dmr.entity_id, am_luong=(am.doc, am.dat_muc))


async def test_duck_khong_tam_dung_va_tra_dung_muc_cu(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    am = AmLuongGia(muc=10)
    giu = await keeper_duck(hass, dmr, am).hold(duck=True, nac=5)
    assert ("pause",) not in dmr.log                     # nhạc vẫn phát, chỉ nhỏ đi
    assert am.dat == [5]                                  # 10 − 5 nấc
    await giu.release()
    assert am.dat == [5, 10]                              # trả đúng mức cũ
    assert dmr.log == []


async def test_duck_long_nhau_chi_ha_mot_lan_va_chi_tra_khi_ben_cuoi_nha(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    am = AmLuongGia(muc=12)
    keeper = keeper_duck(hass, dmr, am)
    ngoai = await keeper.hold(duck=True, nac=5)
    trong = await keeper.hold(duck=True, nac=5)
    assert am.dat == [7]                                  # chỉ hạ một lần
    await trong.release()
    assert am.dat == [7]                                  # bên trong nhả: chưa trả
    await ngoai.release()
    assert am.dat == [7, 12]


async def test_duck_loi_giua_chung_van_tra_am_luong(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    am = AmLuongGia(muc=10)
    giu = await keeper_duck(hass, dmr, am).hold(duck=True, nac=5)
    with pytest.raises(RuntimeError):
        try:
            raise RuntimeError("TTS lỗi (giả)")
        finally:
            await giu.release()                     # nhả trong finally vẫn trả mức cũ
    assert am.dat == [5, 10]


async def test_duck_khong_doc_duoc_muc_thi_tam_dung_nhu_cu(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)

    async def khong_doc():
        return None

    async def dat_muc(_muc):
        raise AssertionError("không được đặt mức khi không đọc được mức cũ")

    keeper = MusicKeeper(hass, lambda: dmr.entity_id, am_luong=(khong_doc, dat_muc))
    giu = await keeper.hold(duck=True, nac=5)
    assert ("pause",) in dmr.log                         # về đường tạm dừng cũ
    await giu.release()
    assert ("play",) in dmr.log


async def test_khong_duck_thi_giu_nguyen_hanh_vi_cu(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    am = AmLuongGia(muc=10)
    giu = await keeper_duck(hass, dmr, am).hold()
    assert ("pause",) in dmr.log and am.dat == []
    await giu.release()
    assert ("play",) in dmr.log and am.dat == []


async def test_duck_bi_huy_giua_chung_van_tra_muc_va_bo_dem_ve_0(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    am = AmLuongGia(muc=10)
    dat_that = am.dat_muc

    async def dat_roi_bi_huy(muc_float):
        await dat_that(muc_float)
        if len(am.dat) == 1:
            raise asyncio.CancelledError()          # bị huỷ ngay sau khi mức đã hạ

    keeper = MusicKeeper(hass, lambda: dmr.entity_id, am_luong=(am.doc, dat_roi_bi_huy))
    with pytest.raises(asyncio.CancelledError):
        await keeper.hold(duck=True, nac=5)
    assert keeper.holds == 0                         # không kẹt bộ đếm
    assert am.dat == [5, 10]                         # mức cũ đã được trả


async def test_giu_thuong_long_trong_duck_thi_tam_dung_not_roi_tra_muc_va_phat_lai(hass):
    """Tin song song đang hạ nhạc mà phiên đàm thoại mở mic (hold thường): nhạc phải IM (không lọt vào mic)."""
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    am = AmLuongGia(muc=10)
    keeper = keeper_duck(hass, dmr, am)
    tin = await keeper.hold(duck=True, nac=5)
    assert ("pause",) not in dmr.log
    dam_thoai = await keeper.hold()
    assert ("pause",) in dmr.log                     # đã tạm dừng nốt
    await tin.release()
    assert am.dat == [5]                             # còn bên giữ: chưa trả
    await dam_thoai.release()
    assert am.dat == [5, 10] and ("play",) in dmr.log   # trả mức rồi phát lại


async def test_duck_tat_nac_0_khong_dong_toi_am_luong(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)

    async def cam(*_):
        raise AssertionError("nac=0 thì không được đọc/đặt âm lượng")

    giu = await MusicKeeper(hass, lambda: dmr.entity_id, am_luong=(cam, cam)).hold(duck=True, nac=0)
    assert dmr.log == []
    await giu.release()
    assert dmr.log == []


async def test_se_phat_lai_chi_dung_khi_that_su_tam_dung_nhac(hass):
    """``se_phat_lai`` (cơ sở của idle_reason=dang_giu) đúng đúng lúc: không có nhạc hoặc mới chỉ hạ nhỏ thì sai;
    đã tạm dừng thì đúng, kể cả suốt lúc khôi phục."""
    dmr = await them_dmr_gia(hass)
    am = AmLuongGia(muc=10)
    keeper = keeper_duck(hass, dmr, am)
    giu = await keeper.hold()                              # chưa có nhạc nào
    assert keeper.holds == 1 and keeper.se_phat_lai is False
    await giu.release()

    dmr.start_music(MUSIC)
    giu = await keeper.hold(duck=True, nac=5)              # hạ nhỏ: nhạc vẫn phát, bài hết là hết thật
    assert keeper.se_phat_lai is False
    await giu.release()

    dmr.start_music(MUSIC)
    giu = await keeper.hold()
    assert keeper.se_phat_lai is True
    thay = []
    goc = keeper._restore

    async def restore_ghi(snap):
        thay.append(keeper.se_phat_lai)                    # đang khôi phục: vẫn phải đúng
        await goc(snap)

    keeper._restore = restore_ghi
    await giu.release()
    assert thay == [True] and keeper.se_phat_lai is False


# ── Tầng thực thể: DLNA giả + RAOP giả ───────────────────────────────────────

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


class Nguon:
    """Thay ``tao_nguon``: ghi (url, bắt đầu), trả bộ phát giả hữu hạn."""

    def __init__(self):
        self.goi: list[tuple[str, float]] = []
        self.so_goi = {}

    def __call__(self, url, bat_dau=0.0, ffmpeg=None):
        self.goi.append((url, bat_dau))

        async def gen():
            import array
            from custom_components.r1_speaker import airplay as ap_mod
            yield array.array("h", [1] * (ap_mod.KHUNG_MOI_GOI * 2 * self.so_goi.get(url, 400))).tobytes()
        return gen


@pytest.fixture
def nguon():
    n = Nguon()
    with mock.patch.object(r1_mp, "tao_nguon", new=n):
        yield n


@pytest.fixture(autouse=True)
def _nhanh_hon():
    with mock.patch.object(r1_mp, "CHAM_NHAC", 0.05), mock.patch.object(r1_mp, "CHAM_TIN", 0.05):
        yield


async def them(hass, r1, raop, che_do, **tuy_chon):
    r1.state["dlna_open"] = False
    r1.state["airplay_open"] = True
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        unique_id=f"127.0.0.1:{r1.port}",
                        options={"duong_phat": che_do, "airplay_port": raop.port, **tuy_chon})
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def phat(hass, url, **extra):
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": LOA, "media_content_id": url, "media_content_type": "music", **extra},
        blocking=True)


async def cho(hass, dieu_kien, han=10.0):
    async with asyncio.timeout(han):
        while not dieu_kien():
            await asyncio.sleep(0.02)


async def cho_state(hass, mong_doi, han=10.0):
    """Đợi trạng thái thực thể (poll DLNA 0,05 s đã patch): tránh gọi announce
    khi thực thể chưa kịp thấy nhạc đang phát."""
    await cho(hass, lambda: hass.states.get(LOA) is not None
              and hass.states.get(LOA).state == mong_doi, han)


def thuoc_tinh(hass):
    return hass.states.get(LOA).attributes


async def test_tin_bao_khong_phat_sinh_het_bai_va_nhac_phat_lai_dung_bai(hass, r1, dmr, raop, nguon):
    """Bộ điều khiển danh sách phát (giả): thấy idle + idle_reason=finished là gọi
    bài kế (và interrupted là gỡ loa). Tin báo DLNA không được phát sinh tín hiệu đó; nhạc phải về đúng bài."""
    await them(hass, r1, raop, "dlna")
    await phat(hass, MUSIC)
    assert dmr.transport_state == "PLAYING"
    bai_ke = []
    ly_do_idle = []

    chuoi_trang_thai = []

    def nghe_thay_doi(event):
        st = event.data.get("new_state")
        if st is not None and event.data.get("entity_id") == LOA and (not chuoi_trang_thai or chuoi_trang_thai[-1] != st.state):
            chuoi_trang_thai.append(st.state)
        if st is not None and st.state == "idle":
            ly_do_idle.append(st.attributes.get("idle_reason"))
            # tritue_youtube_player: finished → sang bài kế; interrupted → GỠ LOA khỏi phiên (xem NV287-KIEM.md)
            if st.attributes.get("idle_reason") in ("finished", "interrupted"):
                bai_ke.append("next_track")

    hass.bus.async_listen("state_changed", nghe_thay_doi)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: TTS in [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")]
              and dmr.transport_state == "PLAYING")       # đợi tin thật sự lên renderer rồi mới giả «tin hết»
    dmr.transport_state = "STOPPED"                       # TTS hết (loa giả đặt tay)
    await cho(hass, lambda: [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [MUSIC, TTS, MUSIC])
    await hass.async_block_till_done()
    assert bai_ke == []                                   # không có lệnh bài kế nào
    assert "dang_giu" in ly_do_idle and set(ly_do_idle) <= {None, "dang_giu"}, ly_do_idle
    # Bộ điều khiển (tritue_youtube_player 0.28.6) chỉ không nhảy bài / không gỡ loa nhờ thấy «paused» giữa nhạc và tin (nó đóng băng vị
    # trí ở đó): ghim rằng R1 THẬT SỰ phát ra trạng thái này, không chỉ mô phỏng bằng tay.
    assert "paused" in chuoi_trang_thai and chuoi_trang_thai.index("paused") < chuoi_trang_thai.index("idle"), chuoi_trang_thai
    assert thuoc_tinh(hass)["media_content_id"] == MUSIC
    assert "Seek" in [n for n, _ in dmr.actions]          # tua về vị trí đã chụp


async def test_tin_song_song_airplay_khong_dung_dlna_dang_phat(hass, r1, dmr, raop, nguon):
    """Chế độ tin song song: nhạc DLNA vẫn phát suốt lúc TTS đi AirPlay; DLNA
    không nhận thêm SetAVTransportURI nào, TTS có phiên RAOP riêng.
    LƯU Ý môi trường: sandbox này chặn UDP send (``Operation not permitted``)
    nên ``raop.audio`` không bao giờ đầy ở đây — kể cả test cũ cũng đỏ ở đó;
    test này vì vậy chứng minh bằng bắt tay RTSP (RECORD) + URI DLNA không đổi
    + watcher báo xong (``announce_seq``), không dựa vào gói UDP tới được loa giả."""
    nguon.so_goi[TTS] = 20
    await them(hass, r1, raop, "dlna", tts_song_song_airplay=True, ha_nhac_xuong=False)
    await phat(hass, MUSIC)
    assert dmr.transport_state == "PLAYING"
    await cho_state(hass, "playing")
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: "RECORD" in raop.phuong_thuc())
    # Giữa lúc tin song song phát: URI DLNA KHÔNG được đổi (đó mới là tính chất
    # chống nhảy bài). Trạng thái có thể là PLAYING (đọc được mức → không tạm
    # dừng) hoặc PAUSED_PLAYBACK (môi trường test này mic_server không nối nên
    # volume_level None → fallback tạm dừng đúng thiết kế; trên loa thật
    # mic_server nối nên volume đọc được, không rơi về đây).
    assert [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [MUSIC]
    assert "Pause" not in [n for n, _ in dmr.actions]   # ducking tắt: nhạc không bao giờ bị tạm dừng, dù chưa đọc được âm lượng
    assert thuoc_tinh(hass)["media_content_id"] == MUSIC
    player = hass.data["entity_components"]["media_player"].get_entity(LOA)
    await cho(hass, lambda: player.coordinator.talk.announce_seq >= 1)
    await hass.async_block_till_done()
    assert dmr.transport_state == "PLAYING"           # nhả giữ → phát lại (nếu đã tạm dừng)
    assert [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [MUSIC]


async def test_tin_song_song_khi_nhac_o_airplay_ma_dlna_khong_len_thi_ve_duong_thuong(hass, r1, dmr, raop, nguon, monkeypatch):
    """Nhạc đang ở AirPlay: từ NV303 tin đi DLNA song song; renderer DLNA không lên được thì về đường tạm dừng/khôi phục thường
    (tin vẫn phát hết, nhạc đặt lại)."""
    monkeypatch.setattr(r1_mp, "DLNA_TIN_NGUOC_SAN_SANG", 0.6)
    dmr.enabled = lambda: False
    nguon.so_goi[TTS] = 20
    await them(hass, r1, raop, "airplay", tts_song_song_airplay=True)
    await phat(hass, MUSIC)
    await cho_state(hass, "playing")
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2)
    assert [u for u, _ in nguon.goi][:3] == [MUSIC, TTS, MUSIC]


async def test_ducking_that_qua_mic_server_ha_nhac_roi_tra_dung_muc(hass, r1, dmr, raop, nguon):
    """Đường SẢN XUẤT (không tiêm am_luong giả): MusicKeeper đọc ``volume_level`` của thực thể và đặt bằng ``volume_set`` →
    ``mic_server.gui_am_luong``. Nhạc không tạm dừng, hạ 5 nấc, tin xong trả đúng mức 10."""
    nguon.so_goi[TTS] = 60
    await them(hass, r1, raop, "dlna", tts_song_song_airplay=True, ha_nhac_xuong=True, ha_nhac_nac=5)
    player = hass.data["entity_components"]["media_player"].get_entity(LOA)
    mic = player.coordinator.mic_server
    mic.am_luong = (10, 15)
    dat: list[int] = []

    async def gui(muc):
        dat.append(muc)
        mic.am_luong = (muc, 15)
        player.async_write_ha_state()

    mic.gui_am_luong = gui
    player.async_write_ha_state()
    await phat(hass, MUSIC)
    await cho_state(hass, "playing")
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: player.coordinator.talk.announce_seq >= 1)
    await hass.async_block_till_done()
    assert dat == [5, 10]
    assert "Pause" not in [n for n, _ in dmr.actions]
    assert [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [MUSIC]


async def test_hai_tin_song_song_lien_tiep_khong_bao_gio_hai_phien_cung_luc(hass, r1, dmr, raop, nguon):
    """Tin thứ hai đến khi tin thứ nhất còn đang nói: tin mới THAY tin cũ, không bao giờ hai phiên RAOP cùng chạy."""
    nguon.so_goi[TTS] = 4000
    dang_chay = {"n": 0, "cao": 0}
    goc = r1_mp.PhienAirPlay

    class PhienDem(goc):
        async def chay(self):
            dang_chay["n"] += 1
            dang_chay["cao"] = max(dang_chay["cao"], dang_chay["n"])
            try:
                return await super().chay()
            finally:
                dang_chay["n"] -= 1

    with mock.patch.object(r1_mp, "PhienAirPlay", PhienDem):
        await them(hass, r1, raop, "dlna", tts_song_song_airplay=True)
        player = hass.data["entity_components"]["media_player"].get_entity(LOA)
        await phat(hass, MUSIC)
        await cho_state(hass, "playing")
        await phat(hass, TTS, announce=True)
        await cho(hass, lambda: raop.phuong_thuc().count("RECORD") >= 1)
        await phat(hass, TTS, announce=True)
        await cho(hass, lambda: raop.phuong_thuc().count("RECORD") >= 2)
        assert dang_chay["cao"] == 1
        await player.async_media_stop()                    # Stop dừng cả phiên tin
        await cho(hass, lambda: dang_chay["n"] == 0)
        await hass.async_block_till_done()
        assert player.coordinator.talk.music.holds == 0    # mọi lượt giữ đã nhả


async def test_tin_bao_khi_khong_co_nhac_thi_idle_khong_phai_dang_giu(hass, r1, dmr, raop, nguon):
    """Lượt giữ không chụp được nhạc nào thì sẽ không phát lại gì: idle sau tin là idle thường, KHÔNG được khai «dang_giu»
    (nếu không bài hết ngay sau đó bị bộ điều khiển đã vá bỏ qua mãi)."""
    await them(hass, r1, raop, "dlna")
    ly_do_idle = []

    def nghe(event):
        st = event.data.get("new_state")
        if st is not None and event.data.get("entity_id") == LOA and st.state == "idle":
            ly_do_idle.append(st.attributes.get("idle_reason"))

    hass.bus.async_listen("state_changed", nghe)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: dmr.transport_state == "PLAYING")
    player = hass.data["entity_components"]["media_player"].get_entity(LOA)
    await cho(hass, lambda: player.coordinator.talk.music.holds == 1)
    assert player.coordinator.talk.music.se_phat_lai is False
    dmr.transport_state = "STOPPED"
    await cho(hass, lambda: player.coordinator.talk.music.holds == 0)
    await hass.async_block_till_done()
    assert "dang_giu" not in ly_do_idle, ly_do_idle
