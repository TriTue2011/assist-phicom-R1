"""Lưu tuỳ chọn khi APK đang nối: mục phải nạp lại được, không kẹt ở dỡ tải."""

import asyncio

from homeassistant.config_entries import ConfigEntryState

from .test_den_nhac import _cong_trong, _noi_apk
from .test_mic_server import KHOA


async def test_luu_tuy_chon_khi_apk_dang_noi_thi_nap_lai_duoc(hass, r1):
    from custom_components.r1_speaker.const import DOMAIN
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    port = _cong_trong()
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port, "mic_listen_key": KHOA,
                                             "mic_listen_port": port}, unique_id="127.0.0.1:tl")
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    reader, writer = await _noi_apk(e, port)
    hass.config_entries.async_update_entry(
        e, options={"agc_enable": True, "agc_max_gain_db": 18.0, "limiter_enable": True})
    await asyncio.wait_for(hass.async_block_till_done(), 20)
    assert e.state is ConfigEntryState.LOADED
    writer.close()


async def test_nap_lai_khong_ket_khi_pipeline_ha_khong_tra_lai(hass, r1):
    """Lỗi thật 23/10: pipeline HA (dò từ đánh thức) nuốt lệnh huỷ → ``async_will_remove_from_hass`` chờ mãi → mục kẹt
    ở «đã dỡ tải», phải khởi động lại HA. Nay luồng tiếng được đóng trước và chờ có hạn."""
    from unittest import mock
    from custom_components.r1_speaker import assist_satellite as sat_mod
    from custom_components.r1_speaker.const import DOMAIN
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    dang_chay = asyncio.Event()

    async def treo(self, audio_stream, start_stage=None, **kw):
        dang_chay.set()
        try:
            async for _ in audio_stream:
                pass
            await asyncio.sleep(3600)          # luồng đã hết mà pipeline vẫn không trả lại
        except asyncio.CancelledError:
            await asyncio.sleep(3600)          # nuốt lệnh huỷ

    port = _cong_trong()
    e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port, "mic_listen_key": KHOA,
                                             "mic_listen_port": port}, unique_id="127.0.0.1:tk")
    e.add_to_hass(hass)
    with mock.patch("homeassistant.components.assist_satellite.entity.AssistSatelliteEntity."
                    "async_accept_pipeline_from_satellite", new=treo), \
            mock.patch.object(sat_mod, "DUNG_TOI_DA", 0.5), \
            mock.patch.object(sat_mod.R1Satellite, "_thieu_tu_danh_thuc", return_value=None):
        assert await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
        reader, writer = await _noi_apk(e, port)
        await asyncio.wait_for(dang_chay.wait(), 5)
        await asyncio.wait_for(hass.config_entries.async_reload(e.entry_id), 10)
        assert e.state is ConfigEntryState.LOADED
        writer.close()
