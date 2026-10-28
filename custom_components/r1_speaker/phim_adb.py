"""Nhận phím nút giữa của loa qua ADB (``getevent``): không cần cài APK mới, không cần dịch vụ trợ năng.

Nguồn: ``getevent`` in sự kiện thô của nhân Linux (đo thật 28/10/2026): nút giữa là ``/dev/input/event0`` (``EV_KEY`` mã 0x00c3 = 195, giá trị 1 nhấn / 0 nhả).
→ ``Phim.tu_tho`` (HA tự nhận diện đơn/đúp/ba/giữ rồi chạy hành động người dùng chọn). Thanh trượt cảm ứng (event1) KHÔNG xử lý ở đây: nó đã chỉnh
âm lượng nhạc ngay trên loa (chủ máy xác nhận 28/10/2026), làm thêm sẽ chạy chồng.

Giữ MỘT luồng ``getevent`` mở liên tục trên kết nối ADB chung (đèn, thông tin hệ thống dùng chung nên không tranh nhau), nghĩa là adbd luôn bận với HA: máy khác
muốn ``adb connect`` phải đợi. Lỗi thì nối lại với thời gian chờ tăng dần; chế độ «đóng ADB» thì không thử."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable

from .adb_client import AdbDevice, AdbError

_LOGGER = logging.getLogger(__name__)

MA_NUT_GIUA = 195
THIET_BI_NUT = "/dev/input/event0"
EV_KEY = 0x0001
CHO_LOI_DAU_S, CHO_LOI_TOI_DA_S = 5.0, 60.0
DAI_DONG_TOI_DA = 2048

_DONG = re.compile(r"^(/dev/input/event\d+): ([0-9a-f]{4}) ([0-9a-f]{4}) ([0-9a-f]{8})$")


def phan_tich_dong(dong: str) -> tuple[str, int, int, int] | None:
    """Một dòng ``getevent`` → (thiết bị, loại, mã, giá trị); dòng lạ trả None. Giá trị có dấu 32 bit."""
    m = _DONG.match(dong.strip())
    if m is None:
        return None
    gt = int(m.group(4), 16)
    return m.group(1), int(m.group(2), 16), int(m.group(3), 16), gt - (1 << 32) if gt >= 1 << 31 else gt


class PhimAdb:
    def __init__(self, dev: AdbDevice, phim, bat: Callable[[], bool]) -> None:
        self._dev, self._phim, self._bat = dev, phim, bat
        self.dang_nghe = False

    # ── Xử lý sự kiện ──────────────────────────────────────────

    def xu_ly_dong(self, dong: str) -> None:
        ev = phan_tich_dong(dong)
        if ev is None:
            return
        tb, loai, ma, gt = ev
        if tb == THIET_BI_NUT and loai == EV_KEY and ma == MA_NUT_GIUA and gt in (0, 1):
            self._phim.tu_tho(MA_NUT_GIUA, gt == 1)

    # ── Vòng đọc ───────────────────────────────────────────────

    async def doc_luong(self, luong) -> None:
        """Đọc tới khi luồng đóng; cắt dòng theo xuống dòng, dòng quá dài bị bỏ (không phình bộ nhớ)."""
        dem = b""
        while True:
            chunk = await luong.read(4096)
            if not chunk:
                return
            dem += chunk
            *dong, dem = dem.split(b"\n")
            if len(dem) > DAI_DONG_TOI_DA:
                dem = b""
            for d in dong:
                self.xu_ly_dong(d.decode("ascii", "ignore"))

    async def chay(self) -> None:
        """Vòng nền theo mục cấu hình (``entry.async_create_background_task``)."""
        cho = CHO_LOI_DAU_S
        while True:
            if not self._bat():
                await asyncio.sleep(30)
                continue
            luong = None
            try:
                luong = await self._dev.open("shell:getevent")
                self.dang_nghe, cho = True, CHO_LOI_DAU_S
                await self.doc_luong(luong)
            except asyncio.CancelledError:
                raise
            except (AdbError, OSError, TimeoutError) as exc:
                _LOGGER.debug("nhận phím qua ADB: %s", exc or type(exc).__name__)
            finally:
                self.dang_nghe = False
                if luong is not None:
                    try:
                        await luong.close()
                    except Exception:  # noqa: BLE001 — đóng luồng hỏng không được dừng vòng nối lại
                        pass
            await asyncio.sleep(cho)
            cho = min(CHO_LOI_TOI_DA_S, cho * 2)
