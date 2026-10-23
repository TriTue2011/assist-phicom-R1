"""Tài liệu «từng cài đặt» phải nói đủ mọi cài đặt có thật: thêm cài đặt mới mà quên tài liệu thì test đỏ."""

import json
from pathlib import Path

from custom_components.r1_speaker import hieu_ung, nang_cao
from custom_components.r1_speaker.den import FUNCTIONS
from custom_components.r1_speaker import const

GOC = Path(__file__).parent.parent
DOC = (GOC / "docs" / "CAI-DAT-CHI-TIET.md").read_text(encoding="utf-8")


def test_du_muoi_chin_khoa_nang_cao_kem_khoang_va_mac_dinh():
    for _nhom, khoa, kieu, lo, hi, _buoc, mac_dinh in nang_cao.BANG:
        dong = next((d for d in DOC.splitlines() if f"`{khoa}`" in d and d.startswith("|")), None)
        assert dong, f"thiếu {khoa} trong tài liệu"
        if kieu == "so":
            # mặc định và hai đầu khoảng phải khớp số thật (viết kiểu Việt: dấu phẩy thập phân)
            def vn(x):
                x = float(x)
                return str(int(x)) if x == int(x) else str(x).replace(".", ",")
            d = dong.replace("−", "-")                     # tài liệu viết dấu trừ đẹp «−»
            assert vn(lo) in d and vn(hi) in d and vn(mac_dinh) in d, (khoa, dong)


def test_du_tam_chuc_nang_den_va_moi_hieu_ung():
    for k in FUNCTIONS:
        assert f"`{k}`" in DOC, k
    for hu in ("thở", "cầu vồng", "nhấp nháy", "nhịp tim", "pháo hoa", "chớp"):
        assert hu in DOC
    assert len(hieu_ung.HIEU_UNG) == 8     # 6 ban đầu + cầu vồng firmware + chạy đuổi viền


def test_du_thuc_the_dich_vu_va_preset_eq():
    d = json.loads((GOC / "custom_components" / "r1_speaker" / "translations" / "vi.json").read_text(encoding="utf-8"))
    for dom in d["entity"].values():
        for k, v in dom.items():
            ten = v["name"].replace("{band}", "").strip()
            if k == "eq_band":
                continue                                           # năm dải EQ được liệt kê theo tần số
            assert ten.split(" / ")[0] in DOC, f"thiếu thực thể «{ten}» trong tài liệu"
    for dv in d["services"]:
        assert f"`{dv}`" in DOC or dv in ("start_duplex", "stop_duplex"), dv
    for p in const.EQ_PRESET_DB:
        assert p in DOC, p
