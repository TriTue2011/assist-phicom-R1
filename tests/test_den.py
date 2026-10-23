"""Đèn theo chức năng: cài đặt hai vùng (đáy, viền), chọn chức năng, áp xuống sink, mục Thử riêng, lưu và chuyển bản cũ.

Sink là ``MemoryLights`` (ghi lại ``ap_dung``): KHÔNG chạm loa, KHÔNG ADB thật."""

import asyncio
from datetime import timedelta

import pytest
from homeassistant.components.assist_pipeline import PipelineEvent, PipelineEventType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.r1_speaker import den
from custom_components.r1_speaker.den import (DEFAULTS, FUNCTIONS, THU_LAI_S, UU_TIEN, FunctionLight, Signals, Zone,
                                              chon_chuc_nang, tao_vung, tu_ban_luu_cu)
from custom_components.r1_speaker.den_hieu_ung import EFFECTS, chuan_hoa
from custom_components.r1_speaker.den_port import NullLights

from .memory_lights import MemoryLights
from .test_bo_dam import _them
from .test_mic import MUTE, SAT, _vet_tinh

CAI_DAT = "sensor.r1_cai_dat"


# ── Thuần: chọn chức năng, mặc định, đọc cài đặt ───────────────────

def test_tam_chuc_nang_va_thu_tu_uu_tien():
    assert set(FUNCTIONS) == {"cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi", "tat_mic"}
    assert UU_TIEN[0] == "tat_mic" and UU_TIEN[-1] == "cho"
    bat_nhac = {**DEFAULTS, "phat_nhac": FunctionLight(True, tao_vung("day", "tho"), Zone())}
    cases = [
        (Signals(), "cho", DEFAULTS), (Signals(ve_tinh="idle"), "cho", DEFAULTS),
        (Signals(ve_tinh="listening"), "nghe", DEFAULTS), (Signals(ve_tinh="processing"), "nghi", DEFAULTS),
        (Signals(ve_tinh="responding"), "phan_hoi", DEFAULTS), (Signals(ve_tinh="unavailable"), "cho", DEFAULTS),
        (Signals(phien=True, ve_tinh="idle"), "dam_thoai", DEFAULTS),
        (Signals(phien=True, ve_tinh="listening"), "nghe", DEFAULTS),
        (Signals(dang_phat=True), "cho", DEFAULTS),           # chức năng nhạc đang TẮT → coi như không có nhạc
        (Signals(dang_phat=True), "phat_nhac", bat_nhac),
        (Signals(dang_phat=True, ve_tinh="responding"), "phan_hoi", bat_nhac),
        (Signals(dang_phat=True, phien=True), "dam_thoai", bat_nhac),
        (Signals(loi=True, ve_tinh="listening", dang_phat=True), "loi", bat_nhac),
        (Signals(tat_mic=True, loi=True, ve_tinh="responding", phien=True), "tat_mic", bat_nhac),
    ]
    for tin, mong, prof in cases:
        assert chon_chuc_nang(tin, prof) == mong, tin


def test_mac_dinh_hop_le_moi_vung_dung_danh_muc_cua_vung():
    assert set(DEFAULTS) == set(FUNCTIONS)
    for fn, p in DEFAULTS.items():
        for vung in ("day", "vien"):
            z = p.zone(vung)
            assert z.effect == "tat" or z.effect in EFFECTS[vung], (fn, vung)
            assert z.params == chuan_hoa(vung, z.effect, z.params), (fn, vung)
        assert p.vien.effect in ("tat", "sang"), fn          # viền mặc định chỉ sáng liên tục hoặc tắt
    assert DEFAULTS["phat_nhac"].enabled is False and DEFAULTS["cho"].enabled is False


def test_doc_cai_dat_hong_roi_ve_mac_dinh_tung_truong():
    base = DEFAULTS["nghe"]
    p = FunctionLight.from_dict({"enabled": "x", "day": {"effect": "ma", "params": {"do_sang": 1}},
                                 "vien": {"effect": "cau_vong"}}, base)
    assert p == base                                          # hiệu ứng lạ / của vùng khác: bỏ, giữ nguyên
    p2 = FunctionLight.from_dict({"day": {"params": {"do_sang": 500, "mau": "rác"}}}, base)
    assert p2.day.effect == base.day.effect and p2.day.params["do_sang"] == 100 and p2.day.params["mau"] == "#0000ff"
    assert FunctionLight.from_dict("rác", base) == base


def test_chuyen_cai_dat_cu_sang_hai_vung():
    # đáy sáng một màu, viền trắng 60% (mặc định cũ của «nghe») chỉ đổi màu
    p = tu_ban_luu_cu("nghe", {"color": "#00ff00", "brightness": 40})
    assert p.day == tao_vung("day", "co_dinh", {"mau": "#00ff00", "do_sang": 40})
    assert p.vien == tao_vung("vien", "sang", {"do_sang": 40}) and p.enabled is True
    # hiệu ứng đáy cũ giữ id, kèm tốc độ; kiểu viền chạy đuổi cũ → viền chạy đuổi
    q = tu_ban_luu_cu("nghi", {"effect": "cau_vong", "toc_do": 200, "rim": True, "rim_kieu": 5})
    assert q.day.effect == "cau_vong" and q.day.params["toc_do"] == 200
    assert q.vien.effect == "chay_duoi" and q.vien.params["toc_do"] == 200
    # không viền, không đáy sáng → tắt cả hai vùng; chức năng tắt giữ nguyên tắt
    r = tu_ban_luu_cu("cho", {"rim": False, "brightness": 0})
    assert r.day.effect == "tat" and r.vien.effect == "tat" and r.enabled is False


# ── Tích hợp HA ────────────────────────────────────────────────

@pytest.fixture
async def den_sink(hass, r1):
    e = await _them(hass, r1)
    mem = MemoryLights()
    lights = e.runtime_data.lights
    lights.set_sink(mem)
    await hass.async_block_till_done()
    return e, lights, mem


async def test_loa_chua_cau_hinh_duong_den_thi_chi_luu_khong_gui(hass, r1):
    e = await _them(hass, r1)
    lights = e.runtime_data.lights
    assert isinstance(lights.sink, NullLights) and lights.sink_state == "CHO_PHIA_LOA"
    st = hass.states.get(CAI_DAT)
    assert st.state == "cho" and st.attributes["anh_sang"]["dich_vu_den"] == "CHO_PHIA_LOA"
    assert "danh_muc" in st.attributes["anh_sang"] and "hieu_ung_ho_tro" not in st.attributes["anh_sang"]
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert lights.current == "nghe" and lights.last_error is None
    for dv in ("set_light_function", "preview_light", "stop_preview_light"):
        assert hass.services.has_service("r1_speaker", dv)
    assert not hass.services.has_service("r1_speaker", "set_music_light")


async def test_moi_chuc_nang_ap_dung_dung_hai_vung(hass, r1, den_sink):
    e, lights, mem = den_sink
    assert lights.current == "cho"                       # chờ: mặc định TẮT → cả hai vùng tắt
    assert mem.cuoi() == {"day": ("tat", {}), "vien": ("tat", {})}
    hass.states.async_set(SAT, "listening")              # nghe: đáy xanh dương cố định 60% + viền sáng 60%
    await hass.async_block_till_done()
    assert mem.cuoi() == {"day": ("co_dinh", {"mau": "#0000ff", "do_sang": 60}), "vien": ("sang", {"do_sang": 60})}
    hass.states.async_set(SAT, "processing")             # nghĩ: đáy thở, viền tắt
    await hass.async_block_till_done()
    assert mem.cuoi()["day"][0] == "tho" and mem.cuoi()["vien"][0] == "tat"
    hass.states.async_set(SAT, "idle")
    await hass.services.async_call("switch", "turn_on", {"entity_id": MUTE}, blocking=True)
    await hass.async_block_till_done()                    # tắt mic: đỏ + viền
    assert lights.current == "tat_mic" and mem.cuoi()["day"][1]["mau"] == "#ff0000"
    await hass.services.async_call("switch", "turn_off", {"entity_id": MUTE}, blocking=True)
    await hass.async_block_till_done()
    assert lights.current == "cho" and mem.cuoi()["day"][0] == "tat"


async def test_do_sang_chung_duoc_chuyen_xuong_sink(hass, r1, den_sink):
    e, lights, mem = den_sink
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    mem.clear()
    await lights.async_set_master(50)
    await hass.async_block_till_done()
    assert {x[4] for x in mem.ap} == {50}


async def test_chuc_nang_tat_thi_tat_ca_hai_vung(hass, r1, den_sink):
    e, lights, mem = den_sink
    await lights.async_set_function("nghe", enabled=False)
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert lights.current == "nghe" and mem.cuoi() == {"day": ("tat", {}), "vien": ("tat", {})}


async def test_set_function_theo_vung_doi_hieu_ung_ve_mac_dinh_va_kiem_gia_tri(hass, r1, den_sink):
    e, lights, mem = den_sink
    p = await lights.async_set_function("nghe", day={"effect": "sao_choi", "params": {"kieu_mau": "don_sac", "dai_duoi": 7}},
                                        vien={"effect": "chay_duoi", "params": {"chieu": "nguoc"}})
    assert p.day.effect == "sao_choi" and p.day.params["dai_duoi"] == 7 and p.day.params["mau"] == "#00ffff"
    assert p.vien.params == {"do_sang": 100, "toc_do": 100, "chieu": "nguoc", "dai_duoi": 4}
    # chỉ gửi params: giữ hiệu ứng, trộn vào thông số hiện có
    p = await lights.async_set_function("nghe", day={"params": {"toc_do": 250}})
    assert p.day.effect == "sao_choi" and p.day.params["toc_do"] == 250 and p.day.params["dai_duoi"] == 7
    for bad in ({"day": {"effect": "chay_duoi"}}, {"vien": {"effect": "cau_vong"}}, {"day": "tho"}, {"enabled": "có"}):
        with pytest.raises(ServiceValidationError):
            await lights.async_set_function("nghe", **bad)
    with pytest.raises(ServiceValidationError):
        await lights.async_set_function("khong_co", enabled=True)


async def test_dich_vu_dat_den_chay_qua_ha_va_tu_choi_gia_tri_sai(hass, r1, den_sink):
    import voluptuous as vol
    e, lights, mem = den_sink
    ent = "sensor.r1_cai_dat"
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": ent, "function": "loi", "day": {"effect": "nhip_tim", "params": {"mau": "#ff0000", "toc_do": 150}}},
        blocking=True)
    assert lights.profiles["loi"].day.effect == "nhip_tim" and lights.profiles["loi"].day.params["toc_do"] == 150
    with pytest.raises(vol.Invalid):
        await hass.services.async_call("r1_speaker", "set_light_function",
                                       {"entity_id": ent, "function": "không có"}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("r1_speaker", "set_light_function", {
            "entity_id": ent, "function": "loi", "day": {"effect": "ma"}}, blocking=True)


async def test_thu_phu_len_tung_vung_roi_tu_tra_ve(hass, r1, den_sink):
    """Thử là mục RIÊNG: không đổi cài đặt đã lưu, chỉ phủ tạm lên vùng được chọn rồi trả về trạng thái thật."""
    e, lights, mem = den_sink
    luu = dict(lights.profiles)
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    lights.thu("vien", "tho", {"toc_do": 200, "do_sang": 70}, seconds=5)
    await hass.async_block_till_done()
    assert mem.cuoi()["vien"] == ("tho", {"do_sang": 70, "toc_do": 200, "do_sau": 0})
    assert mem.cuoi()["day"][0] == "co_dinh"              # vùng đáy không bị đụng
    lights.thu("day", "cau_vong_xoay", {}, seconds=5)
    await hass.async_block_till_done()
    assert mem.cuoi()["day"][0] == "cau_vong_xoay" and mem.cuoi()["vien"][0] == "tho"
    assert lights.attributes()["thu"].keys() == {"day", "vien"}
    assert lights.profiles == luu                          # KHÔNG lưu gì
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert mem.cuoi() == {"day": ("co_dinh", {"mau": "#0000ff", "do_sang": 60}), "vien": ("sang", {"do_sang": 60})}
    assert lights.attributes()["thu"] == {}


async def test_dung_thu_som_va_thu_sai_bi_tu_choi(hass, r1, den_sink):
    e, lights, mem = den_sink
    lights.thu("day", "phao_hoa", {}, seconds=30)
    await hass.async_block_till_done()
    assert mem.cuoi()["day"][0] == "phao_hoa"
    await hass.services.async_call("r1_speaker", "stop_preview_light", {"entity_id": CAI_DAT}, blocking=True)
    await hass.async_block_till_done()
    assert mem.cuoi()["day"][0] == "tat"
    for vung, hu in (("day", "sang"), ("vien", "cau_vong"), ("khac", "tho")):
        with pytest.raises(ServiceValidationError):
            lights.thu(vung, hu, {})
    await hass.services.async_call("r1_speaker", "preview_light", {
        "entity_id": CAI_DAT, "zone": "vien", "effect": "chay_duoi", "params": {"dai_duoi": 9}, "seconds": 5}, blocking=True)
    await hass.async_block_till_done()
    assert mem.cuoi()["vien"][1]["dai_duoi"] == 9


async def test_loi_tu_phien_dong_vi_loi_va_tu_pipeline(hass, r1, den_sink):
    e, lights, mem = den_sink
    talk = e.runtime_data.talk
    talk.claim("bo_dam")
    await hass.async_block_till_done()
    talk.end(talk.session, "xong", cut=False)
    await hass.async_block_till_done()
    assert lights.current == "cho"
    talk.claim("bo_dam")
    talk.end(talk.session, "loi_pipeline", cut=False)
    await hass.async_block_till_done()
    assert lights.current == "loi"
    lights._het_loi()
    await hass.async_block_till_done()
    assert lights.current == "cho"
    sat = _vet_tinh(hass)
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": "stt-stream-failed"}))
    await hass.async_block_till_done()
    assert lights.current == "loi"
    lights._het_loi()
    await hass.async_block_till_done()
    for code in ("stt-no-text-recognized", "wake-word-timeout"):      # «không nghe thấy gì» không phải hỏng
        sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": code}))
    sat._cat_luot()
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": "stt-stream-failed"}))
    await hass.async_block_till_done()
    assert lights.current == "cho"
    sat._cut_luot = sat._cut
    sat.on_pipeline_event(PipelineEvent(PipelineEventType.ERROR, {"code": "stt-stream-failed"}))
    await hass.async_block_till_done()
    assert lights.current == "loi"


async def test_doi_nhanh_nhieu_lan_chi_ap_ban_moi_nhat(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.cham = True
    for st in ("listening", "processing", "responding", "idle", "listening"):
        hass.states.async_set(SAT, st)
    await hass.async_block_till_done()
    assert lights.current == "nghe" and mem.cuoi()["day"][0] == "co_dinh"
    assert mem.cuoi()["vien"][0] == "sang"


async def test_cai_dat_duoc_luu_chi_phan_khac_mac_dinh_va_nap_lai(hass, r1, hass_storage):
    e = await _them(hass, r1)
    lights = e.runtime_data.lights
    await lights.async_set_function("loi", day={"effect": "chop", "params": {"so_chop": 4}})
    await lights.async_set_master(70)
    await hass.async_block_till_done()
    luu = next(v for k, v in hass_storage.items() if k.startswith("r1_speaker.lights."))["data"]
    assert luu["master"] == 70 and list(luu["functions"]) == ["loi"]
    assert luu["functions"]["loi"]["day"]["effect"] == "chop" and luu["functions"]["loi"]["day"]["params"]["so_chop"] == 4
    lights.profiles.update(DEFAULTS)
    lights.master = 100
    await lights.async_load()
    assert lights.profiles["loi"].day.params["so_chop"] == 4 and lights.master == 70


async def test_nap_ban_luu_cu_mo_hinh_phang_duoc_chuyen(hass, r1, hass_storage):
    e = await _them(hass, r1)
    lights = e.runtime_data.lights
    khoa = f"r1_speaker.lights.{e.entry_id}"
    hass_storage[khoa] = {"version": 1, "minor_version": 1, "key": khoa, "data": {
        "functions": {"dam_thoai": {"color": "#0000ff", "effect": "nhip_tim", "brightness": 55, "toc_do": 160, "rim": False}}}}
    lights.profiles.update(DEFAULTS)
    await lights.async_load()
    p = lights.profiles["dam_thoai"]
    assert p.day.effect == "nhip_tim" and p.day.params["do_sang"] == 55 and p.day.params["toc_do"] == 160
    assert p.day.params["mau"] == "#0000ff" and p.vien.effect == "tat"


async def test_sink_loi_khong_lam_hong_gi_va_tu_thu_lai(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.fail = "ADB: adbd bận"
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert lights.last_error == "ADB: adbd bận" and lights.sink_state == "loi_adb"
    mem.fail = None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=THU_LAI_S + 1))
    await hass.async_block_till_done()
    assert lights.last_error is None and mem.cuoi()["day"][0] == "co_dinh"


async def test_sink_khong_san_sang_thi_khong_ghi_gi(hass, r1, den_sink):
    e, lights, mem = den_sink
    mem.set_available(False)
    mem.clear()
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    assert mem.log == [] and lights.last_error is None


async def test_dong_tich_hop_tat_den_va_dung_phien(hass, r1, den_sink):
    e, lights, mem = den_sink
    hass.states.async_set(SAT, "listening")
    await hass.async_block_till_done()
    mem.clear()
    await lights.async_close()
    assert mem.log == [("tat",), ("dung",)]


async def test_thuoc_tinh_cho_the_co_danh_muc_va_khong_lo_khoa(hass, r1):
    import json
    e = await _them(hass, r1)
    a = hass.states.get(CAI_DAT).attributes["anh_sang"]
    assert set(a["chuc_nang"]) == set(FUNCTIONS) and a["danh_muc"]["vien"][0]["id"] == "sang"
    assert all(set(v) >= {"enabled", "day", "vien", "mac_dinh"} for v in a["chuc_nang"].values())
    assert a["thu_tu_uu_tien"] == list(UU_TIEN) and a["do_sang_chung"] == 100
    dump = json.dumps(a)
    for khoa in (e.data.get("mic_listen_key"), e.data.get("intercom_key")):
        assert not khoa or khoa not in dump
