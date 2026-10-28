"""Đàm thoại trên thực thể HA thật: nút, cảm biến trạng thái mic, vệ tinh Assist, trigger từ loa,
giữ nhạc qua ``media_player.r1_loa``, khoá, ``ha_url``, đệm/độ trễ. Loa/mic giả ở 127.0.0.1 và
renderer giả trong bộ nhớ; pipeline Assist được mock (``FakePipeline``). KHÔNG chạm loa thật."""

import asyncio
import time
import types
from unittest import mock

import pytest
from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType, PipelineStage
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import assist_satellite as sat_mod
from custom_components.r1_speaker import cong_vao, const, dam_thoai, giu_nhac
from custom_components.r1_speaker import media_player as mp_mod
from custom_components.r1_speaker import mic as mic_mod
from custom_components.r1_speaker.const import DOMAIN, MIC_CHUNK

from .memory_port import FakeDmr
from .test_mic import (SAT, PcmServer, _bom, _cho, _nhanh, _state, _vet_tinh, pcm,  # noqa: F401
                       pcm_server, pipeline, samples)

INTERCOM, MICST, WAKE_BS, LOA = ("switch.r1_dam_thoai", "sensor.r1_trang_thai_mic",
                                 "binary_sensor.r1_tu_danh_thuc", "media_player.r1_loa")
MUSIC = "http://nhac.example/bai.mp3"
TTS = "http://ha.example/api/tts_proxy/x.mp3"


@pytest.fixture(autouse=True)
def _nhanh_2():
    with mock.patch.object(giu_nhac, "POLL", 0.01), \
            mock.patch.object(const, "PAUSE_CONFIRM_S", 0.3), \
            mock.patch.object(const, "RESTORE_WAIT", 0.3), \
            mock.patch.object(const, "ANNOUNCE_START_WAIT", 1.0):
        yield


async def _them(hass, r1, **options) -> MockConfigEntry:
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options=options, unique_id=f"127.0.0.1:{r1.port}")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


@pytest.fixture
def nhac(hass):
    """Renderer giả trong bộ nhớ (``FakeDmr``) thay ``R1Dmr`` của loa; ``media_source`` được giả để id ``media-source://`` đi
    thẳng tới renderer như cũ (giải URL thật là việc của HA)."""
    patches = []

    async def make():
        dmr = FakeDmr()
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        entry.runtime_data.dmr = dmr
        for p in (mock.patch.object(mp_mod.media_source, "async_resolve_media",
                                    new=mock.AsyncMock(side_effect=lambda h, mid, eid: types.SimpleNamespace(url=mid))),
                  mock.patch.object(mp_mod, "CHAM_NHAC", 0.03), mock.patch.object(mp_mod, "CHAM_TIN", 0.03)):
            p.start()
            patches.append(p)
        return dmr

    yield make
    for p in patches:
        p.stop()


_NUOI: list[asyncio.Task] = []


@pytest.fixture(autouse=True)
async def _dung_nuoi():
    yield
    for t in _NUOI:
        t.cancel()
    _NUOI.clear()


async def _nuoi_mic(server):
    """Loa đẩy tiếng đều như mic thật (không có tiếng thì luồng bị coi là đứt sau READ_TIMEOUT)."""
    while True:
        await server.send(pcm(5))
        await asyncio.sleep(0.05)


async def _san_sang(hass, r1, pcm_server, pipeline, nuoi=True, **opt):
    """HA mode: entry có mic, luồng đã nối và vệ tinh idle. ``nuoi``: tiếp tục đẩy tiếng nền."""
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port, **opt)
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(100),
               lambda: _state(hass, SAT) == "idle" and pipeline.turns)    # lượt từ gọi đã chạy
    if nuoi:
        _NUOI.append(asyncio.create_task(_nuoi_mic(pcm_server)))
    return e


def _talk(e):
    return e.runtime_data.talk


async def _ket_thuc(e):
    """Người dùng đóng phiên Assist đang mở (trước đây là nút «Kết thúc»; nút đã bỏ, phiên còn kết
    thúc khi pipeline xong hoặc khi tắt mic)."""
    talk = _talk(e)
    talk.end(talk.session, "nguoi_dung_ket_thuc")
    await talk.async_settle()


# ── Nút đàm thoại ─────────────────────────────────────────────────────────────────

async def test_nut_dam_thoai_tam_dung_nhac_mo_phien_ket_thuc_phat_lai(
        hass, r1, pcm_server, pipeline, nhac):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)                                      # nhạc do thiết bị khác bật: thực thể thấy ở chu kỳ coordinator kế
    await e.runtime_data.async_refresh()
    await _cho(lambda: _state(hass, LOA) == "playing", hass)    # thẻ thấy nhạc qua r1_loa
    assert PipelineStage.WAKE_WORD in pipeline.turns            # đang chờ từ gọi của HA

    await _talk(e).async_start("button")

    assert _state(hass, LOA) == "paused" and dmr.log == [("pause",)]
    assert _talk(e).session_kind == "button"
    await _cho(lambda: PipelineStage.STT in pipeline.turns, hass)  # nghe thẳng, bỏ bước từ gọi
    assert hass.states.get(MICST).attributes["phien"] == "button"
    assert _state(hass, MICST) == "gui"
    assert _state(hass, LOA) == "paused"

    _vet_tinh(hass)._cat_luot()                                 # pipeline xong lượt
    await _cho(lambda: _talk(e).session is None, hass)
    await _talk(e).async_settle()
    assert dmr.log == [("pause",), ("play",)] and _state(hass, LOA) == "playing"
    assert hass.states.get(MICST).attributes["phien"] is None
    assert hass.states.get(MICST).attributes["ket_thuc_gan_nhat"] == "xong"


async def test_nut_ket_thuc_dong_phien_va_phat_lai_nhac(hass, r1, pcm_server, pipeline, nhac):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    await _talk(e).async_start("button")
    await _ket_thuc(e)
    assert _talk(e).session is None
    assert dmr.log == [("pause",), ("play",)]
    # Lượt từ gọi bị cắt lúc mở phiên rồi vòng nghe quay về chờ từ gọi: KHÔNG được còn lượt STT
    # nào chảy tiếng mic vào pipeline sau khi phiên đã đóng (cú cắt không được mất).
    await _cho(lambda: pipeline.turns[-1] is PipelineStage.WAKE_WORD, hass)
    await asyncio.sleep(0.2)
    assert pipeline.turns_ended == len(pipeline.turns) - 1, pipeline.turns   # chỉ 1 lượt đang chạy
    assert pipeline.turns[-1] is PipelineStage.WAKE_WORD
    assert hass.states.get(MICST).attributes["ket_thuc_gan_nhat"] == "nguoi_dung_ket_thuc"


async def test_phien_thu_hai_qua_nut_bi_tu_choi_co_thong_bao(hass, r1, pcm_server, pipeline, nhac):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    await _talk(e).async_start("button")
    with pytest.raises(HomeAssistantError, match="đang có phiên đàm thoại"):
        await _talk(e).async_start("button")                                  # từ chối NGAY, không treo
    st = hass.states.get(MICST)
    assert st.attributes["so_lan_tu_choi"] == 1 and "button" in st.attributes["tu_choi_gan_nhat"]
    assert dmr.log == [("pause",)]                              # lần hai không tạm dừng thêm
    assert _talk(e).session_kind == "button"
    await _ket_thuc(e)


async def test_cong_tac_dam_thoai_khong_dung_duoc_khi_mic_chua_noi(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port)   # chưa có byte nào
    assert _state(hass, INTERCOM) == "unavailable"
    assert _state(hass, MICST) == "tat"


async def test_tu_goi_cua_ha_khop_thi_tu_giu_nhac(hass, r1, pcm_server, pipeline, nhac):
    """Chế độ ``ha``: câu thoại mở bằng từ gọi (STT_START) cũng tạm dừng nhạc, xong thì phát lại."""
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    sat = _vet_tinh(hass)
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.STT_START, {}))
    await _cho(lambda: dmr.log == [("pause",)], hass)
    assert _talk(e).session_kind == "wake_ha"
    sat._cat_luot()                                             # lượt xong
    await _cho(lambda: _talk(e).session is None, hass)
    await _talk(e).async_settle()
    assert dmr.log == [("pause",), ("play",)]


# ── TTS ───────────────────────────────────────────────────────────────────────────

async def test_tts_khi_dang_phat_nhac_tam_dung_roi_phat_lai_sau_tts(hass, r1, nhac):
    e = await _them(hass, r1)
    dmr = await nhac()
    dmr.start_music(MUSIC, position=30, ago=2)
    # Đúng như tts.speak: media_player.play_media với announce + media-source TTS.
    await asyncio.wait_for(hass.services.async_call("media_player", "play_media", {
        "entity_id": LOA, "media_content_id": "media-source://tts/x?message=hi",
        "media_content_type": "music", "announce": True}, blocking=True), 3)
    assert dmr.log[0] == ("pause",)                             # nhạc dừng TRƯỚC khi tin phát
    assert dmr.urls() == ["media-source://tts/x?message=hi"]
    assert e.runtime_data.talk.music.holds == 1                 # đang giữ nhạc trong lúc tin phát
    await asyncio.sleep(0.15)
    assert dmr.urls() == ["media-source://tts/x?message=hi"]    # tin chưa xong: nhạc chưa về
    dmr.finish()                                                # tin xong
    await _cho(lambda: e.runtime_data.talk.music.holds == 0, hass)
    assert dmr.urls() == ["media-source://tts/x?message=hi", MUSIC]   # chuỗi URI: tin → nhạc
    assert any(x[0] == "seek" for x in dmr.log) and _state(hass, LOA) == "playing"


async def test_nhac_thuong_khong_bi_tam_dung(hass, r1, nhac):
    await _them(hass, r1)
    dmr = await nhac()
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": LOA, "media_content_id": MUSIC, "media_content_type": "music"}, blocking=True)
    assert dmr.log == [("play_media", MUSIC)]


@pytest.mark.parametrize("media_id,kwargs,expect", [
    ("media-source://tts/x", {}, True), ("http://a/b.mp3", {"announce": True}, True),
    ("http://a/b.mp3", {}, False), ("http://a/api/tritue_youtube_player/proxy/t", {}, False)])
def test_phan_biet_tin_va_nhac(media_id, kwargs, expect):
    assert mp_mod.is_announcement(media_id, kwargs) is expect


async def test_loa_pause_play_chuyen_sang_dlna(hass, r1, nhac):
    await _them(hass, r1)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    await hass.services.async_call("media_player", "media_pause", {"entity_id": LOA}, blocking=True)
    assert _state(hass, LOA) == "paused"                        # r1_loa soi trạng thái dlna
    await hass.services.async_call("media_player", "media_play", {"entity_id": LOA}, blocking=True)
    assert _state(hass, LOA) == "playing" and dmr.log == [("pause",), ("play",)]


async def test_loa_pause_khi_renderer_khong_tra_loi_bao_loi_ro(hass, r1):
    await _them(hass, r1)
    with mock.patch("custom_components.r1_speaker.dmr.tim_mo_ta", new=mock.AsyncMock(return_value=None)), \
            pytest.raises(HomeAssistantError, match="SSDP"):
        await hass.services.async_call("media_player", "media_pause", {"entity_id": LOA}, blocking=True)


async def test_tts_cua_assist_trong_phien_nhac_chi_ve_khi_phien_dong(
        hass, r1, pcm_server, pipeline, nhac):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    await _talk(e).async_start("button")
    sat = _vet_tinh(hass)
    await _cho(lambda: PipelineStage.STT in pipeline.turns, hass)   # TTS_END chỉ đến trong lượt chạy
    luong = mock.Mock(media_source_id="media-source://tts/-stream/tok1")
    with mock.patch.object(sat_mod.tts, "async_get_stream", return_value=luong):
        sat.on_pipeline_event(PipelineEvent(PipelineEventType.TTS_END,
                                            {"tts_output": {"token": "tok1"}}))
        await _cho(lambda: dmr.urls() == ["media-source://tts/-stream/tok1"], hass)
        await asyncio.sleep(0.2)                                # để bên theo dõi thấy «đang phát»
        dmr.finish()                                            # tin xong
        await _cho(lambda: sat._tts_xong.is_set(), hass)
    assert not sat._dang_noi, "mic phải được nhả ngay khi tin xong (không treo vòng nghe)"
    assert dmr.urls() == ["media-source://tts/-stream/tok1"]    # phiên còn mở: nhạc im
    sat._cat_luot()
    await _cho(lambda: _talk(e).session is None, hass)
    await _talk(e).async_settle()
    await _cho(lambda: _talk(e).music.holds == 0, hass)
    assert dmr.urls() == ["media-source://tts/-stream/tok1", MUSIC]


async def test_nhac_phat_lai_khong_lam_vet_tinh_treo_mic(hass, r1, pcm_server, pipeline, nhac):
    """Bẫy: nhạc vừa phát lại làm dlna «playing» → vệ tinh tưởng tin chưa xong, bỏ mic 120 s."""
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    sat = _vet_tinh(hass)
    t0 = time.monotonic()
    task = hass.async_create_task(sat._phat("media-source://tts/x"))
    await _cho(lambda: dmr.urls() == ["media-source://tts/x"], hass)
    dmr.finish()                                                # tin xong → nhạc được phát lại
    await asyncio.wait_for(task, 3)
    assert time.monotonic() - t0 < 3 and not sat._dang_noi
    await _cho(lambda: _state(hass, LOA) == "playing", hass)


# ── Trạng thái mic trên thực thể ──────────────────────────────────────────────────

async def test_trang_thai_mic_tat_gui_tat_che_do_ha(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port)
    assert _state(hass, MICST) == "tat"                         # chưa có luồng
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(100), lambda: _state(hass, MICST) == "gui")
    st = hass.states.get(MICST)
    assert st.attributes["luong_ve_ha"] is True and st.attributes["device_class"] == "enum"
    assert st.attributes["options"] == ["tat", "nghe", "gui"]
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.r1_tat_mic"},
                                   blocking=True)
    assert _state(hass, MICST) == "tat"                         # tắt mic: đóng luồng
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.r1_tat_mic"},
                                   blocking=True)
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(100), lambda: _state(hass, MICST) == "gui")


# ── Từ đánh thức TRÊN LOA (phía loa CHƯA có): trigger qua HTTP ─────────────────────

async def test_tu_danh_thuc_tren_loa_chi_nhan_luong_sau_trigger(
        hass, r1, pcm_server, pipeline, hass_client_no_auth):
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port,
                    wake_mode="speaker")
    client = await hass_client_no_auth()
    url = f"/api/r1_speaker/wake/{e.entry_id}?k={e.data['intercom_key']}"
    # 1) Chưa trigger: KHÔNG kết nối, KHÔNG pipeline, KHÔNG byte nào rời loa.
    await asyncio.sleep(0.4)
    assert pcm_server.accepted == 0 and pipeline.turns == []
    assert _state(hass, MICST) == "tat"                         # chưa có phía loa: không nói «nghe»
    assert hass.states.get(WAKE_BS).attributes["phia_loa"] == "CHO_PHIA_LOA"
    # 2) Loa báo còn sống → «nghe» (vẫn chưa gửi gì).
    assert (await client.post(url, json={"event": "alive"})).status == 200
    assert _state(hass, MICST) == "nghe" and pcm_server.accepted == 0
    assert hass.states.get(WAKE_BS).attributes["phia_loa"] == "da_ket_noi"
    # 3) Trigger → phiên mở → HA nối luồng → pipeline nghe từ bước STT → «gửi».
    events = []
    hass.bus.async_listen(const.EVENT_WAKE, events.append)
    r = await client.post(url, json={"word": "hey_r1"})
    assert r.status == 200 and (await r.json()) == {"phien": "mo"}
    assert _state(hass, WAKE_BS) == "on"
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(100), lambda: _state(hass, MICST) == "gui")
    assert pipeline.turns == [PipelineStage.STT]                # không qua bước từ gọi của HA
    await hass.async_block_till_done()
    assert events and events[0].data == {"tu": "hey_r1"}
    # 4) Trigger thứ hai khi phiên còn mở: 409 kèm lý do.
    r2 = await client.post(url, json={"word": "hey_r1"})
    assert r2.status == 409 and "từ chối" in (await r2.json())["loi"]
    # 5) Kết thúc phiên: luồng ĐÓNG, về «nghe».
    await _ket_thuc(e)
    await _cho(lambda: pcm_server.closed_by_client >= 1, hass)
    assert _state(hass, MICST) == "nghe"
    await _cho(lambda: pipeline.turns_ended >= 1, hass)
    assert e.runtime_data.talk.session is None


async def test_trigger_sai_dinh_dang_hoac_mic_tat(hass, r1, pcm_server, pipeline,
                                                    hass_client_no_auth):
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port,
                    wake_mode="speaker")
    client = await hass_client_no_auth()
    url = f"/api/r1_speaker/wake/{e.entry_id}?k={e.data['intercom_key']}"
    assert (await client.post(url, data="không phải json")).status == 400
    assert (await client.post(url, json={"event": "la"})).status == 400
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.r1_tat_mic"},
                                   blocking=True)
    r = await client.post(url, json={})
    assert r.status == 503 and "Mic đang tắt" in (await r.json())["loi"]
    assert e.runtime_data.talk.session is None


async def test_mic_tat_giua_phien_thi_dong_phien_va_phat_lai_nhac(
        hass, r1, pcm_server, pipeline, nhac):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music(MUSIC)
    await _talk(e).async_start("button")
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.r1_tat_mic"},
                                   blocking=True)
    assert _talk(e).session is None
    await _talk(e).async_settle()
    assert dmr.log == [("pause",), ("play",)]


async def test_mic_khong_noi_duoc_trong_phien_khong_treo(hass, r1, pipeline, nhac):
    """Chế độ loa, mic_host trỏ vào cổng đóng: phiên đóng sau hạn, nhạc phát lại."""
    s = PcmServer()
    await s.start()
    port = s.port
    await s.stop()                                              # cổng đóng
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=port, wake_mode="speaker")
    dmr = await nhac()
    dmr.start_music(MUSIC)
    with mock.patch.object(const, "SESSION_MIC_WAIT_S", 0.3):
        await _talk(e).async_start("button")
        await _cho(lambda: _talk(e).session is None, hass)
    await _talk(e).async_settle()
    assert dmr.log == [("pause",), ("play",)]
    assert hass.states.get(MICST).attributes["ket_thuc_gan_nhat"] == "mic_khong_noi_duoc"


# ── Bài học camera: những chỗ kiểm được bằng mock ──────────────────────────────────

async def test_mic_khong_bi_dat_ve_0_khi_khong_co_tieng_nguoi(hass, r1, pcm_server, pipeline):
    """(a) Camera: lọc ồn trên thiết bị cắt tiếng về 0 trong 35–94% thời gian. R1: HA không lọc/đặt
    0 luồng mic; tiếng rất nhỏ (dưới mọi ngưỡng) vẫn tới pipeline nguyên vẹn."""
    assert not hasattr(mic_mod, "Gate") and not hasattr(sat_mod, "Gate")
    await _san_sang(hass, r1, pcm_server, pipeline, nuoi=False)
    pipeline.got.clear()
    await _bom(hass, pcm_server, pcm(3), lambda: len(pipeline.got) >= 3 * MIC_CHUNK)   # ≈ -80 dBFS
    assert set(samples(bytes(pipeline.got))) == {3}             # không bị nuốt thành 0


@pytest.mark.gain_mac_dinh
async def test_tang_mic_mac_dinh_12db_chua_do_va_khuech_dai_khong_loc(hass, r1, pcm_server,
                                                                       pipeline):
    """(b) +12 dB mặc định, 0–30 dB; tuyến tính và chặn cứng, không lọc."""
    assert const.DEFAULT_MIC_GAIN_DB == 12.0 and const.MIC_GAIN_MAX == 30
    await _san_sang(hass, r1, pcm_server, pipeline, nuoi=False)
    st = hass.states.get("number.r1_tang_mic")
    assert st.state == "12.0" and st.attributes["min"] == 0 and st.attributes["max"] == 30
    pipeline.got.clear()
    await _bom(hass, pcm_server, pcm(1000), lambda: set(samples(bytes(pipeline.got[-MIC_CHUNK:]))) == {3981})
    await _bom(hass, pcm_server, pcm(3), lambda: set(samples(bytes(pipeline.got[-MIC_CHUNK:]))) == {11})


async def test_giu_mic_khi_loa_phat_nua_cong(hass, r1, pcm_server, pipeline):
    """(f) Đang nói (loa phát) thì không nghe bên kia."""
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    mic = e.runtime_data.mic
    nha = mic.hold()
    pipeline.got.clear()
    await pcm_server.send(pcm(777))
    await asyncio.sleep(0.2)
    assert 777 not in samples(bytes(pipeline.got))              # bị bỏ
    nha()
    await _bom(hass, pcm_server, pcm(888), lambda: 888 in samples(bytes(pipeline.got)))


async def test_do_tre_va_dem_nho(hass, r1, pcm_server, pipeline):
    """(d) Đệm nhỏ: trễ mic → pipeline đo trên mock, và đệm có trần (tụt hậu thì bỏ khúc cũ)."""
    assert const.MIC_QUEUE_CHUNKS * MIC_CHUNK / 2 / const.MIC_RATE <= 0.6   # trần ≈ 0,5 s
    await _san_sang(hass, r1, pcm_server, pipeline, nuoi=False)
    pipeline.got.clear()
    t0 = time.monotonic()
    # loa đẩy khúc đều (như mic thật); đo từ lúc khúc đầu rời loa tới lúc pipeline nhận được
    await _bom(hass, pcm_server, pcm(4242), lambda: 4242 in samples(bytes(pipeline.got)), giay=1.0)
    tre = time.monotonic() - t0
    assert tre < 0.3, f"trễ mic→pipeline {tre:.3f}s trên mock"
    # tụt hậu: bơm 100 khúc không ai lấy → hàng đợi không phình quá trần, giữ khúc MỚI nhất
    sat = _vet_tinh(hass)
    while not sat._hang.empty():
        sat._hang.get_nowait()
    for i in range(100):
        sat._khi_co_tieng(i.to_bytes(2, "little", signed=True) * 4)
    assert sat._hang.qsize() <= const.MIC_QUEUE_CHUNKS + 1
    assert sat._hang.get_nowait() == (99 - const.MIC_QUEUE_CHUNKS).to_bytes(2, "little") * 4 \
        or sat._hang.qsize() > 0
    ra = []
    while not sat._hang.empty():
        ra.append(sat._hang.get_nowait())
    assert ra[-1] == (99).to_bytes(2, "little") * 4             # khúc mới nhất còn nguyên


async def test_khoa_sai_401_mot_thong_bao_doi_khoa_thi_het(hass, r1, pcm_server, pipeline,
                                                          hass_client_no_auth, caplog):
    """(h) Khoá bị đổi → 401 có lời nhắn; thông báo/log MỘT lần dù bị gọi lặp; khoá đổi được."""
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port)
    client = await hass_client_no_auth()
    cu = e.data["intercom_key"]
    with mock.patch.object(cong_vao.persistent_notification, "async_create") as tao, \
            mock.patch.object(cong_vao.persistent_notification, "async_dismiss") as go:
        for _ in range(6):                                      # go2rtc/loa gọi lặp với khoá cũ
            r = await client.get(f"/api/r1_speaker/mic/{e.entry_id}?k=khoa-sai")
            assert r.status == 401 and r.headers["Retry-After"] == "60"
            assert "key" in (await r.text())
        assert tao.call_count == 1                              # KHÔNG lặp vô hạn
        assert sum("khoá SAI" in x.message for x in caplog.records) == 1
        assert cong_vao.so_lan_khoa_sai(hass, e.entry_id) == 6
        assert "khoá" in tao.call_args.kwargs["message"] and cu not in tao.call_args.kwargs["message"]
        # Đổi khoá bằng tuỳ chọn → khoá cũ chết, thông báo được gỡ, khoá mới chạy.
        res = await hass.config_entries.options.async_init(e.entry_id)
        res = await hass.config_entries.options.async_configure(
            res["flow_id"], {"host": "127.0.0.1", "port": r1.port, "rotate_intercom_key": True})
        assert res["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        moi = e.data["intercom_key"]
        assert moi != cu
        go.assert_called_once()
        assert cong_vao.so_lan_khoa_sai(hass, e.entry_id) == 0
        r = await client.get(f"/api/r1_speaker/ping/{e.entry_id}?k={cu}")
        assert r.status == 401
        r = await client.get(f"/api/r1_speaker/ping/{e.entry_id}?k={moi}")
        assert r.status == 200 and (await r.json()) == {"r1_speaker": True}
    assert (await client.post(f"/api/r1_speaker/wake/{e.entry_id}?k=sai", json={})).status == 401


# ── ha_url: kiểm ngay khi cấu hình, sai thì KHÔNG lưu ──────────────────────────────

async def _luu_ha_url(hass, e, url, **extra):
    res = await hass.config_entries.options.async_init(e.entry_id)
    return await hass.config_entries.options.async_configure(
        res["flow_id"], {"host": e.data["host"], "port": e.data["port"], "ha_url": url, **extra})


@pytest.mark.parametrize("url,loi", [
    ("ha.local:8123", "invalid_ha_url"), ("http://ha local", "invalid_ha_url"),
    ("http://ha.local/duong/dan", "invalid_ha_url"), ("http://u:p@ha.local", "invalid_ha_url"),
    ("ftp://ha.local", "invalid_ha_url"),
    ("http://127.0.0.1:8123", "ha_url_loopback"), ("http://localhost:8123", "ha_url_loopback"),
    ("http://0.0.0.0:8123", "ha_url_loopback"), ("http://[::1]:8123", "ha_url_loopback")])
async def test_ha_url_sai_khong_luu(hass, url, loi):
    """Loa nằm máy khác (tên miền giả .invalid) nên loopback KHÔNG BAO GIỜ đúng."""
    e = MockConfigEntry(domain=DOMAIN, data={"host": "loa.invalid", "port": 8080},
                        unique_id="loa.invalid:8080")
    e.add_to_hass(hass)
    res = await _luu_ha_url(hass, e, url)
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"ha_url": loi}
    assert e.options == {}                                      # không lưu gì


async def test_ha_url_khong_toi_duoc_bao_loi_khong_luu(hass, r1):
    e = await _them(hass, r1)
    s = PcmServer()
    await s.start()
    port = s.port
    await s.stop()                                              # không ai nghe ở cổng này
    res = await _luu_ha_url(hass, e, f"http://127.0.0.1:{port}")
    assert res["errors"] == {"ha_url": "ha_url_unreachable"} and e.options == {}


async def test_ha_url_dung_luu_va_dich_vu_dung_no(hass, r1, hass_client_no_auth):
    e = await _them(hass, r1)
    client = await hass_client_no_auth()
    goc = str(client.make_url("/")).rstrip("/")                 # máy chủ HA thật của test
    res = await _luu_ha_url(hass, e, goc + "/")
    assert res["type"] is FlowResultType.CREATE_ENTRY and e.options["ha_url"] == goc
    await hass.async_block_till_done()
    out = await hass.services.async_call(DOMAIN, "get_wake_endpoint", {"entity_id": LOA},
                                         blocking=True, return_response=True)
    key = e.data["intercom_key"]
    assert out == {"url": f"{goc}/api/r1_speaker/wake/{e.entry_id}?k={key}", "method": "POST",
                   "trang_thai": "CHO_PHIA_LOA"}
    src = await hass.services.async_call(DOMAIN, "get_intercom_source", {"entity_id": LOA},
                                         blocking=True, return_response=True)
    assert goc in src["talk"]                                   # dịch vụ cũ cũng theo ha_url đã kiểm
    # Khoá ẩn đã có (chế độ từ đánh thức) sống sót khi lưu lại form chính.
    hass.config_entries.async_update_entry(e, options={**e.options, "wake_mode": "speaker"})
    res = await _luu_ha_url(hass, e, goc)
    assert res["type"] is FlowResultType.CREATE_ENTRY and e.options["wake_mode"] == "speaker"


# ── Mic theo yêu cầu & bộ đàm chung chỗ với phiên Assist ───────────────────────────

async def test_mic_theo_yeu_cau_chi_noi_khi_co_nguoi_xin(pcm_server):
    """Từ đánh thức trên loa: HA KHÔNG nối (loa không có gì để gửi) cho tới khi có phiên xin."""
    m = mic_mod.R1Mic("127.0.0.1", pcm_server.port, on_demand=True)
    task = asyncio.create_task(m.run())
    try:
        await asyncio.sleep(0.4)
        assert pcm_server.accepted == 0 and not m.connected
        assert m.available                                      # chờ là chủ ý, không phải lỗi
        nha = m.want()
        await _cho(lambda: pcm_server.writers)
        for _ in range(100):
            if m.connected:
                break
            await pcm_server.send(pcm(10))
            await asyncio.sleep(0.02)
        assert m.connected and pcm_server.accepted == 1
        nha()
        await _cho(lambda: pcm_server.closed_by_client >= 1)    # hết người xin → ĐÓNG luồng
        await asyncio.sleep(0.4)
        assert not m.connected and pcm_server.accepted == 1     # và không tự nối lại
    finally:
        task.cancel()


async def test_bo_dam_bi_tu_choi_khi_dang_co_phien_assist(hass, r1, pcm_server, pipeline,
                                                          hass_client_no_auth):
    e = await _san_sang(hass, r1, pcm_server, pipeline, play_host="127.0.0.1", play_port=9)
    client = await hass_client_no_auth()
    await _talk(e).async_start("button")
    r = await client.post(f"/api/r1_speaker/intercom/{e.entry_id}?k={e.data['intercom_key']}",
                          data=b"x")
    assert r.status == 409 and "button" in await r.text()       # nói rõ ai đang giữ chỗ
    await _ket_thuc(e)
    assert e.runtime_data.talk.session is None



async def test_cong_tac_dam_thoai_chua_co_kenh_phat_thi_bao_loi(hass, r1, pcm_server, pipeline):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    with pytest.raises(HomeAssistantError, match="kênh phát"):
        await hass.services.async_call("switch", "turn_on", {"entity_id": INTERCOM}, blocking=True)
    assert _state(hass, INTERCOM) == "off"
    assert not e.runtime_data.duplex.luon and not e.runtime_data.duplex.active
