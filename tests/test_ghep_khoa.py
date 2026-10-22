"""Ghép khoá nghe mic tự động: APK xin khoá, HA trao đúng MỘT lần cho đúng IP loa."""

from .test_tuy_chon import _them

URL = "/api/r1_speaker/ghep"


async def test_apk_xin_khoa_nhan_dung_mot_lan(hass, r1, hass_client_no_auth):
    e = await _them(hass, r1)                                  # IP loa 127.0.0.1 = địa chỉ nguồn của client test
    assert e.data["mic_chua_ghep"] is True                     # khoá HA tự sinh: cửa ghép mở
    client = await hass_client_no_auth()
    r = await client.post(URL)
    assert r.status == 200
    j = await r.json()
    assert j == {"port": e.data["mic_listen_port"], "key": e.data["mic_listen_key"]}
    assert e.data["mic_chua_ghep"] is False                    # đã trao: đóng cửa
    r2 = await client.post(URL)
    assert r2.status == 409 and "key" not in (await r2.json())  # lần hai: KHÔNG trao nữa


async def test_ip_la_khong_nhan_khoa(hass, r1, hass_client_no_auth):
    e = await _them(hass, r1)
    hass.config_entries.async_update_entry(e, data={**e.data, "host": "192.0.2.77"})   # loa ở IP khác
    r = await (await hass_client_no_auth()).post(URL)
    assert r.status == 404 and e.data["mic_chua_ghep"] is True    # khoá vẫn chưa bị trao


async def test_khoa_nguoi_dung_tu_dat_khong_co_cua_ghep(hass, r1, hass_client_no_auth):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.r1_speaker.const import DOMAIN
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options={"mic_listen_key": "khoa-tay", "mic_listen_port": 18999}, unique_id="127.0.0.1:t")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert "mic_chua_ghep" not in e.data
    r = await (await hass_client_no_auth()).post(URL)
    assert r.status == 409                                     # không bao giờ lộ khoá người dùng tự đặt


async def test_ghep_lai_sinh_khoa_moi_va_mo_lai_cua(hass, r1, hass_client_no_auth):
    e = await _them(hass, r1)
    client = await hass_client_no_auth()
    j1 = await (await client.post(URL)).json()
    res = await hass.config_entries.options.async_init(e.entry_id)
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port, "ghep_lai_apk": True})
    assert res["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert e.data["mic_chua_ghep"] is True and e.data["mic_listen_key"] != j1["key"]
    j2 = await (await client.post(URL)).json()
    assert j2["key"] == e.data["mic_listen_key"] != j1["key"]


async def test_apk_xac_thuc_dung_khoa_thi_cua_ghep_dong(hass, r1, hass_client_no_auth):
    """APK đã có khoá (cấp tay hoặc ghép xong): cửa ghép không được mở mãi cho app khác trên loa."""
    import asyncio
    from .test_den_nhac import _noi_apk
    from .test_mic_server import KHOA
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.r1_speaker.const import DOMAIN
    from .test_den_nhac import _cong_trong
    port = _cong_trong()
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port, "mic_listen_key": KHOA,
                                             "mic_listen_port": port, "mic_chua_ghep": True}, unique_id="127.0.0.1:g")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert e.data["mic_chua_ghep"] is True
    reader, writer = await _noi_apk(e, port)                  # hello đúng khoá
    assert e.data["mic_chua_ghep"] is False
    r = await (await hass_client_no_auth()).post(URL)
    assert r.status == 409
    writer.close()


async def test_apk_mat_khoa_thi_cua_ghep_tu_mo_lai_va_tu_lay_duoc(hass, r1, hass_client_no_auth):
    """Xoá/thêm lại tích hợp hoặc cài lại APK: APK gửi khoá cũ → HA tự mở lại cửa ghép, APK xin được khoá mà không ai
    bấm gì. Khoá người dùng tự đặt thì KHÔNG bao giờ mở."""
    from .test_den_nhac import _cong_trong
    from .test_mic_server import cho, khung_json
    import asyncio
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.r1_speaker.const import DOMAIN
    port = _cong_trong()
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port, "mic_listen_key": "khoa-moi-cua-ha",
                                             "mic_listen_port": port, "mic_chua_ghep": False}, unique_id="127.0.0.1:m")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    assert (await client.post(URL)).status == 409                       # đã ghép: cửa đóng
    reader, writer = await asyncio.open_connection("127.0.0.1", port)   # APK mất khoá: gửi khoá cũ
    writer.write(khung_json({"type": "hello", "version": 1, "key": "khoa-cu-da-mat"}))
    await writer.drain()
    await cho(lambda: e.data["mic_chua_ghep"] is True)                  # cửa tự mở lại
    j = await (await client.post(URL)).json()
    assert j == {"port": port, "key": "khoa-moi-cua-ha"}                # và APK lấy được, đúng một lần
    assert (await client.post(URL)).status == 409
    writer.close()


async def test_khoa_tu_dat_bi_gui_sai_van_khong_mo_cua(hass, r1, hass_client_no_auth):
    from .test_den_nhac import _cong_trong
    from .test_mic_server import cho, khung_json
    import asyncio
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.r1_speaker.const import DOMAIN
    port = _cong_trong()
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options={"mic_listen_key": "khoa-tay", "mic_listen_port": port}, unique_id="127.0.0.1:n")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(khung_json({"type": "hello", "version": 1, "key": "sai"}))
    await writer.drain()
    await asyncio.sleep(0.4)
    assert "mic_chua_ghep" not in e.data
    assert (await (await hass_client_no_auth()).post(URL)).status == 409
    writer.close()
