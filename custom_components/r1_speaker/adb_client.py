"""Máy khách ADB tối giản, thuần asyncio, không thêm thư viện. Hai đường tới cùng một loa:

* ``server``: qua ``adb-server`` (mặc định ``127.0.0.1:5037``): ``host:transport:<serial>`` rồi dịch vụ.
* ``direct``: NỐI THẲNG tới adbd của loa (cổng 5555): bắt tay CNXN rồi mở luồng. Loa R1 có ``ro.adb.secure=0``
  nên không đòi khoá; nếu adbd đòi xác thực (AUTH) thì báo lỗi rõ chứ không đoán.

``mode="auto"`` (mặc định): thử adb-server trước (nhanh, dùng chung khoá), không có thì nối thẳng. Mỗi luồng dùng một
kết nối TCP riêng nên không phải ghép kênh. Không chạy lệnh tuỳ ý: nơi gọi chỉ gửi đường dẫn script cố định.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
import time
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

MODE_AUTO, MODE_SERVER, MODE_DIRECT = "auto", "server", "direct"
DEFAULT_SERVER = "127.0.0.1:5037"
TIMEOUT_S = 5.0

A_CNXN, A_AUTH, A_OPEN, A_OKAY, A_CLSE, A_WRTE = (
    0x4E584E43, 0x48545541, 0x4E45504F, 0x59414B4F, 0x45534C43, 0x45545257)
_VERSION = 0x01000000
_MAXDATA = 4096
_HDR = struct.Struct("<6I")


class AdbError(Exception):
    """Không nói chuyện được với loa qua ADB (chưa nối, bị từ chối, hết giờ...)."""


def _split_hostport(value: str, default_port: int) -> tuple[str, int]:
    value = value.strip()
    host, sep, port = value.rpartition(":")
    if sep and port.isdigit():
        return host or "127.0.0.1", int(port)
    return value, default_port


class AdbStream:
    """Luồng byte hai chiều tới một dịch vụ ADB (``shell:...`` hoặc ``sync:``)."""

    async def read(self, n: int = 4096) -> bytes:  # pragma: no cover - giao diện
        raise NotImplementedError

    async def write(self, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def read_exactly(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = await self.read(n - len(buf))
            if not chunk:
                raise AdbError("luồng ADB đóng giữa chừng")
            buf += chunk
        return buf

    async def read_all(self, limit: int = 1 << 20) -> bytes:
        out = b""
        while len(out) < limit:
            chunk = await self.read(4096)
            if not chunk:
                break
            out += chunk
        return out


class _RawStream(AdbStream):
    """Đường adb-server: sau hai lần OKAY, ổ cắm là ống byte thô."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._r, self._w = reader, writer

    async def read(self, n: int = 4096) -> bytes:
        return await self._r.read(n)

    async def write(self, data: bytes) -> None:
        self._w.write(data)
        await asyncio.wait_for(self._w.drain(), TIMEOUT_S)

    async def close(self) -> None:
        self._w.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._w.wait_closed(), 2)


class _DirectTransport:
    """MỘT kết nối TCP tới adbd, ghép nhiều luồng (adbd của loa chỉ phục vụ một kết nối TCP tại một thời điểm: kết nối
    thứ hai không được trả lời). Nhả kết nối ngay khi không còn luồng nào để client ADB khác nối được."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, maxdata: int) -> None:
        self._r, self._w = reader, writer
        self.maxdata = max(256, min(maxdata, 65536))
        self.streams: dict[int, "_MuxStream"] = {}
        self._next = 0
        self.chet = False
        self._task = asyncio.get_running_loop().create_task(self._doc())
        self.khi_het_luong = None

    async def gui(self, cmd: int, a0: int, a1: int, data: bytes = b"") -> None:
        if self.chet:
            raise AdbError("kết nối ADB đã đóng")
        self._w.write(_HDR.pack(cmd, a0, a1, len(data), sum(data) & 0xFFFFFFFF, cmd ^ 0xFFFFFFFF) + data)
        await asyncio.wait_for(self._w.drain(), TIMEOUT_S)

    async def _doc(self) -> None:
        try:
            while True:
                cmd, a0, a1, ln, _c, _m = _HDR.unpack(await self._r.readexactly(_HDR.size))
                data = await self._r.readexactly(ln) if ln else b""
                st = self.streams.get(a1)
                if st is None:
                    continue
                if cmd == A_OKAY:
                    st.remote = a0
                    st.san_sang.set()
                    st.ack.set()
                elif cmd == A_WRTE:
                    st.remote = a0
                    st.q.put_nowait(data)
                    await self.gui(A_OKAY, st.local, st.remote)
                elif cmd == A_CLSE:
                    st.dong_tu_xa()
        except (asyncio.IncompleteReadError, ConnectionError, OSError, AdbError):
            pass
        finally:
            self.chet = True
            for st in list(self.streams.values()):
                st.dong_tu_xa()
            self._w.close()

    async def mo(self, service: str) -> "_MuxStream":
        self._next += 1
        st = _MuxStream(self, self._next)
        self.streams[st.local] = st
        try:
            await self.gui(A_OPEN, st.local, 0, service.encode() + b"\x00")
            await asyncio.wait_for(st.san_sang.wait(), TIMEOUT_S)
        except BaseException:
            self.streams.pop(st.local, None)
            raise
        if st.da_dong and st.remote == 0:
            self.streams.pop(st.local, None)
            raise AdbError(f"loa từ chối dịch vụ {service.split(':')[0]}")
        return st

    async def bo_luong(self, st: "_MuxStream") -> None:
        self.streams.pop(st.local, None)
        if not self.streams:
            self.chet = True
            self._task.cancel()
            self._w.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._w.wait_closed(), 2)
            if self.khi_het_luong is not None:
                self.khi_het_luong()


class _MuxStream(AdbStream):
    def __init__(self, tr: _DirectTransport, local: int) -> None:
        self._tr, self.local, self.remote = tr, local, 0
        self.q: asyncio.Queue[bytes] = asyncio.Queue()
        self.san_sang, self.ack = asyncio.Event(), asyncio.Event()
        self.da_dong = False
        self._buf = b""

    def dong_tu_xa(self) -> None:
        self.da_dong = True
        self.san_sang.set()
        self.ack.set()
        self.q.put_nowait(b"")

    async def read(self, n: int = 4096) -> bytes:
        if not self._buf:
            if self.da_dong and self.q.empty():
                return b""
            self._buf = await self.q.get()
            if not self._buf:
                self.q.put_nowait(b"")                 # giữ dấu hết luồng cho lần đọc sau
                return b""
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    async def write(self, data: bytes) -> None:
        for i in range(0, len(data), self._tr.maxdata):
            if self.da_dong:
                raise AdbError("loa đóng luồng ADB")
            self.ack.clear()
            await self._tr.gui(A_WRTE, self.local, self.remote, data[i:i + self._tr.maxdata])
            await asyncio.wait_for(self.ack.wait(), TIMEOUT_S)

    async def close(self) -> None:
        if not self.da_dong and not self._tr.chet:
            with contextlib.suppress(Exception):
                await self._tr.gui(A_CLSE, self.local, self.remote)
        self.da_dong = True
        await self._tr.bo_luong(self)


@dataclass
class AdbDevice:
    """Một loa: địa chỉ adbd (``host:port``), địa chỉ adb-server (hoặc rỗng) và chế độ."""

    host: str
    port: int = 5555
    server: str = DEFAULT_SERVER
    mode: str = MODE_AUTO
    #: Đường vừa dùng thành công: ``server`` / ``direct`` / None (chưa dùng hoặc vừa lỗi).
    duong: str | None = None
    _tr: "_DirectTransport | None" = field(default=None, init=False, repr=False, compare=False)
    _khoa: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False, compare=False)

    @property
    def serial(self) -> str:
        return f"{self.host}:{self.port}"

    # ── adb-server ────────────────────────────────────────────

    @staticmethod
    async def _svc(r: asyncio.StreamReader, w: asyncio.StreamWriter, cmd: str) -> None:
        b = cmd.encode()
        w.write(b"%04x" % len(b) + b)
        await asyncio.wait_for(w.drain(), TIMEOUT_S)
        resp = await asyncio.wait_for(r.readexactly(4), TIMEOUT_S)
        if resp == b"OKAY":
            return
        if resp == b"FAIL":
            n = int(await asyncio.wait_for(r.readexactly(4), TIMEOUT_S), 16)
            raise AdbError((await asyncio.wait_for(r.readexactly(n), TIMEOUT_S)).decode("utf-8", "replace"))
        raise AdbError(f"adb-server trả lời lạ: {resp!r}")

    async def _server_connect(self) -> None:
        sh, sp = _split_hostport(self.server, 5037)
        r, w = await asyncio.wait_for(asyncio.open_connection(sh, sp), TIMEOUT_S)
        try:
            await self._svc(r, w, f"host:connect:{self.serial}")
            with contextlib.suppress(Exception):          # thông điệp "connected to ..." / "already connected"
                n = int(await asyncio.wait_for(r.readexactly(4), TIMEOUT_S), 16)
                msg = (await asyncio.wait_for(r.readexactly(n), TIMEOUT_S)).decode("utf-8", "replace")
                if "cannot" in msg or "failed" in msg or "unable" in msg:
                    raise AdbError(msg)
        finally:
            w.close()

    async def _open_server(self, service: str) -> AdbStream:
        sh, sp = _split_hostport(self.server, 5037)
        for lan in (1, 2):
            r, w = await asyncio.wait_for(asyncio.open_connection(sh, sp), TIMEOUT_S)
            try:
                await self._svc(r, w, f"host:transport:{self.serial}")
                await self._svc(r, w, service)
                return _RawStream(r, w)
            except AdbError:
                w.close()
                if lan == 2:
                    raise
                await self._server_connect()              # loa chưa nối vào server: nối rồi thử lại một lần
            except BaseException:
                w.close()
                raise
        raise AdbError("không mở được luồng qua adb-server")   # pragma: no cover

    # ── nối thẳng ────────────────────────────────────────────

    async def _transport(self) -> _DirectTransport:
        if self._tr is not None and not self._tr.chet:
            return self._tr
        r, w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), TIMEOUT_S)
        try:
            w.write(_HDR.pack(A_CNXN, _VERSION, _MAXDATA, 7, sum(b"host::\x00"), A_CNXN ^ 0xFFFFFFFF) + b"host::\x00")
            await asyncio.wait_for(w.drain(), TIMEOUT_S)
            while True:
                cmd, _a0, a1, ln, _c, _m = _HDR.unpack(await asyncio.wait_for(r.readexactly(_HDR.size), TIMEOUT_S))
                if ln:
                    await asyncio.wait_for(r.readexactly(ln), TIMEOUT_S)
                if cmd == A_AUTH:
                    raise AdbError("loa đòi xác thực ADB (khoá RSA); chế độ nối thẳng chưa hỗ trợ")
                if cmd == A_CNXN:
                    break
        except asyncio.TimeoutError as exc:
            w.close()
            raise AdbError("adbd của loa không trả lời (đang bận phục vụ một client ADB khác?)") from exc
        except BaseException:
            w.close()
            raise
        tr = _DirectTransport(r, w, a1 or _MAXDATA)
        self._tr = tr
        return tr

    async def _open_direct(self, service: str) -> AdbStream:
        async with self._khoa:                            # một lần nối tại một thời điểm
            tr = await self._transport()
            return await tr.mo(service)

    # ── giao diện chung ────────────────────────────────────────

    async def open(self, service: str) -> AdbStream:
        """Mở luồng tới ``service`` (``shell:<lệnh>`` / ``sync:``). Tự chọn đường theo ``mode``."""
        loi: list[str] = []
        if self.mode in (MODE_AUTO, MODE_SERVER) and self.server:
            try:
                s = await self._open_server(service)
                self.duong = MODE_SERVER
                return s
            except (OSError, asyncio.TimeoutError, AdbError, asyncio.IncompleteReadError) as exc:
                loi.append(f"adb-server: {exc or type(exc).__name__}")
                if self.mode == MODE_SERVER:
                    self.duong = None
                    raise AdbError(loi[-1]) from exc
        try:
            s = await self._open_direct(service)
            self.duong = MODE_DIRECT
            return s
        except (OSError, asyncio.TimeoutError, AdbError, asyncio.IncompleteReadError) as exc:
            self.duong = None
            loi.append(f"nối thẳng: {exc or type(exc).__name__}")
            raise AdbError("; ".join(loi)) from exc

    async def shell(self, cmd: str, *, limit: int = 1 << 20) -> str:
        s = await self.open(f"shell:{cmd}")
        try:
            return (await asyncio.wait_for(s.read_all(limit), 30)).decode("utf-8", "replace")
        finally:
            await s.close()

    async def push(self, data: bytes, remote: str, mode: int = 0o755) -> None:
        """Đẩy tệp bằng giao thức sync (SEND / DATA / DONE)."""
        s = await self.open("sync:")
        try:
            path = f"{remote},{mode}".encode()
            await s.write(b"SEND" + struct.pack("<I", len(path)) + path)
            for i in range(0, len(data), 65536):
                chunk = data[i:i + 65536]
                await s.write(b"DATA" + struct.pack("<I", len(chunk)) + chunk)
            await s.write(b"DONE" + struct.pack("<I", int(time.time())))
            ket = await asyncio.wait_for(s.read_exactly(8), TIMEOUT_S)
            if ket[:4] != b"OKAY":
                n = struct.unpack("<I", ket[4:])[0]
                msg = (await asyncio.wait_for(s.read_exactly(n), TIMEOUT_S)).decode("utf-8", "replace") if n else ""
                raise AdbError(f"đẩy tệp thất bại: {msg or ket[:4]!r}")
        finally:
            await s.close()
