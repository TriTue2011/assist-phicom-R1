"""NV288 — «Loa phản hồi»: loa còn sống không, và nếu không thì đang TREO hay MẤT MẠNG.

Chủ máy mô tả (02/11/2026): thỉnh thoảng loa «rớt» — không chỉnh được âm lượng từ HA, thực thể xám, bấm nút vật lý thì đèn sáng nhưng
nút không ăn. APK không có giám sát nên không biết treo hay mất mạng. CHƯA CÓ nhật ký của một lần treo thật (nhật ký HA ngày 02/11 là do
chủ máy chủ động rút nguồn), nên mọi ngưỡng ở ``const.py`` là ĐỀ XUẤT; thay vào đó mô-đun này GHI LẠI lần cuối từng tín hiệu còn sống
(thuộc tính ``lan_cuoi``) để lần treo thật sau này có số liệu căn ngưỡng.

Hai loại tín hiệu độc lập:

* **Ứng dụng** (chứng tỏ phần mềm trên loa đang chạy): ``get_info`` đọc thành công qua cổng 8080 (vòng hỏi của coordinator), nhịp tim
  của APK (``R1Talk.alive`` — phía loa gọi ``/api/r1_speaker/ping`` chưa chắc đã có) và APK đang nối vào đầu nhận mic của HA
  (``mic_server.receiving``; phiên đó đứt khi loa tắt hẳn, nhưng một loa đơ giữa chừng có thể còn giữ kết nối TCP một lúc — nên ghi vào
  ``lan_cuoi`` để lần treo thật sau này cho biết có đáng tin hay không). Một trong ba còn tươi (≤ ``PHAN_HOI_NGUONG_IM_GIAY``) thì loa **phản hồi**.
* **Mạng** (chứng tỏ máy trên loa còn trả lời ở tầng TCP): bắt tay TCP tới cổng điều khiển 8080 và tới cổng ADB 5555 (nếu ADB chưa đóng).
  «Bị từ chối» cũng là có trả lời (máy bên kia gửi RST); chỉ quá hạn hoặc không có đường tới mới là «không thông». Chỉ thử khi mọi
  tín hiệu ứng dụng đã im — loa khoẻ thì không tốn một gói nào.

Kết luận (``ly_do``): ``phan_hoi`` · ``treo`` (mạng thông, mọi tín hiệu ứng dụng im quá ngưỡng) · ``mat_mang`` (mạng không thông) ·
``dang_khoi_dong`` (HA vừa tự gửi lệnh khởi động lại; loa cần thời gian lên lại) · ``chua_biet`` (HA mới chạy, chưa đủ thời gian để kết luận).

GIỚI HẠN thật: kernel của loa đơ hẳn (không trả lời cả TCP) trông giống hệt rút điện — cả hai là ``mat_mang``; HA không khởi động lại
được ca đó từ xa.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import const
from .settings import adb_tu_dong_dong, speaker_host, speaker_port

_LOGGER = logging.getLogger(__name__)

PHAN_HOI, TREO, MAT_MANG, DANG_KHOI_DONG, CHUA_BIET = "phan_hoi", "treo", "mat_mang", "dang_khoi_dong", "chua_biet"
#: Hai trạng thái «loa có vấn đề» (cùng một đợt mất: chỉ ghi cảnh báo MỘT lần cho cả đợt).
HONG = (TREO, MAT_MANG)

#: Tên tín hiệu trong thuộc tính ``lan_cuoi``.
TIN_HIEU = ("get_info", "apk_nhip_tim", "apk_ket_noi", "tcp_8080", "adb_5555")


async def thu_tcp(host: str, port: int, toi_da: float) -> str:
    """Bắt tay TCP: ``thong`` (nhận kết nối) · ``tu_choi`` (máy bên kia trả lời RST: máy còn sống, cổng đóng) · ``khong`` (quá hạn hoặc
    không có đường tới)."""
    try:
        async with asyncio.timeout(toi_da):
            _r, w = await asyncio.open_connection(host, port)
    except ConnectionRefusedError:
        return "tu_choi"
    except (TimeoutError, OSError):
        return "khong"
    w.close()
    with contextlib.suppress(OSError):
        await w.wait_closed()
    return "thong"


class PhanHoi:
    def __init__(self, hass: HomeAssistant, entry, coordinator, *,
                 dong_ho: Callable[[], datetime] = dt_util.utcnow,
                 thu_tcp: Callable[[str, int, float], Awaitable[str]] = thu_tcp) -> None:
        self.hass, self.entry, self._coordinator = hass, entry, coordinator
        self._dong_ho, self._thu_tcp = dong_ho, thu_tcp
        self.bat_dau = dong_ho()
        self.ly_do = CHUA_BIET
        #: Từ lúc nào loa liên tục ở trạng thái ``treo`` (None nếu không treo); tự phục hồi dựa vào mốc này.
        self.treo_tu: datetime | None = None
        self.lan_cuoi: dict[str, datetime | None] = dict.fromkeys(TIN_HIEU)
        self._khoi_dong_luc: datetime | None = None
        self._da_thay_ung_dung = False
        #: Sau lệnh khởi động lại, phiên APK cũ còn mở thêm một lúc: chỉ tính «APK đang nối» sau khi thấy nó đứt rồi nối lại.
        self._cho_apk_dut = False
        self._nguoi_nghe: list[Callable[[], None]] = []

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._nguoi_nghe.append(cb)
        return lambda: self._nguoi_nghe.remove(cb)

    def vua_khoi_dong_lai(self) -> None:
        """HA vừa gửi lệnh khởi động lại: một lúc nữa loa mất mạng rồi ứng dụng im là BÌNH THƯỜNG, không phải treo."""
        self._khoi_dong_luc = self._dong_ho()
        self._da_thay_ung_dung = False
        self._cho_apk_dut = True

    def _nho(self, ten: str, luc: datetime | None) -> None:
        if luc is not None and (self.lan_cuoi[ten] is None or luc > self.lan_cuoi[ten]):
            self.lan_cuoi[ten] = luc

    async def danh_gia(self) -> None:
        """Một lượt đánh giá (``KDL_NHIP_GIAY`` giây một lần). Ghi cảnh báo đúng MỘT lần mỗi đợt mất / có lại."""
        bay_gio = self._dong_ho()
        c = self._coordinator
        self._nho("get_info", getattr(c, "lan_doc_thanh_cong", None))
        self._nho("apk_nhip_tim", getattr(getattr(c, "talk", None), "last_alive", None))
        if getattr(getattr(c, "mic_server", None), "receiving", False):
            if not self._cho_apk_dut:
                self._nho("apk_ket_noi", bay_gio)
        else:
            self._cho_apk_dut = False
        def con_tuoi(ten: str) -> bool:
            luc = self.lan_cuoi[ten]
            if luc is None or (self._khoi_dong_luc is not None and luc <= self._khoi_dong_luc):
                return False                    # tín hiệu có TRƯỚC lệnh khởi động lại thì không chứng minh loa đã lên lại
            return (bay_gio - luc).total_seconds() <= const.PHAN_HOI_NGUONG_IM_GIAY

        song = con_tuoi("get_info") or con_tuoi("apk_nhip_tim") or con_tuoi("apk_ket_noi")
        if song:
            ly_do, self._da_thay_ung_dung, self._khoi_dong_luc = PHAN_HOI, True, None
        elif (self._khoi_dong_luc is not None
              and bay_gio - self._khoi_dong_luc < timedelta(minutes=const.PHAN_HOI_CHO_KHOI_DONG_PHUT)):
            ly_do = DANG_KHOI_DONG
        elif not self._da_thay_ung_dung and bay_gio - self.bat_dau < timedelta(seconds=const.PHAN_HOI_NGUONG_IM_GIAY):
            ly_do = CHUA_BIET               # HA mới chạy: chưa đủ thời gian để nói loa im
        else:
            ly_do = TREO if await self._mang_thong(bay_gio) else MAT_MANG
        self._doi_trang_thai(ly_do, bay_gio)
        self._bao()

    async def _mang_thong(self, bay_gio: datetime) -> bool:
        host = speaker_host(self.entry)
        ket_qua = await self._thu_tcp(host, speaker_port(self.entry), const.PHAN_HOI_TCP_TOI_DA_GIAY)
        if ket_qua in ("thong", "tu_choi"):
            self._nho("tcp_8080", bay_gio)
            return True
        dev = getattr(getattr(self._coordinator, "apps", None), "dev", None)
        if dev is not None and not adb_tu_dong_dong(self.entry) and await dev.con_nghe_mang():
            self._nho("adb_5555", bay_gio)
            return True
        return False

    def _doi_trang_thai(self, moi: str, bay_gio: datetime) -> None:
        cu = self.ly_do
        self.ly_do = moi
        self.treo_tu = (self.treo_tu or bay_gio) if moi == TREO else None
        host = speaker_host(self.entry)
        if moi in HONG and cu not in HONG:
            _LOGGER.warning("Loa R1 %s: %s. Lần cuối từng tín hiệu còn sống: %s", host,
                            "TREO (mạng còn thông nhưng ứng dụng trên loa im)" if moi == TREO else "MẤT MẠNG (loa không trả lời ở tầng TCP)",
                            self.chuoi_lan_cuoi())
        elif moi in HONG and cu != moi:
            _LOGGER.info("Loa R1 %s: đổi từ %s sang %s", host, cu, moi)
        elif moi == PHAN_HOI and cu in HONG:
            _LOGGER.warning("Loa R1 %s đã phản hồi trở lại (trước đó: %s)", host, cu)

    def chuoi_lan_cuoi(self) -> str:
        return ", ".join(f"{k}={v.isoformat(timespec='seconds') if v else 'chưa thấy'}" for k, v in self.lan_cuoi.items())

    def _bao(self) -> None:
        for cb in list(self._nguoi_nghe):
            try:
                cb()
            except Exception:  # noqa: BLE001 — thực thể hỏng không được chặn vòng đánh giá
                _LOGGER.exception("R1 phản hồi: người nghe lỗi")
