"""Tự kết nối APK bodam về HA sau khi cài, KỂ CẢ khi APK được cài ngoài tích hợp (Bo Cai R1 trên máy tính, ``adb install`` tay).

Cài QUA tích hợp thì ``BoCai.cai`` đã chạy lệnh cấu hình ngay sau khi cài. Cài NGOÀI tích hợp thì APK chưa biết HA ở đâu
(APK chỉ tự xin khoá được khi đã có host HA, xem ``Ghep.java``), nên người dùng mới phải tự nhập — chủ máy 25/10/2026:
«sau khi người mới cài xong apk là tự kết nối với HA luôn».

Nguyên tắc: HA đối chiếu thay người dùng. Máy chủ nhận mic đã có khoá mà chưa có APK nối vào đủ ``CHO_NOI_S`` giây, và bodam ĐÃ
cài trên loa → chạy lại đúng lệnh cấu hình đã dùng khi cài. Lệnh này an toàn khi lặp: APK đã cấu hình thì bỏ qua phần đổi cấu hình
(chỉ mở app, nên cũng đánh thức dịch vụ đang ``stopped``). Không dùng danh sách tên gói hay chuỗi: điều kiện là TRẠNG THÁI thật
(phiên mic có hay không, gói đã cài hay chưa).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .adb_client import AdbError
from .mic_server import SERVER_NHAN, SERVER_TAT

_LOGGER = logging.getLogger(__name__)

#: Chờ ngần này giây không có APK nối vào rồi mới ra tay (loa vừa khởi động lại cần thời gian dựng dịch vụ).
CHO_NOI_S = 90.0
#: Giữa hai lần ra tay; và tối đa mỗi đợt mất kết nối (reset khi APK nối lại): không bao giờ tạo vòng lặp mở app trên loa.
NGHI_GIUA_LAN_S = 600.0
TOI_DA_LAN = 3
CHU_KY_S = 30.0
#: Sau khi HA khởi động: đợi cho ADB và các thực thể ổn định.
TRE_DAU_S = 60.0


class TuKetNoi:
    def __init__(self, bo_cai, mic_server, *, dong_ho: Callable[[], float] = time.monotonic) -> None:  # noqa: ANN001 - BoCai, R1MicServer
        self._bo_cai = bo_cai
        self._mic = mic_server
        self._now = dong_ho
        self._mat_tu: float | None = None      # từ lúc nào không có APK nối vào
        self._lan = 0
        self._lan_cuoi: float | None = None

    async def kiem(self) -> str | None:
        """Một nhịp kiểm. Trả mô tả việc đã làm (để test và log), ``None`` nếu không làm gì."""
        trang_thai = self._mic.state
        if trang_thai == SERVER_TAT:                       # chưa có khoá/cổng nghe: không có gì để nối vào
            self._mat_tu = None
            return None
        now = self._now()
        if trang_thai == SERVER_NHAN:                      # đã nối: xoá nợ, lần mất kết nối sau được thử lại từ đầu
            self._mat_tu, self._lan, self._lan_cuoi = None, 0, None
            return None
        if self._mat_tu is None:
            self._mat_tu = now
            return None
        if now - self._mat_tu < CHO_NOI_S or self._lan >= TOI_DA_LAN:
            return None
        if self._lan_cuoi is not None and now - self._lan_cuoi < NGHI_GIUA_LAN_S:
            return None
        ud = self._bo_cai.bodam()
        if ud is None:
            return None
        try:
            tt = await self._bo_cai.trang_thai(ud, moi=True)
            if not tt.cai or tt.an:                        # chưa cài (hoặc đang ẩn): chưa có gì để cấu hình
                return None
            kq = await self._bo_cai.cau_hinh_lai()
        except (AdbError, OSError, TimeoutError) as exc:   # loa/ADB chưa sẵn sàng: KHÔNG tính là một lần ra tay
            _LOGGER.debug("tự kết nối APK: ADB chưa sẵn sàng (%s)", exc or type(exc).__name__)
            return None
        self._lan += 1
        self._lan_cuoi = now
        _LOGGER.info("APK bodam đã cài nhưng chưa nối về HA %d giây: %s (lần %d/%d)",
                     int(now - self._mat_tu), kq, self._lan, TOI_DA_LAN)
        return kq

    async def chay(self) -> None:
        """Vòng nền theo mục cấu hình (``entry.async_create_background_task``: tự huỷ khi gỡ tải)."""
        await asyncio.sleep(TRE_DAU_S)
        while True:
            try:
                await self.kiem()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - vòng nền không được chết vì một nhịp lỗi
                _LOGGER.exception("tự kết nối APK: lỗi ngoài dự kiến ở một nhịp")
            await asyncio.sleep(CHU_KY_S)
