"""Đèn bằng hiệu ứng CÓ SẴN của firmware (cách app AI box làm) — KHÔNG cần máy chủ quyền shell.

APK trên loa gọi dịch vụ hệ thống ``msgcenter.sendMsg(0x1000, ID, 0)``; ID lấy từ ``/system/etc/lights_effects.conf``
của loa. Hệ quả: chỉ có tập màu/hiệu ứng khai trong tệp đó (không có màu tuỳ ý, không chỉnh độ sáng từng chức năng):

* sáng cố định đáy: đỏ 500, xanh lá 501, xanh dương 502 (màu thử nhà máy), cam 252, tím 253, lục lam 255; tắt 504;
* viền: trắng 503, tắt 505;
* «thở» (đáy): cam 200, xanh dương 203, trắng 202, lục lam 204, đỏ 206.

Đã xác nhận bằng mắt 22/10/2026 (gửi qua APK): đèn đáy lên màu, nhưng là sáng cố định/nhịp của firmware, không phải hiệu ứng tự dựng.
Firmware chỉ chạy MỘT hiệu ứng tại một thời điểm: bật hiệu ứng mới là đóng hiệu ứng cũ (đáy và viền không sáng cùng lúc)."""

from __future__ import annotations

from dataclasses import dataclass

RIM_BAT, RIM_TAT, DAY_TAT = 503, 505, 504

#: Mọi ID mà APK chịu gửi (phải khớp ``TrungTamTin.HIEU_UNG_HOP_LE``).
ID_HOP_LE = frozenset({200, 201, 202, 203, 204, 206, 251, 252, 253, 254, 255, 500, 501, 502, 503, 504, 505,
                       510, 511, 512, 513, 514, 515})


@dataclass(frozen=True)
class MauFirmware:
    ten: str
    ten_en: str
    rgb: tuple[int, int, int]          # màu đại diện (để chọn màu gần nhất và vẽ ô chọn)
    co_dinh: int | None                # ID sáng cố định (None = không có)
    tho: int | None                    # ID «thở» (None = không có)
    da_thu: bool                       # tên màu ĐÃ xác nhận bằng mắt chưa (đỏ/lá/dương của bảng thử nhà máy: chưa)


MAU: dict[str, MauFirmware] = {m.ten_en: m for m in (
    MauFirmware("Đỏ", "red", (255, 0, 0), 500, 206, False),
    MauFirmware("Xanh lá", "green", (0, 255, 0), 501, None, False),
    MauFirmware("Xanh dương", "blue", (0, 0, 255), 502, 203, False),
    MauFirmware("Cam", "orange", (255, 140, 0), 252, 200, False),
    MauFirmware("Tím", "purple", (160, 32, 240), 253, None, False),
    MauFirmware("Lục lam", "cyan", (0, 255, 255), 255, 204, False),
    MauFirmware("Trắng", "white", (255, 255, 255), None, 202, False),
)}

#: Hiệu ứng mà firmware tự chạy bằng MỘT ID (còn lại — cầu vồng, nhịp tim, pháo hoa, chớp — chạy bằng cách HA đổi
#: liên tiếp giữa các màu của firmware, như app AI box gửi chuỗi ID kèm nghỉ ngắn; màu bị làm tròn về bảng ``MAU``).
HIEU_UNG_GOC = ("none", "tho", "nhap_nhay")
#: «Nháy» = ID 206 (đỏ, chu kỳ 0,5 giây — nhanh hơn «thở» 3,3 giây). Chỉ có màu đỏ; màu khác rơi về «thở».
ID_NHAY_DO = 206
#: Dưới ngưỡng này (kênh sáng nhất) coi là tắt đèn đáy.
NGUONG_TAT = 40


def mau_gan_nhat(rgb: tuple[int, int, int]) -> MauFirmware:
    """Màu firmware gần nhất (khoảng cách Euclid trong RGB)."""
    return min(MAU.values(), key=lambda m: sum((a - b) ** 2 for a, b in zip(rgb, m.rgb)))


def id_day(rgb: tuple[int, int, int], hieu_ung: str | bool, sang: float) -> int:
    """ID hiệu ứng đèn ĐÁY cho màu/hiệu ứng/độ sáng. ``hieu_ung``: ``none`` (sáng cố định) | ``tho`` | ``nhap_nhay``
    (bool ``True`` = ``tho``, giữ tương thích). ``sang`` 0–100: 0 hoặc màu quá tối = tắt."""
    if sang <= 0 or max(rgb) < NGUONG_TAT:
        return DAY_TAT
    m = mau_gan_nhat(rgb)
    if hieu_ung == "nhap_nhay" and m.ten_en == "red":
        return ID_NHAY_DO
    tho = hieu_ung is True or hieu_ung in ("tho", "nhap_nhay")
    if tho and m.tho is not None:
        return m.tho
    if m.co_dinh is not None:
        return m.co_dinh
    return m.tho if m.tho is not None else DAY_TAT      # trắng không có «sáng cố định» đáy: thở trắng là gần nhất


def id_vien(bat: bool, sang: float) -> int:
    return RIM_BAT if bat and sang > 0 else RIM_TAT
