"""Trigger thiết bị cho nút giữa của loa R1: chọn bằng giao diện (Tự động hoá → Thêm trigger → Thiết bị → Phicomm R1 → «Nhấn đơn nút giữa»...).

Mỗi cử chỉ (đơn, đúp, ba, giữ, nhấn ngắn) là một loại trigger. Nguồn: sự kiện bus ``r1_speaker_phim`` do ``Phim._cu_chi_that`` bắn cho MỌI cử chỉ,
phím thật hay nút ảo. Biến trong tự động hoá: ``trigger.event.data.phim`` (mã phím). Nhớ: hành động tích hợp của cử chỉ đó (bốn ô chọn) vẫn chạy song
song; chọn «Không làm gì (chỉ phát sự kiện)» nếu muốn cử chỉ chỉ dành cho tự động hoá."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SU_KIEN_PHIM
from .phim import CU_CHI_SU_KIEN

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({vol.Required(CONF_TYPE): vol.In(CU_CHI_SU_KIEN)})


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, str]]:
    """Các trigger của một thiết bị: chỉ thiết bị loa R1 của tích hợp này."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None or not any(i[0] == DOMAIN for i in device.identifiers):
        return []
    return [{CONF_PLATFORM: "device", CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: cu_chi} for cu_chi in CU_CHI_SU_KIEN]


async def async_attach_trigger(hass: HomeAssistant, config: ConfigType, action: TriggerActionType, trigger_info: TriggerInfo) -> CALLBACK_TYPE:
    event_config = event_trigger.TRIGGER_SCHEMA({
        event_trigger.CONF_PLATFORM: "event",
        event_trigger.CONF_EVENT_TYPE: SU_KIEN_PHIM,
        event_trigger.CONF_EVENT_DATA: {CONF_DEVICE_ID: config[CONF_DEVICE_ID], CONF_TYPE: config[CONF_TYPE]},
    })
    return await event_trigger.async_attach_trigger(hass, event_config, action, trigger_info, platform_type="device")
