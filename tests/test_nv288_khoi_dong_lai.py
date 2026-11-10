"""NV288 — khởi động lại loa theo lịch (giờ + ngày trong tuần), hoãn khi bận, nhớ qua khởi động lại HA; cảm biến «Loa phản hồi» phân biệt
treo / mất mạng; tự phục hồi khi treo (mặc định TẮT, không bao giờ lặp). Giờ là giờ GIẢ (freezer): không test nào ngủ thật. Mọi đường đi
qua tích hợp thật dựng bằng ``MockConfigEntry`` và nhịp thời gian thật của HA (``async_fire_time_changed``); chỗ giả duy nhất là thiết bị ADB
(không chạm loa thật) và, ở ca «mất mạng», bước bắt tay TCP."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.r1_speaker import const
from custom_components.r1_speaker.adb_client import AdbError
from custom_components.r1_speaker.client import REBOOT_SHELL, REBOOT_SHELLS, R1Error
from custom_components.r1_speaker.const import DOMAIN
from custom_components.r1_speaker.dam_thoai import Session

from .test_dlna import _nhanh_hon, _phat, dmr  # noqa: F401 — renderer DLNA giả + hàm phát thật qua media_player.r1_loa

VN = ZoneInfo("Asia/Ho_Chi_Minh")
PLAYER = "media_player.r1_loa"
CAM_BIEN = "binary_sensor.r1_loa_phan_hoi"
LAN_CUOI = "sensor.r1_khoi_dong_lai_cuoi"
NUT = "button.r1_khoi_dong_lai"


def gio(ngay: str, h: int, m: int = 0, s: int = 0) -> datetime:
    y, mo, d = (int(x) for x in ngay.split("-"))
    return datetime(y, mo, d, h, m, s, tzinfo=VN)


class DevGia:
    """Thay ``apps.dev`` (ADB): đếm lệnh khởi động lại, có thể cho hỏng hoặc coi như ADB không nối được."""

    def __init__(self):
        self.reboot_goi = 0
        self.qua_8080 = 0
        self.loi: str | None = None
        self.nghe = True

    async def reboot(self):
        self.reboot_goi += 1
        if self.loi:
            raise AdbError(self.loi)

    async def con_nghe_mang(self):
        return self.nghe

    async def shell(self, *a, **k):                                      # các thực thể Cập nhật hỏi ADB theo chu kỳ: loa giả không có ADB
        raise AdbError("loa giả không có ADB")


@pytest.fixture
def freezer_tick():
    """Giờ giả nhưng vẫn CHẠY tiếp từng giây thật: ca có nhạc phát thật qua renderer giả chờ bằng ``asyncio.sleep`` nên đồng hồ đóng băng
    hẳn sẽ treo. Các ca khác dùng ``freezer`` đóng băng."""
    with freeze_time("2026-11-03 20:00:00", tick=True) as f:
        yield f


@pytest.fixture(autouse=True)
async def _mui_gio(hass):
    await hass.config.async_set_time_zone("Asia/Ho_Chi_Minh")


async def dung(hass, r1, freezer, luc, *, entry_id="nv288", **tuy_chon):
    """Dựng tích hợp ở giờ ``luc`` (giờ địa phương), thay ADB bằng bản giả. Trả (entry, dev)."""
    freezer.move_to(luc)
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port}, options=tuy_chon,
                        unique_id=f"127.0.0.1:{r1.port}", entry_id=entry_id)
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    dev = DevGia()
    e.runtime_data.apps.dev = dev
    # Đường CHÍNH là cổng 8080 (không cần ADB), ADB dự phòng: đếm cả hai vào ``reboot_goi`` để các ca cũ vẫn đo «đã gửi bao nhiêu lệnh khởi động lại»;
    # ``dev.qua_8080`` đếm riêng đường 8080.
    # (Giờ giả đóng băng làm kết nối websocket thật tới loa giả hết hạn ngay, nên đây là BẢN GIẢ của lệnh 8080 theo trạng thái máy chủ giả: tắt máy
    # chủ (``r1.stop()``) = cổng 8080 hỏng. Việc gửi đúng khung ``shell`` thật có test riêng ở test_cai_ung_dung.)
    async def dem_8080(cach="adb_cuc_bo"):
        dev.reboot_goi += 1
        dev.qua_8080 += 1
        if r1._runner is None:
            raise R1Error("cổng 8080 đã tắt")
        r1.received.append({"type": "shell", "type_id": "ha", "shell": dict(REBOOT_SHELLS)[cach]})
    e.runtime_data.client.reboot_shell = dem_8080
    # Vòng hỏi get_info tự chạy bằng hẹn giờ riêng của HA; khi cho giờ giả nhảy cả phút, kết nối đang dở của nó hết hạn giả. Tắt hẹn giờ
    # đó, mỗi bước thời gian ``toi`` tự gọi đúng một lần đọc get_info (cùng hàm coordinator, cùng cách ghi thành công / thất bại).
    e.runtime_data.update_interval = None
    e.runtime_data._unschedule_refresh()
    return e, dev


async def toi(hass, freezer, luc):
    """Cho giờ giả trôi tới ``luc`` rồi để HA chạy mọi hẹn giờ đã tới hạn (đúng đường thật của nhịp)."""
    freezer.move_to(luc)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if getattr(entry, "runtime_data", None) is not None:
            await entry.runtime_data.async_refresh()
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def tien(hass, freezer, tu, den, buoc=30):
    """Đi từ ``tu`` tới ``den`` từng bước ``buoc`` giây, mỗi bước một nhịp (như HA chạy thật)."""
    t = tu
    while t < den:
        t = min(t + timedelta(seconds=buoc), den)
        await toi(hass, freezer, t)
    return t


LICH_MOI_NGAY = dict(khoi_dong_lai_bat=True, khoi_dong_lai_gio="04:00")


# ── Lịch: giờ + ngày trong tuần ─────────────────────────────────────────────────

async def test_toi_gio_lich_khoi_dong_lai_dung_mot_lan_roi_hom_sau_lai_mot_lan(hass, r1, freezer, caplog):
    caplog.set_level(logging.INFO)
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50), **LICH_MOI_NGAY)
    t = await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 3, 59, 30))
    assert dev.reboot_goi == 0                                           # chưa tới giờ
    t = await tien(hass, freezer, t, gio("2026-11-04", 5, 0))
    assert dev.reboot_goi == 1                                           # tới giờ: ĐÚNG một lần dù nhịp chạy hàng chục lần sau đó
    assert "lý do: lịch" in caplog.text
    t = await tien(hass, freezer, t, gio("2026-11-05", 3, 59), buoc=600)
    assert dev.reboot_goi == 1
    await tien(hass, freezer, t, gio("2026-11-05", 4, 2))
    assert dev.reboot_goi == 2                                           # hôm sau lại một lần


@pytest.mark.parametrize("ngay_chon, ngay_thu, mong", [
    (["t2", "t4"], "2026-11-03", 0),      # thứ ba KHÔNG được chọn
    (["t2", "t4"], "2026-11-04", 1),      # thứ tư được chọn
    (["t2", "t4"], "2026-11-05", 0),      # thứ năm không
    (["t2", "t6", "cn"], "2026-11-06", 1),
    (["t2", "t6", "cn"], "2026-11-08", 1),
    (["t2", "t6", "cn"], "2026-11-07", 0),
    ([], "2026-11-04", 0),                # bỏ chọn hết: không ngày nào
])
async def test_chi_khoi_dong_lai_vao_cac_thu_da_chon(hass, r1, freezer, ngay_chon, ngay_thu, mong):
    e, dev = await dung(hass, r1, freezer, gio(ngay_thu, 3, 50), khoi_dong_lai_ngay=ngay_chon, **LICH_MOI_NGAY)
    await tien(hass, freezer, gio(ngay_thu, 3, 50), gio(ngay_thu, 4, 10))
    assert dev.reboot_goi == mong


async def test_lich_tat_thi_khong_bao_gio_khoi_dong_lai(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50))      # mặc định TẮT
    await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 4, 30))
    assert dev.reboot_goi == 0


async def test_gio_lech_phut_van_dung_gio_dat(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 22, 0), khoi_dong_lai_bat=True, khoi_dong_lai_gio="23:45")
    t = await tien(hass, freezer, gio("2026-11-04", 22, 0), gio("2026-11-04", 23, 44, 30), buoc=300)
    assert dev.reboot_goi == 0
    await tien(hass, freezer, t, gio("2026-11-04", 23, 47))
    assert dev.reboot_goi == 1


# ── Hoãn khi loa bận ────────────────────────────────────────────────────────────

async def test_dang_phat_nhac_thi_hoan_roi_khoi_dong_khi_nhac_ngung(hass, r1, dmr, freezer_tick, caplog):
    freezer = freezer_tick
    r1.received.append({"type": "Set_DLNA_Open", "open": True})        # renderer giả coi là DLNA đã bật
    caplog.set_level(logging.INFO)
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50), **LICH_MOI_NGAY)
    await _phat(hass)                                                    # nhạc phát THẬT qua media_player.r1_loa → renderer giả
    assert hass.states.get(PLAYER).state == "playing"
    t = await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 4, 20))
    assert dev.reboot_goi == 0 and "hoãn" in caplog.text                 # tới giờ từ 04:00 mà nhạc còn phát: hoãn
    assert hass.states.get(LAN_CUOI).attributes["dang_hoan"] == "đang phát nhạc"
    await hass.services.async_call("media_player", "media_stop", {"entity_id": PLAYER}, blocking=True)
    await tien(hass, freezer, t, gio("2026-11-04", 4, 21))
    assert dev.reboot_goi == 1
    assert hass.states.get(LAN_CUOI).attributes["dang_hoan"] is None


async def test_co_phien_dam_thoai_thi_hoan_va_het_han_hoan_thi_van_khoi_dong(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50), **LICH_MOI_NGAY)
    e.runtime_data.talk.session = Session("assist")                      # đúng thứ mã đọc: phiên đang mở
    t = await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 4, 0) + timedelta(minutes=const.KDL_HOAN_TOI_DA_PHUT - 1))
    assert dev.reboot_goi == 0
    await tien(hass, freezer, t, gio("2026-11-04", 4, 0) + timedelta(minutes=const.KDL_HOAN_TOI_DA_PHUT + 2))
    assert dev.reboot_goi == 1                                           # hết hạn hoãn: khởi động dù phiên chưa đóng
    assert hass.states.get(LAN_CUOI).attributes["chi_tiet"].startswith("đã hoãn")


async def test_bao_thuc_dang_keu_cung_la_ban(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50), **LICH_MOI_NGAY)
    e.runtime_data.bao_thuc.dang_keu = "bt1"
    t = await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 4, 10))
    assert dev.reboot_goi == 0
    e.runtime_data.bao_thuc.dang_keu = None
    await tien(hass, freezer, t, gio("2026-11-04", 4, 12))
    assert dev.reboot_goi == 1


async def test_hoan_qua_nua_dem_van_la_luot_cua_hom_truoc_va_khong_khoi_dong_hai_lan(hass, r1, dmr, freezer_tick):
    freezer = freezer_tick
    r1.received.append({"type": "Set_DLNA_Open", "open": True})        # renderer giả coi là DLNA đã bật
    e, dev = await dung(hass, r1, freezer, gio("2026-11-03", 23, 40), khoi_dong_lai_bat=True, khoi_dong_lai_gio="23:50")
    await _phat(hass)                                                    # nhạc phát THẬT qua media_player.r1_loa → renderer giả
    assert hass.states.get(PLAYER).state == "playing"
    t = await tien(hass, freezer, gio("2026-11-03", 23, 40), gio("2026-11-04", 0, 20))
    assert dev.reboot_goi == 0                                           # đang hoãn, đã sang ngày mới
    await hass.services.async_call("media_player", "media_stop", {"entity_id": PLAYER}, blocking=True)
    t = await tien(hass, freezer, t, gio("2026-11-04", 0, 22))
    assert dev.reboot_goi == 1
    assert e.runtime_data.khoi_dong_lai.ngay_da_chay == "2026-11-03"     # tính cho lượt của ngày 03, không phải ngày 04
    t = await tien(hass, freezer, t, gio("2026-11-04", 23, 45), buoc=900)
    assert dev.reboot_goi == 1                                           # lượt 23:50 ngày 04 chưa tới
    await tien(hass, freezer, t, gio("2026-11-04", 23, 52))
    assert dev.reboot_goi == 2


async def test_lich_chi_t3_00_05_khong_chay_o_cuoi_ngay_t2(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-02", 23, 40), khoi_dong_lai_bat=True, khoi_dong_lai_gio="00:05",
                        khoi_dong_lai_ngay=["t3"])
    t = await tien(hass, freezer, gio("2026-11-02", 23, 40), gio("2026-11-03", 0, 4))
    assert dev.reboot_goi == 0                                           # thứ hai không chọn; 00:05 thứ ba chưa tới
    await tien(hass, freezer, t, gio("2026-11-03", 0, 7))
    assert dev.reboot_goi == 1


# ── Nhớ qua khởi động lại HA; vừa đổi lịch; HA bật lại muộn ────────────────────────

async def test_da_toi_lich_hom_nay_thi_khoi_dong_lai_ha_khong_khoi_dong_loa_lan_hai(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50), **LICH_MOI_NGAY)
    t = await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 4, 5))
    assert dev.reboot_goi == 1
    assert await hass.config_entries.async_reload(e.entry_id)             # HA nạp lại tích hợp: cờ phải còn
    await hass.async_block_till_done()
    dev2 = DevGia()
    e.runtime_data.apps.dev = dev2
    await tien(hass, freezer, t, gio("2026-11-04", 4, 40))
    assert dev2.reboot_goi == 0
    assert hass.states.get(LAN_CUOI).attributes["ly_do"] == "lich"       # lần cuối cũng được nhớ


async def test_bat_lich_hoac_doi_gio_luc_da_qua_gio_thi_khong_khoi_dong_ngay(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 4, 30), khoi_dong_lai_gio="04:00")     # lịch đang tắt
    await tien(hass, freezer, gio("2026-11-04", 4, 30), gio("2026-11-04", 4, 31))
    hass.config_entries.async_update_entry(e, options={**e.options, "khoi_dong_lai_bat": True})
    await tien(hass, freezer, gio("2026-11-04", 4, 31), gio("2026-11-04", 4, 40))
    assert dev.reboot_goi == 0                                           # 04:00 hôm nay đã qua TRƯỚC khi bật lịch
    hass.config_entries.async_update_entry(e, options={**e.options, "khoi_dong_lai_gio": "04:20"})
    await tien(hass, freezer, gio("2026-11-04", 4, 40), gio("2026-11-04", 4, 50))
    assert dev.reboot_goi == 0                                           # đổi sang giờ đã qua cũng vậy
    hass.config_entries.async_update_entry(e, options={**e.options, "khoi_dong_lai_gio": "05:00"})
    await tien(hass, freezer, gio("2026-11-04", 4, 50), gio("2026-11-04", 5, 2))
    assert dev.reboot_goi == 1                                           # giờ SAU lúc đổi thì chạy


@pytest.mark.parametrize("gio_ha_len, mong", [((4, 40), 1), ((6, 30), 0)])
async def test_ha_bat_lai_muon_thi_bu_trong_cua_so_con_qua_cua_so_thi_bo_luot(hass, r1, freezer, hass_storage, gio_ha_len, mong):
    hass_storage["r1_speaker.khoi_dong_lai.nv288"] = {"version": 1, "minor_version": 1, "key": "r1_speaker.khoi_dong_lai.nv288", "data": {
        "ngay_da_chay": "2026-11-03", "lan_cuoi": None, "tu_phuc_hoi_cuoi": None,
        "chu_ky": [True, "04:00", ["t2", "t3", "t4", "t5", "t6", "t7", "cn"]],
        "co_hieu_luc_tu": gio("2026-10-20", 9).isoformat()}}
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", *gio_ha_len), **LICH_MOI_NGAY)
    await tien(hass, freezer, gio("2026-11-04", *gio_ha_len), gio("2026-11-04", gio_ha_len[0], gio_ha_len[1] + 2))
    assert dev.reboot_goi == mong


# ── Lý do và kết quả luôn được ghi ──────────────────────────────────────────────

async def test_nut_bam_ghi_ly_do_bam_va_cam_bien_lan_cuoi(hass, r1, freezer, caplog):
    caplog.set_level(logging.INFO)
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)
    assert dev.reboot_goi == 1 and "lý do: người dùng bấm" in caplog.text
    st = hass.states.get(LAN_CUOI)
    assert st.attributes["ly_do"] == "bam" and st.attributes["ket_qua"] == "ok"
    assert datetime.fromisoformat(st.state) == gio("2026-11-04", 10, 0)


async def test_lenh_hong_theo_lich_ghi_loi_roi_khong_thu_lai_trong_luot_do(hass, r1, freezer, caplog):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 3, 50), **LICH_MOI_NGAY)
    dev.loi = "adbd không trả lời"
    await r1.stop()                                                      # cổng 8080 cũng hỏng: cả hai đường đều lỗi
    await tien(hass, freezer, gio("2026-11-04", 3, 50), gio("2026-11-04", 5, 0))
    assert dev.qua_8080 == len(REBOOT_SHELLS) and dev.reboot_goi == len(REBOOT_SHELLS) + 1     # mỗi cách đúng MỘT lần (các cách 8080 rồi ADB), không vòng lặp
    assert hass.states.get(LAN_CUOI).attributes["ket_qua"].startswith("loi: ")
    assert caplog.text.count("Khởi động lại theo lịch không thành") == 1


async def test_nut_bam_ca_hai_duong_hong_van_bao_loi_nhu_cu(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    dev.loi = "adbd không trả lời"
    await r1.stop()
    with pytest.raises(HomeAssistantError, match=r"cổng 8080 \(adb_cuc_bo\): .*; ADB: adbd không trả lời"):
        await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)


# ── «Loa phản hồi»: treo ≠ mất mạng ─────────────────────────────────────────────

async def test_loa_khoe_thi_phan_hoi_bat(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    await toi(hass, freezer, gio("2026-11-04", 10, 1))
    st = hass.states.get(CAM_BIEN)
    assert st.state == "on" and st.attributes["ly_do"] == "phan_hoi"
    assert st.attributes["lan_cuoi"]["get_info"] is not None             # bằng chứng được ghi lại
    assert st.attributes["nguong_im_giay"] == const.PHAN_HOI_NGUONG_IM_GIAY


async def test_cong_dieu_khien_tat_ma_may_van_tra_loi_tcp_la_treo(hass, r1, freezer, caplog):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    t = await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    await r1.stop()                                                      # 8080 bị từ chối (RST): máy còn sống, ứng dụng không
    t = await tien(hass, freezer, t, gio("2026-11-04", 10, 10))
    st = hass.states.get(CAM_BIEN)
    assert st.state == "off" and st.attributes["ly_do"] == "treo" and st.attributes["treo_tu"] is not None
    assert st.attributes["lan_cuoi"]["tcp_8080"] is not None
    assert caplog.text.count("TREO") == 1                                # cảnh báo MỘT lần cho cả đợt, không lặp mỗi nhịp
    await r1.start()                                                     # cùng cổng
    await tien(hass, freezer, t, t + timedelta(minutes=3))
    assert hass.states.get(CAM_BIEN).state == "on"
    assert caplog.text.count("đã phản hồi trở lại") == 1
    assert caplog.text.count("đọc được trở lại") == 1                    # coordinator: WARNING MỘT lần khi có lại (mục 2d)


async def test_khong_co_duong_toi_loa_la_mat_mang_khong_phai_treo(hass, r1, freezer, caplog):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    t = await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    await r1.stop()

    async def khong_thong(host, port, toi_da):
        return "khong"

    e.runtime_data.phan_hoi._thu_tcp = khong_thong                       # mạng không tới được loa (ranh giới mạng)
    dev.nghe = False
    await tien(hass, freezer, t, gio("2026-11-04", 10, 10))
    st = hass.states.get(CAM_BIEN)
    assert st.state == "off" and st.attributes["ly_do"] == "mat_mang" and st.attributes["treo_tu"] is None
    assert caplog.text.count("MẤT MẠNG") == 1


async def test_nhip_tim_apk_van_ve_thi_khong_phai_treo_du_get_info_im(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    t = await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    await r1.stop()
    for _ in range(12):                                                  # 6 phút, APK vẫn gửi nhịp tim (cong_vao.PingView gọi talk.alive())
        e.runtime_data.talk.alive()
        t = await tien(hass, freezer, t, t + timedelta(seconds=30))
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "phan_hoi"


async def test_vua_khoi_dong_lai_thi_cho_loa_len_lai_khong_ket_luan_treo(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    t = await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)
    await r1.stop()                                                      # loa tắt để khởi động lại
    t = await tien(hass, freezer, t, t + timedelta(minutes=4))
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "dang_khoi_dong"
    await tien(hass, freezer, t, t + timedelta(minutes=3))
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "treo"       # quá hạn chờ mà vẫn im


async def test_ha_moi_chay_chua_co_tin_hieu_thi_chua_biet_khong_vu_vo_ket_luan_treo(hass, r1, freezer):
    await r1.stop()                                                      # loa tắt ngay từ lúc HA lên
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    assert hass.states.get(CAM_BIEN).state == "unknown"
    await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "chua_biet"
    await tien(hass, freezer, gio("2026-11-04", 10, 1), gio("2026-11-04", 10, 5))
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "treo"       # đủ thời gian: 8080 từ chối = máy sống, ứng dụng im


# ── Thực thể không để trạng thái cũ khi loa không đọc được ────────────────────────

async def test_loa_khong_doc_duoc_thi_thuc_the_unavailable_va_log_mot_lan_moi_lan_mat(hass, r1, freezer, caplog):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    assert hass.states.get("switch.phicomm_r1_dlna").state == "on"
    await r1.stop()
    await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 6), buoc=10)
    assert hass.states.get("switch.phicomm_r1_dlna").state == "unavailable"      # không giữ giá trị cũ
    assert caplog.text.count("không đọc được") == 1                       # WARNING MỘT lần dù hỏng hàng chục nhịp


# ── Tự phục hồi khi treo ────────────────────────────────────────────────────────

async def _lam_treo(hass, r1, freezer, e, tu):
    """Loa chạy khoẻ một phút rồi 8080 tắt; trả giờ hiện tại."""
    t = await tien(hass, freezer, tu, tu + timedelta(minutes=1))
    await r1.stop()
    return t


async def test_tu_phuc_hoi_mac_dinh_tat_treo_bao_lau_cung_khong_khoi_dong(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    t = await _lam_treo(hass, r1, freezer, e, gio("2026-11-04", 10, 0))
    await tien(hass, freezer, t, t + timedelta(hours=2), buoc=120)
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "treo"
    assert dev.reboot_goi == 0


async def test_tu_phuc_hoi_bat_thi_khoi_dong_mot_lan_roi_nghi_het_gio_nghi_moi_lai(hass, r1, freezer, caplog):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0), khoi_dong_lai_khi_treo=True)
    t = await _lam_treo(hass, r1, freezer, e, gio("2026-11-04", 10, 0))
    t = await tien(hass, freezer, t, t + timedelta(minutes=const.KDL_TREO_TOI_THIEU_PHUT - 2), buoc=60)
    assert dev.reboot_goi == 0                                           # chưa treo đủ lâu
    t = await tien(hass, freezer, t, t + timedelta(minutes=10), buoc=60)
    assert dev.reboot_goi == 1
    assert "lý do: loa treo (tự phục hồi)" in caplog.text
    assert hass.states.get(LAN_CUOI).attributes["ly_do"] == "treo"
    t = await tien(hass, freezer, t, t + timedelta(hours=const.KDL_NGHI_SAU_TU_PHUC_HOI_GIO - 1), buoc=300)
    assert dev.reboot_goi == 1                                           # loa vẫn treo mà KHÔNG khởi động lại thêm (không lặp vòng)
    await tien(hass, freezer, t, t + timedelta(hours=1, minutes=30), buoc=300)
    assert dev.reboot_goi == 2                                           # hết giờ nghỉ mới được lần nữa


async def test_tu_phuc_hoi_mot_lan_roi_ha_khoi_dong_lai_van_nghi(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0), khoi_dong_lai_khi_treo=True)
    t = await _lam_treo(hass, r1, freezer, e, gio("2026-11-04", 10, 0))
    t = await tien(hass, freezer, t, t + timedelta(minutes=const.KDL_TREO_TOI_THIEU_PHUT + 8), buoc=60)
    assert dev.reboot_goi == 1
    assert await hass.config_entries.async_reload(e.entry_id)
    await hass.async_block_till_done()
    dev2 = DevGia()
    e.runtime_data.apps.dev = dev2
    await tien(hass, freezer, t, t + timedelta(hours=1), buoc=120)
    assert dev2.reboot_goi == 0


async def test_mat_mang_that_thi_khong_tu_khoi_dong_chi_bao(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0), khoi_dong_lai_khi_treo=True)
    t = await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    await r1.stop()

    async def khong_thong(host, port, toi_da):
        return "khong"

    e.runtime_data.phan_hoi._thu_tcp = khong_thong
    dev.nghe = False
    await tien(hass, freezer, t, t + timedelta(hours=3), buoc=300)
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "mat_mang"
    assert dev.reboot_goi == 0


async def test_treo_nhung_adb_khong_noi_duoc_thi_khong_khoi_dong_va_bao_mot_lan(hass, r1, freezer, caplog):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0), khoi_dong_lai_khi_treo=True)
    t = await _lam_treo(hass, r1, freezer, e, gio("2026-11-04", 10, 0))
    dev.nghe = False                                                     # 8080 từ chối (máy sống) nhưng cổng ADB không nhận
    await tien(hass, freezer, t, t + timedelta(minutes=40), buoc=60)
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "treo"
    assert dev.reboot_goi == 0
    assert caplog.text.count("ADB không nối được") == 1


async def test_tu_phuc_hoi_chi_di_duong_adb_khong_goi_cong_8080(hass, r1, freezer):
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0), khoi_dong_lai_khi_treo=True)
    t = await _lam_treo(hass, r1, freezer, e, gio("2026-11-04", 10, 0))
    dev.loi = "adbd từ chối"
    await tien(hass, freezer, t, t + timedelta(minutes=30), buoc=60)
    assert dev.reboot_goi == 1                                           # ADB hỏng thì thôi, không nhờ cổng 8080 đang treo
    assert hass.states.get(LAN_CUOI).attributes["ket_qua"].startswith("loi: ")


# ── Hộp tuỳ chọn HA: lưu đúng, giá trị mặc định không lưu ───────────────────────────

async def test_hop_tuy_chon_luu_lich_va_doc_lai_dung(hass, r1):
    from custom_components.r1_speaker import settings as st
    from .test_tuy_chon import _luu
    from .test_bo_dam import _them
    e = await _them(hass, r1)
    assert (st.khoi_dong_lai_bat(e), st.khoi_dong_lai_gio(e).strftime("%H:%M"), st.khoi_dong_lai_khi_treo(e)) == (False, "04:00", False)
    assert st.khoi_dong_lai_ngay(e) == frozenset(const.KDL_NGAY_MA)
    _res, kq = await _luu(hass, e, host="127.0.0.1", port=r1.port, khoi_dong_lai_bat=True, khoi_dong_lai_gio="05:30:00",
                          khoi_dong_lai_ngay=["cn", "t2"], khoi_dong_lai_khi_treo=True)
    assert kq["type"].value == "create_entry"
    assert e.options["khoi_dong_lai_gio"] == "05:30" and e.options["khoi_dong_lai_ngay"] == ["t2", "cn"]
    assert (st.khoi_dong_lai_bat(e), st.khoi_dong_lai_khi_treo(e)) == (True, True)
    await hass.async_block_till_done()
    # lưu lại với giá trị gốc thì không giữ khoá thừa
    _res, kq = await _luu(hass, e, host="127.0.0.1", port=r1.port, khoi_dong_lai_bat=False, khoi_dong_lai_gio="04:00:00",
                          khoi_dong_lai_ngay=list(const.KDL_NGAY_MA), khoi_dong_lai_khi_treo=False)
    assert not any(k.startswith("khoi_dong_lai") for k in e.options)


def test_gio_va_ngay_hong_roi_ve_mac_dinh():
    from types import SimpleNamespace
    from custom_components.r1_speaker import settings as st
    e = SimpleNamespace(options={"khoi_dong_lai_gio": "25:99", "khoi_dong_lai_ngay": "t2"}, data={})
    assert st.khoi_dong_lai_gio(e).strftime("%H:%M") == "04:00"
    assert st.khoi_dong_lai_ngay(e) == frozenset(const.KDL_NGAY_MA)
    e.options["khoi_dong_lai_ngay"] = ["t2", "xx", "cn"]
    assert st.khoi_dong_lai_ngay(e) == frozenset({"t2", "cn"})


async def test_apk_dang_noi_vao_ha_thi_khong_ket_luan_treo_du_cong_8080_tat(hass, r1, freezer_tick):
    """8080 tắt nhưng APK vẫn nối vào đầu nhận mic của HA: còn một tín hiệu ứng dụng nên KHÔNG phải treo (không được tự khởi động lại)."""
    from .test_den_nhac import KHOA, _cong_trong, _noi_apk
    freezer = freezer_tick
    cong = _cong_trong()
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0), khoi_dong_lai_khi_treo=True,
                        mic_host="127.0.0.1", mic_port=9, mic_listen_port=cong, mic_listen_key=KHOA)
    reader, writer = await _noi_apk(e, cong)
    t = await tien(hass, freezer, gio("2026-11-04", 10, 0), gio("2026-11-04", 10, 1))
    await r1.stop()
    t = await tien(hass, freezer, t, t + timedelta(minutes=40), buoc=60)
    st = hass.states.get(CAM_BIEN)
    assert st.attributes["ly_do"] == "phan_hoi" and st.attributes["lan_cuoi"]["apk_ket_noi"] is not None
    assert dev.reboot_goi == 0
    writer.close()
    await hass.async_block_till_done()
    await tien(hass, freezer, t, t + timedelta(minutes=5), buoc=60)       # APK đứt, 8080 vẫn tắt: lúc đó mới là treo
    assert hass.states.get(CAM_BIEN).attributes["ly_do"] == "treo"


# ── Sửa lỗi chủ máy báo 10/11/2026: hẹn giờ «chỉ cập nhật trạng thái chứ loa không khởi động lại»; đặt lại giờ cùng ngày thì không nhận ───────────

async def test_doi_gio_lich_trong_ngay_thi_luot_moi_van_chay(hass, r1, freezer):
    """Đặt 11:52 lúc 11:50, loa khởi động; rồi đặt lại 12:05 lúc 11:56: lượt 12:05 PHẢI chạy dù hôm nay lịch cũ đã chạy (trước đây cờ «hôm nay đã chạy» chặn)."""
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 11, 50), khoi_dong_lai_bat=True, khoi_dong_lai_gio="11:52")
    t = await tien(hass, freezer, gio("2026-11-04", 11, 50), gio("2026-11-04", 11, 54))
    assert dev.reboot_goi == 1
    hass.config_entries.async_update_entry(e, options={**e.options, "khoi_dong_lai_gio": "12:05"})
    t = await tien(hass, freezer, t, gio("2026-11-04", 12, 4))
    assert dev.reboot_goi == 1                                           # chưa tới 12:05
    await tien(hass, freezer, t, gio("2026-11-04", 12, 7))
    assert dev.reboot_goi == 2                                           # lượt mới chạy
    hass.config_entries.async_update_entry(e, options={**e.options, "khoi_dong_lai_gio": "12:15"})
    await tien(hass, freezer, gio("2026-11-04", 12, 7), gio("2026-11-04", 12, 17))
    assert dev.reboot_goi == 3                                           # và lần thứ ba nữa


async def test_lenh_gui_ma_loa_khong_tat_thi_thu_cach_khac_ghi_ten_duong_va_nho_cach_tot(hass, r1, freezer, monkeypatch):
    """Kênh 8080 «gửi rồi quên»: loa phớt lờ lệnh (ví dụ ADB mạng đã đóng nên ``adb reboot`` không có thiết bị) thì trước đây vẫn báo ok. Giờ không thấy
    loa tắt thì thử cách kế tiếp rồi ADB, trạng thái ghi cách thật sự có tác dụng, và lần sau thử cách đó trước."""
    e, dev = await dung(hass, r1, freezer, gio("2026-11-04", 10, 0))
    from custom_components.r1_speaker.khoi_dong_lai import KhoiDongLai
    khong = lambda self: _sai()
    monkeypatch.setattr(KhoiDongLai, "_cho_loa_tat", khong)
    with pytest.raises(HomeAssistantError, match=r"cổng 8080 \(adb_cuc_bo\): đã gửi lệnh nhưng loa không tắt.*; ADB: đã gửi lệnh nhưng loa không tắt"):
        await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)
    assert dev.qua_8080 == len(REBOOT_SHELLS) and dev.reboot_goi == len(REBOOT_SHELLS) + 1     # đã thử mọi cách
    assert hass.states.get(LAN_CUOI).attributes["ket_qua"].startswith("loi: ")
    assert [m["shell"] for m in r1.commands("shell")] == [c for _, c in REBOOT_SHELLS]          # đúng từng lệnh, đúng thứ tự

    chuoi = iter([False, True])                                          # cách 1 không tắt, cách 2 (ShutdownActivity) thì loa tắt
    monkeypatch.setattr(KhoiDongLai, "_cho_loa_tat", lambda self: _theo(chuoi))
    await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)
    a = hass.states.get(LAN_CUOI).attributes
    assert a["ket_qua"] == "ok" and a["duong"] == "cong_8080/shutdown_activity"
    assert e.runtime_data.khoi_dong_lai.duong_tot == "cong_8080/shutdown_activity"
    truoc = len(r1.commands("shell"))
    monkeypatch.setattr(KhoiDongLai, "_cho_loa_tat", lambda self: _dung())
    await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)
    (moi,) = r1.commands("shell")[truoc:]
    assert moi["shell"] == dict(REBOOT_SHELLS)["shutdown_activity"]       # lần sau thử cách đã có tác dụng ĐẦU TIÊN (không phí 25 giây cho cách hỏng)
    # ADB có tác dụng thì ghi ``adb`` và nhớ.
    e.runtime_data.khoi_dong_lai.duong_tot = None
    chuoi = iter([False] * len(REBOOT_SHELLS) + [True])
    monkeypatch.setattr(KhoiDongLai, "_cho_loa_tat", lambda self: _theo(chuoi))
    await hass.services.async_call("button", "press", {"entity_id": NUT}, blocking=True)
    assert hass.states.get(LAN_CUOI).attributes["duong"] == "adb" and e.runtime_data.khoi_dong_lai.duong_tot == "adb"


async def _sai():
    return False


async def _theo(chuoi):
    return next(chuoi)


async def _dung():
    return True


async def test_cho_loa_tat_that_phat_hien_cong_8080_ngung_nhan_ket_noi(r1, monkeypatch):
    """Thử hàm chờ trên MÁY CHỦ THẬT (không giờ giả): còn nhận kết nối thì hết hạn là False; tắt máy chủ trong lúc chờ thì True."""
    import asyncio
    from types import SimpleNamespace
    from custom_components.r1_speaker.khoi_dong_lai import KhoiDongLai
    monkeypatch.setattr(const, "KDL_XAC_NHAN_GIAY", 1)
    monkeypatch.setattr(const, "KDL_XAC_NHAN_NHIP", 0.1)
    fake = SimpleNamespace(_coordinator=SimpleNamespace(client=SimpleNamespace(host="127.0.0.1", port=r1.port)))
    assert await KhoiDongLai._cho_loa_tat(fake) is False                  # loa vẫn nghe sau 1 giây: lệnh bị phớt lờ
    monkeypatch.setattr(const, "KDL_XAC_NHAN_GIAY", 5)
    cho = asyncio.ensure_future(KhoiDongLai._cho_loa_tat(fake))
    await asyncio.sleep(0.4)
    await r1.stop()                                                      # loa «tắt»
    assert await asyncio.wait_for(cho, 4) is True
