"""Thực thể «Cập nhật» cho từng ứng dụng cài lên loa qua ADB (xem ``cai_ung_dung.py``).

Mỗi ứng dụng trong ``apk/bo-cai.json`` có một thực thể ``update.*``: *đã cài* là phiên bản đang trên loa (chưa cài thì
«chưa cài»), *mới nhất* là phiên bản đi kèm tích hợp. Bấm «Cài đặt» (hoặc dịch vụ ``r1_speaker.install_apps``) thì HA đẩy
và cài qua ADB; loa mới tinh dùng đúng đường này."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .adb_client import AdbError
from .cai_ung_dung import TrangThai, UngDung
from .const import DOMAIN
from .coordinator import R1ConfigEntry

SCAN_INTERVAL = timedelta(hours=1)
CHUA_CAI = "chưa cài"
PARALLEL_UPDATES = 1


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    bo = entry.runtime_data.apps
    async_add_entities([R1AppUpdate(entry, ud) for ud in bo.ung_dung], update_before_add=False)


class R1AppUpdate(UpdateEntity):
    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL
    _attr_entity_registry_enabled_default = True

    def __init__(self, entry: R1ConfigEntry, ud: UngDung) -> None:
        self._entry, self._ud = entry, ud
        self._tt: TrangThai | None = None
        self._loi: str | None = None
        self._attr_unique_id = f"{entry.entry_id}_app_{ud.id}"
        self._attr_name = f"Ứng dụng: {ud.ten}"
        self._attr_title = ud.ten
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_release_summary = (f"{ud.canh_bao}\n\n{ud.mo_ta}" if ud.canh_bao else ud.mo_ta) or None


    @property
    def _bo(self):
        return self._entry.runtime_data.apps

    @property
    def available(self) -> bool:
        return self._loi is None

    @property
    def latest_version(self) -> str:
        tt = self._tt
        if tt is not None and tt.cai and tt.an:
            return self.installed_version or self._ud.phien_ban      # gói bị ẩn: không mời «cập nhật» (xem installed_version)
        return self._ud.phien_ban

    @property
    def installed_version(self) -> str | None:
        tt = self._tt
        if tt is None:
            return None
        if not tt.cai:
            return CHUA_CAI
        if tt.an:
            return f"{tt.phien_ban or '?'} (đang ẩn)"          # có trên loa nhưng bị `pm hide`: coi là đã cài, không so với bản đi kèm
        if tt.giong_di_kem:
            return self._ud.phien_ban                       # trùng từng byte với bản đi kèm
        ver = tt.phien_ban or "?"
        return f"{ver} (khác bản đi kèm)" if ver == self._ud.phien_ban else ver

    @property
    def in_progress(self) -> bool:
        return self._bo.dang_cai == self._ud.id

    @property
    def extra_state_attributes(self) -> dict:
        return {"goi": self._ud.goi, "duong_dan": getattr(self._tt, "duong_dan", None), "an": getattr(self._tt, "an", None),
                "ban_di_kem": self._ud.phien_ban, "loi": self._loi}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        cu = self._bo.khi_doi

        def _doi() -> None:
            self.async_write_ha_state()
            if cu is not None:
                cu()

        self._bo.khi_doi = _doi
        self.async_on_remove(lambda: setattr(self._bo, "khi_doi", cu))
        # Lần đọc đầu chạy NỀN: loa chưa nối thì không làm chậm việc nạp tích hợp.
        self._entry.async_create_background_task(self.hass, self._lam_moi(), f"{self.entity_id} lam moi")

    async def _lam_moi(self) -> None:
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        try:
            self._tt = await self._bo.trang_thai(self._ud)
            self._loi = None
        except (AdbError, OSError, TimeoutError) as exc:
            self._loi = f"ADB: {exc or type(exc).__name__}"

    async def async_install(self, version: str | None, backup: bool, **kwargs) -> None:
        kq = await self._bo.cai(self._ud)
        self._tt = None
        await self.async_update()
        self.async_write_ha_state()
        if not kq.ok:
            raise HomeAssistantError(f"{kq.thong_bao} ({'; '.join(kq.buoc)})")
