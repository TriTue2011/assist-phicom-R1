"""Danh mục hiệu ứng đèn: mỗi hiệu ứng có thông số RIÊNG, số lượng khác nhau; chuẩn hoá và dựng đối số cho r1den.sh."""

import re

import pytest

from custom_components.r1_speaker import den_hieu_ung as hu
from custom_components.r1_speaker.den_hieu_ung import EFFECTS, TAT, chuan_hoa, doi_so

AN_TOAN = re.compile(r"^[a-z_]+=[0-9a-z_]+$")


def test_danh_muc_dung_nhu_chu_may_chot():
    assert list(EFFECTS["day"]) == ["co_dinh", "tho", "nhap_nhay", "nhip_tim", "chop", "phao_hoa", "cau_vong",
                                    "cau_vong_fw", "cau_vong_xoay", "sao_choi"]
    assert list(EFFECTS["vien"]) == ["sang", "chay_duoi", "tho"]        # đúng 3 hiệu ứng viền, KHÔNG có 24 chế độ
    so_tham_so = {e.id: len(e.params) for v in EFFECTS.values() for e in v.values()}
    assert len(set(so_tham_so.values())) > 3                              # số thông số mỗi hiệu ứng khác nhau
    assert so_tham_so["sang"] == 1                                        # viền sáng liên tục: chỉ độ sáng


def test_vien_chi_trang_khong_co_thong_so_mau():
    for e in EFFECTS["vien"].values():
        assert "mau" not in e.by_key, e.id


def test_cau_vong_va_sao_choi_khong_bat_chon_mau_tru_sao_choi_don_sac():
    for hid in ("cau_vong", "cau_vong_fw", "cau_vong_xoay", "phao_hoa"):
        assert "mau" not in EFFECTS["day"][hid].by_key, hid
    sc = EFFECTS["day"]["sao_choi"]
    assert sc.by_key["mau"].chi_khi == ("kieu_mau", "don_sac")
    assert "mau" not in chuan_hoa("day", "sao_choi", {"kieu_mau": "nhieu_mau"})
    assert chuan_hoa("day", "sao_choi", {"kieu_mau": "don_sac", "mau": "#ABCDEF"})["mau"] == "#abcdef"


@pytest.mark.parametrize("vung", hu.VUNG)
def test_moi_hieu_ung_co_mac_dinh_hop_le_va_doi_so_an_toan(vung):
    for hid, e in EFFECTS[vung].items():
        ps = hu.mac_dinh(vung, hid)
        assert chuan_hoa(vung, hid, ps) == ps, hid                         # mặc định đã chuẩn
        args = doi_so(vung, hid, ps)
        assert args and all(AN_TOAN.match(a) for a in args), (hid, args)   # không ký tự lạ nào vào shell loa
        for p in e.params:
            d = p.to_dict()
            assert d["key"] == p.key and d["kind"] in ("range", "color", "select")
            if p.kind == "range":
                assert p.min <= p.default <= p.max, (hid, p.key)


def test_chuan_hoa_kep_khoang_bo_khoa_la_va_gia_tri_hong_ve_mac_dinh():
    r = chuan_hoa("day", "tho", {"mau": "đỏ", "do_sang": 500, "toc_do": -3, "do_sau": "x", "la": 1})
    assert r == {"mau": "#0000ff", "do_sang": 100, "toc_do": 25, "do_sau": 0}
    assert chuan_hoa("day", "tho", None) == hu.mac_dinh("day", "tho")
    assert chuan_hoa("vien", "chay_duoi", {"chieu": "ma"})["chieu"] == "xuoi"
    assert chuan_hoa("day", "chop", {"so_chop": 99})["so_chop"] == 6
    assert chuan_hoa("day", "tho", {"do_sang": True})["do_sang"] == 100        # bool không phải số
    assert chuan_hoa("day", TAT, {"x": 1}) == {}


def test_hieu_ung_hoac_vung_khong_co_thi_bao_loi():
    for vung, he in (("day", "chay_duoi"), ("vien", "cau_vong"), ("khac", "tho")):
        with pytest.raises(ValueError):
            chuan_hoa(vung, he, {})


def test_doi_so_nhan_do_sang_chung_va_bo_dau_thang():
    a = dict(x.split("=") for x in doi_so("day", "co_dinh", {"mau": "#ff8000", "do_sang": 80}, master=50))
    assert a == {"mau": "ff8000", "do_sang": "40"}
    assert doi_so("vien", "sang", {"do_sang": 100}, master=0) == ["do_sang=0"]
