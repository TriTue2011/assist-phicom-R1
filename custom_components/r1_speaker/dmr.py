"""Máy khách DLNA/UPnP AV tối thiểu cho renderer CÓ SẴN trên loa R1 — thay tích hợp ``dlna_dmr`` của Home Assistant.

Chủ máy 28/10/2026: «trên R1 custom không cần thêm DLNA hay AirPlay riêng», «đàm thoại trên R1 nếu không có DLNA thì lại không được».
Trước đây ``media_player.r1_loa`` chuyển lệnh sang thực thể ``dlna_dmr`` của loa (phải tự thêm tay); nay tự làm lấy.

Đã đo trên loa thật (172.16.10.x, 28/10/2026): loa trả lời SSDP **unicast** tới cổng 1900 của chính nó (``M-SEARCH`` với
``ST: urn:schemas-upnp-org:device:MediaRenderer:1``) kèm ``LOCATION`` mô tả thiết bị (Platinum UPnP 1.0.4, cổng cấp phát lúc chạy,
nên tìm lại mỗi lần nối thay vì nhớ cổng). Phần SOAP (SetAVTransportURI/Play/Pause/Stop/Seek/GetTransportInfo/GetPositionInfo)
dùng ``async_upnp_client`` sẵn có của Home Assistant, không tự viết giao thức.

Quy tắc tài nguyên: ổ cắm SSDP đóng ngay sau lượt tìm; thiết bị UPnP chỉ nối khi cần và bỏ khi lỗi (lần sau tìm lại, vì cổng đổi
sau khi loa khởi động lại); không giữ kết nối nền, không đăng ký sự kiện (tiến độ do người gọi hỏi lại có chu kỳ, chỉ khi đang phát).
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from aiohttp import ClientError
from async_upnp_client.aiohttp import AiohttpSessionRequester
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.exceptions import UpnpError
from async_upnp_client.profiles.dlna import DmrDevice, TransportState
from async_upnp_client.utils import str_to_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

SSDP_PORT = 1900
SSDP_ST = "urn:schemas-upnp-org:device:MediaRenderer:1"
#: Chờ loa trả lời SSDP mỗi lượt (giây). Loa trả trong dưới 1 giây khi DLNA đang bật.
SSDP_CHO = 1.5
#: Chờ lệnh SOAP (giây). Loa yếu: đủ rộng để không cắt nhầm, đủ chặt để lệnh treo không giữ luồng.
SOAP_CHO = 8.0
AVT = "urn:schemas-upnp-org:service:AVTransport:1"

_CHAY = {TransportState.PLAYING.value: "playing", TransportState.TRANSITIONING.value: "buffering",
         TransportState.PAUSED_PLAYBACK.value: "paused", TransportState.PAUSED_RECORDING.value: "paused"}


def _giay(chuoi) -> float | None:
    """``HH:MM:SS`` của UPnP → giây; ``NOT_IMPLEMENTED``/rỗng/sai → ``None``."""
    try:
        t = str_to_time(str(chuoi or ""))
    except (ValueError, TypeError):
        return None
    return None if t is None else t.total_seconds()


class R1DmrError(Exception):
    """Không điều khiển được renderer của loa (không tìm thấy, không trả lời, lệnh bị từ chối)."""


@dataclass(frozen=True)
class TrangThaiDmr:
    state: str                     # "playing" | "buffering" | "paused" | "idle"
    loi: bool = False              # renderer báo TransportStatus ERROR_OCCURRED
    position: float | None = None  # giây
    duration: float | None = None  # giây
    uri: str | None = None


def gio_tua(giay: float, thap_phan: bool) -> str:
    """Đích tua ``REL_TIME`` dạng ``H:MM:SS`` (hoặc ``H:MM:SS.mmm`` khi ``thap_phan``). Thư viện UPnP cắt xuống số nguyên giây nên
    mọi lần tua đều lệch tới 1 giây; ở đây tự định dạng: có phần thập phân (đúng đặc tả) hoặc làm tròn GẦN NHẤT."""
    giay = max(0.0, float(giay))
    if not thap_phan:
        giay = float(round(giay))
    h, m = int(giay // 3600), int(giay % 3600 // 60)
    s = giay % 60
    return f"{h}:{m:02d}:{s:06.3f}" if thap_phan else f"{h}:{m:02d}:{int(s):02d}"


class UocViTri:
    """Ước vị trí phát CHÍNH XÁC hơn 1 giây từ ``RelTime`` của renderer (UPnP chỉ báo số NGUYÊN giây, làm tròn xuống).

    Vì sao: ``youtube`` đồng bộ nhiều loa bằng vị trí mà loa báo; vị trí cắt xuống số nguyên lệch trung bình nửa giây và dao động
    ±1 giây theo thời điểm hỏi, nên loa R1 bị «đo sai rồi chỉnh theo số sai» và trôi dần (chủ máy 28/10/2026: «lúc đầu đồng bộ, sau lệch
    dần»). Cách làm: gọi θ = vị trí thật − đồng hồ đơn điệu. Mỗi lần đọc n (nguyên) ở lúc t cho ràng buộc θ ∈ [n−t, n+1−t). GIAO các ràng
    buộc theo thời gian thì khoảng θ co lại nhanh (vài lần hỏi là còn cỡ 0,1–0,2 giây); ước = giữa khoảng. Hai ràng buộc không giao
    nhau (tua, đổi bài, tạm dừng, loa chạy lệch nhịp) thì bỏ khoảng cũ và bắt đầu lại từ lần đọc mới.
    """

    DUNG_SAI_S = 0.15

    def __init__(self) -> None:
        self._lo: float | None = None
        self._hi: float | None = None

    def reset(self) -> None:
        self._lo = self._hi = None

    @property
    def do_rong(self) -> float | None:
        return None if self._lo is None else self._hi - self._lo

    def them(self, doc_giay: float | None, t: float) -> float | None:
        """Đưa một lần đọc (giây nguyên, hoặc None) ở lúc đồng hồ đơn điệu ``t``; trả vị trí ước (giây) tại ``t``."""
        if doc_giay is None:
            self.reset()
            return None
        n = float(int(doc_giay))
        lo, hi = n - t, n + 1.0 - t
        if self._lo is not None:
            nlo, nhi = max(self._lo, lo), min(self._hi, hi)
            if nlo <= nhi:
                lo, hi = nlo, nhi
            elif nlo - nhi <= self.DUNG_SAI_S:
                lo = hi = (nlo + nhi) / 2                    # lệch nhẹ do loa chạy nhanh/chậm: co về điểm giữa, không bỏ lịch sử
        self._lo, self._hi = lo, hi
        return (lo + hi) / 2 + t


class _Nhan(asyncio.DatagramProtocol):
    def __init__(self, host: str, xong: asyncio.Future) -> None:
        self._host, self._xong = host, xong

    def datagram_received(self, data: bytes, addr) -> None:
        if self._xong.done():
            return
        for dong in data.decode("utf-8", "replace").split("\r\n"):
            if dong.lower().startswith("location:"):
                url = dong.split(":", 1)[1].strip()
                # Chỉ nhận mô tả của CHÍNH loa này: thiết bị khác trong mạng không được dẫn ta tới địa chỉ lạ.
                if urlparse(url).hostname == self._host:
                    self._xong.set_result(url)
                return


async def tim_mo_ta(host: str, *, cong: int = SSDP_PORT, cho: float = SSDP_CHO) -> str | None:
    """Địa chỉ mô tả thiết bị của renderer trên ``host`` (SSDP unicast), hoặc ``None`` nếu loa không trả lời."""
    loop = asyncio.get_running_loop()
    xong: asyncio.Future = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Nhan(host, xong), family=socket.AF_INET, local_addr=("0.0.0.0", 0))
    try:
        transport.sendto((f"M-SEARCH * HTTP/1.1\r\nHOST: {host}:{cong}\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\n"
                          f"ST: {SSDP_ST}\r\n\r\n").encode(), (host, cong))
        try:
            return await asyncio.wait_for(xong, cho)
        except TimeoutError:
            return None
    finally:
        transport.close()


async def tim_mo_ta_multicast(host: str, *, cho: float = SSDP_CHO) -> str | None:
    """Như ``tim_mo_ta`` nhưng hỏi bằng M-SEARCH MULTICAST (239.255.255.250:1900) rồi lọc theo địa chỉ loa. Dự phòng cho loa/mạng
    chỉ đáp lời tìm kiếm multicast (một số firmware bỏ qua gói gửi thẳng tới cổng 1900). Cần Home Assistant có đường multicast ra
    mạng của loa (chạy Docker kiểu cầu nối thì không có)."""
    loop = asyncio.get_running_loop()
    xong: asyncio.Future = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Nhan(host, xong), family=socket.AF_INET, local_addr=("0.0.0.0", 0))
    try:
        sock = transport.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        transport.sendto((f"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\n"
                          f"ST: {SSDP_ST}\r\n\r\n").encode(), ("239.255.255.250", SSDP_PORT))
        try:
            return await asyncio.wait_for(xong, cho)
        except TimeoutError:
            return None
    except OSError as exc:
        _LOGGER.debug("SSDP multicast tới loa %s không gửi được: %s", host, type(exc).__name__)
        return None
    finally:
        transport.close()


class R1Dmr:
    """Điều khiển renderer DLNA của một loa R1."""

    def __init__(self, hass: HomeAssistant, host: str, *, cong_ssdp: int = SSDP_PORT) -> None:
        self._hass, self._host, self._cong = hass, host, cong_ssdp
        self._dev: DmrDevice | None = None
        self._khoa = asyncio.Lock()
        self.mo_ta_cuoi: str | None = None     # địa chỉ mô tả lần nối thành công gần nhất (đúng tới khi loa khởi động lại)
        self.cach_tim: str | None = None
        self.chan_doan: list[str] = []         # lần tìm gần nhất hỏng ở đâu (để báo lỗi)
        self.tua_thap_phan = True              # loa nhận đích tua có phần thập phân giây (tự hạ xuống nguyên giây nếu loa từ chối)

    @property
    def da_noi(self) -> bool:
        """Đã nối được renderer (đã có thiết bị UPnP trong bộ nhớ): hỏi trạng thái khi đó chỉ tốn một lệnh SOAP, không tìm SSDP."""
        return self._dev is not None

    def _cach_tim(self, cho_ssdp: float):
        """Các cách tìm địa chỉ mô tả renderer, theo thứ tự rẻ → đắt. Mỗi cách trả ``(nhãn, hàm bất đồng bộ → địa chỉ | None)``.

        Chủ máy/người dùng khác 28/10/2026: bản chỉ dùng SSDP unicast bị rớt DLNA («chưa lên sau 15 giây») trên một mạng khác, trong khi
        ``dlna_dmr`` cũ vẫn tìm được: một đường duy nhất là mong manh, nên thử nhiều đường và ghi rõ đường nào hỏng."""
        async def nho():
            return self.mo_ta_cuoi

        async def dlna_dmr_cu():
            for cfg in self._hass.config_entries.async_entries("dlna_dmr"):
                url = str((cfg.data or {}).get("url") or "")
                if urlparse(url).hostname == self._host:
                    return url                              # địa chỉ người dùng đã nhập khi thêm dlna_dmr (đường chuyển đổi)
            return None

        async def ssdp_ha():
            try:
                from homeassistant.components import ssdp  # noqa: PLC0415
                for x in await ssdp.async_get_discovery_info_by_st(self._hass, SSDP_ST):
                    if urlparse(str(x.ssdp_location or "")).hostname == self._host:
                        return x.ssdp_location
            except Exception as exc:  # noqa: BLE001 - thành phần ssdp chưa nạp/đổi cấu trúc: bỏ qua đường này
                _LOGGER.debug("ssdp của Home Assistant không dùng được: %s", type(exc).__name__)
            return None

        yield "địa chỉ đã nhớ", nho
        yield "dlna_dmr cũ", dlna_dmr_cu
        yield "ssdp của Home Assistant", ssdp_ha
        yield "SSDP unicast", lambda: tim_mo_ta(self._host, cong=self._cong, cho=cho_ssdp)
        yield "SSDP multicast", lambda: tim_mo_ta_multicast(self._host, cho=cho_ssdp)

    async def _dung(self, mo_ta: str) -> DmrDevice | None:
        try:
            async with asyncio.timeout(SOAP_CHO):
                requester = AiohttpSessionRequester(async_get_clientsession(self._hass), with_sleep=True, timeout=SOAP_CHO)
                device = await UpnpFactory(requester, non_strict=True).async_create_device(mo_ta)
            return DmrDevice(device, None)
        except (UpnpError, ClientError, TimeoutError, OSError) as exc:
            _LOGGER.debug("Không đọc được mô tả renderer %s: %s", self._host, type(exc).__name__)
            return None

    async def _thiet_bi(self, cho_ssdp: float = SSDP_CHO) -> DmrDevice:
        async with self._khoa:
            if self._dev is not None:
                return self._dev
            da_thu: list[str] = []
            for nhan, tim in self._cach_tim(cho_ssdp):
                mo_ta = await tim()
                if not mo_ta:
                    da_thu.append(f"{nhan}: không thấy")
                    continue
                dev = await self._dung(mo_ta)
                if dev is None:
                    da_thu.append(f"{nhan}: thấy nhưng không đọc được mô tả")
                    continue
                self._dev, self.mo_ta_cuoi, self.cach_tim = dev, mo_ta, nhan
                if nhan != "địa chỉ đã nhớ":
                    _LOGGER.info("Loa %s: tìm được renderer DLNA bằng «%s»", self._host, nhan)
                return dev
            self.chan_doan = da_thu
            raise R1DmrError(
                f"Không tìm thấy renderer DLNA của loa {self._host} (đã thử: {'; '.join(da_thu)}). DLNA của loa đang tắt, loa mất mạng, "
                "hoặc UDP 1900 giữa Home Assistant và loa bị chặn (tường lửa, cách ly máy khách của wifi, Home Assistant chạy Docker kiểu cầu nối).")

    def _bo(self) -> None:
        """Bỏ thiết bị đã nối: cổng của renderer đổi sau khi loa khởi động lại, lần sau tìm lại."""
        self._dev = None

    async def _goi(self, viec):
        dev = await self._thiet_bi()
        try:
            async with asyncio.timeout(SOAP_CHO + 2):
                return await viec(dev)
        except (UpnpError, ClientError, TimeoutError, OSError) as exc:
            self._bo()
            raise R1DmrError(f"Renderer của loa {self._host} lỗi: {type(exc).__name__}") from exc

    async def async_san_sang(self, toi_da: float) -> None:
        """Chờ renderer lên (loa vừa bật DLNA): thử tìm lại mỗi giây cho tới ``toi_da`` giây."""
        try:
            async with asyncio.timeout(toi_da):
                while True:
                    try:
                        await self._thiet_bi(cho_ssdp=1.0)
                        return
                    except R1DmrError:
                        await asyncio.sleep(0.5)
        except TimeoutError:
            raise R1DmrError(f"Renderer của loa {self._host} chưa lên sau {toi_da:.0f} giây "
                             "(DLNA của loa chưa bật?)") from None

    async def async_phat(self, url: str, tieu_de: str) -> None:
        async def viec(dev: DmrDevice) -> None:
            await dev.async_set_transport_uri(url, tieu_de)
            await dev.async_wait_for_can_play(3)
            await dev.async_play()
        await self._goi(viec)

    async def async_tiep(self) -> None:
        await self._goi(lambda dev: dev.async_play())

    async def async_tam_dung(self) -> None:
        await self._goi(lambda dev: dev.async_pause())

    async def async_dung(self) -> None:
        await self._goi(lambda dev: dev.async_stop())

    async def async_tua(self, giay: float) -> None:
        async def viec(dev: DmrDevice) -> None:
            if not dev.has_seek_rel_time:
                raise UpnpError("renderer không hỗ trợ tua")
            tua = dev.device.service(AVT).action("Seek")
            if self.tua_thap_phan:
                try:
                    await tua.async_call(InstanceID=0, Unit="REL_TIME", Target=gio_tua(giay, True))
                    return
                except UpnpError as exc:
                    # Loa từ chối đích có phần thập phân: nhớ, từ nay làm tròn gần nhất tới giây (chính xác hơn cắt xuống).
                    _LOGGER.info("Loa %s không nhận đích tua thập phân (%s): chuyển sang nguyên giây", self._host, type(exc).__name__)
                    self.tua_thap_phan = False
            await tua.async_call(InstanceID=0, Unit="REL_TIME", Target=gio_tua(giay, False))
        await self._goi(viec)

    async def async_doc(self) -> TrangThaiDmr:
        """Hỏi trạng thái hiện tại (GetTransportInfo, kèm GetPositionInfo khi đang phát)."""
        async def viec(dev: DmrDevice) -> TrangThaiDmr:
            # Gọi thẳng hành động SOAP thay vì ``dev.async_update``: thư viện nuốt lỗi mạng ở đó, nên renderer chết (loa tắt DLNA,
            # khởi động lại) sẽ không bị phát hiện và ta không bao giờ tìm lại cổng mới.
            dich_vu = dev.device.service(AVT)
            thong_tin = await dich_vu.action("GetTransportInfo").async_call(InstanceID=0)
            state = _CHAY.get(str(thong_tin.get("CurrentTransportState") or ""), "idle")
            loi = str(thong_tin.get("CurrentTransportStatus") or "").upper() == "ERROR_OCCURRED"
            pos = duration = uri = None
            if state != "idle":
                vi_tri = await dich_vu.action("GetPositionInfo").async_call(InstanceID=0)
                pos, duration = _giay(vi_tri.get("RelTime")), _giay(vi_tri.get("TrackDuration"))
                uri = str(vi_tri.get("TrackURI") or "") or None
            return TrangThaiDmr(state=state, loi=loi, position=pos, duration=duration, uri=uri)
        return await self._goi(viec)
