"""Bản trong bộ nhớ của ``LightsSink`` (``den_port``). KHÔNG chạm loa, KHÔNG TCP.

Ghi lại, THEO THỨ TỰ, đúng thứ ``lights_test set`` sẽ nhận (mặt nạ + 6 số hex) và các lần dừng/
chạy hiệu ứng, để test kiểm «chức năng nào ghi màu nào, mặt nạ nào, thứ tự nào». Hiệu ứng chạy
bằng ``run_steps`` với ``sleep`` giả (ghi lại thời gian từng bước, không chờ thật)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from custom_components.r1_speaker.den_port import (RGB, LightsError, Step, Write, base_write,
                                                   rim_write, run_steps)


class MemoryLights:
    name = "memory"

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.fail: str | None = None          # đặt chuỗi → mọi lệnh ném LightsError(chuỗi)
        self.cham = False                     # True: mỗi lần ghi nhường vòng lặp (loa chậm thật)
        #: ("write", Write) | ("stop",) | ("effect", steps, repeat), đúng thứ tự xảy ra
        self.log: list[tuple] = []
        self.sleeps: list[float] = []
        self._task: asyncio.Task | None = None

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, value: bool) -> None:
        self._available = value

    def _check(self) -> None:
        if self.fail:
            raise LightsError(self.fail)

    @property
    def writes(self) -> list[Write]:
        return [e[1] for e in self.log if e[0] == "write"]

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def set_rim(self, level: int) -> None:
        self._check()
        if self.cham:
            await asyncio.sleep(0)
        self.log.append(("write", rim_write(level)))

    async def set_base(self, rgb: RGB) -> None:
        self._check()
        if self.cham:
            await asyncio.sleep(0)
        self.log.append(("write", base_write(rgb)))

    async def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        await asyncio.sleep(0.001)

    async def play_effect(self, steps: Sequence[Step], *, repeat: bool) -> None:
        self._check()
        await self.stop_effect()
        self.log.append(("effect", tuple(steps), repeat))
        self._task = asyncio.create_task(run_steps(self, steps, repeat=repeat, sleep=self._sleep))

    async def stop_effect(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.log.append(("stop",))

    def clear(self) -> None:
        self.log.clear()
        self.sleeps.clear()
