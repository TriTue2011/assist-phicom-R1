"""Chế độ «đóng ADB»: tự đóng ADB mạng khi APK đã nối ổn định, KHÔNG đóng khi chưa nối (không tự khoá chính mình)."""

from types import SimpleNamespace

import pytest

from custom_components.r1_speaker import tu_dong_dong_adb as t
from custom_components.r1_speaker.adb_client import AdbError
from custom_components.r1_speaker.mic_server import SERVER_NGHE, SERVER_NHAN


class Dong:
    def __init__(self):
        self.dong = 0
        self.loi = None
        self.nghe = True                 # cổng mạng còn nghe

    async def dong_adb_mang(self):
        self.dong += 1
        if self.loi:
            raise self.loi
        self.nghe = False

    async def con_nghe_mang(self):
        return self.nghe


class Gio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def tao(bat=True, state=SERVER_NHAN):
    dev, gio = Dong(), Gio()
    mic = SimpleNamespace(state=state)
    cfg = {"bat": bat}
    return t.TuDongDongAdb(dev, mic, lambda: cfg["bat"], dong_ho=gio), dev, mic, gio, cfg


async def test_chi_dong_sau_khi_apk_noi_on_dinh_du_lau():
    d, dev, mic, gio, _ = tao()
    assert await d.kiem() is None and dev.dong == 0               # vừa thấy nối: bắt đầu đếm
    gio.t += t.ON_DINH_S - 1
    assert await d.kiem() is None and dev.dong == 0               # chưa đủ ổn định
    gio.t += 2
    assert await d.kiem() == "đã đóng" and dev.dong == 1
    gio.t += 10
    assert await d.kiem() is None and dev.dong == 1               # không đóng lặp trong khoảng nghỉ


async def test_khong_dong_khi_apk_chua_noi_hoac_mat_noi_thi_dem_lai():
    d, dev, mic, gio, _ = tao(state=SERVER_NGHE)
    for _ in range(5):
        gio.t += t.ON_DINH_S
        assert await d.kiem() is None
    assert dev.dong == 0, "APK chưa nối mà đóng ADB là tự khoá: còn cần ADB để cài/cấu hình"
    mic.state = SERVER_NHAN
    await d.kiem()
    gio.t += t.ON_DINH_S - 5
    mic.state = SERVER_NGHE                                         # đứt giữa chừng: phải đếm lại từ đầu
    await d.kiem()
    mic.state = SERVER_NHAN
    await d.kiem()
    gio.t += t.ON_DINH_S - 5
    assert await d.kiem() is None and dev.dong == 0


async def test_che_do_tat_thi_khong_bao_gio_dong():
    d, dev, mic, gio, cfg = tao(bat=False)
    for _ in range(4):
        gio.t += t.ON_DINH_S * 2
        assert await d.kiem() is None
    assert dev.dong == 0


async def test_loa_khoi_dong_lai_adb_mo_lai_thi_dong_lai_sau_nhip_nghi():
    d, dev, mic, gio, _ = tao()
    await d.kiem()
    gio.t += t.ON_DINH_S + 1
    assert await d.kiem() == "đã đóng"
    gio.t += t.NGHI_GIUA_LAN_S + 1
    dev.nghe = True                                                # loa vừa khởi động lại: cổng 5555 mở trở lại
    assert await d.kiem() == "đã đóng" and dev.dong == 2


async def test_da_dong_san_thi_im_lang_con_loa_khong_cho_dong_thi_canh_bao(caplog):
    d, dev, mic, gio, _ = tao()
    await d.kiem()
    gio.t += t.ON_DINH_S + 1
    dev.loi, dev.nghe = AdbError("không nối được"), False          # cổng đã đóng sẵn: lỗi nối là bình thường
    caplog.clear()
    assert await d.kiem() is None and not [r for r in caplog.records if r.levelname == "WARNING"]
    gio.t += t.NGHI_GIUA_LAN_S + 1
    dev.loi, dev.nghe = AdbError("adbd vẫn còn nghe"), True        # vẫn nghe mà đóng không được: phải thấy cảnh báo
    assert await d.kiem() is None
    assert any(r.levelname == "WARNING" and "chưa đóng được" in r.getMessage() for r in caplog.records)
