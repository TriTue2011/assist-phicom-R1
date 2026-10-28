"""Công tắc kết nối của loa R1: DLNA, AirPlay (đã có) và Bluetooth (mới), hiện ở thẻ để dò lỗi (chủ máy 28/10/2026)."""

from unittest import mock

import pytest
from homeassistant.helpers import entity_registry as er

from .test_r1 import _them

BT = "switch.r1_bluetooth"


def _id(hass, khoa):
    reg = er.async_get(hass)
    return next(e.entity_id for e in reg.entities.values() if e.platform == "r1_speaker" and e.translation_key == khoa
                and e.domain == "switch")


async def test_ba_cong_tac_ket_noi_deu_co_va_khong_bi_an(hass, r1):
    await _them(hass, r1)
    reg = er.async_get(hass)
    for khoa in ("dlna", "airplay", "bluetooth"):
        e = reg.async_get(_id(hass, khoa))
        assert e is not None and e.entity_category is None, f"{khoa} phải hiện, không ẩn ở mục Cấu hình"


async def test_cong_tac_dlna_khai_chan_doan_renderer(hass, r1):
    await _them(hass, r1)
    st = hass.states.get(_id(hass, "dlna"))
    assert st.attributes["renderer"] == "chưa thử"


async def test_bluetooth_gui_lenh_va_doc_lai_trang_thai_qua_adb(hass, r1):
    entry = await _them(hass, r1)
    he = entry.runtime_data.he_thong
    sent = []

    async def gui(self_, on):
        sent.append(on)

    with mock.patch("custom_components.r1_speaker.client.R1Client.set_bluetooth", new=gui), \
            mock.patch("custom_components.r1_speaker.switch.BT_DOI_DOC_LAI", 0), \
            mock.patch.object(he, "async_request_refresh", new=mock.AsyncMock()) as doc_lai:
        await hass.services.async_call("switch", "turn_on", {"entity_id": _id(hass, "bluetooth")}, blocking=True)
    assert sent == [True] and doc_lai.await_count == 1


async def test_bluetooth_trang_thai_lay_tu_adb_khong_lac_quan(hass, r1):
    """Sau lệnh mà ADB vẫn báo tắt thì công tắc vẫn «off» (biết lệnh không có tác dụng), không tự đoán bật."""
    from custom_components.r1_speaker.he_thong import HeThong
    entry = await _them(hass, r1)
    he = entry.runtime_data.he_thong
    he.async_set_updated_data(HeThong(bluetooth=False))
    await hass.async_block_till_done()
    eid = _id(hass, "bluetooth")
    with mock.patch("custom_components.r1_speaker.client.R1Client.set_bluetooth", new=mock.AsyncMock()), \
            mock.patch("custom_components.r1_speaker.switch.BT_DOI_DOC_LAI", 0), \
            mock.patch.object(he, "async_request_refresh", new=mock.AsyncMock()):
        await hass.services.async_call("switch", "turn_on", {"entity_id": eid}, blocking=True)
    assert hass.states.get(eid).state == "off"
    he.async_set_updated_data(HeThong(bluetooth=True))
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "on"
    he.async_set_updated_data(HeThong(bluetooth=None))
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unknown"
