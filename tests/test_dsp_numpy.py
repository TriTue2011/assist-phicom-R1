"""Bản numpy của chuỗi DSP mic phải cho cùng kết quả với bản Python thuần (bản chuẩn) và nhanh hơn."""

import array
import math
import random
import time

import numpy as np
import pytest

from custom_components.r1_speaker import agc, mic, noise_suppress
from custom_components.r1_speaker.agc import (Agc, AgcSettings, Limiter, LimiterSettings,
                                             array_to_pcm, floats_to_pcm, pcm_to_array, pcm_to_floats)
from custom_components.r1_speaker.noise_suppress import (NoiseSettings, NoiseSuppressor,
                                                         NoiseSuppressorNp)

RATE = 16000


def _speechish(seconds=3.0, seed=1):
    """Nhiễu nền + các đoạn «tiếng» to nhỏ khác nhau, có đoạn to sát trần để bộ hạn đỉnh làm việc."""
    rnd = random.Random(seed)
    n = int(RATE * seconds)
    out = []
    for i in range(n):
        t = i / RATE
        env = 0.0
        if 0.4 < t % 1.0 < 0.8:
            env = 1.0
        if 2.0 < t < 2.3:
            env = 4.0
        v = rnd.gauss(0, 120) + env * 4000 * math.sin(2 * math.pi * 220 * t) * math.sin(2 * math.pi * 3 * t)
        out.append(max(-32768, min(32767, int(v))))
    return array.array("h", out).tobytes()


def _chunks(pcm, size=2048):
    return [pcm[i:i + size] for i in range(0, len(pcm), size)]


def _close(a: bytes, b: bytes, atol=2):
    x = np.frombuffer(a, "<i2").astype(int)
    y = np.frombuffer(b, "<i2").astype(int)
    assert x.shape == y.shape
    assert int(np.abs(x - y).max()) <= atol


def test_amplify_numpy_giong_ban_python():
    pcm = _speechish(1.0)
    for db in (3.0, 12.0, 30.0):                      # 30 dB làm nhiều mẫu bị chặn trần
        f = 10 ** (db / 20)
        a = array.array("h"); a.frombytes(pcm)
        ref = array.array("h", (max(-32768, min(32767, int(s * f))) for s in a)).tobytes()
        assert mic.amplify(pcm, db) == ref
    assert mic.amplify(pcm + b"\x01", 6.0) == mic.amplify(pcm, 6.0)       # byte lẻ bị bỏ
    assert mic.amplify(pcm, 0.0) is pcm


def test_agc_numpy_giong_ban_python():
    st = AgcSettings(enabled=True)
    a_py, a_np = Agc(st), Agc(st)
    for blk in _chunks(_speechish(3.0)):
        ref = floats_to_pcm(a_py.run(pcm_to_floats(blk)))
        got = array_to_pcm(a_np.run(pcm_to_array(blk)))
        _close(ref, got, atol=1)
    assert abs(a_py.gain_db - a_np.gain_db) < 1e-9


def test_bo_han_dinh_numpy_giong_ban_python_ca_khi_phai_han():
    st = LimiterSettings(enabled=True, ceiling=0.3)           # trần thấp: luôn phải hạn
    l_py, l_np = Limiter(st), Limiter(st)
    for blk in _chunks(_speechish(3.0)):
        ref = floats_to_pcm(l_py.run(pcm_to_floats(blk)))
        got = array_to_pcm(l_np.run(pcm_to_array(blk)))
        _close(ref, got, atol=1)
        assert np.abs(np.frombuffer(got, "<i2").astype(int)).max() <= l_np.cap
    assert abs(l_py._gain - l_np._gain) < 1e-9


def test_bo_han_dinh_numpy_duong_nhanh_khi_khong_phai_han():
    l_np = Limiter(LimiterSettings(enabled=True, ceiling=1.0))
    x = np.full(1024, 1000.0)
    out = l_np.run(x)
    assert out.shape == x.shape


def test_khu_ton_numpy_giong_ban_python():
    st = NoiseSettings(enabled=True)
    py, npv = NoiseSuppressor(st), NoiseSuppressorNp(st)
    pcm = _speechish(3.0)
    ref = b"".join(py.process(c) for c in _chunks(pcm))
    got = b"".join(npv.process(c) for c in _chunks(pcm))
    _close(ref, got, atol=3)
    assert isinstance(noise_suppress.build(st), NoiseSuppressorNp)
    assert noise_suppress.build(NoiseSettings(enabled=False)) is None


@pytest.mark.parametrize("n", [1, 2, 3, 700, 1025])
def test_khu_ton_numpy_giu_do_dai_voi_khuc_le(n):
    s = NoiseSuppressorNp(NoiseSettings(enabled=True))
    pcm = _speechish(0.2)[:n * 2]
    assert len(s.process(pcm)) == len(pcm)
    assert s.process(b"") == b""
    off = NoiseSuppressorNp(NoiseSettings(enabled=False))
    assert off.process(pcm) is pcm


def test_chuoi_mic_ba_tang_numpy_giong_ban_python(monkeypatch):
    from custom_components.r1_speaker import chuoi_mic
    cfg = dict(noise=NoiseSettings(enabled=True), agc=AgcSettings(enabled=True),
               limiter=LimiterSettings(enabled=True))
    pcm = _speechish(2.0)
    fast = chuoi_mic.MicChain(**cfg)
    got = b"".join(fast.process(c) for c in _chunks(pcm))
    monkeypatch.setattr(chuoi_mic, "np", None)                       # ép bản thuần Python
    monkeypatch.setattr(noise_suppress, "np", None)
    slow = chuoi_mic.MicChain(**cfg)
    assert isinstance(slow.noise, NoiseSuppressor) and not isinstance(slow.noise, NoiseSuppressorNp)
    ref = b"".join(slow.process(c) for c in _chunks(pcm))
    _close(ref, got, atol=8)


def test_numpy_nhanh_hon_ban_python_it_nhat_5_lan():
    pcm = _speechish(2.0)
    chunks = _chunks(pcm)

    def run(make):
        c = make()
        t = time.perf_counter()
        for blk in chunks:
            c.process(blk)
        return time.perf_counter() - t
    t_py = run(lambda: NoiseSuppressor(NoiseSettings(enabled=True)))
    t_np = run(lambda: NoiseSuppressorNp(NoiseSettings(enabled=True)))
    assert t_np * 5 < t_py, (t_py, t_np)
