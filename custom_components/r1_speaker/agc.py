"""AGC và bộ hạn đỉnh cho luồng mic của loa R1 (PCM16 mono 16 kHz). Thuần Python, không numpy.

Thứ tự chuỗi mic (xem ``chuoi_mic.py``): amplify (dB cố định) → khử tạp → AGC → bộ hạn đỉnh →
listener. Mỗi tầng có API ``run(list[float]) -> list[float]`` (giữ số thực giữa các tầng để
không cắt cứng ở giữa chuỗi) và ``process(bytes) -> bytes`` (tầng đứng một mình).

**AGC** đưa mức RMS (dBFS, tính theo RMS) về ``target_db``:

* Mức đo bằng công suất trung bình trượt (hằng số 30 ms) trên các khối 128 mẫu (8 ms).
* Mức tăng (dB) bám theo mức mong muốn bằng hàm mũ: ``attack_s`` khi phải GIẢM tăng (tiếng
  to lên), ``release_s`` khi được TĂNG (tiếng nhỏ đi). Giảm nhanh – tăng chậm để một tiếng
  động mạnh không bị kéo vọt, còn tiếng nhỏ không bị bơm lên từng nhịp.
* Mức tăng nằm trong [-24 dB, ``max_gain_db``].
* Dưới ``silence_db`` (khoảng nền): KHÔNG tăng thêm; mức tăng thả dần về 0 dB (hằng số 1 s)
  để nền không bị khuếch đại bằng mức tăng còn dư từ lúc có tiếng.
* Mức tăng nội suy tuyến tính trong từng khối (không tạo bước nhảy).

**Bộ hạn đỉnh** (``Limiter``) chặn đỉnh ở ``ceiling`` × biên độ tối đa mà KHÔNG cắt cứng:
nhìn trước 32 mẫu (2 ms; độ trễ cố định bằng đó), hệ số giảm = trung bình trượt (cùng độ rộng)
của cực tiểu trượt các hệ số cần thiết, nên đường cong hệ số trơn và luôn ≤ hệ số cần cho
từng mẫu → không mẫu nào vượt trần (chứng minh trong ghi chú ``run``). Thả hệ số về 1 tuyến
tính trong ``release_s``.

Tất cả số mặc định CHƯA ĐO trên mic loa R1 (xem ``const.py``).
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

from .const import (DEFAULT_AGC_ENABLE, DEFAULT_AGC_MAX_GAIN_DB, DEFAULT_AGC_SILENCE_DB,
                    DEFAULT_AGC_TARGET_DB, DEFAULT_LIMITER_CEILING, DEFAULT_LIMITER_ENABLE,
                    MIC_RATE)

FULL = 32768.0
BLOCK = 128
_LEVEL_TAU = 0.03
_SILENCE_TAU = 1.0
_MAX_CUT_DB = 24.0
LOOKAHEAD = 32


def pcm_to_floats(pcm: bytes) -> list[float]:
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    return list(map(float, a))


def floats_to_pcm(xs: list[float]) -> bytes:
    """Làm tròn + chặn ở ±32767 (lưới an toàn cuối chuỗi; bộ hạn đỉnh đã giữ dưới trần)."""
    return array.array("h", (-32767 if v < -32767 else 32767 if v > 32767 else int(round(v))
                             for v in xs)).tobytes()


@dataclass(frozen=True)
class AgcSettings:
    enabled: bool = DEFAULT_AGC_ENABLE
    target_db: float = DEFAULT_AGC_TARGET_DB
    max_gain_db: float = DEFAULT_AGC_MAX_GAIN_DB
    silence_db: float = DEFAULT_AGC_SILENCE_DB
    #: Hằng số thời gian giảm mức tăng (s) — tiếng to lên.
    attack_s: float = 0.05
    #: Hằng số thời gian tăng mức tăng (s) — tiếng nhỏ đi.
    release_s: float = 1.0


@dataclass(frozen=True)
class LimiterSettings:
    enabled: bool = DEFAULT_LIMITER_ENABLE
    #: Trần đỉnh theo tỉ lệ biên độ tối đa (0 < ceiling ≤ 1).
    ceiling: float = DEFAULT_LIMITER_CEILING
    #: Thời gian thả hệ số về 1 (s).
    release_s: float = 0.05


class Agc:
    def __init__(self, settings: AgcSettings | None = None) -> None:
        self.settings = settings or AgcSettings()
        self.reset()

    def reset(self) -> None:
        self._gain_db = 0.0
        self._level: float | None = None        # công suất trung bình trượt (đơn vị mẫu²)

    @property
    def gain_db(self) -> float:
        return self._gain_db

    def process(self, pcm: bytes) -> bytes:
        """Tắt thì trả NGUYÊN khúc vào. Bật thì ra cùng độ dài (bỏ byte lẻ), chặn ±32767."""
        if not self.settings.enabled:
            return pcm
        return floats_to_pcm(self.run(pcm_to_floats(pcm)))

    def run(self, xs: list[float]) -> list[float]:
        st = self.settings
        out: list[float] = []
        for b in range(0, len(xs), BLOCK):
            blk = xs[b:b + BLOCK]
            dt = len(blk) / MIC_RATE
            power = sum(v * v for v in blk) / len(blk)
            if self._level is None:
                self._level = power
            else:
                a = math.exp(-dt / _LEVEL_TAU)
                self._level = a * self._level + (1 - a) * power
            level_db = 10 * math.log10(self._level / (FULL * FULL) + 1e-12)
            if level_db < st.silence_db:
                want, tau = 0.0, _SILENCE_TAU
            else:
                want = min(st.max_gain_db, max(-_MAX_CUT_DB, st.target_db - level_db))
                tau = st.attack_s if want < self._gain_db else st.release_s
            g0 = 10 ** (self._gain_db / 20)
            self._gain_db += (want - self._gain_db) * (1 - math.exp(-dt / max(tau, 1e-3)))
            g1 = 10 ** (self._gain_db / 20)
            step = (g1 - g0) / len(blk)
            out.extend(v * (g0 + step * (i + 1)) for i, v in enumerate(blk))
        return out


class Limiter:
    """Hạn đỉnh nhìn trước. Độ trễ cố định ``LOOKAHEAD`` mẫu; đầu ra dài bằng đầu vào."""

    latency_samples = LOOKAHEAD

    def __init__(self, settings: LimiterSettings | None = None) -> None:
        self.settings = settings or LimiterSettings()
        # Trần NGUYÊN (làm tròn xuống): số thực ≤ trần nguyên thì làm tròn ra int16 vẫn ≤ trần.
        self._cap = float(int(min(1.0, max(0.01, self.settings.ceiling)) * (FULL - 1)))
        self._step = 1.0 / max(1.0, self.settings.release_s * MIC_RATE)
        self.reset()

    def reset(self) -> None:
        self._pending = [0.0] * LOOKAHEAD
        self._hist = [1.0] * (2 * LOOKAHEAD)
        self._gain = 1.0

    @property
    def cap(self) -> float:
        """Trần đỉnh tuyệt đối theo đơn vị mẫu."""
        return self._cap

    def process(self, pcm: bytes) -> bytes:
        if not self.settings.enabled:
            return pcm
        return floats_to_pcm(self.run(pcm_to_floats(pcm)))

    def run(self, xs: list[float]) -> list[float]:
        """Mẫu ra thứ m = (mẫu vào m-LOOKAHEAD) × g_m. Với r_j = min(1, cap/|x_j|), S[t] = min
        của r trong cửa sổ L+1 mẫu bắt đầu ở t, g_m = trung bình S[m..m+L]. Mỗi S[t] với
        t ∈ [m, m+L] có cửa sổ chứa mẫu j nên S[t] ≤ r_j, suy ra g_m ≤ r_j, tức |x_j|·g_m ≤ cap.
        Bước thả ``min(g, g_trước + step)`` chỉ làm g nhỏ thêm, nên bất đẳng thức vẫn đúng."""
        n = len(xs)
        if n == 0:
            return []
        L, cap = LOOKAHEAD, self._cap
        r_new = [1.0 if -cap <= v <= cap else cap / abs(v) for v in xs]
        big_r = self._hist + r_new
        big_x = self._pending + xs
        self._pending = big_x[n:]
        self._hist = big_r[-2 * L:]
        if self._gain >= 1.0 and min(big_r) >= 1.0:
            return big_x[:n]                      # đường nhanh: không có gì phải hạn
        s = [min(big_r[t:t + L + 1]) for t in range(n + L)]
        total = sum(s[:L + 1])
        out: list[float] = []
        g_prev, step = self._gain, self._step
        for m in range(n):
            g = total / (L + 1)
            up = g_prev + step
            g_prev = g if g < up else up
            out.append(big_x[m] * g_prev)
            if m + L + 1 < n + L:
                total += s[m + L + 1] - s[m]
        self._gain = g_prev
        return out
