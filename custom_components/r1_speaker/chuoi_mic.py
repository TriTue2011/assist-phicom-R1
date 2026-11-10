"""Chuỗi xử lý mic sau ``amplify``: khử tạp → AGC → bộ hạn đỉnh → listener.

Mỗi luồng (mỗi lần nối mic) một ``MicChain`` mới nên nền tạp / mức tăng không dính từ lần nối
trước. Tầng nào tắt thì KHÔNG tồn tại; cả ba tắt (mặc định) thì ``process`` trả đúng đối tượng
bytes vào, không đụng tới khúc.
"""

from __future__ import annotations

from .agc import Agc, AgcSettings, Limiter, LimiterSettings, floats_to_pcm, pcm_to_floats
from . import xu_ly_nang_cao
from .noise_suppress import NoiseSettings, NoiseSuppressor


class MicChain:
    def __init__(self, noise: NoiseSettings | None = None, agc: AgcSettings | None = None,
                 limiter: LimiterSettings | None = None) -> None:
        self.noise = None
        if noise and noise.enabled:
            # Động cơ nâng cao (Speex NS có sẵn trong HA) chỉ khi thư viện có; không thì bộ Wiener như cũ (không bao giờ làm hỏng luồng mic).
            if noise.engine == "nang_cao" and xu_ly_nang_cao.co_san_khu_on():
                self.noise = xu_ly_nang_cao.SpeexMic(noise.strength_db)
            else:
                self.noise = NoiseSuppressor(noise)
        self.agc = Agc(agc) if agc and agc.enabled else None
        self.limiter = Limiter(limiter) if limiter and limiter.enabled else None

    @property
    def active(self) -> bool:
        return bool(self.noise or self.agc or self.limiter)

    def process(self, pcm: bytes) -> bytes:
        if not self.active:
            return pcm
        if self.noise:
            pcm = self.noise.process(pcm)
        if self.agc or self.limiter:
            xs = pcm_to_floats(pcm)
            if self.agc:
                xs = self.agc.run(xs)
            if self.limiter:
                xs = self.limiter.run(xs)
            pcm = floats_to_pcm(xs)
        return pcm
