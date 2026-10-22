"""Bộ đàm nửa công: cổng thoại, kênh phát về loa, nửa công với mic, đường HTTP của go2rtc.

Loa giả: máy chủ TCP ở 127.0.0.1 (nhận PCM phát về loa, và phát PCM mic). KHÔNG chạm loa thật,
KHÔNG có dịch vụ thật phía loa (chưa tồn tại): đây là test HỢP ĐỒNG phía HA."""

import array
import asyncio
import json
from unittest import mock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import intercom as ic
from custom_components.r1_speaker import playback as pb
from custom_components.r1_speaker.const import (CONF_INTERCOM_KEY, DOMAIN, INTERCOM_RATE,
                                                MIC_CHUNK)
from custom_components.r1_speaker.settings import TalkSettings

# Dùng lại loa mic giả, pipeline giả và đồng hồ rút ngắn của test_mic.
from .test_mic import (SAT, PcmServer, _bom, _cho, _nhanh, _state, pcm, pcm_server,  # noqa: F401
                       pipeline, samples)

LINK = "binary_sensor.r1_bo_dam"
S = TalkSettings(threshold_db=-40.0, silence_s=0.3, preroll_s=0.1, tail_s=0.1)


def tieng8k(value: int, giay: float = 0.1) -> bytes:
    return array.array("h", [value] * int(INTERCOM_RATE * giay)).tobytes()


# ── Cổng thoại (thuần tính toán) ─────────────────────────────────────────────────

def test_level_db():
    assert ic.level_db(b"") == -120.0
    assert ic.level_db(tieng8k(0)) == -120.0
    assert ic.level_db(tieng8k(32767)) == pytest.approx(0.0, abs=0.01)
    assert ic.level_db(tieng8k(3277)) == pytest.approx(-20.0, abs=0.1)


def test_alaw_va_nang_tan_so():
    # Mẫu ITU: 0xD5 → +8, 0x55 → -8 (biên độ nhỏ nhất); 0xAA → biên độ lớn.
    assert samples(ic.alaw_to_pcm(b"\xd5\x55")) == [8, -8]
    assert samples(ic.alaw_to_pcm(b"\xaa"))[0] > 20000
    up = ic.upsample2x(array.array("h", [0, 100, 200]).tobytes())
    assert samples(up) == [0, 50, 100, 150, 200, 200]          # gấp đôi, nội suy tuyến tính
    assert ic.upsample2x(b"") == b""


def test_gate_im_thi_dong_co_tieng_thi_mo():
    g = ic.Gate(INTERCOM_RATE, S)
    assert not g.feed(tieng8k(0)).opened and not g.is_open     # yên: không mở
    ra = g.feed(tieng8k(3000))
    assert ra.opened and g.is_open
    assert g.feed(tieng8k(3000)).audio == tieng8k(3000)         # đang mở: chuyển nguyên
    assert not g.feed(tieng8k(0)).closed                        # im 0,1 s < 0,3 s
    assert not g.feed(tieng8k(0)).closed
    cuoi = g.feed(tieng8k(0))                                   # im đủ 0,3 s
    assert cuoi.closed and not g.is_open
    assert g.feed(tieng8k(3000)).opened                         # nói tiếp thì mở lại


def test_gate_giu_dau_cau_dung_preroll():
    g = ic.Gate(INTERCOM_RATE, S)
    for _ in range(5):
        g.feed(tieng8k(0))                                      # 0,5 s yên, preroll chỉ 0,1 s
    ra = g.feed(tieng8k(3000))
    assert ra.audio == tieng8k(0) + tieng8k(3000)               # đúng 0,1 s trước tiếng
    g2 = ic.Gate(INTERCOM_RATE, TalkSettings(-40.0, 0.3, 0.0, 0.1))
    g2.feed(tieng8k(0))
    assert g2.feed(tieng8k(3000)).audio == tieng8k(3000)        # preroll 0: không giữ gì


def test_gate_tham_so_quyet_dinh_nguong():
    """Ngưỡng là THAM SỐ, không mã cứng: cùng một khúc mở ở ngưỡng thấp, không mở ở ngưỡng cao."""
    khuc = tieng8k(330)                                         # ~ -40 dBFS
    assert ic.Gate(INTERCOM_RATE, TalkSettings(-50.0, 0.3, 0.1, 0.1)).feed(khuc).opened
    assert not ic.Gate(INTERCOM_RATE, TalkSettings(-30.0, 0.3, 0.1, 0.1)).feed(khuc).opened


def test_nguon_go2rtc_khong_dau_cach_hay_thang_trong_url():
    nguon = ic.go2rtc_source("http://ha.local:8123/", "ENTRYID", "KHOA_abc-1")
    talk = nguon["talk"]
    assert talk.startswith("exec:ffmpeg") and "-probesize 32 -analyzeduration 0" in talk
    assert "-f alaw -ar 8000" in talk and "#backchannel=1#audio=alaw/8000" in talk
    url = talk.split("-method POST ")[1].split("#")[0]
    assert url == "http://ha.local:8123/api/r1_speaker/intercom/ENTRYID?k=KHOA_abc-1"
    assert " " not in url and "#" not in url
    assert "api/r1_speaker/mic/ENTRYID?k=KHOA_abc-1" in nguon["listen"]
    assert "{output}" in nguon["listen"]


# ── Kênh phát về loa ────────────────────────────────────────────────────────────

class PlayServer:
    """Phía loa GIẢ nhận PCM phát về: gom byte, đếm số kết nối."""

    def __init__(self):
        self.port = 0
        self.data = bytearray()
        self.connections = 0
        self.closed = 0
        self._server = None
        self._writers = []

    async def _on_conn(self, reader, writer):
        self.connections += 1
        self._writers.append(writer)
        while chunk := await reader.read(4096):
            self.data += chunk
        self.closed += 1
        writer.close()

    async def start(self):
        self._server = await asyncio.start_server(self._on_conn, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        for w in self._writers:      # đóng cả kết nối còn mở: wait_closed() đợi chúng
            w.close()
        self._server.close()
        await self._server.wait_closed()


@pytest.fixture
async def loa_phat():
    s = PlayServer()
    await s.start()
    yield s
    await s.stop()


async def _nguon(*khuc):
    for k in khuc:
        yield k


async def test_playback_gui_dung_byte_va_dong_ket_noi(loa_phat):
    p = pb.R1Playback("127.0.0.1", loa_phat.port)
    giay = await p.async_play(_nguon(pcm(1, 1600), pcm(2, 1600)))
    await _cho(lambda: loa_phat.closed == 1)
    assert bytes(loa_phat.data) == pcm(1, 1600) + pcm(2, 1600)
    assert giay == pytest.approx(0.2)                           # 3200 mẫu / 16 kHz
    assert p.ok is True


async def test_playback_chua_cau_hinh_hoac_khong_noi_duoc(loa_phat, caplog):
    with pytest.raises(pb.R1PlayError):
        await pb.R1Playback("127.0.0.1", 0).async_play(_nguon(b"\0\0"))
    cong = loa_phat.port
    await loa_phat.stop()
    p = pb.R1Playback("127.0.0.1", cong)
    for _ in range(3):
        with pytest.raises(pb.R1PlayError):
            await p.async_play(_nguon(b"\0\0"))
    assert p.ok is False
    assert sum("R1 playback" in r.message for r in caplog.records
               if r.levelname == "WARNING") == 1               # không dồn log
    await loa_phat.start()                                     # fixture sẽ stop lần nữa
    loa_phat.port, p.port = loa_phat.port, loa_phat.port
    await p.async_play(_nguon(b"\0\0"))
    assert p.ok is True                                        # khôi phục


# ── Nửa công trên tích hợp đầy đủ ───────────────────────────────────────────────

async def _them(hass, r1, **options) -> MockConfigEntry:
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options=options, unique_id=f"127.0.0.1:{r1.port}")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


def _tat_ca(e):
    return {"talk_threshold_db": S.threshold_db, "talk_silence_s": S.silence_s,
            "talk_preroll_s": S.preroll_s, "talk_tail_s": S.tail_s}


async def test_nua_cong_khong_gui_mic_khi_dang_phat_va_mo_lai_sau_im(
        hass, r1, pcm_server, loa_phat, pipeline):
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port,
                    play_port=loa_phat.port, **_tat_ca(None))
    c = e.runtime_data
    await _cho(lambda: pcm_server.writers)
    # Trước khi nói: mic chảy vào pipeline như thường.
    await _bom(hass, pcm_server, pcm(11), lambda: 11 in samples(bytes(pipeline.got)))
    assert not c.mic.holding

    # Có tiếng người: cổng mở, kênh phát nối, mic bị giữ.
    for _ in range(3):
        c.intercom.feed(tieng8k(3000))
    await _cho(lambda: c.mic.holding and loa_phat.data, hass)
    assert c.intercom.talking and loa_phat.connections == 1
    pipeline.got.clear()
    for _ in range(10):                          # mic nghe thấy loa (7) phải bị BỎ
        await pcm_server.send(pcm(7))
        await asyncio.sleep(0.02)
    assert 7 not in samples(bytes(pipeline.got))
    assert _state(hass, SAT) == "idle"           # luồng mic vẫn sống, chỉ không phát đi

    # Im đủ lâu: cổng đóng, kết nối phát đóng, sau tail mic được nhả.
    for _ in range(4):
        c.intercom.feed(tieng8k(0))
    await _cho(lambda: loa_phat.closed == 1 and not c.mic.holding, hass)
    assert not c.intercom.talking
    await _bom(hass, pcm_server, pcm(9), lambda: 9 in samples(bytes(pipeline.got)))

    # Tiếng phát ra đúng 16 kHz: mọi mẫu giọng nói là 3000, gấp đôi số mẫu 8 kHz.
    played = samples(bytes(loa_phat.data))
    assert played.count(3000) >= 2 * 3 * (INTERCOM_RATE // 10) - 1        # 3 khúc × 0,1 s × 16 kHz
    assert set(played) <= {0, 1500, 3000}


async def test_giu_dau_cau_khi_mo(hass, r1, loa_phat, pipeline):
    e = await _them(hass, r1, play_port=loa_phat.port, **_tat_ca(None))
    c = e.runtime_data
    for _ in range(4):
        c.intercom.feed(tieng8k(0))              # yên 0,4 s; preroll chỉ giữ 0,1 s
    c.intercom.feed(tieng8k(3000))
    c.intercom.stop_talking()
    await _cho(lambda: loa_phat.closed == 1, hass)
    played = samples(bytes(loa_phat.data))
    # 0,1 s yên (1600 mẫu @16 kHz) rồi 0,1 s tiếng (1600 mẫu); đúng một mẫu chuyển tiếp 1500
    # do nội suy tuyến tính giữa mẫu yên cuối và mẫu tiếng đầu.
    assert played == [0] * 1599 + [1500] + [3000] * 1600


async def test_kenh_phat_hong_thi_khong_sap_va_nha_mic(hass, r1, pcm_server, caplog):
    dong = PlayServer()
    await dong.start()
    cong = dong.port
    await dong.stop()                            # cổng đóng: loa không nhận
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port,
                    play_port=cong, **_tat_ca(None))
    c = e.runtime_data
    await _cho(lambda: pcm_server.writers)
    assert hass.states.get(LINK).state == STATE_UNKNOWN          # chưa thử
    for _ in range(3):
        c.intercom.feed(tieng8k(3000))           # không ném ra ngoài
    await _cho(lambda: hass.states.get(LINK).state == STATE_OFF, hass)
    await _cho(lambda: not c.mic.holding, hass)                  # mic không kẹt
    assert not c.intercom.talking
    assert _state(hass, "sensor.phicomm_r1_device_state") not in (None, STATE_UNAVAILABLE)
    for _ in range(4):
        c.intercom.feed(tieng8k(0))              # đóng cổng sạch sau lỗi
    c.intercom.feed(tieng8k(3000))               # và mở lại được
    await _cho(lambda: c.playback.ok is False, hass)

    # Loa phía phát sống lại cùng cổng: tự khôi phục ở lần nói kế.
    dong.port = cong
    await dong.start()
    try:
        for _ in range(4):
            c.intercom.feed(tieng8k(0))
        c.intercom.feed(tieng8k(3000))
        c.intercom.stop_talking()
        await _cho(lambda: hass.states.get(LINK).state == STATE_ON, hass)
    finally:
        await dong.stop()


async def test_chua_cau_hinh_phat_thi_bo_dam_tat(hass, r1):
    e = await _them(hass, r1)
    assert hass.states.get(LINK).state == STATE_UNAVAILABLE
    assert not e.runtime_data.playback.configured


# ── Đường HTTP cho go2rtc ───────────────────────────────────────────────────────

async def test_post_bo_dam_khoa_sai_va_chua_cau_hinh(hass, r1, hass_client_no_auth):
    e = await _them(hass, r1)
    cl = await hass_client_no_auth()
    khoa = e.data[CONF_INTERCOM_KEY]
    assert len(khoa) >= 24
    url = f"/api/r1_speaker/intercom/{e.entry_id}"
    assert (await cl.post(url, data=b"x")).status == 401
    assert (await cl.post(url + "?k=sai", data=b"x")).status == 401
    assert (await cl.post(f"/api/r1_speaker/intercom/khong-co?k={khoa}", data=b"x")).status == 401
    assert (await cl.post(f"{url}?k={khoa}", data=b"x")).status == 503      # chưa có kênh phát


async def test_post_bo_dam_phat_ra_loa(hass, r1, loa_phat, hass_client_no_auth):
    e = await _them(hass, r1, play_port=loa_phat.port, **_tat_ca(None))
    cl = await hass_client_no_auth()
    khoa = e.data[CONF_INTERCOM_KEY]
    alaw_to = b"\xaa" * 1600                      # 0,2 s tiếng lớn (A-law 8 kHz)
    alaw_im = b"\xd5" * 4000                      # 0,5 s gần như im lặng
    r = await cl.post(f"/api/r1_speaker/intercom/{e.entry_id}?k={khoa}",
                      data=alaw_im[:800] + alaw_to + alaw_im)
    assert r.status == 200
    assert (await r.json())["seconds"] > 0.15
    await _cho(lambda: loa_phat.closed == 1, hass)
    played = samples(bytes(loa_phat.data))
    assert max(played) > 20000 and len(played) >= 2 * 1600


async def test_post_thu_hai_dong_thoi_bi_tu_choi(hass, r1, loa_phat, hass_client_no_auth):
    e = await _them(hass, r1, play_port=loa_phat.port)
    e.runtime_data.intercom.busy = True
    cl = await hass_client_no_auth()
    r = await cl.post(f"/api/r1_speaker/intercom/{e.entry_id}?k={e.data[CONF_INTERCOM_KEY]}",
                      data=b"x")
    assert r.status == 409


async def test_get_mic_phat_pcm_va_bi_chan_khi_tat(hass, r1, pcm_server, hass_client_no_auth):
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port)
    cl = await hass_client_no_auth()
    khoa = e.data[CONF_INTERCOM_KEY]
    url = f"/api/r1_speaker/mic/{e.entry_id}"
    assert (await cl.get(url + "?k=sai")).status == 401
    await _cho(lambda: pcm_server.writers)
    # chưa có khúc nào → mic chưa "available" → 503
    assert (await cl.get(f"{url}?k={khoa}")).status == 503
    await pcm_server.send(pcm(5))
    await _cho(lambda: e.runtime_data.mic.available, hass)
    r = await cl.get(f"{url}?k={khoa}")
    assert r.status == 200 and r.headers["Content-Type"].startswith("audio/L16;rate=16000")
    await pcm_server.send(pcm(1234))
    got = b""
    while 1234 not in samples(got):
        got += await asyncio.wait_for(r.content.readany(), 3)
    r.close()
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.r1_tat_mic"},
                                   blocking=True)
    assert (await cl.get(f"{url}?k={khoa}")).status == 503     # tắt mic: không có luồng


async def test_dich_vu_nguon_bo_dam(hass, r1):
    e = await _them(hass, r1)
    kq = await hass.services.async_call(
        DOMAIN, "get_intercom_source",
        {"entity_id": "media_player.r1_loa", "ha_url": "http://ha.local:8123"},
        blocking=True, return_response=True)
    assert f"http://ha.local:8123/api/r1_speaker/intercom/{e.entry_id}?k=" \
           f"{e.data[CONF_INTERCOM_KEY]}#backchannel=1" in kq["talk"]
    assert "api/r1_speaker/mic/" in kq["listen"]
    with pytest.raises(Exception):
        await hass.services.async_call(
            DOMAIN, "get_intercom_source",
            {"entity_id": "media_player.r1_loa", "ha_url": "http://x y"}, blocking=True,
            return_response=True)


async def test_khoa_bo_dam_giu_nguyen_qua_nap_lai(hass, r1):
    e = await _them(hass, r1)
    khoa = e.data[CONF_INTERCOM_KEY]
    assert await hass.config_entries.async_reload(e.entry_id)
    assert e.data[CONF_INTERCOM_KEY] == khoa


async def test_dich_vu_nhac_mac_dinh_khong_dang_ky(hass, r1):
    await _them(hass, r1)
    for ten in ("music_play", "music_search", "music_control", "music_playlist"):
        assert not hass.services.has_service(DOMAIN, ten)
    assert hass.services.has_service(DOMAIN, "get_intercom_source")
