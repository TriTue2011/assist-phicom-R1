"""NV288 — khởi động lại loa theo lịch, và tự phục hồi khi loa treo (mặc định TẮT).

Chủ máy yêu cầu rõ (02/11/2026) làm lịch kể cả khi chưa có bằng chứng treo: coi là phòng ngừa (firmware AIBox cũ có lịch khởi động lại
mỗi ngày nên ít treo; bản hiện tại không có). MỌI lần khởi động lại đều đi qua ``KhoiDongLai.thuc_hien`` và để lại một dòng nhật ký nêu
lý do: ``lich`` (tới giờ), ``treo`` (tự phục hồi), ``bam`` (người dùng bấm nút).

Lịch: bật/tắt + giờ + các ngày trong tuần (tuỳ chọn của tích hợp, xem ``settings.py``). Tới giờ mà loa đang có phiên Assist / đàm thoại /
báo thức kêu hoặc đang phát nhạc thì HOÃN tối đa ``KDL_HOAN_TOI_DA_PHUT`` phút rồi mới khởi động. Cờ «lượt của ngày đó đã chạy» lưu
qua khởi động lại HA và được đặt TRƯỚC khi gửi lệnh, nên không bao giờ khởi động hai lần một lượt, kể cả khi lệnh hỏng. HA bật lại
muộn quá ``KDL_CUA_SO_BU_PHUT`` phút sau giờ lịch thì bỏ lượt đó. Vừa bật lịch / đổi giờ / đổi ngày thì chỉ các lượt SAU lúc đổi mới tính
(đặt giờ 04:00 lúc 04:30 không khởi động loa ngay).

Tự phục hồi (công tắc riêng, mặc định TẮT): «treo» (mạng thông, mọi tín hiệu ứng dụng im — xem ``phan_hoi.py``) liên tục ít nhất
``KDL_TREO_TOI_THIEU_PHUT`` phút VÀ ADB còn nối được thì HA khởi động lại loa MỘT lần qua ADB, rồi nghỉ ít nhất
``KDL_NGHI_SAU_TU_PHUC_HOI_GIO`` giờ (mốc lưu qua khởi động lại HA, đặt TRƯỚC khi gửi lệnh) — không có vòng lặp khởi động lại.
Loa MẤT MẠNG thật thì HA không làm được gì từ xa: chỉ báo, không khởi động.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.assist_satellite.entity import AssistSatelliteState
from homeassistant.const import STATE_PLAYING
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import const
from .adb_client import AdbError
from .client import R1Error
from .const import DOMAIN, KDL_LY_DO_BAM, KDL_LY_DO_LICH, KDL_LY_DO_TREO
from .phan_hoi import TREO
from .settings import adb_tu_dong_dong, khoi_dong_lai_bat, khoi_dong_lai_gio, khoi_dong_lai_khi_treo, khoi_dong_lai_ngay

_LOGGER = logging.getLogger(__name__)

#: Câu mô tả lý do để ghi nhật ký và hiện trên thẻ.
MO_TA_LY_DO = {KDL_LY_DO_LICH: "lịch", KDL_LY_DO_TREO: "loa treo (tự phục hồi)", KDL_LY_DO_BAM: "người dùng bấm"}

#: Trạng thái vệ tinh Assist coi là «đang có phiên» (không phải rảnh).
_VE_TINH_BAN = frozenset({AssistSatelliteState.LISTENING, AssistSatelliteState.PROCESSING, AssistSatelliteState.RESPONDING})


class KhoiDongLai:
    def __init__(self, hass: HomeAssistant, entry, coordinator, *,
                 dong_ho: Callable[[], datetime] = dt_util.now) -> None:
        self.hass, self.entry, self._coordinator, self._dong_ho = hass, entry, coordinator, dong_ho
        self._store = Store(hass, 1, f"{DOMAIN}.khoi_dong_lai.{entry.entry_id}")
        #: Ngày (``YYYY-MM-DD``) của lượt lịch gần nhất đã chạy. Lưu qua khởi động lại HA.
        self.ngay_da_chay: str | None = None
        #: Lần khởi động lại gần nhất: ``{"luc": iso, "ly_do": lich|treo|bam, "chi_tiet": str, "ket_qua": "ok"|"loi: ..."}``.
        self.lan_cuoi: dict[str, Any] | None = None
        self.tu_phuc_hoi_cuoi: datetime | None = None
        #: Chữ ký lịch (bật, giờ, ngày) lần cuối thấy và mốc nó bắt đầu có hiệu lực; chỉ lượt lịch SAU mốc này mới tính.
        self._chu_ky: list | None = None
        self._co_hieu_luc_tu: datetime | None = None
        #: Lý do đang hoãn (None = không hoãn) và mốc bắt đầu hoãn / lượt đang hoãn.
        self.dang_hoan: str | None = None
        self._hoan_tu: datetime | None = None
        self._hoan_luot: datetime | None = None
        self._da_bao: set[str] = set()
        self._khoa = asyncio.Lock()
        self._nguoi_nghe: list[Callable[[], None]] = []

    # ── Lưu và báo ──────────────────────────────────────────────────────────────

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._nguoi_nghe.append(cb)
        return lambda: self._nguoi_nghe.remove(cb)

    def _bao(self) -> None:
        for cb in list(self._nguoi_nghe):
            try:
                cb()
            except Exception:  # noqa: BLE001 — thực thể hỏng không được chặn khởi động lại
                _LOGGER.exception("R1 khởi động lại: người nghe lỗi")

    async def async_load(self) -> None:
        du = await self._store.async_load()
        if not isinstance(du, dict):
            return
        self.ngay_da_chay = du.get("ngay_da_chay") if isinstance(du.get("ngay_da_chay"), str) else None
        self.lan_cuoi = du.get("lan_cuoi") if isinstance(du.get("lan_cuoi"), dict) else None
        self.tu_phuc_hoi_cuoi = _doc_gio(du.get("tu_phuc_hoi_cuoi"))
        self._chu_ky = du.get("chu_ky") if isinstance(du.get("chu_ky"), list) else None
        self._co_hieu_luc_tu = _doc_gio(du.get("co_hieu_luc_tu"))

    def _du_lieu(self) -> dict[str, Any]:
        return {"ngay_da_chay": self.ngay_da_chay, "lan_cuoi": self.lan_cuoi, "chu_ky": self._chu_ky,
                "tu_phuc_hoi_cuoi": self.tu_phuc_hoi_cuoi.isoformat() if self.tu_phuc_hoi_cuoi else None,
                "co_hieu_luc_tu": self._co_hieu_luc_tu.isoformat() if self._co_hieu_luc_tu else None}

    async def _luu_ngay(self) -> None:
        """Ghi xuống đĩa NGAY (không trì hoãn): HA có thể khởi động lại ngay sau lệnh."""
        await self._store.async_save(self._du_lieu())

    # ── Hành động khởi động lại (mọi đường đều qua đây) ────────────────────────

    async def thuc_hien(self, ly_do: str, chi_tiet: str = "", *, chi_adb: bool = False) -> None:
        """Gửi lệnh khởi động lại, ghi nhật ký lý do, nhớ kết quả. ``chi_adb``: không đi đường dự phòng cổng 8080 (loa treo thì cổng đó
        cũng không nghe). Lỗi → ``HomeAssistantError``."""
        host = self._coordinator.client.host
        muc = logging.INFO if ly_do == KDL_LY_DO_BAM else logging.WARNING
        _LOGGER.log(muc, "Khởi động lại loa R1 %s — lý do: %s%s", host, MO_TA_LY_DO[ly_do], f" ({chi_tiet})" if chi_tiet else "")
        try:
            await self._gui_lenh(chi_adb)
        except HomeAssistantError as exc:
            self._ghi(ly_do, chi_tiet, f"loi: {exc}")
            raise
        self._ghi(ly_do, chi_tiet, "ok")
        phan_hoi = getattr(self._coordinator, "phan_hoi", None)
        if phan_hoi is not None:
            phan_hoi.vua_khoi_dong_lai()

    async def _gui_lenh(self, chi_adb: bool) -> None:
        c = self._coordinator
        try:
            await c.apps.dev.reboot()
            return
        except (AdbError, OSError, TimeoutError) as exc:
            loi_adb = exc or type(exc).__name__
        if chi_adb:
            raise HomeAssistantError(f"Không khởi động lại được loa (ADB: {loi_adb})")
        try:                                                        # ADB mạng đóng/hỏng: đi đường cổng 8080
            await c.client.reboot_shell()
        except R1Error as exc:
            raise HomeAssistantError(f"Không khởi động lại được loa (ADB: {loi_adb}; cổng 8080: {exc})") from exc

    def _ghi(self, ly_do: str, chi_tiet: str, ket_qua: str) -> None:
        self.lan_cuoi = {"luc": dt_util.utcnow().isoformat(), "ly_do": ly_do, "chi_tiet": chi_tiet, "ket_qua": ket_qua}
        self._store.async_delay_save(self._du_lieu, 1.0)
        self._bao()

    # ── Nhịp ────────────────────────────────────────────────────────────────────

    async def nhip(self, _luc: datetime | None = None) -> None:
        """Gọi mỗi ``KDL_NHIP_GIAY`` giây: đánh giá «Loa phản hồi», kiểm lịch, kiểm tự phục hồi."""
        async with self._khoa:
            phan_hoi = getattr(self._coordinator, "phan_hoi", None)
            if phan_hoi is not None:
                await phan_hoi.danh_gia()
            bay_gio = self._dong_ho()
            await self._nhip_lich(bay_gio)
            await self._nhip_tu_phuc_hoi(bay_gio)

    def _luot_den_han(self, bay_gio: datetime) -> datetime | None:
        """Lượt lịch đang chờ chạy: hôm nay hoặc hôm qua (lượt 23:50 bị hoãn qua nửa đêm vẫn là lượt của hôm qua), đã tới giờ, chưa chạy,
        có hiệu lực từ trước giờ đó, còn trong cửa sổ bù (hoặc đang hoãn chính lượt đó)."""
        gio, ngay = khoi_dong_lai_gio(self.entry), khoi_dong_lai_ngay(self.entry)
        for lui in (0, 1):
            d = bay_gio.date() - timedelta(days=lui)
            if const.KDL_NGAY_MA[d.weekday()] not in ngay:
                continue
            luot = datetime.combine(d, gio, tzinfo=bay_gio.tzinfo)
            if luot > bay_gio or (self.ngay_da_chay is not None and self.ngay_da_chay >= d.isoformat()):
                continue
            if self._co_hieu_luc_tu is not None and luot < self._co_hieu_luc_tu:
                continue
            if self._hoan_luot == luot or bay_gio - luot <= timedelta(minutes=const.KDL_CUA_SO_BU_PHUT):
                return luot
        return None

    async def cap_nhat_hieu_luc(self) -> None:
        """Ghi nhận lịch hiện tại có hiệu lực từ BÂY GIỜ nếu nó khác lần trước (gọi lúc nạp tích hợp và mỗi nhịp)."""
        bay_gio = self._dong_ho()
        chu_ky = [khoi_dong_lai_bat(self.entry), khoi_dong_lai_gio(self.entry).strftime("%H:%M"), [m for m in const.KDL_NGAY_MA if m in khoi_dong_lai_ngay(self.entry)]]
        if chu_ky != self._chu_ky:
            self._chu_ky, self._co_hieu_luc_tu = chu_ky, bay_gio
            await self._luu_ngay()
            self._bao()

    async def _nhip_lich(self, bay_gio: datetime) -> None:
        await self.cap_nhat_hieu_luc()
        luot = self._luot_den_han(bay_gio) if khoi_dong_lai_bat(self.entry) else None
        if luot is None:
            self._het_hoan()
            return
        ban = self._ly_do_ban()
        chi_tiet = ""
        if self._hoan_tu is not None and self._hoan_luot != luot:
            self._hoan_tu = None                                    # lượt cũ đã qua, đây là lượt khác
        if ban is not None:
            if self._hoan_tu is None:
                self._hoan_tu, self._hoan_luot = bay_gio, luot
                _LOGGER.info("Loa R1 %s: tới giờ khởi động lại theo lịch nhưng %s — hoãn tối đa %d phút",
                             self._coordinator.client.host, ban, const.KDL_HOAN_TOI_DA_PHUT)
            if bay_gio - self._hoan_tu < timedelta(minutes=const.KDL_HOAN_TOI_DA_PHUT):
                if self.dang_hoan != ban:
                    self.dang_hoan = ban
                    self._bao()
                return
            chi_tiet = f"đã hoãn {const.KDL_HOAN_TOI_DA_PHUT} phút vì {ban}, hết hạn hoãn"
        elif self._hoan_tu is not None:
            chi_tiet = f"đã hoãn từ {self._hoan_tu.strftime('%H:%M')} cho tới khi loa rảnh"
        self._het_hoan()
        self.ngay_da_chay = luot.date().isoformat()
        await self._luu_ngay()                                      # đặt cờ TRƯỚC khi gửi lệnh: lệnh hỏng cũng không lặp
        try:
            await self.thuc_hien(KDL_LY_DO_LICH, chi_tiet)
        except HomeAssistantError as exc:
            _LOGGER.warning("Khởi động lại theo lịch không thành: %s (không thử lại trong lượt này)", exc)

    def _het_hoan(self) -> None:
        if self.dang_hoan is not None:
            self.dang_hoan = None
            self._bao()
        self._hoan_tu = self._hoan_luot = None

    def _ly_do_ban(self) -> str | None:
        """Loa có đang bận không (phiên Assist / đàm thoại / báo thức kêu / nhạc)? Trả câu mô tả hoặc None."""
        c = self._coordinator
        if getattr(c.talk, "session", None) is not None:
            return f"đang có phiên đàm thoại ({c.talk.session_kind})"
        if getattr(c.duplex, "active", False):
            return "đang có phiên đàm thoại song công"
        if getattr(c.intercom, "talking", False):
            return "đang nói qua bộ đàm"
        if getattr(c.bao_thuc, "dang_keu", None):
            return "báo thức đang kêu"
        dang = self._thuc_the("assist_satellite")
        if dang is not None and (st := self.hass.states.get(dang)) is not None and st.state in _VE_TINH_BAN:
            return f"Assist đang {st.state}"
        nhac = self._thuc_the("media_player")
        if nhac is not None and (st := self.hass.states.get(nhac)) is not None and st.state == STATE_PLAYING:
            return "đang phát nhạc"
        return None

    def _thuc_the(self, domain: str) -> str | None:
        for e in er.async_entries_for_config_entry(er.async_get(self.hass), self.entry.entry_id):
            if e.domain == domain and e.platform == DOMAIN:
                return e.entity_id
        return None

    async def _nhip_tu_phuc_hoi(self, bay_gio: datetime) -> None:
        ph = getattr(self._coordinator, "phan_hoi", None)
        if ph is None or ph.ly_do != TREO:
            self._da_bao.clear()                                    # hết đợt treo: lần treo sau được báo lại
            return
        if not khoi_dong_lai_khi_treo(self.entry) or ph.treo_tu is None:
            return
        if bay_gio - ph.treo_tu < timedelta(minutes=const.KDL_TREO_TOI_THIEU_PHUT):
            return
        host = self._coordinator.client.host
        if self.tu_phuc_hoi_cuoi is not None and bay_gio - self.tu_phuc_hoi_cuoi < timedelta(hours=const.KDL_NGHI_SAU_TU_PHUC_HOI_GIO):
            self._bao_mot_lan("nghi", logging.INFO, "Loa R1 %s vẫn treo nhưng mới tự khởi động lại lúc %s: nghỉ tối thiểu %d giờ, không lặp",
                              host, self.tu_phuc_hoi_cuoi.isoformat(timespec="seconds"), const.KDL_NGHI_SAU_TU_PHUC_HOI_GIO)
            return
        if adb_tu_dong_dong(self.entry) or not await self._coordinator.apps.dev.con_nghe_mang():
            self._bao_mot_lan("adb", logging.WARNING, "Loa R1 %s treo nhưng ADB không nối được (đã đóng hoặc loa không trả lời cổng 5555): "
                              "HA không tự khởi động lại được, cần rút điện", host)
            return
        self.tu_phuc_hoi_cuoi = bay_gio
        await self._luu_ngay()                                      # đặt mốc nghỉ TRƯỚC khi gửi lệnh
        try:
            await self.thuc_hien(KDL_LY_DO_TREO, f"treo từ {ph.treo_tu.isoformat(timespec='seconds')}", chi_adb=True)
        except HomeAssistantError as exc:
            _LOGGER.warning("Tự khởi động lại khi loa treo không thành: %s (nghỉ %d giờ rồi mới thử lại)", exc, const.KDL_NGHI_SAU_TU_PHUC_HOI_GIO)

    def _bao_mot_lan(self, khoa: str, muc: int, mau: str, *tham_so: Any) -> None:
        if khoa not in self._da_bao:
            self._da_bao.add(khoa)
            _LOGGER.log(muc, mau, *tham_so)

    # ── Thuộc tính cho cảm biến ─────────────────────────────────────────────────

    def ke_tiep(self) -> datetime | None:
        """Lượt lịch kế tiếp (giờ địa phương), None nếu lịch tắt hoặc không chọn ngày nào."""
        if not khoi_dong_lai_bat(self.entry):
            return None
        bay_gio = self._dong_ho()
        gio, ngay = khoi_dong_lai_gio(self.entry), khoi_dong_lai_ngay(self.entry)
        for lui in range(8):
            d = bay_gio.date() + timedelta(days=lui)
            luot = datetime.combine(d, gio, tzinfo=bay_gio.tzinfo)
            if const.KDL_NGAY_MA[d.weekday()] in ngay and luot > bay_gio and (self.ngay_da_chay or "") < d.isoformat():
                return luot
        return None


def _doc_gio(v: Any) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        return dt_util.parse_datetime(v)
    except ValueError:
        return None
