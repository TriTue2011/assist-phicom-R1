"""Đèn theo nhạc của firmware, công tắc «Đàm thoại», «Chế độ đàm thoại» và cảm biến «Bộ đàm».

APK loa giả: kết nối TCP thật vào đầu nhận mic của tích hợp (hello đúng khoá), rồi đọc các khung điều
khiển HA gửi xuống. Định dạng khung là hợp đồng với ``LenhDieuKhien.java`` trên loa (khoá đúng thứ tự,
dạng tách gọn): đổi một byte là APK từ chối.
"""

import asyncio
import socket

import pytest
from homeassistant.exceptions import HomeAssistantError

from .test_mic_server import KHOA, cho, hello
from .test_song_cong import _them

LUMA, CHROMA, DEN = "number.r1_do_sang_den_nhac", "number.r1_sac_do_den_nhac", "switch.r1_den_nhac"
DAM_THOAI, BO_DAM = "switch.r1_dam_thoai", "binary_sensor.r1_bo_dam"
SONG_SONG = "switch.r1_mic_loa_song_song"


def _cong_trong() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _them_co_dau_nhan(hass, r1):
    port = _cong_trong()
    return await _them(hass, r1, mic_host="127.0.0.1", mic_port=9, mic_listen_port=port,
                       mic_listen_key=KHOA), port


async def _noi_apk(e, port):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(hello())
    await writer.drain()
    await cho(lambda: e.runtime_data.mic_server.receiving)
    return reader, writer


async def _khung_xuong(reader) -> bytes:
    do_dai = int.from_bytes(await asyncio.wait_for(reader.readexactly(4), 3), "big")
    return await asyncio.wait_for(reader.readexactly(do_dai), 3)


def _st(hass, eid) -> str:
    return hass.states.get(eid).state


async def _goi(hass, domain, service, eid, **data):
    await hass.services.async_call(domain, service, {"entity_id": eid, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_den_nhac_chi_dung_duoc_khi_apk_noi_va_gui_dung_khung(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    for eid in (LUMA, CHROMA, DEN):                      # chưa có APK: không điều khiển được
        assert _st(hass, eid) == "unavailable", eid
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    assert (_st(hass, LUMA), _st(hass, CHROMA), _st(hass, DEN)) == ("50", "60", "on")  # đọc từ get_info
    await _goi(hass, "number", "set_value", LUMA, value=70)
    assert await _khung_xuong(reader) == b'{"type":"den_nhac","ma":65,"gia_tri":70}'
    assert _st(hass, LUMA) == "70"
    await _goi(hass, "number", "set_value", CHROMA, value=8)
    assert await _khung_xuong(reader) == b'{"type":"den_nhac","ma":66,"gia_tri":8}'
    await _goi(hass, "switch", "turn_off", DEN)
    assert await _khung_xuong(reader) == b'{"type":"den_nhac","ma":64,"gia_tri":0}'
    assert _st(hass, DEN) == "off"
    await _goi(hass, "switch", "turn_on", DEN)
    assert await _khung_xuong(reader) == b'{"type":"den_nhac","ma":64,"gia_tri":1}'
    assert _st(hass, DEN) == "on"
    writer.close()                                       # APK đứt: lại không điều khiển được
    await cho(lambda: not e.runtime_data.mic_server.receiving)
    await hass.async_block_till_done()
    assert _st(hass, LUMA) == "unavailable" and _st(hass, DEN) == "unavailable"


async def test_den_nhac_ngoai_khoang_bi_chan_truoc_khi_gui(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    server = e.runtime_data.mic_server
    for ma, gia_tri in ((65, 101), (65, -1), (66, 0), (64, 2), (99, 1)):
        with pytest.raises(ValueError):
            await server.set_music_light(ma, gia_tri)
    with pytest.raises(ValueError):                      # bool không phải số đo
        await server.set_music_light(64, True)
    with pytest.raises(HomeAssistantError):              # HA chặn giá trị ngoài khoảng của thanh trượt
        await hass.services.async_call("number", "set_value", {"entity_id": LUMA, "value": 150},
                                       blocking=True)
    with pytest.raises(asyncio.TimeoutError):            # không khung nào lọt xuống loa
        await asyncio.wait_for(reader.readexactly(4), 0.3)
    writer.close()


async def test_den_nhac_bao_loi_ro_khi_mat_ket_noi_giua_chung(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    reader, writer = await _noi_apk(e, port)
    server = e.runtime_data.mic_server
    writer.close()
    await cho(lambda: not server.receiving)
    with pytest.raises(ConnectionError):
        await server.set_music_light(65, 50)


async def test_bo_dam_theo_ket_noi_apk(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    assert _st(hass, BO_DAM) == "unavailable"            # chưa có kênh phát
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    assert _st(hass, BO_DAM) != "unavailable"            # APK nối → có kênh phát (trước đây đứng yên)
    writer.close()
    await cho(lambda: not e.runtime_data.mic_server.receiving)
    await hass.async_block_till_done()
    assert _st(hass, BO_DAM) == "unavailable"


async def test_mic_loa_song_song_bat_la_song_cong_tat_la_nua_cong_va_khong_lien_quan_cach_mo_mic(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    assert _st(hass, SONG_SONG) == "on" and not d.half_duplex                  # mặc định: song song
    reader, writer = await _noi_apk(e, port)
    for che_do, nua_cong in (("off", True), ("on", False)):                  # nửa công rồi song song
        await _goi(hass, "switch", "turn_on" if che_do == "on" else "turn_off", SONG_SONG)
        assert d.half_duplex is nua_cong and _st(hass, SONG_SONG) == che_do
        await _goi(hass, "switch", "turn_on", DAM_THOAI)             # «Bật mic luôn» chạy ở CẢ hai chế độ
        assert d.active and hass.states.get(DAM_THOAI).attributes["giu_mo"] is True
        assert d.half_duplex is nua_cong                              # mở mic không đổi chế độ
        await _goi(hass, "switch", "turn_off", DAM_THOAI)
        assert not d.active and d.half_duplex is nua_cong             # đóng mic cũng không đổi chế độ
    writer.close()


async def test_cong_tac_dam_thoai_mo_giu_mo_va_giu_de_noi_khong_giu_mo(hass, r1):
    e, port = await _them_co_dau_nhan(hass, r1)
    d = e.runtime_data.duplex
    reader, writer = await _noi_apk(e, port)
    await hass.async_block_till_done()
    assert _st(hass, DAM_THOAI) == "off"
    await _goi(hass, "switch", "turn_on", DAM_THOAI)             # «Bật mic luôn»
    st = hass.states.get(DAM_THOAI)
    assert st.state == "on" and st.attributes["giu_mo"] is True and d.active
    await _goi(hass, "switch", "turn_off", DAM_THOAI)
    st = hass.states.get(DAM_THOAI)
    assert st.state == "off" and st.attributes["giu_mo"] is False and not d.active
    # «Giữ để nói»: dịch vụ start/stop; đang giữ thì công tắc bật nhưng KHÔNG đặt giu_mo.
    await hass.services.async_call("r1_speaker", "start_duplex", {"entity_id": DAM_THOAI}, blocking=True)
    await hass.async_block_till_done()
    st = hass.states.get(DAM_THOAI)
    assert st.state == "on" and st.attributes["giu_mo"] is False
    await _goi(hass, "switch", "turn_on", DAM_THOAI)             # bấm «Bật mic luôn» khi đang giữ → giữ mở
    assert hass.states.get(DAM_THOAI).attributes["giu_mo"] is True and d.active
    await hass.services.async_call("r1_speaker", "stop_duplex", {"entity_id": DAM_THOAI}, blocking=True)
    await hass.async_block_till_done()
    assert _st(hass, DAM_THOAI) == "off" and not d.luon
    writer.close()


async def test_thuc_the_cu_da_bo_khoi_so_dang_ky(hass, r1):
    """Nút Đàm thoại/Kết thúc, «Bật mic luôn», hai công tắc chế độ cũ, ô chọn gộp, hai cảm biến đèn nhạc: dọn khỏi sổ đăng ký."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.r1_speaker.const import DOMAIN
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        unique_id=f"127.0.0.1:{r1.port}")
    e.add_to_hass(hass)
    reg = er.async_get(hass)
    cu = [("button", "talk"), ("button", "end_talk"), ("switch", "always_on"),
          ("switch", "half_duplex"), ("switch", "duplex_enable"), ("select", "intercom_mode"),
          ("sensor", "music_light_luma"), ("sensor", "music_light_chroma")]
    for domain, key in cu:                                # bản cũ để lại các dòng này
        reg.async_get_or_create(domain, DOMAIN, f"{e.entry_id}_{key}", config_entry=e)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    for domain, key in cu:
        assert reg.async_get_entity_id(domain, DOMAIN, f"{e.entry_id}_{key}") is None, (domain, key)


async def test_co_khoa_dau_nhan_thi_khong_chay_vong_noi_ra_cong_cu(hass, r1):
    """Đường mic mới là APK nối VÀO HA: không được còn thử nối ra cổng cũ của loa (cảnh báo 8765)."""
    e, port = await _them_co_dau_nhan(hass, r1)             # mic_port=9: cổng đóng, nối ra sẽ bị từ chối
    await asyncio.sleep(0.4)
    assert not e.runtime_data.mic._warned                    # chưa từng thử nối ra
    reader, writer = await _noi_apk(e, port)                 # đường vào vẫn chạy
    assert e.runtime_data.mic.connected
    writer.close()
