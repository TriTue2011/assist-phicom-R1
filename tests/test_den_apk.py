"""Đèn viền/đáy qua APK loa → máy chủ đèn quyền shell.

APK loa giả nối thật vào đầu nhận mic của tích hợp (như ``test_den_nhac``): đọc các khung điều khiển đèn HA gửi
xuống, báo trạng thái ``den_trang_thai`` lên. Định dạng khung là hợp đồng với ``LenhDieuKhien.java``.
"""

import asyncio
import json

import pytest

from custom_components.r1_speaker.den_apk import ApkLights
from custom_components.r1_speaker.den_port import LightsError, Step
from custom_components.r1_speaker.hieu_ung import sang_rgb, sang_vien

from .test_den_nhac import (_cong_trong, _goi, _khung_xuong, _noi_apk, _st, _them_co_dau_nhan)
from .test_mic_server import KHOA, cho, khung, khung_json, noi

DICH_VU, DO_SANG = "binary_sensor.r1_dich_vu_den", "number.r1_do_sang_den"
SAT = "assist_satellite.r1"


async def _doc_khung_hoac_none(reader, han: float = 0.3):
    try:
        n = int.from_bytes(await asyncio.wait_for(reader.readexactly(4), han), "big")
    except asyncio.TimeoutError:
        return None
    return await asyncio.wait_for(reader.readexactly(n), 1)


async def _bo_khung(reader) -> int:
    """Đọc và bỏ mọi khung đang chờ (đèn hiện tại được áp lại khi máy chủ đèn sẵn sàng)."""
    dem = 0
    while await _doc_khung_hoac_none(reader) is not None:
        dem += 1
    return dem


async def _bao_trang_thai(writer, san_sang: bool) -> None:
    writer.write(khung_json({"type": "den_trang_thai", "san_sang": san_sang}))
    await writer.drain()


async def test_khung_den_dung_hop_dong_va_gioi_han_gia_tri(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    server = e.runtime_data.mic_server
    await server.gui_den_vien(128)
    assert await _khung_xuong(reader) == b'{"type":"den_vien","muc":128}'
    await server.gui_den_day("00ff7f")
    assert await _khung_xuong(reader) == b'{"type":"den_day","rgb":"00ff7f"}'
    await server.hoi_den()
    assert await _khung_xuong(reader) == b'{"type":"den_hoi"}'
    for muc in (-1, 256, True, "9"):
        with pytest.raises(ValueError):
            await server.gui_den_vien(muc)
    for rgb in ("00FF7F", "00ff7", "gg0000", "#00ff7f", 0, None):
        with pytest.raises(ValueError):
            await server.gui_den_day(rgb)
    writer.close()


async def test_trang_thai_dich_vu_den_tu_apk_va_json_la_khong_lot_vao_tieng(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    mic, server = e.runtime_data.mic, e.runtime_data.mic_server
    khuc: list[bytes] = []
    mic.add_chunk_listener(khuc.append)
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    assert server.den_san_sang is None and _st(hass, DICH_VU) == "unknown"
    await _bao_trang_thai(writer, True)
    await cho(lambda: server.den_san_sang is True)
    await hass.async_block_till_done()
    assert _st(hass, DICH_VU) == "on"
    await _bao_trang_thai(writer, False)
    await cho(lambda: server.den_san_sang is False)
    await hass.async_block_till_done()
    assert _st(hass, DICH_VU) == "off"
    # Khung JSON hợp lệ nhưng LẠ không được coi là tiếng (trước đây mọi JSON không phải «end» bị đẩy vào mic).
    # (Khung bắt đầu bằng «{» mà không phải JSON hợp lệ thì không phân biệt được với PCM thật: vẫn là tiếng.)
    writer.write(khung_json({"type": "gi_do_la", "x": 1}))
    writer.write(khung(b"\x01\x00" * 160))                       # một khung PCM thật
    await writer.drain()
    await cho(lambda: len(khuc) >= 1)
    assert khuc == [b"\x01\x00" * 160]
    assert not any(b"gi_do_la" in c for c in khuc)
    writer.close()
    await cho(lambda: server.den_san_sang is None)               # loa đứt: không còn biết
    await hass.async_block_till_done()
    assert _st(hass, DICH_VU) == "unavailable"


async def test_sink_apk_chi_san_sang_khi_loa_noi_va_may_chu_den_chay(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    sink = e.runtime_data.lights.sink
    assert isinstance(sink, ApkLights) and not sink.available and sink.ly_do == "mat_ket_noi"
    reader, writer = await _noi_apk(e, port)
    assert not sink.available and sink.ly_do == "CHO_DICH_VU_DEN"   # loa nối, máy chủ đèn chưa báo
    await _bao_trang_thai(writer, True)
    await cho(lambda: sink.available)
    assert e.runtime_data.lights.sink_state == "san_sang"
    assert await _bo_khung(reader) >= 2                              # HA tự áp lại đèn hiện tại (viền + đáy)
    await sink.set_rim(40)
    assert await _khung_xuong(reader) == b'{"type":"den_vien","muc":40}'
    await sink.set_base((0, 128, 255))
    assert await _khung_xuong(reader) == b'{"type":"den_day","rgb":"0080ff"}'
    with pytest.raises(ValueError):
        await sink.set_rim(300)
    writer.close()
    await cho(lambda: not sink.available)
    with pytest.raises(LightsError):
        await sink.set_rim(10)


async def test_hieu_ung_chay_qua_sink_va_dung_duoc(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    sink = e.runtime_data.lights.sink
    reader, writer = await _noi_apk(e, port)
    await _bao_trang_thai(writer, True)
    await cho(lambda: sink.available)
    await _bo_khung(reader)                                      # bỏ các khung áp lại đèn lúc sẵn sàng
    await sink.play_effect([Step(rim=10, seconds=0.06), Step(rim=20, seconds=0.06)], repeat=True)
    thay = []
    for _ in range(4):
        thay.append(json.loads(await _khung_xuong(reader))["muc"])
    assert thay[:4] == [10, 20, 10, 20]                          # lặp đúng thứ tự
    await sink.stop_effect()
    await _bo_khung(reader)                                       # khung còn đang bay lúc dừng
    assert await _doc_khung_hoac_none(reader, 0.4) is None        # dừng rồi thì không còn khung nào
    writer.close()


async def test_ap_dung_den_hien_tai_khi_may_chu_den_san_sang_va_do_sang_chung(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    lights = e.runtime_data.lights
    # chức năng «chờ»: bật, có viền, xanh lá, sáng 100 %
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": "sensor.r1_cai_dat", "function": "cho", "enabled": True, "rim": True,
        "color": "#00ff00", "brightness": 100}, blocking=True)
    reader, writer = await _noi_apk(e, port)
    await _bao_trang_thai(writer, True)                          # máy chủ đèn lên → HA TỰ áp lại đèn hiện tại
    khung_vien, khung_day = await _khung_xuong(reader), await _khung_xuong(reader)
    assert json.loads(khung_vien) == {"type": "den_vien", "muc": sang_vien(100)}
    assert json.loads(khung_day) == {"type": "den_day", "rgb": "00ff00"}
    assert _st(hass, DO_SANG) == "100"
    await _goi(hass, "number", "set_value", DO_SANG, value=40)   # độ sáng chung 40 % nhân vào mọi chức năng
    assert lights.master == 40 and _st(hass, DO_SANG) == "40"
    v, d = json.loads(await _khung_xuong(reader)), json.loads(await _khung_xuong(reader))
    assert v == {"type": "den_vien", "muc": sang_vien(40)}
    r, g, b = sang_rgb((0, 255, 0), 40)
    assert d == {"type": "den_day", "rgb": f"{r:02x}{g:02x}{b:02x}"}
    writer.close()


async def test_do_sang_chung_duoc_nho_va_chan_gia_tri_sai(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    lights = e.runtime_data.lights
    await _goi(hass, "number", "set_value", DO_SANG, value=25)
    assert lights.master == 25
    assert lights._du_lieu()["master"] == 25                      # được lưu (chỉ lưu khi khác 100)
    await _goi(hass, "number", "set_value", DO_SANG, value=100)
    assert "master" not in lights._du_lieu()
    from homeassistant.exceptions import ServiceValidationError
    for sai in (-1, 101, True, 12.5):
        with pytest.raises(ServiceValidationError):
            await lights.async_set_master(sai)
