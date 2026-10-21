"""Tín hiệu TỔNG HỢP cho phép đo khử tạp / AGC (không có âm thanh thật, không chạm loa).

Mọi nguồn ngẫu nhiên dùng hạt giống cố định → kết quả đo lặp lại được.
"""

import array

import numpy as np

RATE = 16000


def sine(freq: float, seconds: float, amp: float = 1.0) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return amp * np.sin(2 * np.pi * freq * t)


def tieng_nguoi_gia(seconds: float, seed: int = 1) -> np.ndarray:
    """Chuỗi âm tiết: cao độ f0 trượt 110→190 Hz, 12 hài âm, hình bao formant đổi theo âm tiết
    (đỉnh quanh 500/1500/2500 Hz), biên độ bật-tắt ~4 âm tiết/giây. Chuẩn hoá RMS = 1."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    f0 = 110 + 80 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t))
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    syl = int(0.25 * RATE)
    out = np.zeros(n)
    for h in range(1, 13):
        env = np.zeros(n)
        for s in range(0, n, syl):
            f1, f2 = rng.uniform(350, 800), rng.uniform(1100, 2400)
            freq = h * 150
            g = np.exp(-((freq - f1) / 300) ** 2) + 0.6 * np.exp(-((freq - f2) / 500) ** 2)
            env[s:s + syl] = g
        out += env * np.sin(h * phase)
    am = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t - 1.0)
    am = np.clip(am * 1.6, 0, 1)
    out *= am
    # Phụ âm xát giả: cứ 4 âm tiết có một nhát nhiễu dải 3–7 kHz dài 100 ms (tiếng người thật
    # không chỉ có hài âm thưa; bộ lọc ép quá tay sẽ làm mất những nhát này).
    nhat = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / RATE)
    nhat = np.fft.irfft(nhat * ((f > 3000) & (f < 7000)), n)
    nhat *= 0.5 * np.sqrt(np.mean(out ** 2)) / np.sqrt(np.mean(nhat ** 2))
    gate = np.zeros(n)
    for s in range(0, n, 4 * syl):
        gate[s + syl // 2:s + syl // 2 + int(0.1 * RATE)] = 1.0
    out += nhat * gate
    return out / np.sqrt(np.mean(out ** 2))


def nhieu_trang(n: int, seed: int = 2) -> np.ndarray:
    x = np.random.default_rng(seed).standard_normal(n)
    return x / np.sqrt(np.mean(x ** 2))


def nhieu_hong(n: int, seed: int = 3) -> np.ndarray:
    """Nhiễu hồng (công suất ∝ 1/f), RMS = 1."""
    w = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / RATE)
    f[0] = f[1]
    x = np.fft.irfft(w / np.sqrt(f), n)
    return x / np.sqrt(np.mean(x ** 2))


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2)))


def tron(sach: np.ndarray, nhieu: np.ndarray, snr_db: float, mask: np.ndarray) -> np.ndarray:
    """sạch + nhiễu, nhiễu chỉnh để SNR TRÊN ĐOẠN ``mask`` đúng ``snr_db``."""
    k = rms(sach[mask]) / (rms(nhieu[mask]) * 10 ** (snr_db / 20))
    return sach + k * nhieu


def to_pcm(x: np.ndarray) -> bytes:
    return array.array("h", np.clip(np.round(x), -32768, 32767).astype(np.int16)).tobytes()


def from_pcm(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype="<i2").astype(float)


def chay(bo, pcm: bytes, khuc: int = 2048) -> bytes:
    """Đưa PCM qua ``bo.process`` theo từng khúc ``khuc`` byte như luồng mic thật."""
    return b"".join(bo.process(pcm[i:i + khuc]) for i in range(0, len(pcm), khuc))


def kich_ban(snr_db: float, loai: str, giay: float = 6.0, bien: float = 6000.0):
    """(sạch, nhiễu+sạch, mask đoạn có tiếng). Nhiễu thuần 0–1,5 s và 5,5 s–hết; tiếng
    (sine 1 kHz + tiếng người giả) từ 1,5 s đến 5,5 s."""
    n = int(giay * RATE)
    mask = np.zeros(n, bool)
    mask[int(1.5 * RATE):int(5.5 * RATE)] = True
    voice = tieng_nguoi_gia(giay) * 0.6
    sach = np.where(mask, sine(1000, giay, 0.8) + voice, 0.0)
    sach *= bien / rms(sach[mask])
    nhieu = (nhieu_trang(n) if loai == "trang" else nhieu_hong(n))
    return sach, tron(sach, nhieu, snr_db, mask), mask
