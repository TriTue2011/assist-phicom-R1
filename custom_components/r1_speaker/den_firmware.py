"""Đèn bằng hiệu ứng CÓ SẴN của firmware (cách app AI box làm): APK trên loa gọi ``msgcenter.sendMsg(0x1000, ID, 0)``,
ID lấy từ ``/system/etc/lights_effects.conf`` của loa. Không cần ADB, không cần quyền shell.

Hệ quả (đo 28/10/2026 từ chính tệp cấu hình của loa): chỉ có tập màu/hiệu ứng khai trong tệp đó, KHÔNG có màu tuỳ ý, tốc độ hay độ sáng
từng chức năng; firmware chỉ chạy MỘT hiệu ứng tại một thời điểm nên đáy và viền không sáng cùng lúc.

* đáy sáng cố định: đỏ 500, xanh lá 501, xanh dương 502, cam 252, tím 253, lục lam 255; tắt 504;
* đáy «thở» (firmware tự lặp): cam 200, xanh dương 203, trắng 202, lục lam 204, đỏ 206;
* viền: trắng 503, tắt 505, chạy đuổi 1 (firmware tự lặp).

Mọi ID gửi đi phải nằm trong ``ID_HOP_LE``, khớp danh sách APK chịu gửi (``TrungTamTin.HIEU_UNG_HOP_LE``, có test canh)."""

from __future__ import annotations

from dataclasses import dataclass

DAY_TAT, RIM_BAT, RIM_TAT, ID_CHAY_DUOI = 504, 503, 505, 1

#: Mọi ID mà APK chịu gửi (phải khớp ``TrungTamTin.HIEU_UNG_HOP_LE``).
ID_HOP_LE = frozenset({200, 201, 202, 203, 204, 206, 251, 252, 253, 254, 255, 500, 501, 502, 503, 504, 505,
                       510, 511, 512, 513, 514, 515} | set(range(1, 25)))

#: Dưới ngưỡng này (kênh sáng nhất) coi là tắt đèn đáy.
NGUONG_TAT = 40


@dataclass(frozen=True)
class MauFirmware:
    ten_en: str
    rgb: tuple[int, int, int]          # màu đại diện (để chọn màu gần nhất)
    co_dinh: int | None                # ID sáng cố định (None = không có)
    tho: int | None                    # ID «thở» (None = không có)


MAU: dict[str, MauFirmware] = {m.ten_en: m for m in (
    MauFirmware("red", (255, 0, 0), 500, 206),
    MauFirmware("green", (0, 255, 0), 501, None),
    MauFirmware("blue", (0, 0, 255), 502, 203),
    MauFirmware("orange", (255, 140, 0), 252, 200),
    MauFirmware("purple", (160, 32, 240), 253, None),
    MauFirmware("cyan", (0, 255, 255), 255, 204),
    MauFirmware("white", (255, 255, 255), None, 202),
)}

#: Sáu màu sáng cố định theo thứ tự cầu vồng; hiệu ứng «cầu vồng», «sao chổi»… chạy bằng cách đổi lần lượt các màu này.
CAU_VONG = (500, 252, 501, 255, 502, 253)


def mau_gan_nhat(rgb: tuple[int, int, int]) -> MauFirmware:
    """Màu firmware gần nhất (khoảng cách Euclid trong RGB)."""
    return min(MAU.values(), key=lambda m: sum((a - b) ** 2 for a, b in zip(rgb, m.rgb)))


def rgb_tu_hex(mau: str) -> tuple[int, int, int]:
    mau = mau.lstrip("#")
    return int(mau[0:2], 16), int(mau[2:4], 16), int(mau[4:6], 16)


def id_day(rgb: tuple[int, int, int], tho: bool, sang: float) -> int:
    """ID đáy cho màu: ``tho`` thì ID thở nếu màu có, không thì sáng cố định. ``sang`` 0–100: 0 hoặc màu quá tối = tắt."""
    if sang <= 0 or max(rgb) < NGUONG_TAT:
        return DAY_TAT
    m = mau_gan_nhat(rgb)
    if tho and m.tho is not None:
        return m.tho
    if m.co_dinh is not None:
        return m.co_dinh
    return m.tho if m.tho is not None else DAY_TAT      # trắng không có «sáng cố định» đáy: thở trắng là gần nhất
