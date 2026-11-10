"""NV304 — xử lý âm thanh nâng cao (khử ồn Speex có sẵn trong HA, khử vọng miền tần số), hành động phím «chạy thực thể HA», âm lượng media riêng.

Không cần cài thêm thư viện: pyspeex_noise đã có trong HA (và trong môi trường test), khử vọng chỉ cần numpy.
"""

from __future__ import annotations

import math
import struct
from types import SimpleNamespace

import numpy as np
import pytest

from custom_components.r1_speaker import phim, xu_ly_nang_cao
from custom_components.r1_speaker.chuoi_mic import MicChain
from custom_components.r1_speaker.khu_vong_fdaf import RATE, KhuVongFdaf
from custom_components.r1_speaker.noise_suppress import NoiseSettings, NoiseSuppressor


def _pcm(vals):
    return struct.pack("<%dh" % len(vals), *vals)


def _rms(b):
    v = np.frombuffer(b, dtype="<i2").astype(float)
    return math.sqrt(float(np.mean(v * v)))


# ── Khử ồn Speex (thư viện của HA) ──────────────────────────────────────────────────────────────

async def test_speex_do_dai_ra_luon_bang_do_dai_vao_voi_moi_kieu_khuc():
    m = xu_ly_nang_cao.SpeexMic(12.0)
    for n in (2, 6, 158, 160, 162, 320, 1024, 2048, 322):          # nhỏ hơn / lẻ / nhiều khung / byte lẻ
        pcm = _pcm([100] * (n // 2))
        assert len(m.process(pcm)) == len(pcm), n
    assert len(m.process(b"")) == 0


async def test_speex_giam_nen_on_that():
    rng = np.random.default_rng(1)
    m = xu_ly_nang_cao.SpeexMic(25.0)
    vao, ra = [], []
    for i in range(300):
        b = (rng.standard_normal(160) * 300).astype("<i2").tobytes()
        o = m.process(b)
        if i > 150:
            vao.append(_rms(b)), ra.append(_rms(o))
    assert 20 * math.log10(np.mean(vao) / np.mean(ra)) >= 10           # nền ồn trắng giảm ít nhất 10 dB (đo thật ~20 dB)


async def test_muc_khu_on_db_bi_chan():
    assert [xu_ly_nang_cao.muc_khu_on_db(x) for x in (-5, 0, 0.4, 12, 12.6, 99)] == [1, 1, 1, 12, 13, 40]


async def test_mic_chain_chon_dong_co_va_ro_ve_bo_cu_khi_thieu_thu_vien(monkeypatch):
    bat = NoiseSettings(enabled=True, strength_db=20.0, engine="nang_cao")
    assert isinstance(MicChain(bat).noise, xu_ly_nang_cao.SpeexMic)
    assert isinstance(MicChain(NoiseSettings(enabled=True)).noise, NoiseSuppressor)              # mặc định noi_bo = hành vi cũ
    assert MicChain(NoiseSettings(enabled=False, engine="nang_cao")).noise is None               # tắt thì không dựng gì
    monkeypatch.setattr(xu_ly_nang_cao, "_speex", lambda: None)       # thư viện không có: dùng Wiener, KHÔNG ném lỗi
    assert isinstance(MicChain(bat).noise, NoiseSuppressor)
    assert len(MicChain(bat).process(_pcm([300] * 480))) == 960


async def test_dsp_dong_co_gia_tri_la_ve_mac_dinh():
    from custom_components.r1_speaker.settings import dsp_dong_co
    mk = lambda o: SimpleNamespace(options=o, data={})
    assert dsp_dong_co(mk({})) == "noi_bo" and dsp_dong_co(mk({"dsp_dong_co": "nang_cao"})) == "nang_cao"
    assert dsp_dong_co(mk({"dsp_dong_co": "webrtc"})) == "noi_bo"                                  # giá trị cũ/lạ → mặc định


# ── Khử vọng miền tần số (FDAF) ────────────────────────────────────────────────────────────────────

def _tieng_gia(giay, seed):
    """Tiếng giả có nhịp (nhiễu có dạng bao như âm tiết) đủ để bộ lọc học."""
    rng = np.random.default_rng(seed)
    n = int(giay * RATE)
    t = np.arange(n) / RATE
    x = rng.standard_normal(n) * (np.clip(np.sin(2 * np.pi * 3.2 * t), 0, None) ** 0.7 + 0.1)
    for k in (1, 2):                                       # làm màu (mất tính trắng) như tiếng nói
        x[k:] += 0.6 * x[:-k]
    return x / np.max(np.abs(x)) * 4000


def _vang(x, tre_ms, he_so=0.55, seed=5):
    rng = np.random.default_rng(seed)
    d, L = int(tre_ms * RATE / 1000), int(0.15 * RATE)
    h = np.zeros(L + d)
    h[d] = 1.0
    h[d:d + L] += rng.standard_normal(L) * np.exp(-6.9 * np.arange(L) / L) * 0.1
    return np.convolve(x, h)[:len(x)] * he_so


def _chay(aec, mic, far, gio):
    """Đưa từng khúc 20 ms như R1: loa chỉ bơm khi CÓ tiếng, đồng hồ giả = thời gian mô phỏng."""
    out = []
    for i in range(0, len(mic) - 319, 320):
        gio["v"] = i / RATE
        ch = far[i:i + 320]
        if np.abs(ch).max() > 50:
            aec.day_ref(ch.astype("<i2").tobytes())
        out.append(np.frombuffer(aec.xu_ly(mic[i:i + 320].astype("<i2").tobytes()), dtype="<i2"))
    return np.concatenate(out)


def _erle(mic, out, a, b):
    m, o = mic[int(a * RATE):int(b * RATE)].astype(float), out[int(a * RATE):int(b * RATE)].astype(float)
    return 10 * math.log10((np.mean(m ** 2) + 1e-9) / (np.mean(o ** 2) + 1e-9))


@pytest.mark.parametrize("tre_ms", [120, 300])
async def test_fdaf_khu_vong_that_va_tu_do_tre(tre_ms):
    far = _tieng_gia(14, 1)
    far[int(6 * RATE):int(7.5 * RATE)] = 0                 # quãng im của bên kia (R1 thật không bơm lúc này)
    mic = np.clip(_vang(far, tre_ms) + np.random.default_rng(2).standard_normal(len(far)) * 60, -32768, 32767)
    gio = {"v": 0.0}
    aec = KhuVongFdaf(clock=lambda: gio["v"])
    out = _chay(aec, mic, far, gio)
    assert len(out) == len(mic)
    assert abs(aec.delay * 1000 / RATE - tre_ms) <= 25, aec.delay * 1000 / RATE    # tự dò đúng độ trễ loa → mic
    assert _erle(mic, out, 9, 13.5) >= 8, _erle(mic, out, 9, 13.5)               # khử ≥ 8 dB sau khi hội tụ


async def test_fdaf_giu_tieng_nguoi_noi_chen_va_khong_te_hon_mic():
    far = _tieng_gia(14, 3)
    near = np.zeros(len(far))
    near[int(8 * RATE):int(13 * RATE)] = _tieng_gia(5, 9) * 1.5
    mic = np.clip(_vang(far, 200) + near, -32768, 32767)
    gio = {"v": 0.0}
    out = _chay(KhuVongFdaf(clock=lambda: gio["v"]), mic, far, gio)
    c = near[int(8 * RATE):int(13 * RATE)]
    tot = max(float(np.dot(out[int(8 * RATE) + L:int(13 * RATE) + L].astype(float), c)
                    / (np.linalg.norm(out[int(8 * RATE) + L:int(13 * RATE) + L].astype(float)) * np.linalg.norm(c) + 1e-9))
              for L in range(0, 600, 16))                      # đầu ra trễ một khối (16 ms) + bù
    assert tot >= 0.7, tot                                     # tiếng gần micro vẫn còn nhận ra
    assert np.mean(out.astype(float) ** 2) <= 1.5 * np.mean(mic ** 2)        # chốt an toàn: không bao giờ tệ hơn mic thô


async def test_fdaf_do_dai_ra_bang_vao_va_khong_xu_ly_khi_chua_co_loa():
    aec = KhuVongFdaf(clock=lambda: 0.0)
    near = _pcm([500] * 160)
    assert aec.xu_ly(near) == near                             # chưa bơm tham chiếu: trả nguyên
    aec.day_ref(_pcm([2000] * 160))
    for n in (2, 6, 158, 160, 322, 640, 1000, 2048):
        pcm = _pcm([100] * (n // 2))
        assert len(aec.xu_ly(pcm)) == len(pcm), n
    assert aec.xu_ly(b"") == b""


async def test_fdaf_quang_im_dai_khong_lam_hong_va_khong_phinh_bo_nho():
    gio = {"v": 0.0}
    aec = KhuVongFdaf(clock=lambda: gio["v"])
    far = _tieng_gia(3, 4)
    mic = np.clip(_vang(far, 100), -32768, 32767)
    _chay(aec, mic, far, gio)
    gio["v"] = 400.0                                           # im 400 giây rồi loa nói lại
    aec.day_ref(_pcm([1000] * 320))
    assert len(aec.xu_ly(_pcm([10] * 320))) == 640
    assert aec._far.size == 16000 * 6 and aec._near.size == 16000 * 6          # vòng cố định, không phình


# ── Hành động phím «chạy thực thể» ──────────────────────────────────────────────────────────────

class _Services:
    def __init__(self):
        self.goi = []

    async def async_call(self, domain, service, data, blocking=False):
        self.goi.append((domain, service, dict(data), blocking))


def _ctx(dich, co_the=("script.gia", "automation.a", "scene.s", "button.b", "lock.cua")):
    states = {e: object() for e in co_the}
    hass = SimpleNamespace(services=_Services(), states=SimpleNamespace(get=lambda e: states.get(e)))
    coordinator = SimpleNamespace(phim=SimpleNamespace(dich=dich))
    return phim.PhimCtx(hass=hass, entry=None, coordinator=coordinator, ma=195, cu_chi="don")


async def test_kich_hoat_chi_nhan_loai_an_toan():
    assert phim.kich_hoat("script.x")[:2] == ("script", "turn_on")
    assert phim.kich_hoat("automation.x") == ("automation", "trigger", {"skip_condition": True})
    assert phim.kich_hoat("scene.x")[:2] == ("scene", "turn_on")
    assert phim.kich_hoat("button.x")[:2] == ("button", "press")
    for bad in ("lock.cua", "alarm_control_panel.a", "cover.garage", "shell_command.x", "khong_co_dau_cham", ""):
        assert phim.kich_hoat(bad) is None, bad


async def test_hanh_dong_chay_thuc_the_goi_dung_dich_vu_khong_cho():
    assert "chay_thuc_the" in phim.danh_sach()
    for ent, mong in (("script.gia", ("script", "turn_on", {"entity_id": "script.gia"})),
                      ("automation.a", ("automation", "trigger", {"entity_id": "automation.a", "skip_condition": True})),
                      ("button.b", ("button", "press", {"entity_id": "button.b"}))):
        ctx = _ctx({"don": ent})
        await phim._DANG_KY["chay_thuc_the"].ham(ctx)
        domain, dv, data, cho = ctx.hass.services.goi[0]
        assert (domain, dv, data) == mong and cho is False             # không chờ: script dài không giữ bộ nhận diện phím


async def test_hanh_dong_chay_thuc_the_tu_choi_khi_chua_chon_loai_cam_hoac_da_go():
    ham = phim._DANG_KY["chay_thuc_the"].ham
    for dich, loi in (({}, "chưa chọn"), ({"don": "lock.cua"}, "không được phím kích hoạt"),
                      ({"don": "script.da_xoa"}, "không còn trong HA")):
        ctx = _ctx(dich)
        with pytest.raises(RuntimeError, match=loi):
            await ham(ctx)
        assert ctx.hass.services.goi == []


# ── Âm lượng media riêng (hệ số PCM của phiên AirPlay phát nhạc) ─────────────────────────────────

async def test_ap_he_so_giam_cat_va_khong_ton_gi_khi_bang_mot():
    from custom_components.r1_speaker.airplay import ap_he_so, goi_am_thanh
    pcm = _pcm([1000, -1000, 32767, -32768, 0, 5])
    assert ap_he_so(pcm, 1.0) is pcm                                  # không đổi: trả đúng đối tượng, không sao chép
    assert struct.unpack("<6h", ap_he_so(pcm, 0.5)) == (500, -500, 16383, -16384, 0, 2)
    assert struct.unpack("<6h", ap_he_so(pcm, 0.0)) == (0,) * 6
    assert struct.unpack("<6h", ap_he_so(pcm, 2.0)) == (2000, -2000, 32767, -32768, 0, 10)     # tăng bị cắt, không tràn số
    a = goi_am_thanh(1, 2, 3, pcm, False)
    assert goi_am_thanh(1, 2, 3, pcm, False, 1.0) == a                # mặc định giữ nguyên hành vi cũ
    half = goi_am_thanh(1, 2, 3, pcm, False, 0.5)
    assert half[:12] == a[:12] and struct.unpack(">6h", half[12:]) == (500, -500, 16383, -16384, 0, 2)


async def test_am_luong_media_tu_tuy_chon_va_gia_tri_hong():
    from custom_components.r1_speaker.settings import am_luong_media
    mk = lambda o: SimpleNamespace(options=o, data={})
    assert am_luong_media(mk({})) == 1.0 and am_luong_media(mk({"am_luong_media": 30})) == 0.3
    assert am_luong_media(mk({"am_luong_media": 500})) == 1.0 and am_luong_media(mk({"am_luong_media": -5})) == 0.0
    assert am_luong_media(mk({"am_luong_media": "abc"})) == 1.0


def test_chan_doan_khu_vong_noi_ro_bo_nao_dang_chay_va_so_do_fdaf():
    """Người dùng báo «vẫn vọng»: thuộc tính ``khu_vong`` phải nói bộ nào chạy và ERLE thật, không để đoán."""
    from types import SimpleNamespace
    from custom_components.r1_speaker.khu_vong import KhuVong
    from custom_components.r1_speaker.song_cong import R1Duplex
    gia = SimpleNamespace(_aec=None)
    do = lambda aec: R1Duplex._do_khu_vong(SimpleNamespace(_aec=aec))  # noqa: E731
    assert do(None) == {"dong_co": None}
    assert do(KhuVong(do_tre_mau=0)) == {"dong_co": "nlms"}
    f = KhuVongFdaf()
    f.erle_db, f.delay, f.tin_cay = 9.26, int(0.25 * RATE), 31.04
    assert do(f) == {"dong_co": "fdaf", "erle_db": 9.3, "tre_ms": 250, "tin_cay": 31.0}
