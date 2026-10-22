"""Cấu hình qua giao diện tích hợp (config flow + options flow), như tích hợp camera: host, cổng
EQ, mic, kênh phát về loa, bốn tham số cổng thoại, khoá bộ đàm. Không số nào mã cứng ở nơi dùng."""

from unittest import mock

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.r1_speaker import const
from custom_components.r1_speaker.const import CONF_INTERCOM_KEY, DOMAIN
from custom_components.r1_speaker.settings import TalkSettings, play_address

from .conftest import FakeR1
from .test_bo_dam import _them


@pytest.fixture(autouse=True)
def _nhanh():
    with mock.patch("custom_components.r1_speaker.client.RESPONSE_TIMEOUT", 0.5):
        yield


async def _luu(hass, e, **tuy_chon):
    res = await hass.config_entries.options.async_init(e.entry_id)
    assert res["type"] is FlowResultType.FORM and res["step_id"] == "init"
    return res, await hass.config_entries.options.async_configure(res["flow_id"], tuy_chon)


#: Mọi số của bước nâng cao ở giá trị gốc (form bắt buộc đủ trường).
_NANG_CAO_GOC = dict(
    talk_threshold_db=-45.0, talk_silence_s=1.5, talk_preroll_s=0.3, talk_tail_s=0.5,
    noise_suppress=False, noise_strength_db=const.DEFAULT_NOISE_STRENGTH_DB,
    noise_voice_db=const.DEFAULT_NOISE_VOICE_DB, agc_enable=False,
    agc_target_db=const.DEFAULT_AGC_TARGET_DB, agc_max_gain_db=const.DEFAULT_AGC_MAX_GAIN_DB,
    agc_silence_db=const.DEFAULT_AGC_SILENCE_DB, limiter_enable=False,
    limiter_ceiling=const.DEFAULT_LIMITER_CEILING,
    duplex_vad_threshold=const.DEFAULT_DUPLEX_VAD_THRESHOLD,
    duplex_preroll_s=const.DEFAULT_DUPLEX_PREROLL, duplex_hangover_s=const.DEFAULT_DUPLEX_HANGOVER,
    duplex_max_s=const.DEFAULT_DUPLEX_MAX_S, duplex_duck=const.DEFAULT_DUPLEX_DUCK,
    duplex_duck_db=const.DEFAULT_DUPLEX_DUCK_DB)


def test_mac_dinh_cong_dieu_khien_la_8080_da_do():
    assert const.DEFAULT_PORT == 8080
    assert const.DEFAULT_PLAY_PORT == 0          # chưa có số đo → không đoán cổng phát
    # mặc định cổng thoại mượn từ bộ đàm camera, CHƯA đo trên loa R1 (ghi rõ trong const)
    assert (const.DEFAULT_TALK_THRESHOLD_DB, const.DEFAULT_TALK_SILENCE,
            const.DEFAULT_TALK_PREROLL) == (-45.0, 1.5, 0.3)


async def test_form_co_du_truong(hass, r1):
    e = await _them(hass, r1)
    res = await hass.config_entries.options.async_init(e.entry_id)
    khoa = {str(k) for k in res["data_schema"].schema}
    # Form chính chỉ còn thứ người dùng biết; khoá/cổng nghe mic tự cấp, mục chết đã gỡ khỏi form.
    assert khoa == {"host", "port", "ha_url", "rotate_intercom_key", "ghep_lai_apk", "nang_cao"}
    macdinh = {str(k): k.default() for k in res["data_schema"].schema
               if k.default is not vol.UNDEFINED}
    assert macdinh["host"] == "127.0.0.1" and macdinh["port"] == r1.port
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port, "nang_cao": True})
    assert res["type"] is FlowResultType.FORM and res["step_id"] == "nang_cao"
    assert {str(k) for k in res["data_schema"].schema} == {
        "talk_threshold_db", "talk_silence_s", "talk_preroll_s", "talk_tail_s",
        "noise_suppress", "noise_strength_db", "noise_voice_db", "agc_enable",
        "agc_target_db", "agc_max_gain_db", "agc_silence_db", "limiter_enable", "limiter_ceiling",
        "duplex_vad_threshold", "duplex_preroll_s", "duplex_hangover_s",
        "duplex_max_s", "duplex_duck", "duplex_duck_db"}


async def test_luu_chi_giu_gia_tri_khac_goc_va_ap_ngay(hass, r1):
    e = await _them(hass, r1)
    # Khoá ẩn (không còn trên form) đã có sẵn trong options phải SỐNG SÓT sau khi lưu form.
    hass.config_entries.async_update_entry(e, options={"play_host": "127.0.0.1", "play_port": 9})
    res = await hass.config_entries.options.async_init(e.entry_id)
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port, "nang_cao": True})
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], _NANG_CAO_GOC | {"talk_threshold_db": -38.5, "talk_silence_s": 0.8})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    # host/cổng điều khiển bằng lúc thêm, các số bằng mặc định → KHÔNG lưu (mặc định đổi sau khi
    # đo thì mục chưa chỉnh tay tự theo)
    assert e.options == {"play_host": "127.0.0.1", "play_port": 9, "talk_threshold_db": -38.5,
                         "talk_silence_s": 0.8}
    await hass.async_block_till_done()                      # OptionsFlowWithReload nạp lại
    c = e.runtime_data
    assert c.intercom.settings == TalkSettings(-38.5, 0.8, 0.3, 0.5)
    assert (c.playback.host, c.playback.port) == ("127.0.0.1", 9)
    assert play_address(e) == ("127.0.0.1", 9)


async def test_luu_form_chinh_khong_dat_lai_so_nang_cao_da_chinh(hass, r1):
    e = await _them(hass, r1)
    hass.config_entries.async_update_entry(e, options={"talk_silence_s": 0.8, "noise_suppress": True})
    _, res = await _luu(hass, e, host="127.0.0.1", port=r1.port)      # không mở bước nâng cao
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert e.options == {"talk_silence_s": 0.8, "noise_suppress": True}


async def test_doi_host_cong_dieu_khien_kiem_lai_bang_get_info(hass, r1):
    e = await _them(hass, r1)
    r2 = FakeR1()
    await r2.start()
    try:
        _, res = await _luu(hass, e, host="127.0.0.1", port=r2.port)
        assert res["type"] is FlowResultType.CREATE_ENTRY and e.options == {"port": r2.port}
        await hass.async_block_till_done()
        assert e.runtime_data.client.port == r2.port         # client dùng cổng mới
        assert r2.commands("get_info")                        # đã kiểm bằng loa mới
    finally:
        await r2.stop()


async def test_cong_sai_bao_loi_khong_luu(hass, r1):
    e = await _them(hass, r1)
    dong = FakeR1()
    await dong.start()
    cong = dong.port
    await dong.stop()
    _, res = await _luu(hass, e, host="127.0.0.1", port=cong)
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"base": "cannot_connect"}
    assert e.options == {}
    _, res = await _luu(hass, e, host="  ", port=r1.port)
    assert res["errors"] == {"host": "invalid_host"} and e.options == {}


async def test_doi_khoa_bo_dam(hass, r1):
    e = await _them(hass, r1)
    cu = e.data[CONF_INTERCOM_KEY]
    _, res = await _luu(hass, e, host="127.0.0.1", port=r1.port, rotate_intercom_key=True)
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert e.data[CONF_INTERCOM_KEY] != cu and len(e.data[CONF_INTERCOM_KEY]) >= 24
    assert "rotate_intercom_key" not in e.options        # cờ một lần, không lưu


async def test_config_flow_them_loa_mac_dinh_8080(hass, r1):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    mac = {str(k): k.default() for k in res["data_schema"].schema}
    assert mac["port"] == 8080
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert res["data"] == {"host": "127.0.0.1", "port": r1.port}


# ── Tự cấp khoá + cổng nghe mic, nhiều loa ────────────────────────────────────────────



async def test_tu_cap_khoa_va_cong_nghe_mic_khong_can_nhap(hass, r1):
    e = await _them(hass, r1)
    khoa, cong = e.data["mic_listen_key"], e.data["mic_listen_port"]
    assert len(khoa) >= 24 and cong == const.DEFAULT_MIC_LISTEN_PORT
    assert e.runtime_data.mic_server.port in (cong, 0) or e.runtime_data.mic_server.receiving is False
    assert e.options == {}                                    # tự cấp nằm ở data, không đụng options
    await hass.config_entries.async_reload(e.entry_id)        # khởi động lại HA: khoá và cổng GIỮ NGUYÊN
    assert (e.data["mic_listen_key"], e.data["mic_listen_port"]) == (khoa, cong)


async def test_khoa_nghe_mic_da_dat_tay_thi_khong_bi_ghi_de(hass, r1):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port},
                        options={"mic_listen_key": "khoa-cu", "mic_listen_port": 18999},
                        unique_id="127.0.0.1:x")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert "mic_listen_key" not in e.data and "mic_listen_port" not in e.data


async def test_nhieu_loa_moi_loa_mot_cong_va_mot_khoa(hass, r1):
    from .conftest import FakeR1
    e1 = await _them(hass, r1)
    r2 = FakeR1()
    await r2.start()
    try:
        from pytest_homeassistant_custom_component.common import MockConfigEntry
        e2 = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r2.port},
                             unique_id=f"127.0.0.1:{r2.port}")
        e2.add_to_hass(hass)
        assert await hass.config_entries.async_setup(e2.entry_id)
        await hass.async_block_till_done()
        assert e1.data["mic_listen_port"] != e2.data["mic_listen_port"]
        assert e2.data["mic_listen_port"] == const.DEFAULT_MIC_LISTEN_PORT + 1
        assert e1.data["mic_listen_key"] != e2.data["mic_listen_key"]
        assert e1.runtime_data is not e2.runtime_data
        assert e1.runtime_data.mic_server is not e2.runtime_data.mic_server
    finally:
        await r2.stop()
