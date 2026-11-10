"""Xử lý âm thanh NÂNG CAO cho mic loa R1 — chỉ dùng thư viện MÀ HOME ASSISTANT ĐÃ CÓ SẴN (không cài thêm gì):

* khử tạp âm: ``pyspeex_noise`` (cùng bộ tăng cường tiếng của Assist);
* khử vọng: ``khu_vong_fdaf.KhuVongFdaf`` (miền tần số, numpy) có ước lượng độ trễ tự động.

KHÔNG dùng ``pywebrtc-audio`` (AEC3) trong HA: nó đăng ký cùng lớp ``AudioProcessor`` với ``pyspeex_noise`` nên nạp cái nọ làm cái kia lỗi
(«already registered») — có thể làm hỏng bộ tăng cường của Assist. AEC3 vẫn dùng được ở TIẾN TRÌNH RIÊNG (gateway Zalo/Telegram).

Thiếu thư viện thì ``co_san_*()`` là False và nơi dùng rơi về bộ có sẵn (Wiener / NLMS); không bao giờ làm hỏng luồng mic.
Khung Speex là 10 ms = 160 mẫu PCM16 mono 16 kHz; khúc vào dài bao nhiêu cũng được, đầu ra luôn bằng đầu vào (khúc đầu chèn câm một khung).
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

RATE = 16000
KHUNG = RATE // 100            # 160 mẫu = 10 ms
BYTE_KHUNG = KHUNG * 2


def _speex():
    try:
        import pyspeex_noise
    except ImportError:
        return None
    return pyspeex_noise


def co_san_khu_on() -> bool:
    return _speex() is not None


def co_san_khu_vong() -> bool:
    try:
        import numpy  # noqa: F401
    except ImportError:
        return False
    return True


class _Dem:
    """Cắt luồng byte PCM16 thành khung 160 mẫu; giữ phần dư; đầu ra bằng độ dài đầu vào."""

    def __init__(self) -> None:
        self._du = b""
        self._ra = b""
        self._tre = BYTE_KHUNG  # độ trễ cố định một khung: chèn câm đầu luồng

    def chay(self, pcm: bytes, xu_ly_khung) -> bytes:
        n = len(pcm) - (len(pcm) % 2)
        pcm = pcm[:n]
        buf = self._du + pcm
        k = len(buf) // BYTE_KHUNG * BYTE_KHUNG
        self._du = buf[k:]
        for i in range(0, k, BYTE_KHUNG):
            self._ra += xu_ly_khung(buf[i:i + BYTE_KHUNG])
        if self._tre:
            self._ra = bytes(self._tre) + self._ra
            self._tre = 0
        out, self._ra = self._ra[:n], self._ra[n:]
        if len(out) < n:                      # phòng hờ: không bao giờ trả ngắn hơn đầu vào
            out += bytes(n - len(out))
        return out


def muc_khu_on_db(strength_db: float) -> int:
    """Mức giảm tối đa (dB, dương) → tham số Speex: bị chặn 1–40 (0 là tắt, không dùng)."""
    return int(min(max(round(strength_db), 1), 40))


class SpeexMic:
    """Khử tạp (Speex NS của HA) cho luồng mic; giao diện ``process(pcm) -> bytes`` như ``NoiseSuppressor``."""

    def __init__(self, strength_db: float = 12.0) -> None:
        sp = _speex()
        if sp is None:
            raise RuntimeError("chưa có pyspeex_noise")
        self._ap = sp.AudioProcessor(0, -muc_khu_on_db(strength_db))     # (tự chỉnh mức = tắt, mức giảm ồn âm dB) — đúng cách HA gọi
        self._dem = _Dem()

    def _khung(self, b: bytes) -> bytes:
        return bytes(self._ap.Process10ms(b).audio)

    def process(self, pcm: bytes) -> bytes:
        return self._dem.chay(pcm, self._khung)
