"""NV246 — đàm thoại SONG CÔNG kích hoạt từ HA: VAD chỉ cho tiếng người qua (kèm đệm
trước/sau), HA phát xuống loa đồng thời mà mic không bị giữ, hạn phiên tối đa, mất kết nối
đóng sạch/mở lại được, tranh chỗ với Assist/bộ đàm. VAD giả lập theo dấu mẫu (tiêm vào),
một ca dùng microVAD THẬT với tín hiệu im lặng. Loa/mic/phát đều giả ở 127.0.0.1."""

import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import const
from custom_components.r1_speaker.const import DOMAIN
from custom_components.r1_speaker.dam_thoai import R1SessionBusy, R1Talk
from custom_components.r1_speaker.mic import R1Mic
from custom_components.r1_speaker.playback import R1Playback
from custom_components.r1_speaker.settings import DuplexSettings, duplex_settings
from custom_components.r1_speaker.song_cong import VAD_FRAME, R1Duplex, VadGate

from .test_mic import PcmServer, pcm_server  # noqa: F401  (fixture dùng lại)


def khung10(gia_tri: int) -> bytes:
    """Một khung VAD 10 ms: 160 mẫu PCM16 cùng giá trị."""
    return gia_tri.to_bytes(2, "little", signed=True) * (VAD_FRAME // 2)


class VadGia:
    """VAD giả: khung có mẫu đủ lớn (|mẫu| >= 1000) là «tiếng người» (xác suất 0.9)."""

    def __init__(self):
        self.reset_lan = 0

    def process_10ms(self, khung: bytes) -> float:
        mau = [int.from_bytes(khung[i:i + 2], "little", signed=True)
               for i in range(0, len(khung), 2)]
        return 0.9 if max(abs(m) for m in mau) >= 1000 else 0.0

    def reset(self):
        self.reset_lan += 1


async def cho(fn, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    han = loop.time() + timeout
    while loop.time() < han:
        if fn():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("hết giờ chờ điều kiện")


class PlayServer:
    """Loa giả phía phát: TCP ghi lại mọi byte HA bơm xuống."""

    def __init__(self):
        self.port = 0
        self.data = bytearray()
        self._server = None

    async def _on(self, reader, writer):
        try:
            while b := await reader.read(65536):
                self.data += b
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def start(self):
        self._server = await asyncio.start_server(self._on, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


@pytest.fixture
async def play_server():
    s = PlayServer()
    await s.start()
    yield s
    await s.stop()


def tao_phien(hass, play_port, settings=None):
    mic = R1Mic("127.0.0.1", 8765)
    talk = R1Talk(hass, mic, None)
    playback = R1Playback("127.0.0.1", play_port)
    d = R1Duplex(hass, talk, mic, playback, settings or DuplexSettings(),
                 vad_factory=VadGia)
    return d, mic, talk


# ── VadGate: chỉ tiếng người qua, kèm đệm ─────────────────────────────────────────

def test_vad_gate_chi_chuyen_tieng_nguoi_kem_dem_truoc_sau():
    s = DuplexSettings(vad_threshold=0.5, preroll_s=0.03, hangover_s=0.02)
    g = VadGate(s, VadGia())
    nen = [khung10(100 + i) for i in range(5)]            # 5 khung nền (giá trị phân biệt)
    noi = [khung10(5000), khung10(5001)]                  # 2 khung tiếng người
    ra = []
    for k in nen + noi + [khung10(200 + i) for i in range(5)]:
        ra += g.feed(k)
    # đệm trước = 3 khung nền NGAY TRƯỚC câu; đệm sau = 2 khung nền ngay sau câu
    assert ra == nen[2:] + noi + [khung10(200), khung10(201)]
    assert g.seen == 12 and g.passed == 7


def test_vad_gate_nhan_khuc_le_giu_phan_du():
    g = VadGate(DuplexSettings(preroll_s=0.0, hangover_s=0.0), VadGia())
    k = khung10(5000)
    assert g.feed(k[:100]) == []                          # chưa đủ một khung 10 ms
    assert g.feed(k[100:]) == [k]
    assert g.feed(khung10(100)) == []                     # nền, không đệm → bỏ


def test_vad_that_im_lang_khong_qua_cong():
    g = VadGate(DuplexSettings())                         # microVAD THẬT của HA
    assert g.feed(khung10(0) * 20) == []
    assert g.seen == 20 and g.passed == 0
    g.reset()
    assert g.seen == 0


def test_duplex_settings_doc_tu_options_va_mac_dinh_chua_do():
    e = SimpleNamespace(data={}, options={"duplex_vad_threshold": 0.7, "duplex_max_s": 600})
    s = duplex_settings(e)
    assert s.vad_threshold == 0.7 and s.max_s == 600.0
    assert s.preroll_s == const.DEFAULT_DUPLEX_PREROLL and s.duck is False
    mac_dinh = duplex_settings(SimpleNamespace(data={}, options={}))
    assert mac_dinh.max_s == 1800.0                       # 30 phút theo đề xuất, CHƯA ĐO


# ── Phiên: hai chiều chạy song song ───────────────────────────────────────────────

async def test_phien_song_cong_hai_chieu_chay_song_song(hass, play_server):
    d, mic, talk = tao_phien(hass, play_server.port,
                             DuplexSettings(preroll_s=0.0, hangover_s=0.0))
    nhan: list[bytes] = []
    d.add_audio_listener(nhan.append)
    mic.note_inbound(True)                                # APK đã nối vào đầu nhận NV244
    await d.async_start()
    assert talk.session_kind == "song_cong" and d.active and d.dang_nghe
    # Mic: nền bị VAD bỏ, tiếng người qua.
    mic.feed_inbound(khung10(100) * 4 + khung10(5000) * 2)
    assert nhan == [khung10(5000)] * 2
    # HA phát xuống loa ĐỒNG THỜI: khúc vào là phát ngay, mic KHÔNG bị giữ (khác nửa công).
    d.feed_playback(khung10(7000))
    await cho(lambda: len(play_server.data) >= VAD_FRAME)
    assert bytes(play_server.data) == khung10(7000)
    assert not mic.holding
    mic.feed_inbound(khung10(5000))                       # mic vẫn chảy trong lúc loa phát
    assert len(nhan) == 3
    attrs = d.as_attributes()
    assert attrs["song_cong"] is True and attrs["song_cong_khung_chuyen"] == 3
    d.end("nguoi_dung_ket_thuc")
    await d.async_settle()
    assert talk.session is None and d.last_end == "nguoi_dung_ket_thuc"
    assert d.play_seconds > 0


async def test_phien_khong_dong_theo_im_lang(hass, play_server):
    """Khác cổng thoại nửa công: im lặng lâu KHÔNG đóng phiên (chỉ HA/hạn tối đa mới đóng)."""
    d, mic, talk = tao_phien(hass, play_server.port,
                             DuplexSettings(max_s=60.0, preroll_s=0.0, hangover_s=0.0))
    mic.note_inbound(True)
    await d.async_start()
    mic.feed_inbound(khung10(100) * 50)                   # 0.5 giây toàn tiếng nền
    await asyncio.sleep(0.3)
    assert d.active and talk.session_kind == "song_cong"  # vẫn mở, không tự đóng
    d.end("nguoi_dung_ket_thuc")
    await d.async_settle()


async def test_het_gio_toi_da_dong_phien(hass, play_server):
    d, mic, talk = tao_phien(hass, play_server.port, DuplexSettings(max_s=0.2))
    mic.note_inbound(True)
    await d.async_start()
    await cho(lambda: not d.active)
    assert d.last_end == "het_gio" and talk.session is None
    await d.async_settle()


async def test_mat_ket_noi_dong_sach_va_mo_lai_duoc(hass, play_server):
    d, mic, talk = tao_phien(hass, play_server.port,
                             DuplexSettings(preroll_s=0.0, hangover_s=0.0))
    nhan: list[bytes] = []
    d.add_audio_listener(nhan.append)
    mic.note_inbound(True)
    await d.async_start()
    mic.feed_inbound(khung10(5000))
    assert len(nhan) == 1
    mic.note_inbound(False)                               # loa đứt giữa chừng
    assert not d.active and d.last_end == "mat_ket_noi" and talk.session is None
    mic.note_inbound(True)                                # nối lại → mở phiên mới được
    await d.async_start()
    assert d.active
    mic.feed_inbound(khung10(5000))
    assert len(nhan) == 2
    d.end("nguoi_dung_ket_thuc")
    await d.async_settle()


async def test_tranh_cho_voi_assist_va_bo_dam(hass, play_server):
    d, mic, talk = tao_phien(hass, play_server.port)
    mic.note_inbound(True)
    nha = talk.claim("bo_dam")                            # bộ đàm đang chiếm phiên
    with pytest.raises(R1SessionBusy):
        await d.async_start()
    nha()
    await d.async_start()                                 # song công mở → bên khác bị từ chối
    with pytest.raises(R1SessionBusy):
        talk.claim("bo_dam")
    d.end("nguoi_dung_ket_thuc")
    await d.async_settle()


async def test_mo_phien_thieu_cau_hinh_bao_loi_ro(hass):
    mic = R1Mic("", 8765)                                 # chưa cấu hình mic
    talk = R1Talk(hass, mic, None)
    d = R1Duplex(hass, talk, mic, R1Playback("127.0.0.1", 9), DuplexSettings(),
                 vad_factory=VadGia)
    with pytest.raises(HomeAssistantError, match="mic_host"):
        await d.async_start()
    mic2 = R1Mic("127.0.0.1", 8765)
    d2 = R1Duplex(hass, R1Talk(hass, mic2, None), mic2, R1Playback("", 0),
                  DuplexSettings(), vad_factory=VadGia)
    with pytest.raises(HomeAssistantError, match="play_port"):
        await d2.async_start()


# ── Vọng: không hú vô hạn; cắt vọng tuỳ chọn ──────────────────────────────────────

async def test_vong_khong_hu_vo_han(hass, play_server):
    """Vòng lặp mô phỏng: khung đã chuyển được phát ra loa, mic thu lại thành tiếng vọng
    (không còn dấu tiếng người) → VAD chặn, số khung chuyển KHÔNG tăng thêm, phiên không
    tự khuếch đại."""
    d, mic, talk = tao_phien(hass, play_server.port,
                             DuplexSettings(preroll_s=0.0, hangover_s=0.0))
    nhan: list[bytes] = []
    d.add_audio_listener(nhan.append)
    mic.note_inbound(True)
    await d.async_start()
    mic.feed_inbound(khung10(5000))
    assert len(nhan) == 1
    for _ in range(20):                                   # vọng quay lại 20 vòng
        mic.feed_inbound(khung10(120))                    # vọng: mẫu nhỏ, VAD bảo không phải người
        d.feed_playback(khung10(120))
    await cho(lambda: len(play_server.data) >= 20 * VAD_FRAME)
    assert len(nhan) == 1 and d.active                    # không tăng, không hú, phiên còn mở
    d.end("nguoi_dung_ket_thuc")
    await d.async_settle()


def _chunk_nho_co_dau_nguoi() -> bytes:
    """6 khung: khung đầu có MỘT mẫu lớn (VAD giả đánh là tiếng người) nhưng mức cả khúc
    rất nhỏ (≈ -46 dBFS) — đúng dạng tiếng vọng yếu."""
    dau = bytearray(khung10(0))
    dau[0:2] = (5000).to_bytes(2, "little", signed=True)
    return bytes(dau) + khung10(0) * 5


async def test_cat_vong_tuy_chon_mac_dinh_tat(hass, play_server):
    # Mặc định TẮT: khung nhỏ có tiếng người vẫn qua khi HA đang phát (chấp nhận vọng).
    d, mic, talk = tao_phien(hass, play_server.port,
                             DuplexSettings(preroll_s=0.0, hangover_s=0.0, duck=False))
    nhan: list[bytes] = []
    d.add_audio_listener(nhan.append)
    mic.note_inbound(True)
    await d.async_start()
    d.feed_playback(khung10(7000))
    await cho(lambda: len(play_server.data) >= VAD_FRAME)
    mic.feed_inbound(_chunk_nho_co_dau_nguoi())
    assert len(nhan) == 1                                 # chỉ khung đầu (có dấu người) qua
    d.end("nguoi_dung_ket_thuc")
    await d.async_settle()

    # BẬT cắt vọng: cùng khung nhỏ bị bỏ cả; khung TO (tiếng người thật gần mic) vẫn qua.
    d2, mic2, _ = tao_phien(hass, play_server.port,
                            DuplexSettings(preroll_s=0.0, hangover_s=0.0,
                                           duck=True, duck_db=-45.0))
    nhan2: list[bytes] = []
    d2.add_audio_listener(nhan2.append)
    mic2.note_inbound(True)
    await d2.async_start()
    d2.feed_playback(khung10(7000))
    await cho(lambda: len(play_server.data) >= 2 * VAD_FRAME)
    mic2.feed_inbound(_chunk_nho_co_dau_nguoi())
    assert nhan2 == [] and d2.duck_dropped == 6
    mic2.feed_inbound(khung10(5000) * 6)                  # tiếng to: không bị cắt
    assert len(nhan2) == 6
    d2.end("nguoi_dung_ket_thuc")
    await d2.async_settle()


# ── Tích hợp HA thật: dịch vụ mở/dừng, sensor, DuplexView ─────────────────────────

LOA = "media_player.r1_loa"
MICST = "sensor.r1_trang_thai_mic"


async def _them(hass, r1, **options) -> MockConfigEntry:
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options=options, unique_id=f"127.0.0.1:{r1.port}")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def test_dich_vu_mo_dung_va_trang_thai_sensor(hass, r1, pcm_server, play_server):
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port,
                    play_port=play_server.port)
    c = e.runtime_data
    assert hass.services.has_service(DOMAIN, "start_duplex")
    await hass.services.async_call(DOMAIN, "start_duplex", {"entity_id": LOA}, blocking=True)
    assert c.duplex.active and c.talk.session_kind == "song_cong"
    st = hass.states.get(MICST)
    assert st.attributes["phien"] == "song_cong" and st.attributes["song_cong"] is True
    # Mic thật (microVAD thật): bơm khung im lặng qua đầu vào chung → cổng VAD đếm khung vào.
    c.mic.note_inbound(True)
    c.mic.feed_inbound(khung10(0) * 6)
    assert c.duplex.as_attributes()["song_cong_khung_vao"] == 6
    st = hass.states.get(MICST)                           # đọc lại state sau khi mic nối
    assert st.attributes["song_cong_dang_nghe"] is True
    await hass.services.async_call(DOMAIN, "stop_duplex", {"entity_id": LOA}, blocking=True)
    assert not c.duplex.active and c.talk.session is None
    assert hass.states.get(MICST).attributes["song_cong"] is False
    assert hass.states.get(MICST).attributes["song_cong_ket_thuc_gan_nhat"] == \
        "nguoi_dung_ket_thuc"


async def test_duplex_view_phat_xuong_loa_va_dong_phien(hass, r1, pcm_server, play_server,
                                                        hass_client_no_auth):
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port,
                    play_port=play_server.port)
    c = e.runtime_data
    client = await hass_client_no_auth()
    url = f"/api/r1_speaker/duplex/{e.entry_id}?k={e.data['intercom_key']}"
    # Khoá sai → 401 như các view khác.
    assert (await client.post(
        f"/api/r1_speaker/duplex/{e.entry_id}?k=sai", data=b"x")).status == 401
    # POST tự mở phiên, bơm PCM xuống loa; POST đóng → phiên đóng sạch.
    mot_giay = khung10(7000) * 100                        # 32000 byte = đúng 1.0 giây PCM
    r = await client.post(url, data=mot_giay)
    assert r.status == 200 and (await r.json())["seconds"] == 1.0
    assert bytes(play_server.data) == mot_giay
    assert not c.duplex.active and c.talk.session is None
    assert c.duplex.last_end == "nguoi_dung_ket_thuc"


async def test_tat_mic_giua_phien_song_cong_dong_phien_va_ngat_loa(hass, play_server):
    """switch.r1_tat_mic trong lúc song công: đầu nhận NGẮT kết nối loa → phiên đóng sạch
    (mat_ket_noi), tiếng không còn tới điện thoại. Ca biên thêm khi đóng gói R1."""
    from custom_components.r1_speaker.mic_server import R1MicServer
    d, mic, talk = tao_phien(hass, play_server.port,
                             DuplexSettings(preroll_s=0.0, hangover_s=0.0))
    server = R1MicServer(mic, 0, "khoa-gia", "127.0.0.1")
    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        hello = b'{"type":"hello","version":1,"key":"khoa-gia"}'
        writer.write(len(hello).to_bytes(4, "big") + hello)
        await writer.drain()
        await cho(lambda: server.receiving)
        await d.async_start()
        nhan: list[bytes] = []
        d.add_audio_listener(nhan.append)
        mic.set_muted(True)
        assert await asyncio.wait_for(reader.read(), 3) == b""   # loa bị ngắt
        assert not d.active and d.last_end == "mat_ket_noi" and talk.session is None
        assert nhan == []
        writer.close()
    finally:
        await server.async_close()
