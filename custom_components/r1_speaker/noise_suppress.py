"""Khử tạp âm cho luồng mic của loa R1: PCM16 mono 16 kHz, phía HA (không đụng loa).

Thuật toán: lọc Wiener trên phổ ngắn hạn (spectral gating mềm) với ước lượng nền thích nghi.

* Cửa sổ 512 mẫu = 32 ms, bước nhảy 256 mẫu (chồng lấn 50%), cửa sổ căn-Hann (sin) cho cả
  phân tích lẫn tổng hợp nên cộng chồng lấn khôi phục đúng biên độ khi hệ số lọc = 1.
* Nền tạp ``Nn[k]`` (công suất từng ô tần số) được học khi khung KHÔNG có tiếng người. Khung
  có tiếng người khi trung bình (trên các ô) của công suất/nền, đổi ra dB, vượt ``voice_db``. Ngưỡng
  tương đối (so với nền đang theo dõi) chứ không tuyệt đối, vì mức mic của loa R1 chưa đo và
  còn phụ thuộc mức khuếch đại ``amplify`` đứng trước.
* GIỚI HẠN ĐÃ ĐO (tests/test_noise_suppress.py): tiếng ỔN ĐỊNH kéo dài trong cùng một ô tần
  số (sine thuần, tiếng ù) bị coi là nhiễu và dần bị nuốt vào nền: sau ~8 s còn ~75% biên
  độ, sau ~12 s về sàn; luồng mở đầu ngay bằng một âm kéo dài thì bị ép về sàn ngay. Luồng mở
  đầu bằng tiếng nói bị ép ~3 dB trong giây đầu rồi hồi phục dần.
* Trong khung có tiếng người nền KHÔNG bị cập nhật theo kiểu trung bình, chỉ nhích lên chậm
  ``_RISE_DB_PER_S`` để tiếng ồn nền to dần (quạt, nhạc) cuối cùng cũng được học. Khung không
  có tiếng cũng không được làm nền tăng nhanh hơn mức đó (chặn xoáy ốc nuốt tiếng vào nền).
  Nền không bao giờ bị kéo xuống ngoài phép trung bình ở khung không có tiếng.
* Hệ số lọc theo ước lượng SNR tiên nghiệm kiểu "decision-directed" (Ephraim–Malah): giảm
  "nhiễu nhạc" (các đốm tần số nhấp nháy) so với trừ phổ thô. ``strength_db`` là mức giảm tối
  đa của MỘT ô tần số (sàn hệ số lọc), cũng là mức giảm nền tạp thuần tối đa.

LỰA CHỌN: **thuần Python, không numpy.** Tích hợp có ``requirements: []`` và numpy KHÔNG nằm
trong yêu cầu lõi của Home Assistant (chỉ các thành phần như ``stream`` kéo nó vào), nên không
được giả định nó có. FFT thực 512 điểm làm bằng FFT phức 256 điểm (mẹo gói chẵn/lẻ). Giá
phải trả: tốn CPU hơn bản numpy; thời gian đo được ghi ở ``tests/test_noise_suppress.py`` và
trong báo cáo, có chạy trong vòng lặp sự kiện của HA (xem ``process``).

Độ trễ thuật toán cố định: ``HOP`` mẫu = 16 ms khi khúc vào là bội số của ``HOP`` (khúc mic
thật 2048 byte = 1024 mẫu = 4 bước nhảy). Khúc lẻ: độ dài ra LUÔN bằng độ dài vào; nếu khung
chưa đủ thì chèn câm một lần ở đầu khúc và độ trễ tăng thêm tương ứng (tối đa ``HOP - 1``
mẫu cho cả đời luồng).

Không ném lỗi với dữ liệu lạ: byte lẻ cuối khúc bị bỏ (như ``mic.amplify``).
"""

from __future__ import annotations

import array
import cmath
import math
from dataclasses import dataclass

from .const import (DEFAULT_NOISE_ENABLE, DEFAULT_NOISE_STRENGTH_DB, DEFAULT_NOISE_VOICE_DB,
                    MIC_RATE)

#: Cửa sổ 32 ms, bước nhảy 16 ms (chồng lấn 50%) ở 16 kHz.
FRAME = 512
HOP = FRAME // 2
_BINS = FRAME // 2 + 1

#: Hằng số thuật toán (KHÔNG cấu hình): chọn theo đo trên tín hiệu tổng hợp, chưa đo trên mic thật.
_NOISE_ALPHA = 0.90        # trung bình trượt nền khi khung không có tiếng (hằng số ≈ 160 ms)
_RISE_DB_PER_S = 3.0       # nền được nhích lên tối đa ngần này dB/giây trong khung có tiếng
_DD_ALPHA = 0.98           # hệ số decision-directed
_WARMUP_FRAMES = 6         # ~100 ms đầu luôn học nền (coi là chưa có tiếng)
_EPS = 1e-9
#: Nhân nền khi tính SNR tiên nghiệm. Đo trên tín hiệu tổng hợp (bản cuối): 1,0 cho SNR ra
#: cao nhất ở 0 dB trắng (≈ 7,5 so 7,2 dB) nhưng nhiễu hồng thuần chỉ giảm ~6 dB; 2,0 giảm
#: nhiễu hồng thuần ~8,7 dB (trắng ~11,8 dB) và SNR ra kém 1,0 chừng 0,3–1 dB. Chọn 2,0 vì
#: «nhiễu thuần phải giảm mạnh». Số lớn hơn dễ cắt phụ âm nhiễu của tiếng người thật (CHƯA ĐO).
_OVERSUB = 2.0

_RISE = 10 ** (_RISE_DB_PER_S / 10 * HOP / MIC_RATE)


@dataclass(frozen=True)
class NoiseSettings:
    """Cấu hình khử tạp. Mặc định lấy từ ``const.py`` (CHƯA ĐO trên mic loa R1)."""

    enabled: bool = DEFAULT_NOISE_ENABLE
    #: Giảm tối đa một ô tần số (dB) = sàn hệ số lọc. 0 = không giảm gì.
    strength_db: float = DEFAULT_NOISE_STRENGTH_DB
    #: Khung có tiếng người khi mức vượt nền (trung bình công suất/nền theo ô, dB) lớn hơn ngần này.
    voice_db: float = DEFAULT_NOISE_VOICE_DB


# ── FFT thực thuần Python ─────────────────────────────────────────────────────────────

_M = FRAME // 2
_REV = []
for _i in range(_M):
    _r, _x = 0, _i
    for _ in range(_M.bit_length() - 1):
        _r = (_r << 1) | (_x & 1)
        _x >>= 1
    _REV.append(_r)
#: Hệ số xoay theo tầng: _TW[s] = e^{-2πi j/(2·half)}, j < half, half = 2**s.
_TW = [[cmath.exp(-2j * math.pi * j / (2 * (1 << s))) for j in range(1 << s)]
       for s in range(_M.bit_length() - 1)]
#: e^{-2πik/FRAME}, k = 0.._M
_W = [cmath.exp(-2j * math.pi * k / FRAME) for k in range(_M + 1)]
_WC = [w.conjugate() for w in _W]
_WIN = [math.sin(math.pi * n / FRAME) for n in range(FRAME)]


def _fft(x: list[complex], inverse: bool = False) -> list[complex]:
    """FFT phức _M điểm (cơ số 2, thế chỗ trên bản sao). ``inverse`` có chia _M."""
    a = [x[i] for i in _REV]
    if inverse:
        a = [v.conjugate() for v in a]
    for s, tw in enumerate(_TW):
        half = 1 << s
        size = half << 1
        for base in range(0, _M, size):
            for j in range(half):
                p = base + j
                q = p + half
                t = tw[j] * a[q]
                u = a[p]
                a[p] = u + t
                a[q] = u - t
    if inverse:
        return [v.conjugate() / _M for v in a]
    return a


def rfft(x: list[float]) -> list[complex]:
    """FFT của chuỗi thực FRAME mẫu → _M+1 ô (0..Nyquist)."""
    z = _fft([complex(x[2 * n], x[2 * n + 1]) for n in range(_M)])
    out = [0j] * (_M + 1)
    for k in range(_M + 1):
        zk = z[k % _M]
        zc = z[(_M - k) % _M].conjugate()
        out[k] = (zk + zc) * 0.5 + _W[k] * (zk - zc) * -0.5j
    return out


def irfft(X: list[complex]) -> list[float]:
    """Ngược của ``rfft``: _M+1 ô → FRAME mẫu thực."""
    z = []
    for k in range(_M):
        xc = X[_M - k].conjugate()
        xe = (X[k] + xc) * 0.5
        xo = (X[k] - xc) * 0.5 * _WC[k]
        z.append(xe + 1j * xo)
    z = _fft(z, inverse=True)
    out = [0.0] * FRAME
    for n, v in enumerate(z):
        out[2 * n] = v.real
        out[2 * n + 1] = v.imag
    return out


# ── Bộ khử tạp ────────────────────────────────────────────────────────────────────────

class NoiseSuppressor:
    """Một luồng một đối tượng (có trạng thái). ``process(bytes) -> bytes``.

    Tắt (``enabled=False``) thì ``process`` trả NGUYÊN khúc vào (cùng đối tượng bytes), kể cả
    khúc lẻ, và không giữ trạng thái nào.
    """

    def __init__(self, settings: NoiseSettings | None = None) -> None:
        self.settings = settings or NoiseSettings()
        self._gmin = 10 ** (-max(0.0, self.settings.strength_db) / 20)
        self.reset()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def reset(self) -> None:
        """Quên nền tạp và đệm (gọi khi luồng nối lại)."""
        self._in: list[float] = [0.0] * HOP        # mồi: mẫu thật đầu tiên được chồng lấn đủ
        self._tail: list[float] = [0.0] * HOP
        self._out: list[float] = []
        self._noise: list[float] | None = None
        self._clean_prev = [0.0] * _BINS            # công suất đã khử của khung trước
        self._gain_prev = [1.0] * _BINS
        self._frames = 0

    #: Độ trễ thuật toán (mẫu) khi khúc vào là bội số của HOP.
    latency_samples = HOP

    def process(self, pcm: bytes) -> bytes:
        """Khử tạp một khúc PCM16 mono LE. Độ dài ra = độ dài vào (làm tròn xuống số chẵn byte
        khi đang bật). Chạy ĐỒNG BỘ và tốn CPU thuần Python (xem ghi chú đo): một khúc 64 ms
        chặn vòng lặp sự kiện vài chục mili-giây."""
        if not self.settings.enabled:
            return pcm
        raw = array.array("h")
        raw.frombytes(pcm[: len(pcm) // 2 * 2])
        n = len(raw)
        if n == 0:
            return b""
        self._in.extend(raw)
        while len(self._in) >= FRAME:
            self._frame(self._in[:FRAME])
            del self._in[:HOP]
        out = self._out[:n]
        del self._out[:n]
        if len(out) < n:                       # khúc lẻ: chưa đủ khung → độ trễ tăng, vẫn đủ độ dài
            out = [0.0] * (n - len(out)) + out
        return array.array(
            "h", (-32768 if v < -32768 else 32767 if v > 32767 else int(round(v))
                  for v in out)).tobytes()

    def _frame(self, x: list[float]) -> None:
        spec = rfft([a * b for a, b in zip(x, _WIN)])
        power = [c.real * c.real + c.imag * c.imag for c in spec]
        noise = self._noise
        if noise is None:
            noise = self._noise = [p + _EPS for p in power]
        warm = self._frames < _WARMUP_FRAMES
        # Thống kê giọng: trung bình của P/N trên mọi ô (đổi ra dB). Nhiễu thuần cho ~0 dB, độ
        # lệch chuẩn ~0,3 dB và KHÔNG phụ thuộc màu nhiễu, vì mỗi ô được chuẩn hoá bằng nền của
        # chính nó (tỉ số tổng công suất bị vài ô thấp của nhiễu hồng chi phối nên dao động
        # mạnh; trung bình log lại điếc với tiếng người thưa, chỉ vài ô hài âm).
        stat = 10 * math.log10(sum(p / (nn + _EPS) for p, nn in zip(power, noise)) / _BINS
                               + _EPS)
        voice = (not warm) and stat > self.settings.voice_db
        if voice:
            # Khung có tiếng: chỉ nhích nền LÊN chậm (tiếng ồn nền to dần cuối cùng cũng được
            # học). KHÔNG kéo nền xuống: ước lượng thấp quá làm khung nhiễu thuần bị gắn nhãn
            # «có tiếng» mãi và nền trôi xuống không dừng (đã đo, xem tests).
            for k in range(_BINS):
                nn = noise[k]
                if power[k] > nn:
                    noise[k] = min(nn * _RISE, power[k])
        else:
            a = 0.5 if warm else _NOISE_ALPHA
            cap = 1e30 if warm else _RISE      # nền chỉ được tăng ≤ _RISE_DB_PER_S ngay cả khi
            for k in range(_BINS):             # khung bị coi là «chưa có tiếng» (chặn xoáy ốc
                nn = noise[k]                  # nuốt tiếng người vào nền khi SNR thấp)
                new = a * nn + (1 - a) * power[k]
                noise[k] = new if new < nn * cap else nn * cap
        gmin = self._gmin
        gprev, cprev = self._gain_prev, self._clean_prev
        gains = [1.0] * _BINS
        for k in range(_BINS):
            nn = noise[k] * _OVERSUB + _EPS
            post = power[k] / nn
            xi = _DD_ALPHA * cprev[k] / nn + (1 - _DD_ALPHA) * (post - 1.0 if post > 1.0 else 0.0)
            g = xi / (1.0 + xi)
            gains[k] = gmin if g < gmin else g
        for k in range(_BINS):
            spec[k] *= gains[k]
            cprev[k] = gains[k] * gains[k] * power[k]
        self._gain_prev = gains
        self._frames += 1
        y = irfft(spec)
        tail = self._tail
        self._out.extend(tail[i] + y[i] * _WIN[i] for i in range(HOP))
        self._tail = [y[HOP + i] * _WIN[HOP + i] for i in range(HOP)]


def build(settings: NoiseSettings | None) -> NoiseSuppressor | None:
    """Bộ khử tạp cho luồng mới, hoặc ``None`` nếu tắt (chuỗi mic khỏi đụng tới khúc)."""
    return NoiseSuppressor(settings) if settings and settings.enabled else None
