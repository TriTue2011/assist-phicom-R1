"""Hợp đồng đường âm thanh giữa HA và loa R1 — GIAO DIỆN TRỪU TƯỢNG, không gắn với phần cứng.

Đường mic thật trên loa (thiết bị thu nào, tiến trình nào giữ mic, chương trình nào đẩy
tiếng ra) **chưa lấy được** nên mã phía HA KHÔNG đoán nó. Toàn bộ phần đàm thoại
(``dam_thoai.R1Talk``, vệ tinh Assist, bộ đàm) chỉ nói chuyện với hai giao diện dưới đây;
chỗ cắm thật sau này chỉ cần thoả hai giao diện, không sửa phần còn lại.

Khung tiếng (cả hai chiều): **PCM 16-bit mono 16 kHz little-endian**, không tiêu đề, không
đóng khung; độ dài khúc tuỳ ý nhưng là số chẵn byte (``MIC_CHUNK`` là cỡ đọc mặc định).

* ``PcmSource`` — loa → HA (mic). Nhận khung PCM qua ``add_chunk_listener``; trạng thái qua
  ``connected`` / ``available`` / ``muted`` / ``holding``; ``want()`` xin luồng chạy (loa
  chỉ cần gửi khi có người xin — đó là chỗ «không gửi gì cho tới khi trigger»); ``hold()``
  bỏ tiếng (nửa công).
* ``PcmSink`` — HA → loa. ``async_play`` nhận một dòng khung PCM, gửi hết rồi trả số giây.

Hai bản cài hiện có: ``mic.R1Mic`` (máy khách TCP) và ``playback.R1Playback`` (máy khách TCP),
đều theo ``docs/HOP-DONG-PHIA-LOA.md``. Test dùng bản trong bộ nhớ.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Protocol, runtime_checkable

from .const import MIC_CHUNK, MIC_RATE

FRAME_FORMAT = "pcm_s16le"
FRAME_RATE = MIC_RATE
FRAME_CHANNELS = 1
#: Khúc lớn hơn ngần này byte bị coi là sai hợp đồng (chống bơm tràn bộ nhớ).
MAX_FRAME_BYTES = MIC_CHUNK * 16


class FrameError(ValueError):
    """Khung PCM sai hợp đồng (rỗng, lẻ byte, quá lớn)."""


def check_frame(frame: bytes) -> bytes:
    """Trả lại ``frame`` nếu đúng hợp đồng, ngược lại ném ``FrameError``."""
    if not frame:
        raise FrameError("khung PCM rỗng")
    if len(frame) % 2:
        raise FrameError(f"khung PCM lẻ byte ({len(frame)}): PCM16 cần số chẵn")
    if len(frame) > MAX_FRAME_BYTES:
        raise FrameError(f"khung PCM quá lớn ({len(frame)} > {MAX_FRAME_BYTES} byte)")
    return frame


@runtime_checkable
class PcmSource(Protocol):
    """Nguồn tiếng từ loa (mic)."""

    gain_db: float

    @property
    def configured(self) -> bool: ...
    @property
    def available(self) -> bool: ...
    @property
    def muted(self) -> bool: ...
    @property
    def connected(self) -> bool: ...
    @property
    def holding(self) -> bool: ...

    def add_chunk_listener(self, cb: Callable[[bytes], None]) -> Callable[[], None]: ...
    def add_state_listener(self, cb: Callable[[], None]) -> Callable[[], None]: ...
    def add_link_listener(self, cb: Callable[[], None]) -> Callable[[], None]: ...
    def want(self) -> Callable[[], None]: ...
    def hold(self) -> Callable[[], None]: ...


@runtime_checkable
class PcmSink(Protocol):
    """Đích tiếng tới loa (phát PCM)."""

    @property
    def configured(self) -> bool: ...

    def add_state_listener(self, cb: Callable[[], None]) -> Callable[[], None]: ...
    async def async_play(self, source: AsyncIterator[bytes]) -> float: ...
