"""Tích hợp Phicomm R1 với loa giả (WebSocket thật ở 127.0.0.1)."""

import asyncio
import logging
from datetime import timedelta
from unittest import mock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry, async_fire_time_changed)

from custom_components.r1_speaker import const
from custom_components.r1_speaker.client import build_message
from custom_components.r1_speaker.const import DOMAIN

import json


@pytest.fixture(autouse=True)
def _nhanh():
    """Rút giờ chờ để ca mất kết nối không làm chậm bộ test."""
    with mock.patch("custom_components.r1_speaker.client.RESPONSE_TIMEOUT", 0.5):
        yield


async def _them(hass, r1) -> MockConfigEntry:
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        unique_id=f"127.0.0.1:{r1.port}")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def _chu_ky(hass: HomeAssistant, eid="sensor.phicomm_r1_device_state", state=None):
    """Tới chu kỳ hỏi loa kế tiếp, rồi chờ thực thể ``eid`` đạt ``state`` (làm mới chạy ở
    tác vụ nền nên async_block_till_done không đợi nó)."""
    async_fire_time_changed(hass, dt_util.utcnow() + const.SCAN_INTERVAL + timedelta(seconds=1))
    for _ in range(150):
        await asyncio.sleep(0.02)
        await hass.async_block_till_done()
        st = hass.states.get(eid).state
        if (st == state) if state is not None else True:
            return
    raise AssertionError(f"{eid} không đạt {state!r}, đang {st!r}")


def _num(hass, eid):
    return float(hass.states.get(eid).state)


def _st(hass, eid):
    return hass.states.get(eid)


async def test_doc_get_info(hass, r1):
    e = await _them(hass, r1)
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "1"
    assert _st(hass, "switch.phicomm_r1_dlna").state == STATE_ON
    assert _st(hass, "switch.phicomm_r1_airplay").state == STATE_OFF
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "1"
    d = e.runtime_data.data                       # đèn nhạc: đọc từ get_info, thực thể điều khiển ở test_den_nhac
    assert (d.music_light_enable, d.music_light_luma, d.music_light_chroma) == (True, 50, 60)
    # EQ đọc từ get_eq_config
    assert _st(hass, "switch.phicomm_r1_bass_boost").state == STATE_OFF
    # Sửa ca cũ: loa giả giờ trả get_eq_config THẬT (tests/du_lieu_that.py) thay cho số tự
    # nghĩ. Loa thật: loudness TẮT, dải 230 Hz = -400, bass 200.
    assert _st(hass, "switch.phicomm_r1_loudness").state == STATE_OFF
    assert _num(hass, "number.phicomm_r1_eq_230_hz") == -400
    assert _num(hass, "number.phicomm_r1_bass_strength") == 200
    assert _num(hass, "number.phicomm_r1_loudness_gain") == 200


@pytest.mark.parametrize("entity,field,msg_type,payload", [
    ("switch.phicomm_r1_dlna", None, "Set_DLNA_Open", {"open": False}),
    ("switch.phicomm_r1_airplay", None, "Set_AirPlay_Open", {"open": True}),
    ("switch.phicomm_r1_bass_boost", None, "set_bass_enable", {"enable": True}),
    # Sửa ca cũ: loudness thật đang TẮT nên đổi sang BẬT mới là một lần đổi trạng thái.
    ("switch.phicomm_r1_loudness", None, "set_loudness_enable", {"enable": True}),
    ("switch.phicomm_r1_eq", None, "set_eq_enable", {"enable": False}),
])
async def test_doi_tung_switch(hass, r1, entity, field, msg_type, payload):
    await _them(hass, r1)
    turn_on = next(iter(payload.values())) is True
    await hass.services.async_call("switch", "turn_on" if turn_on else "turn_off",
                                   {"entity_id": entity}, blocking=True)
    cmds = r1.commands(msg_type)
    assert len(cmds) == 1
    for k, v in payload.items():
        assert cmds[0]["data"][k] == v  # khung theo hợp đồng
        assert cmds[0][k] == v          # và khung phẳng như web của loa
    assert _st(hass, entity).state == (STATE_ON if turn_on else STATE_OFF)


@pytest.mark.parametrize("band,name", enumerate(
    ["60_hz", "230_hz", "910_hz", "3_6_khz", "14_khz"]))
async def test_eq_tung_dai(hass, r1, band, name):
    await _them(hass, r1)
    eid = f"number.phicomm_r1_eq_{name}"
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": eid, "value": -500}, blocking=True)
    (cmd,) = r1.commands("set_eq_bandlevel")
    assert cmd["data"] == {"band": band, "level": -500}
    assert _num(hass, eid) == -500


async def test_bass_strength_va_loudness_gain(hass, r1):
    await _them(hass, r1)
    await hass.services.async_call("number", "set_value", {
        "entity_id": "number.phicomm_r1_bass_strength", "value": 800}, blocking=True)
    await hass.services.async_call("number", "set_value", {
        "entity_id": "number.phicomm_r1_loudness_gain", "value": 400}, blocking=True)
    assert r1.commands("set_bass_strength")[0]["data"] == {"strength": 800}
    assert r1.commands("set_loudness_gain")[0]["data"] == {"gain": 400}


async def test_mat_ket_noi_roi_tu_khoi_phuc(hass, r1, caplog):
    await _them(hass, r1)
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "1"
    await r1.stop()
    with caplog.at_level(logging.WARNING):
        await _chu_ky(hass, state=STATE_UNAVAILABLE)
    for eid in ("switch.phicomm_r1_dlna", "sensor.phicomm_r1_device_state", "number.phicomm_r1_eq_60_hz"):
        assert _st(hass, eid).state == STATE_UNAVAILABLE
    assert any(r.levelno == logging.WARNING and "R1" in r.message for r in caplog.records)
    await r1.start()  # cùng cổng
    r1.state["device_state"] = 3
    await _chu_ky(hass, state="3")
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "3"


async def test_loa_tat_luc_khoi_dong_van_them_va_hoi_phuc(hass, r1):
    await r1.stop()
    await _them(hass, r1)
    assert _st(hass, "sensor.phicomm_r1_device_state").state == STATE_UNAVAILABLE
    await r1.start()
    await _chu_ky(hass, state="1")
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "1"


@pytest.mark.parametrize("mode", ["garbage_info", "silent", "drop"])
async def test_phan_hoi_sai_khong_crash(hass, r1, mode):
    r1.mode = mode
    await _them(hass, r1)
    assert _st(hass, "sensor.phicomm_r1_device_state").state == STATE_UNAVAILABLE
    r1.mode = "ok"
    await _chu_ky(hass, state="1")
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "1"


async def test_eq_sai_dinh_dang_chi_mat_phan_eq(hass, r1):
    r1.mode = "bad_eq"
    await _them(hass, r1)
    assert _st(hass, "sensor.phicomm_r1_device_state").state == "1"
    assert _st(hass, "switch.phicomm_r1_bass_boost").state == STATE_UNAVAILABLE
    assert _st(hass, "number.phicomm_r1_eq_60_hz").state == STATE_UNAVAILABLE


async def test_gui_lenh_khi_loa_chet_bao_loi_khong_sap_vong(hass, r1):
    await _them(hass, r1)
    await r1.stop()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_off", {
            "entity_id": "switch.phicomm_r1_dlna"}, blocking=True)
    await r1.start()
    r1.state["device_state"] = 5
    await _chu_ky(hass, state="5")  # vòng cập nhật vẫn sống sau lệnh hỏng
    assert _st(hass, "switch.phicomm_r1_dlna").state == STATE_ON


def test_khung_lenh_theo_hop_dong():
    m = json.loads(build_message("get_info"))
    assert m["type"] == "get_info" and m["data"] == {}


async def test_config_flow(hass, r1):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert res["type"] is FlowResultType.FORM
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert res["data"] == {"host": "127.0.0.1", "port": r1.port}


async def test_config_flow_loa_khong_tra_loi(hass, r1):
    r1.mode = "garbage_info"
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port})
    assert res["type"] is FlowResultType.FORM
    assert res["errors"] == {"base": "cannot_connect"}


async def test_config_flow_loa_moi_reset_adb_song_cong_dieu_khien_chua_co_van_them_duoc(hass, r1, monkeypatch):
    """Yêu cầu chủ máy: phải cài đặt được loa kể cả khi reset ban đầu (cổng 8080 chưa có, ADB 5555 sống)."""
    from custom_components.r1_speaker import config_flow

    async def adb_song(host):
        return True

    monkeypatch.setattr(config_flow, "_thu_adb", adb_song)
    r1.mode = "garbage_info"
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    res = await hass.config_entries.flow.async_configure(res["flow_id"], {"host": "127.0.0.1", "port": r1.port})
    assert res["type"] is FlowResultType.FORM and res["step_id"] == "chua_co_dich_vu" and not res.get("errors")
    assert res["description_placeholders"]["adb_port"] == "5555"
    res = await hass.config_entries.flow.async_configure(res["flow_id"], {})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert res["data"] == {"host": "127.0.0.1", "port": r1.port}


async def test_config_flow_ca_dieu_khien_lan_adb_khong_tra_loi_van_bao_loi(hass, r1, monkeypatch):
    from custom_components.r1_speaker import config_flow

    async def adb_chet(host):
        return False

    monkeypatch.setattr(config_flow, "_thu_adb", adb_chet)
    r1.mode = "garbage_info"
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    res = await hass.config_entries.flow.async_configure(res["flow_id"], {"host": "127.0.0.1", "port": r1.port})
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"base": "cannot_connect"}


async def test_thu_adb_that_khong_co_adbd_thi_false():
    from custom_components.r1_speaker import config_flow
    assert await config_flow._thu_adb("127.0.0.1") is False          # không có adbd cổng 5555 trên máy thử


def test_mac_dinh_theo_hop_dong():
    assert const.DEFAULT_HOST == ""
