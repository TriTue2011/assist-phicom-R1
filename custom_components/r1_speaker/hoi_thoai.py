"""Phòng đàm thoại nhiều loa: Home Assistant làm trung gian TRỘN tiếng mic của các loa (và điện thoại) rồi phát ra loa khác.

Dựng trên phiên song công của TỪNG loa (``song_cong.R1Duplex``): mỗi loa vẫn có phiên riêng (chiếm chỗ qua ``R1Talk.claim``, canh giờ, đứt mic
thì đóng, khử vọng với tiếng HA phát xuống loa đó); phòng chỉ nối chúng lại bằng bộ trộn thuần ``tron_tieng.BoTron``:

* **Điện thoại ↔ một hay nhiều loa**: điện thoại nói thì mọi loa trong phòng nghe; điện thoại nghe tiếng mic của mọi loa (đã trộn).
* **Loa ↔ loa** (``giua_cac_loa``): mỗi loa nghe tiếng mic của các loa KHÁC, không nghe lại chính mình.
  ``che_do="tron"`` (mặc định): ai nói cũng nghe, hợp khi mỗi loa một phòng. ``che_do="quyen_noi"``: mỗi lúc một loa giữ quyền nói, dùng khi
  hai loa đặt chung một phòng để khỏi vòng hú (CHƯA KIỂM trên loa thật).

Vòng đời: mở TRỌN GÓI (một loa bận thì đóng lại các loa đã mở), mỗi loa bị đặt ``downlink_busy`` để các đường đàm thoại riêng (WebSocket, POST
``/duplex``) từ chối, nhạc đang phát bị giữ (tạm dừng) suốt phòng để tiếng nhạc phòng này không lọt qua mic sang phòng khác. Một loa rớt (mic đứt,
hết giờ, gỡ tích hợp) thì chỉ loa đó rời; còn đủ bên thì phòng chạy tiếp. Trộn chạy theo nhịp 20 ms bằng đồng hồ thật, bù khi vòng lặp trễ
(trần ``BUOC_TOI_DA``); mỗi nguồn có đệm có trần (quy tắc tài nguyên của kho)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from aiohttp import WSMsgType, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, EVENT_HOI_THOAI
from .tron_tieng import CHE_DO, DIEN_THOAI, KHUNG_S, LOA, BoTron

_LOGGER = logging.getLogger(__name__)

TICK_S = 0.02
#: Vòng lặp trễ thì bù tối đa ngần này khung 10 ms mỗi nhịp (0,25 s) rồi bỏ phần còn lại, không dồn tiếng.
BUOC_TOI_DA = 25
TOI_DA_LOA = 6
DT = "dt"
#: Gộp tiếng chờ gửi điện thoại (giống dam_thoai_ws): ~0,05 s một khung, trần 64 KB.
GOP_S = 0.05
TRAN_DEM = 64 * 1024
MA_BAN = 4409          # loa đang trong phòng/phiên khác
MA_LOI_MO = 4400       # không mở được phòng
MA_PHIEN_DONG = 4001   # phòng đã đóng


@dataclass(frozen=True)
class LoaCuaPhong:
    """Một loa trong phòng: ``ma`` = id mục cấu hình; ``duplex`` là ``R1Duplex``; ``music`` là ``MusicKeeper`` (giữ nhạc)."""

    ma: str
    ten: str
    duplex: Any
    music: Any


class DienThoai:
    """Đầu cắm của điện thoại trong phòng (một điện thoại một phòng)."""

    def __init__(self, phong: "Phong") -> None:
        self._phong = phong

    def feed(self, pcm: bytes) -> None:
        if pcm and len(pcm) % 2 == 0 and self._phong.dang:
            self._phong.bo_tron.dua(DT, pcm)

    def ptt(self, giu: bool) -> None:
        self._phong.bo_tron.dat_ptt(DT, giu)

    def roi(self) -> None:
        self._phong.roi(DT, "dien_thoai_roi")


class Phong:
    def __init__(self, hass: HomeAssistant, loa: list[LoaCuaPhong], *, giua_cac_loa: bool = True, che_do: str = "tron",
                 tren_dong: Callable[["Phong"], None] | None = None) -> None:
        self.hass, self.ma = hass, uuid.uuid4().hex[:8]
        self.giua_cac_loa, self.che_do = giua_cac_loa, che_do
        self.bo_tron = BoTron(giua_cac_loa=giua_cac_loa, che_do=che_do)
        self._loa = {b.ma: b for b in loa}
        self._huy: dict[str, list[Callable[[], None]]] = {}
        self._giu_nhac: dict[str, Any] = {}
        self._sink_dt: Callable[[bytes], None] | None = None
        self._tick: asyncio.Task | None = None
        self._tren_dong = tren_dong
        self._cb: list[Callable[[], None]] = []
        self.dang = False
        self.ly_do_dong: str | None = None

    # ── Trạng thái ───────────────────────────────────────────────

    @property
    def loa(self) -> list[LoaCuaPhong]:
        return list(self._loa.values())

    @property
    def co_dien_thoai(self) -> bool:
        return self._sink_dt is not None

    def mo_ta(self) -> dict[str, Any]:
        return {"ma": self.ma, "loa": [b.ten for b in self._loa.values()], "dien_thoai": self.co_dien_thoai,
                "che_do": self.che_do, "giua_cac_loa": self.giua_cac_loa}

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._cb.append(cb)
        return lambda: self._cb.remove(cb) if cb in self._cb else None

    def _bao(self) -> None:
        for b in self._loa.values():
            with contextlib.suppress(Exception):
                b.duplex.dat_phong(self)              # làm mới thuộc tính trên cảm biến mic của từng loa
        for cb in list(self._cb):
            try:
                cb()
            except Exception:  # noqa: BLE001 — bên nghe hỏng không được phá phòng
                _LOGGER.exception("R1 hoi_thoai: listener failed")

    # ── Mở ───────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Mở phiên song công của MỌI loa; một loa không mở được thì đóng lại các loa đã mở rồi ném lỗi (không để phòng nửa vời)."""
        da_mo: list[LoaCuaPhong] = []
        try:
            for b in self._loa.values():
                d = b.duplex
                if d.active or d.downlink_busy or d.phong is not None:
                    raise HomeAssistantError(f"{b.ten}: đang có phiên đàm thoại khác")
                await d.async_start()                 # chiếm chỗ qua R1Talk.claim; Assist/bộ đàm đang bận thì R1SessionBusy
                da_mo.append(b)
                d.downlink_busy = True
        except BaseException:
            for b in da_mo:
                self._nha(b, "hoi_thoai_loi")
            raise
        self.dang = True
        for b in self._loa.values():
            try:
                self._giu_nhac[b.ma] = await b.music.hold()   # nhạc phòng này im suốt phòng: khỏi lọt qua mic sang phòng khác
            except Exception:  # noqa: BLE001 — không giữ được nhạc không phải lý do bỏ phòng
                _LOGGER.warning("hoi_thoai: không giữ được nhạc của %s", b.ten, exc_info=True)
            self.bo_tron.them(b.ma, LOA)
            self._huy[b.ma] = [b.duplex.add_audio_listener(lambda khung, ma=b.ma: self.bo_tron.dua(ma, khung)),
                               b.duplex.add_listener(lambda ma=b.ma: self._khi_phien_doi(ma))]
        self._tick = self.hass.async_create_background_task(self._chay(), "r1_speaker hoi_thoai tron")
        self.hass.bus.async_fire(EVENT_HOI_THOAI, {"su_kien": "mo", "ma": self.ma, "loa": [b.ten for b in self._loa.values()]})
        self._bao()
        _LOGGER.debug("hoi_thoai %s: mở với %d loa (%s)", self.ma, len(self._loa), self.che_do)

    def gan_dien_thoai(self, sink: Callable[[bytes], None]) -> DienThoai:
        """Điện thoại vào phòng. ``sink`` nhận tiếng đã trộn (PCM16 16 kHz mono) để gửi về điện thoại."""
        if not self.dang:
            raise HomeAssistantError("Phòng đàm thoại đã đóng.")
        if self._sink_dt is not None:
            raise HomeAssistantError("Phòng đã có một điện thoại.")
        self._sink_dt = sink
        self.bo_tron.them(DT, DIEN_THOAI)
        self._bao()
        return DienThoai(self)

    # ── Nhịp trộn ────────────────────────────────────────────────

    async def _chay(self) -> None:
        truoc = time.monotonic()
        while self.dang:
            await asyncio.sleep(TICK_S)
            nay = time.monotonic()
            so = int((nay - truoc) / KHUNG_S)
            truoc = nay if so > BUOC_TOI_DA else truoc + so * KHUNG_S
            self.nhip(min(so, BUOC_TOI_DA))

    def nhip(self, so_buoc: int) -> None:
        """Trộn ``so_buoc`` khung 10 ms rồi phát cho từng bên (test gọi thẳng, không cần ngủ)."""
        ra: dict[str, list[bytes]] = {}
        for _ in range(so_buoc):
            for ma, khung in self.bo_tron.buoc().items():
                ra.setdefault(ma, []).append(khung)
        for ma, ds in ra.items():
            pcm = b"".join(ds)
            if ma == DT:
                if self._sink_dt is not None:
                    self._sink_dt(pcm)
                continue
            b = self._loa.get(ma)
            if b is None:
                continue
            try:
                b.duplex.feed_playback(pcm, vox=False)
            except HomeAssistantError:                # phiên loa đã đóng giữa chừng
                self.roi(ma, "mat_loa")

    # ── Rời / đóng ───────────────────────────────────────────────

    def _khi_phien_doi(self, ma: str) -> None:
        b = self._loa.get(ma)
        if b is not None and not b.duplex.active:
            self.roi(ma, "mat_loa")

    def _nha(self, b: LoaCuaPhong, ly_do: str) -> None:
        for h in self._huy.pop(b.ma, []):
            with contextlib.suppress(Exception):
                h()
        d = b.duplex
        d.downlink_busy = False
        if d.phong is self:
            d.dat_phong(None)
        d.end(ly_do)
        giu = self._giu_nhac.pop(b.ma, None)
        if giu is not None:
            self.hass.async_create_background_task(giu.release(), "r1_speaker hoi_thoai nha nhac")

    def _con_du(self) -> bool:
        so_loa = len(self._loa)
        return so_loa >= (1 if self.co_dien_thoai else 2)

    def roi(self, ma: str, ly_do: str) -> None:
        """Một bên rời phòng (loa rớt, điện thoại ngắt). Còn đủ bên thì phòng chạy tiếp, không thì đóng."""
        if not self.dang:
            return
        self.bo_tron.bo(ma)
        if ma == DT:
            self._sink_dt = None
        else:
            b = self._loa.pop(ma, None)
            if b is not None:
                self._nha(b, ly_do)
        if not self._con_du():
            self.end("het_ben")
        else:
            self._bao()

    def end(self, ly_do: str) -> None:
        """Đóng phòng sạch (gọi lại không sao): đóng phiên của mọi loa còn lại, nhả nhạc, huỷ nhịp trộn."""
        if not self.dang:
            return
        self.dang = False
        self.ly_do_dong = ly_do
        if self._tick is not None:
            self._tick.cancel()
            self._tick = None
        ten = [b.ten for b in self._loa.values()]
        for b in list(self._loa.values()):
            self._nha(b, ly_do)
        self._loa.clear()
        self._sink_dt = None
        if self._tren_dong is not None:
            self._tren_dong(self)
        self.hass.bus.async_fire(EVENT_HOI_THOAI, {"su_kien": "dong", "ma": self.ma, "loa": ten, "ly_do": ly_do})
        for cb in list(self._cb):
            with contextlib.suppress(Exception):
                cb()


class HoiThoai:
    """Các phòng đang mở của cả HA (trải qua nhiều mục cấu hình nên nằm ở cấp miền)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._phong: dict[str, Phong] = {}

    def phong_cua(self, ma_loa: str) -> Phong | None:
        return next((p for p in self._phong.values() if ma_loa in p._loa), None)

    def phong_theo_bo_loa(self, ma_loa: set[str]) -> Phong | None:
        return next((p for p in self._phong.values() if set(p._loa) == ma_loa), None)

    async def mo(self, loa: list[LoaCuaPhong], *, giua_cac_loa: bool = True, che_do: str = "tron") -> Phong:
        if not 1 <= len(loa) <= TOI_DA_LOA:
            raise HomeAssistantError(f"Phòng đàm thoại cần 1–{TOI_DA_LOA} loa.")
        if len({b.ma for b in loa}) != len(loa):
            raise HomeAssistantError("Có loa bị chọn trùng.")
        if che_do not in CHE_DO:
            raise HomeAssistantError(f"Chế độ không hợp lệ: {che_do}")
        for b in loa:
            if self.phong_cua(b.ma) is not None:
                raise HomeAssistantError(f"{b.ten}: đang ở trong một phòng đàm thoại khác")
        p = Phong(self.hass, loa, giua_cac_loa=giua_cac_loa, che_do=che_do, tren_dong=self._go)
        self._phong[p.ma] = p                          # đăng ký TRƯỚC khi mở: hai lệnh mở cùng lúc không cùng chiếm một loa
        try:
            await p.async_start()
        except BaseException:
            self._phong.pop(p.ma, None)
            raise
        return p

    def _go(self, p: Phong) -> None:
        self._phong.pop(p.ma, None)

    def dong_het(self, ly_do: str) -> None:
        for p in list(self._phong.values()):
            p.end(ly_do)


def hub(hass: HomeAssistant) -> HoiThoai:
    return hass.data.setdefault(f"{DOMAIN}_hoi_thoai", HoiThoai(hass))


# ── Từ thực thể HA ra loa ────────────────────────────────────────

def loa_tu_thuc_the(hass: HomeAssistant, entity_id: str) -> LoaCuaPhong:
    rec = er.async_get(hass).async_get(entity_id)
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    c = getattr(entry, "runtime_data", None) if entry is not None and entry.domain == DOMAIN else None
    if c is None:
        raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker, hoặc loa chưa nạp xong")
    return LoaCuaPhong(entry.entry_id, entry.title, c.duplex, c.music)


# ── Dịch vụ ──────────────────────────────────────────────────────

def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _mo(call) -> None:
        loa = [loa_tu_thuc_the(hass, e) for e in call.data["entity_ids"]]
        try:
            await hub(hass).mo(loa, giua_cac_loa=call.data["giua_cac_loa"], che_do=call.data["che_do"])
        except HomeAssistantError as exc:
            raise ServiceValidationError(str(exc)) from exc

    async def _dong(call) -> None:
        p = hub(hass).phong_cua(loa_tu_thuc_the(hass, call.data["entity_id"]).ma)
        if p is not None:
            p.end("nguoi_dung_ket_thuc")

    hass.services.async_register(DOMAIN, "start_conference", _mo, schema=vol.Schema({
        vol.Required("entity_ids"): vol.All(cv.ensure_list, [cv.entity_id], vol.Length(min=2, max=TOI_DA_LOA)),
        vol.Optional("che_do", default="tron"): vol.In(CHE_DO),
        vol.Optional("giua_cac_loa", default=True): cv.boolean}))
    hass.services.async_register(DOMAIN, "stop_conference", _dong, schema=vol.Schema({vol.Required("entity_id"): cv.entity_id}))


# ── WebSocket cho điện thoại (từ 2 loa trở lên) ──────────────────

class HoiThoaiWsView(HomeAssistantView):
    """Điện thoại đàm thoại với MỘT HAY NHIỀU loa qua một WebSocket: ``?e=<thực thể loa>`` (lặp lại cho mỗi loa), ``&giua=1`` để các loa nghe nhau,
    ``&che_do=tron|quyen_noi``. Xác thực bằng đường dẫn đã ký (``auth/sign_path`` ký cả tham số truy vấn). Khung nhị phân PCM16 16 kHz mono hai chiều;
    chữ ``noi``/``het`` = giữ/thả nút nói; lỗi dạng JSON ``{"loi": "..."}``. Kết nối vào phòng đã có đúng bộ loa này thì gia nhập, không thì mở phòng
    mới và đóng khi điện thoại ngắt."""

    url = "/api/r1_speaker/hoi_thoai/ws"
    name = "api:r1_speaker:hoi_thoai_ws"
    requires_auth = True

    async def get(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        ws = web.WebSocketResponse(heartbeat=20.0, max_msg_size=1 << 16)
        await ws.prepare(request)

        async def tu_choi(ma: int, loi: str) -> web.StreamResponse:
            await ws.send_json({"loi": loi})
            await ws.close(code=ma)
            return ws

        ds = list(dict.fromkeys(request.query.getall("e", [])))
        che_do = request.query.get("che_do", "tron")
        if not 1 <= len(ds) <= TOI_DA_LOA or che_do not in CHE_DO:
            return await tu_choi(MA_LOI_MO, "Tham số không hợp lệ (e=1–6 loa, che_do=tron|quyen_noi).")
        try:
            loa = [loa_tu_thuc_the(hass, e) for e in ds]
        except ServiceValidationError as exc:
            return await tu_choi(MA_LOI_MO, str(exc))
        dem = bytearray()

        def dem_gui(pcm: bytes) -> None:
            dem.extend(pcm)
            if len(dem) > TRAN_DEM:
                del dem[: len(dem) - TRAN_DEM]       # điện thoại chậm: bỏ phần cũ nhất

        h = hub(hass)
        phong = h.phong_theo_bo_loa({b.ma for b in loa})
        tu_mo = False
        try:
            if phong is None:
                phong = await h.mo(loa, giua_cac_loa=request.query.get("giua") == "1", che_do=che_do)
                tu_mo = True
        except HomeAssistantError as exc:                # loa bận, chưa nối mic/kênh phát, hoặc Assist đang giữ phiên
            return await tu_choi(MA_LOI_MO, str(exc))
        try:
            dt = phong.gan_dien_thoai(dem_gui)
        except HomeAssistantError as exc:                # phòng đã có điện thoại khác, hoặc vừa đóng
            if tu_mo:
                phong.end("loi_vao")
            return await tu_choi(MA_BAN, str(exc))

        def phong_doi() -> None:
            if not phong.dang and not ws.closed:
                hass.async_create_task(ws.close(code=MA_PHIEN_DONG))

        huy_doi = phong.add_listener(phong_doi)

        async def gui_di() -> None:
            while not ws.closed:
                await asyncio.sleep(GOP_S)
                if dem:
                    khuc = bytes(dem)
                    dem.clear()
                    await ws.send_bytes(khuc)

        gui = hass.async_create_background_task(gui_di(), "r1_speaker hoi_thoai ws gui")
        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    dt.feed(msg.data)
                elif msg.type == WSMsgType.TEXT:
                    if msg.data == "noi":
                        dt.ptt(True)
                    elif msg.data == "het":
                        dt.ptt(False)
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            gui.cancel()
            with contextlib.suppress(asyncio.CancelledError, ConnectionError):
                await gui
            huy_doi()
            dt.roi()
            if tu_mo:
                phong.end("dong_dien_thoai")
        return ws
