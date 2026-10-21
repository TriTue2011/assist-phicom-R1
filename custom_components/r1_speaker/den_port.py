"""Hợp đồng đèn LED của loa R1 — GIAO DIỆN TRỪU TƯỢNG, không gắn với phần cứng.

Từ HA tới đèn loa **chưa có đường nào**: lệnh duy nhất đã chạy được là
``/system/bin/lights_test set <mặt nạ> <rgb 6 số>`` và nó chỉ chạy được TRÊN LOA (shell hoặc
một dịch vụ trên loa; dịch vụ đó CHƯA được duyệt, CHƯA có). Nên mọi mã phía HA (``den.py``) chỉ
nói chuyện với ``LightsSink`` ở đây, giống cách ``audio_port.py`` che đường mic/phát; chỗ cắm
thật sau này chỉ cần thoả giao diện, không sửa phần còn lại. Bản mặc định là ``NullLights``
(``available = False``): HA lưu cài đặt, tính ra đèn nào cần sáng, nhưng KHÔNG gửi gì đi đâu.

Phần cứng ĐÃ KIỂM (chủ máy xác nhận bằng mắt):

* **Đèn viền** — mặt nạ ``7fffff8000``, CHỈ TRẮNG: bật ``ffffff``, tắt ``000000``, chỉnh sáng bằng
  giá trị trắng (``404040`` mờ rõ). Vì thế ``set_rim`` chỉ nhận MỨC 0–255, không có tham số màu:
  luật «viền chỉ trắng» do chữ ký hàm bảo đảm. Hiệu ứng thở ID 202 của firmware KHÔNG chạy.
* **Đèn đáy** — mặt nạ ``7fff``, RGB. Xanh lá ``00ff00`` và xanh dương ``0000ff`` đã xác nhận.
  Đỏ ``ff0000`` CHƯA CHẮC (chưa phân biệt được với mặt nạ). Mọi màu pha (vàng, tím, lục lam…)
  và việc «nhân RGB để chỉnh sáng» là GIẢ ĐỊNH chưa đo.
* ``/system/etc/lights_effects.conf`` có danh mục hiệu ứng của firmware (ID 200–255, 300–315,
  400–412) nhưng ``lights_test set`` không áp dụng được ID hiệu ứng từ shell → hiệu ứng ở đây là
  DỮ LIỆU (danh sách bước màu + thời gian) do sink chạy, không phải ID của firmware.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Đường dẫn lệnh TRÊN LOA — chỉ để tài liệu/lệnh mẫu; HA không chạy nó.
LIGHTS_TEST = "/system/bin/lights_test"
RIM_MASK = "7fffff8000"
BASE_MASK = "7fff"
LEVEL_MAX = 255
#: Bước ngắn nhất ``run_steps`` chịu giữ (giây). CHƯA ĐO: mỗi lần ``lights_test`` là một tiến trình
#: riêng nên tốc độ đổi tối đa thật có thể chậm hơn nhiều.
MIN_STEP_S = 0.05

RGB = tuple[int, int, int]


class LightsError(Exception):
    """Sink không đặt được đèn (chưa có dịch vụ trên loa, mất kết nối…)."""


@dataclass(frozen=True)
class Step:
    """Một bước của hiệu ứng: đặt rồi giữ ``seconds`` giây. ``None`` = giữ nguyên giá trị cũ.

    ``rim`` là MỨC trắng 0–255 (viền chỉ trắng); ``base`` là RGB của đèn đáy."""

    base: RGB | None = None
    rim: int | None = None
    seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.base is not None and (len(self.base) != 3 or
                                      any(not 0 <= c <= LEVEL_MAX for c in self.base)):
            raise ValueError(f"màu đèn đáy ngoài 0–255: {self.base}")
        if self.rim is not None and not 0 <= self.rim <= LEVEL_MAX:
            raise ValueError(f"mức đèn viền ngoài 0–255: {self.rim}")
        if self.seconds < 0:
            raise ValueError("thời gian bước âm")


@dataclass(frozen=True)
class Write:
    """Đúng thứ ``lights_test set`` nhận: mặt nạ + 6 số hex."""

    mask: str
    rgb_hex: str

    @property
    def command(self) -> str:
        return f"set {self.mask} {self.rgb_hex}"


def rim_write(level: int) -> Write:
    """Đèn viền: ``level`` 0 (tắt) – 255 (sáng nhất), luôn là xám/trắng ``LLLLLL``."""
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= LEVEL_MAX:
        raise ValueError(f"mức đèn viền phải là số nguyên 0–255, nhận {level!r}")
    return Write(RIM_MASK, f"{level:02x}" * 3)


def base_write(rgb: RGB) -> Write:
    """Đèn đáy: RGB 0–255 mỗi kênh."""
    if len(rgb) != 3 or any(not isinstance(c, int) or not 0 <= c <= LEVEL_MAX for c in rgb):
        raise ValueError(f"màu đèn đáy phải là 3 số nguyên 0–255, nhận {rgb!r}")
    return Write(BASE_MASK, "".join(f"{c:02x}" for c in rgb))


@runtime_checkable
class LightsSink(Protocol):
    """Đích đèn của loa. Mọi lệnh ném ``LightsError`` khi không đặt được.

    ``play_effect`` trả về NGAY (sink tự chạy các bước nền, nên bản trên loa có thể chạy vòng lặp
    tại chỗ thay vì HA gửi từng bước qua mạng); ``stop_effect`` dừng nó. Bên gọi (``den.R1Lights``)
    LUÔN gọi ``stop_effect`` trước khi ghi đèn theo cách khác, để không có hai nơi cùng ghi."""

    name: str

    @property
    def available(self) -> bool: ...

    async def set_rim(self, level: int) -> None: ...
    async def set_base(self, rgb: RGB) -> None: ...
    async def play_effect(self, steps: Sequence[Step], *, repeat: bool) -> None: ...
    async def stop_effect(self) -> None: ...


class _BasicSink(Protocol):
    async def set_rim(self, level: int) -> None: ...
    async def set_base(self, rgb: RGB) -> None: ...


async def run_steps(sink: _BasicSink, steps: Sequence[Step], *, repeat: bool,
                    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
    """Chạy ``steps`` đúng thứ tự: đặt viền (nếu có), đặt đáy (nếu có), giữ ``seconds``. Dành cho
    sink không có bộ chạy riêng. ``repeat`` lặp mãi tới khi bị huỷ. Giữ tối thiểu ``MIN_STEP_S``
    mỗi bước để vòng lặp không bao giờ chiếm CPU."""
    if not steps:
        return
    while True:
        for st in steps:
            if st.rim is not None:
                await sink.set_rim(st.rim)
            if st.base is not None:
                await sink.set_base(st.base)
            await sleep(max(st.seconds, MIN_STEP_S))
        if not repeat:
            return


class NullLights:
    """Sink mặc định: CHƯA có dịch vụ đèn trên loa. ``available`` luôn False; ghi vào là lỗi."""

    name = "CHO_PHIA_LOA"

    @property
    def available(self) -> bool:
        return False

    async def set_rim(self, level: int) -> None:
        raise LightsError("chưa có dịch vụ đèn trên loa")

    async def set_base(self, rgb: RGB) -> None:
        raise LightsError("chưa có dịch vụ đèn trên loa")

    async def play_effect(self, steps: Sequence[Step], *, repeat: bool) -> None:
        raise LightsError("chưa có dịch vụ đèn trên loa")

    async def stop_effect(self) -> None:
        return None
