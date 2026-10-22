"""Sink đèn thật: lệnh đèn của HA đi qua kết nối mic đã xác thực tới APK trên loa; APK chuyển cho MÁY CHỦ ĐÈN
chạy quyền shell (``apk/nguon/den``, bật bằng ``scripts/den_loa.sh``) — SELinux không cho ứng dụng thường
ghi ``led_color``. Máy chủ đèn không tự sống sau khi loa khởi động lại (trên loa không giữ được tiến trình
quyền shell), nên ``available`` đòi cả hai: APK đang nối VÀ máy chủ đèn báo sẵn sàng; chưa sẵn sàng thì
``den.R1Lights`` lưu cài đặt rồi tự áp lại khi sẵn sàng."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from .den_port import RGB, LightsError, Step, base_write, rim_write, run_steps


class ApkLights:
    name = "apk_loa"

    def __init__(self, mic_server) -> None:
        self._server = mic_server
        self._task: asyncio.Task | None = None

    @property
    def available(self) -> bool:
        return bool(self._server.receiving and self._server.den_san_sang)

    @property
    def ly_do(self) -> str:
        """Vì sao chưa sáng: loa chưa nối (``mat_ket_noi``) hay máy chủ đèn chưa chạy."""
        return "CHO_DICH_VU_DEN" if self._server.receiving else "mat_ket_noi"

    async def _gui(self, coro) -> None:
        try:
            await coro
        except (ConnectionError, OSError, TimeoutError) as exc:
            raise LightsError(f"loa chưa nối về HA: {exc}") from exc

    async def set_rim(self, level: int) -> None:
        rim_write(level)                       # kiểm 0–255
        await self._gui(self._server.gui_den_vien(level))

    async def set_base(self, rgb: RGB) -> None:
        await self._gui(self._server.gui_den_day(base_write(rgb).rgb_hex))

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
