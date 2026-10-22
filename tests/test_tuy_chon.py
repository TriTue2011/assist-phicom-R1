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
    assert khoa == {"host", "port", "mic_host", "mic_port", "mic_listen_port", "mic_listen_key",
                    "play_host", "play_port",
                    "talk_threshold_db", "talk_silence_s", "talk_preroll_s", "talk_tail_s",
                    "rotate_intercom_key", "wake_mode", "ha_url",
                    # chín khoá DSP mic (khử tạp, AGC, hạn đỉnh), thêm sau
                    "noise_suppress", "noise_strength_db", "noise_voice_db", "agc_enable",
                    "agc_target_db", "agc_max_gain_db", "agc_silence_db", "limiter_enable",
                    "limiter_ceiling",
                    # ba khoá từ đánh thức (cài đặt; chưa có dịch vụ đánh thức trên loa)
                    "wake_enable", "wake_word", "wake_sensitivity",
                    # sáu khoá đàm thoại song công NV246 (VAD, đệm, hạn phiên, cắt vọng)
                    "duplex_vad_threshold", "duplex_preroll_s", "duplex_hangover_s",
                    "duplex_max_s", "duplex_duck", "duplex_duck_db"}
    # giá trị gợi ý = hiện hành
    macdinh = {str(k): k.default() for k in res["data_schema"].schema
               if k.default is not vol.UNDEFINED}
    assert macdinh["host"] == "127.0.0.1" and macdinh["port"] == r1.port


async def test_luu_chi_giu_gia_tri_khac_goc_va_ap_ngay(hass, r1):
    e = await _them(hass, r1)
    _, res = await _luu(hass, e, host="127.0.0.1", port=r1.port, mic_port=const.DEFAULT_MIC_PORT,
                        play_host=" 127.0.0.1 ", play_port=9, talk_threshold_db=-38.5,
                        talk_silence_s=0.8, talk_preroll_s=0.3, talk_tail_s=0.5)
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


async def test_doi_host_cong_dieu_khien_kiem_lai_bang_get_info(hass, r1):
    e = await _them(hass, r1)
    r2 = FakeR1()
    await r2.start()
    try:
        _, res = await _luu(hass, e, host="127.0.0.1", port=r2.port, mic_port=const.DEFAULT_MIC_PORT,
                            play_port=0, talk_threshold_db=-45.0, talk_silence_s=1.5,
                            talk_preroll_s=0.3, talk_tail_s=0.5)
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
    _, res = await _luu(hass, e, host="127.0.0.1", port=cong, mic_port=const.DEFAULT_MIC_PORT,
                        play_port=0, talk_threshold_db=-45.0, talk_silence_s=1.5,
                        talk_preroll_s=0.3, talk_tail_s=0.5)
    assert res["type"] is FlowResultType.FORM and res["errors"] == {"base": "cannot_connect"}
    assert e.options == {}
    _, res = await _luu(hass, e, host="  ", port=r1.port, mic_port=const.DEFAULT_MIC_PORT,
                        play_port=0, talk_threshold_db=-45.0, talk_silence_s=1.5,
                        talk_preroll_s=0.3, talk_tail_s=0.5)
    assert res["errors"] == {"host": "invalid_host"} and e.options == {}


@pytest.mark.parametrize("truong,gia_tri", [
    ("talk_threshold_db", 0.0), ("talk_threshold_db", -120.0), ("talk_silence_s", 0.0),
    ("talk_silence_s", 60.0), ("talk_preroll_s", -1.0), ("talk_tail_s", 99.0),
    ("port", 0), ("port", 70000), ("play_port", 70000), ("mic_port", 0)])
async def test_gia_tri_ngoai_dai_bi_tu_choi_o_bieu_mau(hass, r1, truong, gia_tri):
    e = await _them(hass, r1)
    ok = dict(host="127.0.0.1", port=r1.port, mic_port=const.DEFAULT_MIC_PORT, play_port=0,
              talk_threshold_db=-45.0, talk_silence_s=1.5, talk_preroll_s=0.3, talk_tail_s=0.5)
    res = await hass.config_entries.options.async_init(e.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(res["flow_id"], {**ok, truong: gia_tri})


async def test_doi_khoa_bo_dam(hass, r1):
    e = await _them(hass, r1)
    cu = e.data[CONF_INTERCOM_KEY]
    _, res = await _luu(hass, e, host="127.0.0.1", port=r1.port, mic_port=const.DEFAULT_MIC_PORT,
                        play_port=0, talk_threshold_db=-45.0, talk_silence_s=1.5,
                        talk_preroll_s=0.3, talk_tail_s=0.5, rotate_intercom_key=True)
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
