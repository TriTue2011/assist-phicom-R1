"""Đèn LED theo chức năng: giao diện ``LightsSink``, danh mục hiệu ứng, bộ chọn chức năng, cài đặt
được lưu, dịch vụ và thuộc tính cho thẻ. Mọi thứ chạy với ``MemoryLights`` (trong bộ nhớ):
KHÔNG chạm loa, KHÔNG ADB, KHÔNG dịch vụ trên loa (chưa có)."""

import asyncio
import colorsys
import inspect
import json
import random
from datetime import timedelta

import pytest
import voluptuous as vol
from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.r1_speaker import const, den, hieu_ung
from custom_components.r1_speaker.den import (DEFAULTS, FUNCTIONS, UU_TIEN, FunctionLight, Signals,
                                              chon_chuc_nang)
from custom_components.r1_speaker.den_port import (BASE_MASK, MIN_STEP_S, RIM_MASK, LightsSink,
                                                   NullLights, Step, Write, base_write, rim_write,
                                                   run_steps)

from .memory_lights import MemoryLights
from .test_bo_dam import _them
from .test_mic import LOA, MUTE, SAT, _vet_tinh

CAI_DAT = "sensor.r1_cai_dat"
SAMPLE_RGB = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (12, 200, 99)]


# ── Giao diện: mặt nạ và màu ────────────────────────────────────────────────────

def test_mat_na_va_hex_dung_phan_cung_da_kiem():
    assert RIM_MASK == "7fffff8000" and BASE_MASK == "7fff"
    assert rim_write(255) == Write("7fffff8000", "ffffff")           # bật
    assert rim_write(0) == Write("7fffff8000", "000000")             # tắt
    assert rim_write(0x40).rgb_hex == "404040"                       # «mờ rõ»
    assert rim_write(255).command == "set 7fffff8000 ffffff"
    assert base_write((0, 255, 0)) == Write("7fff", "00ff00")        # xanh lá đã xác nhận
    assert base_write((0, 0, 255)) == Write("7fff", "0000ff")        # xanh dương đã xác nhận
    assert base_write((255, 0, 0)).command == "set 7fff ff0000"


def test_den_vien_chi_co_muc_khong_co_mau_va_tu_choi_gia_tri_la():
    assert list(inspect.signature(rim_write).parameters) == ["level"]
    assert list(inspect.signature(LightsSink.set_rim).parameters) == ["self", "level"]
    for bad in (-1, 256, 1.5, True, "ff", None):
        with pytest.raises(ValueError):
            rim_write(bad)
    for bad in ((256, 0, 0), (0, 0), (0, 0, 0, 0), (0.5, 0, 0), (-1, 0, 0)):
        with pytest.raises(ValueError):
            base_write(bad)
    with pytest.raises(ValueError):
        Step(rim=300)
    with pytest.raises(ValueError):
        Step(base=(0, 0, 256))


async def test_null_lights_khong_san_sang_va_khong_ghi_duoc():
    n = NullLights()
    assert isinstance(n, LightsSink) and n.available is False
    from custom_components.r1_speaker.den_port import LightsError
    for coro in (n.set_rim(1), n.set_base((0, 0, 0)), n.play_effect([], repeat=False)):
        with pytest.raises(LightsError):
            await coro
    await n.stop_effect()


# ── Chạy bước đúng thứ tự ──────────────────────────────────────────────────────

class _Ghi:
    def __init__(self):
        self.ra, self.ngu = [], []

    async def set_rim(self, level): self.ra.append(("rim", level))
    async def set_base(self, rgb): self.ra.append(("base", rgb))

    async def sleep(self, s):
        self.ngu.append(s)


async def test_run_steps_dung_thu_tu_va_thoi_gian():
    g = _Ghi()
    steps = [Step(base=(1, 2, 3), rim=10, seconds=0.5), Step(base=(4, 5, 6), seconds=0.01),
             Step(rim=0, seconds=0.2)]
    await run_steps(g, steps, repeat=False, sleep=g.sleep)
    assert g.ra == [("rim", 10), ("base", (1, 2, 3)), ("base", (4, 5, 6)), ("rim", 0)]
    assert g.ngu == [0.5, MIN_STEP_S, 0.2]                      # bước ngắn bị nâng lên mức tối thiểu
    g2 = _Ghi()
    await run_steps(g2, [], repeat=True, sleep=g2.sleep)          # rỗng: không lặp vô hạn
    assert g2.ra == []


async def test_run_steps_lap_den_khi_bi_huy():
    g = _Ghi()
    n = 0

    async def sleep(s):
        nonlocal n
        n += 1
        if n >= 7:
            raise asyncio.CancelledError
        g.ngu.append(s)

    with pytest.raises(asyncio.CancelledError):
        await run_steps(g, [Step(base=(1, 1, 1), seconds=0.1), Step(base=(2, 2, 2), seconds=0.1)],
                        repeat=True, sleep=sleep)
    assert [r[1][0] for r in g.ra] == [1, 2, 1, 2, 1, 2, 1]       # vòng 1,2,1,2,… đúng thứ tự


# ── Danh mục hiệu ứng ──────────────────────────────────────────────────────────

def test_danh_muc_5_den_6_hieu_ung_co_nguon():
    ids = set(hieu_ung.HIEU_UNG)
    assert ids == {"tho", "cau_vong", "nhap_nhay", "nhip_tim", "phao_hoa", "chop"}
    assert 5 <= len(ids) <= 6
    for h in hieu_ung.HIEU_UNG.values():
        assert h.nguon.startswith("https://kno.wled.ge/") and h.wled and h.ten and h.ten_en
    # Hiệu ứng cần ghi từng LED (đuổi, quét, sóng) bị bỏ có chủ đích.
    assert not {"chase", "dui", "scan", "song"} & ids


@pytest.mark.parametrize("eid", list(hieu_ung.HIEU_UNG))
@pytest.mark.parametrize("use_rim", [True, False])
def test_moi_hieu_ung_chi_dung_mau_day_va_vien_trang(eid, use_rim):
    for accent in SAMPLE_RGB:
        for pct in (100, 60, 25, 0):
            steps = hieu_ung.dung(eid, accent, pct, use_rim, random.Random(3))
            assert steps and all(isinstance(s, Step) for s in steps)
            assert all(s.seconds >= MIN_STEP_S for s in steps)
            for s in steps:                                       # Step tự kiểm 0–255
                assert s.rim is None or isinstance(s.rim, int)
            if not use_rim:
                # chức năng không dùng viền: viền chỉ ghi 0, không bao giờ sáng
                assert all(s.rim in (None, 0) for s in steps)
                assert steps[0].rim == 0
            if pct == 0:
                assert all(s.base in (None, (0, 0, 0)) for s in steps)
                assert all(s.rim in (None, 0) for s in steps)


def test_tho_sang_dan_roi_toi_dan_va_dan_theo_do_sang():
    s = hieu_ung.dung("tho", (255, 0, 0), 100, True)
    assert [x.base[0] for x in s] == [0, 37, 128, 218, 255, 218, 128, 37]
    assert [x.rim for x in s] == [0, 37, 128, 218, 255, 218, 128, 37]    # viền thở theo đáy
    half = hieu_ung.dung("tho", (255, 0, 0), 50, True)
    assert max(x.base[0] for x in half) == 128 and max(x.rim for x in half) == 128


def test_cau_vong_di_het_vong_mau_theo_thu_tu_va_vien_mo_co_dinh():
    s = hieu_ung.dung("cau_vong", (1, 2, 3), 100, True)               # màu của chức năng bị bỏ qua
    assert len(s) == 12 and s[0].base == (255, 0, 0) and s[4].base == (0, 255, 0)
    assert s[8].base == (0, 0, 255)
    hues = [colorsys.rgb_to_hsv(*(c / 255 for c in x.base))[0] for x in s]
    assert hues == sorted(hues) and hues[0] == 0
    assert s[0].rim == 102 and all(x.rim is None for x in s[1:])     # viền mờ, ghi một lần
    assert hieu_ung.dung("cau_vong", (1, 2, 3), 50, False)[4].base == (0, 128, 0)


def test_nhap_nhay_nhip_tim_chop_dung_nhip():
    assert hieu_ung.dung("nhap_nhay", (0, 255, 0), 100, True) == [
        Step(base=(0, 255, 0), rim=255, seconds=0.5), Step(base=(0, 0, 0), rim=0, seconds=0.5)]
    hb = hieu_ung.dung("nhip_tim", (0, 0, 255), 100, False)
    assert [x.base[2] for x in hb] == [255, 38, 191, 0]
    assert sum(x.seconds for x in hb) == pytest.approx(1.0)
    st = hieu_ung.dung("chop", (0, 0, 255), 100, False)
    assert [x.base for x in st[:5]] == [(0, 0, 255), (0, 0, 0), (0, 0, 255), (0, 0, 0), (0, 0, 255)]
    assert st[-1].seconds == 0.8


def test_phao_hoa_xac_dinh_theo_seed():
    a = hieu_ung.dung("phao_hoa", (9, 9, 9), 100, True, random.Random(7))
    b = hieu_ung.dung("phao_hoa", (9, 9, 9), 100, True, random.Random(7))
    c = hieu_ung.dung("phao_hoa", (9, 9, 9), 100, True, random.Random(8))
    assert a == b and a != c
    assert len(a) == 24                                              # 6 chùm × 4 bước
    for k in range(6):                                               # mỗi chùm: bừng → mờ → mờ hơn → tắt
        bung, mo, mo2, tat = a[4 * k:4 * k + 4]
        assert max(bung.base) == 255 and 0 < max(mo.base) < 255 and 0 < max(mo2.base) < max(mo.base)
        assert tat.base == (0, 0, 0) and 0.25 <= tat.seconds <= 0.7
        assert [x.seconds for x in (bung, mo, mo2)] == [0.08, 0.10, 0.10]


# ── Bộ chọn chức năng ──────────────────────────────────────────────────────────

def test_tam_chuc_nang_va_thu_tu_uu_tien():
    assert set(FUNCTIONS) == {"cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi",
                              "tat_mic"}
    assert UU_TIEN[0] == "tat_mic" and UU_TIEN[-1] == "cho"
    bat_nhac = {**DEFAULTS, "phat_nhac": FunctionLight(True, False, "#00ff00", "tho", 40)}
    cases = [
        (Signals(), "cho", DEFAULTS),
        (Signals(ve_tinh="idle"), "cho", DEFAULTS),
        (Signals(ve_tinh="listening"), "nghe", DEFAULTS),
        (Signals(ve_tinh="processing"), "nghi", DEFAULTS),
        (Signals(ve_tinh="responding"), "phan_hoi", DEFAULTS),
        (Signals(ve_tinh="unavailable"), "cho", DEFAULTS),
        (Signals(phien=True, ve_tinh="idle"), "dam_thoai", DEFAULTS),
        (Signals(phien=True, ve_tinh="listening"), "nghe", DEFAULTS),
        (Signals(dang_phat=True), "cho", DEFAULTS),           # chức năng nhạc đang TẮT → coi như không có nhạc
        (Signals(dang_phat=True), "phat_nhac", bat_nhac),
        (Signals(dang_phat=True, ve_tinh="responding"), "phan_hoi", bat_nhac),
        (Signals(dang_phat=True, phien=True), "dam_thoai", bat_nhac),
        (Signals(loi=True, ve_tinh="listening", dang_phat=True), "loi", bat_nhac),
        (Signals(tat_mic=True, loi=True, ve_tinh="responding", phien=True), "tat_mic", bat_nhac),
    ]
    for tin, mong, prof in cases:
        assert chon_chuc_nang(tin, prof) == mong, tin


def test_mac_dinh_hop_le_va_do_chi_dung_cung_den_vien():
    assert set(DEFAULTS) == set(FUNCTIONS)
    for fn, p in DEFAULTS.items():
        assert den.chuan_mau(p.color) == p.color and 0 <= p.brightness <= 100, fn
        assert p.effect == "none" or p.effect in hieu_ung.HIEU_UNG, fn
    # Chỉ xanh lá / xanh dương đã xác nhận được dùng trừ ĐỎ; đỏ chỉ ở «lỗi» và «tắt mic», và luôn kèm
    # đèn viền trắng (đã xác nhận) để vẫn thấy được nếu đèn đáy không hiện đỏ.
    for fn, p in DEFAULTS.items():
        if p.color not in ("#00ff00", "#0000ff"):
            assert p.color == "#ff0000" and fn in ("loi", "tat_mic") and p.rim is True, fn
    assert DEFAULTS["tat_mic"].brightness == 25 and den.sang_vien(25) == 0x40   # 404040 «mờ rõ»
    assert DEFAULTS["phat_nhac"].enabled is False and DEFAULTS["cho"].enabled is False


def test_doc_cai_dat_hong_roi_ve_mac_dinh_tung_truong():
    base = DEFAULTS["nghe"]
    p = FunctionLight.from_dict({"enabled": "x", "rim": False, "color": "đỏ", "effect": "ma",
                                 "brightness": 101}, base)
    assert p == FunctionLight(base.enabled, False, base.color, base.effect, base.brightness)
    assert FunctionLight.from_dict("rác", base) == base
    assert FunctionLight.from_dict({"brightness": True}, base).brightness == base.brightness
    assert den.chuan_mau("00FF00") == "#00ff00" and den.chuan_mau("#12345") is None
    assert den.mau_rgb("#0a0b0c") == (10, 11, 12)


# ── Tích hợp HA: chức năng → đèn ──────────────────────────────────────────────

@pytest.fixture
async def den_sink(hass, r1):
    e = await _them(hass, r1)
    mem = MemoryLights()
    lights = e.runtime_data.lights
    lights.set_sink(mem)
    await hass.async_block_till_done()
    return e, lights, mem


def _sau_lan_dung_cuoi(mem):
    i = max(k for k, x in enumerate(mem.log) if x[0] == "stop")
    return mem.log[i + 1:]


async def test_loa_chua_noi_thi_chi_luu_khong_gui(hass, r1):
    """Tích hợp dùng sink qua APK loa; APK chưa nối thì đèn chỉ lưu cài đặt, không gửi, không báo lỗi."""
    from custom_components.r1_speaker.den_apk import ApkLights
    e = await _them(hass, r1)
    lights = e.runtime_data.lights
    assert isinstance(lights.sink, ApkLights) and lights.sink_state == "mat_ket_noi"
    assert not lights.sink.available
    st = hass.states.get(CAI_DAT)
    assert st.state == "cho" and st.attributes["anh_sang"]["dich_vu_den"] == "mat_ket_noi"
    # đổi trạng thái vẫn không ném lỗi, không gửi gì
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert lights.current == "nghe" and lights.last_error is None
    assert hass.services.has_service("r1_speaker", "set_light_function")
    assert hass.services.has_service("r1_speaker", "set_music_light")


async def test_moi_chuc_nang_ghi_dung_mat_na_va_mau(hass, r1, den_sink):
    e, lights, mem = den_sink
    # chờ: mặc định TẮT → tắt cả hai đèn (viền 000000 mặt nạ viền, đáy 000000 mặt nạ đáy)
    assert lights.current == "cho"
    assert _sau_lan_dung_cuoi(mem) == [("write", Write(RIM_MASK, "000000")),
                                       ("write", Write(BASE_MASK, "000000"))]

    mem.clear()
    hass.states.async_set(SAT, "listening")                      # nghe: xanh dương 60% + viền 60%
    await hass.async_block_till_done()
    assert _sau_lan_dung_cuoi(mem) == [("write", Write(RIM_MASK, "999999")),
                                       ("write", Write(BASE_MASK, "000099"))]

    mem.clear()
    hass.states.async_set(SAT, "responding")                     # phản hồi: xanh lá 60% + viền 60%
    await hass.async_block_till_done()
    assert _sau_lan_dung_cuoi(mem) == [("write", Write(RIM_MASK, "999999")),
                                       ("write", Write(BASE_MASK, "009900"))]

    mem.clear()
    hass.states.async_set(SAT, "idle")
    await hass.services.async_call("switch", "turn_on", {"entity_id": MUTE}, blocking=True)
    await hass.async_block_till_done()                           # tắt mic: đỏ 25% + viền 404040
    assert lights.current == "tat_mic"
    assert _sau_lan_dung_cuoi(mem) == [("write", Write(RIM_MASK, "404040")),
                                       ("write", Write(BASE_MASK, "400000"))]
    mem.clear()
    await hass.services.async_call("switch", "turn_off", {"entity_id": MUTE}, blocking=True)
    await hass.async_block_till_done()
    assert lights.current == "cho"
    assert _sau_lan_dung_cuoi(mem)[:2] == [("write", Write(RIM_MASK, "000000")),
                                           ("write", Write(BASE_MASK, "000000"))]


async def test_vien_chi_bao_gio_ghi_xam_trang(hass, r1, den_sink):
    """Mọi lần ghi mặt nạ viền, ở mọi chức năng và hiệu ứng, đều là ``LLLLLL`` (trắng)."""
    e, lights, mem = den_sink
    for fn in FUNCTIONS:
        for eff in ("none", *hieu_ung.HIEU_UNG):
            await lights.async_set_function(fn, enabled=True, rim=True, effect=eff, brightness=70,
                                            color="#00ff00")
            lights.preview(fn)
            await hass.async_block_till_done()
            await asyncio.sleep(0.02)
    rim = [w for w in mem.writes if w.mask == RIM_MASK]
    base = [w for w in mem.writes if w.mask == BASE_MASK]
    assert rim and base
    assert all(w.rgb_hex[0:2] == w.rgb_hex[2:4] == w.rgb_hex[4:6] for w in rim)
    assert {w.mask for w in mem.writes} == {RIM_MASK, BASE_MASK}


async def test_nghi_dam_thoai_va_loi_dung_hieu_ung_da_cai(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.clear()
    hass.states.async_set(SAT, "processing")                      # nghĩ: thở xanh dương, KHÔNG viền
    await hass.async_block_till_done()
    ev = [x for x in mem.log if x[0] == "effect"]
    assert len(ev) == 1 and ev[0][2] is True
    assert list(ev[0][1]) == hieu_ung.dung("tho", (0, 0, 255), 60, False)

    mem.clear()
    hass.states.async_set(SAT, "idle")
    rel = e.runtime_data.talk.claim("bo_dam")                     # có phiên, vệ tinh rảnh → đàm thoại
    await hass.async_block_till_done()
    assert lights.current == "dam_thoai"
    ev = [x for x in mem.log if x[0] == "effect"]
    assert list(ev[0][1]) == hieu_ung.dung("tho", (0, 255, 0), 50, True)
    rel()
    await hass.async_block_till_done()
    assert lights.current == "cho"

    mem.clear()
    lights.bao_loi()                                              # lỗi: nhấp nháy đỏ + viền
    await hass.async_block_till_done()
    assert lights.current == "loi"
    ev = [x for x in mem.log if x[0] == "effect"]
    assert list(ev[0][1]) == hieu_ung.dung("nhap_nhay", (255, 0, 0), 80, True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(
        seconds=const.LIGHT_ERROR_HOLD_S + 1))
    await hass.async_block_till_done()
    assert lights.current == "cho"                                # hết giữ → về đúng lúc đó


async def test_loi_tu_phien_dong_vi_loi_va_tu_pipeline(hass, r1, den_sink):
    e, lights, mem = den_sink
    talk = e.runtime_data.talk
    talk.claim("bo_dam")
    await hass.async_block_till_done()
    talk.end(talk.session, "xong", cut=False)                     # đóng bình thường: không phải lỗi
    await hass.async_block_till_done()
    assert lights.current == "cho"
    talk.claim("bo_dam")
    talk.end(talk.session, "loi_pipeline", cut=False)             # đóng vì lỗi pipeline
    await hass.async_block_till_done()
    assert lights.current == "loi"
    lights._het_loi()
    await hass.async_block_till_done()
    assert lights.current == "cho"
    # sự kiện ERROR của pipeline cũng báo lỗi (điểm đấu ở assist_satellite.on_pipeline_event)
    sat = _vet_tinh(hass)
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": "stt-stream-failed"}))
    await hass.async_block_till_done()
    assert lights.current == "loi"
    lights._het_loi()
    await hass.async_block_till_done()
    # «không nghe thấy gì» không phải hỏng; lượt do chính ta cắt (bấm kết thúc…) cũng không
    for code in ("stt-no-text-recognized", "wake-word-timeout"):
        sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": code}))
    sat._cat_luot()
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": "stt-stream-failed"}))
    await hass.async_block_till_done()
    assert lights.current == "cho"
    sat._cut_luot = sat._cut                     # lượt mới bắt đầu, không bị cắt: lỗi thật lại báo
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": "stt-stream-failed"}))
    await hass.async_block_till_done()
    assert lights.current == "loi"


async def test_hieu_ung_nhac_chay_dung_thu_tu_buoc(hass, r1, den_sink):
    e, lights, mem = den_sink
    await hass.services.async_call("r1_speaker", "set_music_light", {
        "entity_id": CAI_DAT, "enabled": True, "effect": "cau_vong", "brightness": 50}, blocking=True)
    mem.clear()
    hass.states.async_set(LOA, "playing")
    await hass.async_block_till_done()
    assert lights.current == "phat_nhac"
    for _ in range(300):                                          # chờ chạy ≥ 2 vòng
        if len(mem.sleeps) >= 24:
            break
        await asyncio.sleep(0.005)
    steps = hieu_ung.dung("cau_vong", (0, 255, 0), 50, False)
    muon = [(("base", s.base) if s.base is not None else ("rim", s.rim)) for s in steps]
    got = []
    for w in mem.writes:
        got.append(("rim", int(w.rgb_hex[:2], 16)) if w.mask == RIM_MASK
                   else ("base", tuple(int(w.rgb_hex[i:i + 2], 16) for i in (0, 2, 4))))
    # bước đầu ghi cả viền (0, vì chức năng không dùng viền) rồi đáy; sau đó chỉ đổi đáy theo thứ tự
    assert got[0] == ("rim", 0)
    day = [g[1] for g in got if g[0] == "base"]
    assert day[:12] == [s.base for s in steps] and day[12:24] == [s.base for s in steps]
    assert mem.sleeps[:12] == [s.seconds for s in steps]
    assert muon  # (giữ để đọc diff dễ: danh sách bước dự kiến)


async def test_chu_nang_khac_chen_vao_thi_hieu_ung_nhac_dung(hass, r1, den_sink):
    e, lights, mem = den_sink
    await lights.async_set_music(enabled=True, effect="nhap_nhay", brightness=100)
    hass.states.async_set(LOA, "playing")
    await hass.async_block_till_done()
    for _ in range(200):
        if len(mem.writes) >= 6:
            break
        await asyncio.sleep(0.005)
    assert mem.running and lights.current == "phat_nhac"
    hass.states.async_set(SAT, "listening")                       # «nghe» chen vào
    await hass.async_block_till_done()
    assert lights.current == "nghe" and not mem.running           # hiệu ứng cũ đã dừng
    chot = len(mem.log)
    sau = _sau_lan_dung_cuoi(mem)
    assert sau == [("write", Write(RIM_MASK, "999999")), ("write", Write(BASE_MASK, "000099"))]
    await asyncio.sleep(0.1)                                       # không còn ai ghi đè nữa
    assert len(mem.log) == chot
    hass.states.async_set(SAT, "idle")                             # nghe xong: nhạc vẫn phát → quay lại nhạc
    await hass.async_block_till_done()
    assert lights.current == "phat_nhac" and mem.running


async def test_doi_nhanh_nhieu_lan_chi_ap_ban_moi_nhat(hass, r1, den_sink):
    """Loa chậm: ba lần đổi chức năng liền nhau → bản giữa (phản hồi) bị bỏ, không ghi xen kẽ."""
    e, lights, mem = den_sink
    mem.cham = True
    mem.clear()
    lights.preview("nghe")            # evaluate chạy đồng bộ: ba lần đổi trong cùng một nhịp
    lights.preview("phan_hoi")
    lights._het_thu()
    await hass.async_block_till_done()
    assert lights.current == "cho"
    assert Write(BASE_MASK, "009900") not in mem.writes            # «phản hồi» chưa từng được ghi
    assert mem.writes[-2:] == [Write(RIM_MASK, "000000"), Write(BASE_MASK, "000000")]   # kết thúc ở «chờ»


async def test_nhac_tat_thi_khong_co_hieu_ung_nhac(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.clear()
    hass.states.async_set(LOA, "playing")                         # mặc định chức năng nhạc TẮT
    await hass.async_block_till_done()
    assert lights.current == "cho" and not [x for x in mem.log if x[0] == "effect"]
    await lights.async_set_music(enabled=True)
    assert lights.current == "phat_nhac"
    await lights.async_set_music(enabled=False)
    assert lights.current == "cho"


async def test_cai_dat_duoc_luu_va_nap_lai(hass, r1, hass_storage):
    e = await _them(hass, r1)
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": CAI_DAT, "function": "nghe", "color": "#00FF00", "brightness": 30,
        "effect": "nhip_tim", "rim": False}, blocking=True)
    key = f"r1_speaker.lights.{e.entry_id}"
    assert hass_storage[key]["data"] == {"functions": {"nghe": {
        "rim": False, "color": "#00ff00", "effect": "nhip_tim", "brightness": 30}}}   # chỉ phần KHÁC mặc định
    assert hass.states.get(CAI_DAT).attributes["anh_sang"]["chuc_nang"]["nghe"] == {
        "enabled": True, "rim": False, "color": "#00ff00", "effect": "nhip_tim", "brightness": 30, "toc_do": 100,
        "mac_dinh": False}
    assert await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    p = e.runtime_data.lights.profiles["nghe"]
    assert p == FunctionLight(True, False, "#00ff00", "nhip_tim", 30)
    assert e.runtime_data.lights.profiles["nghi"] == DEFAULTS["nghi"]


async def test_dich_vu_tu_choi_gia_tri_sai(hass, r1):
    await _them(hass, r1)
    base = {"entity_id": CAI_DAT, "function": "nghe"}
    for extra in ({"color": "đỏ"}, {"color": "#12345"}, {"effect": "ma"}, {"brightness": 101},
                  {"brightness": -1}, {"function": "khong_co"}, {"enabled": "may-be"}):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call("r1_speaker", "set_light_function", {**base, **extra},
                                           blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("r1_speaker", "set_light_function", {
            "entity_id": "sensor.khong_phai_r1", "function": "nghe"}, blocking=True)
    # hàm trực tiếp cũng tự kiểm (không tin lớp lược đồ)
    lights = hass.config_entries.async_entries("r1_speaker")[0].runtime_data.lights
    with pytest.raises(ServiceValidationError):
        await lights.async_set_function("nghe", brightness=500)
    assert lights.profiles["nghe"] == DEFAULTS["nghe"]


async def test_thu_den_hien_chuc_nang_vai_giay_roi_tra_ve(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.clear()
    await hass.services.async_call("r1_speaker", "preview_light", {
        "entity_id": CAI_DAT, "function": "tat_mic", "seconds": 5}, blocking=True)
    await hass.async_block_till_done()
    assert lights.current == "tat_mic"
    assert ("write", Write(BASE_MASK, "400000")) in mem.log
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert lights.current == "cho"


async def test_sink_loi_khong_lam_hong_gi_va_hoi_phuc(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.fail = "mất kết nối tới loa"
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert lights.current == "nghe" and lights.last_error == "mất kết nối tới loa"
    assert hass.states.get(CAI_DAT).attributes["anh_sang"]["loi_dich_vu"] == "mất kết nối tới loa"
    mem.fail = None
    hass.states.async_set(SAT, "responding")
    await hass.async_block_till_done()
    assert lights.last_error is None and lights.current == "phan_hoi"


async def test_sink_khong_san_sang_thi_khong_ghi_gi(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.set_available(False)
    lights.set_sink(mem)
    mem.clear()
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert lights.current == "nghe" and mem.log == []
    assert lights.sink_state == "mat_ket_noi"


async def test_dong_tich_hop_tat_den_va_dung_hieu_ung(hass, r1, den_sink):
    e, lights, mem = den_sink
    await lights.async_set_music(enabled=True, effect="tho")
    hass.states.async_set(LOA, "playing")
    await hass.async_block_till_done()
    assert mem.running
    assert await hass.config_entries.async_unload(e.entry_id)
    await hass.async_block_till_done()
    assert not mem.running
    assert mem.log[-3:] == [("stop",), ("write", Write(RIM_MASK, "000000")),
                            ("write", Write(BASE_MASK, "000000"))]


async def test_thuoc_tinh_cho_the_ba_nhom_va_khong_lo_khoa(hass, r1):
    e = await _them(hass, r1, ha_url="http://ha.example:8123", mic_host="192.0.2.30", mic_port=9999)
    khoa = e.data[const.CONF_INTERCOM_KEY]
    assert len(khoa) > 20
    a = hass.states.get(CAI_DAT).attributes
    assert set(a) >= {"am_thanh", "anh_sang", "ket_noi"}
    assert khoa not in json.dumps(dict(a), ensure_ascii=False)            # KHÔNG bao giờ lộ khoá
    assert a["ket_noi"]["khoa_bo_dam"] == "da_co"
    assert (a["ket_noi"]["host"], a["ket_noi"]["cong"]) == ("127.0.0.1", r1.port)
    assert a["ket_noi"]["ha_url"] == "http://ha.example:8123" and a["ket_noi"]["mic_cong"] == 9999
    assert a["ket_noi"]["tuy_chon"].startswith("/config/integrations/")
    assert a["am_thanh"]["khu_tap"]["bat"] is False and a["am_thanh"]["agc"]["bat"] is False
    assert a["am_thanh"]["sua_o"] == "the"
    al = a["anh_sang"]
    assert list(al["chuc_nang"]) == list(FUNCTIONS) and al["thu_tu_uu_tien"] == list(UU_TIEN)
    assert [h["id"] for h in al["hieu_ung"]] == list(hieu_ung.HIEU_UNG)
    assert all(h["nguon"].startswith("https://") for h in al["hieu_ung"])
    assert all(v["mac_dinh"] for v in al["chuc_nang"].values())
    assert al["den_nhac_firmware"] == {"bat": True, "luma": 50, "chroma": 60,
                                       "dieu_khien": "qua_apk_msgcenter"}


async def test_toc_do_hieu_ung_luu_kiem_gia_tri_va_chia_thoi_gian_moi_buoc(hass, r1, hass_storage):
    from custom_components.r1_speaker import hieu_ung
    e = await _them(hass, r1)
    cd = hass.states.get(CAI_DAT).attributes["anh_sang"]
    assert cd["toc_do"] == {"min": 25, "max": 400, "mac_dinh": 100}
    assert cd["chuc_nang"]["nghe"]["toc_do"] == 100
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": CAI_DAT, "function": "nghe", "effect": "chop", "toc_do": 200}, blocking=True)
    assert hass_storage[f"r1_speaker.lights.{e.entry_id}"]["data"]["functions"]["nghe"]["toc_do"] == 200
    assert hass.states.get(CAI_DAT).attributes["anh_sang"]["chuc_nang"]["nghe"]["toc_do"] == 200
    for xau in (10, 401, 0, -5):                                # ngoài 25–400 bị chặn từ lược đồ dịch vụ
        with pytest.raises(Exception):
            await hass.services.async_call("r1_speaker", "set_light_function", {
                "entity_id": CAI_DAT, "function": "nghe", "toc_do": xau}, blocking=True)
    # Hiệu ứng gốc của firmware (thở/nháy) có chu kỳ cố định: không nằm trong danh sách chỉnh được tốc độ
    ds = hass.states.get(CAI_DAT).attributes["anh_sang"]
    assert not {"tho", "nhap_nhay"} & set(ds["hieu_ung_co_toc_do"])
    assert {"cau_vong", "nhip_tim", "phao_hoa", "chop"} <= set(ds["hieu_ung_co_toc_do"]) or ds["hieu_ung_goc"] is None
    # dung(): 200% = thời gian mỗi bước giảm một nửa; 50% = gấp đôi; 100% không đổi; ngoài khoảng bị kẹp
    mau = (0, 0, 255)
    goc = [st.seconds for st in hieu_ung.dung("nhap_nhay", mau, 100, False)]
    assert [st.seconds for st in hieu_ung.dung("nhap_nhay", mau, 100, False, toc_do=200)] == [g / 2 for g in goc]
    assert [st.seconds for st in hieu_ung.dung("nhap_nhay", mau, 100, False, toc_do=50)] == [g * 2 for g in goc]
    assert [st.seconds for st in hieu_ung.dung("nhap_nhay", mau, 100, False, toc_do=100)] == goc
    assert [st.seconds for st in hieu_ung.dung("nhap_nhay", mau, 100, False, toc_do=9999)] == [g / 4 for g in goc]
