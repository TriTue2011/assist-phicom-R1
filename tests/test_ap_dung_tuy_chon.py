"""Đổi cài đặt ở thực thể phải áp TẠI CHỖ lên mic / bộ đàm / song công đang chạy (không cần tải lại tích hợp).

Lớp lỗi (đo 10/11/2026 trên loa thật): thực thể chỉ ghi entry.options, còn đối tượng đang chạy giữ bản chụp cài đặt
lúc khởi động — đặt «Động cơ xử lý âm thanh» = nang_cao mà phiên song công vẫn chạy bộ khử vọng nlms."""

from custom_components.r1_speaker import const
from custom_components.r1_speaker.khu_vong_fdaf import KhuVongFdaf
from custom_components.r1_speaker.song_cong import KhuVong
from custom_components.r1_speaker.thuc_the_tuy_chon import luu_tuy_chon

from .test_bo_dam import _them
from .test_nv302_the_cai_dat import _eid, _goi


async def test_doi_dong_co_thanh_nang_cao_ap_ngay_cho_phien_song_cong_moi(hass, r1):
    e = await _them(hass, r1)
    c = e.runtime_data
    assert c.duplex.settings.engine == "noi_bo" and isinstance(c.duplex._tao_khu_vong(), KhuVong)
    assert c.mic.noise.engine == "noi_bo"
    await _goi(hass, "select", "select_option", entity_id=_eid(hass, "select", "dsp_dong_co"), option="nang_cao")
    await hass.async_block_till_done()
    assert c.duplex.settings.engine == "nang_cao"
    assert isinstance(c.duplex._tao_khu_vong(), KhuVongFdaf)           # phiên mở SAU đó dùng FDAF
    assert c.mic.noise.engine == "nang_cao"
    # đổi lại về mặc định cũng áp tại chỗ
    await _goi(hass, "select", "select_option", entity_id=_eid(hass, "select", "dsp_dong_co"), option="noi_bo")
    await hass.async_block_till_done()
    assert c.duplex.settings.engine == "noi_bo" and isinstance(c.duplex._tao_khu_vong(), KhuVong)


async def test_cong_tac_khu_on_va_khu_vong_ap_ngay(hass, r1):
    e = await _them(hass, r1)
    c = e.runtime_data
    assert c.mic.noise.enabled is False and c.duplex.settings.aec is True
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "khu_on"))
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "khu_vong"))
    await hass.async_block_till_done()
    assert c.mic.noise.enabled is True
    assert c.duplex.settings.aec is False and c.duplex._tao_khu_vong() is None


async def test_bo_dam_nhan_cai_dat_moi_ca_o_cong_thoai(hass, r1):
    e = await _them(hass, r1)
    c = e.runtime_data
    luu_tuy_chon(hass, e, const.CONF_TALK_THRESHOLD_DB, -30.0, const.DEFAULT_TALK_THRESHOLD_DB)   # đường các thực thể ghi
    await hass.async_block_till_done()
    assert c.intercom.settings.threshold_db == -30.0
    assert c.intercom._gate.s is c.intercom.settings                    # cổng VOX dùng cùng cài đặt, không giữ bản cũ
