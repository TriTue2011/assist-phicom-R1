"""Lệnh cài APK đã kèm khoá: chỉ quản trị viên xem được (không nằm trong trạng thái thực thể)."""

from .test_den_nhac import _them_co_dau_nhan
from .test_tuy_chon import _them

THUC_THE = "sensor.r1_trang_thai_mic"


async def test_quan_tri_nhan_lenh_co_khoa_va_cong_dung(hass, r1, hass_ws_client):
    e = await _them(hass, r1)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "r1_speaker/apk_lenh", "entity_id": THUC_THE})
    r = await ws.receive_json()
    assert r["success"], r
    lenh = r["result"]["lenh"]
    assert f"--es khoa {e.data['mic_listen_key']}" in lenh
    assert f"--ei port {e.data['mic_listen_port']}" in lenh
    assert lenh.endswith("--ez bat true")                    # lần đầu chỉ LƯU cấu hình; «bat» mới bật mic
    assert "--es host " in lenh and "vn.r1.bodam/.ManHinhChinh" in lenh and "/system/bin/am" in lenh


async def test_khong_phai_quan_tri_bi_tu_choi(hass, r1, hass_ws_client, hass_admin_user):
    await _them(hass, r1)
    hass_admin_user.groups = []                       # hạ xuống người dùng thường
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "r1_speaker/apk_lenh", "entity_id": THUC_THE})
    r = await ws.receive_json()
    assert not r["success"] and r["error"]["code"] == "unauthorized"


async def test_thuc_the_la_hoac_chua_co_khoa_bao_loi(hass, r1, hass_ws_client):
    await _them(hass, r1)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "r1_speaker/apk_lenh", "entity_id": "sensor.khong_co"})
    r = await ws.receive_json()
    assert not r["success"] and r["error"]["code"] == "not_found"


async def test_khoa_khong_lo_ra_trang_thai_thuc_the(hass, r1):
    e = await _them(hass, r1)
    khoa = e.data["mic_listen_key"]
    for st in hass.states.async_all():
        if st.entity_id.split(".")[1].startswith("r1"):
            assert khoa not in str(st.attributes), st.entity_id
