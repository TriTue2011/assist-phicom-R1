"""Chẩn đoán đường phím APK ≥ 1.4: khung `phim_cd` (dịch vụ trợ năng nối chưa, phím tới / báo HA / mất) hiện ở sensor.r1_apk để biết phím mất ở đâu."""

from unittest import mock

from custom_components.r1_speaker.mic_server import R1MicServer


def _server():
    return R1MicServer(mock.MagicMock(), 0, "khoa-gia", "127.0.0.1")


def test_phim_cd_hop_le_duoc_luu_va_bao_thay_doi():
    s = _server()
    dem = []
    s._on_state.append(lambda: dem.append(1))
    assert s.phim_cd is None
    assert s._xu_ly_khung_apk("phim_cd", {"noi": True, "nhan": 3, "bao": 2, "mat": 1}) is True
    assert s.phim_cd == {"dich_vu_noi": True, "nhan": 3, "bao_ha": 2, "mat": 1} and len(dem) == 1
    s._xu_ly_khung_apk("phim_cd", {"noi": True, "nhan": 3, "bao": 2, "mat": 1})
    assert len(dem) == 1                                   # giống hệt: không báo lại
    s._xu_ly_khung_apk("phim_cd", {"noi": True, "nhan": 4, "bao": 3, "mat": 1})
    assert s.phim_cd["nhan"] == 4 and len(dem) == 2


def test_phim_cd_sai_dang_bi_bo_khong_lam_hong_ket_noi():
    s = _server()
    for xau in ({"noi": 1, "nhan": 0, "bao": 0, "mat": 0}, {"noi": True, "nhan": -1, "bao": 0, "mat": 0}, {"noi": True, "nhan": "3", "bao": 0, "mat": 0},
                {"noi": True, "nhan": True, "bao": 0, "mat": 0}, {"noi": True, "nhan": 0, "bao": 0}, {"noi": True, "nhan": 10**12, "bao": 0, "mat": 0}):
        assert s._xu_ly_khung_apk("phim_cd", xau) is True       # đã xử lý (bỏ), không ném lỗi
        assert s.phim_cd is None, xau
