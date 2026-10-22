"""Sink đèn thật: lệnh đèn của HA đi qua kết nối mic đã xác thực tới APK trên loa, APK gọi hiệu ứng CÓ SẴN của firmware
(``msgcenter.sendMsg(0x1000, ID, 0)``) — cách app AI box làm, KHÔNG cần máy chủ quyền shell hay máy ngoài.

``available`` = APK đang nối VÀ APK báo ``che_do = firmware`` với ``san_sang`` (lấy được dịch vụ msgcenter). APK bản cũ
(đèn qua máy chủ shell) không báo ``che_do`` nên coi là chưa sẵn sàng thay vì gửi vào hư không."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from . import den_firmware as fw
from .den_port import RGB, LightsError, Step, run_steps


class ApkLights:
    name = "apk_firmware"
    firmware = True
    #: Hiệu ứng firmware tự chạy bằng một ID; các hiệu ứng khác chạy bằng chuỗi ID (``play_effect``).
    hieu_ung_goc = fw.HIEU_UNG_GOC
    hieu_ung_ho_tro = None            # None = mọi hiệu ứng của tích hợp (màu làm tròn về bảng của firmware)

    def __init__(self, mic_server) -> None:
        self._server = mic_server
        self._task: asyncio.Task | None = None
        self._cuoi: dict[str, int | None] = {"day": None, "rim": None}

    @property
    def available(self) -> bool:
        return bool(self._server.receiving and self._server.den_san_sang)

    @property
    def ly_do(self) -> str:
        """Vì sao chưa sáng: loa chưa nối (``mat_ket_noi``) hay APK chưa hỗ trợ đèn firmware (``CHO_DICH_VU_DEN``)."""
        return "CHO_DICH_VU_DEN" if self._server.receiving else "mat_ket_noi"

    async def _gui(self, coro) -> None:
        try:
            await coro
        except (ConnectionError, OSError, TimeoutError) as exc:
            raise LightsError(f"loa chưa nối về HA: {exc}") from exc

    async def _dat(self, o: str, ma: int, *, ep: bool = False) -> None:
        """Gửi ID cho ô ``day``/``rim`` — bỏ qua nếu ô đó đang đúng ID rồi (hiệu ứng chuỗi không dội lệnh thừa)."""
        if not ep and self._cuoi[o] == ma:
            return
        await self._gui(self._server.gui_hieu_ung(ma))
        self._cuoi[o] = ma

    async def ap_dung_ham(self, *, rim: bool, color: RGB, effect: str, sang: float) -> None:
        """Áp MỘT chức năng đèn bằng hiệu ứng gốc: đáy (màu + sáng cố định/thở/nháy) rồi viền (trắng)."""
        await self._dat("day", fw.id_day(color, effect, sang), ep=True)
        await self._dat("rim", fw.id_vien(rim, sang), ep=True)

    async def tat(self) -> None:
        await self._dat("day", fw.DAY_TAT, ep=True)
        await self._dat("rim", fw.RIM_TAT, ep=True)

    # Giao diện LightsSink gốc: viền theo mức trắng, đáy theo RGB (làm tròn về màu gần nhất của firmware).
    async def set_rim(self, level: int) -> None:
        await self._dat("rim", fw.id_vien(level > 0, level))

    async def set_base(self, rgb: RGB) -> None:
        await self._dat("day", fw.id_day(rgb, "none", 100 if max(rgb) else 0))

    async def play_effect(self, steps: Sequence[Step], *, repeat: bool) -> None:
        await self.stop_effect()
        self._task = asyncio.get_running_loop().create_task(self._chay(steps, repeat))

    async def _chay(self, steps: Sequence[Step], repeat: bool) -> None:
        try:
            await run_steps(self, steps, repeat=repeat)
        except LightsError:
            pass                                # mất kết nối giữa hiệu ứng: dừng, lần áp sau sẽ chạy lại

    async def stop_effect(self) -> None:
        t, self._task = self._task, None
        if t is not None and not t.done():
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
