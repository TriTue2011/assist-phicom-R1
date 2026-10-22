"""Khử vọng khối NLMS (khu_vong.py): vọng giảm, tiếng người gần mic còn lại, không có tham chiếu thì giữ nguyên."""
import numpy as np

from custom_components.r1_speaker.khu_vong import KhuVong, KHOI_CON

RATE = 16000
D = 32  # trễ loa→mic giả lập (mẫu)


def _tieng_loa(n: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    # làm mượt để gần giọng hơn (băng hẹp)
    k = np.ones(8) / 8
    return np.convolve(x, k, mode="same") * 3000


def _vong(ref: np.ndarray) -> np.ndarray:
    echo = np.zeros(len(ref))
    echo[D:] += 0.6 * ref[:-D]
    echo[D + 1:] += 0.2 * ref[:-D - 1]
    return echo


def _chay(mic: np.ndarray, ref: np.ndarray, ch: int = 320) -> np.ndarray:
    kv = KhuVong(do_tre_mau=D, do_dai=256, mu=1.5)
    out = []
    for i in range(0, len(mic), ch):
        kv.day_ref(ref[i:i + ch].astype("<i2").tobytes())
        part = mic[i:i + ch].astype("<i2").tobytes()
        out.append(np.frombuffer(kv.xu_ly(part), dtype="<i2").astype(np.float64))
    return np.concatenate(out)


def test_vong_giam_it_nhat_10db_sau_hoi_tu():
    n = RATE * 6
    ref = _tieng_loa(n)
    mic = _vong(ref) + np.random.default_rng(2).standard_normal(n) * 20
    e = _chay(mic, ref)
    lo = RATE * 3  # bỏ 3 s đầu khi bộ lọc đang hội tụ
    erle = 10 * np.log10(np.mean(mic[lo:] ** 2) / np.mean(e[lo:] ** 2))
    assert erle >= 10.0, f"ERLE {erle:.1f} dB < 10 dB"


def test_nguoi_noi_cung_luc_van_con():
    n = RATE * 6
    ref = _tieng_loa(n)
    t = np.arange(n) / RATE
    giong = np.where(t > 3.0, 1500 * np.sin(2 * np.pi * 300 * t), 0.0)  # người gần mic nói từ giây 3
    mic = _vong(ref) + giong + np.random.default_rng(3).standard_normal(n) * 20
    e = _chay(mic, ref)
    doan = slice(int(4.0 * RATE), int(5.5 * RATE))
    tuong_quan = np.corrcoef(e[doan], giong[doan])[0, 1]
    assert tuong_quan > 0.6, f"tương quan với giọng {tuong_quan:.2f} — giọng bị trừ nhầm"


def test_khong_co_tham_chieu_thi_giu_nguyen():
    kv = KhuVong(do_tre_mau=D)
    pcm = np.arange(-160, 160, dtype="<i2").tobytes()
    assert kv.xu_ly(pcm) == pcm


def test_khoi_con_dung_kich_thuoc():
    assert KHOI_CON == 80
    kv = KhuVong(do_tre_mau=0)
    kv.day_ref(np.zeros(1000, dtype="<i2").tobytes())
    pcm = np.zeros(333, dtype="<i2").tobytes()  # không chia hết cho khối con
    assert len(kv.xu_ly(pcm)) == len(pcm)
