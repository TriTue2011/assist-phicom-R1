"""Bản trong bộ nhớ của ``LightsSink`` (``den_port``). KHÔNG chạm loa, KHÔNG ADB.

Ghi lại, THEO THỨ TỰ, mọi lần ``ap_dung`` (vùng, hiệu ứng, thông số, độ sáng chung), ``tat`` và ``dung``."""

from __future__ import annotations

import asyncio
from typing import Any

from custom_components.r1_speaker.den_port import LightsError


class MemoryLights:
    name = "memory"
    ly_do = "memory"

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.fail: str | None = None          # đặt chuỗi → mọi lệnh ném LightsError(chuỗi)
        self.cham = False                     # True: mỗi lần ghi nhường vòng lặp (loa chậm thật)
        #: ("ap", vung, hieu_ung, params, master) | ("tat",) | ("dung",), đúng thứ tự xảy ra
        self.log: list[tuple] = []

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, value: bool) -> None:
        self._available = value

    def clear(self) -> None:
        self.log.clear()

    async def ap_dung(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int = 100) -> None:
        if self.fail:
            raise LightsError(self.fail)
        if self.cham:
            await asyncio.sleep(0)
        self.log.append(("ap", vung, hieu_ung, dict(params), master))

    async def tat(self) -> None:
        self.log.append(("tat",))

    async def dung(self) -> None:
        self.log.append(("dung",))

    @property
    def ap(self) -> list[tuple]:
        return [e for e in self.log if e[0] == "ap"]

    def cuoi(self) -> dict[str, tuple[str, dict]]:
        """Hiệu ứng áp gần nhất của từng vùng: ``{vùng: (hiệu ứng, thông số)}``."""
        ra: dict[str, tuple[str, dict]] = {}
        for _t, vung, hu, ps, _m in self.ap:
            ra[vung] = (hu, ps)
        return ra
