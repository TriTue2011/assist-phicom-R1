"""Hợp đồng đèn LED của loa R1 — GIAO DIỆN TRỪU TƯỢNG giữa ``den.py`` (chọn chức năng, cài đặt) và nơi thực sự ghi đèn.

Đèn của loa chỉ ghi được bằng quyền shell (``/sys/class/leds/multi_leds0/led_color``); app thường bị SELinux chặn.
Đường thật duy nhất là ADB (``den_adb.AdbLights``) chạy ``r1den.sh`` trên loa. Mặc định (chưa cấu hình) là
``NullLights``: ``den.py`` vẫn lưu cài đặt và tính chức năng đang hiệu lực nhưng không gửi gì.

Hai vùng độc lập: ``day`` (15 đèn RGB) và ``vien`` (24 đèn CHỈ TRẮNG); mỗi vùng chạy MỘT hiệu ứng tại một thời điểm.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class LightsError(Exception):
    """Sink không đặt được đèn (ADB chưa nối, loa không trả lời...)."""


@runtime_checkable
class LightsSink(Protocol):
    #: ``True`` = đã cấu hình đường tới đèn (lỗi từng lần gọi báo bằng ``LightsError``).
    available: bool
    #: Vì sao chưa dùng được (khi ``available`` False) hoặc đang dùng đường nào.
    ly_do: str

    async def ap_dung(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int = 100) -> None:
        """Chạy ``hieu_ung`` ở ``vung`` với ``params`` (đã chuẩn hoá). ``hieu_ung == "tat"`` = tắt vùng đó."""

    async def tat(self) -> None:
        """Tắt cả hai vùng."""

    async def dung(self) -> None:
        """Dừng mọi hiệu ứng đang chạy và nhả kết nối (đèn tự tắt)."""


class NullLights:
    """Chưa có đường tới đèn: không làm gì, ``available`` False."""

    available = False
    ly_do = "CHO_PHIA_LOA"

    async def ap_dung(self, vung: str, hieu_ung: str, params: dict[str, Any], master: int = 100) -> None:
        return None

    async def tat(self) -> None:
        return None

    async def dung(self) -> None:
        return None
