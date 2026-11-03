"""NV303 — tin báo (TTS) đi đường NGƯỢC với nhạc: nhạc AirPlay ⇒ tin DLNA (nhạc DLNA ⇒ tin AirPlay đã có từ NV287).

Loa DLNA giả (``FakeDMR``) + loa AirPlay giả (``FakeRaop``) + bộ phát giả thay ffmpeg, như NV287. Mỗi test khẳng định CẢ HAI phía: tin có tới
renderer DLNA, và phiên AirPlay của nhạc không bị đụng (không FLUSH / TEARDOWN, không nguồn mới, thực thể vẫn ``playing`` và KHÔNG BAO GIỜ
có ``idle_reason``). Gọi qua ``media_player.play_media`` thật (``announce``). CHƯA thử trên loa thật."""

import pytest

from custom_components.r1_speaker import media_player as r1_mp

from .test_nv287_giu_nhac import (LOA, MUSIC, TTS, _nhanh, _nhanh_hon, cho, cho_state, dmr, nguon, phat, raop,  # noqa: F401
                                  them)


@pytest.fixture(autouse=True)
def _cham_nho(monkeypatch):
    monkeypatch.setattr(r1_mp, "CHAM_TIN_NGUOC", 0.05)
    monkeypatch.setattr(r1_mp, "DLNA_TIN_NGUOC_SAN_SANG", 1.0)


async def _dung_nhac(hass):
    """Cuối ca: dừng nhạc AirPlay (nhạc dài, phiên còn mở thì bộ RAOP giả không tắt được ở phần dọn)."""
    await hass.services.async_call("media_player", "media_stop", {"entity_id": LOA}, blocking=True)
    await hass.async_block_till_done()


def _player(hass):
    return hass.data["entity_components"]["media_player"].get_entity(LOA)


def _ghi_trang_thai(hass):
    """Ghi mọi trạng thái + idle_reason mà thực thể từng phát ra (bộ điều khiển danh sách phát đọc đúng những thứ này)."""
    ds = []

    def nghe(ev):
        st = ev.data.get("new_state")
        if st is not None and ev.data.get("entity_id") == LOA:
            ds.append((st.state, st.attributes.get("idle_reason")))

    hass.bus.async_listen("state_changed", nghe)
    return ds


async def _nhac_airplay(hass, r1, raop, nguon, **tuy_chon):
    nguon.so_goi[MUSIC] = 4000                         # nhạc dài (~32 giây): không tự hết trong lúc test
    nguon.so_goi[TTS] = 40
    e = await them(hass, r1, raop, "airplay", **tuy_chon)
    await phat(hass, MUSIC)
    await cho_state(hass, "playing")
    assert _player(hass)._duong == "airplay"
    return e


def _am_luong_gia(hass, muc=10):
    p = _player(hass)
    mic = p.coordinator.mic_server
    mic.am_luong = (muc, 15)
    dat: list[int] = []

    async def gui(m):
        dat.append(m)
        mic.am_luong = (m, 15)
        p.async_write_ha_state()

    mic.gui_am_luong = gui
    p.async_write_ha_state()
    return dat


async def test_nhac_airplay_tin_di_dlna_khong_dung_phien_airplay(hass, r1, dmr, raop, nguon):
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True)
    ds = _ghi_trang_thai(hass)
    phuong_thuc_truoc = list(raop.phuong_thuc())
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: dmr.transport_state == "PLAYING")
    assert [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [TTS] and len(dmr.called("Play")) == 1
    assert [u for u, _ in nguon.goi] == [MUSIC]                     # tin KHÔNG mở phiên AirPlay thứ hai
    assert raop.phuong_thuc() == phuong_thuc_truoc                   # RAOP không nhận gì thêm: không FLUSH, không TEARDOWN
    assert "FLUSH" not in raop.phuong_thuc() and "TEARDOWN" not in raop.phuong_thuc()
    assert hass.states.get(LOA).state == "playing" and hass.states.get(LOA).attributes["duong_phat"] == "airplay"
    dmr.transport_state = "STOPPED"                                  # tin hết (loa giả đặt tay)
    p = _player(hass)
    await cho(hass, lambda: p.coordinator.talk.announce_seq >= 1)
    await hass.async_block_till_done()
    assert not p._tin_dlna_dang and p._tin_dlna_tac is None
    assert hass.states.get(LOA).state == "playing" and "FLUSH" not in raop.phuong_thuc()
    # trạng thái renderer của TIN không lọt vào thực thể: không idle / paused, không idle_reason (finished → sang bài, interrupted → gỡ loa)
    assert all(s == "playing" and r is None for s, r in ds), ds
    assert [u for u, _ in nguon.goi] == [MUSIC] and "Stop" not in [n for n, _ in dmr.actions]       # tin tự hết: không cần Stop


async def test_cong_tat_thi_hanh_vi_nhu_cu_tin_di_duong_thuong(hass, r1, dmr, raop, nguon):
    await _nhac_airplay(hass, r1, raop, nguon)                       # tts_song_song_airplay mặc định TẮT
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2)
    assert [u for u, _ in nguon.goi][:3] == [MUSIC, TTS, MUSIC]      # tạm dừng nhạc, tin qua AirPlay, nhạc phát lại
    assert dmr.called("SetAVTransportURI") == [] and dmr.called("Play") == []
    await _dung_nhac(hass)


async def test_renderer_dlna_khong_len_thi_roi_ve_duong_thuong_khong_cho_15_giay(hass, r1, dmr, raop, nguon):
    dmr.enabled = lambda: False                                      # DLNA của loa không bật được
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2, han=8.0)
    assert [u for u, _ in nguon.goi][:3] == [MUSIC, TTS, MUSIC]
    assert dmr.called("SetAVTransportURI") == []


async def test_renderer_tu_choi_play_thi_dung_renderer_va_ve_duong_thuong(hass, r1, dmr, raop, nguon):
    dmr.tu_choi = {"Play"}
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2, han=8.0)
    assert [u for u, _ in nguon.goi][:3] == [MUSIC, TTS, MUSIC]
    assert "Stop" in [n for n, _ in dmr.actions]                     # không để renderer giữ tin dở: loa không phát hai thứ
    assert not _player(hass)._tin_dlna_dang                          # cổng trả về cho nhạc
    await _dung_nhac(hass)


async def test_renderer_khong_phat_sau_han_thi_roi_ve_duong_thuong(hass, r1, dmr, raop, nguon, monkeypatch):
    from custom_components.r1_speaker import const
    monkeypatch.setattr(const, "ANNOUNCE_START_WAIT", 0.5)
    dmr.play_cham = True                                             # nhận Play mà không phát
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2, han=10.0)
    assert [u for u, _ in nguon.goi][:3] == [MUSIC, TTS, MUSIC] and "Stop" in [n for n, _ in dmr.actions]
    await _dung_nhac(hass)


async def test_ha_nhac_xuong_ap_cho_chieu_nay_va_tra_dung_muc(hass, r1, dmr, raop, nguon):
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True, ha_nhac_xuong=True, ha_nhac_nac=5)
    dat = _am_luong_gia(hass, 10)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: dmr.transport_state == "PLAYING")
    assert dat == [5]                                                # nhạc AirPlay hạ 5 nấc trong lúc tin nói
    assert "FLUSH" not in raop.phuong_thuc()                         # hạ bằng âm lượng, không tạm dừng nhạc
    dmr.transport_state = "STOPPED"
    p = _player(hass)
    await cho(hass, lambda: p.coordinator.talk.announce_seq >= 1)
    await hass.async_block_till_done()
    assert dat == [5, 10] and "FLUSH" not in raop.phuong_thuc()


async def test_tin_loi_van_tra_dung_muc_cu(hass, r1, dmr, raop, nguon):
    dmr.tu_choi = {"Play"}
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True, ha_nhac_xuong=True, ha_nhac_nac=5)
    dat = _am_luong_gia(hass, 10)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2, han=8.0)
    await hass.async_block_till_done()
    assert dat[:2] == [5, 10] and dat[-1] == 10                      # hạ rồi trả; đường thường sau đó không để nhạc nhỏ mãi
    assert not _player(hass).coordinator.talk.music.holds


async def test_muon_ha_nhac_ma_chua_doc_duoc_am_luong_thi_ve_duong_thuong_khong_dung_phien_airplay_truoc(hass, r1, dmr, raop, nguon):
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True, ha_nhac_xuong=True)   # APK chưa nối: am_luong None
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: [u for u, _ in nguon.goi].count(MUSIC) >= 2, han=8.0)
    assert dmr.called("SetAVTransportURI") == []                      # không thử DLNA (hạ mù phải tạm dừng nhạc, trái «không đụng nhạc»)
    await _dung_nhac(hass)


async def test_stop_giua_luc_tin_dlna_noi_thi_dung_ca_tin_va_nhac(hass, r1, dmr, raop, nguon):
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True, ha_nhac_xuong=True, ha_nhac_nac=5)
    dat = _am_luong_gia(hass, 10)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: dmr.transport_state == "PLAYING")
    await hass.services.async_call("media_player", "media_stop", {"entity_id": LOA}, blocking=True)
    await hass.async_block_till_done()
    assert dmr.transport_state == "STOPPED" and "Stop" in [n for n, _ in dmr.actions]     # tin im
    assert dat[-1] == 10 and not _player(hass).coordinator.talk.music.holds              # mức trả lại, không kẹt giữ
    assert hass.states.get(LOA).state == "idle"                                          # nhạc AirPlay cũng dừng theo lệnh Stop


async def test_hai_tin_lien_tiep_tin_moi_thay_tin_cu_khong_chong_nhau(hass, r1, dmr, raop, nguon):
    await _nhac_airplay(hass, r1, raop, nguon, tts_song_song_airplay=True)
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: dmr.transport_state == "PLAYING")
    await phat(hass, TTS + "2", announce=True)
    await cho(hass, lambda: [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [TTS, TTS + "2"] and dmr.transport_state == "PLAYING")
    dmr.transport_state = "STOPPED"
    p = _player(hass)
    await cho(hass, lambda: p.coordinator.talk.announce_seq >= 2)
    await hass.async_block_till_done()
    assert not p.coordinator.talk.music.holds and hass.states.get(LOA).state == "playing"
    assert "FLUSH" not in raop.phuong_thuc()


async def test_nhac_dlna_van_di_airplay_nhu_nv287_chieu_kia_khong_hong(hass, r1, dmr, raop, nguon):
    """Chiều kia (NV287) không bị phá: nhạc DLNA thì tin vẫn đi AirPlay, DLNA không nhận thêm URI."""
    nguon.so_goi[TTS] = 20
    await them(hass, r1, raop, "dlna", tts_song_song_airplay=True)
    await phat(hass, MUSIC)
    await cho_state(hass, "playing")
    await phat(hass, TTS, announce=True)
    await cho(hass, lambda: "RECORD" in raop.phuong_thuc())
    assert [a["CurrentURI"] for a in dmr.called("SetAVTransportURI")] == [MUSIC]
