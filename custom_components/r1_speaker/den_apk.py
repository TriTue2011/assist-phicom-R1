"""Sink đèn KHÔNG cần ADB: lệnh đèn của HA đi qua kết nối mic đã xác thực tới APK trên loa, APK gọi hiệu ứng CÓ SẴN của firmware
(``msgcenter.sendMsg(0x1000, ID, 0)``, xem ``den_firmware``). Dùng khi người dùng chọn chế độ «đóng ADB» (``tu_dong_dong_adb``), và là
đường dự phòng khi ADB lỗi.

Khác ADB: không có màu tuỳ ý, tốc độ hay độ sáng riêng; hiệu ứng «thở» và «chạy đuổi» do firmware tự lặp, các hiệu ứng còn lại (nhấp nháy,
nhịp tim, chớp, pháo hoa, cầu vồng, sao chổi) chạy bằng cách HA đổi lần lượt các màu của firmware (màu bị làm tròn về bảng màu của firmware,
bước đổi không nhanh hơn ``BUOC_TOI_THIEU_S``). Firmware chỉ giữ MỘT hiệu ứng tại một thời điểm: đáy và viền không sáng cùng lúc; đáy đang
sáng thì ưu tiên đáy (gửi ID tắt viền sẽ đóng luôn hiệu ứng đáy vừa bật: lỗi «đáy không sáng, viền thì sáng» 22/10/2026).

``available`` = APK đang nối VÀ báo ``che_do = firmware`` với ``san_sang``: APK bản cũ không báo nên coi là chưa sẵn sàng thay vì gửi vào hư không."""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import random
import time
from collections.abc import Callable, Iterable
from typing import Any

from . import den_firmware as fw
from .den_hieu_ung import TAT, VUNG_DAY, VUNG_VIEN, chuan_hoa
from .den_port import LightsError

_LOGGER = logging.getLogger(__name__)

#: Bước đổi màu nhanh nhất (giây): tin tới APK qua TCP rồi binder tới firmware, không đáng đẩy dày hơn.
BUOC_TOI_THIEU_S = 0.3

Buoc = tuple[int, float]            # (ID firmware, giữ bao lâu trước bước kế)


def _kich_ban(vung: str, hieu_ung: str, ps: dict[str, Any], master: int, rng: random.Random) -> tuple[Iterable[Buoc], bool]:
    """(các bước, lặp?) cho MỘT hiệu ứng. Không lặp = gửi bước đầu rồi để firmware giữ (hoặc tự lặp)."""
    sang = ps.get("do_sang", 100) * master / 100
    toc = max(ps.get("toc_do", 100), 1) / 100
    if vung == VUNG_VIEN:
        bat = sang > 0
        if hieu_ung == "sang":
            return [(fw.RIM_BAT if bat else fw.RIM_TAT, 0.0)], False
        if hieu_ung == "chay_duoi":
            return [(fw.ID_CHAY_DUOI if bat else fw.RIM_TAT, 0.0)], False
        ck = 2.0 / toc                                   # «thở» của viền: firmware không có, nên bật/tắt chậm
        return (itertools.cycle([(fw.RIM_BAT, ck / 2), (fw.RIM_TAT, ck / 2)]) if bat else [(fw.RIM_TAT, 0.0)]), bat
    if sang <= 0:
        return [(fw.DAY_TAT, 0.0)], False
    rgb = fw.rgb_tu_hex(ps["mau"]) if "mau" in ps else (255, 255, 255)
    if hieu_ung == "co_dinh":
        return [(fw.id_day(rgb, False, sang), 0.0)], False
    if hieu_ung == "tho":
        return [(fw.id_day(rgb, True, sang), 0.0)], False                 # firmware tự lặp, tốc độ/độ sâu do nó quyết định
    bat = fw.id_day(rgb, False, sang)
    tat = fw.DAY_TAT
    if hieu_ung == "nhap_nhay":
        ck, tl = 1.0 / toc, ps.get("ty_le_bat", 50) / 100
        return itertools.cycle([(bat, ck * tl), (tat, ck * (1 - tl))]), True
    if hieu_ung == "nhip_tim":
        b, nghi = 0.12 / toc, ps.get("nghi_ms", 660) / 1000 / toc
        return itertools.cycle([(bat, b), (tat, b), (bat, b), (tat, nghi)]), True
    if hieu_ung == "chop":
        c, nghi = 0.1 / toc, ps.get("nghi_ms", 800) / 1000 / toc
        return itertools.cycle([(bat, c), (tat, c)] * int(ps.get("so_chop", 3)) + [(tat, nghi)]), True
    if hieu_ung == "phao_hoa":
        bang = {"am": (500, 252), "lanh": (502, 255, 253)}.get(ps.get("bang_mau"), fw.CAU_VONG)
        nghi = ps.get("nghi_ms", 450) / 1000 / toc

        def chum():
            while True:
                yield rng.choice(bang), 0.25 / toc
                yield fw.DAY_TAT, nghi
        return chum(), True
    # cau_vong, cau_vong_fw, cau_vong_xoay, sao_choi: đổi lần lượt sáu màu của firmware (không có 12 sắc độ, dải xoay hay đuôi sao chổi)
    mau = tuple(reversed(fw.CAU_VONG)) if ps.get("chieu") == "nguoc" else fw.CAU_VONG
    if hieu_ung == "sao_choi" and ps.get("kieu_mau") == "don_sac":
        return itertools.cycle([(bat, 0.3 / toc), (tat, 0.3 / toc)]), True
    return itertools.cycle([(m, 0.4 / toc) for m in mau]), True


class ApkLights:
    name = "apk"

    def __init__(self, mic_server, *, rng: random.Random | None = None) -> None:
        self._server = mic_server
        self._rng = rng or random.Random()
        self._khoa = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._chu: str | None = None                  # vùng đang giữ hiệu ứng của firmware
        self._dang: tuple | None = None               # (vùng, hiệu ứng, thông số, master) đang chạy: không áp lại cái đang chạy
        self._cuoi: int | None = None                 # ID đã gửi gần nhất (bỏ lệnh thừa)
        self._dang_ap = 0
        self._xong_luc = 0.0
        self.loi: str | None = None
        self.khi_roi: Callable[[], None] | None = None

    @property
    def available(self) -> bool:
        return bool(self._server.receiving and self._server.den_san_sang)

    @property
    def ly_do(self) -> str:
        """Vì sao chưa sáng: loa chưa nối (``mat_ket_noi``) hay APK chưa hỗ trợ đèn firmware (``CHO_DICH_VU_DEN``)."""
        return self.loi or ("CHO_DICH_VU_DEN" if self._server.receiving else "mat_ket_noi")

    def dang_ap_dung(self, yen_s: float = 2.0) -> bool:
        return self._dang_ap > 0 or time.monotonic() - self._xong_luc < yen_s

    def hieu_ung_chay(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _gui(self, ma: int, *, ep: bool = False) -> None:
        if not ep and ma == self._cuoi:
            return
        try:
            await self._server.gui_hieu_ung(ma)
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            self._cuoi = None
            self.loi = f"loa chưa nối về HA: {exc or type(exc).__name__}"
            raise LightsError(self.loi) from exc
        self._cuoi = ma
        self.loi = None

    async def _dung_vong(self) -> None:
        t, self._task = self._task, None
        if t is not None and not t.done():
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    async def ap_dung(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int = 100) -> None:
        self._dang_ap += 1
        try:
            async with self._khoa:
                await self._ap(vung, hieu_ung, params, master)
        finally:
            self._dang_ap -= 1
            self._xong_luc = time.monotonic()

    async def _ap(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int) -> None:
        tat_id = fw.DAY_TAT if vung == VUNG_DAY else fw.RIM_TAT
        if hieu_ung == TAT:
            if self._chu not in (None, vung):          # vùng kia đang giữ hiệu ứng: ID tắt của vùng này sẽ đóng luôn nó
                return
            await self._dung_vong()
            self._chu = self._dang = None
            await self._gui(tat_id)
            return
        if vung == VUNG_VIEN and self._chu == VUNG_DAY:
            return                                     # đáy đang sáng thì ưu tiên đáy
        try:
            ps = chuan_hoa(vung, hieu_ung, params)
        except ValueError as exc:
            raise LightsError(str(exc)) from exc
        khoa = (vung, hieu_ung, tuple(sorted(ps.items())), master)
        if khoa == self._dang and (self._task is None or not self._task.done()):
            return
        await self._dung_vong()
        buoc, lap = _kich_ban(vung, hieu_ung, ps, master, self._rng)
        self._chu, self._dang = vung, khoa
        if not lap:
            try:
                await self._gui(next(iter(buoc))[0])
            except LightsError:
                self._chu = self._dang = None           # chưa gửi được thì CHƯA «đang chạy»: lần áp sau (loa nối lại) phải gửi lại
                raise
            return
        self._task = asyncio.get_running_loop().create_task(self._chay(iter(buoc)))

    async def _chay(self, buoc) -> None:
        try:
            for ma, giu in buoc:
                await self._gui(ma)
                await asyncio.sleep(max(giu, BUOC_TOI_THIEU_S))
        except LightsError:
            pass                                       # mất kết nối giữa hiệu ứng: dừng, lần áp sau (loa nối lại) sẽ chạy lại

    async def tat(self) -> None:
        async with self._khoa:
            await self._dung_vong()
            self._chu = self._dang = None
            for ma in (fw.DAY_TAT, fw.RIM_TAT):
                await self._gui(ma, ep=True)

    async def dung(self) -> None:
        async with self._khoa:
            await self._dung_vong()
            self._chu = self._dang = None


class LightsRouter:
    """Chọn đường đèn theo chế độ người dùng chọn: «đóng ADB» (``dong()`` đúng) thì CHỈ APK, không chạm ADB; ngược lại ADB trước,
    ADB lỗi mà APK sẵn sàng thì dùng APK."""

    def __init__(self, adb, apk: ApkLights, dong: Callable[[], bool]) -> None:
        self.adb, self.apk, self._dong = adb, apk, dong

    @property
    def name(self) -> str:
        return "apk" if self._dong() else "adb"

    @property
    def available(self) -> bool:
        return self.apk.available if self._dong() else bool(self.adb.available)

    @property
    def ly_do(self) -> str:
        return self.apk.ly_do if self._dong() else self.adb.ly_do

    @property
    def dev(self):
        return self.adb.dev

    @property
    def loi(self):
        return self.apk.loi if self._dong() else self.adb.loi

    @property
    def khi_roi(self):
        return self.adb.khi_roi

    @khi_roi.setter
    def khi_roi(self, cb) -> None:
        self.adb.khi_roi = cb
        self.apk.khi_roi = cb

    def dang_ap_dung(self, yen_s: float = 2.0) -> bool:
        return self.adb.dang_ap_dung(yen_s) or self.apk.dang_ap_dung(yen_s)

    def hieu_ung_chay(self) -> bool:
        return self.adb.hieu_ung_chay() or self.apk.hieu_ung_chay()

    async def ap_dung(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int = 100) -> None:
        if self._dong():
            await self.apk.ap_dung(vung, hieu_ung, params, master)
            return
        if self.apk.hieu_ung_chay():                   # vừa rời chế độ đóng ADB: vòng hiệu ứng của APK không được tranh đèn với ADB
            await self.apk.dung()
        try:
            await self.adb.ap_dung(vung, hieu_ung, params, master)
        except LightsError:
            if not self.apk.available:
                raise
            _LOGGER.debug("đèn: ADB lỗi, dùng đường APK")
            await self.apk.ap_dung(vung, hieu_ung, params, master)

    async def tat(self) -> None:
        if not self._dong():
            try:
                await self.adb.tat()
            except LightsError:
                if not self.apk.available:
                    raise
        if self.apk.available:
            await self.apk.tat()

    async def dung(self) -> None:
        await self.apk.dung()
        if not self._dong():
            await self.adb.dung()
