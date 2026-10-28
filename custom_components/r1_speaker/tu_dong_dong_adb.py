"""Chế độ «đóng ADB» do người dùng chọn: khi APK đã nối về HA thì tự đóng ADB mạng của loa.

Vì sao: ADB mạng mở không xác thực là cửa vào cho botnet cùng mạng (chủ máy 28/10/2026, Kimwolf). Đóng được thì mic, âm lượng, phát nhạc,
Dừng/Tắt tiếng (đều đi qua APK hoặc DLNA) vẫn chạy; mất đèn tự do, cài ứng dụng, khởi động lại từ HA, thông tin hệ thống, công tắc Bluetooth
cho tới khi loa khởi động lại (rút điện cắm lại), lúc đó cổng 5555 tự mở và tích hợp đóng lại sau ``ON_DINH_S`` giây kể từ khi APK nối lại.

Cầu chì: CHỈ đóng khi APK đang nối về HA (``SERVER_NHAN``) đủ ``ON_DINH_S`` giây, nên không bao giờ tự khoá chính mình khi APK chưa cài
hay chưa nối (lúc đó còn cần ADB để cài và cấu hình). Điều kiện là TRẠNG THÁI thật, không phải danh sách tên.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .adb_client import AdbDevice, AdbError
from .mic_server import SERVER_NHAN

_LOGGER = logging.getLogger(__name__)

#: APK phải nối liên tục ngần này giây rồi mới đóng (HA khởi động lại, đang cài/cấu hình dở thì chưa đóng).
ON_DINH_S = 120.0
#: Giữa hai lần ra tay; cũng là nhịp thử lại khi loa vừa khởi động lại (ADB mở trở lại).
NGHI_GIUA_LAN_S = 600.0
CHU_KY_S = 30.0


class TuDongDongAdb:
    def __init__(self, dev: AdbDevice, mic_server, bat: Callable[[], bool], *, dong_ho: Callable[[], float] = time.monotonic) -> None:  # noqa: ANN001
        self._dev = dev
        self._mic = mic_server
        self._bat = bat
        self._now = dong_ho
        self._noi_tu: float | None = None      # từ lúc nào APK nối liên tục
        self._lan_cuoi: float | None = None

    async def kiem(self) -> str | None:
        """Một nhịp kiểm. Trả mô tả việc đã làm (để test và log), ``None`` nếu không làm gì."""
        if not self._bat() or self._mic.state != SERVER_NHAN:
            self._noi_tu = None                # tắt chế độ, hoặc APK chưa/không nối: giữ ADB mở
            return None
        now = self._now()
        if self._noi_tu is None:
            self._noi_tu = now
            return None
        if now - self._noi_tu < ON_DINH_S:
            return None
        if self._lan_cuoi is not None and now - self._lan_cuoi < NGHI_GIUA_LAN_S:
            return None
        self._lan_cuoi = now
        try:
            await self._dev.dong_adb_mang()
        except (AdbError, OSError, TimeoutError) as exc:
            if not await self._dev.con_nghe_mang():
                _LOGGER.debug("đóng ADB: cổng mạng của loa đã đóng sẵn")
                return None
            _LOGGER.warning("chế độ «đóng ADB» bật nhưng loa chưa đóng được ADB mạng: %s", exc or type(exc).__name__)
            return None
        _LOGGER.info("đã đóng ADB mạng của loa (chế độ «đóng ADB»); mở lại bằng cách rút điện loa rồi cắm lại")
        return "đã đóng"

    async def chay(self) -> None:
        """Vòng nền theo mục cấu hình (``entry.async_create_background_task``: tự huỷ khi gỡ tải)."""
        while True:
            try:
                await self.kiem()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - vòng nền không được chết; ghi một dòng rồi nhịp sau thử lại
                _LOGGER.warning("đóng ADB tự động gặp lỗi %s", type(exc).__name__)
            await asyncio.sleep(CHU_KY_S)
