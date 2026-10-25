"""Khai báo MỘT NGUỒN DỮ LIỆU cho hiệu ứng đèn R1: mỗi vùng (đáy, viền) có danh sách hiệu ứng, mỗi hiệu ứng có
danh sách thông số RIÊNG (số lượng khác nhau). Thẻ cài đặt vẽ form từ chính danh sách này; ``r1den.sh`` trên loa
nhận đúng các khoá này dạng ``khoa=gia_tri``. Thêm hiệu ứng hay thông số = thêm dữ liệu ở đây, không sửa giao diện.

Vùng ``day``: 15 đèn RGB. Vùng ``vien``: 24 đèn CHỈ TRẮNG (không có thông số màu).
Mọi hiệu ứng chạy NGAY TRÊN LOA (``r1den.sh``); HA chỉ gửi tên hiệu ứng + các số đã kiểm khoảng giá trị.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

VUNG_DAY, VUNG_VIEN = "day", "vien"
VUNG = (VUNG_DAY, VUNG_VIEN)
TAT = "tat"

_MAU = re.compile(r"^#?([0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class Opt:
    value: str
    vi: str
    en: str


@dataclass(frozen=True)
class Param:
    """Một thông số. ``kind``: ``range`` (số nguyên trong [min, max]), ``color`` (#rrggbb) hoặc ``select``."""

    key: str
    kind: str
    vi: str
    en: str
    default: Any
    min: int = 0
    max: int = 0
    step: int = 1
    unit: str = ""
    options: tuple[Opt, ...] = ()
    #: Chỉ hiện (và chỉ gửi) khi thông số khác có giá trị này, ví dụ ``("kieu_mau", "don_sac")``.
    chi_khi: tuple[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"key": self.key, "kind": self.kind, "vi": self.vi, "en": self.en, "default": self.default}
        if self.kind == "range":
            d.update(min=self.min, max=self.max, step=self.step, unit=self.unit)
        if self.kind == "select":
            d["options"] = [{"value": o.value, "vi": o.vi, "en": o.en} for o in self.options]
        if self.chi_khi:
            d["chi_khi"] = {"key": self.chi_khi[0], "value": self.chi_khi[1]}
        return d


@dataclass(frozen=True)
class Effect:
    id: str
    vi: str
    en: str
    params: tuple[Param, ...]
    #: Hiệu ứng tĩnh: script đặt giá trị rồi thoát (không cần giữ phiên ADB mở).
    tinh: bool = False
    mo_ta: str = ""
    by_key: dict[str, Param] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_key", {p.key: p for p in self.params})

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "vi": self.vi, "en": self.en, "tinh": self.tinh, "mo_ta": self.mo_ta,
                "params": [p.to_dict() for p in self.params]}


def _sang() -> Param:
    return Param("do_sang", "range", "Độ sáng", "Brightness", 100, 0, 100, 1, "%")


def _toc_do() -> Param:
    return Param("toc_do", "range", "Tốc độ", "Speed", 100, 25, 400, 5, "%")


def _mau(default: str = "#ffffff", chi_khi: tuple[str, str] | None = None) -> Param:
    return Param("mau", "color", "Màu", "Colour", default, chi_khi=chi_khi)


def _chieu() -> Param:
    return Param("chieu", "select", "Chiều", "Direction", "xuoi",
                 options=(Opt("xuoi", "Xuôi", "Forward"), Opt("nguoc", "Ngược", "Reverse")))


def _bao_hoa() -> Param:
    return Param("bao_hoa", "range", "Độ bão hoà màu", "Saturation", 100, 30, 100, 5, "%")


def _do_sau() -> Param:
    return Param("do_sau", "range", "Độ sâu (mức tối thấp nhất)", "Depth (lowest level)", 0, 0, 80, 5, "%")


_DAY = (
    Effect("co_dinh", "Sáng cố định", "Steady", (_mau("#00ff00"), _sang()), tinh=True,
           mo_ta="Một màu sáng liên tục."),
    Effect("tho", "Thở", "Breathe", (_mau("#0000ff"), _sang(), _toc_do(), _do_sau()),
           mo_ta="Sáng dần rồi tối dần, chu kỳ 2 giây ở tốc độ 100%."),
    Effect("nhap_nhay", "Nhấp nháy", "Blink",
           (_mau("#00ff00"), _sang(), _toc_do(),
            Param("ty_le_bat", "range", "Tỷ lệ thời gian bật", "On time share", 50, 10, 90, 5, "%")),
           mo_ta="Bật rồi tắt, chu kỳ 1 giây ở tốc độ 100%."),
    Effect("nhip_tim", "Nhịp tim", "Heartbeat",
           (_mau("#ff0000"), _sang(), _toc_do(),
            Param("nghi_ms", "range", "Nghỉ giữa các nhịp", "Rest between beats", 660, 200, 2000, 20, "ms")),
           mo_ta="Hai nhịp mạnh, yếu rồi nghỉ."),
    Effect("chop", "Chớp", "Strobe",
           (_mau("#ffffff"), _sang(), _toc_do(),
            Param("so_chop", "range", "Số chớp mỗi lượt", "Flashes per burst", 3, 1, 6, 1),
            Param("nghi_ms", "range", "Nghỉ giữa các lượt", "Rest between bursts", 800, 300, 3000, 100, "ms")),
           mo_ta="Vài chớp rất ngắn rồi nghỉ."),
    Effect("phao_hoa", "Pháo hoa nhỏ", "Fireworks",
           (_sang(), _toc_do(),
            Param("bang_mau", "select", "Bảng màu", "Palette", "nhieu_mau",
                  options=(Opt("nhieu_mau", "Nhiều màu", "Multicolour"), Opt("am", "Tông ấm", "Warm"),
                           Opt("lanh", "Tông lạnh", "Cool"))),
            Param("nghi_ms", "range", "Nghỉ giữa các chùm", "Rest between bursts", 450, 100, 2000, 50, "ms")),
           mo_ta="Chùm màu ngẫu nhiên bừng lên rồi tắt dần."),
    Effect("cau_vong", "Cầu vồng 12 sắc", "Rainbow (12 hues)", (_sang(), _toc_do(), _bao_hoa(), _chieu()),
           mo_ta="Cả vòng đáy đổi 12 sắc độ, mỗi sắc 0,4 giây ở tốc độ 100%."),
    Effect("cau_vong_fw", "Cầu vồng 6 màu", "Rainbow (6 colours)", (_sang(), _toc_do(), _chieu()),
           mo_ta="Đổi lần lượt đỏ, cam, xanh lá, xanh dương, tím, lục lam."),
    Effect("cau_vong_xoay", "Cầu vồng xoay", "Rotating rainbow",
           (_sang(), _toc_do(), _chieu(), _bao_hoa(),
            Param("kieu_dai", "select", "Kiểu dải", "Band style", "ca_vong",
                  options=(Opt("ca_vong", "Cả vòng 15 màu", "Full ring, 15 colours"),
                           Opt("dai_ngan", "Dải ngắn chạy quanh", "Short bands running around"))),
            Param("so_dai", "range", "Số dải", "Number of bands", 1, 1, 5, 1),
            Param("do_rong", "range", "Độ rộng mỗi dải", "Band width", 5, 3, 8, 1, " đèn", chi_khi=("kieu_dai", "dai_ngan"))),
           mo_ta="Cả vòng: mỗi đèn một màu, xoay vòng, số dải là số vòng cầu vồng lặp lại. Dải ngắn: vài dải cầu vồng chạy quanh đáy, đèn còn lại tối."),
    Effect("sao_choi", "Sao chổi", "Comet",
           (_sang(), _toc_do(), _chieu(),
            Param("dai_duoi", "range", "Độ dài đuôi", "Tail length", 5, 2, 8, 1, " đèn"),
            Param("so_choi", "range", "Số sao chổi chạy cùng lúc", "Comets at once", 1, 1, 4, 1),
            Param("kieu_mau", "select", "Kiểu màu", "Colour mode", "nhieu_mau",
                  options=(Opt("nhieu_mau", "Nhiều màu (đỏ đến tím)", "Multicolour (red to violet)"),
                           Opt("don_sac", "Đơn sắc", "Single colour"))),
            _mau("#00ffff", chi_khi=("kieu_mau", "don_sac"))),
           mo_ta="Đầu sáng nhất, đuôi tối dần chạy quanh đáy; nhiều sao chổi thì cách đều nhau."),
)

_VIEN = (
    Effect("sang", "Sáng liên tục", "Steady", (_sang(),), tinh=True, mo_ta="Viền trắng sáng liên tục."),
    Effect("chay_duoi", "Chạy đuổi", "Chase",
           (_sang(), _toc_do(), _chieu(),
            Param("dai_duoi", "range", "Độ dài đuôi", "Tail length", 4, 1, 10, 1, " đèn")),
           mo_ta="Điểm sáng có đuôi mờ chạy quanh 24 đèn viền."),
    Effect("tho", "Thở", "Breathe", (_sang(), _toc_do(), _do_sau()),
           mo_ta="Cả viền sáng dần rồi tối dần."),
)

EFFECTS: dict[str, dict[str, Effect]] = {
    VUNG_DAY: {e.id: e for e in _DAY},
    VUNG_VIEN: {e.id: e for e in _VIEN},
}


def danh_muc() -> dict[str, list[dict[str, Any]]]:
    """Toàn bộ danh mục cho thẻ cài đặt (thứ tự cố định)."""
    return {v: [e.to_dict() for e in EFFECTS[v].values()] for v in VUNG}


def chuan_mau(value: Any) -> str | None:
    m = _MAU.match(str(value or "").strip())
    return f"#{m.group(1).lower()}" if m else None


def _kep(p: Param, value: Any) -> Any:
    """Giá trị hợp lệ của thông số; sai kiểu hoặc ngoài khoảng thì rơi về mặc định, trong khoảng thì kẹp."""
    if p.kind == "range":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return p.default
        return max(p.min, min(p.max, int(round(value))))
    if p.kind == "color":
        return chuan_mau(value) or p.default
    return value if value in {o.value for o in p.options} else p.default


def loc_hop_le(vung: str, hieu_ung: str, params: Any) -> dict[str, Any]:
    """Chỉ giữ các thông số ĐÚNG KIỂU (số cho ``range``, #rrggbb cho ``color``, giá trị có trong danh sách cho
    ``select``). Dùng khi trộn vào thông số đang có: giá trị hỏng không được thay giá trị tốt hiện có."""
    eff = EFFECTS.get(vung, {}).get(hieu_ung)
    if eff is None or not isinstance(params, dict):
        return {}
    ra = {}
    for k, v in params.items():
        p = eff.by_key.get(k)
        if p is None:
            continue
        if p.kind == "range" and not isinstance(v, bool) and isinstance(v, (int, float)):
            ra[k] = v
        elif p.kind == "color" and chuan_mau(v):
            ra[k] = v
        elif p.kind == "select" and v in {o.value for o in p.options}:
            ra[k] = v
    return ra


def chuan_hoa(vung: str, hieu_ung: str, params: Any) -> dict[str, Any]:
    """Bộ thông số ĐẦY ĐỦ của hiệu ứng: khoá lạ bị bỏ, thiếu/hỏng rơi về mặc định. ``ValueError`` nếu vùng hoặc
    hiệu ứng không có trong danh mục (``tat`` được phép, không thông số)."""
    if vung not in EFFECTS:
        raise ValueError(f"vùng đèn không có: {vung!r}")
    if hieu_ung == TAT:
        return {}
    eff = EFFECTS[vung].get(hieu_ung)
    if eff is None:
        raise ValueError(f"hiệu ứng {hieu_ung!r} không có ở vùng {vung!r}")
    src = params if isinstance(params, dict) else {}
    ra = {p.key: _kep(p, src.get(p.key, p.default)) for p in eff.params}
    return {k: v for k, v in ra.items() if _hien(eff.by_key[k], ra)}


def _hien(p: Param, gia_tri: dict[str, Any]) -> bool:
    return p.chi_khi is None or gia_tri.get(p.chi_khi[0]) == p.chi_khi[1]


def mac_dinh(vung: str, hieu_ung: str) -> dict[str, Any]:
    return chuan_hoa(vung, hieu_ung, {})


def doi_so(vung: str, hieu_ung: str, params: dict[str, Any], *, master: int = 100) -> list[str]:
    """Danh sách ``khoa=gia_tri`` gửi cho ``r1den.sh``. ``master`` (0–100) nhân vào độ sáng. Màu bỏ dấu ``#``."""
    ps = chuan_hoa(vung, hieu_ung, params)
    out = []
    for k, v in ps.items():
        if k == "do_sang":
            v = round(int(v) * max(0, min(100, int(master))) / 100)
        elif k == "mau":
            v = str(v).lstrip("#")
        out.append(f"{k}={v}")
    return out
