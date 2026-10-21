"""AGC + bộ hạn đỉnh: đo trên tín hiệu TỔNG HỢP (sine, nhiễu nền), không chạm loa.

Mức dBFS trong file này là mức RMS: 20·log10(rms / 32768); sine «-20 dBFS» có RMS = 0,1 FS
(đỉnh = RMS·√2). Chạy ``pytest -s`` để in bảng.
"""

import time

import numpy as np
import pytest

from custom_components.r1_speaker import const
from custom_components.r1_speaker.agc import (FULL, LOOKAHEAD, Agc, AgcSettings, Limiter,
                                              LimiterSettings)

from .tin_hieu_tong_hop import RATE, chay, from_pcm, nhieu_trang, rms, sine, to_pcm


def dbfs(x) -> float:
    return float(20 * np.log10(rms(x) / FULL + 1e-12))


def sine_dbfs(muc_db: float, giay: float = 6.0, freq: float = 440.0) -> np.ndarray:
    return sine(freq, giay, FULL * 10 ** (muc_db / 20) * np.sqrt(2))


BAT = AgcSettings(enabled=True, target_db=-20.0, max_gain_db=24.0, silence_db=-55.0)


def test_mac_dinh_tat_ca_hai_va_ghi_ro():
    assert AgcSettings().enabled is False and LimiterSettings().enabled is False
    assert const.DEFAULT_AGC_ENABLE is False and const.DEFAULT_LIMITER_ENABLE is False
    assert LimiterSettings().ceiling == 0.89


def test_tat_thi_khung_khong_doi():
    for bo in (Agc(AgcSettings(enabled=False)), Limiter(LimiterSettings(enabled=False))):
        for khung in (b"", b"\x01", b"\x01\x02\x03", to_pcm(sine_dbfs(-20, 0.1))):
            assert bo.process(khung) is khung


# ── AGC ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("muc", [-40, -20, -6])
def test_agc_dua_sine_ve_dich(muc):
    x = sine_dbfs(muc)
    y = from_pcm(chay(Agc(BAT), to_pcm(x)))
    ra = dbfs(y[-RATE:])
    print(f"\nAGC sine vào {muc:+d} dBFS → ra {ra:+.2f} dBFS (đích {BAT.target_db:+.0f})")
    assert abs(ra - BAT.target_db) < 1.0


def test_agc_bang_do_sau_limiter_khong_vuot_tran():
    print("\nvào dBFS | AGC ra (giây cuối) | đỉnh sau AGC+limiter / FS | trần")
    lim = LimiterSettings(enabled=True, ceiling=0.89)
    for muc in (-40, -20, -6):
        x = sine_dbfs(muc)
        a = chay(Agc(BAT), to_pcm(x))
        z = from_pcm(chay(Limiter(lim), a))
        dinh = float(np.abs(z).max()) / FULL
        print(f"{muc:+4d}      | {dbfs(from_pcm(a)[-RATE:]):+6.2f}             | "
              f"{dinh:.4f}                    | 0.89")
        assert dinh <= 0.89


def test_agc_khong_khuech_dai_nen_duoi_nguong_im_lang():
    nen = nhieu_trang(6 * RATE) * FULL * 10 ** (-60 / 20)          # -60 dBFS < -55
    a = Agc(BAT)
    y = from_pcm(chay(a, to_pcm(nen)))
    print(f"\nnền -60 dBFS: ra {dbfs(y[-RATE:]):+.2f} dBFS, mức tăng AGC {a.gain_db:+.2f} dB")
    assert dbfs(y[-RATE:]) < -58.5          # làm tròn int16 làm nền nhích; vẫn không bị tăng
    assert a.gain_db <= 0.01


def test_agc_nen_sau_tieng_noi_khong_bi_khuech_dai_bang_muc_tang_con_du():
    """Tiếng nhỏ -40 dBFS (AGC tăng ~ +20 dB) rồi im sang nền -62 dBFS: mức tăng phải thả về 0 dB
    chứ không giữ +20 dB làm nền thành -42 dBFS."""
    x = np.concatenate([sine_dbfs(-40, 3.0), nhieu_trang(5 * RATE) * FULL * 10 ** (-62 / 20)])
    a = Agc(BAT)
    y = from_pcm(chay(a, to_pcm(x)))
    assert a.gain_db > -0.5 and a.gain_db < 3.0, a.gain_db           # sau 5 s: gần 0 dB
    assert dbfs(y[-RATE:]) < -58


def test_agc_tran_muc_tang_toi_da():
    x = sine_dbfs(-50)                                              # trên ngưỡng im lặng -55
    y = from_pcm(chay(Agc(AgcSettings(True, -20.0, 12.0, -55.0)), to_pcm(x)))
    assert dbfs(y[-RATE:]) == pytest.approx(-50 + 12, abs=1.0)      # -38, không lên -20


def test_agc_hang_so_thoi_gian_giam_nhanh_tang_cham():
    """Đo theo khối 128 mẫu (8 ms). Tiếng nhỏ → to đột ngột: mức tăng phải hạ ≥12 dB trong
    ≤0,3 s (attack 50 ms). To → nhỏ: tăng lại ≥8 dB phải mất ≥0,3 s (release 1 s) và lâu hơn
    hạ ít nhất 3 lần."""
    cho = BAT.attack_s
    a = Agc(BAT)
    nho = list(sine_dbfs(-30, 2.0))
    a.run(nho)
    g0 = a.gain_db
    to = list(sine_dbfs(-6, 2.0))
    t_giam = None
    for i in range(0, len(to), 128):
        a.run(to[i:i + 128])
        if t_giam is None and a.gain_db < g0 - 12:
            t_giam = (i + 128) / RATE
    g1 = a.gain_db
    t_tang = None
    for i in range(0, len(nho), 128):
        a.run(nho[i:i + 128])
        if t_tang is None and a.gain_db > g1 + 8:
            t_tang = (i + 128) / RATE
    print(f"\nAGC: hạ ≥12 dB sau {t_giam:.3f} s (attack {cho} s); tăng ≥8 dB sau {t_tang:.3f} s "
          f"(release {BAT.release_s} s)")
    assert t_giam is not None and t_tang is not None
    assert 0.0 < t_giam <= 0.3 and t_tang >= 0.3 and t_tang > 3 * t_giam


def test_agc_thoi_gian_va_do_dai():
    pcm = to_pcm(sine_dbfs(-30, 3.0))
    a = Agc(BAT)
    t = time.perf_counter()
    out = chay(a, pcm)
    dt = (time.perf_counter() - t) / 3
    print(f"\nAGC: {dt * 1000:.0f} ms / 1 s âm thanh, không trễ (không nhìn trước)")
    assert len(out) == len(pcm) and dt < 0.25
    assert len(Agc(BAT).process(b"\x01\x02\x03")) == 2 and Agc(BAT).process(b"") == b""


# ── Bộ hạn đỉnh ───────────────────────────────────────────────────────────────────────

def test_limiter_khong_mau_nao_vuot_tran_ca_khi_goi_sat_bien():
    cap = 0.89
    ngau = np.random.default_rng(4)
    for x in (sine(300, 2, 32767.0), ngau.standard_normal(RATE) * 20000,
              np.where(np.arange(RATE) % 40 < 20, 32767.0, -32768.0)):
        z = from_pcm(chay(Limiter(LimiterSettings(True, cap)), to_pcm(x)))
        assert np.abs(z).max() <= int(cap * 32767)


def test_limiter_khong_meo_cung_va_do_tre_co_dinh():
    """Sine 300 Hz biên độ 0,99 FS, trần 0,5: đầu ra vẫn là sine (tương quan ≈ 1, méo hài thấp),
    KHÔNG bị cắt phẳng; độ trễ đúng LOOKAHEAD mẫu."""
    x = sine(300, 1.0, 0.99 * FULL)
    z = from_pcm(chay(Limiter(LimiterSettings(True, 0.5)), to_pcm(x)))
    y = z[LOOKAHEAD:]                      # bù độ trễ cố định
    ref = x[:len(y)]
    seg = slice(2000, 14000)               # sau khi hệ số đã ổn
    tuong_quan = float(np.corrcoef(y[seg], ref[seg])[0, 1])
    # phân rã: thành phần cơ bản 300 Hz + dư; THD = dư / cơ bản
    t = np.arange(len(y))[seg] / RATE
    c = 2 * np.mean(y[seg] * np.exp(-2j * np.pi * 300 * t))
    du = y[seg] - np.real(c * np.exp(2j * np.pi * 300 * t))
    thd = rms(du) / (abs(c) / np.sqrt(2))
    print(f"\nlimiter trần 0.5 trên sine 0.99 FS: đỉnh {np.abs(y).max() / FULL:.3f} FS, "
          f"tương quan {tuong_quan:.5f}, THD {thd * 100:.2f}%; trễ {LOOKAHEAD} mẫu = "
          f"{LOOKAHEAD / RATE * 1000:.0f} ms")
    assert np.abs(y).max() <= int(0.5 * 32767)
    assert tuong_quan > 0.999 and thd < 0.02
    # cắt cứng cùng biên độ làm đối chứng: THD của sine bị cắt ở 0,5/0,99 cao hơn nhiều
    cat = np.clip(x, -0.5 * 32767, 0.5 * 32767)
    c2 = 2 * np.mean(cat[seg] * np.exp(-2j * np.pi * 300 * t))
    thd_cat = rms(cat[seg] - np.real(c2 * np.exp(2j * np.pi * 300 * t))) / (abs(c2) / np.sqrt(2))
    assert thd < thd_cat / 5


def test_limiter_tin_hieu_duoi_tran_di_qua_khong_doi_chi_tre():
    x = sine_dbfs(-12, 1.0)
    z = from_pcm(chay(Limiter(LimiterSettings(True, 0.89)), to_pcm(x)))
    assert np.array_equal(z[LOOKAHEAD:], to_pcm_round(x)[:len(z) - LOOKAHEAD])


def to_pcm_round(x):
    return from_pcm(to_pcm(x))


def test_limiter_khung_le_va_nhieu_kich_co_khong_sap_giu_do_dai():
    bo = Limiter(LimiterSettings(True, 0.5))
    pcm = to_pcm(sine(200, 0.5, 32000))
    tong = 0
    i = 0
    for k in (2, 6, 998, 2, 30, 4096, 1, 22, 640, 0, 3):
        tong += len(bo.process(pcm[i:i + k]))
        i += k
    assert tong == sum(k // 2 * 2 for k in (2, 6, 998, 2, 30, 4096, 1, 22, 640, 0, 3))


def test_limiter_thoi_gian_xu_ly_ca_luc_dang_han():
    pcm = to_pcm(sine(300, 3.0, 0.99 * FULL))
    bo = Limiter(LimiterSettings(True, 0.5))
    t = time.perf_counter()
    chay(bo, pcm)
    dt = (time.perf_counter() - t) / 3
    print(f"\nlimiter (đang hạn liên tục): {dt * 1000:.0f} ms / 1 s âm thanh")
    assert dt < 0.5
