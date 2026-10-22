"""Number: âm lượng, 5 dải EQ, cường độ bass, độ lợi loudness."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfSoundPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (DEFAULT_MIC_GAIN_DB, EQ_BAND_NAMES, EQ_BANDS, EQ_MAX, EQ_MIN, GAIN_MAX, GAIN_MIN, MIC_GAIN_MAX,
                    MUSIC_LIGHT_CHROMA, MUSIC_LIGHT_LUMA, MUSIC_LIGHT_RANGE, STRENGTH_MAX, STRENGTH_MIN, VOL_MAX,
                    VOL_MIN)
from .coordinator import R1ConfigEntry, R1Coordinator
from .entity import R1Entity, R1MicEntity, R1MusicLightEntity, preregister


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    preregister(hass, entry, "number", f"{entry.entry_id}_music_light_luma", "r1_do_sang_den_nhac")
    preregister(hass, entry, "number", f"{entry.entry_id}_music_light_chroma", "r1_sac_do_den_nhac")
    preregister(hass, entry, "number", f"{entry.entry_id}_light_master", "r1_do_sang_den")
    async_add_entities([
        R1Volume(c),
        *(R1EqBand(c, i) for i in range(EQ_BANDS)),
        R1BassStrength(c),
        R1LoudnessGain(c),
        R1MusicLightNumber(c, "music_light_luma", MUSIC_LIGHT_LUMA),
        R1MusicLightNumber(c, "music_light_chroma", MUSIC_LIGHT_CHROMA),
    ])
    preregister(hass, entry, "number", f"{entry.entry_id}_mic_gain", "r1_tang_mic")
    async_add_entities([R1MicGain(entry), R1LightMaster(entry)])


class R1Volume(R1Entity, NumberEntity):
    _attr_translation_key = "volume"
    command = "set_volume"
    _attr_native_min_value, _attr_native_max_value = VOL_MIN, VOL_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "volume")

    def _value(self):
        return self.coordinator.data.vol

    @property
    def native_value(self) -> float | None:
        return self._value() if self.coordinator.data is not None else None

    async def async_set_native_value(self, value: float) -> None:
        vol = int(round(value))
        # send_message: CHƯA KIỂM trên thiết bị (xem client.set_volume).
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_volume(vol), vol=vol)


class R1EqBand(R1Entity, NumberEntity):
    _attr_translation_key = "eq_band"
    command = "set_eq_bandlevel"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "mB"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: R1Coordinator, band: int) -> None:
        super().__init__(coordinator, f"eq_band_{band}")
        self._band = band
        self._attr_translation_placeholders = {"band": EQ_BAND_NAMES[band]}

    @property
    def extra_state_attributes(self) -> dict | None:
        # Thẻ Lovelace xếp 5 thanh theo ``band`` (không đoán từ tên thực thể).
        return {**(super().extra_state_attributes or {}), "band": self._band,
                "label": EQ_BAND_NAMES[self._band]}

    @property
    def native_min_value(self) -> float:
        """Giới hạn do loa báo (minBandLevel); chỉ khi loa không báo mới dùng số dự phòng."""
        d = self.coordinator.data
        return d.eq_min if d is not None and d.eq_min is not None else EQ_MIN

    @property
    def native_max_value(self) -> float:
        d = self.coordinator.data
        return d.eq_max if d is not None and d.eq_max is not None else EQ_MAX

    def _value(self):
        return self.coordinator.data.bands[self._band]

    @property
    def native_value(self) -> float | None:
        return self._value() if self.coordinator.data is not None else None

    async def async_set_native_value(self, value: float) -> None:
        level = int(round(value))
        bands = list(self.coordinator.data.bands)
        bands[self._band] = level
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_eq_bandlevel(self._band, level),
            bands=tuple(bands))


class R1BassStrength(R1Entity, NumberEntity):
    _attr_translation_key = "bass_strength"
    command = "set_bass_strength"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value, _attr_native_max_value = STRENGTH_MIN, STRENGTH_MAX
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "bass_strength")

    def _value(self):
        return self.coordinator.data.bass_strength

    @property
    def native_value(self) -> float | None:
        return self._value() if self.coordinator.data is not None else None

    async def async_set_native_value(self, value: float) -> None:
        v = int(round(value))
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_bass_strength(v), bass_strength=v)


class R1LoudnessGain(R1Entity, NumberEntity):
    _attr_translation_key = "loudness_gain"
    command = "set_loudness_gain"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value, _attr_native_max_value = GAIN_MIN, GAIN_MAX
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "mB"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: R1Coordinator) -> None:
        super().__init__(coordinator, "loudness_gain")

    def _value(self):
        return self.coordinator.data.loudness_gain

    @property
    def native_value(self) -> float | None:
        return self._value() if self.coordinator.data is not None else None

    async def async_set_native_value(self, value: float) -> None:
        v = int(round(value))
        await self.coordinator.async_command(
            lambda: self.coordinator.client.set_loudness_gain(v), loudness_gain=v)


class R1MusicLightNumber(R1MusicLightEntity, NumberEntity):
    """Độ sáng (luma 0–100) / sắc độ (chroma 1–100) đèn theo nhạc của firmware."""

    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: R1Coordinator, key: str, code: int) -> None:
        super().__init__(coordinator, key)
        self._key, self._code = key, code
        self._attr_translation_key = key
        self._attr_native_min_value, self._attr_native_max_value = MUSIC_LIGHT_RANGE[code]

    def _value(self):
        return getattr(self.coordinator.data, self._key)

    @property
    def native_value(self) -> float | None:
        return self._value() if self.coordinator.data is not None else None

    async def async_set_native_value(self, value: float) -> None:
        v = int(round(value))
        await self._dat(self._code, v, **{self._key: v})


class R1LightMaster(R1MicEntity, NumberEntity):
    """Độ sáng chung 0–100 % của đèn viền và đèn đáy: nhân vào độ sáng của mọi chức năng đèn (cài từng
    chức năng ở thẻ). Chỉ ra đèn thật khi máy chủ đèn trên loa chạy (xem «Dịch vụ đèn»)."""

    _attr_translation_key = "light_master"
    _attr_native_min_value, _attr_native_max_value, _attr_native_step = 0, 100, 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "light_master")

    @property
    def _lights(self):
        return self._entry.runtime_data.lights

    @property
    def native_value(self) -> float:
        return self._lights.master

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._lights.add_listener(self.async_write_ha_state))

    async def async_set_native_value(self, value: float) -> None:
        await self._lights.async_set_master(int(round(value)))


class R1MicGain(R1MicEntity, RestoreNumber):
    """Tăng mic 0–30 dB, áp trước khi tiếng vào Assist. Mặc định +12 dB (CHƯA ĐO); nhớ giá trị đã
    chỉnh qua lần khởi động HA. Bản thân số này là khuếch đại tuyến tính chặn cứng ở ±32767, không lọc ồn."""

    _attr_translation_key = "mic_gain"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = MIC_GAIN_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_mode = NumberMode.SLIDER

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "mic_gain")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        cu = await self.async_get_last_number_data()
        if cu is not None and cu.native_value is not None:
            self.mic.set_gain(min(max(float(cu.native_value), 0), MIC_GAIN_MAX))
        else:
            self.mic.set_gain(DEFAULT_MIC_GAIN_DB)   # +12 dB, CHƯA ĐO trên mic loa

    @property
    def native_value(self) -> float:
        return self.mic.gain_db

    async def async_set_native_value(self, value: float) -> None:
        self.mic.set_gain(value)
        self.async_write_ha_state()
