"""Khử vọng miền tần số (PBFDAF) cho phiên đàm thoại song công — thay bộ NLMS thời gian ngắn, dùng numpy (HA đã có).

Vì sao tự viết: ``pywebrtc-audio`` (AEC3) KHÔNG dùng được trong tiến trình HA vì cùng ``pyspeex_noise`` của Assist đăng ký lớp ``AudioProcessor``
(nạp cái nọ thì cái kia lỗi «already registered»). Bộ này cùng giao diện ``day_ref`` / ``xu_ly`` với ``khu_vong.KhuVong`` nên cắm thay được.

Thuật toán (kinh điển, không phát minh gì mới):
* Bộ lọc thích nghi chia khối (P khối × N mẫu = ~128 ms) trong miền tần số, overlap-save, chuẩn hoá theo công suất tín hiệu loa.
* Bước thích nghi biến thiên: tỉ lệ «tiếng vọng ước lượng / sai số» — người gần micro nói chen (sai số lớn hơn vọng ước lượng) thì bước giảm, bộ lọc
  không bị tiếng người làm hỏng (double-talk).
* ĐỘ TRỄ LỚN (loa → mic qua đường phát của R1, hàng trăm mili giây) do bộ ước lượng GCC-PHAT riêng tìm và dịch tín hiệu loa, nên bộ lọc chỉ phải
  phủ phần vang phòng ngắn.
* Căn thời gian THEO ĐỒNG HỒ: tiếng gửi xuống loa chỉ có khi bên kia nói (không liên tục) còn mic chạy liên tục. Mỗi khúc loa được đặt vào trục thời
  gian theo lúc nó tới (nối tiếp khúc trước nếu dồn cục), nên khoảng lặng không làm lệch tham chiếu (bộ NLMS cũ đếm mẫu nên lệch sau mỗi quãng lặng).

Đầu ra luôn dài bằng đầu vào (khúc đầu thiếu một khối thì chèn câm; trễ cố định một khối = 16 ms). Chưa có tiếng loa → trả nguyên mic.
"""

from __future__ import annotations

import time

import numpy as np

RATE = 16000
N = 256                  # mẫu mỗi khối (16 ms)
P = 8                    # số khối của bộ lọc → 128 ms phủ vang phòng
H = RATE * 6             # trục thời gian giữ lại (mẫu)
TRE_TOI_DA = RATE * 1    # độ trễ loa → mic tối đa dò được (1 s)
CHU_KY_UOC_LUONG = RATE // 2
CUA_SO_UOC_LUONG = RATE * 3
MU0 = 0.6
DELTA = 1e-2
KHOI_HOC_DAU = 150        # số khối có tiếng loa đầu tiên học với bước cố định (chưa có vọng ước lượng nên bước biến thiên sẽ kẹt ở 0)
SAN_BUOC = 0.08           # sau đó bước không nhỏ hơn MU0 × ngần này (người nói chen dài cũng không làm bộ lọc chết hẳn)
NGUONG_LOA = 20.0 ** 2   # công suất trung bình khối loa dưới mức này coi là im lặng (không thích nghi)
DO_TIN_CAY = 8.0         # đỉnh GCC-PHAT / trung vị tối thiểu để tin độ trễ
BUOC_DOI_TRE = RATE // 50  # độ trễ mới lệch hơn 20 ms mới đổi (và xoá bộ lọc)


class KhuVongFdaf:
    def __init__(self, clock=time.monotonic, tre_ban_dau_ms: int = 0) -> None:
        self._clock = clock
        self._t0: float | None = None
        self.W = np.zeros((P, N + 1), dtype=np.complex64)
        self._hist: list[np.ndarray] = [np.zeros(N + 1, dtype=np.complex64) for _ in range(P)]
        self._pow = np.full(N + 1, 1.0, dtype=np.float32)
        self._far = np.zeros(H, dtype=np.float32)        # trục thời gian: far[i % H] = mẫu loa tại chỉ số i
        self._near = np.zeros(H, dtype=np.float32)
        self._far_end = 0                                # chỉ số sau mẫu loa cuối đã đặt
        self._n = 0                                      # chỉ số mẫu mic kế tiếp (trục thời gian chung)
        self._co_ref = False
        self._du = np.zeros(0, dtype=np.float32)         # mic chưa đủ một khối
        self._ra = np.zeros(0, dtype=np.float32)         # đã xử lý, chưa trả
        self._tre_chen = True
        self.delay = int(tre_ban_dau_ms * RATE / 1000)
        self._ke = 0                                     # lần ước lượng độ trễ kế tiếp (chỉ số mẫu mic)
        self._ung_vien = None                            # độ trễ ứng viên chờ xác nhận lần hai
        self.tin_cay = 0.0
        self._da_hoc = 0                                 # số khối đã thích nghi
        self.erle_db = 0.0                               # trung bình trượt (dB) mức giảm trên khối có tiếng loa — chẩn đoán

    # -- tham chiếu (tiếng đã gửi xuống loa) ---------------------------------------------------------
    def _t(self) -> float:
        now = self._clock()
        if self._t0 is None:
            self._t0 = now
        return now - self._t0

    def day_ref(self, pcm: bytes) -> None:
        """Bơm khúc PCM16 mono 16 kHz mà HA vừa gửi xuống loa; đặt vào trục thời gian theo lúc tới (nối tiếp khúc trước nếu dồn cục)."""
        x = np.frombuffer(pcm[:len(pcm) - (len(pcm) % 2)], dtype="<i2").astype(np.float32)
        if x.size == 0:
            return
        pos = max(self._far_end, int(self._t() * RATE))
        pos = max(pos, self._n - H // 2)                 # không ghi lùi quá cũ
        idx = (pos + np.arange(x.size)) % H
        # Khoảng trống giữa khúc trước và khúc này phải là câm (ô cũ của vòng có thể còn tiếng 6 giây trước).
        if pos > self._far_end:
            gap = min(pos - self._far_end, H)
            self._far[(self._far_end + np.arange(gap)) % H] = 0.0
        self._far[idx] = x
        self._far_end = pos + x.size
        self._co_ref = True

    def _far_block(self, start: int, n: int) -> np.ndarray:
        """Mẫu loa tại các chỉ số [start, start+n) (câm ngoài phạm vi đã ghi / quá cũ)."""
        idx = np.arange(start, start + n)
        ok = (idx >= max(0, self._far_end - H)) & (idx < self._far_end)
        out = np.zeros(n, dtype=np.float32)
        out[ok] = self._far[idx[ok] % H]
        return out

    # -- xử lý ---------------------------------------------------------------------------------------------
    def xu_ly(self, pcm: bytes) -> bytes:
        if not self._co_ref:
            return pcm
        n_vao = len(pcm) - (len(pcm) % 2)
        d = np.frombuffer(pcm[:n_vao], dtype="<i2").astype(np.float32)
        buf = np.concatenate([self._du, d])
        k = buf.size // N * N
        for i in range(0, k, N):
            self._ra = np.concatenate([self._ra, self._khoi(buf[i:i + N])])
        self._du = buf[k:]
        if self._tre_chen:
            self._ra = np.concatenate([np.zeros(N, dtype=np.float32), self._ra])
            self._tre_chen = False
        out, self._ra = self._ra[:d.size], self._ra[d.size:]
        if out.size < d.size:
            out = np.concatenate([out, np.zeros(d.size - out.size, dtype=np.float32)])
        res = np.clip(np.round(out), -32768, 32767).astype("<i2").tobytes()
        return res + pcm[n_vao:]

    def _khoi(self, d: np.ndarray) -> np.ndarray:
        s = self._n                                      # chỉ số mẫu mic đầu khối
        self._near[(s + np.arange(N)) % H] = d
        self._n += N
        self._uoc_luong_tre()
        x_cur = self._far_block(s - self.delay, N)
        x_prev = self._far_block(s - self.delay - N, N)
        X = np.fft.rfft(np.concatenate([x_prev, x_cur]).astype(np.float32)).astype(np.complex64)
        self._hist.insert(0, X)
        del self._hist[P:]
        pw = sum(np.abs(h) ** 2 for h in self._hist)
        self._pow = (0.9 * self._pow + 0.1 * pw).astype(np.float32)
        pnorm = np.maximum(self._pow, pw).astype(np.float32)   # khi loa bật lại sau im, công suất làm mượt còn nhỏ: dùng mức tức thời (tránh bước quá lớn)
        Y = sum(self.W[p] * self._hist[p] for p in range(P))
        y = np.fft.irfft(Y, 2 * N)[N:].astype(np.float32)
        e = d - y
        e_loa = float(np.mean(x_cur * x_cur))
        if e_loa < NGUONG_LOA:                           # loa im: không có vọng để học, trả mic nguyên
            return d
        dn, ey, ee = float(np.mean(d * d)) + 1e-6, float(np.mean(y * y)) + 1e-6, float(np.mean(e * e)) + 1e-6
        if ee > 1.5 * dn and self._da_hoc >= KHOI_HOC_DAU:      # phát tán (tệ hơn mic thô): thu nhỏ bộ lọc, KHÔNG bao giờ trả tệ hơn mic
            self.W *= 0.5
            return d
        self.erle_db = 0.95 * self.erle_db + 0.05 * 10 * np.log10(dn / ee)
        # Bước biến thiên: người nói chen làm sai số lớn hơn vọng ước lượng → bước nhỏ lại (bảo vệ bộ lọc).
        if self._da_hoc < KHOI_HOC_DAU:
            mu = MU0
        else:
            mu = MU0 * min(1.0, max(SAN_BUOC, ey / ee))
        self._da_hoc += 1
        E = np.fft.rfft(np.concatenate([np.zeros(N, dtype=np.float32), e])).astype(np.complex64)
        g = (mu * E / (pnorm + DELTA * float(np.mean(pnorm)) + 1e-3)).astype(np.complex64)
        for p in range(P):
            w = np.fft.irfft(self.W[p] + np.conj(self._hist[p]) * g, 2 * N)
            w[N:] = 0.0                                  # ràng buộc nhân quả
            self.W[p] = np.fft.rfft(w).astype(np.complex64)
        return e

    # -- ước lượng độ trễ loa → mic (GCC-PHAT) --------------------------------------------------------------
    def _uoc_luong_tre(self) -> None:
        if self._n < self._ke or self._n < CUA_SO_UOC_LUONG:
            return
        self._ke = self._n + CHU_KY_UOC_LUONG
        a = self._n - CUA_SO_UOC_LUONG
        d = self._near[(a + np.arange(CUA_SO_UOC_LUONG)) % H]
        x = self._far_block(a - TRE_TOI_DA, CUA_SO_UOC_LUONG + TRE_TOI_DA)
        if float(np.mean(x * x)) < NGUONG_LOA or float(np.mean(d * d)) < 1.0:
            return
        m = 1 << int(np.ceil(np.log2(x.size + d.size)))
        Xf, Df = np.fft.rfft(x, m), np.fft.rfft(d, m)
        # r[k] = Σ_n d[n]·x[n+k] (FT = conj(D)·X): d[i] ≈ x[i + TRE_TOI_DA - tre] nên đỉnh ở k = TRE_TOI_DA - tre ∈ [0, TRE_TOI_DA].
        cross = np.conj(Df) * Xf
        r = np.fft.irfft(cross / (np.abs(cross) + 1e-9), m)
        seg = r[:TRE_TOI_DA + 1]
        k = int(np.argmax(seg))
        tin_cay = float(seg[k] / (np.median(np.abs(seg)) + 1e-9))
        self.tin_cay = tin_cay
        if tin_cay < DO_TIN_CAY:
            return
        tre = TRE_TOI_DA - k
        if abs(tre - self.delay) <= BUOC_DOI_TRE:
            self._ung_vien = None
            return
        if self._ung_vien is not None and abs(self._ung_vien - tre) <= BUOC_DOI_TRE:   # hai lần liên tiếp cùng kết quả mới đổi
            self.delay, self._ung_vien = tre, None
            self.W[:] = 0                                # đổi độ trễ: bộ lọc cũ vô nghĩa → học lại nhanh (bước cố định)
            self._da_hoc = 0
            for i in range(P):
                self._hist[i][:] = 0
        else:
            self._ung_vien = tre
