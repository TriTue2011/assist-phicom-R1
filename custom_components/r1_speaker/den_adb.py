"""Sink đèn thật: chạy ``r1den.sh`` trên loa qua ADB (adb-server hoặc nối thẳng, xem ``adb_client``).

Mỗi vùng (đáy, viền) giữ tối đa MỘT phiên ADB mở khi hiệu ứng lặp đang chạy: đóng phiên thì script trên loa tự tắt
vùng đó. Hiệu ứng tĩnh (``co_dinh``, ``sang``) và ``tat`` chỉ đặt giá trị rồi script thoát, không giữ phiên.
Thay hiệu ứng cùng vùng: script mới tự dừng (kill -9) tiến trình cũ trước khi ghi, nên không bao giờ hai tiến trình
cùng ghi một vùng. Lệnh gửi đi luôn là ``sh /data/local/tmp/r1den.sh <vùng> <hiệu ứng> khoa=giatri...`` với MỌI phần
đã qua ``den_hieu_ung`` (tên trong danh mục, số trong khoảng, màu hex, giá trị chọn trong danh sách): không có đường nào
đưa chuỗi tuỳ ý vào shell của loa.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .adb_client import AdbDevice, AdbError, AdbStream
from .den_hieu_ung import EFFECTS, TAT, VUNG, doi_so
from .den_port import LightsError

_LOGGER = logging.getLogger(__name__)

SCRIPT_REMOTE = "/data/local/tmp/r1den.sh"
SCRIPT_LOCAL = Path(__file__).with_name("r1den.sh")
_AN_TOAN = re.compile(r"^[a-z_]+=[0-9a-z_]+$")


class AdbLights:
    name = "adb"

    def __init__(self, dev: AdbDevice) -> None:
        self.dev = dev
        self._streams: dict[str, AdbStream] = {}
        self._watch: dict[str, asyncio.Task] = {}
        self._khoa = {v: asyncio.Lock() for v in VUNG}
        self._script_ok = False
        self._script_ver: str | None = None
        self._dang_ap = 0                      # số lần ap_dung đang chạy (ưu tiên số 1: việc đọc thông tin nhường)
        self._xong_luc = 0.0
        #: Gọi khi một phiên đang chạy bị đứt ngoài ý muốn (loa khởi động lại, ADB rớt).
        self.khi_roi: Callable[[], None] | None = None
        self.loi: str | None = None

    @property
    def available(self) -> bool:
        return True

    def dang_ap_dung(self, yen_s: float = 2.0) -> bool:
        """Đèn đang được áp (hoặc vừa xong trong ``yen_s`` giây): việc ưu tiên thấp hơn phải chờ."""
        return self._dang_ap > 0 or time.monotonic() - self._xong_luc < yen_s

    def hieu_ung_chay(self) -> bool:
        """Có hiệu ứng LẶP đang chạy trên loa (tốn CPU của loa 4 nhân 1 GHz): việc phụ phải nhẹ và thưa."""
        return bool(self._streams)

    @property
    def ly_do(self) -> str:
        return self.loi or {"server": "ADB_QUA_SERVER", "direct": "ADB_NOI_THANG"}.get(self.dev.duong or "", "ADB_CHUA_NOI")

    # ── script trên loa ────────────────────────────────────────

    @staticmethod
    def _phien_ban(text: str) -> str | None:
        m = re.search(r"\((r1den-v\d+)\)", text)
        return m.group(1) if m else None

    async def _dam_bao_script(self) -> None:
        if self._script_ok:
            return
        data = await asyncio.get_running_loop().run_in_executor(None, SCRIPT_LOCAL.read_bytes)
        can = self._phien_ban(data.decode("utf-8", "replace"))
        co = self._phien_ban(await self.dev.shell(f"grep -m1 r1den-v {SCRIPT_REMOTE} 2>/dev/null; true"))
        if co != can:
            await self.dev.push(data, SCRIPT_REMOTE)
            _LOGGER.info("đã đẩy r1den.sh (%s) lên loa", can)
        self._script_ok = True

    # ── áp dụng ───────────────────────────────────────────────

    @staticmethod
    def _lenh(vung: str, hieu_ung: str, args: list[str]) -> str:
        if vung not in VUNG or (hieu_ung != TAT and hieu_ung not in EFFECTS[vung]):
            raise LightsError(f"hiệu ứng đèn không có: {vung}/{hieu_ung}")
        for a in args:
            if not _AN_TOAN.match(a):
                raise LightsError(f"thông số đèn không hợp lệ: {a!r}")
        return " ".join(["sh", SCRIPT_REMOTE, vung, hieu_ung, *args])

    async def ap_dung(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int = 100) -> None:
        try:
            args = [] if hieu_ung == TAT else doi_so(vung, hieu_ung, params, master=master)
        except ValueError as exc:
            raise LightsError(str(exc)) from exc
        lenh = self._lenh(vung, hieu_ung, args)
        tinh = hieu_ung == TAT or EFFECTS[vung][hieu_ung].tinh
        self._dang_ap += 1
        try:
            await self._ap_trong_khoa(vung, hieu_ung, lenh, tinh)
        finally:
            self._dang_ap -= 1
            self._xong_luc = time.monotonic()

    async def _ap_trong_khoa(self, vung: str, hieu_ung: str, lenh: str, tinh: bool) -> None:
        async with self._khoa[vung]:
            try:
                await self._dam_bao_script()
                stream = await self.dev.open(f"shell:{lenh}")
            except (AdbError, OSError, asyncio.TimeoutError) as exc:
                self._script_ok = False
                self.loi = f"ADB: {exc or type(exc).__name__}"
                raise LightsError(self.loi) from exc
            self.loi = None
            cu = self._streams.pop(vung, None)
            huy = self._watch.pop(vung, None)
            if huy is not None:
                huy.cancel()
            if tinh:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(stream.read_all(), 10)      # script tĩnh tự thoát
                with contextlib.suppress(Exception):
                    await stream.close()
            else:
                self._streams[vung] = stream
                self._watch[vung] = asyncio.get_running_loop().create_task(self._canh(vung, stream))
            if cu is not None:                                         # tiến trình cũ đã bị script mới dừng
                with contextlib.suppress(Exception):
                    await cu.close()

    async def _canh(self, vung: str, stream: AdbStream) -> None:
        """Đọc tới hết luồng: hết mà vẫn là luồng hiện tại = bị đứt ngoài ý muốn."""
        with contextlib.suppress(Exception):
            await stream.read_all()
        if self._streams.get(vung) is stream:
            self._streams.pop(vung, None)
            self._script_ok = False
            _LOGGER.debug("phiên đèn %s đứt", vung)
            if self.khi_roi is not None:
                self.khi_roi()

    async def tat(self) -> None:
        for v in VUNG:
            await self.ap_dung(v, TAT, {})

    async def dung(self) -> None:
        for v in VUNG:
            huy = self._watch.pop(v, None)
            if huy is not None:
                huy.cancel()
            s = self._streams.pop(v, None)
            if s is not None:
                with contextlib.suppress(Exception):
                    await s.close()                                    # HUP: script trên loa tự tắt vùng này
