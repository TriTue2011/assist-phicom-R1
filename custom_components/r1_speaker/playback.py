"""Kênh phát PCM từ HA về loa R1 (chiều HA → loa của bộ đàm).

HỢP ĐỒNG (đề xuất, xem docs/HOP-DONG-PHIA-LOA.md): loa chạy một dịch vụ TCP; HA là máy khách,
nối vào ``play_host:play_port``, ghi liên tục PCM16 mono 16 kHz little-endian (cùng định dạng
luồng mic, không tiêu đề, không khung), rồi đóng kết nối khi hết tiếng. Loa phát ra loa ngay
khi nhận byte và dừng khi kết nối đóng.

**PHÍA LOA CHƯA CÓ.** Chưa có dịch vụ nào trên loa nhận luồng này và chưa có đường đã chứng
minh để phát PCM thô ra loa R1 (TODO: chờ kết quả đo). Lớp này chỉ giữ đúng hợp đồng phía HA,
test bằng máy chủ TCP giả ở 127.0.0.1. ``play_port`` mặc định 0 = chưa có kênh.

Lỗi (không nối được, loa đóng giữa chừng, nghẽn quá lâu) KHÔNG làm sập ai: ``async_play``
ném ``R1PlayError``, trạng thái ``ok`` thành False cho tới lần phát thành công kế tiếp.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable

from .const import PLAY_RATE

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
#: Ghi một khúc mà loa không nhận (nghẽn) quá ngần này giây thì coi là hỏng.
WRITE_TIMEOUT = 5.0


class R1PlayError(Exception):
    """Phát về loa không được (chưa cấu hình, không nối được, loa đóng giữa chừng)."""


class R1Playback:
    def __init__(self, host: str, port: int, via=None) -> None:
        self.host = (host or "").strip()
        self.port = int(port or 0)
        #: đầu nhận mic (R1MicServer) nếu phát xuống loa qua chính kết nối APK; None = kênh TCP riêng
        self._via = via
        if via is not None:
            via.add_state_listener(self._notify_state)   # APK nối/đứt → «configured» đổi
        #: None = chưa thử lần nào; True/False = kết quả lần phát gần nhất.
        self.ok: bool | None = None
        self._warned = False
        self._on_state: list[Callable[[], None]] = []

    @property
    def configured(self) -> bool:
        if self.host and 0 < self.port < 65536:
            return True                     # kênh TCP riêng đã cấu hình
        return self._via is not None and bool(self._via.receiving)

    def add_state_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._on_state.append(cb)
        return lambda: self._on_state.remove(cb)

    def _set_ok(self, ok: bool) -> None:
        if ok == self.ok:
            return
        self.ok = ok
        self._notify_state()

    def _notify_state(self) -> None:
        for cb in list(self._on_state):
            try:
                cb()
            except Exception:  # noqa: BLE001 — người nghe hỏng không được phá luồng phát
                _LOGGER.exception("R1 playback: state listener failed")

    async def async_play(self, source: AsyncIterator[bytes]) -> float:
        """Nối vào loa, ghi mọi khúc từ ``source`` rồi đóng. Trả số giây tiếng đã gửi."""
        if not self.configured:
            raise R1PlayError("chưa cấu hình kênh phát về loa (play_port)")
        if not (self.host and 0 < self.port < 65536):
            return await self._play_via(source)   # không có kênh riêng: phát qua kết nối APK
        sent = 0
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT)
        except (OSError, TimeoutError) as exc:
            self._lost(f"không nối được: {exc!r}")
            raise R1PlayError(f"{self.host}:{self.port} không nối được: {exc!r}") from exc
        try:
            async for chunk in source:
                if reader.at_eof():
                    raise ConnectionResetError("loa đóng kênh phát")
                writer.write(chunk)
                await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)
                sent += len(chunk)
        except (OSError, TimeoutError) as exc:
            self._lost(f"đứt giữa chừng: {exc!r}")
            raise R1PlayError(f"kênh phát về loa đứt: {exc!r}") from exc
        finally:
            writer.close()
            with contextlib.suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), CONNECT_TIMEOUT)
        self._warned = False
        self._set_ok(True)
        return sent / (2 * PLAY_RATE)

    async def _play_via(self, source: AsyncIterator[bytes]) -> float:
        sent = 0
        try:
            async for chunk in source:
                await self._via.send_pcm(chunk)
                sent += len(chunk)
        except (OSError, TimeoutError, ConnectionError) as exc:
            self._lost(f"qua kết nối mic đứt: {exc!r}")
            raise R1PlayError(f"kênh phát qua APK đứt: {exc!r}") from exc
        self._warned = False
        self._set_ok(True)
        return sent / (2 * PLAY_RATE)

    def _lost(self, why: str) -> None:
        if not self._warned:
            self._warned = True
            _LOGGER.warning("R1 playback %s:%s lỗi (%s)", self.host, self.port, why)
        else:
            _LOGGER.debug("R1 playback %s:%s vẫn lỗi (%s)", self.host, self.port, why)
        self._set_ok(False)
