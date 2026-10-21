"""Select: pipeline Assist cho vệ tinh loa R1 (``r1_tro_ly``) và preset EQ của loa."""

from __future__ import annotations

from homeassistant.components.assist_pipeline import AssistPipelineSelect
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import R1ConfigEntry, R1Coordinator
from .entity import R1Entity, R1MicEntity, preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    # unique_id do AssistPipelineSelect tự đặt: f"{entry_id}-pipeline".
    preregister(hass, entry, "select", f"{entry.entry_id}-pipeline", "r1_tro_ly")
    async_add_entities([R1PipelineSelect(hass, entry), R1EqPreset(entry.runtime_data)])


class R1PipelineSelect(R1MicEntity, AssistPipelineSelect):
    def __init__(self, hass: HomeAssistant, entry: R1ConfigEntry) -> None:
        R1MicEntity.__init__(self, entry, "pipeline")
        AssistPipelineSelect.__init__(self, hass, DOMAIN, entry.entry_id)


class R1EqPreset(R1Entity, SelectEntity):
    """Preset EQ của loa: tên đọc từ ``eq.Preset_list``, ``eq.Current_Preset`` = -1 (đang
    chỉnh tay, không preset nào) thì không chọn gì.

    CHỈ ĐỌC được: lệnh đặt preset theo số KHÔNG có trong tài liệu dịch ngược (danh sách lệnh
    cổng 8080 chỉ có set_eq_enable + set_eq_bandlevel; web của loa và R1-card tự áp preset
    bằng cách ghi 5 dải), nên chưa gửi lệnh tự nghĩ lên loa. Chọn → báo lỗi rõ ràng."""

    _attr_translation_key = "eq_preset"
    _attr_entity_category = EntityCategory.CONFIG
    command = None   # chưa có lệnh đặt preset nào được xác định

    @property
    def extra_state_attributes(self) -> dict:
        # Thẻ Lovelace: chỉ cho chọn khi ``selectable`` là True (chưa có lệnh đã xác nhận).
        return {"selectable": False, "confirmed": False}

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
        if d is None or d.eq_preset is None:
            return None
        return next((name for num, name in (d.eq_presets or ()) if num == d.eq_preset), None)

    async def async_select_option(self, option: str) -> None:
        raise HomeAssistantError(
            "Chưa đặt được preset EQ: lệnh đặt preset của loa chưa xác định "
            "(chỉnh từng dải bằng thực thể EQ)")
