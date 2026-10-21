"""EQ / bass / loudness / preset, dữ liệu mẫu là get_eq_config ĐO TRÊN LOA THẬT."""

import json

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError

from custom_components.r1_speaker import const
from custom_components.r1_speaker.client import R1Error, parse_eq

from .du_lieu_that import GET_EQ_CONFIG, GET_EQ_CONFIG_DATA, GET_EQ_CONFIG_MSG
from .test_r1 import _num, _st, _them


def test_fixture_la_chuoi_json_that():
    assert isinstance(GET_EQ_CONFIG_DATA, str)
    assert GET_EQ_CONFIG["eq"]["Bands"]["minBandLevel"] == -1500


def test_parse_dung_5_dai_va_gioi_han():
    p = parse_eq(GET_EQ_CONFIG_MSG)
    assert p["bands"] == (200, -400, -100, -500, 100)
    assert (p["eq_min"], p["eq_max"]) == (-1500, 1500)


def test_parse_bass_loudness_eq_enable():
    p = parse_eq(GET_EQ_CONFIG_MSG)
    assert p["bass_enable"] is False and p["bass_strength"] == 200
    assert p["loudness_enable"] is False and p["loudness_gain"] == 200
    assert p["eq_enable"] is True


def test_parse_preset():
    p = parse_eq(GET_EQ_CONFIG_MSG)
    assert len(p["eq_presets"]) == 10
    assert p["eq_presets"][0] == (0, "Normal") and p["eq_presets"][9] == (9, "Rock")
    assert p["eq_preset"] == -1


def test_parse_dung_co_enable_khi_hai_co_khac_nhau():
    data = json.loads(GET_EQ_CONFIG_DATA)
    data["bass"]["Bass_Enable"] = True       # cờ chính
    data["bass"]["sound_effects_bass_enable"] = False
    assert parse_eq({"type": "get_eq_config", "data": data})["bass_enable"] is True
    del data["bass"]["Bass_Enable"]          # chỉ còn cờ sound_effects_*
    data["bass"]["sound_effects_bass_enable"] = True
    assert parse_eq({"type": "get_eq_config", "data": data})["bass_enable"] is True


def test_parse_khoa_vang_la_none():
    p = parse_eq({"type": "get_eq_config", "data": {"eq": {}}})
    assert p["eq_min"] is None and p["eq_presets"] is None and p["eq_enable"] is None
    assert p["bands"] == (None,) * 5


def test_parse_preset_sai_dinh_dang():
    data = json.loads(GET_EQ_CONFIG_DATA)
    data["eq"]["Preset_list"] = [{"Preset": 0}]
    with pytest.raises(R1Error):
        parse_eq({"type": "get_eq_config", "data": data})


async def test_thuc_the_doc_dung_du_lieu_that(hass, r1):
    await _them(hass, r1)
    for i, (name, lv) in enumerate(zip(
            ["60_hz", "230_hz", "910_hz", "3_6_khz", "14_khz"], (200, -400, -100, -500, 100))):
        eid = f"number.phicomm_r1_eq_{name}"
        assert _num(hass, eid) == lv, i
        st = _st(hass, eid)
        assert st.attributes["min"] == -1500 and st.attributes["max"] == 1500
    assert _st(hass, "switch.phicomm_r1_eq").state == STATE_ON
    assert _st(hass, "switch.phicomm_r1_bass_boost").state == STATE_OFF
    assert _st(hass, "switch.phicomm_r1_loudness").state == STATE_OFF
    assert _num(hass, "number.phicomm_r1_bass_strength") == 200
    assert _num(hass, "number.phicomm_r1_loudness_gain") == 200


async def test_dai_vuot_1000_van_ghi_duoc_den_1500(hass, r1):
    """Giới hạn lấy từ loa (±1500), không phải -1000..1000 cũ."""
    await _them(hass, r1)
    eid = "number.phicomm_r1_eq_60_hz"
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": eid, "value": 1400}, blocking=True)
    (cmd,) = r1.commands("set_eq_bandlevel")
    assert cmd["data"] == {"band": 0, "level": 1400}
    with pytest.raises(Exception):
        await hass.services.async_call("number", "set_value",
                                       {"entity_id": eid, "value": 1600}, blocking=True)
    assert len(r1.commands("set_eq_bandlevel")) == 1


async def test_gioi_han_du_phong_khi_loa_khong_bao(hass, r1):
    data = json.loads(GET_EQ_CONFIG_DATA)
    del data["eq"]["Bands"]["minBandLevel"], data["eq"]["Bands"]["maxBandLevel"]
    r1.eq = {**GET_EQ_CONFIG_MSG, "data": json.dumps(data)}
    await _them(hass, r1)
    st = _st(hass, "number.phicomm_r1_eq_60_hz")
    assert (st.attributes["min"], st.attributes["max"]) == (const.EQ_MIN, const.EQ_MAX)


async def test_select_preset_doc_ten_va_khong_chon_khi_la_minus_1(hass, r1):
    await _them(hass, r1)
    st = _st(hass, "select.phicomm_r1_eq_preset")
    assert st.attributes["options"] == ["Normal", "Classical", "Dance", "Flat", "Folk",
                                        "Heavy Metal", "Hip Hop", "Jazz", "Pop", "Rock"]
    assert st.state == "unknown"       # Current_Preset = -1: đang chỉnh tay


async def test_select_preset_hien_preset_dang_dung(hass, r1):
    data = json.loads(GET_EQ_CONFIG_DATA)
    data["eq"]["Current_Preset"] = 9
    r1.eq = {**GET_EQ_CONFIG_MSG, "data": json.dumps(data)}
    await _them(hass, r1)
    assert _st(hass, "select.phicomm_r1_eq_preset").state == "Rock"


async def test_chon_preset_bao_loi_va_khong_gui_lenh(hass, r1):
    """Lệnh đặt preset CHƯA xác định → không gửi lệnh tự nghĩ lên loa."""
    await _them(hass, r1)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("select", "select_option", {
            "entity_id": "select.phicomm_r1_eq_preset", "option": "Rock"}, blocking=True)
    assert [m for m in r1.received if m["type"].startswith(("set_", "Set_"))] == []


async def test_eq_hong_thi_select_va_switch_eq_unavailable(hass, r1):
    r1.mode = "bad_eq"
    await _them(hass, r1)
    assert _st(hass, "select.phicomm_r1_eq_preset").state == STATE_UNAVAILABLE
    assert _st(hass, "switch.phicomm_r1_eq").state == STATE_UNAVAILABLE
