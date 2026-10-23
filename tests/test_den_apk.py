"""Đèn bằng hiệu ứng CÓ SẴN của firmware (cách app AI box): HA → khung ``den_hieu_ung`` → APK → ``msgcenter.sendMsg``.

APK loa giả nối thật vào đầu nhận mic của tích hợp (như ``test_den_nhac``): đọc các khung điều khiển đèn HA gửi xuống,
báo ``den_trang_thai`` (kèm ``che_do = firmware``) lên. Định dạng khung là hợp đồng với ``LenhDieuKhien.java``.
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

from custom_components.r1_speaker import den_firmware as fw
from custom_components.r1_speaker.den_apk import ApkLights
from custom_components.r1_speaker.den_port import LightsError

from .test_den_nhac import _goi, _khung_xuong, _noi_apk, _st, _them_co_dau_nhan
from .test_mic_server import cho, khung, khung_json

DICH_VU, DO_SANG = "binary_sensor.r1_dich_vu_den", "number.r1_do_sang_den"
CAI_DAT = "sensor.r1_cai_dat"
JAVA = Path(__file__).parent.parent / "apk" / "nguon" / "src" / "vn" / "r1" / "bodam" / "TrungTamTin.java"


async def _doc_khung_hoac_none(reader, han: float = 0.3):
    try:
        n = int.from_bytes(await asyncio.wait_for(reader.readexactly(4), han), "big")
    except asyncio.TimeoutError:
        return None
    return await asyncio.wait_for(reader.readexactly(n), 1)


async def _bo_khung(reader) -> int:
    dem = 0
    while await _doc_khung_hoac_none(reader) is not None:
        dem += 1
    return dem


async def _lay_id(reader, so: int) -> list[int]:
    ra = []
    for _ in range(so):
        j = json.loads(await _khung_xuong(reader))
        assert j["type"] == "den_hieu_ung"
        ra.append(j["id"])
    return ra


async def _bao(writer, san_sang: bool, che_do: str | None = "firmware") -> None:
    d = {"type": "den_trang_thai", "san_sang": san_sang}
    if che_do is not None:
        d["che_do"] = che_do
    writer.write(khung_json(d))
    await writer.drain()


def test_danh_sach_id_o_ha_khop_danh_sach_cho_phep_o_apk():
    """Hai danh sách ID (HA và APK) nằm ở hai ngôn ngữ: đổi một bên mà quên bên kia là đèn im lặng."""
    java = JAVA.read_text(encoding="utf-8")
    khoi = re.search(r"HIEU_UNG_HOP_LE = \{(.*?)\};", java, re.S).group(1)
    assert {int(x) for x in re.findall(r"\d+", khoi)} == set(fw.ID_HOP_LE)


def test_moi_to_hop_mau_hieu_ung_ra_id_hop_le_va_dung_y():
    assert fw.id_day((0, 255, 0), False, 60) == 501 and fw.id_day((255, 0, 0), False, 60) == 500
    assert fw.id_day((0, 0, 255), False, 60) == 502 and fw.id_day((0, 0, 255), True, 60) == 203
    assert fw.id_day((255, 0, 0), True, 60) == 206 and fw.id_day((255, 140, 0), True, 60) == 200
    assert fw.id_day((0, 255, 0), True, 60) == 501          # xanh lá không có «thở»: rơi về sáng cố định
    assert fw.id_day((255, 255, 255), False, 60) == 202     # trắng không có sáng cố định ở đáy: thở trắng là gần nhất
    assert fw.id_day((0, 255, 0), False, 0) == fw.DAY_TAT   # sáng 0 = tắt
    assert fw.id_day((10, 10, 10), False, 80) == fw.DAY_TAT  # quá tối = tắt
    assert fw.id_day((255, 0, 0), "nhap_nhay", 60) == 206          # nháy: chỉ đỏ có
    assert fw.id_day((0, 0, 255), "nhap_nhay", 60) == 203          # màu khác: rơi về thở
    assert fw.id_day((0, 255, 0), "nhap_nhay", 60) == 501          # xanh lá không có thở: sáng cố định
    assert fw.id_vien(True, 60) == 503 and fw.id_vien(True, 0) == 505 and fw.id_vien(False, 60) == 505
    for r in range(0, 256, 51):
        for g in range(0, 256, 51):
            for b in range(0, 256, 51):
                for hu in ("none", "tho", "nhap_nhay", True, False):
                    for sang in (0, 30, 100):
                        assert fw.id_day((r, g, b), hu, sang) in fw.ID_HOP_LE


async def test_khung_hieu_ung_dung_hop_dong_va_chan_id_la(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    server = e.runtime_data.mic_server
    await server.gui_hieu_ung(501)
    assert await _khung_xuong(reader) == b'{"type":"den_hieu_ung","id":501}'
    for ma in (0, 205, 999, 4096, -1, True, "501", 501.0, None):
        with pytest.raises(ValueError):
            await server.gui_hieu_ung(ma)
    assert await _doc_khung_hoac_none(reader, 0.4) is None   # không khung nào lọt xuống loa
    writer.close()


async def test_trang_thai_firmware_json_la_khong_lot_vao_tieng_apk_cu_khong_duoc_coi_la_san_sang(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    mic, server = e.runtime_data.mic, e.runtime_data.mic_server
    khuc: list[bytes] = []
    mic.add_chunk_listener(khuc.append)
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    assert server.den_san_sang is None and _st(hass, DICH_VU) == "unknown"
    await _bao(writer, True, che_do=None)                    # APK BẢN CŨ (đèn qua máy chủ shell): không báo che_do
    await cho(lambda: server.den_san_sang is False)
    await hass.async_block_till_done()
    assert _st(hass, DICH_VU) == "off"
    await _bao(writer, True)                                  # APK mới: đèn firmware sẵn sàng
    await cho(lambda: server.den_san_sang is True)
    await hass.async_block_till_done()
    assert _st(hass, DICH_VU) == "on"
    writer.write(khung_json({"type": "gi_do_la", "x": 1}))
    writer.write(khung(b"\x01\x00" * 160))
    await writer.drain()
    await cho(lambda: len(khuc) >= 1)
    assert khuc == [b"\x01\x00" * 160]                        # JSON lạ không bị coi là tiếng
    writer.close()
    await cho(lambda: server.den_san_sang is None)
    await hass.async_block_till_done()
    assert _st(hass, DICH_VU) == "unavailable"


async def test_sink_chi_san_sang_khi_loa_noi_va_apk_bao_firmware(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    sink = e.runtime_data.lights.sink
    assert isinstance(sink, ApkLights) and sink.firmware and not sink.available and sink.ly_do == "mat_ket_noi"
    assert sink.hieu_ung_ho_tro is None and sink.hieu_ung_goc == fw.HIEU_UNG_GOC
    reader, writer = await _noi_apk(e, port)
    assert not sink.available and sink.ly_do == "CHO_DICH_VU_DEN"
    await _bao(writer, True)
    await cho(lambda: sink.available)
    assert e.runtime_data.lights.sink_state == "san_sang"
    await _bo_khung(reader)                                   # khung áp lại đèn hiện tại lúc sẵn sàng
    await sink.ap_dung_ham(rim=True, color=(0, 255, 0), effect="none", sang=60)
    # Firmware chỉ giữ MỘT hiệu ứng: gửi thêm 503 sẽ đóng luôn hiệu ứng đáy (lỗi «đáy không sáng» 22/10/2026) → chỉ gửi đáy.
    assert await _lay_id(reader, 1) == [501]
    assert await _doc_khung_hoac_none(reader) is None         # KHÔNG có ID viền theo sau
    await sink.ap_dung_ham(rim=False, color=(0, 0, 255), effect="tho", sang=60)
    assert await _lay_id(reader, 1) == [203]                  # đáy xanh dương thở; không gửi 505 (sẽ đóng hiệu ứng đáy)
    assert await _doc_khung_hoac_none(reader) is None
    await sink.ap_dung_ham(rim=True, color=(0, 0, 0), effect="none", sang=60)
    assert await _lay_id(reader, 1) == [503]                  # đáy tắt, viền bật → chỉ viền
    await sink.tat()
    assert await _lay_id(reader, 2) == [504, 505]
    from custom_components.r1_speaker.den_port import Step
    await sink.play_effect([Step(base=(255, 0, 0), rim=0, seconds=0.2), Step(base=(0, 255, 0), rim=255, seconds=0.2)], repeat=False)
    # mỗi bước đúng một ID: đáy đỏ; rồi đáy xanh lá (đáy sáng thì ưu tiên đáy, viền bật cũng không gửi thêm)
    assert await _lay_id(reader, 2) == [500, 501]
    await sink.stop_effect()
    writer.close()
    await cho(lambda: not sink.available)
    with pytest.raises(LightsError):
        await sink.tat()


async def test_ap_dung_den_hien_tai_khi_apk_san_sang_va_tat_khi_do_sang_chung_bang_0(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    lights = e.runtime_data.lights
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": CAI_DAT, "function": "cho", "enabled": True, "rim": True,
        "color": "#00ff00", "effect": "none", "brightness": 100}, blocking=True)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, True)                                   # APK báo sẵn sàng → HA TỰ áp lại đèn hiện tại
    assert await _lay_id(reader, 1) == [501]                   # đáy xanh lá (viền cùng bật nhưng firmware chỉ giữ một hiệu ứng)
    await _goi(hass, "number", "set_value", DO_SANG, value=0)  # độ sáng chung 0 = tắt cả hai
    assert lights.master == 0
    assert await _lay_id(reader, 2) == [504, 505]
    await _goi(hass, "number", "set_value", DO_SANG, value=70)
    assert await _lay_id(reader, 1) == [501]                   # >0: bật lại (đèn firmware không chỉnh được mức sáng)
    writer.close()


async def test_hieu_ung_phan_mem_chay_bang_chuoi_id_firmware_va_hieu_ung_goc_dung_mot_id(hass, r1):
    """Cầu vồng/nhịp tim/pháo hoa/chớp chạy bằng cách đổi liên tiếp ID (như AI box gửi chuỗi ID); thở/nháy dùng ID gốc."""
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    await _bao(writer, True)
    await _bo_khung(reader)
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": CAI_DAT, "function": "cho", "enabled": True, "rim": False,
        "color": "#0000ff", "effect": "cau_vong", "brightness": 80}, blocking=True)
    thay: list[int] = []
    han = asyncio.get_running_loop().time() + 6
    while len(set(thay)) < 4 and asyncio.get_running_loop().time() < han:
        k = await _doc_khung_hoac_none(reader, 1.0)
        if k is not None:
            thay.append(json.loads(k)["id"])
    assert len(set(thay)) >= 4, thay                           # đổi qua nhiều màu khác nhau
    assert set(thay) <= fw.ID_HOP_LE                           # và mọi ID đều nằm trong danh sách cho phép
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": CAI_DAT, "function": "cho", "effect": "tho"}, blocking=True)   # hiệu ứng gốc: dừng chuỗi, một ID
    await _bo_khung(reader)
    await hass.services.async_call("r1_speaker", "set_light_function", {
        "entity_id": CAI_DAT, "function": "cho", "effect": "none"}, blocking=True)
    thay2 = []
    while (k := await _doc_khung_hoac_none(reader, 0.5)) is not None:
        thay2.append(json.loads(k)["id"])
    assert thay2 == [502]                                      # sáng cố định xanh dương (một ID), rồi YÊN (hết chuỗi)
    a = hass.states.get(CAI_DAT).attributes["anh_sang"]
    assert a["den_firmware"] is True and a["hieu_ung_ho_tro"] is None
    assert a["hieu_ung_goc"] == list(fw.HIEU_UNG_GOC)
    assert {m["ten_en"] for m in a["bang_mau_firmware"]} == set(fw.MAU)
    writer.close()


async def test_do_sang_chung_duoc_nho_va_chan_gia_tri_sai(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    lights = e.runtime_data.lights
    await _goi(hass, "number", "set_value", DO_SANG, value=25)
    assert lights.master == 25
    assert lights._du_lieu()["master"] == 25
    await _goi(hass, "number", "set_value", DO_SANG, value=100)
    assert "master" not in lights._du_lieu()
    from homeassistant.exceptions import ServiceValidationError
    for sai in (-1, 101, True, 12.5):
        with pytest.raises(ServiceValidationError):
            await lights.async_set_master(sai)
