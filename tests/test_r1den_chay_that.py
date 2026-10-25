"""Chạy THẬT ``r1den.sh`` (ghi ra tệp thay vì đèn) và đối chiếu danh mục thông số với phần đọc tham số của script.

Lý do: test khác chỉ kiểm chuỗi lệnh HA gửi đi, không bao giờ chạy script nên không bắt được ca «thông số có trong thẻ nhưng script
không đọc / đọc nhưng không dùng» (chủ máy 25/10: «số dải cầu vồng, sao chổi đang không hoạt động»). Script chạy trên loa bằng
Android sh; ở đây chạy bằng bash (cùng cú pháp mksh dùng: ``${H:i:n}``, ``$(( ))``)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from custom_components.r1_speaker.den_hieu_ung import EFFECTS, VUNG_DAY, doi_so

SCRIPT = Path(__file__).parents[1] / "custom_components" / "r1_speaker" / "r1den.sh"
BASH = shutil.which("bash")


def _chay(tmp_path: Path, vung: str, hieu_ung: str, *args: str, giay: float = 1.6) -> list[tuple[str, str]]:
    """Chạy script giả lập: tệp đèn và tệp pid trỏ vào tmp_path; trả danh sách (mặt nạ, màu) đã ghi theo thứ tự."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count("F=/sys/class/leds/multi_leds0/led_color") == 1 and src.count('echo "$1 $2" > $F') == 1
    nhat_ky = tmp_path / "led.log"
    nhat_ky.write_text("")
    gia = (src.replace("F=/sys/class/leds/multi_leds0/led_color", "F=/dev/null")
              .replace('echo "$1 $2" > $F', f'echo "$1 $2" >> {nhat_ky}')
              .replace("/data/local/tmp/r1den", str(tmp_path / "r1den")))
    sh = tmp_path / "r1den_gia.sh"
    sh.write_text(gia, encoding="utf-8")
    subprocess.run(["timeout", str(giay), BASH, str(sh), vung, hieu_ung, *args], capture_output=True, timeout=giay + 5)
    return [tuple(d.split()) for d in nhat_ky.read_text().splitlines() if d.strip()]


def _khung_dau(ghi: list[tuple[str, str]], so_den: int = 15) -> list[bool]:
    """Khung đầu tiên: mỗi đèn sáng (màu khác 000000) hay tắt."""
    khung = ghi[:so_den]
    assert len(khung) == so_den, f"script ghi quá ít: {len(ghi)} dòng"
    return [int(mau, 16) > 0 for _, mau in khung]


pytestmark = pytest.mark.skipif(BASH is None or shutil.which("timeout") is None, reason="cần bash và timeout")


def test_moi_khoa_trong_danh_muc_deu_duoc_script_doc():
    """Lớp lỗi: thêm thông số vào danh mục mà quên dạy script đọc (hoặc ngược lại)."""
    src = SCRIPT.read_text(encoding="utf-8")
    doc = set(re.findall(r"\b([a-z_]+)=\*\)", src))
    thieu = sorted({p.key for vung in EFFECTS.values() for e in vung.values() for p in e.params} - doc)
    assert not thieu, f"script không đọc các khoá của danh mục: {thieu}"


def test_dau_phien_ban_script_da_tang_khi_them_so_choi():
    """HA chỉ đẩy lại script lên loa khi dấu ``(r1den-vN)`` đổi; script có khoá mới mà giữ v1 thì loa cũ không bao giờ nhận."""
    assert re.search(r"\(r1den-v([2-9]|\d{2,})\)", SCRIPT.read_text(encoding="utf-8").splitlines()[1])


@pytest.mark.parametrize("so_choi, sang", [(1, 5), (2, 10), (3, 15)])
def test_so_sao_choi_la_so_dau_sang_cach_deu(tmp_path, so_choi, sang):
    """Đuôi 5 đèn: N sao chổi sáng 5×N đèn (trần 15 khi các đuôi nối nhau)."""
    ghi = _chay(tmp_path, "day", "sao_choi", "do_sang=100", "dai_duoi=5", "kieu_mau=nhieu_mau", f"so_choi={so_choi}")
    assert sum(_khung_dau(ghi)) == sang


def test_hai_sao_choi_cach_nua_vong_va_chay_thanh_hai_nhom(tmp_path):
    ghi = _chay(tmp_path, "day", "sao_choi", "do_sang=100", "dai_duoi=4", "so_choi=2")
    k0 = _khung_dau(ghi)
    nhom = [i for i in range(15) if k0[i] and not k0[i - 1]]      # đầu mỗi nhóm đèn sáng liền nhau
    assert len(nhom) == 2 and sum(k0) == 8
    # sau một bước hai nhóm dịch cùng chiều một đèn
    k1 = [int(m, 16) > 0 for _, m in ghi[15:30]]
    assert k1 != k0 and sum(k1) == 8


def test_khong_khai_so_choi_giong_het_mot_sao_choi(tmp_path):
    """Tương thích: cấu hình cũ (không có so_choi) vẫn là một sao chổi như trước."""
    a = _khung_dau(_chay(tmp_path, "day", "sao_choi", "do_sang=100", "dai_duoi=5"))
    b = _khung_dau(_chay(tmp_path, "day", "sao_choi", "do_sang=100", "dai_duoi=5", "so_choi=1"))
    assert a == b and sum(a) == 5


@pytest.mark.parametrize("gia_tri, sang", [("0", 5), ("9", 15), ("abc", 5), ("-3", 5)])
def test_so_choi_ngoai_khoang_bi_kep(tmp_path, gia_tri, sang):
    """Script tự kẹp 1–4 (HA đã kiểm, nhưng một lệnh sai không được ghi bậy vào đèn): 0/chữ/âm → 1; 9 → 4 sao chổi (đuôi 5 kín 15 đèn)."""
    ghi = _chay(tmp_path, "day", "sao_choi", "do_sang=100", "dai_duoi=5", f"so_choi={gia_tri}")
    assert sum(_khung_dau(ghi)) == sang


def test_tran_so_sao_choi_la_bon_voi_duoi_ngan(tmp_path):
    """Đuôi 2 đèn: 9 sao chổi bị kẹp về 4 → sáng 8 đèn (không kẹp thì 9 sao chổi sáng 15 đèn kín vòng)."""
    assert sum(_khung_dau(_chay(tmp_path, "day", "sao_choi", "do_sang=100", "dai_duoi=2", "so_choi=9"))) == 8


def test_so_dai_cau_vong_xoay_dung_so_vong(tmp_path):
    """Số dải = số vòng cầu vồng lặp lại: 1 → 15 sắc khác nhau; 3 → 5 sắc lặp 3 lần."""
    def sac(n):
        ghi = _chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", f"so_dai={n}")
        return len({mau for _, mau in ghi[:15]})
    assert sac(1) == 15 and sac(3) == 5


def _sac(ghi, so_den=15):
    """Sắc độ (0–359) của từng đèn trong khung đầu; đèn tắt = None."""
    import colorsys
    ra = []
    for _, mau in ghi[:so_den]:
        r, g, b = (int(mau[i:i + 2], 16) / 255 for i in (0, 2, 4))
        ra.append(None if max(r, g, b) == 0 else round(colorsys.rgb_to_hsv(r, g, b)[0] * 360) % 360)
    return ra


def test_cau_vong_xoay_khong_khai_kieu_dai_giu_nguyen_ca_vong(tmp_path):
    """Tương thích: cấu hình cũ (không có kieu_dai) vẫn là cả vòng 15 đèn đều sáng, 15 sắc khác nhau."""
    sac = _sac(_chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", "so_dai=1"))
    assert None not in sac and len(set(sac)) == 15


@pytest.mark.parametrize("so_dai, rong, sang", [(1, 5, 5), (2, 4, 8), (3, 4, 12), (5, 3, 15)])
def test_dai_ngan_so_den_sang_bang_so_dai_nhan_do_rong(tmp_path, so_dai, rong, sang):
    ghi = _chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", "kieu_dai=dai_ngan", f"so_dai={so_dai}", f"do_rong={rong}")
    sac = _sac(ghi)
    assert sum(s is not None for s in sac) == sang


def test_dai_ngan_moi_dai_du_sac_dau_do_va_cac_dai_cach_deu(tmp_path):
    """Hai dải rộng 5: mỗi dải 5 đèn đủ sắc (đỏ ở đầu, các đèn sau khác nhau), hai dải cách nhau nửa vòng, 5 đèn tối còn lại."""
    sac = _sac(_chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", "kieu_dai=dai_ngan", "so_dai=2", "do_rong=5"))
    assert sum(s is None for s in sac) == 5
    nhom, i = [], 0
    while i < 15:                                       # tách các nhóm đèn sáng liền nhau (vòng kín)
        if sac[i] is not None and sac[i - 1] is None:
            j = i
            while sac[j % 15] is not None and j - i < 15:
                j += 1
            nhom.append([sac[x % 15] for x in range(i, j)])
            i = j
        else:
            i += 1
    assert len(nhom) == 2 and all(len(n) == 5 and len(set(n)) == 5 for n in nhom)
    assert all(0 in n for n in nhom) and nhom[0][0] != nhom[0][-1]


def test_dai_ngan_chay_quanh_moi_khung_dich_mot_den(tmp_path):
    ghi = _chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", "kieu_dai=dai_ngan", "so_dai=1", "do_rong=4")
    k0 = [s is not None for s in _sac(ghi[:15])]
    k1 = [s is not None for s in _sac(ghi[15:30])]
    assert k0 != k1 and sum(k0) == sum(k1) == 4
    assert k1 == k0[-1:] + k0[:-1] or k1 == k0[1:] + k0[:1]


def test_dai_ngan_tran_so_dai_nam_va_do_rong_kep(tmp_path):
    """so_dai=9 bị kẹp 5 (5 dải rộng 3 chia đều: chu kỳ sắc lặp đúng 3 đèn); do_rong=99 bị kẹp 8 (một dải sáng 8 đèn)."""
    sac = _sac(_chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", "kieu_dai=dai_ngan", "so_dai=9", "do_rong=3"))
    assert None not in sac and all(sac[i] == sac[i + 3] for i in range(12))
    rong = _sac(_chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "kieu_dai=dai_ngan", "so_dai=1", "do_rong=99"))
    assert sum(s is not None for s in rong) == 8


def test_kieu_dai_la_gia_tri_la_roi_ve_ca_vong(tmp_path):
    sac = _sac(_chay(tmp_path, "day", "cau_vong_xoay", "do_sang=100", "bao_hoa=100", "kieu_dai=xyz", "so_dai=1"))
    assert None not in sac and len(set(sac)) == 15


def test_danh_muc_do_rong_chi_hien_o_kieu_dai_ngan():
    from custom_components.r1_speaker.den_hieu_ung import chuan_hoa
    assert "do_rong" not in chuan_hoa(VUNG_DAY, "cau_vong_xoay", {"do_rong": 6})
    ps = chuan_hoa(VUNG_DAY, "cau_vong_xoay", {"kieu_dai": "dai_ngan", "do_rong": 6, "so_dai": 4})
    assert ps["do_rong"] == 6 and ps["so_dai"] == 4 and ps["kieu_dai"] == "dai_ngan"
    assert chuan_hoa(VUNG_DAY, "cau_vong_xoay", {"so_dai": 99})["so_dai"] == 5


def test_lenh_ha_gui_di_khop_voi_script(tmp_path):
    """Đi trọn đường: thông số → ``doi_so`` (cái HA gửi) → script chạy thật cho đúng hai sao chổi."""
    args = doi_so(VUNG_DAY, "sao_choi", {"so_choi": 2, "dai_duoi": 5})
    assert "so_choi=2" in args
    assert sum(_khung_dau(_chay(tmp_path, "day", "sao_choi", *args))) == 10
