"""Phím trên loa: nhận diện cử chỉ từ phím thô, bảng hành động mở rộng được, ô chọn, sự kiện, nối với kết nối mic. Không chạm loa thật."""

import asyncio
import json

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.r1_speaker import phim as P
from custom_components.r1_speaker.phim import NhanDien

from .test_den_nhac import _cong_trong, _khung_xuong, _noi_apk, _them_co_dau_nhan
from .test_mic_server import KHOA, khung_json
from .test_song_cong import _them


class GioGia:
    """Bộ hẹn giờ giả: ``tien(giay)`` chạy các hẹn đến hạn theo thứ tự."""

    def __init__(self):
        self.t = 0.0
        self.ds: list[list] = []

    def hen(self, giay, ham):
        muc = [self.t + giay, ham, True]
        self.ds.append(muc)

        def huy():
            muc[2] = False
        return huy

    def tien(self, giay):
        han = self.t + giay
        while True:
            dau = sorted((m for m in self.ds if m[2] and m[0] <= han), key=lambda m: m[0])
            if not dau:
                break
            m = dau[0]
            self.t, m[2] = m[0], False
            m[1]()
        self.t = han


def tao():
    g, ra = GioGia(), []
    return NhanDien(lambda ma, cc: ra.append((ma, cc)), g.hen), g, ra


def nhan(nd, g, ma=195, giu_ms=100):
    nd.xuong(ma)
    g.tien(giu_ms / 1000)
    nd.len(ma)


# ── Nhận diện cử chỉ ──────────────────────────────────────────────

def test_nhan_don_cho_het_khoang_roi_moi_ra_don():
    nd, g, ra = tao()
    nhan(nd, g)
    assert ra == []                                   # còn chờ có nhấn tiếp không
    g.tien(P.KHOANG_NHAN_MS / 1000 + 0.01)
    assert ra == [(195, "don")]


def test_nhan_hai_lan_trong_khoang_la_doi_va_ba_lan_ra_ba_ngay():
    nd, g, ra = tao()
    nhan(nd, g); g.tien(0.2); nhan(nd, g)
    g.tien(P.KHOANG_NHAN_MS / 1000 + 0.01)
    assert ra == [(195, "doi")]
    ra.clear()
    nhan(nd, g); g.tien(0.1); nhan(nd, g); g.tien(0.1); nhan(nd, g)
    assert ra == [(195, "ba")]                         # đủ ba lần là ra ngay, không chờ hết khoảng
    g.tien(2)
    assert ra == [(195, "ba")]                         # và không ra thêm lần nữa


def test_nhan_cach_nhau_qua_khoang_la_hai_lan_don_rieng():
    nd, g, ra = tao()
    nhan(nd, g); g.tien(P.KHOANG_NHAN_MS / 1000 + 0.05)
    nhan(nd, g); g.tien(P.KHOANG_NHAN_MS / 1000 + 0.05)
    assert ra == [(195, "don"), (195, "don")]


def test_giu_qua_nguong_ra_giu_mot_lan_va_nha_ra_khong_tinh_them_don():
    nd, g, ra = tao()
    nd.xuong(195)
    g.tien(P.NGUONG_GIU_MS / 1000 + 0.01)
    assert ra == [(195, "giu")]                        # ra ngay khi đủ ngưỡng, không chờ nhả
    nd.len(195)
    g.tien(2)
    assert ra == [(195, "giu")]


def test_hai_ma_phim_doc_lap():
    nd, g, ra = tao()
    nhan(nd, g, 195); nhan(nd, g, 116)
    g.tien(1)
    assert sorted(ra) == [(116, "don"), (195, "don")]


# ── Bảng hành động mở rộng được ────────────────────────────────

def test_them_hanh_dong_moi_chi_can_dang_ky_mot_ham_va_trung_ten_bi_chan():
    ten = "thu_nghiem_them_hanh_dong"
    assert ten not in P.danh_sach()
    try:
        @P.hanh_dong(ten, vi="Thử", en="Test")
        async def _x(ctx):
            return None
        assert ten in P.danh_sach() and P.nhan(ten) == "Thử" and P.nhan(ten, "en") == "Test"
        with pytest.raises(ValueError, match="trùng"):
            P.hanh_dong(ten, vi="a", en="b")(_x)
    finally:
        P._DANG_KY.pop(ten, None)


def test_hanh_dong_tich_hop_day_du_va_mac_dinh_giu_hanh_vi_cu():
    for ten in ("khong_lam_gi", "bat_tat_mic", "bat_tat_bluetooth", "phat_tam_dung", "dung_nhac", "bai_ke", "bai_truoc", "tang_am_luong",
                "giam_am_luong", "tat_tieng_loa", "bao_thuc_dung", "bao_thuc_hoan", "hen_gio_tat_nhac_30", "bat_tat_dam_thoai",
                "bat_tat_assist", "bat_tat_den_nhac", "bao_thuc_hoac_dam_thoai"):
        assert ten in P.danh_sach(), ten
    assert P.MAC_DINH == {"don": "bao_thuc_hoac_dam_thoai", "doi": "bat_tat_assist", "ba": "bat_tat_bluetooth", "giu": "bat_tat_den_nhac"}  # như AI box
    assert set(P.MAC_DINH.values()) <= set(P.danh_sach())


# ── Tích hợp HA ──────────────────────────────────────────────────

async def _lien_ket(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    await hass.async_block_till_done()
    return e, e.runtime_data.phim, e.runtime_data.mic_server, port


async def test_bon_o_chon_va_mot_thuc_the_su_kien_cho_phim(hass, r1):
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    for cc in P.CU_CHI:
        ent = reg.async_get_entity_id("select", "r1_speaker", f"{e.entry_id}_phim_{cc}")
        assert ent, cc
        assert hass.states.get(ent).state == P.MAC_DINH[cc]
        assert set(hass.states.get(ent).attributes["options"]) == set(P.danh_sach())
    ev = reg.async_get_entity_id("event", "r1_speaker", f"{e.entry_id}_phim")
    assert ev and set(hass.states.get(ev).attributes["event_types"]) == set(P.CU_CHI_SU_KIEN)


async def test_chon_hanh_dong_cho_cu_chi_roi_bam_phim_chay_dung_hanh_dong_va_phat_su_kien(hass, r1):
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    sel = reg.async_get_entity_id("select", "r1_speaker", f"{e.entry_id}_phim_ba")
    await hass.services.async_call("select", "select_option", {"entity_id": sel, "option": "tang_am_luong"}, blocking=True)
    assert phim.cau_hinh["ba"] == "tang_am_luong"
    goi = []
    hass.services.async_register("media_player", "volume_up", lambda c: goi.append(c.data["entity_id"]))
    phim._cu_chi_that(195, "ba")
    await hass.async_block_till_done()
    assert goi and goi[0].startswith("media_player.")
    ev = reg.async_get_entity_id("event", "r1_speaker", f"{e.entry_id}_phim")
    st = hass.states.get(ev)
    assert st.attributes["event_type"] == "ba" and st.attributes["phim"] == 195


async def test_mac_dinh_bon_cu_chi_chay_dung_thuc_the_nhu_ai_box_va_nhan_mot_lan_uu_tien_tat_bao_thuc(hass, r1):
    """1 lần = tắt báo thức đang kêu, không thì đàm thoại; 2 lần = Assist; 3 lần = Bluetooth; giữ = đèn theo nhạc."""
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    toggle = []
    hass.services.async_register("switch", "toggle", lambda c: toggle.append(c.data["entity_id"]))
    ent = lambda khoa: reg.async_get_entity_id("switch", "r1_speaker", f"{e.entry_id}_{khoa}")   # noqa: E731

    for cu_chi, khoa in (("doi", "assist"), ("ba", "bluetooth"), ("giu", "music_light"), ("don", "intercom_open")):
        toggle.clear()
        phim._cu_chi_that(195, cu_chi)
        await hass.async_block_till_done()
        assert toggle == [ent(khoa)] and toggle[0], (cu_chi, khoa)

    bt, tat = e.runtime_data.bao_thuc, []

    async def tat_gia():
        tat.append(1)

    bt.tat, bt.dang_keu = tat_gia, "bt1"                    # báo thức đang kêu: nhấn 1 lần chỉ tắt báo thức
    toggle.clear()
    phim._cu_chi_that(195, "don")
    await hass.async_block_till_done()
    assert tat == [1] and toggle == []


async def test_phim_khac_ma_hanh_dong_chi_phat_su_kien_khong_chay_hanh_dong(hass, r1):
    e, phim, _, _p = await _lien_ket(hass, r1)
    goi = []
    hass.services.async_register("switch", "toggle", lambda c: goi.append(1))
    phim._cu_chi_that(24, "don")                        # mã phím không nằm trong phim_ma (mặc định chỉ 195)
    await hass.async_block_till_done()
    assert goi == []
    reg = er.async_get(hass)
    ev = reg.async_get_entity_id("event", "r1_speaker", f"{e.entry_id}_phim")
    assert hass.states.get(ev).attributes["event_type"] == "don" and hass.states.get(ev).attributes["phim"] == 24


async def test_hanh_dong_hong_khong_lam_hong_vong_nghe_phim(hass, r1, caplog):
    e, phim, _, _p = await _lien_ket(hass, r1)
    ten = "thu_nghiem_hanh_dong_hong"

    @P.hanh_dong(ten, vi="Hỏng", en="Broken")
    async def _hong(ctx):
        raise RuntimeError("cố ý hỏng")
    try:
        phim.cau_hinh["don"] = ten
        phim._cu_chi_that(195, "don")                    # hành động hỏng: chỉ ghi cảnh báo, không ném lỗi ra ngoài
        await hass.async_block_till_done()
        assert any("phím don" in r.getMessage() and "cố ý hỏng" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)
        phim.cau_hinh["don"] = "khong_lam_gi"
        phim._cu_chi_that(195, "don")                    # và vòng nghe vẫn chạy bình thường sau đó
        await hass.async_block_till_done()
    finally:
        P._DANG_KY.pop(ten, None)


async def test_phim_tho_tu_apk_qua_ket_noi_mic_that_thanh_cu_chi_doi_va_khung_sai_bi_bo(hass, r1):
    e, phim, mic, port = await _lien_ket(hass, r1)
    ra = []
    phim.tren_su_kien.append(lambda cc, ma: ra.append((cc, ma)))
    reader, writer = await _noi_apk(e, port)
    for _ in range(2):                                   # hai lần nhấn nhanh của nút giữa (mã 195)
        writer.write(khung_json({"type": "phim", "ma": 195, "xuong": True}))
        await writer.drain()
        await asyncio.sleep(0.15)
        writer.write(khung_json({"type": "phim", "ma": 195, "xuong": False}))
        await writer.drain()
        await asyncio.sleep(0.15)
    for _ in range(300):
        if ("doi", 195) in ra:
            break
        await asyncio.sleep(0.01)
    assert ra == [("doi", 195)]
    # khung sai dạng bị bỏ, không làm đứt kết nối
    writer.write(khung_json({"type": "phim", "ma": 0, "xuong": True}))
    writer.write(khung_json({"type": "phim", "ma": 195, "xuong": "co"}))
    writer.write(khung_json({"type": "phim", "ma": True, "xuong": True}))
    await writer.drain()
    await asyncio.sleep(0.2)
    assert ra == [("doi", 195)] and mic.receiving
    writer.close()


async def _khung_cau_hinh_phim(reader) -> dict:
    khung = {}
    for _ in range(6):                                   # HA gửi xuống vài khung sau khi nối (đèn, âm lượng...): tìm khung cấu hình phím
        khung = json.loads(await _khung_xuong(reader, ca_bat_tay=True))
        if khung.get("type") == "phim_cau_hinh":
            break
    return khung


async def test_nguon_phim_mac_dinh_adb_thi_khong_dong_ma_phim_voi_apk(hass, r1):
    """Nguồn phím mặc định là ADB (``phim_adb``): HA báo APK danh sách RỖNG để APK tự xử lý phím cũ, tránh một phím chạy hai lần."""
    e, phim, mic, port = await _lien_ket(hass, r1)
    reader, writer = await _noi_apk(e, port)
    assert await _khung_cau_hinh_phim(reader) == {"type": "phim_cau_hinh", "ma": [], "do": False}
    writer.close()


async def test_nguon_phim_apk_thi_apk_nhan_cau_hinh_phim_tu_ha(hass, r1):
    port = _cong_trong()
    e = await _them(hass, r1, mic_host="127.0.0.1", mic_port=9, mic_listen_port=port, mic_listen_key=KHOA, phim_nguon="apk")
    reader, writer = await _noi_apk(e, port)
    assert await _khung_cau_hinh_phim(reader) == {"type": "phim_cau_hinh", "ma": [195], "do": False}
    writer.close()
