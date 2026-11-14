"""Chặn VỌNG TRỄ còn sót sau bộ khử vọng của phiên song công (cùng thuật toán với EchoGuard của app Zalo-calling).

Vì sao cần: đo thật trên loa R1 (cuộc gọi 14/11/2026, bản ghi tiếng gửi xuống loa + tiếng mic nhận về) cho thấy đường loa → mic có độ trễ ~470 ms và KHÔNG cố định
(dạng sóng lệch 480–745 ms giữa các đoạn 0,5 s; đường bao năng lượng bám tiếng loa ở 450–550 ms). Bộ khử vọng thích nghi trễ cố định (NLMS 300 ms) hoặc bộ lọc ngắn
(FDAF phủ 128 ms) không bám được nên mic vẫn đầy vọng; ``duck`` cũ dùng ngưỡng tuyệt đối, không bù trễ nên cũng không bắt được.

Cách làm: nhớ mức RMS từng khung 20 ms của tiếng HA bơm xuống loa. Một khúc mic bị coi là VỌNG (bỏ) khi loa có tiếng (RMS ≥ ngưỡng) trong cửa sổ trễ
[bây giờ - cao, bây giờ - thấp] mà RMS khúc mic < ``ty_le`` × đỉnh RMS loa trong cửa sổ đó. Mic to hơn mức vọng có thể có ⇒ người nhà nói chen ⇒ cho qua.
Chạy lại bản ghi thật: chặn ~86% năng lượng mic khi chỉ có vọng; tiếng người nói ở loa vẫn qua ~95%.
"""
from __future__ import annotations

import math
import time
from array import array
from collections import deque

RATE = 16000
KHUNG_MAU = 320                   # 20 ms
KHUNG_S = KHUNG_MAU / RATE


def rms(pcm: bytes) -> float:
    n = len(pcm) // 2
    if not n:
        return 0.0
    a = array("h")
    a.frombytes(pcm[:n * 2])
    return math.sqrt(sum(v * v for v in a) / n)


class ChanVongTre:
    """``note_far`` cho MỌI khúc HA bơm xuống loa; ``chan(mic)`` hỏi khúc mic (đã qua bộ khử vọng) có phải vọng không."""

    def __init__(self, thap_s: float = 0.3, cao_s: float = 0.75, ty_le: float = 2.0, nguong: float = 180.0,
                 clock=time.monotonic) -> None:
        self.thap_s, self.cao_s, self.ty_le, self.nguong, self._clock = thap_s, cao_s, ty_le, nguong, clock
        self._lich_su: deque[tuple[float, float]] = deque()      # (giờ khung bắt đầu phát, RMS khung loa)
        self._het = 0.0                                          # giờ kết thúc khúc loa trước (khúc dồn cục nối tiếp, không đặt theo giờ tới)
        self.da_chan = 0
        self.da_qua = 0                                          # trong cửa sổ trễ nhưng mic to hơn mức vọng: người nhà nói chen

    @property
    def bat(self) -> bool:
        return self.cao_s > self.thap_s > 0

    def note_far(self, pcm: bytes) -> None:
        if not self.bat or not pcm:
            return
        bay_gio = self._clock()
        t = max(bay_gio, self._het)
        for i in range(0, len(pcm), KHUNG_MAU * 2):               # khung 20 ms; khúc cuối lẻ (≥ 5 ms) cũng tính theo đúng độ dài của nó
            seg = pcm[i:i + KHUNG_MAU * 2]
            if len(seg) < 160:
                break
            self._lich_su.append((t, rms(seg)))
            t += len(seg) / 2 / RATE
        self._het = t
        while self._lich_su and bay_gio - self._lich_su[0][0] > self.cao_s + 0.5:
            self._lich_su.popleft()

    def dinh_loa(self, bay_gio: float | None = None) -> float:
        bay_gio = self._clock() if bay_gio is None else bay_gio
        dinh = 0.0
        for t, r in self._lich_su:
            if bay_gio - self.cao_s <= t <= bay_gio - self.thap_s and r > dinh:
                dinh = r
        return dinh

    def chan(self, mic_pcm: bytes) -> bool:
        if not self.bat:
            return False
        dinh = self.dinh_loa()
        if dinh < self.nguong:
            return False
        if rms(mic_pcm) < self.ty_le * dinh:
            self.da_chan += 1
            return True
        self.da_qua += 1
        return False

    def mo_ta(self) -> dict:
        return {"cua_so_ms": [round(self.thap_s * 1000), round(self.cao_s * 1000)], "ty_le": self.ty_le, "da_chan": self.da_chan, "da_qua": self.da_qua}
