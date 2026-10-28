"""Đèn qua APK (không ADB): hiệu ứng có sẵn của firmware + bộ chọn đường theo chế độ «đóng ADB». APK/loa giả; không chạm loa thật."""

import asyncio
import random
import re
from pathlib import Path

import pytest

from custom_components.r1_speaker import den_apk, den_firmware as fw
from custom_components.r1_speaker.den_apk import ApkLights, LightsRouter
from custom_components.r1_speaker.den_port import LightsError


class MayChu:
    """Đầu nhận mic giả: ghi các ID đã gửi; ``receiving`` False thì gửi là ConnectionError như thật."""

    def __init__(self):
        self.receiving = True
        self.den_san_sang = True
        self.da_gui: list[int] = []

    async def gui_hieu_ung(self, ma):
        if not self.receiving:
            raise ConnectionError("loa chưa nối vào đầu nhận mic")
        if ma not in fw.ID_HOP_LE:
            raise ValueError("ngoài danh sách")
        self.da_gui.append(ma)


@pytest.fixture(autouse=True)
def _nhanh(monkeypatch):
    monkeypatch.setattr(den_apk, "BUOC_TOI_THIEU_S", 0.01)


def tao():
    mc = MayChu()
    return ApkLights(mc, rng=random.Random(1)), mc


async def cho(fn, timeout=2.0):
    han = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < han:
        if fn():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("hết giờ chờ")


# ── Hợp đồng với APK ─────────────────────────────────────────────

def test_danh_sach_id_o_ha_khop_danh_sach_cho_phep_o_apk():
    """HA chỉ gửi ID mà APK chịu nhận: lệch là lệnh bị bỏ im lặng trên loa."""
    java = (Path(__file__).parents[1] / "apk/nguon/src/vn/r1/bodam/TrungTamTin.java").read_text(encoding="utf-8")
    khoi = re.search(r"HIEU_UNG_HOP_LE = \{(.*?)\};", java, re.S).group(1)
    apk = {int(x) for x in re.findall(r"\d+", khoi)}
    assert fw.ID_HOP_LE <= apk, sorted(fw.ID_HOP_LE - apk)


# ── Một hiệu ứng, một vùng ───────────────────────────────────────

async def test_dao_sang_co_dinh_xanh_la_la_id_501_va_tat_la_504():
    a, mc = tao()
    await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert mc.da_gui == [501] and a.hieu_ung_chay() is False
    await a.ap_dung("day", "tat", {})
    assert mc.da_gui == [501, 504]


async def test_mau_tuy_y_duoc_lam_tron_ve_mau_firmware_gan_nhat():
    a, mc = tao()
    await a.ap_dung("day", "co_dinh", {"mau": "#fe0505"})          # gần đỏ nhất
    assert mc.da_gui == [500]


async def test_tho_dung_id_tho_cua_firmware_va_khong_lap_tu_ha():
    a, mc = tao()
    await a.ap_dung("day", "tho", {"mau": "#0000ff"})
    await asyncio.sleep(0.05)
    assert mc.da_gui == [203] and a.hieu_ung_chay() is False        # firmware tự lặp


async def test_do_sang_hoac_master_bang_0_la_tat():
    a, mc = tao()
    await a.ap_dung("day", "co_dinh", {"mau": "#ff0000", "do_sang": 100}, master=0)
    assert mc.da_gui == [504]


async def test_ap_lai_dung_hieu_ung_dang_chay_khong_gui_thua():
    a, mc = tao()
    await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert mc.da_gui == [501]


async def test_cau_vong_la_vong_lap_doi_lan_luot_sau_mau_va_dung_khi_tat():
    a, mc = tao()
    await a.ap_dung("day", "cau_vong_fw", {"toc_do": 400})
    await cho(lambda: len(mc.da_gui) >= 8)
    assert mc.da_gui[:6] == list(fw.CAU_VONG) and a.hieu_ung_chay() is True
    await a.ap_dung("day", "tat", {})
    n = len(mc.da_gui)
    await asyncio.sleep(0.1)
    assert len(mc.da_gui) == n and a.hieu_ung_chay() is False and mc.da_gui[-1] == 504


async def test_cau_vong_chieu_nguoc_dao_thu_tu():
    a, mc = tao()
    await a.ap_dung("day", "cau_vong_fw", {"chieu": "nguoc", "toc_do": 400})
    await cho(lambda: len(mc.da_gui) >= 6)
    assert mc.da_gui[:6] == list(reversed(fw.CAU_VONG))
    await a.dung()


@pytest.mark.parametrize("hieu_ung", ["nhap_nhay", "nhip_tim", "chop", "phao_hoa", "cau_vong", "cau_vong_xoay", "sao_choi"])
async def test_moi_hieu_ung_con_lai_chay_bang_id_hop_le_va_dung_duoc(hieu_ung):
    a, mc = tao()
    await a.ap_dung("day", hieu_ung, {"mau": "#00ffff"})
    await cho(lambda: len(mc.da_gui) >= 4)
    assert set(mc.da_gui) <= fw.ID_HOP_LE
    await a.dung()
    assert a.hieu_ung_chay() is False


async def test_vien_sang_chay_duoi_va_tho():
    a, mc = tao()
    await a.ap_dung("vien", "sang", {})
    await a.ap_dung("vien", "chay_duoi", {})
    assert mc.da_gui == [503, 1] and a.hieu_ung_chay() is False     # chạy đuổi do firmware tự lặp
    await a.ap_dung("vien", "tho", {"toc_do": 400})
    await cho(lambda: len(mc.da_gui) >= 5)
    assert set(mc.da_gui[2:]) <= {503, 505}
    await a.dung()


# ── Firmware chỉ giữ MỘT hiệu ứng ────────────────────────────────

async def test_day_dang_sang_thi_vien_khong_duoc_chen_va_tat_vien_khong_dong_hieu_ung_day():
    """Lỗi thật 22/10/2026: gửi ID tắt viền 505 làm đóng luôn hiệu ứng đáy vừa bật (đáy không sáng, viền thì sáng)."""
    a, mc = tao()
    await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    await a.ap_dung("vien", "sang", {})                              # bị bỏ qua: ưu tiên đáy
    await a.ap_dung("vien", "tat", {})                               # KHÔNG được gửi 505
    assert mc.da_gui == [501]


async def test_day_tat_roi_vien_moi_duoc_sang():
    a, mc = tao()
    await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    await a.ap_dung("day", "tat", {})
    await a.ap_dung("vien", "sang", {})
    assert mc.da_gui == [501, 504, 503]


async def test_tat_ca_hai_vung_khi_khong_vung_nao_giu_hieu_ung():
    a, mc = tao()
    await a.ap_dung("day", "tat", {})
    await a.ap_dung("vien", "tat", {})
    assert mc.da_gui == [504, 505]


# ── Mất kết nối ──────────────────────────────────────────────────

async def test_gui_luc_loa_chua_noi_bao_loi_ro_va_ap_lai_duoc_khi_noi_lai():
    a, mc = tao()
    mc.receiving = False
    with pytest.raises(LightsError, match="chưa nối"):
        await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert a.available is False and "chưa nối" in a.ly_do
    mc.receiving = True
    await a.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert mc.da_gui == [501] and a.ly_do != ""


async def test_vong_lap_dung_khi_mat_ket_noi_va_chay_lai_khi_ap_lai():
    a, mc = tao()
    await a.ap_dung("day", "cau_vong_fw", {})
    await cho(lambda: len(mc.da_gui) >= 2)
    mc.receiving = False
    await cho(lambda: a.hieu_ung_chay() is False)                    # vòng tự dừng, không ném lỗi ra ngoài
    mc.receiving = True
    n = len(mc.da_gui)
    await a.ap_dung("day", "cau_vong_fw", {})                        # loa nối lại → áp lại → chạy lại
    await cho(lambda: len(mc.da_gui) > n)
    await a.dung()


async def test_apk_cu_khong_bao_che_do_firmware_thi_chua_san_sang():
    a, mc = tao()
    mc.den_san_sang = None
    assert a.available is False and a.ly_do == "CHO_DICH_VU_DEN"


# ── Bộ chọn đường theo chế độ «đóng ADB» ─────────────────────────

class Adb:
    name = "adb"
    available = True
    ly_do = "ADB_NOI_THANG"
    loi = None
    dev = object()
    khi_roi = None

    def __init__(self):
        self.goi = []
        self.hong = False

    def dang_ap_dung(self, yen_s=2.0):
        return False

    def hieu_ung_chay(self):
        return False

    async def ap_dung(self, vung, hieu_ung, params, master=100):
        self.goi.append((vung, hieu_ung))
        if self.hong:
            raise LightsError("ADB: adbd không trả lời")

    async def tat(self):
        self.goi.append("tat")

    async def dung(self):
        self.goi.append("dung")


def router(dong):
    adb, (apk, mc) = Adb(), tao()
    cfg = {"dong": dong}
    return LightsRouter(adb, apk, lambda: cfg["dong"]), adb, apk, mc, cfg


async def test_che_do_dong_adb_chi_dung_apk_va_khong_cham_adb():
    r, adb, apk, mc, _ = router(True)
    assert r.name == "apk" and r.available is True
    await r.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    await r.tat()
    assert adb.goi == [] and mc.da_gui[0] == 501


async def test_che_do_giu_adb_dung_adb_va_khong_dung_apk():
    r, adb, apk, mc, _ = router(False)
    assert r.name == "adb"
    await r.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert adb.goi == [("day", "co_dinh")] and mc.da_gui == []


async def test_giu_adb_nhung_adb_loi_thi_du_phong_bang_apk():
    r, adb, apk, mc, _ = router(False)
    adb.hong = True
    await r.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert mc.da_gui == [501]
    mc.den_san_sang = None                                            # APK cũng không sẵn sàng: lỗi của ADB phải lộ ra
    with pytest.raises(LightsError, match="adbd"):
        await r.ap_dung("day", "co_dinh", {"mau": "#ff0000"})


async def test_roi_che_do_dong_adb_thi_vong_hieu_ung_apk_phai_dung_khong_tranh_den_voi_adb():
    r, adb, apk, mc, cfg = router(True)
    await r.ap_dung("day", "cau_vong_fw", {})
    await cho(lambda: apk.hieu_ung_chay())
    cfg["dong"] = False
    await r.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert apk.hieu_ung_chay() is False and adb.goi == [("day", "co_dinh")]


async def test_router_chuyen_tiep_khi_roi_va_dev_cho_phan_ADB():
    r, adb, *_ = router(False)
    cb = lambda: None
    r.khi_roi = cb
    assert adb.khi_roi is cb and r.dev is adb.dev
