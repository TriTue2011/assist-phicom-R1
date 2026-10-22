"""Khử vọng (AEC) cho đàm thoại song công: trừ tiếng HA đã phát xuống loa khỏi luồng mic.

Thuật toán: NLMS theo khối (block NLMS) trên tín hiệu tham chiếu = PCM HA đã bơm xuống loa,
trễ ``do_tre`` mẫu (loa → mic). Cập nhật bộ lọc bị bỏ qua khi: mic bão hoà (clip), hoặc
mic lớn hơn rõ rệt so với tiếng vọng dự đoán (người gần micro đang nói — double-talk).
Không có tiếng vọng dự đoán thì trả nguyên khúc mic. Cần numpy (HA có sẵn).
"""
from __future__ import annotations

import numpy as np

RATE = 16000
CLIP = 32000.0
KHOI_CON = 80          # 5 ms: cập nhật bộ lọc thường xuyên (ERLE tốt hơn khối lớn)


class KhuVong:
    def __init__(self, do_tre_mau: int = 0, do_dai: int = 256, mu: float = 1.5) -> None:
        self.do_tre = max(0, int(do_tre_mau))
        self.L = int(do_dai)
        self.mu = float(mu)
        self.w = np.zeros(self.L)
        self._ref = np.zeros(self.do_tre + 2 * RATE)   # đệm tham chiếu (trễ + 2 s)
        self._ghi = 0          # chỉ số ghi trong đệm (tuyệt đối, mod độ dài)
        self._doc = -self.do_tre  # vị trí đọc tham chiếu cho khúc mic kế tiếp (tuyệt đối)
        self._co_ref = False

    def day_ref(self, pcm: bytes) -> None:
        """Bơm khúc PCM16 mono 16 kHz mà HA vừa gửi xuống loa."""
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        n = len(self._ref)
        for v in x:
            self._ref[self._ghi % n] = v
            self._ghi += 1
        self._co_ref = True

    def _lay_ref(self, n: int) -> np.ndarray:
        """Lấy n mẫu tham chiếu liền sau vị trí đọc (mẫu chưa có → 0)."""
        n_buf = len(self._ref)
        out = np.zeros(n)
        for i in range(n):
            t = self._doc + i
            if 0 <= t < self._ghi:
                out[i] = self._ref[t % n_buf]
        self._doc += n
        return out

    def xu_ly(self, pcm: bytes) -> bytes:
        """Khử vọng một khúc mic PCM16; trả khúc đã trừ tiếng vọng (cùng độ dài).
        Cập nhật bộ lọc theo khối con KHOI_CON mẫu (hội tụ nhanh hơn một lần cho cả khúc)."""
        d = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        if len(d) == 0 or not self._co_ref:
            return pcm
        out = [self._xu_ly_khoi(d[i:i + KHOI_CON]) for i in range(0, len(d), KHOI_CON)]
        return np.clip(np.round(np.concatenate(out)), -32768, 32767).astype("<i2").tobytes()

    def _xu_ly_khoi(self, d: np.ndarray) -> np.ndarray:
        n = len(d)
        x = self._lay_ref(n)
        # ma trận trượt: hàng t chứa x[t-L+1..t] (mẫu trước khúc lấy từ đệm)
        hist = np.concatenate([np.zeros(self.L - 1), x])
        X = np.lib.stride_tricks.sliding_window_view(hist, self.L)[:n]
        y = X @ self.w
        e = d - y
        clip = np.max(np.abs(d)) >= CLIP
        rms_d = np.sqrt(np.mean(d * d)); rms_y = np.sqrt(np.mean(y * y))
        # người gần mic đang nói: dự đoán vọng đã có (rms_y đáng kể) mà mic lớn hơn hẳn
        nearend = rms_y > 0.2 * rms_d and rms_d > 2.0 * rms_y + 50.0
        if (not clip) and (not nearend) and np.any(x):
            norm = float(np.sum(X * X)) / n + 1e-3
            self.w += self.mu * (X.T @ e) / (n * norm)
        return e


def uoc_tre(mic: np.ndarray, ref: np.ndarray, toi_da: int = 16000) -> int:
    """Ước lượng trễ (mẫu) loa→mic bằng tương quan chéo; trả 0 nếu không đủ dữ liệu."""
    m = min(len(mic), len(ref), toi_da * 2)
    if m < 1000:
        return 0
    c = np.correlate(mic[:m] - mic[:m].mean(), ref[:m] - ref[:m].mean(), mode="full")
    lag = int(np.argmax(np.abs(c))) - (m - 1)
    return max(0, lag)
