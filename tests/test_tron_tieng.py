"""Bộ trộn tiếng nhiều bên (``tron_tieng``): mã thuần, gọi thẳng, không ngủ, không đồng hồ.

Mỗi bên phát một khung HẰNG SỐ (A=1000, B=2000, điện thoại=3000; mức 1000 ≈ -30 dBFS, trên ngưỡng tiếng -42 dBFS) nên tổng nghe được
tính nhẩm được: mỗi bên phải nghe ĐÚNG tổng các bên khác."""

import array

import pytest

from custom_components.r1_speaker import tron_tieng as T


def khung(v: int, n: int = 1) -> bytes:
    return array.array("h", [v] * 160 * n).tobytes()


def mau(b: bytes) -> list[int]:
    a = array.array("h")
    a.frombytes(b)
    return list(a)


def gia_tri(b: bytes) -> int:
    """Khung hằng số → giá trị (khẳng định cả 160 mẫu bằng nhau)."""
    m = mau(b)
    assert len(m) == 160 and len(set(m)) == 1, m[:4]
    return m[0]


def phong(**kw):
    bt = T.BoTron(**kw)
    bt.them("A", T.LOA)
    bt.them("B", T.LOA)
    bt.them("P", T.DIEN_THOAI)
    return bt


def nghe(bt, **tieng):
    """Mỗi bên nói ``v`` đúng một khung, trộn một bước, trả {bên: giá trị nghe được}."""
    for ma, v in tieng.items():
        bt.dua(ma, khung(v))
    return {m: gia_tri(k) for m, k in bt.buoc().items()}


# ── Cổng theo mức tiếng ──────────────────────────────────────────

def test_cong_vox_bo_khung_im_cho_qua_tieng_kem_dau_cau_va_giu_duoi():
    g = T.CongVox(nguong_db=-42.0, giu=3, tien=2)
    im, tieng = khung(10), khung(1000)
    assert g.feed(im) == ([], False) and g.feed(im) == ([], False) and g.feed(im) == ([], False)
    ra, co = g.feed(tieng)
    assert co and ra == [im, im, tieng]                                   # đệm đầu câu: đúng 2 khung im gần nhất rồi tới khung tiếng
    assert [g.feed(im) for _ in range(3)] == [([im], False)] * 3          # giữ đuôi 3 khung
    assert g.feed(im) == ([], False)                                      # hết đuôi: lại bỏ
    assert g.feed(khung(40))[1] is False and g.feed(khung(5000))[1] is True   # ngưỡng -42 dBFS (~ 260 trên thang 32768)


# ── Luật nghe: mỗi bên nghe tổng các bên KHÁC ────────────────────

def test_moi_ben_nghe_dung_tong_cac_ben_khac_khi_loa_nghe_nhau():
    assert nghe(phong(), A=1000, B=2000, P=3000) == {"A": 2000 + 3000, "B": 1000 + 3000, "P": 1000 + 2000}


def test_giua_cac_loa_tat_thi_loa_chi_nghe_dien_thoai_dien_thoai_nghe_moi_loa():
    assert nghe(phong(giua_cac_loa=False), A=1000, B=2000, P=3000) == {"A": 3000, "B": 3000, "P": 1000 + 2000}


def test_chi_mot_ben_noi_thi_nguoi_khac_nghe_nguoi_do_con_chinh_no_khong_nghe_lai_minh():
    bt = phong()
    assert nghe(bt, A=1000) == {"B": 1000, "P": 1000}                      # A không có trong kết quả: không nghe lại mình
    assert nghe(bt, P=3000) == {"A": 3000, "B": 3000}                      # điện thoại nói: hai loa nghe, điện thoại không
    assert bt.buoc() == {}                                                  # không ai nói: không có gì phát (im lặng, không trễ cũ)


def test_hai_loa_khong_co_dien_thoai_nghe_nhau_va_giua_cac_loa_tat_thi_khong_nghe_ai():
    bt = T.BoTron()
    bt.them("A", T.LOA)
    bt.them("B", T.LOA)
    assert nghe(bt, A=1000, B=2000) == {"A": 2000, "B": 1000}
    bt = T.BoTron(giua_cac_loa=False)
    bt.them("A", T.LOA)
    bt.them("B", T.LOA)
    assert nghe(bt, A=1000, B=2000) == {}


def test_tong_bi_chan_o_gioi_han_int16_khong_tran_so():
    bt = phong()
    assert nghe(bt, A=30000, B=30000, P=-32000) == {"A": 30000 - 32000, "B": 30000 - 32000, "P": 32767}   # 60000 → 32767
    assert nghe(bt, A=-30000, B=-30000) == {"A": -30000, "B": -30000, "P": -32768}                         # -60000 → -32768


# ── Đệm: khung hoá, cụm đầu câu, trần ───────────────────────────

def test_chunk_le_duoc_ghep_thanh_khung_con_du_giu_cho_lan_sau():
    bt = phong()
    pcm = khung(1000, 2)                                                    # 640 byte
    bt.dua("A", pcm[:500])
    assert bt.thong_ke()["A"]["dem"] == 1                                   # 1 khung đủ 320 byte, 180 byte dư
    bt.dua("A", pcm[500:])
    assert bt.thong_ke()["A"]["dem"] == 2


def test_cum_dau_cau_lon_hon_dem_truoc_van_giu_du_va_vuot_tran_thi_bo_khung_cu_nhat():
    bt = phong()
    bt.dua("A", khung(1000, 40))                                            # bộ lọc VAD đổ cả cụm đầu câu 0,3 s + một lúc: không được cắt
    assert bt.thong_ke()["A"] == {"dem": 40, "tran": 0, "bo": 0}
    bt.dua("A", khung(2000, 40))                                            # tổng 80 > trần 60: bỏ 20 khung CŨ nhất
    assert bt.thong_ke()["A"] == {"dem": T.DEM_TOI_DA, "tran": 20, "bo": 0}
    ra = bt.buoc()
    assert gia_tri(ra["B"]) == 1000                                         # khung cũ còn lại là phần đầu của lượt 1 (20 khung 1000 + 40 khung 2000)
    for _ in range(19):
        bt.buoc()
    assert gia_tri(bt.buoc()["B"]) == 2000                                  # hết 20 khung 1000 còn lại thì tới 2000: tiếng mới nhất được giữ


def test_khung_im_bi_cong_muc_tieng_bo_nhung_dang_giu_nut_noi_thi_cho_qua_het():
    bt = phong()
    bt.dua("A", khung(10, 5))                                               # dưới ngưỡng, chưa từng có tiếng
    assert bt.thong_ke()["A"] == {"dem": 0, "tran": 0, "bo": 5}
    bt.dat_ptt("P", True)
    bt.dua("P", khung(10, 5))                                               # điện thoại giữ nút: im cũng qua (người dùng chủ động nói)
    assert bt.thong_ke()["P"]["dem"] == 5
    bt.dat_ptt("P", False)
    bt.dua("P", khung(10, 5))
    assert bt.thong_ke()["P"]["dem"] == 5 and bt.thong_ke()["P"]["bo"] == 5


def test_ben_roi_phong_thi_het_nghe_va_het_duoc_nghe_va_dua_cho_ben_la_bi_bo():
    bt = phong()
    bt.bo("B")
    bt.dua("B", khung(2000))                                                # bên đã rời: bỏ, không lỗi
    assert nghe(bt, A=1000, P=3000) == {"A": 3000, "P": 1000}
    with pytest.raises(ValueError):
        bt.them("A", T.LOA)
    with pytest.raises(ValueError):
        bt.them("C", "khac")
    with pytest.raises(ValueError):
        T.BoTron(che_do="xx")


# ── Chế độ quyền nói (hai loa chung một phòng) ───────────────────

def _quyen_noi():
    return phong(che_do="quyen_noi")


def test_quyen_noi_chi_loa_to_nhat_duoc_chuyen_loa_kia_bi_bo_dien_thoai_luon_qua():
    bt = _quyen_noi()
    r = nghe(bt, A=3000, B=1000, P=500)
    assert r == {"A": 500, "B": 3000 + 500, "P": 3000}                      # A giữ quyền: B bị bỏ; điện thoại vẫn nghe A và loa vẫn nghe điện thoại
    r = nghe(bt, A=3000, B=9000)                                            # B to hơn nhưng A đang giữ: vẫn là A
    assert r == {"B": 3000, "P": 3000}


def test_quyen_noi_nha_sau_khi_nguoi_giu_im_du_lau_roi_loa_khac_nhan_quyen():
    bt = _quyen_noi()
    assert nghe(bt, A=3000, B=1000) == {"B": 3000, "P": 3000}
    for _ in range(T.QUYEN_GIU_KHUNG - 1):                                  # A im, B nói: chưa nhả
        assert nghe(bt, B=1000) == {}
    assert nghe(bt, B=1000) == {"A": 1000, "P": 1000}                       # đủ lâu: B nhận quyền
    bt.bo("B")
    assert nghe(bt, A=2000) == {"P": 2000}                                  # người giữ rời phòng thì nhả ngay


def test_quyen_noi_khi_nguoi_giu_noi_lien_tuc_thi_khong_bi_nha_giua_chung():
    bt = _quyen_noi()
    assert nghe(bt, A=3000) == {"B": 3000, "P": 3000}                        # A nói trước nên giữ quyền
    for _ in range(T.QUYEN_GIU_KHUNG * 3):                                  # B to hơn mãi vẫn không giành được khi A còn nói
        assert nghe(bt, A=3000, B=9000) == {"B": 3000, "P": 3000}


def test_mac_dinh_cua_bo_tron_dem_dau_cau_va_giu_duoi_dung_so_khung():
    """Cổng mức tiếng trong BoTron dùng mặc định ``TIEN_KHUNG``/``GIU_KHUNG``: khung im trước tiếng được đẩy kèm, khung im sau tiếng được giữ rồi bỏ."""
    bt = T.BoTron()
    bt.them("A", T.LOA)
    bt.dua("A", khung(10, 25))                                              # im, chưa từng có tiếng: chỉ được đệm, chưa có gì để phát
    assert bt.thong_ke()["A"]["dem"] == 0
    bt.dua("A", khung(1000))
    assert bt.thong_ke()["A"]["dem"] == 21                                  # tiếng + đúng 20 khung im (0,2 s) ngay trước nó
    bt._nguon["A"].dem.clear()
    bt.dua("A", khung(10, 60))
    assert bt.thong_ke()["A"]["dem"] == 50                                  # sau tiếng giữ đúng 50 khung im (0,5 s) rồi bỏ
    assert (T.TIEN_KHUNG, T.GIU_KHUNG) == (20, 50)                          # số cụ thể ở trên là mặc định đã chọn; đổi mặc định thì đổi cả hai chỗ
