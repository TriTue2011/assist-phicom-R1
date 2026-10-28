"""Tự kết nối APK bodam về HA khi APK được cài ngoài tích hợp: điều kiện là TRẠNG THÁI thật (phiên mic, gói đã cài), có giới hạn lần."""

from __future__ import annotations

import pytest

from custom_components.r1_speaker.adb_client import AdbError
from custom_components.r1_speaker.cai_ung_dung import BoCai, TrangThai, UngDung, doc_bo_cai
from custom_components.r1_speaker.mic_server import SERVER_NGHE, SERVER_NHAN, SERVER_TAT
from custom_components.r1_speaker.tu_ket_noi import CHO_NOI_S, NGHI_GIUA_LAN_S, TOI_DA_LAN, TuKetNoi


class _Mic:
    def __init__(self, state=SERVER_NGHE):
        self.state = state


class _Dong:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _BoCai:
    """Giả bộ cài: ghi lại số lần cấu hình lại; có thể cho ADB lỗi hoặc gói chưa cài/đang ẩn."""

    def __init__(self, cai=True, an=False):
        self.tt = TrangThai(cai=cai, an=an)
        self.lan_cau_hinh = 0
        self.loi: Exception | None = None
        self.ud = UngDung(id="bodam", ten="b", goi="vn.r1.bodam", tep=("x.apk",), sha256="0" * 64, phien_ban="1", thu_tu=3,
                          mac_dinh=True, sau_cai="cau_hinh_bodam")

    def bodam(self):
        return self.ud

    async def trang_thai(self, ud, *, moi=False):
        if self.loi:
            raise self.loi
        return self.tt

    async def cau_hinh_lai(self):
        if self.loi:
            raise self.loi
        self.lan_cau_hinh += 1
        return "đã chạy lệnh cấu hình APK"


def _tao(cai=True, an=False, state=SERVER_NGHE):
    d, b, m = _Dong(), _BoCai(cai, an), _Mic(state)
    return TuKetNoi(b, m, dong_ho=d), d, b, m


async def _qua_han(k, d):
    """Nhịp đầu ghi mốc «mất kết nối», rồi trôi qua hạn chờ và kiểm lại."""
    assert await k.kiem() is None
    d.t += CHO_NOI_S + 1
    return await k.kiem()


async def test_da_cai_ma_khong_noi_ve_ha_thi_cau_hinh_mot_lan():
    k, d, b, _ = _tao()
    kq = await _qua_han(k, d)
    assert kq and b.lan_cau_hinh == 1


async def test_chua_du_thoi_gian_cho_thi_khong_lam_gi():
    k, d, b, _ = _tao()
    await k.kiem()
    d.t += CHO_NOI_S - 5
    assert await k.kiem() is None and b.lan_cau_hinh == 0


async def test_apk_da_noi_thi_khong_dong_den():
    k, d, b, m = _tao(state=SERVER_NHAN)
    assert await _qua_han(k, d) is None and b.lan_cau_hinh == 0


async def test_chua_co_khoa_hoac_cong_nghe_thi_khong_lam_gi():
    """Máy chủ mic tắt (chưa có khoá): không có gì để APK nối vào."""
    k, d, b, _ = _tao(state=SERVER_TAT)
    assert await _qua_han(k, d) is None and b.lan_cau_hinh == 0


@pytest.mark.parametrize("cai, an", [(False, False), (True, True)])
async def test_chua_cai_hoac_dang_an_thi_chua_cau_hinh(cai, an):
    k, d, b, _ = _tao(cai=cai, an=an)
    assert await _qua_han(k, d) is None and b.lan_cau_hinh == 0


async def test_cai_xong_sau_do_van_duoc_cau_hinh():
    """Người dùng cài APK SAU khi HA đã chờ lâu: ngay nhịp thấy gói đã cài là cấu hình (không đợi thêm hạn chờ)."""
    k, d, b, _ = _tao(cai=False)
    assert await _qua_han(k, d) is None
    b.tt = TrangThai(cai=True)
    assert await k.kiem() and b.lan_cau_hinh == 1


async def test_nghi_giua_hai_lan_va_tran_so_lan():
    k, d, b, _ = _tao()
    await _qua_han(k, d)
    for _ in range(10):                                    # trong thời gian nghỉ: không lặp
        d.t += NGHI_GIUA_LAN_S / 20
        assert await k.kiem() is None
    assert b.lan_cau_hinh == 1
    for _ in range(10):                                    # sau mỗi quãng nghỉ thêm một lần, nhưng tối đa TOI_DA_LAN
        d.t += NGHI_GIUA_LAN_S + 1
        await k.kiem()
    assert b.lan_cau_hinh == TOI_DA_LAN


async def test_loi_adb_khong_tinh_la_mot_lan_ra_tay():
    k, d, b, _ = _tao()
    b.loi = AdbError("adbd bận")
    assert await _qua_han(k, d) is None
    d.t += 1
    assert await k.kiem() is None
    b.loi = None
    assert await k.kiem() and b.lan_cau_hinh == 1          # hết lỗi: ra tay ngay, chưa mất lần nào


async def test_noi_lai_roi_mat_ket_noi_lan_nua_duoc_thu_lai_tu_dau():
    k, d, b, m = _tao()
    await _qua_han(k, d)
    for _ in range(TOI_DA_LAN - 1):
        d.t += NGHI_GIUA_LAN_S + 1
        await k.kiem()
    assert b.lan_cau_hinh == TOI_DA_LAN
    m.state = SERVER_NHAN
    assert await k.kiem() is None                          # APK đã nối: xoá nợ
    m.state = SERVER_NGHE
    assert await _qua_han(k, d) and b.lan_cau_hinh == TOI_DA_LAN + 1


async def test_bo_cai_that_co_ung_dung_bodam_va_cau_hinh_lai_giu_khoa():
    """Đường thật: danh sách ``bo-cai.json`` có đúng một ứng dụng khai ``sau_cai``; ``cau_hinh_lai`` chạy lệnh am start với host/cổng/khoá."""
    lenh: list[str] = []

    class Dev:
        async def shell(self, c, timeout=0):
            lenh.append(c)
            return ""

    bo = BoCai(Dev(), danh_sach=doc_bo_cai(), cau_hinh_bodam=lambda: ("172.16.10.200", 18765, "khoa_thu_nghiem_12345678"))
    ud = bo.bodam()
    assert ud is not None and ud.goi == "vn.r1.bodam"
    assert (await bo.cau_hinh_lai()).startswith("đã chạy lệnh cấu hình APK")
    assert lenh and lenh[0].startswith("am start -n vn.r1.bodam/.ManHinhChinh --es host 172.16.10.200 --ei port 18765 --es khoa ")
    # chưa đủ thông tin (chưa có khoá) thì bỏ qua, không chạy lệnh
    lenh.clear()
    bo2 = BoCai(Dev(), danh_sach=doc_bo_cai(), cau_hinh_bodam=lambda: None)
    assert "bỏ qua" in await bo2.cau_hinh_lai() and not lenh
