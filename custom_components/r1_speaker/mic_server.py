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
import time
import contextlib
import hmac
import json
import logging
from collections.abc import Callable

from .const import MUSIC_LIGHT_RANGE
from .mic import R1Mic

_LOGGER = logging.getLogger(__name__)

#: Thời gian tối đa chờ một khúc PCM / khung điều khiển xuống APK được ghi xong.
WRITE_TIMEOUT_S = 2.0

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


#: Máy chủ đang giữ cổng, theo số cổng. Mục cấu hình bị xoá lúc đang «chưa nạp» thì HA không gọi dỡ tải, máy chủ cũ
#: (khoá cũ) vẫn giữ cổng và chặn mục thêm lại («address in use»): máy chủ mới đòi cổng thì máy chủ cũ phải nhả.
_DANG_GIU: dict[int, "R1MicServer"] = {}


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
        self._on_state: list[Callable[[], None]] = []
        #: Âm lượng NHẠC của loa (APK báo): ``(mức, tối đa)``; None = chưa biết / loa chưa nối / APK cũ không báo.
        self.am_luong: tuple[int, int] | None = None
        #: Gọi mỗi khi APK xác thực thành công (hello đúng khoá): dùng để đóng «cửa ghép khoá».
        self.khi_xac_thuc: Callable[[], None] | None = None
        #: Gọi khi loa (đúng IP) gửi hello nhưng SAI khoá: APK đã mất khoá, cần được ghép lại.
        self.khi_sai_khoa: Callable[[], None] | None = None

    @property
    def khoa(self) -> str:
        return self._key

    def dat_khoa(self, key: str) -> None:
        """Đổi khoá đang kiểm hello NGAY, không đóng cổng: phiên đang nối giữ nguyên, kết nối sau phải chào khoá mới."""
        self._key = key or ""

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
        cu = _DANG_GIU.get(self.port)
        if cu is not None and cu is not self:
            _LOGGER.warning("R1 mic server: cổng %s còn do máy chủ của mục cũ giữ — đóng nó trước", self.port)
            await cu.async_close()
        try:
            self._server = await asyncio.start_server(self._handle, "0.0.0.0", self.port)
            self.port = self._server.sockets[0].getsockname()[1]
            _DANG_GIU[self.port] = self
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

    def add_state_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Báo mỗi khi loa nối vào / đứt khỏi đầu nhận (thực thể phụ thuộc kết nối cập nhật theo)."""
        self._on_state.append(cb)
        return lambda: self._on_state.remove(cb)

    def _notify_state(self) -> None:
        for cb in list(self._on_state):
            try:
                cb()
            except Exception:  # noqa: BLE001 — người nghe hỏng không được giết vòng đọc
                _LOGGER.exception("R1 mic server: state listener failed")

    async def _gui_khung(self, payload: bytes) -> None:
        writer = self._writer
        if writer is None:
            raise ConnectionError("loa chưa nối vào đầu nhận mic")
        writer.write(_khung(payload))
        await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT_S)

    async def send_pcm(self, pcm: bytes) -> None:
        """Gửi một khúc PCM16 16 kHz mono xuống APK loa (cùng kết nối đang nhận mic)."""
        await self._gui_khung(pcm)

    async def gui_am_luong(self, muc: int) -> None:
        """Đặt âm lượng NHẠC của loa (0–``VOL_MAX``) qua APK (``AudioManager.setStreamVolume``). Hợp đồng khung với
        ``LenhDieuKhien.java``. APK trả lại ``am_luong_trang_thai`` với mức thật."""
        from .const import VOL_MAX, VOL_MIN
        if isinstance(muc, bool) or not isinstance(muc, int) or not VOL_MIN <= muc <= VOL_MAX:
            raise ValueError(f"âm lượng ngoài {VOL_MIN}–{VOL_MAX}: {muc!r}")
        await self._gui_khung(json.dumps({"type": "am_luong", "muc": muc}, separators=(",", ":")).encode())

    async def hoi_am_luong(self) -> None:
        """Hỏi APK mức âm lượng hiện tại; APK trả ``am_luong_trang_thai``."""
        await self._gui_khung(b'{"type":"am_hoi"}')

    async def set_music_light(self, ma: int, gia_tri: int) -> None:
        """Đặt đèn theo nhạc của firmware qua APK loa (mã/giá trị xem ``const.MUSIC_LIGHT_*``).
        APK chỉ nhận đúng định dạng khung này và kiểm khoảng giá trị lần nữa."""
        khoang = MUSIC_LIGHT_RANGE.get(ma)
        if khoang is None or isinstance(gia_tri, bool) or not khoang[0] <= gia_tri <= khoang[1]:
            raise ValueError(f"đèn nhạc: mã {ma} / giá trị {gia_tri} ngoài khoảng cho phép")
        # Thứ tự khoá và dạng tách gọn là hợp đồng với LenhDieuKhien.java (đọc bằng mẫu chặt).
        await self._gui_khung(json.dumps(
            {"type": "den_nhac", "ma": ma, "gia_tri": gia_tri}, separators=(",", ":")).encode())

    async def async_close(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()
        if self._server is not None:
            server, self._server = self._server, None
            if _DANG_GIU.get(self.port) is self:
                del _DANG_GIU[self.port]
            server.close()
            # Python ≥ 3.12: wait_closed chờ MỌI kết nối kết thúc; kết nối treo không được giữ cổng mãi.
            if hasattr(server, "close_clients"):
                server.close_clients()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(server.wait_closed(), 3)
        self._mic.set_inbound_closer(None)
        self._mic.note_listening(False)
        self._mic.note_inbound(False)
        self._notify_state()

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
                # APK thử nối lại đều đặn khi còn luồng cũ: ghi cảnh báo tối đa 5 phút một lần.
                bay_gio = time.monotonic()
                if bay_gio - getattr(self, "_bao_luong_hai", 0.0) >= 300.0:
                    self._bao_luong_hai = bay_gio
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
                if (data is not None and data.get("type") == "hello" and data.get("version") == 1
                        and self.khi_sai_khoa is not None):
                    self.khi_sai_khoa()
                return
            self._writer = writer
            self.am_luong = None
            if self.khi_xac_thuc is not None:
                self.khi_xac_thuc()
            self._mic.note_inbound(True)
            self._notify_state()
            _LOGGER.debug("R1 mic server: loa %s đã nối, bắt đầu nhận tiếng", ip)
            try:
                du = b""                            # byte lẻ cuối khung, dồn sang khung sau
                while True:
                    payload = await self._read_frame(reader)
                    if payload is None:
                        break                       # mất kết nối giữa chừng
                    ctrl = _la_khung_json(payload)
                    if ctrl is not None:            # khung điều khiển: KHÔNG bao giờ coi là tiếng
                        loai = ctrl.get("type")
                        if loai == "end":
                            break                   # loa báo kết thúc phiên
                        if loai == "am_luong_trang_thai":
                            muc, toi_da = ctrl.get("muc"), ctrl.get("toi_da")
                            if (isinstance(muc, int) and isinstance(toi_da, int) and not isinstance(muc, bool)
                                    and not isinstance(toi_da, bool) and 0 < toi_da <= 100 and 0 <= muc <= toi_da):
                                if (muc, toi_da) != self.am_luong:
                                    self.am_luong = (muc, toi_da)
                                    self._notify_state()
                            continue
                        continue                    # khung điều khiển khác: bỏ qua
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
                    self.am_luong = None
                self._mic.note_inbound(False)
                self._notify_state()
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
