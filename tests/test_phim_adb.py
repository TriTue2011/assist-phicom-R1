"""Nhận phím nút giữa qua ``getevent`` của ADB (``phim_adb``): phân tích dòng, lọc đúng nút giữa, ghép dòng bị cắt giữa các khúc đọc,
và vòng nối lại (chờ tăng dần, không thử khi tắt, huỷ thì đóng luồng). Thiết bị ADB và luồng là bản giả; dòng mẫu là dòng ``getevent``
ĐO THẬT trên loa 28/10/2026 (nút giữa = /dev/input/event0, mã 0x00c3, nhấn 1 / nhả 0)."""

import asyncio
import types

import pytest

from custom_components.r1_speaker import phim_adb as PA
from custom_components.r1_speaker.adb_client import AdbError

XUONG = "/dev/input/event0: 0001 00c3 00000001"
LEN = "/dev/input/event0: 0001 00c3 00000000"
SYN = "/dev/input/event0: 0000 0000 00000000"


class PhimGia:
    def __init__(self):
        self.ra = []

    def tu_tho(self, ma, xuong):
        self.ra.append((ma, xuong))


def tao():
    p = PhimGia()
    return PA.PhimAdb(None, p, lambda: True), p


# ── Phân tích dòng ───────────────────────────────────────────────

def test_phan_tich_dong_that_va_dong_la():
    assert PA.phan_tich_dong(XUONG) == ("/dev/input/event0", 1, 0xC3, 1)
    assert PA.phan_tich_dong("  " + LEN + "\r") == ("/dev/input/event0", 1, 0xC3, 0)         # khoảng trắng và CR đầu/cuối
    assert PA.phan_tich_dong("/dev/input/event1: 0003 0000 000000ff") == ("/dev/input/event1", 3, 0, 255)
    assert PA.phan_tich_dong("/dev/input/event0: 0003 0001 ffffffff")[3] == -1                 # giá trị có dấu 32 bit
    for la in ("", "add device 1: /dev/input/event0", "  name:     \"gpio-keys\"", "/dev/input/event0: 0001 00c3",
               "/dev/input/event0: 0001 00c3 1", "/dev/input/event0: 00zz 00c3 00000001", "/dev/input/mouse0: 0001 00c3 00000001", "💥"):
        assert PA.phan_tich_dong(la) is None, la


# ── Chỉ nút giữa nhấn/nhả mới thành cử chỉ thô ───────────────────

def test_chi_nut_giua_nhan_va_nha_di_vao_nhan_dien_cu_chi():
    p_adb, p = tao()
    for dong in (XUONG, SYN, LEN):
        p_adb.xu_ly_dong(dong)
    assert p.ra == [(195, True), (195, False)]                                   # dòng đồng bộ (0000) bỏ qua
    p.ra.clear()
    for dong in ("/dev/input/event1: 0001 00c3 00000001",                         # thiết bị khác (thanh cảm ứng)
                 "/dev/input/event0: 0001 0072 00000001",                         # mã phím khác (âm lượng)
                 "/dev/input/event0: 0003 00c3 00000001",                         # không phải EV_KEY
                 "/dev/input/event0: 0001 00c3 00000002",                         # giá trị «lặp phím», không phải nhấn/nhả
                 "rác không phải dòng getevent"):
        p_adb.xu_ly_dong(dong)
    assert p.ra == []


# ── Đọc luồng ────────────────────────────────────────────────────

class LuongGia:
    def __init__(self, khuc, tren_doc=None, loi_dong=False):
        self.khuc, self.da_dong, self.tren_doc, self.loi_dong = list(khuc), False, tren_doc, loi_dong

    async def read(self, n):
        if self.tren_doc:
            self.tren_doc()
        if self.khuc and isinstance(self.khuc[0], BaseException):
            raise self.khuc.pop(0)
        return self.khuc.pop(0) if self.khuc else b""

    async def close(self):
        self.da_dong = True
        if self.loi_dong:
            raise RuntimeError("đóng luồng hỏng")


async def test_doc_luong_ghep_dong_bi_cat_giua_cac_khuc_va_bo_dong_qua_dai():
    p_adb, p = tao()
    chuoi = (XUONG + "\n" + LEN + "\n").encode()
    cat = [chuoi[:10], chuoi[10:40], chuoi[40:]]                                  # cắt giữa dòng, kể cả giữa mã phím
    await p_adb.doc_luong(LuongGia(cat))
    assert p.ra == [(195, True), (195, False)]
    p.ra.clear()
    # Rác dài quá giới hạn mà không có xuống dòng bị bỏ (không phình bộ nhớ): dòng đúng đến ngay sau NHẬN ĐƯỢC. Không có giới hạn thì rác dính
    # vào đầu dòng đúng và cả dòng bị loại.
    rac = b"x" * (PA.DAI_DONG_TOI_DA + 100)
    await p_adb.doc_luong(LuongGia([rac, XUONG.encode() + b"\n"]))
    assert p.ra == [(195, True)]


# ── Vòng nối lại ─────────────────────────────────────────────────

class ThietBiGia:
    def __init__(self, ket_qua):
        self.ket_qua, self.dich_vu = list(ket_qua), []

    async def open(self, service):
        self.dich_vu.append(service)
        r = self.ket_qua.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


class _Dung(Exception):
    pass


def _thay_ngu(monkeypatch, toi_da):
    """Thay ``asyncio.sleep`` BÊN TRONG phim_adb: ghi số giây chờ, dừng vòng sau ``toi_da`` lần."""
    ngu = []

    async def sleep(giay):
        ngu.append(giay)
        if len(ngu) >= toi_da:
            raise _Dung

    monkeypatch.setattr(PA, "asyncio", types.SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError))
    return ngu


async def test_chay_loi_thi_cho_tang_dan_thanh_cong_thi_cho_ve_dau_va_dong_luong_hong_khong_dung_vong(monkeypatch):
    ngu = _thay_ngu(monkeypatch, 4)
    p = PhimGia()
    dev = ThietBiGia([AdbError("adbd không trả lời"), None, OSError("mất mạng"), TimeoutError()])
    adb = PA.PhimAdb(dev, p, lambda: True)
    thay = []
    luong = LuongGia([(XUONG + "\n" + LEN + "\n").encode()], tren_doc=lambda: thay.append(adb.dang_nghe), loi_dong=True)
    dev.ket_qua[1] = luong
    with pytest.raises(_Dung):
        await adb.chay()
    assert dev.dich_vu == ["shell:getevent"] * 4
    assert p.ra == [(195, True), (195, False)] and thay[0] is True                # đang nghe khi mở luồng
    assert ngu == [PA.CHO_LOI_DAU_S, PA.CHO_LOI_DAU_S, 2 * PA.CHO_LOI_DAU_S, 4 * PA.CHO_LOI_DAU_S]   # lỗi: gấp đôi; thành công: về mức đầu
    assert luong.da_dong and adb.dang_nghe is False                              # đóng hỏng không làm dừng vòng; hết nghe thì cờ về False


async def test_chay_cho_toi_da_khong_vuot_tran(monkeypatch):
    ngu = _thay_ngu(monkeypatch, 8)
    adb = PA.PhimAdb(ThietBiGia([AdbError("x")] * 8), PhimGia(), lambda: True)
    with pytest.raises(_Dung):
        await adb.chay()
    assert max(ngu) == PA.CHO_LOI_TOI_DA_S and ngu[-1] == PA.CHO_LOI_TOI_DA_S


async def test_chay_tat_thi_khong_mo_luong_chi_cho_30_giay(monkeypatch):
    ngu = _thay_ngu(monkeypatch, 2)
    dev = ThietBiGia([])
    with pytest.raises(_Dung):
        await PA.PhimAdb(dev, PhimGia(), lambda: False).chay()                   # «tắt» hoặc chế độ «đóng ADB»
    assert dev.dich_vu == [] and ngu == [30, 30]


async def test_chay_bi_huy_thi_dong_luong_va_ngoai_le_huy_di_tiep(monkeypatch):
    _thay_ngu(monkeypatch, 5)
    luong = LuongGia([asyncio.CancelledError()])
    adb = PA.PhimAdb(ThietBiGia([luong]), PhimGia(), lambda: True)
    with pytest.raises(asyncio.CancelledError):
        await adb.chay()
    assert luong.da_dong and adb.dang_nghe is False
