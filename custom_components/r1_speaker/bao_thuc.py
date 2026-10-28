"""Báo thức, nhắc nhở và hẹn giờ tắt nhạc của loa R1 chạy bằng Home Assistant, thay cho báo thức/ghi nhớ đám mây của hãng (``MemoRingingService``,
``PhicommAlarmHandler`` trong ứng dụng gốc phụ thuộc máy chủ Phicomm đã ngừng).

* **Báo thức**: giờ ``HH:MM``, ngày lặp (rỗng = một lần), nhãn, kiểu kêu: ``tts`` (đọc lời nhắn qua vệ tinh Assist của loa) hoặc ``media`` (phát một địa chỉ âm thanh).
  Kêu lặp lại mỗi ``lap_s`` giây cho tới khi bị tắt (``bao_thuc_tat``, hành động phím ``bao_thuc_dung``) hoặc hết ``toi_da_s``; ``bao_thuc_hoan`` báo lại sau N phút.
* **Nhắc nhở**: báo thức một lần theo thời điểm tuyệt đối hoặc sau N phút, tự xoá sau khi kêu.
* **Hẹn giờ tắt nhạc**: sau N phút nhỏ dần âm lượng (qua APK) rồi dừng nhạc, trả âm lượng về mức cũ.

Lưu bằng ``Store`` nên sống qua khởi động lại HA. Mỗi lần kêu / tắt / hoãn phát sự kiện ``r1_speaker_bao_thuc`` trên bus để tự động hoá bắt.
Giờ tính theo múi giờ của HA (đổi giờ mùa hè không được xử lý riêng)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TOI_DA_BAO_THUC = 50
SU_KIEN = "r1_speaker_bao_thuc"
NGAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LAP_MAC_DINH_S, TOI_DA_MAC_DINH_S, HOAN_MAC_DINH_PHUT = 30, 300, 9
LOI_NHAC_MAC_DINH = "Đến giờ rồi"
#: Hẹn giờ tắt nhạc: số nấc giảm âm lượng tối đa và mức âm lượng bị coi là «đã tắt».
SO_NAC_NHO_DAN = 10


def ke_tiep(a: dict[str, Any], bay_gio: datetime) -> datetime | None:
    """Lần kêu kế tiếp (sau ``bay_gio``) của một báo thức; None nếu không còn (nhắc nhở đã qua giờ, hoặc báo thức tắt)."""
    if not a.get("bat", True):
        return None
    if a.get("luc"):
        d = dt_util.parse_datetime(a["luc"])
        if d is None:
            return None
        d = dt_util.as_local(d)
        return d if d > bay_gio else None
    try:
        gio, phut = (int(x) for x in str(a["gio"]).split(":"))
    except (KeyError, ValueError):
        return None
    ngay = {NGAY.index(n) for n in a.get("ngay") or [] if n in NGAY}
    for them in range(8):
        d = (bay_gio + timedelta(days=them)).replace(hour=gio, minute=phut, second=0, microsecond=0)
        if d > bay_gio and (not ngay or d.weekday() in ngay):
            return d
    return None


def _thuc_the(hass: HomeAssistant, entry, domain: str) -> str | None:
    for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if e.domain == domain and e.platform == DOMAIN:
            return e.entity_id
    return None


class BaoThuc:
    def __init__(self, hass: HomeAssistant, entry, coordinator) -> None:
        self.hass, self.entry, self.coordinator = hass, entry, coordinator
        self._store = Store(hass, 1, f"{DOMAIN}.bao_thuc.{entry.entry_id}")
        self.ds: dict[str, dict[str, Any]] = {}
        self._hen: dict[str, Callable[[], None]] = {}
        self._keu: asyncio.Task | None = None
        self.dang_keu: str | None = None
        self._hen_gio: Callable[[], None] | None = None
        self._lam_mo: asyncio.Task | None = None
        self.hen_gio_luc: datetime | None = None
        self.tren_doi: list[Callable[[], None]] = []
        self._am_luong_cu: int | None = None
        self._noi_dung_keu: dict[str, Any] | None = None       # bản sao báo thức đang kêu (nhắc nhở một lần đã bị xoá khỏi danh sách)

    # ── Lưu và xếp lịch ─────────────────────────────────────────

    async def async_load(self) -> None:
        du = await self._store.async_load()
        if isinstance(du, dict):
            self.ds = {k: v for k, v in (du.get("bao_thuc") or {}).items() if isinstance(v, dict)}
        for i in list(self.ds):
            self._xep(i)

    def _bao_doi(self) -> None:
        for cb in list(self.tren_doi):
            try:
                cb()
            except Exception:  # noqa: BLE001 — người nghe hỏng không được chặn báo thức
                _LOGGER.exception("báo thức: người nghe lỗi")

    def _luu(self) -> None:
        self._store.async_delay_save(lambda: {"bao_thuc": self.ds}, 1.0)
        self._bao_doi()

    def _xep(self, i: str) -> None:
        h = self._hen.pop(i, None)
        if h is not None:
            h()
        a = self.ds.get(i)
        d = ke_tiep(a, dt_util.now()) if a else None
        if d is not None:
            # ``callback(...)``: hàm thường (kể cả lambda) bị HA chạy trong luồng nền, nơi ``bus.async_fire`` bị cấm.
            self._hen[i] = async_track_point_in_time(self.hass, callback(lambda _t, i=i: self._den_gio(i)), d)

    def ke_tiep_chung(self) -> datetime | None:
        ds = [d for a in self.ds.values() if (d := ke_tiep(a, dt_util.now())) is not None]
        return min(ds) if ds else None

    def huy(self) -> None:
        """Gỡ tích hợp: huỷ mọi hẹn giờ và tác vụ đang chạy (không xoá dữ liệu đã lưu)."""
        for h in self._hen.values():
            h()
        self._hen.clear()
        self._dung_keu()
        self._huy_hen_gio()

    # ── Thêm / sửa / xoá ────────────────────────────────────────

    async def dat(self, **kw: Any) -> dict[str, Any]:
        """Thêm báo thức, hoặc cập nhật khi có ``id`` đã tồn tại (chỉ ghi đè các trường truyền vào)."""
        i = kw.pop("id", None) or uuid.uuid4().hex[:8]
        if i not in self.ds and len(self.ds) >= TOI_DA_BAO_THUC:
            raise ServiceValidationError(f"Tối đa {TOI_DA_BAO_THUC} báo thức/nhắc nhở")
        a = {**self.ds.get(i, {"bat": True, "loai": "tts", "lap_s": LAP_MAC_DINH_S, "toi_da_s": TOI_DA_MAC_DINH_S}), **{k: v for k, v in kw.items() if v is not None}}
        if not a.get("gio") and not a.get("luc"):
            raise ServiceValidationError("Cần giờ (gio, dạng HH:MM) hoặc thời điểm (luc)")
        a["id"] = i
        self.ds[i] = a
        self._xep(i)
        self._luu()
        return a

    async def nhac_nho(self, noi_dung: str, *, sau_phut: float | None = None, luc: datetime | None = None, **kw: Any) -> dict[str, Any]:
        """Nhắc nhở một lần: sau ``sau_phut`` phút hoặc đúng ``luc``; kêu xong tự xoá."""
        if (sau_phut is None) == (luc is None):
            raise ServiceValidationError("Cần đúng một trong sau_phut hoặc luc")
        moc = dt_util.now() + timedelta(minutes=sau_phut) if luc is None else dt_util.as_local(luc)
        if moc <= dt_util.now():
            raise ServiceValidationError("Thời điểm nhắc đã qua")
        return await self.dat(luc=moc.isoformat(), nhan=noi_dung, noi_dung=noi_dung, mot_lan=True, **kw)

    async def xoa(self, i: str) -> None:
        if i not in self.ds:
            raise ServiceValidationError(f"Không có báo thức {i}")
        if self.dang_keu == i:
            self._dung_keu()
        h = self._hen.pop(i, None)
        if h is not None:
            h()
        del self.ds[i]
        self._luu()

    async def bat_tat(self, i: str, bat: bool) -> None:
        if i not in self.ds:
            raise ServiceValidationError(f"Không có báo thức {i}")
        self.ds[i]["bat"] = bat
        self._xep(i)
        self._luu()

    # ── Kêu ─────────────────────────────────────────────────────

    @callback
    def _den_gio(self, i: str) -> None:
        a = self.ds.get(i)
        self._hen.pop(i, None)
        if a is None or not a.get("bat", True):
            return
        mot_lan = bool(a.get("mot_lan")) or bool(a.get("luc"))
        if mot_lan:
            self.ds.pop(i, None)                              # nhắc nhở: kêu xong tự xoá (bản sao `a` còn dùng để kêu)
        elif not a.get("ngay"):
            self.ds[i]["bat"] = False                         # báo thức một lần: kêu xong tự tắt, giữ lại để bật lại
        else:
            self._xep(i)                                      # báo thức lặp: xếp lần kế
        self._luu()
        self.hass.bus.async_fire(SU_KIEN, {"entry_id": self.entry.entry_id, "id": i, "nhan": a.get("nhan"), "trang_thai": "keu"})
        self._bat_dau_keu(dict(a))

    def _bat_dau_keu(self, a: dict[str, Any]) -> None:
        self._dung_keu(bao_doi=False)
        self.dang_keu = a["id"]
        self._noi_dung_keu = a
        # Vòng kêu sống tới 30 phút: tác vụ NỀN (không chặn ``async_block_till_done`` hay lúc tắt HA), huỷ khi gỡ tích hợp.
        self._keu = self.hass.async_create_background_task(self._vong_keu(a), f"r1_speaker báo thức {a['id']}")
        self._bao_doi()

    def _dung_keu(self, bao_doi: bool = True) -> None:
        t, self._keu = self._keu, None
        if t is not None and not t.done():
            t.cancel()
        co = self.dang_keu is not None
        self.dang_keu = None
        if co:
            self._noi_dung_keu = None
        if co and bao_doi:
            self._bao_doi()

    async def _vong_keu(self, a: dict[str, Any]) -> None:
        han = self.hass.loop.time() + int(a.get("toi_da_s") or TOI_DA_MAC_DINH_S)
        lap = max(5, int(a.get("lap_s") or LAP_MAC_DINH_S))
        try:
            await self._dat_am_luong(a)
            while self.hass.loop.time() < han:
                await self._phat(a)
                await asyncio.sleep(lap)
            self.hass.bus.async_fire(SU_KIEN, {"entry_id": self.entry.entry_id, "id": a["id"], "nhan": a.get("nhan"), "trang_thai": "het_gio"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — loa chưa nối / vệ tinh lỗi: ghi một dòng, không làm hỏng HA
            _LOGGER.warning("báo thức %s không kêu được: %s", a.get("id"), exc or type(exc).__name__)
        finally:
            if self.dang_keu == a["id"]:
                self.dang_keu = None
                await self._tra_am_luong()
                self._bao_doi()

    async def _phat(self, a: dict[str, Any]) -> None:
        if a.get("loai") == "media" and a.get("noi_dung"):
            loa = _thuc_the(self.hass, self.entry, "media_player")
            if loa is None:
                raise RuntimeError("chưa có thực thể loa")
            await self.hass.services.async_call("media_player", "play_media", {
                "entity_id": loa, "media_content_id": a["noi_dung"], "media_content_type": "music"}, blocking=True)
            return
        sat = _thuc_the(self.hass, self.entry, "assist_satellite")
        if sat is None:
            raise RuntimeError("chưa có vệ tinh Assist của loa")
        await self.hass.services.async_call("assist_satellite", "announce", {
            "entity_id": sat, "message": a.get("noi_dung") or a.get("nhan") or LOI_NHAC_MAC_DINH}, blocking=True)

    async def _dat_am_luong(self, a: dict[str, Any]) -> None:
        pc = a.get("am_luong")
        may = self.coordinator.mic_server
        if pc is None or may.am_luong is None:
            return
        self._am_luong_cu = may.am_luong[0]
        with contextlib.suppress(ConnectionError, OSError, TimeoutError, ValueError):
            await may.gui_am_luong(round(may.am_luong[1] * int(pc) / 100))

    async def _tra_am_luong(self) -> None:
        cu, self._am_luong_cu = self._am_luong_cu, None
        if cu is not None:
            with contextlib.suppress(ConnectionError, OSError, TimeoutError, ValueError):
                await self.coordinator.mic_server.gui_am_luong(cu)

    async def tat(self) -> None:
        """Tắt báo thức đang kêu (không làm gì nếu không có cái nào đang kêu)."""
        i = self.dang_keu
        if i is None:
            return
        self._dung_keu()
        await self._tra_am_luong()
        self.hass.bus.async_fire(SU_KIEN, {"entry_id": self.entry.entry_id, "id": i, "trang_thai": "tat"})

    async def hoan(self, phut: float = HOAN_MAC_DINH_PHUT) -> None:
        """Hoãn báo thức đang kêu: im đi và báo lại sau ``phut`` phút (như nhắc nhở một lần cùng nội dung)."""
        i, a = self.dang_keu, self._noi_dung_keu
        if i is None or a is None:
            return
        await self.tat()
        await self.nhac_nho(a.get("noi_dung") or a.get("nhan") or LOI_NHAC_MAC_DINH, sau_phut=phut, loai=a.get("loai", "tts"),
                            lap_s=a.get("lap_s"), toi_da_s=a.get("toi_da_s"), am_luong=a.get("am_luong"))
        self.hass.bus.async_fire(SU_KIEN, {"entry_id": self.entry.entry_id, "id": i, "trang_thai": "hoan"})

    # ── Hẹn giờ tắt nhạc ────────────────────────────────────────

    async def hen_gio_tat_nhac(self, phut: float, lam_mo_giay: float = 20) -> None:
        """Sau ``phut`` phút: nhỏ dần âm lượng trong ``lam_mo_giay`` giây (cần APK đang nối) rồi dừng nhạc và trả âm lượng cũ."""
        self._huy_hen_gio()
        cho = max(0.0, phut * 60 - lam_mo_giay)
        self.hen_gio_luc = dt_util.now() + timedelta(minutes=phut)
        self._hen_gio = async_call_later(self.hass, cho, callback(lambda _n: self._bat_dau_lam_mo(lam_mo_giay)))
        self._bao_doi()

    def _huy_hen_gio(self) -> None:
        h, self._hen_gio = self._hen_gio, None
        if h is not None:
            h()
        t, self._lam_mo = self._lam_mo, None
        if t is not None and not t.done():
            t.cancel()
        if self.hen_gio_luc is not None:
            self.hen_gio_luc = None
            self._bao_doi()

    async def huy_hen_gio_tat_nhac(self) -> None:
        self._huy_hen_gio()

    @callback
    def _bat_dau_lam_mo(self, lam_mo_giay: float) -> None:
        self._hen_gio = None
        self._lam_mo = self.hass.async_create_background_task(self._lam_mo_roi_dung(lam_mo_giay), "r1_speaker hẹn giờ tắt nhạc")

    async def _lam_mo_roi_dung(self, giay: float) -> None:
        may = self.coordinator.mic_server
        goc = may.am_luong[0] if may.am_luong is not None else None
        try:
            if goc and giay > 0:
                nac = min(SO_NAC_NHO_DAN, goc)
                for k in range(1, nac + 1):
                    await may.gui_am_luong(max(0, goc - round(goc * k / nac)))
                    await asyncio.sleep(giay / nac)
            loa = _thuc_the(self.hass, self.entry, "media_player")
            if loa is not None:
                await self.hass.services.async_call("media_player", "media_stop", {"entity_id": loa}, blocking=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("hẹn giờ tắt nhạc lỗi: %s", exc or type(exc).__name__)
        finally:
            if goc:
                with contextlib.suppress(ConnectionError, OSError, TimeoutError, ValueError, asyncio.CancelledError):
                    await may.gui_am_luong(goc)                    # trả âm lượng cũ cho lần phát sau
            self._lam_mo = None
            self.hen_gio_luc = None
            self._bao_doi()

    # ── Cho thực thể ────────────────────────────────────────────

    def trang_thai(self) -> dict[str, Any]:
        bay_gio = dt_util.now()
        return {
            "bao_thuc": [{**{k: v for k, v in a.items() if k != "noi_dung" or a.get("loai") != "media"},
                          "ke_tiep": (d.isoformat() if (d := ke_tiep(a, bay_gio)) else None)} for a in self.ds.values()],
            "dang_keu": self.dang_keu,
            "hen_gio_tat_nhac": self.hen_gio_luc.isoformat() if self.hen_gio_luc else None,
        }


# ── Dịch vụ HA ────────────────────────────────────────────────────

def _bt_cua(hass: HomeAssistant, entity_id: str) -> BaoThuc:
    rec = er.async_get(hass).async_get(entity_id)
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker")
    bt = getattr(getattr(entry, "runtime_data", None), "bao_thuc", None)
    if bt is None:
        raise ServiceValidationError(f"{entity_id}: loa chưa nạp xong")
    return bt


_GIO = vol.All(cv.string, vol.Match(r"^([01]\d|2[0-3]):[0-5]\d$"))
_KIEU = {
    vol.Optional("nhan"): vol.All(cv.string, vol.Length(max=80)),
    vol.Optional("loai"): vol.In(["tts", "media"]),
    vol.Optional("noi_dung"): vol.All(cv.string, vol.Length(max=500)),
    vol.Optional("lap_s"): vol.All(vol.Coerce(int), vol.Range(min=5, max=600)),
    vol.Optional("toi_da_s"): vol.All(vol.Coerce(int), vol.Range(min=30, max=1800)),
    vol.Optional("am_luong"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
}
DAT_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_id, vol.Optional("id"): cv.string, vol.Optional("gio"): _GIO,
                         vol.Optional("ngay"): vol.All(cv.ensure_list, [vol.In(NGAY)]), vol.Optional("bat"): cv.boolean, **_KIEU})
NHAC_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_id, vol.Required("noi_dung"): vol.All(cv.string, vol.Length(min=1, max=500)),
                          vol.Optional("sau_phut"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10080)), vol.Optional("luc"): cv.datetime,
                          vol.Optional("loai"): vol.In(["tts", "media"]), vol.Optional("lap_s"): _KIEU[vol.Optional("lap_s")],
                          vol.Optional("toi_da_s"): _KIEU[vol.Optional("toi_da_s")], vol.Optional("am_luong"): _KIEU[vol.Optional("am_luong")]})


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _dat(call: ServiceCall) -> None:
        d = dict(call.data)
        await _bt_cua(hass, d.pop("entity_id")).dat(**d)

    async def _nhac(call: ServiceCall) -> None:
        d = dict(call.data)
        bt = _bt_cua(hass, d.pop("entity_id"))
        await bt.nhac_nho(d.pop("noi_dung"), sau_phut=d.pop("sau_phut", None), luc=d.pop("luc", None), **d)

    async def _xoa(call: ServiceCall) -> None:
        await _bt_cua(hass, call.data["entity_id"]).xoa(call.data["id"])

    async def _bat_tat(call: ServiceCall) -> None:
        await _bt_cua(hass, call.data["entity_id"]).bat_tat(call.data["id"], call.data["bat"])

    async def _tat(call: ServiceCall) -> None:
        await _bt_cua(hass, call.data["entity_id"]).tat()

    async def _hoan(call: ServiceCall) -> None:
        await _bt_cua(hass, call.data["entity_id"]).hoan(call.data.get("phut", HOAN_MAC_DINH_PHUT))

    async def _hen_gio(call: ServiceCall) -> None:
        await _bt_cua(hass, call.data["entity_id"]).hen_gio_tat_nhac(call.data["phut"], call.data.get("lam_mo_giay", 20))

    async def _huy_hen_gio(call: ServiceCall) -> None:
        await _bt_cua(hass, call.data["entity_id"]).huy_hen_gio_tat_nhac()

    chi_id = vol.Schema({vol.Required("entity_id"): cv.entity_id})
    hass.services.async_register(DOMAIN, "bao_thuc_dat", _dat, schema=DAT_SCHEMA)
    hass.services.async_register(DOMAIN, "nhac_nho", _nhac, schema=NHAC_SCHEMA)
    hass.services.async_register(DOMAIN, "bao_thuc_xoa", _xoa, schema=vol.Schema({vol.Required("entity_id"): cv.entity_id, vol.Required("id"): cv.string}))
    hass.services.async_register(DOMAIN, "bao_thuc_bat_tat", _bat_tat, schema=vol.Schema(
        {vol.Required("entity_id"): cv.entity_id, vol.Required("id"): cv.string, vol.Required("bat"): cv.boolean}))
    hass.services.async_register(DOMAIN, "bao_thuc_tat", _tat, schema=chi_id)
    hass.services.async_register(DOMAIN, "bao_thuc_hoan", _hoan, schema=vol.Schema(
        {vol.Required("entity_id"): cv.entity_id, vol.Optional("phut"): vol.All(vol.Coerce(float), vol.Range(min=1, max=120))}))
    hass.services.async_register(DOMAIN, "hen_gio_tat_nhac", _hen_gio, schema=vol.Schema(
        {vol.Required("entity_id"): cv.entity_id, vol.Required("phut"): vol.All(vol.Coerce(float), vol.Range(min=1, max=720)),
         vol.Optional("lam_mo_giay"): vol.All(vol.Coerce(float), vol.Range(min=0, max=120))}))
    hass.services.async_register(DOMAIN, "huy_hen_gio_tat_nhac", _huy_hen_gio, schema=chi_id)
