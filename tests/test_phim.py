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


def test_danh_muc_hanh_dong_con_du_de_lam_dich_vu_sau_nay():
    for ten in ("khong_lam_gi", "bat_tat_mic", "bat_tat_bluetooth", "phat_tam_dung", "dung_nhac", "bai_ke", "bai_truoc", "tang_am_luong",
                "giam_am_luong", "tat_tieng_loa", "bao_thuc_dung", "bao_thuc_hoan", "hen_gio_tat_nhac_30", "bat_tat_dam_thoai",
                "bat_tat_assist", "bat_tat_den_nhac", "bao_thuc_hoac_dam_thoai"):
        assert ten in P.danh_sach(), ten


# ── Tích hợp HA ──────────────────────────────────────────────────

async def _lien_ket(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    await hass.async_block_till_done()
    return e, e.runtime_data.phim, e.runtime_data.mic_server, port


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


async def test_phim_khong_con_o_chon_hanh_dong_chi_con_thuc_the_su_kien(hass, r1):
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    for cc in P.CU_CHI:
        assert reg.async_get_entity_id("select", "r1_speaker", f"{e.entry_id}_phim_{cc}") is None, cc
    ev = reg.async_get_entity_id("event", "r1_speaker", f"{e.entry_id}_phim")
    assert ev and set(hass.states.get(ev).attributes["event_types"]) == set(P.CU_CHI_SU_KIEN)
    assert not hasattr(phim, "cau_hinh") and not hasattr(P, "MAC_DINH")


async def test_cu_chi_chi_phat_su_kien_khong_chay_hanh_dong_nao_ke_ca_khi_la_mat_dinh_cu(hass, r1):
    """Không còn hành động gắn sẵn: bốn cử chỉ (kể cả đơn/đúp/ba/giữ của mặc định cũ) chỉ bắn sự kiện, việc làm gì do tự động hoá."""
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    goi = []
    for dom, dv in (("switch", "toggle"), ("script", "turn_on"), ("media_player", "volume_up"), ("media_player", "media_play_pause")):
        hass.services.async_register(dom, dv, lambda c: goi.append(c.service))
    for cu_chi in P.CU_CHI:
        phim._cu_chi_that(195, cu_chi)
    await hass.async_block_till_done()
    assert goi == [], goi
    ev = reg.async_get_entity_id("event", "r1_speaker", f"{e.entry_id}_phim")
    st = hass.states.get(ev)
    assert st.attributes["event_type"] == "giu" and st.attributes["phim"] == 195


async def test_select_phim_cu_cua_ban_truoc_bi_go_khoi_so_thuc_the_khi_nap_lai(hass, r1):
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    cu = [reg.async_get_or_create("select", "r1_speaker", f"{e.entry_id}{hau}", config_entry=e).entity_id
          for hau in ("_phim_don", "_phim_chay_don", "_phim_giu")]
    assert all(reg.async_get(x) for x in cu)
    assert await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    assert not any(reg.async_get(x) for x in cu), cu


def test_moi_hanh_dong_cu_cua_nut_deu_co_dich_vu_hoac_ly_do_khong_can():
    """Nút giữa không còn hành động gắn sẵn: mỗi hành động trong danh mục phải gọi được bằng dịch vụ (hoặc đã có dịch vụ riêng/không cần)."""
    khong_can = {"khong_lam_gi", "chay_thuc_the", "bao_thuc_dung", "bao_thuc_hoan"}      # bao_thuc_dung = bao_thuc_tat, bao_thuc_hoan đã là dịch vụ sẵn có
    assert set(P._DANG_KY) - khong_can == set(P.DICH_VU_HANH_DONG), set(P._DANG_KY) ^ set(P.DICH_VU_HANH_DONG)


async def test_dich_vu_hanh_dong_goi_dung_thuc_the_cua_loa_va_tu_choi_thuc_the_la(hass, r1):
    from homeassistant.exceptions import ServiceValidationError
    e, phim, _, _p = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    toggle = []
    hass.services.async_register("switch", "toggle", lambda c: toggle.append(c.data["entity_id"]))
    ent = lambda khoa: reg.async_get_entity_id("switch", "r1_speaker", f"{e.entry_id}_{khoa}")   # noqa: E731
    anh = reg.async_get_entity_id("event", "r1_speaker", f"{e.entry_id}_phim")                    # thực thể bất kỳ của loa
    for dv, khoa in (("bat_tat_assist", "assist"), ("bat_tat_bluetooth", "bluetooth"), ("bat_tat_den_nhac", "music_light"), ("bat_tat_dam_thoai", "intercom_open")):
        assert hass.services.has_service("r1_speaker", dv), dv
        toggle.clear()
        await hass.services.async_call("r1_speaker", dv, {"entity_id": anh}, blocking=True)
        assert toggle == [ent(khoa)] and toggle[0], (dv, toggle)
    goi = []
    hass.services.async_register("media_player", "volume_up", lambda c: goi.append(("up", c.data["entity_id"])))
    hass.services.async_register("media_player", "media_next_track", lambda c: goi.append(("next", c.data["entity_id"])))
    await hass.services.async_call("r1_speaker", "tang_am_luong", {"entity_id": anh}, blocking=True)
    await hass.services.async_call("r1_speaker", "bai_ke", {"entity_id": anh}, blocking=True)
    assert [g[0] for g in goi] == ["up", "next"] and all(g[1].startswith("media_player.") for g in goi), goi
    # Dịch vụ sẵn có không bị ghi đè; thực thể không phải của r1_speaker bị từ chối
    assert hass.services.has_service("r1_speaker", "bao_thuc_tat") and hass.services.has_service("r1_speaker", "bao_thuc_hoan")
    hass.states.async_set("light.khac", "off")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("r1_speaker", "bat_tat_assist", {"entity_id": "light.khac"}, blocking=True)

