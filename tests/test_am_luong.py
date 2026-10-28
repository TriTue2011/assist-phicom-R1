"""Âm lượng NHẠC của loa qua APK: ``AudioManager.setStreamVolume`` (chủ máy nghe xác nhận 22/10/2026: 0 mất tiếng, 8 to hơn).

APK loa giả nối thật vào đầu nhận mic, báo ``am_luong_trang_thai`` và đọc khung ``am_luong`` HA gửi xuống. Khung là hợp đồng
với ``LenhDieuKhien.java`` (khoá đúng thứ tự, dạng tách gọn). Thực thể số ``number.r1_am_luong``… và ``media_player.r1_loa``
(thẻ YouTube chỉnh âm lượng loa bằng ``volume_set``) dùng chung một nguồn.
"""

import asyncio
import json

import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .test_den_nhac import _goi, _khung_xuong, _noi_apk, _them_co_dau_nhan
from .test_mic_server import cho, khung_json

PLAYER = "media_player.r1_loa"


def _so_am_luong(hass) -> str:
    """``number`` âm lượng: tìm trong sổ đăng ký theo unique_id kết thúc ``_volume`` (thực thể không khả dụng không có thuộc tính)."""
    from homeassistant.helpers import entity_registry as er
    for ent in er.async_get(hass).entities.values():
        if ent.domain == "number" and ent.platform == "r1_speaker" and ent.unique_id.endswith("_volume"):
            return ent.entity_id
    raise AssertionError("không có number âm lượng")


def _gt(hass, eid):
    """Giá trị số của một thực thể (HA có thể viết ``7`` hoặc ``7.0``); không phải số (unavailable…) thì trả chuỗi."""
    st = hass.states.get(eid).state
    try:
        return float(st)
    except ValueError:
        return st


async def _bao(writer, muc, toi_da=15):
    writer.write(khung_json({"type": "am_luong_trang_thai", "muc": muc, "toi_da": toi_da}))
    await writer.drain()


async def test_am_luong_khong_kha_dung_khi_chua_noi_hoac_apk_cu_khong_bao(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    so = _so_am_luong(hass)
    assert hass.states.get(so).state == "unavailable"            # chưa có APK
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    assert hass.states.get(so).state == "unavailable"            # APK cũ không báo âm lượng: không giả vờ có
    assert hass.states.get(PLAYER).attributes.get("volume_level") is None
    writer.close()


async def test_apk_bao_muc_thi_number_va_media_player_theo_dung(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    so = _so_am_luong(hass)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, 7)
    await cho(lambda: _gt(hass, so) == 7)
    p = hass.states.get(PLAYER)
    assert p.attributes["volume_level"] == pytest.approx(7 / 15, abs=1e-3)
    feats = p.attributes["supported_features"]
    assert feats & MediaPlayerEntityFeature.VOLUME_SET and feats & MediaPlayerEntityFeature.VOLUME_STEP
    await _bao(writer, 3)                                         # vuốt/đổi ở loa → thanh trượt theo
    await cho(lambda: _gt(hass, so) == 3)
    assert hass.states.get(PLAYER).attributes["volume_level"] == pytest.approx(3 / 15, abs=1e-3)
    writer.close()


async def test_dat_am_luong_gui_dung_khung_tu_number_volume_set_va_volume_up(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    so = _so_am_luong(hass)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, 7)
    await cho(lambda: _gt(hass, so) == 7)
    await _goi(hass, "number", "set_value", so, value=9)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":9}'
    await hass.services.async_call("media_player", "volume_set", {"entity_id": PLAYER, "volume_level": 0.2}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":3}'      # 0,2 × 15
    await hass.services.async_call("media_player", "volume_set", {"entity_id": PLAYER, "volume_level": 1.0}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":15}'
    await hass.services.async_call("media_player", "volume_set", {"entity_id": PLAYER, "volume_level": 0.0}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":0}'
    await _bao(writer, 7)
    await cho(lambda: hass.states.get(PLAYER).attributes.get("volume_level") == pytest.approx(7 / 15, abs=1e-3))
    await hass.services.async_call("media_player", "volume_up", {"entity_id": PLAYER}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":8}'
    writer.close()


async def test_khung_trang_thai_sai_bi_bo_qua_va_mat_ket_noi_thi_het_kha_dung(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    so = _so_am_luong(hass)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, 7)
    await cho(lambda: _gt(hass, so) == 7)
    for xau in ({"muc": 99, "toi_da": 15}, {"muc": -1, "toi_da": 15}, {"muc": "8", "toi_da": 15},
                {"muc": 8, "toi_da": 0}, {"muc": True, "toi_da": 15}, {"muc": 8}):
        writer.write(khung_json({"type": "am_luong_trang_thai", **xau}))
    await writer.drain()
    await asyncio.sleep(0.2)
    assert _gt(hass, so) == 7                    # mọi khung hỏng bị bỏ, không đổi trạng thái
    writer.close()
    await cho(lambda: hass.states.get(so).state == "unavailable")


async def test_dat_am_luong_khi_loa_chua_noi_bao_loi_ro_rang(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    server = e.runtime_data.mic_server
    with pytest.raises(ValueError):
        await server.gui_am_luong(16)
    with pytest.raises(ValueError):
        await server.gui_am_luong(True)
    with pytest.raises(ConnectionError):
        await server.gui_am_luong(8)


async def test_tat_tieng_loa_nho_muc_cu_va_bat_lai_dung_muc(hass, r1):
    """Nút «Tắt tiếng loa» (chủ máy 28/10/2026): tắt = âm lượng 0 và nhớ mức cũ; bật = trả về đúng mức đã nhớ; khác «Tắt mic»."""
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, 9)
    await cho(lambda: hass.states.get(PLAYER).attributes.get("volume_level") == pytest.approx(9 / 15, abs=1e-3))
    feats = hass.states.get(PLAYER).attributes["supported_features"]
    assert feats & MediaPlayerEntityFeature.VOLUME_MUTE and hass.states.get(PLAYER).attributes["is_volume_muted"] is False
    await hass.services.async_call("media_player", "volume_mute", {"entity_id": PLAYER, "is_volume_muted": True}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":0}'
    await _bao(writer, 0)                                              # APK báo lại mức thật
    await cho(lambda: hass.states.get(PLAYER).attributes.get("is_volume_muted") is True)
    await hass.services.async_call("media_player", "volume_mute", {"entity_id": PLAYER, "is_volume_muted": False}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":9}'      # đúng mức trước khi tắt
    await _bao(writer, 9)
    await cho(lambda: hass.states.get(PLAYER).attributes.get("is_volume_muted") is False)
    writer.close()


async def test_bat_tieng_khi_chua_tung_tat_thi_lay_nua_thang_va_loa_chua_noi_bao_loi(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, 0)                                              # loa đang 0 (tắt từ lúc khởi động), chưa từng «tắt» qua HA
    await cho(lambda: hass.states.get(PLAYER).attributes.get("is_volume_muted") is True)
    await hass.services.async_call("media_player", "volume_mute", {"entity_id": PLAYER, "is_volume_muted": False}, blocking=True)
    assert await _khung_xuong(reader) == b'{"type":"am_luong","muc":8}'      # nửa thang 15 → 8
    writer.close()
    await asyncio.sleep(0.1)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("media_player", "volume_mute", {"entity_id": PLAYER, "is_volume_muted": True}, blocking=True)
