"""Cài đặt chi tiết chỉnh ở thẻ: dịch vụ ``set_advanced_option`` + dữ liệu ``nang_cao`` của cảm biến cài đặt."""

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

from custom_components.r1_speaker import nang_cao
from custom_components.r1_speaker.settings import TalkSettings, noise_settings

from .test_tuy_chon import _them

SID = "sensor.r1_tom_tat_cai_dat"


async def _dat(hass, khoa, gia_tri, eid=SID):
    await hass.services.async_call("r1_speaker", "set_advanced_option",
                                   {"entity_id": eid, "key": khoa, "value": gia_tri}, blocking=True)
    await hass.async_block_till_done()


def _sid(hass):
    from homeassistant.helpers import entity_registry as er
    return next(e.entity_id for e in er.async_get(hass).entities.values() if e.translation_key == "settings")


async def test_thuoc_tinh_du_muoi_chin_cai_dat_dung_mac_dinh(hass, r1):
    e = await _them(hass, r1)
    ds = hass.states.get(_sid(hass)).attributes["am_thanh"]["nang_cao"]
    assert len(ds) == 19 == len(nang_cao.BANG)
    assert {d["nhom"] for d in ds} == {"thoai", "khu_tap", "agc", "han_dinh", "song_cong"}
    assert all(d["v"] == d["mac_dinh"] for d in ds)
    t = next(d for d in ds if d["k"] == "talk_silence_s")
    assert (t["min"], t["max"], t["kieu"]) == (0.2, 10, "so")


async def test_doi_mot_cai_dat_luu_ap_dung_sau_khi_nap_lai_va_mac_dinh_thi_khong_luu(hass, r1):
    e = await _them(hass, r1)
    await _dat(hass, "talk_silence_s", 0.8, _sid(hass))
    assert e.options == {"talk_silence_s": 0.8}
    assert e.runtime_data.intercom.settings == TalkSettings(-45.0, 0.8, 0.3, 0.5)    # đã nạp lại và áp dụng
    await _dat(hass, "noise_suppress", True, _sid(hass))
    assert e.options["noise_suppress"] is True and noise_settings(e).enabled
    await _dat(hass, "talk_silence_s", 1.5, _sid(hass))                                # về mặc định → bỏ khỏi options
    assert "talk_silence_s" not in e.options and e.options["noise_suppress"] is True
    ds = hass.states.get(_sid(hass)).attributes["am_thanh"]["nang_cao"]
    assert next(d for d in ds if d["k"] == "noise_suppress")["v"] is True


@pytest.mark.parametrize("khoa,gia_tri", [
    ("talk_silence_s", 99.0), ("talk_silence_s", 0.0), ("talk_silence_s", True), ("noise_suppress", 1),
    ("noise_suppress", "true"), ("agc_target_db", 5.0), ("khong_co_khoa_nay", 1.0), ("duplex_max_s", 10.0)])
async def test_gia_tri_sai_bi_tu_choi_va_khong_luu(hass, r1, khoa, gia_tri):
    e = await _them(hass, r1)
    with pytest.raises((ServiceValidationError, vol.Invalid)):        # kiểu sai bị lược đồ chặn, khoảng sai bị kiểm chặn
        await _dat(hass, khoa, gia_tri, _sid(hass))
    assert e.options == {}


async def test_giu_nguyen_khoa_an_da_co_khi_doi_cai_dat(hass, r1):
    e = await _them(hass, r1)
    hass.config_entries.async_update_entry(e, options={"play_host": "127.0.0.1", "play_port": 9})
    await _dat(hass, "duplex_vad_threshold", 0.7, _sid(hass))
    assert e.options == {"play_host": "127.0.0.1", "play_port": 9, "duplex_vad_threshold": 0.7}


async def test_thuc_the_la_bi_tu_choi(hass, r1):
    await _them(hass, r1)
    with pytest.raises(ServiceValidationError):
        await _dat(hass, "talk_silence_s", 1.0, "sensor.khong_phai_cua_r1")
