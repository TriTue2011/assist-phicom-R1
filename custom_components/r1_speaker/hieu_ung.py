"""Danh mục hiệu ứng đèn cho loa R1 — hiệu ứng là DỮ LIỆU: danh sách ``Step`` (màu đáy, mức viền,
thời gian), không phải ID hiệu ứng của firmware (``lights_test set`` không áp dụng được chúng).

Chọn theo tên/mô tả của danh mục hiệu ứng WLED (https://kno.wled.ge/features/effects/, đọc
22/10/2026; chỉ đọc tên + mô tả, KHÔNG lấy mã): sáu hiệu ứng chỉ cần «đổi màu đáy theo thời gian
+ bật/tắt viền trắng». Các hiệu ứng làm bằng cách di chuyển điểm sáng dọc vòng đèn (Chase, Scan,
Wipe, Ripple…) bị BỎ: cần ghi từng LED, mà chưa biết các bit của mặt nạ có địa chỉ riêng từng LED
hay không (mới thấy ``7fff`` = cả đèn đáy, ``7fffff8000`` = cả viền).

Đèn viền chỉ có trắng nên ở mọi hiệu ứng nó chỉ bật/tắt hoặc đổi mức sáng, không đổi màu; khi
cài đặt không dùng viền thì mọi bước giữ viền = 0.

Số thời gian trong từng hiệu ứng là ĐỀ XUẤT, CHƯA ĐO trên loa (tốc độ đổi đèn thật tối đa của
``lights_test`` chưa biết).
"""

from __future__ import annotations

import colorsys
import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from .den_port import LEVEL_MAX, RGB, Step

KHONG = "none"
NGUON_WLED = "https://kno.wled.ge/features/effects/"


@dataclass(frozen=True)
class Ctx:
    accent: RGB          # màu đáy của chức năng
    pct: int             # độ sáng 0–100
    use_rim: bool        # chức năng có dùng viền không
    rng: random.Random   # chỉ pháo hoa dùng; truyền seed vào để test xác định được


def sang_rgb(rgb: RGB, pct: float) -> RGB:
    """Nhân từng kênh với ``pct``/100 (giả định: chưa đo phần cứng có tuyến tính không)."""
    pct = min(max(pct, 0.0), 100.0)
    return (round(rgb[0] * pct / 100), round(rgb[1] * pct / 100), round(rgb[2] * pct / 100))


def sang_vien(pct: float) -> int:
    pct = min(max(pct, 0.0), 100.0)
    return round(LEVEL_MAX * pct / 100)


def _b(c: Ctx, f: float, giay: float, mau: RGB | None = None, vien: float | None = None) -> Step:
    """Bước ở hệ số sáng ``f`` (0–1) của độ sáng đã cài; viền theo ``f`` trừ khi nêu ``vien``."""
    vf = f if vien is None else vien
    return Step(base=sang_rgb(mau or c.accent, c.pct * f),
                rim=sang_vien(c.pct * vf) if c.use_rim else 0, seconds=giay)


def _tinh_gon(steps: list[Step]) -> list[Step]:
    """Bỏ giá trị lặp liên tiếp (viền không dùng chỉ ghi 0 một lần) để bớt lệnh gửi loa."""
    ra, rim, base = [], None, None
    for s in steps:
        r = None if s.rim == rim and ra else s.rim
        b = None if s.base == base and ra else s.base
        rim = s.rim if s.rim is not None else rim
        base = s.base if s.base is not None else base
        ra.append(Step(base=b, rim=r, seconds=s.seconds))
    return ra


def _tho(c: Ctx) -> list[Step]:
    n = 8   # chu kỳ 8 × 0,25 s = 2 s, sáng dần rồi tối dần theo nửa chu kỳ cos
    return [_b(c, round(0.5 - 0.5 * math.cos(2 * math.pi * k / n), 3), 0.25) for k in range(n)]


def _cau_vong(c: Ctx) -> list[Step]:
    # 12 sắc độ đều nhau; ĐỎ và mọi màu pha CHƯA xác nhận trên đèn đáy. Màu cố định, không dùng
    # màu của chức năng. Viền giữ mờ cố định (không đổi màu được).
    return [Step(base=sang_rgb(tuple(round(x * 255) for x in colorsys.hsv_to_rgb(k / 12, 1, 1)),
                               c.pct),
                 rim=sang_vien(c.pct * 0.4) if c.use_rim else 0, seconds=0.4) for k in range(12)]


def _nhap_nhay(c: Ctx) -> list[Step]:
    return [_b(c, 1.0, 0.5), _b(c, 0.0, 0.5)]


def _nhip_tim(c: Ctx) -> list[Step]:
    # «thình – thịch» rồi nghỉ; chu kỳ ≈ 1 s.
    return [_b(c, 1.0, 0.12), _b(c, 0.15, 0.10), _b(c, 0.75, 0.12), _b(c, 0.0, 0.66)]


#: Màu pháo hoa; chỉ xanh lá và xanh dương đã xác nhận trên đèn đáy, ba màu sau chưa.
_PALETA_PHAO = ((0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255))


def _phao_hoa(c: Ctx) -> list[Step]:
    # WLED «Fireworks: Random color blobs light up, then fade again». 6 chùm: bừng → mờ dần →
    # tắt, nghỉ ngẫu nhiên (theo ``rng``). Mỗi lần dựng lại ra một dãy chùm khác (nếu rng khác).
    ra: list[Step] = []
    for _ in range(6):
        mau = c.rng.choice(_PALETA_PHAO)
        ra += [_b(c, 1.0, 0.08, mau), _b(c, 0.45, 0.10, mau), _b(c, 0.15, 0.10, mau),
               _b(c, 0.0, round(c.rng.uniform(0.25, 0.7), 2))]
    return ra


def _chop(c: Ctx) -> list[Step]:
    # WLED «Strobe Mega»: nhiều chớp rất ngắn rồi nghỉ. Tốc độ chớp có đạt được hay không CHƯA ĐO.
    on, off = _b(c, 1.0, 0.06), _b(c, 0.0, 0.20)
    return [on, off, on, off, on, _b(c, 0.0, 0.8)]


@dataclass(frozen=True)
class HieuUng:
    id: str
    ten: str                 # tiếng Việt
    ten_en: str
    mo_ta: str
    nguon: str               # URL nguồn ý tưởng (chỉ đọc, không tải mã)
    wled: str                # tên + ID trong danh mục WLED
    vien: str                # viền làm gì trong hiệu ứng này
    lap: bool
    tao: Callable[[Ctx], list[Step]]


HIEU_UNG: dict[str, HieuUng] = {h.id: h for h in (
    HieuUng("tho", "Thở", "Breathe", "Đèn sáng dần rồi tối dần, chu kỳ 2 giây.", NGUON_WLED,
            "Breathe (2): fades between primary and secondary color", "sáng tối theo đáy", True, _tho),
    HieuUng("cau_vong", "Cầu vồng", "Rainbow", "Đèn đáy đi hết 12 sắc độ, 0,4 giây một sắc.",
            NGUON_WLED, "Colorloop (8): cycle all LEDs through the rainbow colors",
            "mờ cố định", True, _cau_vong),
    HieuUng("nhap_nhay", "Nhấp nháy", "Blink", "Bật 0,5 giây, tắt 0,5 giây.", NGUON_WLED,
            "Blink (1): blinks between primary and secondary color", "nháy cùng đáy", True,
            _nhap_nhay),
    HieuUng("nhip_tim", "Nhịp tim", "Heartbeat", "Hai nhịp mạnh – yếu rồi nghỉ, chu kỳ khoảng 1 giây.",
            NGUON_WLED, "Heartbeat (100): pulsing rhythm similar to a heart beat",
            "đập cùng đáy", True, _nhip_tim),
    HieuUng("phao_hoa", "Pháo hoa nhỏ", "Fireworks", "Sáu chùm màu ngẫu nhiên bừng lên rồi tắt dần.",
            NGUON_WLED, "Fireworks (42): random color blobs light up, then fade again",
            "bừng cùng đáy", True, _phao_hoa),
    HieuUng("chop", "Chớp", "Strobe", "Ba chớp rất ngắn rồi nghỉ gần một giây.", NGUON_WLED,
            "Strobe Mega (25): several short flash bursts", "chớp cùng đáy", True, _chop),
)}


def dung(effect_id: str, accent: RGB, pct: int, use_rim: bool,
         rng: random.Random | None = None) -> list[Step]:
    """Dựng các bước của hiệu ứng ``effect_id`` cho màu ``accent`` ở độ sáng ``pct`` (0–100).
    ``rng`` chỉ pháo hoa dùng; bỏ trống thì mỗi lần một dãy mới (ngẫu nhiên không cần mật mã)."""
    h = HIEU_UNG[effect_id]
    # Ngẫu nhiên chỉ để trang trí đèn, không dùng cho bảo mật.
    ctx = Ctx(accent, pct, use_rim, rng or random.Random())  # nosec B311
    return _tinh_gon(h.tao(ctx))
