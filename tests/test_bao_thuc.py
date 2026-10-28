"""Báo thức / nhắc nhở / hẹn giờ tắt nhạc chạy bằng HA: tính lần kêu kế tiếp, lịch, kêu lặp và tắt, hoãn, nhắc nhở một lần, hẹn giờ nhỏ dần, dịch vụ."""

import asyncio
from datetime import datetime, timedelta

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.r1_speaker import bao_thuc as BT
from custom_components.r1_speaker.bao_thuc import ke_tiep

from .test_den_nhac import _noi_apk, _them_co_dau_nhan, _khung_xuong


def luc(s):
    """Giờ NGAY TRONG múi giờ của HA (không đổi múi: «21:30» là 21:30 giờ địa phương của HA, mặc định trong test là US/Pacific)."""
    tz = dt_util.get_default_time_zone() if hasattr(dt_util, "get_default_time_zone") else dt_util.DEFAULT_TIME_ZONE
    return datetime.fromisoformat(s.replace("+07:00", "")).replace(tzinfo=tz)


# ── Tính lần kêu kế tiếp (hàm thuần) ─────────────────────────────

def test_ke_tiep_mot_lan_hom_nay_neu_chua_qua_gio_con_lai_ngay_mai():
    bay_gio = luc("2026-10-28T20:00:00+07:00")
    assert ke_tiep({"gio": "21:30"}, bay_gio) == luc("2026-10-28T21:30:00+07:00")
    assert ke_tiep({"gio": "07:00"}, bay_gio) == luc("2026-10-29T07:00:00+07:00")
    assert ke_tiep({"gio": "20:00"}, bay_gio) == luc("2026-10-29T20:00:00+07:00")      # đúng giờ hiện tại: đã qua


def test_ke_tiep_theo_ngay_lap_t2_toi_t6_bo_qua_cuoi_tuan():
    t6_toi = luc("2026-10-30T20:00:00+07:00")                                          # thứ sáu
    a = {"gio": "06:30", "ngay": ["mon", "tue", "wed", "thu", "fri"]}
    assert ke_tiep(a, t6_toi) == luc("2026-11-02T06:30:00+07:00")                      # thứ hai tuần sau
    assert ke_tiep({"gio": "21:00", "ngay": ["sat"]}, t6_toi) == luc("2026-10-31T21:00:00+07:00")


def test_ke_tiep_nhac_nho_tuyet_doi_qua_gio_va_bao_thuc_tat_hoac_hong_la_none():
    bay_gio = luc("2026-10-28T20:00:00+07:00")
    assert ke_tiep({"luc": "2026-10-28T21:00:00" + luc("2026-10-28T00:00:00").strftime("%z")[:3] + ":" + luc("2026-10-28T00:00:00").strftime("%z")[3:]}, bay_gio) == luc("2026-10-28T21:00:00+07:00")
    assert ke_tiep({"luc": "2026-10-28T19:00:00" + luc("2026-10-28T00:00:00").strftime("%z")[:3] + ":" + luc("2026-10-28T00:00:00").strftime("%z")[3:]}, bay_gio) is None
    assert ke_tiep({"gio": "21:00", "bat": False}, bay_gio) is None
    assert ke_tiep({"gio": "xx:yy"}, bay_gio) is None and ke_tiep({}, bay_gio) is None and ke_tiep({"luc": "hỏng"}, bay_gio) is None


# ── Tích hợp HA ──────────────────────────────────────────────────

@pytest.fixture
async def bt(hass, r1):
    """(mục, BaoThuc, danh sách lần phát tiếng, danh sách sự kiện): vệ tinh Assist và media_player được giả bằng dịch vụ ghi lại."""
    e, port = await _them_co_dau_nhan(hass, r1)
    await hass.async_block_till_done()
    phat, su_kien = [], []
    hass.services.async_register("assist_satellite", "announce", lambda c: phat.append(("tts", c.data.get("message"))))
    hass.services.async_register("media_player", "play_media", lambda c: phat.append(("media", c.data.get("media_content_id"))))
    hass.services.async_register("media_player", "media_stop", lambda c: phat.append(("stop", None)))
    hass.bus.async_listen(BT.SU_KIEN, lambda ev: su_kien.append(ev.data))
    yield e, e.runtime_data.bao_thuc, phat, su_kien, port
    e.runtime_data.bao_thuc.huy()


async def _tien(hass, giay):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=giay))
    await hass.async_block_till_done()


async def test_bao_thuc_den_gio_keu_lap_den_khi_tat_va_phat_su_kien(hass, bt):
    e, b, phat, sk, _ = bt
    a = await b.dat(gio=(dt_util.now() + timedelta(minutes=1)).strftime("%H:%M"), nhan="Dậy đi", noi_dung="Dậy đi thôi", lap_s=5)
    await _tien(hass, 125)
    for _ in range(100):
        if phat:
            break
        await asyncio.sleep(0.01)
    assert phat and phat[0] == ("tts", "Dậy đi thôi") and b.dang_keu == a["id"]
    await hass.async_block_till_done()                                              # sự kiện bus tới người nghe (lambda thường) chạy trong luồng nền
    assert any(s["trang_thai"] == "keu" and s["id"] == a["id"] for s in sk)
    await b.tat()
    await hass.async_block_till_done()
    assert b.dang_keu is None and any(s["trang_thai"] == "tat" for s in sk)
    n = len(phat)
    await asyncio.sleep(0.1)
    assert len(phat) == n                                                           # tắt rồi thì không kêu thêm
    assert b.ds[a["id"]]["bat"] is False                                            # báo thức một lần: kêu xong tự tắt nhưng còn đó để bật lại


async def test_bao_thuc_lap_theo_ngay_van_con_sau_khi_keu_va_xep_lan_ke(hass, bt):
    e, b, phat, sk, _ = bt
    a = await b.dat(gio=(dt_util.now() + timedelta(minutes=1)).strftime("%H:%M"), ngay=list(BT.NGAY), nhan="Hằng ngày")
    await _tien(hass, 125)
    await b.tat()
    assert a["id"] in b.ds and b.ds[a["id"]]["bat"] is True
    assert ke_tiep(b.ds[a["id"]], dt_util.now()) is not None                          # vẫn có lần kế (ngày mai)


async def test_nhac_nho_mot_lan_sau_n_phut_keu_xong_tu_xoa(hass, bt):
    e, b, phat, sk, _ = bt
    a = await b.nhac_nho("Uống thuốc", sau_phut=2)
    assert a["id"] in b.ds
    await _tien(hass, 125)
    for _ in range(100):
        if phat:
            break
        await asyncio.sleep(0.01)
    assert phat[0] == ("tts", "Uống thuốc") and a["id"] not in b.ds                   # đã xoá khỏi danh sách ngay khi kêu
    await b.tat()


async def test_nhac_nho_gio_da_qua_va_thieu_tham_so_bi_tu_choi(hass, bt):
    _, b, *_ = bt
    with pytest.raises(ServiceValidationError, match="đã qua"):
        await b.nhac_nho("x", luc=dt_util.now() - timedelta(minutes=1))
    with pytest.raises(ServiceValidationError, match="đúng một"):
        await b.nhac_nho("x")
    with pytest.raises(ServiceValidationError, match="đúng một"):
        await b.nhac_nho("x", sau_phut=1, luc=dt_util.now() + timedelta(hours=1))


async def test_hoan_im_di_va_bao_lai_sau_n_phut_voi_cung_noi_dung(hass, bt):
    e, b, phat, sk, _ = bt
    await b.nhac_nho("Họp lúc 9 giờ", sau_phut=1)
    await _tien(hass, 65)
    for _ in range(100):
        if phat:
            break
        await asyncio.sleep(0.01)
    assert b.dang_keu is not None
    await b.hoan(5)
    await hass.async_block_till_done()
    assert b.dang_keu is None and any(s["trang_thai"] == "hoan" for s in sk)
    cho_lai = [a for a in b.ds.values() if a.get("noi_dung") == "Họp lúc 9 giờ"]
    assert len(cho_lai) == 1 and ke_tiep(cho_lai[0], dt_util.now()) is not None       # đã xếp lại một nhắc nhở cùng lời
    await b.tat()                                                                      # không có gì đang kêu: không lỗi


async def test_kieu_media_phat_dia_chi_am_thanh_va_het_gio_thi_dung_lai(hass, bt):
    e, b, phat, sk, _ = bt
    a = await b.dat(gio=(dt_util.now() + timedelta(minutes=1)).strftime("%H:%M"), loai="media", noi_dung="http://ha.local/chuong.mp3", lap_s=5, toi_da_s=30)
    await _tien(hass, 125)
    for _ in range(100):
        if phat:
            break
        await asyncio.sleep(0.01)
    assert phat[0] == ("media", "http://ha.local/chuong.mp3")
    b._dung_keu()


async def test_loa_loi_khi_kêu_chi_ghi_canh_bao_khong_lam_hong(hass, bt, caplog):
    e, b, phat, sk, _ = bt
    hass.services.async_remove("assist_satellite", "announce")
    hass.services.async_register("assist_satellite", "announce", lambda c: (_ for _ in ()).throw(RuntimeError("vệ tinh lỗi")))
    await b.nhac_nho("Thử", sau_phut=1)
    await _tien(hass, 65)
    for _ in range(100):
        if any("không kêu được" in r.getMessage() for r in caplog.records):
            break
        await asyncio.sleep(0.01)
    assert any("không kêu được" in r.getMessage() and "vệ tinh lỗi" in r.getMessage() for r in caplog.records)
    assert b.dang_keu is None


async def test_luu_qua_khoi_dong_lai_va_xoa_bat_tat(hass, bt):
    e, b, *_ = bt
    a = await b.dat(gio="07:00", ngay=["mon"], nhan="T2")
    await b.bat_tat(a["id"], False)
    assert b.ds[a["id"]]["bat"] is False and ke_tiep(b.ds[a["id"]], dt_util.now()) is None
    await b._store.async_save({"bao_thuc": b.ds})
    moi = BT.BaoThuc(hass, e, e.runtime_data)
    await moi.async_load()
    assert moi.ds == b.ds
    await b.xoa(a["id"])
    assert a["id"] not in b.ds
    with pytest.raises(ServiceValidationError):
        await b.xoa("khong-co")
    moi.huy()


async def test_gioi_han_so_bao_thuc(hass, bt):
    _, b, *_ = bt
    for i in range(BT.TOI_DA_BAO_THUC):
        await b.dat(gio="07:00", nhan=str(i))
    with pytest.raises(ServiceValidationError, match="Tối đa"):
        await b.dat(gio="08:00")


async def test_hen_gio_tat_nhac_nho_dan_roi_dung_va_tra_am_luong(hass, bt):
    e, b, phat, sk, port = bt
    reader, writer = await _noi_apk(e, port)
    import json
    writer.write(len(json.dumps({"type": "am_luong_trang_thai", "muc": 8, "toi_da": 15}).encode()).to_bytes(4, "big") +
                 json.dumps({"type": "am_luong_trang_thai", "muc": 8, "toi_da": 15}).encode())
    await writer.drain()
    for _ in range(200):
        if e.runtime_data.mic_server.am_luong == (8, 15):
            break
        await asyncio.sleep(0.01)
    await b.hen_gio_tat_nhac(1, lam_mo_giay=0.2)
    assert b.hen_gio_luc is not None
    await _tien(hass, 61)
    for _ in range(300):
        if ("stop", None) in phat:
            break
        await asyncio.sleep(0.01)
    assert ("stop", None) in phat                                                      # đã dừng nhạc
    muc = []
    for _ in range(40):
        try:
            k = json.loads(await asyncio.wait_for(_khung_xuong(reader), 0.3))
        except (asyncio.TimeoutError, ValueError):
            break
        if k.get("type") == "am_luong":
            muc.append(k["muc"])
    assert muc and muc[-1] == 8 and min(muc) == 0 and muc[0] < 8, muc                  # nhỏ dần về 0 rồi trả lại 8
    assert b.hen_gio_luc is None
    writer.close()


async def test_huy_hen_gio_tat_nhac_khong_dung_nhac(hass, bt):
    e, b, phat, *_ = bt
    await b.hen_gio_tat_nhac(1, lam_mo_giay=0)
    await b.huy_hen_gio_tat_nhac()
    await _tien(hass, 120)
    assert ("stop", None) not in phat and b.hen_gio_luc is None


async def test_dich_vu_va_thuc_the(hass, bt):
    e, b, phat, sk, _ = bt
    reg = er.async_get(hass)
    sen = reg.async_get_entity_id("sensor", "r1_speaker", f"{e.entry_id}_bao_thuc_ke_tiep")
    btn = reg.async_get_entity_id("button", "r1_speaker", f"{e.entry_id}_tat_bao_thuc")
    apk = reg.async_get_entity_id("sensor", "r1_speaker", f"{e.entry_id}_apk")
    assert sen and btn and apk
    assert hass.states.get(sen).state == "unknown"
    await hass.services.async_call("r1_speaker", "bao_thuc_dat", {"entity_id": sen, "gio": "06:30", "ngay": ["mon", "fri"], "nhan": "Đi làm"}, blocking=True)
    st = hass.states.get(sen)
    assert st.state != "unknown" and st.attributes["bao_thuc"][0]["nhan"] == "Đi làm" and st.attributes["bao_thuc"][0]["ke_tiep"]
    i = st.attributes["bao_thuc"][0]["id"]
    await hass.services.async_call("r1_speaker", "bao_thuc_bat_tat", {"entity_id": sen, "id": i, "bat": False}, blocking=True)
    assert hass.states.get(sen).state == "unknown"
    await hass.services.async_call("r1_speaker", "bao_thuc_xoa", {"entity_id": sen, "id": i}, blocking=True)
    assert hass.states.get(sen).attributes["bao_thuc"] == []
    with pytest.raises(Exception):
        await hass.services.async_call("r1_speaker", "bao_thuc_dat", {"entity_id": sen, "gio": "25:99"}, blocking=True)       # giờ sai bị chặn ở biên
    with pytest.raises(Exception):
        await hass.services.async_call("r1_speaker", "bao_thuc_dat", {"entity_id": "sensor.khong_phai_r1", "gio": "06:30"}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": btn}, blocking=True)                                      # không có gì kêu: không lỗi
    assert hass.states.get(apk).state in ("mat_ket_noi", "cu") or hass.states.get(apk).state
