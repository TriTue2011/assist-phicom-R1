"""Bộ gửi AirPlay 1 (RAOP) RIÊNG của tích hợp: không dùng ``apple_tv``/``pyatv``, không thêm thư viện Python nào.

Chủ máy 29/10/2026: «Tích hợp riêng vào custom, không phụ thuộc bên khác để kiểm soát dễ hơn». Loa R1 báo (mDNS ``_raop._tcp``) ``cn=0,1`` (PCM, ALAC),
``et=0,1`` (không mã hoá hoặc RSA), ``tp=UDP``, nên ta gửi **PCM 16 bit 44,1 kHz 2 kênh KHÔNG nén, KHÔNG mã hoá** (SDP ``L16/44100/2``).

Giao thức (đặc tả không chính thức của RAOP + mã ``libraop`` MIT làm đối chiếu; đã chạy thử với loa giả cục bộ, xem ``tests/fake_raop.py``):

* RTSP/TCP: ``OPTIONS`` → ``ANNOUNCE`` (SDP) → ``SETUP`` (``Transport`` nêu cổng ``control_port``/``timing_port`` của ta; loa trả ``server_port``, ``control_port``,
  ``timing_port``) → ``RECORD`` (``RTP-Info: seq;rtptime``; loa trả ``Audio-Latency`` tính bằng KHUNG) → ``SET_PARAMETER volume`` → ``FLUSH`` (tạm dừng) → ``TEARDOWN``.
* RTP/UDP tới ``server_port``: gói 352 khung (1408 byte PCM đã đổi sang big-endian), kiểu 0x60, gói ĐẦU sau RECORD/FLUSH đặt bit marker (0xE0).
* Kênh điều khiển (UDP): ta gửi gói đồng bộ kiểu 0xD4 mỗi giây (20 byte: dấu thời gian RTP trừ độ trễ, NTP, dấu thời gian RTP hiện tại); loa gửi yêu cầu gửi lại kiểu
  0xD5 (8 byte), ta trả kiểu 0xD6 kèm nguyên gói RTP cũ.
* Kênh timing (UDP): loa hỏi kiểu 0xD2 (32 byte), ta trả kiểu 0xD3 (tham chiếu = giờ gửi của yêu cầu, giờ nhận, giờ gửi).

Gửi theo thời gian thật (mỗi gói đúng khe 8 ms), sớm hơn khe ``DAN_DAU`` giây để chịu trễ của vòng lặp; loa đệm ``Audio-Latency`` (mặc định 2 giây) rồi mới phát. Tạm dừng
= ``FLUSH`` (loa bỏ phần đệm ngay) + giữ lại phần CHƯA KỊP NGHE trong lịch sử để phát lại khi tiếp tục, nên tiếp tục đúng chỗ đã dừng. Hết bài thì chờ loa phát nốt phần đệm rồi mới ``TEARDOWN``
(đóng sớm sẽ cụt ~2 giây cuối).

Nguồn tiếng do bên gọi đưa vào (``tai_pcm``: iterator bất đồng bộ PCM16 LE 44,1 kHz 2 kênh, độ dài khúc tuỳ ý): bộ giải mã (ffmpeg) nằm ngoài tệp này nên test tiêm được."""

from __future__ import annotations

import array
import asyncio
import contextlib
import logging
import random
import shutil
import struct
import sys
import time
from collections import deque
from collections.abc import AsyncIterator, Callable

_LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 44100
BYTE_MAU = 4                                    # 2 kênh × 16 bit
KHUNG_MOI_GOI = 352
BYTE_MOI_GOI = KHUNG_MOI_GOI * BYTE_MAU         # 1408
GOI_S = KHUNG_MOI_GOI / SAMPLE_RATE             # ~7,98 ms
DO_TRE_MAC_DINH = 2 * SAMPLE_RATE               # khung; dùng khi loa không báo Audio-Latency
DO_TRE_TOI_DA = 5 * SAMPLE_RATE                 # loa báo quá lớn thì cắt (tránh lịch sử phình)
DAN_DAU = 0.25                                  # gửi sớm hơn khe thời gian thật ngần này giây
DONG_BO_S = 1.0                                 # chu kỳ gói đồng bộ
GIU_KET_NOI_S = 20.0                            # OPTIONS giữ kết nối RTSP
CHO_RTSP_S = 5.0                                # chờ nối TCP / một phản hồi RTSP
DUONG_MAC_DINH_PORT = 5012                      # cổng RAOP loa R1 báo qua mDNS (đo 28/10/2026)
NTP_LECH = 2208988800                           # giây từ 1900 tới 1970
DEM_GUI_LAI = 512                               # số gói giữ để trả lời yêu cầu gửi lại

TRANG_THAI = ("ket_noi", "phat", "tam_dung", "xong")


class LoiAirPlay(Exception):
    """Không nối/không phát được qua AirPlay (loa từ chối, mất kết nối, bộ giải mã hỏng)."""


class LoiKhongNoi(LoiAirPlay):
    """Chưa mở được kết nối TCP tới cổng RAOP của loa (loa vừa bật AirPlay có thể cần vài trăm mili giây): đáng thử lại."""


# ── Đóng gói (hàm thuần, test trực tiếp) ─────────────────────────────────────

def ap_he_so(pcm_le: bytes, he_so: float) -> bytes:
    """Nhân PCM16 LE với ``he_so`` (0..1 giảm; >1 tăng, bị cắt ở ±32767). 1.0 trả đúng đối tượng vào: không tốn gì."""
    if he_so == 1.0:
        return pcm_le
    a = array.array("h")
    a.frombytes(pcm_le)
    toi, toi_thieu = 32767, -32768
    return array.array("h", [toi_thieu if v < toi_thieu else toi if v > toi else v for v in (int(x * he_so) for x in a)]).tobytes()


def goi_am_thanh(seq: int, ts: int, ssrc: int, pcm_le: bytes, dau: bool, he_so: float = 1.0) -> bytes:
    """Gói RTP: 12 byte tiêu đề + PCM big-endian. ``dau``: gói đầu sau RECORD/FLUSH (bit marker). ``he_so``: âm lượng MEDIA phần mềm
    (độc lập với âm lượng loa và với tin báo — xem ``settings.am_luong_media``)."""
    a = array.array("h")
    a.frombytes(ap_he_so(pcm_le, he_so))
    if sys.byteorder == "little":
        a.byteswap()
    return struct.pack(">BBHII", 0x80, 0x60 | (0x80 if dau else 0), seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc & 0xFFFFFFFF) + a.tobytes()


def ntp_tu(thoi_gian_unix: float) -> tuple[int, int]:
    giay = int(thoi_gian_unix)
    return (giay + NTP_LECH) & 0xFFFFFFFF, int((thoi_gian_unix - giay) * (1 << 32)) & 0xFFFFFFFF


def goi_dong_bo(ts_hien_tai: int, do_tre: int, thoi_gian_unix: float, dau: bool) -> bytes:
    """Gói đồng bộ 20 byte: [0x80|0x10 nếu đầu][0xD4][seq=7][ts-trễ][NTP giây][NTP phân số][ts]."""
    giay, frac = ntp_tu(thoi_gian_unix)
    return struct.pack(">BBHIIII", 0x80 | (0x10 if dau else 0), 0xD4, 7, (ts_hien_tai - do_tre) & 0xFFFFFFFF, giay, frac, ts_hien_tai & 0xFFFFFFFF)


def tra_loi_timing(yeu_cau: bytes, thoi_gian_unix: float) -> bytes | None:
    """Loa hỏi kiểu 0xD2 (32 byte); trả kiểu 0xD3: tham chiếu = giờ gửi của yêu cầu, rồi giờ nhận, giờ gửi (cùng một giá trị)."""
    if len(yeu_cau) < 32 or (yeu_cau[1] & 0x7F) != 0x52:
        return None
    giay, frac = ntp_tu(thoi_gian_unix)
    now = struct.pack(">II", giay, frac)
    return struct.pack(">BBH4x", 0x80, 0xD3, 7) + yeu_cau[24:32] + now + now


def doc_yeu_cau_gui_lai(goi: bytes) -> tuple[int, int] | None:
    """Yêu cầu gửi lại kiểu 0xD5: [4 byte tiêu đề][seq đầu: 2][số gói: 2]."""
    if len(goi) < 8 or (goi[1] & 0x7F) != 0x55:
        return None
    return struct.unpack(">HH", goi[4:8])


def goi_gui_lai(goi_rtp: bytes) -> bytes:
    return struct.pack(">BBH", 0x80, 0xD6, 1) + goi_rtp


def tu_am_luong(muc: float) -> float:
    """0..1 → dB: 0 là tắt tiếng (-144), còn lại -30..0 (đúng thang RAOP)."""
    muc = min(max(float(muc), 0.0), 1.0)
    return -144.0 if muc <= 0 else round(-30.0 + 30.0 * muc, 6)


# ── RTSP tối giản ────────────────────────────────────────────────────────────

class _Rtsp:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._r, self._w = reader, writer
        self._cseq = 0
        self._khoa = asyncio.Lock()
        self.phien: str | None = None

    async def yeu_cau(self, phuong_thuc: str, url: str, dau: dict[str, str] | None = None, than: bytes = b"") -> tuple[int, dict[str, str], bytes]:
        async with self._khoa:
            self._cseq += 1
            d = {"CSeq": str(self._cseq), "User-Agent": "AirPlay/1.0 r1_speaker", "Client-Instance": "52314E4F5253", "DACP-ID": "52314E4F5253",
                 "Active-Remote": "1986535575", **(dau or {})}
            if self.phien and "Session" not in d:
                d["Session"] = self.phien
            if than:
                d["Content-Length"] = str(len(than))
            msg = f"{phuong_thuc} {url} RTSP/1.0\r\n" + "".join(f"{k}: {v}\r\n" for k, v in d.items()) + "\r\n"
            self._w.write(msg.encode("ascii") + than)
            await asyncio.wait_for(self._w.drain(), CHO_RTSP_S)
            dong_dau = await asyncio.wait_for(self._r.readline(), CHO_RTSP_S)
            if not dong_dau:
                raise LoiAirPlay("loa đóng kết nối RTSP")
            try:
                ma = int(dong_dau.split()[1])
            except (IndexError, ValueError) as exc:
                raise LoiAirPlay(f"phản hồi RTSP lạ: {dong_dau[:40]!r}") from exc
            dau_tl: dict[str, str] = {}
            while True:
                dong = await asyncio.wait_for(self._r.readline(), CHO_RTSP_S)
                if dong in (b"\r\n", b"\n", b""):
                    break
                k, _, v = dong.decode("latin-1").partition(":")
                dau_tl[k.strip().lower()] = v.strip()
            do_dai = int(dau_tl.get("content-length", "0") or 0)
            than_tl = await asyncio.wait_for(self._r.readexactly(do_dai), CHO_RTSP_S) if 0 < do_dai <= 65536 else b""
            return ma, dau_tl, than_tl

    def dong(self) -> None:
        with contextlib.suppress(Exception):
            self._w.close()


class _Giao(asyncio.DatagramProtocol):
    def __init__(self, khi_nhan: Callable[[bytes, tuple], None] | None = None) -> None:
        self.khi_nhan, self.tp = khi_nhan, None

    def connection_made(self, transport) -> None:
        self.tp = transport

    def datagram_received(self, data: bytes, addr) -> None:
        if self.khi_nhan is not None:
            self.khi_nhan(data, addr)


# ── Phiên phát ───────────────────────────────────────────────────────────────

class PhienAirPlay:
    """Một lượt phát tới một loa. ``chay()`` chạy trọn: mở → phát → chờ phát nốt phần đệm → TEARDOWN; huỷ tác vụ là dừng (vẫn TEARDOWN).

    ``da_bat_dau`` được đặt khi gói âm thanh đầu tiên đã gửi đi (sau bắt tay RTSP và khi bộ giải mã đã ra byte đầu); ném ``LoiAirPlay`` trước lúc đó là «không bắt đầu được»."""

    def __init__(self, host: str, port: int, tai_pcm: Callable[[], AsyncIterator[bytes]], *, tren_doi: Callable[[str], None] | None = None,
                 he_so: Callable[[], float] | None = None) -> None:
        self.host, self.port = host, int(port)
        self._he_so = he_so            # đọc MỖI gói: đổi âm lượng media có hiệu lực ngay, không cần mở lại phiên
        self._tai_pcm, self._tren_doi = tai_pcm, tren_doi
        self.trang_thai = "ket_noi"
        self.da_bat_dau = asyncio.Event()
        self.do_tre_khung = DO_TRE_MAC_DINH
        self._seq0 = random.getrandbits(16)  # nosec B311 — số thứ tự/định danh RTP theo đặc tả, không phải bí mật
        self._ts0 = random.getrandbits(32)  # nosec B311 — số thứ tự/định danh RTP theo đặc tả, không phải bí mật
        self._ssrc = random.getrandbits(32)  # nosec B311 — số thứ tự/định danh RTP theo đặc tả, không phải bí mật
        self._n = 0                              # chỉ số gói vận chuyển đã gửi
        self._neo_t = 0.0                        # mốc (đồng hồ đơn điệu) khớp với gói số ``_neo_n``
        self._neo_n = 0
        self._dau = True                         # gói kế tiếp là gói đầu (marker + đồng bộ đầu)
        self._lich_su: deque[tuple[float, bytes]] = deque()   # (giờ gửi, PCM) các gói gửi trong khoảng độ trễ
        self._dem: dict[int, bytes] = {}         # seq → gói RTP, để gửi lại
        self._chay_duoc = asyncio.Event()
        self._chay_duoc.set()
        self._ev_tam_dung = asyncio.Event()      # đặt khi đang tạm dừng: đánh thức các vòng chờ
        self._lai: deque[bytes] = deque()        # PCM cần phát lại sau khi tiếp tục
        self._vt_goc = 0.0                       # giây đã nghe tính tới lần tạm dừng gần nhất
        self._nghe_t0 = 0.0                      # mốc đồng hồ đơn điệu mà tiếng đầu BẮT ĐẦU được nghe
        self._am_luong: float | None = None
        self._rtsp: _Rtsp | None = None
        self._url = ""
        self._ctrl: _Giao | None = None
        self._timing: _Giao | None = None
        self._data: _Giao | None = None
        self._dich_ctrl: tuple[str, int] | None = None
        self._dich_data: tuple[str, int] | None = None
        self._nen: list[asyncio.Task] = []
        self._so_goi_gui = 0
        self._so_gui_lai = 0

    # ── trạng thái ───────────────────────────────────────────────

    def _dat(self, tt: str) -> None:
        if tt != self.trang_thai:
            self.trang_thai = tt
            if self._tren_doi is not None:
                try:
                    self._tren_doi(tt)
                except Exception as exc:  # noqa: BLE001 — bên nghe hỏng không được phá luồng phát
                    _LOGGER.warning("airplay: bên nghe trạng thái lỗi (%s)", type(exc).__name__)

    @property
    def vi_tri(self) -> float:
        """Giây ĐÃ NGHE (không tính phần còn nằm trong bộ đệm của loa)."""
        if self.trang_thai == "phat":
            return self._vt_goc + max(0.0, time.monotonic() - self._nghe_t0)
        return self._vt_goc

    @property
    def thong_ke(self) -> dict[str, int]:
        return {"goi_da_gui": self._so_goi_gui, "goi_gui_lai": self._so_gui_lai}

    # ── chạy ─────────────────────────────────────────────────────

    async def chay(self) -> str:
        phat = None
        try:
            await self._mo()
            phat = asyncio.get_running_loop().create_task(self._phat(), name="r1 airplay phat")
            xong, _ = await asyncio.wait({phat, *self._nen}, return_when=asyncio.FIRST_COMPLETED)
            for t in xong:
                t.result()                          # tác vụ nền hoặc luồng phát hỏng → ném LoiAirPlay lên bên gọi
            return "finished"
        finally:
            if phat is not None and not phat.done():
                phat.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await phat
            await asyncio.shield(self._dong())

    async def _mo(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CHO_RTSP_S)
        except (OSError, TimeoutError) as exc:
            raise LoiKhongNoi(f"không nối được AirPlay {self.host}:{self.port}: {exc!r}") from exc
        self._rtsp = _Rtsp(reader, writer)
        local = writer.get_extra_info("sockname")[0]
        sid = random.getrandbits(32)  # nosec B311 — số thứ tự/định danh RTP theo đặc tả, không phải bí mật
        self._url = f"rtsp://{local}/{sid}"
        try:
            ma, _, _ = await self._rtsp.yeu_cau("OPTIONS", "*")
            self._kiem(ma, "OPTIONS")
            sdp = (f"v=0\r\no=iTunes {sid} 0 IN IP4 {local}\r\ns=iTunes\r\nc=IN IP4 {self.host}\r\nt=0 0\r\n"
                   "m=audio 0 RTP/AVP 96\r\na=rtpmap:96 L16/44100/2\r\n").encode("ascii")
            ma, _, _ = await self._rtsp.yeu_cau("ANNOUNCE", self._url, {"Content-Type": "application/sdp"}, sdp)
            self._kiem(ma, "ANNOUNCE")
            loop = asyncio.get_running_loop()
            # Ba cổng UDP chỉ nghe trên địa chỉ cục bộ đang nói chuyện với loa (không mở ra mọi giao diện mạng).
            self._ctrl = _Giao(self._khi_nhan_ctrl)
            await loop.create_datagram_endpoint(lambda: self._ctrl, local_addr=(local, 0))
            self._timing = _Giao(self._khi_nhan_timing)
            await loop.create_datagram_endpoint(lambda: self._timing, local_addr=(local, 0))
            self._data = _Giao()
            await loop.create_datagram_endpoint(lambda: self._data, local_addr=(local, 0))
            cp, tp = self._ctrl.tp.get_extra_info("sockname")[1], self._timing.tp.get_extra_info("sockname")[1]
            ma, dau, _ = await self._rtsp.yeu_cau(
                "SETUP", self._url, {"Transport": f"RTP/AVP/UDP;unicast;interleaved=0-1;mode=record;control_port={cp};timing_port={tp}"})
            self._kiem(ma, "SETUP")
            cong = dict(p.split("=", 1) for p in dau.get("transport", "").split(";") if "=" in p)
            try:
                self._dich_data = (self.host, int(cong["server_port"]))
                self._dich_ctrl = (self.host, int(cong["control_port"]))
            except (KeyError, ValueError) as exc:
                raise LoiAirPlay(f"SETUP không trả cổng: {dau.get('transport')!r}") from exc
            self._rtsp.phien = dau.get("session") or "1"
            ma, dau, _ = await self._rtsp.yeu_cau("RECORD", self._url, {"Range": "npt=0-", "RTP-Info": f"seq={self._seq0};rtptime={self._ts0}"})
            self._kiem(ma, "RECORD")
            with contextlib.suppress(ValueError):
                self.do_tre_khung = min(max(int(dau.get("audio-latency", "")), 0), DO_TRE_TOI_DA) or DO_TRE_MAC_DINH
            if self._am_luong is not None:
                await self._gui_am_luong()
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as exc:
            raise LoiAirPlay(f"lỗi bắt tay AirPlay: {exc!r}") from exc
        self._nen = [asyncio.get_running_loop().create_task(self._vong_dong_bo(), name="r1 airplay sync"),
                     asyncio.get_running_loop().create_task(self._vong_giu_ket_noi(), name="r1 airplay keepalive")]

    @staticmethod
    def _kiem(ma: int, buoc: str) -> None:
        if ma != 200:
            raise LoiAirPlay(f"loa từ chối {buoc}: RTSP {ma}")

    # ── gửi âm thanh ─────────────────────────────────────────────

    def _do_tre_s(self) -> float:
        return self.do_tre_khung / SAMPLE_RATE

    def _neo(self, t: float) -> None:
        self._neo_t, self._neo_n = t, self._n
        self._dau = True
        self._nghe_t0 = t + self._do_tre_s()

    async def _phat(self) -> None:
        loop = asyncio.get_running_loop()
        self._neo(loop.time())
        buf = bytearray()
        nguon = self._tai_pcm()
        try:
            try:
                async for chunk in nguon:
                    buf += chunk
                    while len(buf) >= BYTE_MOI_GOI:
                        goi = bytes(buf[:BYTE_MOI_GOI])
                        del buf[:BYTE_MOI_GOI]
                        await self._gui_goi(goi)
            except LoiAirPlay:
                raise
            except Exception as exc:  # noqa: BLE001 — nguồn/bộ giải mã hỏng: báo thành lỗi AirPlay, kèm kiểu lỗi
                raise LoiAirPlay(f"nguồn tiếng lỗi: {type(exc).__name__}: {exc}") from exc
            if buf:
                await self._gui_goi(bytes(buf) + b"\x00" * (BYTE_MOI_GOI - len(buf)))
            if not self.da_bat_dau.is_set():
                raise LoiAirPlay("nguồn không có tiếng nào")
            await self._cho_phat_not()
        finally:
            aclose = getattr(nguon, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()

    async def _cho_phat_not(self) -> None:
        """Hết nguồn: chờ loa phát nốt phần đã đệm (tính theo gói cuối), xử lý tạm dừng/tiếp tục trong lúc chờ."""
        while True:
            await self._chay_duoc.wait()
            if self._lai:
                await self._xa_lai()
            het = self._neo_t + (self._n - self._neo_n) * GOI_S + self._do_tre_s() + 0.1
            cho = het - asyncio.get_running_loop().time()
            if cho <= 0:
                return
            try:
                await asyncio.wait_for(self._ev_tam_dung.wait(), cho)
            except TimeoutError:
                return

    async def _gui_goi(self, pcm: bytes) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await self._chay_duoc.wait()
            if self._lai:
                await self._xa_lai()
            ke_hoach = self._neo_t + (self._n - self._neo_n) * GOI_S - DAN_DAU
            cho = ke_hoach - loop.time()
            if cho > 0:
                try:
                    await asyncio.wait_for(self._ev_tam_dung.wait(), cho)
                except TimeoutError:
                    pass
            if self._chay_duoc.is_set():
                break
        self._phat_mot(pcm)

    def _phat_mot(self, pcm: bytes, *, tu_lai: bool = False) -> None:
        dau = self._dau
        if dau:
            self._gui_dong_bo(True)
        seq, ts = (self._seq0 + self._n) & 0xFFFF, (self._ts0 + self._n * KHUNG_MOI_GOI) & 0xFFFFFFFF
        goi = goi_am_thanh(seq, ts, self._ssrc, pcm, dau, self._he_so() if self._he_so else 1.0)
        self._dau = False
        self._data.tp.sendto(goi, self._dich_data)
        self._dem[seq] = goi
        if len(self._dem) > DEM_GUI_LAI:
            self._dem.pop(next(iter(self._dem)))
        now = time.monotonic()
        self._lich_su.append((now, pcm))
        gioi_han = self._do_tre_s() + DAN_DAU + 0.5
        while self._lich_su and now - self._lich_su[0][0] > gioi_han:
            self._lich_su.popleft()
        self._n += 1
        self._so_goi_gui += 1
        if not tu_lai and not self.da_bat_dau.is_set():
            self.da_bat_dau.set()
            self._dat("phat")

    async def _xa_lai(self) -> None:
        """Sau khi tiếp tục: phát lại phần chưa kịp nghe, đúng nhịp thời gian thật như gói thường."""
        loop = asyncio.get_running_loop()
        while self._lai:
            ke_hoach = self._neo_t + (self._n - self._neo_n) * GOI_S - DAN_DAU
            cho = ke_hoach - loop.time()
            if cho > 0:
                await asyncio.sleep(cho)
            if not self._chay_duoc.is_set():
                return
            self._phat_mot(self._lai.popleft(), tu_lai=True)

    # ── đồng bộ / giữ kết nối / kênh UDP ────────────────────────

    def _ts_luc(self, t: float) -> int:
        """Dấu thời gian RTP ứng với đồng hồ đơn điệu ``t`` (theo mốc neo hiện tại)."""
        goi = self._neo_n + (t - self._neo_t) / GOI_S
        return int(self._ts0 + goi * KHUNG_MOI_GOI) & 0xFFFFFFFF

    def _gui_dong_bo(self, dau: bool) -> None:
        if self._ctrl is None or self._dich_ctrl is None:
            return
        t = asyncio.get_running_loop().time()
        self._ctrl.tp.sendto(goi_dong_bo(self._ts_luc(t), self.do_tre_khung, time.time(), dau), self._dich_ctrl)

    async def _vong_dong_bo(self) -> None:
        while True:
            await asyncio.sleep(DONG_BO_S)
            if self._chay_duoc.is_set() and self.da_bat_dau.is_set() and not self._dau:
                self._gui_dong_bo(False)

    async def _vong_giu_ket_noi(self) -> None:
        while True:
            await asyncio.sleep(GIU_KET_NOI_S)
            try:
                ma, _, _ = await self._rtsp.yeu_cau("OPTIONS", "*")
                self._kiem(ma, "OPTIONS (giữ kết nối)")
            except (LoiAirPlay, OSError, TimeoutError, asyncio.IncompleteReadError) as exc:
                raise LoiAirPlay(f"mất kết nối AirPlay: {exc!r}") from exc

    def _khi_nhan_ctrl(self, data: bytes, addr) -> None:
        yc = doc_yeu_cau_gui_lai(data)
        if yc is None:
            return
        dau, so = yc
        for i in range(min(so, 32)):
            goi = self._dem.get((dau + i) & 0xFFFF)
            if goi is not None and self._ctrl is not None:
                self._ctrl.tp.sendto(goi_gui_lai(goi), addr)
                self._so_gui_lai += 1

    def _khi_nhan_timing(self, data: bytes, addr) -> None:
        tl = tra_loi_timing(data, time.time())
        if tl is not None and self._timing is not None:
            self._timing.tp.sendto(tl, addr)

    # ── điều khiển ───────────────────────────────────────────────

    async def tam_dung(self) -> None:
        if self.trang_thai != "phat":
            return
        now = time.monotonic()
        do_tre = self._do_tre_s()
        self._lai = deque(p for t, p in self._lich_su if now - t < do_tre + DAN_DAU)   # đã gửi nhưng CHƯA kịp nghe (gói gửi sớm DAN_DAU giây)
        self._vt_goc = self.vi_tri
        self._chay_duoc.clear()
        self._ev_tam_dung.set()
        self._dat("tam_dung")
        seq, ts = (self._seq0 + self._n) & 0xFFFF, (self._ts0 + self._n * KHUNG_MOI_GOI) & 0xFFFFFFFF
        self._lich_su.clear()
        ma, _, _ = await self._rtsp.yeu_cau("FLUSH", self._url, {"RTP-Info": f"seq={seq};rtptime={ts}"})
        self._kiem(ma, "FLUSH")

    async def tiep(self) -> None:
        if self.trang_thai != "tam_dung":
            return
        self._neo(asyncio.get_running_loop().time())
        self._ev_tam_dung.clear()
        self._dat("phat")
        self._chay_duoc.set()

    async def dat_am_luong(self, muc: float) -> None:
        """``muc`` 0..1. Chưa mở xong thì nhớ và gửi sau RECORD."""
        self._am_luong = min(max(float(muc), 0.0), 1.0)
        if self._rtsp is not None and self._rtsp.phien:
            await self._gui_am_luong()

    async def _gui_am_luong(self) -> None:
        body = f"volume: {tu_am_luong(self._am_luong):f}\r\n".encode("ascii")
        ma, _, _ = await self._rtsp.yeu_cau("SET_PARAMETER", self._url, {"Content-Type": "text/parameters"}, body)
        self._kiem(ma, "SET_PARAMETER volume")

    async def _dong(self) -> None:
        for t in self._nen:
            t.cancel()
        for t in self._nen:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._nen = []
        if self._rtsp is not None and self._rtsp.phien:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._rtsp.yeu_cau("TEARDOWN", self._url), 2.0)
        if self._rtsp is not None:
            self._rtsp.dong()
        for g in (self._ctrl, self._timing, self._data):
            if g is not None and g.tp is not None:
                g.tp.close()
        self._dat("xong")


# ── Nguồn tiếng: ffmpeg giải mã mọi định dạng (mp3, m4a, opus, flac, wav…) ra PCM 16 bit 44,1 kHz 2 kênh ────────────────────────────────

#: Chỉ cho ffmpeg đi qua http(s): chặn ``file:``, ``concat:``, ``subfile:``… nếu địa chỉ phát bị làm giả.
GIAO_THUC_CHO_PHEP = "http,https,tcp,tls,crypto"
DOC_FFMPEG = BYTE_MOI_GOI * 16


def lenh_ffmpeg(ffmpeg: str, url: str, bat_dau: float = 0.0) -> list[str]:
    cmd = [ffmpeg, "-nostdin", "-loglevel", "error", "-protocol_whitelist", GIAO_THUC_CHO_PHEP]
    if bat_dau > 0:
        cmd += ["-ss", f"{bat_dau:.3f}"]
    return cmd + ["-i", url, "-vn", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "2", "-ar", str(SAMPLE_RATE), "-"]


def tao_nguon(url: str, bat_dau: float = 0.0, ffmpeg: str | None = None) -> Callable[[], AsyncIterator[bytes]]:
    """Hàm dựng nguồn cho ``PhienAirPlay``: mỗi lần gọi mở một tiến trình ffmpeg đọc ``url`` (bắt đầu từ ``bat_dau`` giây)."""

    async def doc() -> AsyncIterator[bytes]:
        ff = ffmpeg or shutil.which("ffmpeg")
        if not ff:
            raise LoiAirPlay("máy chạy HA không có ffmpeg để giải mã tiếng cho AirPlay")
        if not url.lower().startswith(("http://", "https://")):
            raise LoiAirPlay("AirPlay chỉ nhận địa chỉ http(s)")
        try:
            tien_trinh = await asyncio.create_subprocess_exec(
                *lenh_ffmpeg(ff, url, bat_dau), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        except OSError as exc:
            raise LoiAirPlay(f"không chạy được ffmpeg: {exc!r}") from exc
        try:
            while chunk := await tien_trinh.stdout.read(DOC_FFMPEG):
                yield chunk
            ma = await tien_trinh.wait()
            if ma != 0:
                raise LoiAirPlay(f"ffmpeg thoát mã {ma} (không mở/giải mã được nguồn)")
        finally:
            if tien_trinh.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    tien_trinh.kill()
                await tien_trinh.wait()

    return doc
