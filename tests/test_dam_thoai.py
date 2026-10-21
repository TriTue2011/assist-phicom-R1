"""Phiên đàm thoại (``dam_thoai.R1Talk``) + giữ nhạc (``giu_nhac``) + hợp đồng âm thanh trừu tượng
(``audio_port``). Chạy trên bản giả trong bộ nhớ: KHÔNG TCP, KHÔNG chạm loa, KHÔNG đoán đường mic
phần cứng (chưa có). Phần có thực thể HA (nút, sensor, vệ tinh) ở ``test_dam_thoai_ha.py``."""

import asyncio
from unittest import mock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.r1_speaker import const, dam_thoai, giu_nhac
from custom_components.r1_speaker.audio_port import (FrameError, PcmSink, PcmSource,
                                                      check_frame)
from custom_components.r1_speaker.dam_thoai import R1SessionBusy, R1Talk
from custom_components.r1_speaker.giu_nhac import MusicKeeper
from custom_components.r1_speaker.mic import R1Mic
from custom_components.r1_speaker.playback import R1Playback

from .memory_port import FakeDriver, MemorySink, MemorySource, them_dmr_gia

MUSIC = "http://nhac.example/bai.mp3"
TTS = "http://ha.example/api/tts_proxy/x.mp3"


def pcm(n=1024):
    return bytes(n)


def make_talk(hass, src, dmr_id="media_player.dmr_gia", mode=const.WAKE_HA):
    talk = R1Talk(hass, src, MusicKeeper(hass, lambda: dmr_id), mode)
    talk.driver = FakeDriver()
    return talk


@pytest.fixture(autouse=True)
def _nhanh():
    with mock.patch.object(giu_nhac, "POLL", 0.01), \
            mock.patch.object(const, "PAUSE_CONFIRM_S", 0.3), \
            mock.patch.object(const, "RESTORE_WAIT", 0.3):
        yield


# ── Hợp đồng âm thanh trừu tượng ──────────────────────────────────────────────────

def test_ban_cai_dat_thoa_hop_dong():
    assert isinstance(MemorySource(), PcmSource) and isinstance(MemorySink(), PcmSink)
    # Hai bản thật (TCP) thoả cùng giao diện: đổi đường thật sau này không sửa phần đàm thoại.
    assert isinstance(R1Mic("", 0), PcmSource) and isinstance(R1Playback("", 0), PcmSink)


def test_khung_pcm_dung_hop_dong():
    assert check_frame(bytes(2048)) == bytes(2048)
    for sai in (b"", b"\x00\x01\x02", bytes(2 * const.MIC_CHUNK * 16 + 2)):
        with pytest.raises(FrameError):
            check_frame(sai)


async def test_nhan_va_gui_khung_qua_ban_trong_bo_nho():
    """Nhận khung PCM (mic) và gửi khung PCM (đích) chỉ bằng giao diện, không biết đường thật."""
    src, sink = MemorySource(), MemorySink()
    got = []
    src.add_chunk_listener(got.append)
    assert src.push(b"\x01\x00" * 100) and got == [b"\x01\x00" * 100]
    src.muted = True
    assert not src.push(b"\x02\x00" * 10) and len(got) == 1        # tắt mic: không khung nào đi
    release = src.hold()
    src.muted = False
    assert not src.push(b"\x03\x00" * 10)                          # nửa công: giữ mic thì bỏ
    release()
    assert src.push(b"\x04\x00" * 10)

    async def nguon():
        yield b"\x05\x00" * 8
        yield b"\x06\x00" * 8

    assert await sink.async_play(nguon()) == pytest.approx(32 / 32000)
    assert bytes(sink.played) == b"\x05\x00" * 8 + b"\x06\x00" * 8


# ── Trạng thái mic: tắt / nghe / gửi ──────────────────────────────────────────────

async def test_trang_thai_mic_che_do_ha(hass):
    src = MemorySource(auto_connect=False)
    talk = make_talk(hass, src)
    assert talk.mic_status == const.MIC_TAT                 # chưa có luồng
    src.set_connected(True)
    assert talk.mic_status == const.MIC_GUI                 # byte mic đang về HA
    src.set_muted(True)
    assert talk.mic_status == const.MIC_TAT
    assert make_talk(hass, MemorySource(configured=False)).mic_status == const.MIC_TAT


async def test_trang_thai_mic_tu_danh_thuc_tren_loa(hass):
    src = MemorySource(on_demand=True)
    talk = make_talk(hass, src, mode=const.WAKE_SPEAKER)
    seen = []
    talk.add_listener(lambda: seen.append(talk.mic_status))
    # Chưa có phía loa: KHÔNG được nói «nghe» (không nói dối).
    assert talk.mic_status == const.MIC_TAT and not src.connected
    talk.alive()                                            # loa báo còn sống (CHỜ phía loa)
    assert talk.mic_status == const.MIC_NGHE and src.wants == 0   # chờ từ gọi, chưa nối/gửi gì
    s = await talk.async_start("wake")                      # trigger → mở phiên → nối luồng
    assert talk.mic_status == const.MIC_GUI and src.connected
    talk.end(s, "xong")
    assert talk.mic_status == const.MIC_NGHE and not src.connected   # nhả luồng
    src.set_muted(True)
    assert talk.mic_status == const.MIC_TAT
    assert const.MIC_NGHE in seen and const.MIC_GUI in seen and const.MIC_TAT in seen
    await talk.async_settle()


async def test_loa_im_qua_lau_thi_het_nghe(hass):
    src = MemorySource(on_demand=True)
    talk = make_talk(hass, src, mode=const.WAKE_SPEAKER)
    talk.alive()
    assert talk.mic_status == const.MIC_NGHE
    with mock.patch.object(const, "WAKE_ALIVE_S", -1):      # coi như đã quá hạn
        assert talk.mic_status == const.MIC_TAT


# ── Một phiên một lúc ─────────────────────────────────────────────────────────────

async def test_phien_thu_hai_bi_tu_choi_co_thong_bao_khong_treo(hass, caplog):
    src = MemorySource()
    talk = make_talk(hass, src, dmr_id=None)
    events = []
    hass.bus.async_listen(const.EVENT_SESSION_REFUSED, events.append)
    s1 = await asyncio.wait_for(talk.async_start("button"), 2)
    assert talk.session is s1 and talk.driver.began == 1
    with pytest.raises(R1SessionBusy) as exc:
        await asyncio.wait_for(talk.async_start("wake"), 2)       # từ chối NGAY, không xếp hàng
    msg = str(exc.value)
    assert "button" in msg and "wake" in msg and "từ chối" in msg
    await hass.async_block_till_done()
    assert talk.session is s1 and talk.driver.began == 1          # phiên một không bị đụng
    assert talk.refused == 1 and talk.last_refusal == msg
    assert events and events[0].data["ban"] == "button" and events[0].data["bi_tu_choi"] == "wake"
    assert "từ chối" in caplog.text
    talk.end(s1, "xong")
    s2 = await asyncio.wait_for(talk.async_start("wake"), 2)      # đóng rồi thì mở được
    assert talk.session is s2
    talk.end(s2, "xong")


async def test_hai_loi_xin_cung_luc_chi_mot_thang(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    ket = await asyncio.gather(talk.async_start("button"), talk.async_start("wake"),
                               return_exceptions=True)
    assert sum(isinstance(k, R1SessionBusy) for k in ket) == 1
    assert sum(not isinstance(k, Exception) for k in ket) == 1
    talk.end(talk.session, "xong")


async def test_bo_dam_va_phien_assist_loai_tru_nhau(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    nha = talk.claim("bo_dam")
    with pytest.raises(R1SessionBusy, match="bo_dam"):
        await talk.async_start("button")
    nha()
    s = await talk.async_start("button")
    with pytest.raises(R1SessionBusy, match="button"):
        talk.claim("bo_dam")
    talk.end(s, "xong")


@pytest.mark.parametrize("sua,msg", [
    (lambda s: setattr(s, "configured", False), "Chưa cấu hình mic"),
    (lambda s: setattr(s, "muted", True), "Mic đang tắt"),
    (lambda s: setattr(s, "_connected", False), "chưa nối được"),
])
async def test_khong_mo_phien_khi_mic_khong_san_sang(hass, sua, msg):
    src = MemorySource()
    sua(src)
    talk = make_talk(hass, src, dmr_id=None)
    with pytest.raises(HomeAssistantError, match=msg):
        await talk.async_start("button")
    assert talk.session is None and src.wants == 0                  # không để lại phiên mồ côi


async def test_phien_het_gio_thi_tu_dong(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    with mock.patch.object(const, "SESSION_MAX_S", 0.3), \
            mock.patch.object(const, "SESSION_MIC_WAIT_S", 0.1):
        s = await talk.async_start("button")
        await asyncio.wait_for(_cho(lambda: talk.session is None), 2)
    assert s.ended == "het_gio" and talk.driver.cut == 1           # lượt pipeline bị cắt


async def test_mic_khong_noi_duoc_thi_dong_phien_va_nha_nhac(hass):
    src = MemorySource(on_demand=True, auto_connect=False)
    talk = make_talk(hass, src, mode=const.WAKE_SPEAKER)
    with mock.patch.object(const, "SESSION_MIC_WAIT_S", 0.1):
        s = await talk.async_start("wake")
        await asyncio.wait_for(_cho(lambda: talk.session is None), 2)
    assert s.ended == "mic_khong_noi_duoc" and src.wants == 0


async def test_noi_tiep_hoi_thoai_gia_han_phien(hass):
    talk = make_talk(hass, MemorySource(), dmr_id=None)
    with mock.patch.object(const, "SESSION_MAX_S", 0.4), \
            mock.patch.object(const, "SESSION_MIC_WAIT_S", 0.05):
        s = await talk.async_start("button")
        for _ in range(4):                                        # 0,8 s > hạn 0,4 s
            await asyncio.sleep(0.2)
            talk.turn_finished(s, continue_conversation=True)
            assert talk.session is s
        talk.turn_finished(s, continue_conversation=False)
    assert talk.session is None and s.ended == "xong"


async def _cho(cond, giay=3.0):
    for _ in range(int(giay / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("điều kiện không đạt trong hạn")


# ── Giữ nhạc: tạm dừng khi bắt đầu, phát lại khi xong ─────────────────────────────

async def test_phien_tam_dung_nhac_roi_phat_lai(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    talk = make_talk(hass, MemorySource())
    s = await talk.async_start("button")
    assert dmr.log == [("pause",)] and hass.states.get(dmr.entity_id).state == "paused"
    talk.turn_finished(s, continue_conversation=False)
    await talk.async_settle()
    assert dmr.log == [("pause",), ("play",)]                      # cùng URI → chỉ Play lại
    assert hass.states.get(dmr.entity_id).state == "playing"
    assert dmr.urls() == []


async def test_tts_chen_giua_nhac_nhac_tam_dung_tts_phat_nhac_phat_lai(hass):
    """DLNA: TTS thay URI đang phát → khôi phục phải đặt lại ĐÚNG URI nhạc (+ tua về vị trí cũ)."""
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC, position=40, ago=5)
    keeper = MusicKeeper(hass, lambda: dmr.entity_id)
    giu = await keeper.hold()                                      # đường TTS: hold trước khi phát
    assert dmr.log == [("pause",)]
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": dmr.entity_id, "media_content_id": TTS, "media_content_type": "music"},
        blocking=True)
    assert hass.states.get(dmr.entity_id).attributes["media_content_id"] == TTS
    dmr.finish()                                                   # TTS xong
    await giu.release()
    assert dmr.urls() == [TTS, MUSIC]                              # chuỗi SetAVTransportURI
    assert hass.states.get(dmr.entity_id).attributes["media_content_id"] == MUSIC
    seeks = [e for e in dmr.log if e[0] == "seek"]
    assert len(seeks) == 1 and seeks[0][1] == pytest.approx(45, abs=2)   # 40 s + 5 s trước lúc chụp
    assert dmr.log[0] == ("pause",)


async def test_giu_long_nhau_chi_phat_lai_khi_ben_cuoi_nha(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    keeper = MusicKeeper(hass, lambda: dmr.entity_id)
    phien = await keeper.hold()
    tin = await keeper.hold()                                      # TTS trong phiên
    assert keeper.holds == 2 and dmr.log == [("pause",)]           # chỉ tạm dừng MỘT lần
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": dmr.entity_id, "media_content_id": TTS, "media_content_type": "music"},
        blocking=True)
    dmr.finish()
    await tin.release()
    await tin.release()                                            # nhả lần hai không tác dụng
    assert dmr.urls() == [TTS]                                     # TTS xong mà phiên còn: nhạc im
    await phien.release()
    assert dmr.urls() == [TTS, MUSIC]
    assert keeper.holds == 0 and keeper.snapshot is None


async def test_khong_co_nhac_thi_khong_dong_gi(hass):
    dmr = await them_dmr_gia(hass)                                 # đang idle
    keeper = MusicKeeper(hass, lambda: dmr.entity_id)
    h = await keeper.hold()
    await h.release()
    assert dmr.log == []
    k2 = MusicKeeper(hass, lambda: None)                           # chưa có dlna_dmr
    await (await k2.hold()).release()


async def test_nguoi_dung_tu_bat_nhac_khac_thi_khong_de_len(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    keeper = MusicKeeper(hass, lambda: dmr.entity_id)
    h = await keeper.hold()
    await dmr.async_play_media("music", "http://khac.example/b.mp3")   # người dùng bật bài khác
    await h.release()
    assert dmr.urls() == ["http://khac.example/b.mp3"]


async def test_tam_dung_loi_thi_van_phat_tin(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    with mock.patch.object(type(dmr), "async_media_pause",
                           side_effect=HomeAssistantError("renderer chết")):
        keeper = MusicKeeper(hass, lambda: dmr.entity_id)
        h = await keeper.hold()                                    # không ném, không treo
        assert keeper.snapshot is None
        await h.release()


async def test_phien_dong_giua_chung_khi_dang_chup_nhac_khong_mo_coi(hass):
    dmr = await them_dmr_gia(hass)
    dmr.start_music(MUSIC)
    talk = make_talk(hass, MemorySource())
    s = await talk.async_start("button")
    talk.end(s, "nguoi_dung_ket_thuc")
    talk.end(s, "lan_hai")                                         # đóng hai lần: bỏ qua
    await talk.async_settle()
    assert talk.session is None and talk.music.holds == 0
    assert dmr.log == [("pause",), ("play",)]


# ── Trigger từ loa ────────────────────────────────────────────────────────────────

async def test_trigger_tu_loa_mo_phien_phat_su_kien(hass):
    src = MemorySource(on_demand=True)
    talk = make_talk(hass, src, dmr_id=None, mode=const.WAKE_SPEAKER)
    events = []
    hass.bus.async_listen(const.EVENT_WAKE, events.append)
    s = await talk.trigger("hey_r1")
    await hass.async_block_till_done()
    assert s.kind == "wake" and talk.driver.began == 1 and talk.wake_pulse
    assert events[0].data == {"tu": "hey_r1"} and talk.last_wake_word == "hey_r1"
    with pytest.raises(R1SessionBusy):                              # trigger thứ hai khi đang bận
        await talk.trigger("hey_r1")
    talk.end(s, "xong")
    await talk.async_close()
