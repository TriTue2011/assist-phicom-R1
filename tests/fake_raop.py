"""Loa AirPlay 1 (RAOP) giả ở 127.0.0.1: máy chủ RTSP/TCP + ba cổng UDP (dữ liệu, điều khiển, timing). Viết theo đặc tả RAOP, ĐỘC LẬP với
``custom_components/r1_speaker/airplay.py`` (không dùng lại hàm dựng/đọc gói của nó) nên test không thành vòng tròn tự khẳng định.

Ghi lại mọi yêu cầu RTSP (kèm giờ nhận), mọi gói UDP, và cho test chủ động gửi yêu cầu gửi lại / hỏi timing tới bộ gửi."""

from __future__ import annotations

import asyncio
import struct
import time


class _Udp(asyncio.DatagramProtocol):
    def __init__(self, ten, ghi):
        self.ten, self.ghi, self.tp = ten, ghi, None

    def connection_made(self, tp):
        self.tp = tp

    def datagram_received(self, data, addr):
        self.ghi.append((time.monotonic(), data, addr))


class FakeRaop:
    def __init__(self, *, do_tre=2205, tra_ma=None, dong_sau_record=False):
        self.port = 0
        self.do_tre = do_tre                      # Audio-Latency (khung)
        self.tra_ma = tra_ma or {}                # {"ANNOUNCE": 453, ...}: trả mã lỗi cho phương thức đó
        self.dong_sau_record = dong_sau_record    # đóng kết nối RTSP ngay sau RECORD (kiểm bắt mất kết nối)
        self.yeu_cau: list[tuple[float, str, str, dict, bytes]] = []
        self.audio: list[tuple[float, bytes, tuple]] = []
        self.ctrl: list[tuple[float, bytes, tuple]] = []
        self.timing: list[tuple[float, bytes, tuple]] = []
        self._server = None
        self._udp = {}
        self.cong_nguoi_gui_ctrl = None           # control_port của bộ gửi (từ SETUP)
        self.cong_nguoi_gui_timing = None
        self.dia_chi_ctrl_nguoi_gui = None
        self._khach_dang_mo: set = set()

    async def start(self, cong_tcp: int = 0):
        loop = asyncio.get_running_loop()
        for ten, ds in (("data", self.audio), ("ctrl", self.ctrl), ("timing", self.timing)):
            tp, _ = await loop.create_datagram_endpoint(lambda t=ten, d=ds: _Udp(t, d), local_addr=("127.0.0.1", 0))
            self._udp[ten] = tp
        self._server = await asyncio.start_server(self._khach, "127.0.0.1", cong_tcp)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            for w in list(self._khach_dang_mo):               # test hỏng giữa chừng có thể để lại kết nối: đóng hẳn, đừng chờ mãi
                w.close()
            await asyncio.wait_for(self._server.wait_closed(), 2)
        for tp in self._udp.values():
            tp.close()

    def cong(self, ten):
        return self._udp[ten].get_extra_info("sockname")[1]

    def phuong_thuc(self):
        return [r[1] for r in self.yeu_cau]

    # ── RTSP ─────────────────────────────────────────────────────

    async def _khach(self, reader, writer):
        self._khach_dang_mo.add(writer)
        try:
            while True:
                dong = await reader.readline()
                if not dong:
                    return
                pt, url, _ = dong.decode().split(" ", 2)
                dau = {}
                while True:
                    d = await reader.readline()
                    if d in (b"\r\n", b""):
                        break
                    k, _, v = d.decode().partition(":")
                    dau[k.strip().lower()] = v.strip()
                than = await reader.readexactly(int(dau["content-length"])) if "content-length" in dau else b""
                self.yeu_cau.append((time.monotonic(), pt, url, dau, than))
                ma = self.tra_ma.get(pt, 200)
                them = {}
                if pt == "SETUP" and ma == 200:
                    tr = dict(p.split("=", 1) for p in dau["transport"].split(";") if "=" in p)
                    self.cong_nguoi_gui_ctrl, self.cong_nguoi_gui_timing = int(tr["control_port"]), int(tr["timing_port"])
                    them = {"Transport": f"RTP/AVP/UDP;unicast;mode=record;server_port={self.cong('data')};control_port={self.cong('ctrl')};"
                                         f"timing_port={self.cong('timing')}", "Session": "1"}
                if pt == "RECORD" and ma == 200:
                    them = {"Audio-Latency": str(self.do_tre)}
                tl = f"RTSP/1.0 {ma} {'OK' if ma == 200 else 'Lỗi'}\r\nCSeq: {dau.get('cseq', '0')}\r\nServer: FakeRaop\r\n"
                tl += "".join(f"{k}: {v}\r\n" for k, v in them.items()) + "\r\n"
                writer.write(tl.encode())
                await writer.drain()
                if (pt == "RECORD" and self.dong_sau_record) or pt == "TEARDOWN":
                    return
        except (ConnectionError, asyncio.IncompleteReadError):
            return
        finally:
            self._khach_dang_mo.discard(writer)
            writer.close()

    # ── chủ động gửi tới bộ gửi ──────────────────────────────────

    def gui_yeu_cau_gui_lai(self, seq_dau: int, so_goi: int):
        """Yêu cầu gửi lại kiểu 0x55|0x80 từ cổng điều khiển của loa tới cổng điều khiển của bộ gửi."""
        self._udp["ctrl"].sendto(struct.pack(">BBHHH", 0x80, 0xD5, 1, seq_dau, so_goi), ("127.0.0.1", self.cong_nguoi_gui_ctrl))

    def gui_hoi_timing(self, gio_gui: bytes = b"\x01\x02\x03\x04\x05\x06\x07\x08"):
        """Yêu cầu timing kiểu 0x52|0x80, 32 byte: tiêu đề 8, ref 8, nhận 8, GỬI 8 (gio_gui)."""
        goi = struct.pack(">BBH4x", 0x80, 0xD2, 7) + b"\x00" * 16 + gio_gui
        self._udp["timing"].sendto(goi, ("127.0.0.1", self.cong_nguoi_gui_timing))
        return gio_gui
