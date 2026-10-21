"""Đầu NHẬN luồng mic của loa R1 (NV244): HA lắng nghe, APK trên loa là máy khách.

Đảo chiều so với ``mic.py`` (ở đó HA nối TỚI loa): APK NV243 chỉ làm client — loa kết nối
ra HA, không mở cổng nghe trong LAN. Lớp này mở một cổng TCP (``asyncio.start_server``,
0.0.0.0), chỉ nhận đúng IP loa đã cấu hình (``mic_host``) và đúng khoá (options
``mic_listen_key``, không mã cứng, không ghi vào log).

Giao thức (khớp APK NV243 — MỌI khung đều đóng khung thống nhất):

* khung = 4 byte độ dài big-endian + payload;
* khung đầu: payload JSON ``{"type": "hello", "version": 1, "key": "..."}``;
* khung giữa: payload PCM16 LE mono 16 kHz thô → đưa vào ĐÚNG chuỗi listener của
  ``R1Mic`` (``feed_inbound`` → ``add_chunk_listener``), không tạo đường mic thứ hai,
  để ``MicView`` và đàm thoại dùng chung;
* khung cuối: payload JSON ``{"type": "end"}``.

Một luồng nhận tại một thời điểm: luồng thứ hai bị đóng ngay kèm log cảnh báo. Mất kết
nối giữa chừng chỉ đóng phiên đó, máy chủ vẫn nghe tiếp cho lần nối lại. Lỗi ở đây
KHÔNG bao giờ làm sập HA: ``start`` nuốt lỗi bind và chỉ log.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging

from .mic import R1Mic

_LOGGER = logging.getLogger(__name__)

#: Chờ khung hello tối đa ngần này giây kể từ lúc nối.
HELLO_TIMEOUT = 10.0
#: Trần một khung: PCM của APK là khúc ngắn; trần này chỉ để chặn khung lỗi/phá đệm.
MAX_FRAME = 1 << 20

#: Trạng thái đầu nhận (sensor + thuộc tính): tắt (không nghe) / nghe (đang chờ loa) /
#: nhan (đang nhận tiếng từ loa).
SERVER_TAT, SERVER_NGHE, SERVER_NHAN = "tat", "nghe", "nhan"


def _khung(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


def _la_khung_json(payload: bytes) -> dict | None:
    """Payload là khung điều khiển JSON (hello/end) thì trả dict, không thì None (PCM)."""
    if not payload.startswith(b"{"):
        return None
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


class R1MicServer:
    """Máy chủ TCP nhận luồng mic từ APK loa. Vòng đời: ``start()`` khi setup tích hợp,
    ``async_close()`` khi unload."""

    def __init__(self, mic: R1Mic, port: int, key: str, speaker_ip: str) -> None:
        self._mic = mic
        self.port = int(port)
        self._key = key or ""
        self._speaker_ip = (speaker_ip or "").strip()
        self._server: asyncio.Server | None = None
        self._writer: asyncio.StreamWriter | None = None

    # ── Trạng thái ────────────────────────────────────────────────────────────

    @property
    def listening(self) -> bool:
        return self._server is not None

    @property
    def receiving(self) -> bool:
        """Đang có một phiên loa đã chào đúng khoá và đang gửi tiếng."""
        return self._writer is not None

    @property
    def state(self) -> str:
        if self._writer is not None:
            return SERVER_NHAN
        return SERVER_NGHE if self._server is not None else SERVER_TAT

    # ── Vòng đời ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Mở cổng nghe. Thiếu khoá / thiếu IP loa / bind lỗi → KHÔNG nghe, chỉ log
        (không ném ra ngoài: HA vẫn phải lên)."""
        if self._server is not None:
            return
        if not self._key:
            _LOGGER.warning("R1 mic server: chưa đặt khoá (mic_listen_key) — không mở cổng nghe")
            return
        if not self._speaker_ip:
            _LOGGER.warning("R1 mic server: chưa có IP loa (mic_host) — không mở cổng nghe")
            return
        if self.port < 0:
            _LOGGER.warning("R1 mic server: cổng nghe %s không hợp lệ — không mở", self.port)
            return
        try:
            self._server = await asyncio.start_server(self._handle, "0.0.0.0", self.port)
            self.port = self._server.sockets[0].getsockname()[1]
        except OSError as exc:
            _LOGGER.error("R1 mic server: mở cổng %s thất bại: %s", self.port, exc)
            self._server = None
            return
        self._mic.set_inbound_closer(self._ngat_phien)
        self._mic.note_listening(True)
        _LOGGER.info("R1 mic server: đang nghe cổng %s, chỉ nhận từ %s",
                     self.port, self._speaker_ip)

    def _ngat_phien(self) -> None:
        """Tắt mic: đóng ngay kết nối loa đang nhận (vòng đọc thấy EOF và dọn trạng thái)."""
        if self._writer is not None:
            self._writer.close()

    async def async_close(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._mic.set_inbound_closer(None)
        self._mic.note_listening(False)
        self._mic.note_inbound(False)

    # ── Một kết nối ───────────────────────────────────────────────────────────

    async def _handle(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        ip = peer[0] if peer else ""
        try:
            if ip != self._speaker_ip:
                _LOGGER.warning("R1 mic server: từ chối kết nối từ IP lạ %s (chỉ nhận %s)",
                                ip, self._speaker_ip)
                return
            if self._writer is not None:
                _LOGGER.warning("R1 mic server: từ chối luồng thứ hai từ %s — đang có "
                                "một luồng mic đang nhận", ip)
                return
            if self._mic.muted:
                _LOGGER.warning("R1 mic server: mic đang tắt — từ chối kết nối từ %s", ip)
                return
            hello = await asyncio.wait_for(self._read_frame(reader), HELLO_TIMEOUT)
            data = _la_khung_json(hello) if hello is not None else None
            if (data is None or data.get("type") != "hello" or data.get("version") != 1
                    or not hmac.compare_digest(str(data.get("key") or ""), self._key)):
                # KHÔNG log khoá (kể cả khoá sai bên kia gửi).
                _LOGGER.warning("R1 mic server: khung hello sai (khoá/phiên bản) từ %s — đóng",
                                ip)
                return
            self._writer = writer
            self._mic.note_inbound(True)
            _LOGGER.debug("R1 mic server: loa %s đã nối, bắt đầu nhận tiếng", ip)
            try:
                du = b""                            # byte lẻ cuối khung, dồn sang khung sau
                while True:
                    payload = await self._read_frame(reader)
                    if payload is None:
                        break                       # mất kết nối giữa chừng
                    ctrl = _la_khung_json(payload)
                    if ctrl is not None and ctrl.get("type") == "end":
                        break                       # loa báo kết thúc phiên
                    # PCM16 phải đủ cặp byte: khung rỗng bỏ qua, byte lẻ chuyển sang khung sau
                    # để mẫu không bị lệch một byte về sau.
                    payload = du + payload
                    chan = len(payload) // 2 * 2
                    du = payload[chan:]
                    if chan:
                        self._mic.feed_inbound(payload[:chan])
            finally:
                if self._writer is writer:
                    self._writer = None
                self._mic.note_inbound(False)
                _LOGGER.debug("R1 mic server: phiên từ %s đã đóng", ip)
        except (TimeoutError, asyncio.IncompleteReadError):
            _LOGGER.debug("R1 mic server: kết nối từ %s đứt/chậm khung", ip)
        except (ConnectionError, OSError) as exc:
            _LOGGER.debug("R1 mic server: lỗi kết nối từ %s: %s", ip, exc)
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()

    @staticmethod
    async def _read_frame(reader: asyncio.StreamReader) -> bytes | None:
        """Đọc một khung 4-byte BE + payload; EOF/giữa khung → None."""
        try:
            header = await reader.readexactly(4)
            size = int.from_bytes(header, "big")
            if size > MAX_FRAME:
                _LOGGER.warning("R1 mic server: khung quá lớn (%s byte) — đóng", size)
                return None
            return await reader.readexactly(size)
        except asyncio.IncompleteReadError:
            return None
