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
import re
import struct
import time
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

MODE_AUTO, MODE_SERVER, MODE_DIRECT = "auto", "server", "direct"
DEFAULT_SERVER = "127.0.0.1:5037"

#: adbd của loa TỪ CHỐI ngay (A_CLSE trước A_OKAY) mọi dịch vụ ``shell:`` có lệnh bắt đầu bằng ``pm`` (đo 24/10/2026 trên loa
#: thật: ``pm``, ``pm path x``, ``pmx``, ``pminstall`` đều bị từ chối; `` pm``, ``/system/bin/pm``, ``sh -c "pm …"``, ``am …`` chạy được).
#: Đường adb-server không dính vì ``adb shell`` dùng dịch vụ ``shell,v2``. Nên mọi lệnh ``pm`` đi nối thẳng phải gọi bằng đường dẫn đầy đủ.
_PM_DAU_LENH = re.compile(r"^\s*pm(?=\s|$)")


def chuan_hoa_shell(lenh: str) -> str:
    """Đổi ``pm …`` thành ``/system/bin/pm …`` để adbd của loa không từ chối dịch vụ."""
    return _PM_DAU_LENH.sub("/system/bin/pm", lenh, count=1)
TIMEOUT_S = 5.0
#: Nối thẳng: giữ kết nối thêm ngần này giây sau luồng cuối cùng rồi mới nhả (adbd đôi khi im lặng với kết nối mở NGAY sau
#: khi đóng; giữ thêm cũng tránh nối đi nối lại khi hai lệnh đến sát nhau).
IDLE_S = 8.0
#: Chờ trước khi thử lại một lần nếu adbd không trả lời bắt tay.
THU_LAI_S = 1.5

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
        self._nha: asyncio.TimerHandle | None = None
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
        self.huy_nha()
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
        if not self.streams and self._nha is None and not self.chet:
            self._nha = asyncio.get_running_loop().call_later(IDLE_S, lambda: asyncio.get_running_loop().create_task(self.dong()))

    def huy_nha(self) -> None:
        """Có luồng mới: huỷ hẹn nhả kết nối."""
        if self._nha is not None:
            self._nha.cancel()
            self._nha = None

    async def dong(self) -> None:
        """Nhả kết nối nếu vẫn không còn luồng nào."""
        self._nha = None
        if self.streams or self.chet:
            return
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

    async def _server_lenh(self, lenh: str) -> str:
        """Lệnh ``host:`` của adb-server (connect/disconnect): trả thông điệp; thông điệp báo lỗi thì ``AdbError``."""
        sh, sp = _split_hostport(self.server, 5037)
        r, w = await asyncio.wait_for(asyncio.open_connection(sh, sp), TIMEOUT_S)
        try:
            await self._svc(r, w, lenh)
            msg = ""
            with contextlib.suppress(Exception):
                n = int(await asyncio.wait_for(r.readexactly(4), TIMEOUT_S), 16)
                msg = (await asyncio.wait_for(r.readexactly(n), TIMEOUT_S)).decode("utf-8", "replace")
            if any(x in msg for x in ("cannot", "failed", "unable")):
                raise AdbError(msg)
            return msg
        finally:
            w.close()

    async def _server_connect(self) -> None:
        await self._server_lenh(f"host:connect:{self.serial}")

    async def _server_ngat_noi_lai(self) -> None:
        """Server giữ kết nối HỎNG tới loa (``device offline``/``not found``) thì nó chiếm luôn chỗ duy nhất của adbd:
        ngắt rồi nối lại để lấy kết nối mới."""
        with contextlib.suppress(Exception):
            await self._server_lenh(f"host:disconnect:{self.serial}")
        await self._server_connect()

    async def _mo_qua_server(self, service: str) -> AdbStream:
        sh, sp = _split_hostport(self.server, 5037)
        r, w = await asyncio.wait_for(asyncio.open_connection(sh, sp), TIMEOUT_S)
        try:
            await self._svc(r, w, f"host:transport:{self.serial}")
            await self._svc(r, w, service)
            return _RawStream(r, w)
        except BaseException:
            w.close()
            raise

    async def _open_server(self, service: str) -> AdbStream:
        try:
            return await self._mo_qua_server(service)
        except AdbError:
            await self._server_ngat_noi_lai()                # loa chưa nối / đang offline: nối lại rồi thử đúng một lần nữa
            return await self._mo_qua_server(service)

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
            try:
                tr = await self._transport()
            except AdbError as exc:
                if "không trả lời" not in str(exc):
                    raise
                await asyncio.sleep(THU_LAI_S)             # adbd còn đang dọn kết nối vừa đóng: thử lại đúng một lần
                tr = await self._transport()
            return await tr.mo(service)

    # ── giao diện chung ────────────────────────────────────────

    async def open(self, service: str) -> AdbStream:
        """Mở luồng tới ``service`` (``shell:<lệnh>`` / ``sync:``). Tự chọn đường theo ``mode``."""
        loi: list[str] = []
        if service.startswith("shell:"):
            service = "shell:" + chuan_hoa_shell(service[len("shell:"):])
        if self.mode in (MODE_AUTO, MODE_SERVER) and self.server:
            try:
                s = await self._open_server(service)
                self.duong = MODE_SERVER
                return s
            except (OSError, asyncio.TimeoutError, AdbError, asyncio.IncompleteReadError) as exc:
                if self.mode == MODE_SERVER or not isinstance(exc, ConnectionRefusedError):
                    loi.append(f"adb-server: {exc or type(exc).__name__}")   # auto mà adb-server không tồn tại: không đáng nhắc, nối thẳng là đường chính
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

    async def shell(self, cmd: str, *, limit: int = 1 << 20, timeout: float = 30) -> str:
        s = await self.open(f"shell:{cmd}")
        try:
            return (await asyncio.wait_for(s.read_all(limit), timeout)).decode("utf-8", "replace")
        finally:
            await s.close()

    async def reboot(self) -> None:
        """Khởi động lại loa (dịch vụ ``reboot:`` của adbd). Loa đóng kết nối ngay nên lỗi đọc sau lệnh là bình thường."""
        s = await self.open("reboot:")
        try:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(s.read_all(), 5)
        finally:
            with contextlib.suppress(Exception):
                await s.close()
        self.duong = None

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
