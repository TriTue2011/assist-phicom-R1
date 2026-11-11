"""Nút giữa → trigger thiết bị chọn bằng giao diện + bốn nút ảo mô phỏng cử chỉ (để gán vào tự động hoá cho dễ)."""

import pytest
from homeassistant.core import callback
from homeassistant.components.device_automation import async_get_device_automations, DeviceAutomationType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.r1_speaker import phim as P
from custom_components.r1_speaker.const import DOMAIN, SU_KIEN_PHIM

from .test_phim import _lien_ket


def _device(hass, e):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, e.entry_id)})


async def test_moi_cu_chi_la_mot_trigger_thiet_bi_va_thiet_bi_khac_khong_co(hass, r1):
    e, *_ = await _lien_ket(hass, r1)
    dev = _device(hass, e)
    trig = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, [dev.id])
    cua_r1 = [t for t in trig[dev.id] if t["domain"] == DOMAIN]          # thực thể khác của thiết bị còn có trigger riêng của nền tảng chúng
    assert {t["type"] for t in cua_r1} == set(P.CU_CHI_SU_KIEN) and len(cua_r1) == len(P.CU_CHI_SU_KIEN)
    assert all(t["device_id"] == dev.id for t in cua_r1)
    # Thiết bị của tích hợp khác: không có trigger của R1
    lạ = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, identifiers={("khac", "x")})
    assert not [t for t in (await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, [lạ.id])).get(lạ.id, []) if t["domain"] == DOMAIN]


async def test_cu_chi_that_bat_trigger_thiet_bi_dung_loai_va_dung_thiet_bi(hass, r1):
    e, phim, *_ = await _lien_ket(hass, r1)
    dev = _device(hass, e)
    chay = []
    hass.services.async_register("test", "ghi", lambda c: chay.append((c.data["loai"], c.data.get("phim"))))
    assert await async_setup_component(hass, "automation", {"automation": [
        {"alias": loai, "trigger": {"platform": "device", "domain": DOMAIN, "device_id": dev.id, "type": loai},
         "action": {"service": "test.ghi", "data": {"loai": loai, "phim": "{{ trigger.event.data.phim }}"}}}
        for loai in ("don", "giu")]})
    for cu_chi in ("don", "doi", "ba", "giu"):
        phim._cu_chi_that(195, cu_chi)
        await hass.async_block_till_done()
    assert chay == [("don", 195), ("giu", 195)], chay            # chỉ hai loại đã gán chạy; đúp/ba không kích hoạt gì
    phim._cu_chi_that(196, "don")                                      # mã phím khác vẫn bắn trigger (kèm mã), automation tự lọc nếu cần
    await hass.async_block_till_done()
    assert chay[-1] == ("don", 196)


async def test_su_kien_bus_co_device_id_va_moi_loai_cu_chi_ke_ca_nhan_ngan(hass, r1):
    e, phim, *_ = await _lien_ket(hass, r1)
    dev = _device(hass, e)
    thu = []
    hass.bus.async_listen(SU_KIEN_PHIM, callback(lambda ev: thu.append(dict(ev.data))))
    for cu_chi in P.CU_CHI_SU_KIEN:
        phim._cu_chi_that(195, cu_chi)
    await hass.async_block_till_done()
    assert [x["type"] for x in thu] == list(P.CU_CHI_SU_KIEN)
    assert all(x["device_id"] == dev.id and x["entry_id"] == e.entry_id and x["phim"] == 195 for x in thu)


async def test_bon_nut_ao_mo_phong_dung_duong_cua_phim_that(hass, r1):
    """Bấm nút ảo = bắn trigger + cập nhật event.r1_phim + chạy hành động đang chọn cho cử chỉ đó (như bấm phím thật)."""
    e, phim, *_ = await _lien_ket(hass, r1)
    reg = er.async_get(hass)
    dev = _device(hass, e)
    nut = {cc: reg.async_get_entity_id("button", DOMAIN, f"{e.entry_id}_phim_nut_{cc}") for cc in P.CU_CHI}
    assert all(nut.values()) and len(set(nut.values())) == 4, nut
    assert nut["don"] == "button.r1_nut_giua_don"
    bat = []
    hass.bus.async_listen(SU_KIEN_PHIM, callback(lambda ev: bat.append((ev.data["type"], ev.data["phim"]))))
    goi = []
    hass.services.async_register("media_player", "volume_up", lambda c: goi.append(c.data["entity_id"]))
    sel = reg.async_get_entity_id("select", DOMAIN, f"{e.entry_id}_phim_ba")
    await hass.services.async_call("select", "select_option", {"entity_id": sel, "option": "tang_am_luong"}, blocking=True)
    for cc in P.CU_CHI:
        await hass.services.async_call("button", "press", {"entity_id": nut[cc]}, blocking=True)
    await hass.async_block_till_done()
    assert bat == [(cc, 195) for cc in P.CU_CHI], bat
    assert goi and goi[0].startswith("media_player."), goi                  # nhấn ba lần ảo chạy hành động đã chọn (tăng âm lượng)
    ev = reg.async_get_entity_id("event", DOMAIN, f"{e.entry_id}_phim")
    assert hass.states.get(ev).attributes["event_type"] == "giu"           # cử chỉ cuối cùng
    assert nut["don"] and dev


async def test_nut_ao_dung_ma_phim_hanh_dong_da_cau_hinh_va_cu_chi_la_bi_tu_choi(hass, r1):
    e, phim, *_ = await _lien_ket(hass, r1)
    phim._ma = lambda: {200}                                               # người dùng đổi mã phím hành động
    thu = []
    hass.bus.async_listen(SU_KIEN_PHIM, callback(lambda ev: thu.append(ev.data["phim"])))
    phim.gia_lap("don")
    await hass.async_block_till_done()
    assert thu == [200]
    with pytest.raises(ValueError):
        phim.gia_lap("xoay")
