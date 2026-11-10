"""Select: pipeline Assist cho vệ tinh loa R1 (``r1_tro_ly``) và preset EQ của loa."""

from __future__ import annotations

import contextlib

from homeassistant.components.assist_pipeline import AssistPipelineSelect
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, EQ_MAX, EQ_MIN, EQ_PRESET_MB
from .coordinator import R1ConfigEntry, R1Coordinator
from . import thuc_the_tuy_chon
from .entity import R1Entity, R1MicEntity, preregister
from .phim import CU_CHI, KICH_HOAT, danh_sach


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    # unique_id do AssistPipelineSelect tự đặt: f"{entry_id}-pipeline".
    registry = er.async_get(hass)
    preregister(hass, entry, "select", f"{entry.entry_id}-pipeline", "r1_tro_ly")
    for cc in CU_CHI:
        preregister(hass, entry, "select", f"{entry.entry_id}_phim_{cc}", f"r1_phim_nhan_{cc}")
        # Bản 0.14.0 có thêm một select «Phím …: chạy» riêng cho mỗi cử chỉ (trùng với select hành động): gỡ khỏi sổ thực thể.
        if (cu := registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_phim_chay_{cc}")) is not None:
            registry.async_remove(cu)
    async_add_entities([R1PipelineSelect(hass, entry), R1EqPreset(entry.runtime_data), *[R1PhimSelect(hass, entry, cc) for cc in CU_CHI],
                        *thuc_the_tuy_chon.selects(hass, entry)])


class R1PhimSelect(SelectEntity, RestoreEntity):
    """Hành động khi bấm phím trên loa theo MỘT cử chỉ (đơn / đúp / ba / giữ). Danh sách lấy từ bảng hành động của ``phim.py``: thêm mục
    mới trong mã là nó tự có ở đây. Cuối danh sách là «Chạy: <script / tự động hoá / cảnh / nút> · <entity_id>» lấy từ chính HA (hành động
    ``chay_thuc_the`` kèm đích gộp vào MỘT lựa chọn: loa chỉ có một phím nên mỗi cử chỉ chỉ cần một thực thể). Nhớ lựa chọn qua lần khởi động."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _CHAY = "Chạy: "

    def __init__(self, hass: HomeAssistant, entry: R1ConfigEntry, cu_chi: str) -> None:
        self.hass, self._entry, self._cu_chi = hass, entry, cu_chi
        self._attr_translation_key = f"phim_{cu_chi}"
        self._attr_unique_id = f"{entry.entry_id}_phim_{cu_chi}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    def _nhan(self, entity_id: str) -> str:
        st = self.hass.states.get(entity_id)
        ten = (st.attributes.get("friendly_name") if st else None) or entity_id
        return f"{self._CHAY}{entity_id if ten == entity_id else f'{ten} · {entity_id}'}"

    def _ids(self) -> list[str]:
        return sorted(e for d in KICH_HOAT for e in self.hass.states.async_entity_ids(d))

    @staticmethod
    def _thanh_hanh_dong() -> list[str]:
        return [a for a in danh_sach() if a != "chay_thuc_the"]          # «chạy» chỉ có nghĩa kèm đích: nằm ở các mục «Chạy: …»

    @property
    def options(self) -> list[str]:
        ops = [*self._thanh_hanh_dong(), *[self._nhan(e) for e in self._ids()]]
        cur = self.current_option
        if cur and cur not in ops:                        # thực thể đã bị gỡ: vẫn hiện để chọn lại
            ops.append(cur)
        return ops

    @property
    def current_option(self) -> str | None:
        phim = self._entry.runtime_data.phim
        hd = phim.cau_hinh.get(self._cu_chi)
        if hd == "chay_thuc_the":
            dich = phim.dich.get(self._cu_chi)
            return self._nhan(dich) if dich else None
        return hd

    def _dat(self, option: str) -> None:
        phim = self._entry.runtime_data.phim
        if option.startswith(self._CHAY):
            ent = option[len(self._CHAY):].rsplit(" · ", 1)[-1]
            if ent.split(".", 1)[0] not in KICH_HOAT:
                raise HomeAssistantError(f"«{ent}»: phím chỉ chạy được script, tự động hoá, cảnh hoặc nút")
            phim.cau_hinh[self._cu_chi], phim.dich[self._cu_chi] = "chay_thuc_the", ent
        elif option in self._thanh_hanh_dong():
            phim.cau_hinh[self._cu_chi] = option
            phim.dich.pop(self._cu_chi, None)
        else:
            raise HomeAssistantError(f"Hành động phím «{option}» không có")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        cu = await self.async_get_last_state()
        if cu is not None:
            with contextlib.suppress(HomeAssistantError):
                self._dat(cu.state)

    async def async_select_option(self, option: str) -> None:
        self._dat(option)
        self.async_write_ha_state()


class R1PipelineSelect(R1MicEntity, AssistPipelineSelect):
    def __init__(self, hass: HomeAssistant, entry: R1ConfigEntry) -> None:
        R1MicEntity.__init__(self, entry, "pipeline")
        AssistPipelineSelect.__init__(self, hass, DOMAIN, entry.entry_id)


class R1EqPreset(R1Entity, SelectEntity):
    """Preset EQ của loa: tên đọc từ ``eq.Preset_list``. Loa KHÔNG có lệnh «đặt preset», nên chọn
    preset = ghi 5 dải theo bảng của firmware (``const.EQ_PRESET_MB``) bằng ``set_eq_bandlevel``
    đã xác nhận. ``eq.Current_Preset`` luôn là -1 sau khi ghi từng dải, nên trạng thái hiện tại
    suy ra từ 5 dải: trùng một preset thì hiện tên, lệch thì không chọn gì (đang chỉnh tay)."""

    _attr_translation_key = "eq_preset"
    _attr_entity_category = EntityCategory.CONFIG
    command = "set_eq_bandlevel"

    @property
    def extra_state_attributes(self) -> dict:
        # Thẻ Lovelace: ``selectable`` True vì chọn preset thực chất là ghi 5 dải đã xác nhận.
        return {**(super().extra_state_attributes or {}), "selectable": True}

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "eq_preset")

    def _value(self):
        return self.coordinator.data.eq_presets

    @property
    def options(self) -> list[str]:
        d = self.coordinator.data
        return [name for _, name in (d.eq_presets or ())] if d is not None else []

    @property
    def current_option(self) -> str | None:
        d = self.coordinator.data
        if d is None:
            return None
        if d.eq_preset is not None and d.eq_preset >= 0:
            return next((name for num, name in (d.eq_presets or ()) if num == d.eq_preset), None)
        return next((name for name, levels in EQ_PRESET_MB.items()
                     if tuple(d.bands) == levels and name in self.options), None)

    async def async_select_option(self, option: str) -> None:
        levels = EQ_PRESET_MB.get(option)
        if levels is None:
            raise HomeAssistantError(f"Preset «{option}» chưa có bảng giá trị 5 dải")
        d = self.coordinator.data
        lo = d.eq_min if d is not None and d.eq_min is not None else EQ_MIN
        hi = d.eq_max if d is not None and d.eq_max is not None else EQ_MAX
        levels = tuple(min(max(v, lo), hi) for v in levels)
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_eq_bands(levels), bands=levels)
