"""Khử tạp âm: đo trên tín hiệu TỔNG HỢP (không có mic thật, không chạm loa).

Chạy ``pytest -s tests/test_noise_suppress.py`` để in bảng SNR / méo / thời gian.
Số ngưỡng trong các ``assert`` có chừa biên so với số đo, nhưng KHÔNG chứng minh gì về mic thật
của loa R1, tiếng nhà thật, hay lúc loa đang phát nhạc.
"""

import time

import numpy as np
import pytest

from custom_components.r1_speaker import noise_suppress as ns
from custom_components.r1_speaker.noise_suppress import (HOP, NoiseSettings, NoiseSuppressor)

from .tin_hieu_tong_hop import (RATE, chay, from_pcm, kich_ban, nhieu_hong, nhieu_trang, rms,
                                tieng_nguoi_gia,
                                sine, to_pcm)

BAT = NoiseSettings(enabled=True)
#: Ngưỡng giảm nhiễu thuần (dB) có chừa biên: đo trắng ≈ -12, hồng ≈ -9 (hồng dồn công suất
#: vào vài ô thấp nên nền khó ước lượng hơn).
NGUONG_GIAM = {"trang": -10.0, "hong": -8.0}


def _xu_ly(vao: np.ndarray, settings: NoiseSettings = BAT, khuc: int = 2048) -> np.ndarray:
    """Chạy cả tín hiệu qua bộ khử, bù độ trễ cố định HOP mẫu."""
    return from_pcm(chay(NoiseSuppressor(settings), to_pcm(vao), khuc))[HOP:]


def _do(sach, vao, mask, settings: NoiseSettings = BAT):
    out = _xu_ly(vao, settings)
    n = len(out)
    s, v = sach[:n], vao[:n]
    a = np.zeros(n, bool)
    a[int(1.8 * RATE):int(5.4 * RATE)] = True      # đoạn có tiếng, bỏ 0,3 s đầu cho nền kịp hội tụ
    nz = np.zeros(n, bool)
    nz[int(0.6 * RATE):int(1.4 * RATE)] = True     # đoạn nhiễu thuần
    snr = lambda y: 10 * np.log10(np.sum(s[a] ** 2) / np.sum((y[a] - s[a]) ** 2))
    cor = lambda y: float(np.corrcoef(y[a], s[a])[0, 1])
    return {"snr_vao": snr(v), "snr_ra": snr(out), "cor_vao": cor(v), "cor_ra": cor(out),
            "giam_nhieu_db": 20 * np.log10(rms(out[nz]) / rms(v[nz]))}


# ── FFT thuần Python đúng so với numpy ────────────────────────────────────────────────

def test_fft_thuc_khop_numpy_va_dao_nguoc():
    x = np.random.default_rng(7).standard_normal(ns.FRAME)
    X = ns.rfft(list(x))
    assert np.max(np.abs(np.array(X) - np.fft.rfft(x))) < 1e-9
    assert np.max(np.abs(np.array(ns.irfft(X)) - x)) < 1e-9


# ── Hợp đồng ──────────────────────────────────────────────────────────────────────────

def test_tat_thi_khung_khong_doi_ke_ca_khung_le():
    bo = NoiseSuppressor(NoiseSettings(enabled=False))
    for khung in (b"", b"\x01", b"\x01\x02\x03", to_pcm(sine(500, 0.1, 9000))):
        assert bo.process(khung) is khung            # cùng đối tượng bytes: không đụng tới
    assert ns.build(NoiseSettings(enabled=False)) is None
    assert isinstance(ns.build(BAT), NoiseSuppressor)


def test_mac_dinh_tat_va_ghi_ro_chua_do():
    from custom_components.r1_speaker import const
    assert NoiseSettings().enabled is False and const.DEFAULT_NOISE_ENABLE is False


@pytest.mark.parametrize("byte", [0, 1, 2, 3, 333, 511, 512, 513, 2047, 2048, 2049, 4097])
def test_khung_do_dai_bat_ky_khong_sap_va_giu_do_dai(byte):
    bo = NoiseSuppressor(BAT)
    pcm = to_pcm(nhieu_trang(5000) * 3000)[:byte] + (b"\x7f" if byte % 2 else b"")
    pcm = pcm[:byte]
    out = bo.process(pcm)
    assert len(out) == byte // 2 * 2                 # byte lẻ cuối bị bỏ, như mic.amplify


def test_luong_chia_khuc_le_bao_toan_tong_do_dai_va_khong_sap():
    pcm = to_pcm(nhieu_trang(RATE) * 3000)
    bo = NoiseSuppressor(BAT)
    tong, i = 0, 0
    for kich in (2, 6, 998, 2, 30, 4096, 1, 22, 640):          # độ dài byte lẻ chẵn lẫn lộn
        khung = pcm[i:i + kich]
        i += kich
        tong += len(bo.process(khung))
    assert tong == sum(k // 2 * 2 for k in (2, 6, 998, 2, 30, 4096, 1, 22, 640))


def test_tin_hieu_toi_da_va_im_lang_khong_tran_khong_nan():
    bo = NoiseSuppressor(BAT)
    to = to_pcm(np.where(np.arange(RATE) % 2, 32767.0, -32768.0))     # toàn biên cực đại
    im = bytes(2 * RATE)
    for khung in (to, im, to, im):
        out = chay(bo, khung)
        assert len(out) == len(khung)
    assert np.all(np.abs(from_pcm(out)) <= 32767)


def test_do_tre_thuat_toan_dung_bang_hop_va_do_tre_xu_ly_ghi_lai():
    """Độ trễ = HOP mẫu (16 ms) với khúc mic thật; tương quan chéo tìm đúng mẫu."""
    x = nhieu_trang(RATE) * 4000
    y = from_pcm(chay(NoiseSuppressor(NoiseSettings(True, 0.0, 4.0)), to_pcm(x)))
    # strength 0 dB = hệ số lọc ≥ 1 mọi nơi → bộ khử là thông suốt, chỉ còn độ trễ
    best = max(range(0, 600), key=lambda d: float(np.dot(y[d:d + 8000], x[:8000])))
    assert best == HOP == 256
    assert HOP / RATE == pytest.approx(0.016)
    assert NoiseSuppressor.latency_samples == HOP


def test_reset_quen_nen_cu():
    bo = NoiseSuppressor(BAT)
    ồn = to_pcm(nhieu_trang(RATE) * 3000)
    chay(bo, ồn)
    assert bo._noise is not None
    bo.reset()
    assert bo._noise is None and bo._frames == 0


# ── Đo chất lượng ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("loai", ["trang", "hong"])
def test_nhieu_thuan_bi_giam_manh(loai):
    n = 4 * RATE
    nhieu = (nhieu_trang(n) if loai == "trang" else nhieu_hong(n)) * 3000
    out = _xu_ly(nhieu)
    seg = slice(RATE, None)                          # bỏ 1 s đầu cho nền hội tụ
    giam = 20 * np.log10(rms(out[seg]) / rms(nhieu[HOP:][seg]))
    print(f"\nnhiễu thuần {loai}: giảm {giam:.1f} dB (strength mặc định "
          f"{NoiseSettings().strength_db} dB)")
    assert giam < NGUONG_GIAM[loai]


def test_tien_hieu_sine_giu_duoc_trong_nhieu():
    """Nhiễu thuần 1,5 s rồi sine 1 kHz (SNR 10 dB): biên độ 1 kHz ra ≥ 90% biên độ vào."""
    n = 5 * RATE
    mask = np.zeros(n, bool)
    mask[int(1.5 * RATE):] = True
    sach = np.where(mask, sine(1000, 5, 6000), 0.0)
    vao = sach + 6000 / np.sqrt(2) / 10 ** 0.5 * nhieu_trang(n)
    out = _xu_ly(vao)
    t = np.arange(n) / RATE

    def bien_do(y, a, b):
        y = y[a:b]
        tt = t[a:b]
        return 2 * abs(np.mean(y * np.exp(-2j * np.pi * 1000 * tt)))

    a, b = int(2.5 * RATE), int(4.5 * RATE)
    ty_le = bien_do(out, a, b) / bien_do(vao[HOP:], a, b)
    print(f"\nsine 1 kHz: biên độ ra / vào = {ty_le:.3f} ({20 * np.log10(ty_le):+.2f} dB)")
    assert ty_le > 0.9


def test_bang_snr_va_meo_o_0_5_10_db():
    dong = []
    for loai in ("trang", "hong"):
        for snr in (0, 5, 10):
            sach, vao, mask = kich_ban(snr, loai)
            r = _do(sach, vao, mask)
            dong.append((loai, snr, r))
            # SNR đầu ra phải TỐT HƠN đầu vào, tiếng không méo hơn đầu vào quá 0,02 tương quan
            assert r["snr_ra"] > r["snr_vao"] + 1.0, (loai, snr, r)
            assert r["cor_ra"] > r["cor_vao"] - 0.02, (loai, snr, r)
            assert r["giam_nhieu_db"] < NGUONG_GIAM[loai], (loai, snr, r)
    print("\nloại   SNR vào  SNR ra   tương quan vào→ra   giảm nhiễu thuần")
    for loai, snr, r in dong:
        print(f"{loai:5s} {r['snr_vao']:6.1f}  {r['snr_ra']:6.1f}   "
              f"{r['cor_vao']:.3f} → {r['cor_ra']:.3f}      {r['giam_nhieu_db']:6.1f} dB")


def test_thoi_gian_xu_ly_tren_1_giay_am_thanh():
    sach, vao, mask = kich_ban(5, "trang", giay=3.0)
    pcm = to_pcm(vao)
    bo = NoiseSuppressor(BAT)
    tren_khuc = []
    t0 = time.perf_counter()
    for i in range(0, len(pcm), 2048):
        t = time.perf_counter()
        bo.process(pcm[i:i + 2048])
        tren_khuc.append(time.perf_counter() - t)
    giay_cpu_tren_giay_am = (time.perf_counter() - t0) / 3.0
    print(f"\nthời gian xử lý / 1 s âm thanh: {giay_cpu_tren_giay_am * 1000:.0f} ms; "
          f"khúc 64 ms: trung bình {np.mean(tren_khuc) * 1000:.1f} ms, "
          f"lớn nhất {max(tren_khuc) * 1000:.1f} ms; độ trễ thuật toán {HOP / RATE * 1000:.0f} ms")
    assert giay_cpu_tren_giay_am < 0.5               # đo ≈ 0,1 s; ngưỡng rộng cho máy chậm


def test_gioi_han_da_biet_luong_bat_dau_bang_tieng_noi_bi_ep():
    """Mô tả giới hạn ĐÃ ĐO chứ không phải ưu điểm: luồng mở đầu ngay bằng tiếng nói (chưa có
    đoạn nhiễu thuần để học nền, như ``wake_mode=speaker`` mở luồng sau từ đánh thức) thì giây
    đầu bị ép ~3 dB (≈0,7 biên độ) rồi mới hồi phục. Hồi phục chưa tới 1,0 vì nền còn lẫn tiếng."""
    n = 4 * RATE
    giong = tieng_nguoi_gia(4) * 3000
    vao = giong + nhieu_trang(n) * 3000 / 10 ** 0.5
    ra = _xu_ly(vao)
    dau = slice(0, RATE)
    cuoi = slice(3 * RATE, 4 * RATE)
    ty_dau = rms(ra[dau]) / rms(giong[dau])
    ty_cuoi = rms(ra[cuoi]) / rms(giong[cuoi])
    print(f"\nbắt đầu bằng tiếng nói: biên độ ra/sạch giây đầu {ty_dau:.2f}, giây 4 {ty_cuoi:.2f}")
    assert 0.5 < ty_dau < ty_cuoi <= 1.1


def test_gioi_han_da_biet_sine_co_san_tu_dau_luong_bi_ep_ve_san():
    """Giới hạn ĐÃ ĐO: luồng mở đầu ngay bằng một âm ổn định (chưa có nền để học) thì cả âm bị
    coi là nền và ép về sàn (strength 12 dB → ~0,25 biên độ) suốt thời gian."""
    n = 4 * RATE
    x = sine(1000, 4, 6000) + nhieu_trang(n) * 6000 / np.sqrt(2) / 10 ** 0.5
    ra = _xu_ly(x)
    t = np.arange(len(ra)) / RATE
    a, b = 2 * RATE, 4 * RATE - HOP
    ty_le = 2 * abs(np.mean(ra[a:b] * np.exp(-2j * np.pi * 1000 * t[a:b]))) / 6000
    print(f"\nsine có sẵn từ đầu: biên độ ra/vào giây 2–4 = {ty_le:.2f}")
    assert ty_le < 0.4


def test_gioi_han_da_biet_tieng_on_dinh_keo_dai_bi_nuot_dan_vao_nen():
    """Giới hạn ĐÃ ĐO: nhiễu 1,5 s rồi sine 1 kHz kéo dài 16,5 s (SNR 10 dB). Nền nhích lên
    3 dB/s trong khung «có tiếng» nên sine ổn định bị nuốt dần: ~0,99 ở giây 2–4, ~0,75 ở giây
    8–10, ~0,25 (sàn) ở giây 12–15. Liên quan tới nhạc đang phát có âm kéo dài."""
    n = 18 * RATE
    x = np.zeros(n)
    x[int(1.5 * RATE):] = sine(1000, 16.5, 6000)
    x += nhieu_trang(n) * 6000 / np.sqrt(2) / 10 ** 0.5
    ra = _xu_ly(x)
    t = np.arange(len(ra)) / RATE

    def ty(a, b):
        a, b = int(a * RATE), int(b * RATE)
        return (abs(np.mean(ra[a:b] * np.exp(-2j * np.pi * 1000 * t[a:b])))
                / abs(np.mean(x[HOP:][a:b] * np.exp(-2j * np.pi * 1000 * t[a:b]))))

    dau, giua, cuoi = ty(2, 4), ty(8, 10), ty(12, 15)
    print(f"\nsine kéo dài: giây 2–4 {dau:.2f}, giây 8–10 {giua:.2f}, giây 12–15 {cuoi:.2f}")
    assert dau > 0.9 and cuoi < 0.4 and dau > giua > cuoi
