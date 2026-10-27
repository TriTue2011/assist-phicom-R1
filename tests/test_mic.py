"""assist_satellite.r1 + mic: luồng PCM giả qua máy chủ TCP cục bộ (127.0.0.1), pipeline Assist
được mock ở mức HA (``async_accept_pipeline_from_satellite``). KHÔNG chạm loa thật."""

import array
import asyncio
from unittest import mock

import pytest
from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType, PipelineStage
from homeassistant.components.assist_satellite import AssistSatelliteAnnouncement
from homeassistant.components.assist_satellite.const import DATA_COMPONENT
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import assist_satellite as sat_mod
from custom_components.r1_speaker import media_player as mp_mod
from custom_components.r1_speaker import mic as mic_mod
from custom_components.r1_speaker.const import DOMAIN, MIC_CHUNK

SAT, GAIN, MUTE, SEL, LOA = ("assist_satellite.r1", "number.r1_tang_mic", "switch.r1_tat_mic",
                             "select.r1_tro_ly", "media_player.r1_loa")


def pcm(value: int, n: int = MIC_CHUNK // 2) -> bytes:
    return array.array("h", [value] * n).tobytes()


def samples(b: bytes) -> list[int]:
    a = array.array("h")
    a.frombytes(b)
    return list(a)


class PcmServer:
    """Loa giả phía mic: TCP, ghi lại số kết nối, phát khúc PCM khi được bảo."""

    def __init__(self):
        self.port = 0
        self.writers: list[asyncio.StreamWriter] = []
        self.accepted = 0
        self.closed_by_client = 0
        self._server = None

    async def _on_conn(self, reader, writer):
        self.accepted += 1
        self.writers.append(writer)
        await reader.read()                  # tới khi máy khách đóng
        self.closed_by_client += 1

    async def start(self):
        self._server = await asyncio.start_server(self._on_conn, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        for w in self.writers:
            w.close()
        self.writers.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def drop_clients(self):
        for w in self.writers:
            w.close()
        self.writers.clear()

    async def send(self, data: bytes):
        for w in list(self.writers):
            try:
                w.write(data)
                await w.drain()
            except ConnectionError:           # máy khách vừa đóng (tắt mic / nối lại)
                self.writers.remove(w)


@pytest.fixture
async def pcm_server():
    s = PcmServer()
    await s.start()
    yield s
    await s.stop()


class FakePipeline:
    """Thay ``async_accept_pipeline_from_satellite``: gom mọi byte vào ``got``."""

    def __init__(self):
        self.got = bytearray()
        self.turns: list[PipelineStage] = []
        self.turns_ended = 0

    async def __call__(self, entity, audio_stream, start_stage=PipelineStage.STT, **kw):
        self.turns.append(start_stage)
        async for chunk in audio_stream:
            self.got += chunk
        self.turns_ended += 1


@pytest.fixture
def pipeline():
    f = FakePipeline()
    async def thay(self, **kw):
        await f(self, **kw)

    # Môi trường test không có engine từ đánh thức thật: coi như đã có để vệ tinh mở pipeline (giả) như thường.
    with mock.patch(
            "homeassistant.components.assist_satellite.entity.AssistSatelliteEntity."
            "async_accept_pipeline_from_satellite", new=thay), \
            mock.patch.object(sat_mod.R1Satellite, "_thieu_tu_danh_thuc", return_value=None):
        yield f


@pytest.fixture(autouse=True)
def _nhanh():
    with mock.patch.object(mic_mod, "RETRY_DELAY", 0.1), \
            mock.patch.object(mic_mod, "READ_TIMEOUT", 0.6), \
            mock.patch.object(mic_mod, "CONNECT_TIMEOUT", 0.5), \
            mock.patch.object(sat_mod, "RECHECK", 0.05), \
            mock.patch.object(sat_mod, "TAIL", 0), \
            mock.patch.object(sat_mod, "POLL", 0.02), \
            mock.patch.object(sat_mod, "PLAY_START_WAIT", 0.3), \
            mock.patch.object(mp_mod, "READY_POLL", 0.05):
        yield


async def _them(hass, r1, mic_host="", mic_port=0) -> MockConfigEntry:
    options = {"mic_host": mic_host, "mic_port": mic_port} if mic_host else {}
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options=options, unique_id=f"127.0.0.1:{r1.port}")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def _cho(cond, hass=None, giay=4.0):
    for _ in range(int(giay / 0.02)):
        if cond():
            return
        await asyncio.sleep(0.02)
        if hass is not None:
            await hass.async_block_till_done()
    raise AssertionError("điều kiện không đạt trong hạn")


async def _bom(hass, server, data, cond, giay=4.0):
    """Loa giả phát liên tục (như mic thật) tới khi ``cond``; khúc đến trước lượt pipeline
    đầu bị bỏ theo thiết kế nên không thể phát một lần rồi chờ."""
    for _ in range(int(giay / 0.02)):
        if cond():
            return
        await server.send(data)
        await asyncio.sleep(0.02)
        await hass.async_block_till_done()
    raise AssertionError("điều kiện không đạt trong hạn")


def _cuoi(pipeline) -> list[int]:
    return samples(bytes(pipeline.got[-MIC_CHUNK:]))


def _state(hass, eid):
    st = hass.states.get(eid)
    return st.state if st else None


def _vet_tinh(hass):
    return hass.data[DATA_COMPONENT].get_entity(SAT)


# ── Ca bắt buộc ────────────────────────────────────────────────────────────────

async def test_host_trong_thi_unavailable(hass, r1, pipeline):
    await _them(hass, r1)
    assert _state(hass, SAT) == STATE_UNAVAILABLE
    # Các thực thể còn lại vẫn có tên theo hợp đồng và dùng được.
    assert _state(hass, GAIN) == "0.0"
    assert _state(hass, MUTE) == "off"
    assert _state(hass, SEL) == "preferred"
    assert not pipeline.turns            # không có luồng thì không mở pipeline


async def test_nhan_luong_va_day_vao_pipeline(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(1000), lambda: len(pipeline.got) >= 3 * MIC_CHUNK)
    assert set(samples(bytes(pipeline.got))) == {1000}           # nguyên vẹn, đúng thứ tự khối
    assert len(pipeline.got) % MIC_CHUNK == 0
    assert pipeline.turns[0] is PipelineStage.WAKE_WORD     # từ gọi do pipeline HA quyết
    assert _state(hass, SAT) == "idle"
    # Thực thể chọn pipeline là cái vệ tinh dùng.
    assert _vet_tinh(hass).pipeline_entity_id == SEL


async def test_tat_mic_thi_khong_nhan(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    await _cho(lambda: pcm_server.writers)
    await hass.services.async_call("switch", "turn_on", {"entity_id": MUTE}, blocking=True)
    await _cho(lambda: pcm_server.closed_by_client >= 1, hass)     # luồng bị ĐÓNG
    assert _state(hass, SAT) == "idle"                  # tắt chủ động không phải lỗi
    n = pcm_server.accepted
    await asyncio.sleep(0.4)                            # qua vài chu kỳ thử lại
    assert pcm_server.accepted == n                     # không nối lại khi đang tắt
    assert bytes(pipeline.got) == b""
    # Bật lại thì nối lại và nhận.
    await hass.services.async_call("switch", "turn_off", {"entity_id": MUTE}, blocking=True)
    await _cho(lambda: pcm_server.accepted > n and pcm_server.writers)
    await _bom(hass, pcm_server, pcm(500), lambda: len(pipeline.got) >= MIC_CHUNK)
    assert set(samples(bytes(pipeline.got))) == {500}


async def test_tang_mic_tang_bien_do(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(1000), lambda: len(pipeline.got) >= MIC_CHUNK)
    assert set(samples(bytes(pipeline.got))) == {1000}                 # 0 dB: nguyên vẹn
    await hass.services.async_call("number", "set_value", {"entity_id": GAIN, "value": 20},
                                   blocking=True)
    assert _state(hass, GAIN) == "20.0"
    await _bom(hass, pcm_server, pcm(1000), lambda: set(_cuoi(pipeline)) == {10000})  # ×10
    await _bom(hass, pcm_server, pcm(30000), lambda: set(_cuoi(pipeline)) == {32767})  # chặn


def test_amplify_don_vi():
    assert samples(mic_mod.amplify(pcm(1000, 4), 6)) == [1995] * 4     # 10**(6/20)=1.995
    assert samples(mic_mod.amplify(pcm(-30000, 2), 30)) == [-32768] * 2
    assert mic_mod.amplify(pcm(1000, 4), 0) == pcm(1000, 4)


async def test_luong_dut_thi_unavailable_roi_tu_khoi_phuc(hass, r1, pcm_server, pipeline, caplog):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(100), lambda: pipeline.turns and _state(hass, SAT) == "idle")
    # Đứt hẳn: đóng kết nối và tắt máy chủ.
    port = pcm_server.port
    await pcm_server.stop()
    await _cho(lambda: _state(hass, SAT) == STATE_UNAVAILABLE, hass)
    await _cho(lambda: pipeline.turns_ended >= 1, hass)        # lượt đang chạy bị cắt
    assert "R1 mic 127.0.0.1" in caplog.text and "unavailable" in caplog.text
    n_canh_bao = sum("unavailable (" in r.message for r in caplog.records)
    await asyncio.sleep(0.5)                                   # nhiều lần thử lại không dồn log
    assert sum("unavailable (" in r.message for r in caplog.records) == n_canh_bao == 1
    # Loa mic sống lại cùng cổng: tự khôi phục.
    pcm_server.port = port
    await pcm_server.start()
    await _cho(lambda: pcm_server.writers)
    await _bom(hass, pcm_server, pcm(100), lambda: _state(hass, SAT) == "idle")
    await _bom(hass, pcm_server, pcm(100), lambda: len(pipeline.turns) >= 2)   # lượt mới mở lại


async def test_luong_im_qua_lau_la_dut(hass, r1, pcm_server, pipeline):
    """Nối được nhưng không có khúc nào: chưa tính là có luồng; có rồi mà im thì dứt."""
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    await _cho(lambda: pcm_server.writers)
    await asyncio.sleep(0.2)
    assert _state(hass, SAT) == STATE_UNAVAILABLE
    await pcm_server.send(pcm(1))
    await _cho(lambda: _state(hass, SAT) == "idle", hass)
    await _cho(lambda: _state(hass, SAT) == STATE_UNAVAILABLE, hass)    # im > READ_TIMEOUT


async def test_cong_dong_khong_ai_nghe_khong_sap(hass, r1, pipeline):
    s = PcmServer()
    await s.start()
    port = s.port
    await s.stop()                       # cổng đóng: ECONNREFUSED
    await _them(hass, r1, "127.0.0.1", port)
    await asyncio.sleep(0.3)
    assert _state(hass, SAT) == STATE_UNAVAILABLE
    assert _state(hass, GAIN) == "0.0"   # phần còn lại của tích hợp vẫn sống


# ── Trả lời qua media_player.r1_loa ─────────────────────────────────────────────

async def test_tra_loi_di_qua_media_player_r1_loa(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    await _cho(lambda: pcm_server.writers)
    await pcm_server.send(pcm(100))
    await _cho(lambda: _state(hass, SAT) == "idle", hass)
    sat = _vet_tinh(hass)
    luong = mock.Mock(media_source_id="media-source://tts/-stream/tok123")
    dang_noi = []

    async def phat(self, media_type, media_id, **kw):
        dang_noi.append(sat._dang_noi)
        await pcm_server.send(pcm(7))        # mic nghe thấy mình: phải bị bỏ
        await asyncio.sleep(0.15)

    with mock.patch.object(mp_mod.R1Player, "async_play_media", new=phat), \
            mock.patch.object(sat_mod.tts, "async_get_stream", return_value=luong):
        pipeline.got.clear()
        sat.on_pipeline_event(PipelineEvent(PipelineEventType.TTS_END,
                                            {"tts_output": {"token": "tok123"}}))
        await _cho(lambda: sat._tts_xong.is_set(), hass)
    assert dang_noi == [True]                    # bỏ mic trong lúc loa nói
    assert not sat._dang_noi
    assert 7 not in samples(bytes(pipeline.got))


async def test_tra_loi_goi_play_media_dung_tham_so(hass, r1, pcm_server, pipeline):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    calls = mock.AsyncMock()
    ann = AssistSatelliteAnnouncement("", "http://x/a.mp3", "http://x/a.mp3", None, "url")
    with mock.patch.object(mp_mod.R1Player, "async_play_media", new=calls):
        await _vet_tinh(hass).async_announce(ann)
    calls.assert_awaited_once()
    args, kwargs = calls.await_args
    assert kwargs["media_type"] == "music" and kwargs["media_id"] == "http://x/a.mp3"
    assert kwargs.get("announce") is True


async def test_cho_phat_xong_theo_dlna(hass, r1, pcm_server, pipeline):
    """Có thực thể dlna_dmr: giữ bỏ-mic tới khi nó hết phát."""
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    sat = _vet_tinh(hass)
    hass.states.async_set("media_player.dmr_gia", "idle")
    xong = asyncio.Event()

    async def chay():
        with mock.patch.object(sat_mod, "dlna_entity_id", return_value="media_player.dmr_gia"), \
                mock.patch.object(mp_mod.R1Player, "async_play_media", new=mock.AsyncMock()):
            await sat._phat("media-source://x")
        xong.set()

    t = hass.async_create_task(chay())
    await asyncio.sleep(0.05)
    hass.states.async_set("media_player.dmr_gia", "playing")
    await asyncio.sleep(0.2)
    assert not xong.is_set() and sat._dang_noi          # còn đang phát
    hass.states.async_set("media_player.dmr_gia", "idle")
    await asyncio.wait_for(t, 2)
    assert xong.is_set() and not sat._dang_noi


async def test_loa_loi_khi_tra_loi_khong_sap(hass, r1, pcm_server, pipeline, caplog):
    await _them(hass, r1, "127.0.0.1", pcm_server.port)
    sat = _vet_tinh(hass)
    from homeassistant.exceptions import HomeAssistantError
    with mock.patch.object(mp_mod.R1Player, "async_play_media",
                           new=mock.AsyncMock(side_effect=HomeAssistantError("dlna chết"))):
        await sat._phat("media-source://x")
    assert "cannot play reply" in caplog.text and not sat._dang_noi


# ── Cấu hình ───────────────────────────────────────────────────────────────────

async def test_tuy_chon_dat_host_mic_roi_nap_lai(hass, r1, pcm_server, pipeline):
    e = await _them(hass, r1)
    assert _state(hass, SAT) == STATE_UNAVAILABLE
    # Chế độ nối ra cũ (hộp thử): ô mic không còn trên form, đặt thẳng vào options như dữ liệu đã lưu từ trước.
    hass.config_entries.async_update_entry(
        e, options={"mic_host": "127.0.0.1", "mic_port": pcm_server.port, "mic_listen_key": ""})
    await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    await _cho(lambda: pcm_server.writers)
    await pcm_server.send(pcm(5))
    await _cho(lambda: _state(hass, SAT) == "idle", hass)


async def test_pipeline_loi_ngay_khong_quay_vong(hass, r1, pcm_server, caplog):
    """Pipeline HA lỗi tức thì (vd chưa có engine từ đánh thức: ``wake-engine-missing``) kết thúc bằng
    sự kiện ERROR chứ không ném ngoại lệ. Vòng nghe PHẢI nghỉ tăng dần, không mở lượt mới liên tục:
    bản cũ quay hàng nghìn vòng/giây, mỗi vòng bật đèn «lỗi» (một lệnh ADB) làm HA đầy RAM rồi bị khởi động lại."""
    lan_goi = []

    async def loi_ngay(self, audio_stream, start_stage=PipelineStage.STT, **kw):
        lan_goi.append(start_stage)
        self.on_pipeline_event(PipelineEvent(
            PipelineEventType.ERROR, {"code": "wake-engine-missing", "message": "No wake word engine"}))

    with mock.patch("homeassistant.components.assist_satellite.entity.AssistSatelliteEntity."
                    "async_accept_pipeline_from_satellite", new=loi_ngay), \
            mock.patch.object(sat_mod, "LOI_NGHI_DAU", 0.2), mock.patch.object(sat_mod, "LOI_NGHI_TOI_DA", 0.4), \
            mock.patch.object(sat_mod.R1Satellite, "_thieu_tu_danh_thuc", return_value=None):
        e = await _them(hass, r1, "127.0.0.1", pcm_server.port)
        den_loi = mock.patch.object(type(e.runtime_data.lights), "bao_loi")
        with den_loi as bao_loi:
            await _cho(lambda: pcm_server.writers)
            await _bom(hass, pcm_server, pcm(1000), lambda: len(lan_goi) >= 1)
            await asyncio.sleep(1.2)
        # nghỉ 0,2 → 0,4 → 0,4…: tối đa vài lượt trong ~1,2 giây (bản cũ: hàng trăm)
        assert 1 <= len(lan_goi) <= 8, f"{len(lan_goi)} lượt pipeline trong 1,2 giây — vòng nghe quay vòng"
        assert bao_loi.call_count <= 1, "đèn «lỗi» bật mỗi vòng thay vì một lần"
    assert "wake" in caplog.text.lower() and "engine" in caplog.text.lower()   # có dòng cảnh báo nói rõ nguyên nhân


async def test_chua_co_engine_tu_danh_thuc_thi_khong_mo_pipeline(hass, r1, pcm_server, caplog):
    """GỐC của lỗi quay vòng: HA chưa có engine từ đánh thức thì mọi lượt pipeline đều lỗi ngay. Vệ tinh phải
    phát hiện TRƯỚC khi chạy: không mở pipeline nào, không bật đèn «lỗi», tạo mục «Sửa chữa» + một dòng
    cảnh báo; khi engine xuất hiện thì tự chạy lại và xoá mục Sửa chữa."""
    from homeassistant.helpers import issue_registry as ir
    lan_goi = []

    async def ghi(self, audio_stream, start_stage=PipelineStage.STT, **kw):
        lan_goi.append(start_stage)
        async for _ in audio_stream:
            pass

    with mock.patch("homeassistant.components.assist_satellite.entity.AssistSatelliteEntity."
                    "async_accept_pipeline_from_satellite", new=ghi), \
            mock.patch.object(sat_mod, "KIEM_LAI_CAU_HINH", 0.1):
        e = await _them(hass, r1, "127.0.0.1", pcm_server.port)
        ma_van_de = f"thieu_tu_danh_thuc_{e.entry_id}"
        with mock.patch.object(type(e.runtime_data.lights), "bao_loi") as bao_loi:
            await _cho(lambda: pcm_server.writers)
            await _bom(hass, pcm_server, pcm(1000), lambda: ir.async_get(hass).async_get_issue(DOMAIN, ma_van_de))
            await asyncio.sleep(0.5)
            assert lan_goi == [], "đã mở pipeline dù chưa có engine từ đánh thức"
            assert bao_loi.call_count == 0
        assert caplog.text.count("chưa có engine từ đánh thức") == 1     # một dòng, không lặp mỗi lượt kiểm

        # engine xuất hiện (thật: thêm Wyoming/openWakeWord) → tự chạy lại, mục Sửa chữa biến mất
        with mock.patch.object(sat_mod.R1Satellite, "_thieu_tu_danh_thuc", return_value=None):
            await _bom(hass, pcm_server, pcm(1000), lambda: lan_goi)
        assert lan_goi[0] is PipelineStage.WAKE_WORD
        assert ir.async_get(hass).async_get_issue(DOMAIN, ma_van_de) is None
