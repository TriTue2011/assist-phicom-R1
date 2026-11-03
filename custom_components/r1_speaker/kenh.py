"""Kênh đàm thoại giữa loa với loa (NV292): nửa công, qua ĐÚNG đường bộ đàm.

Một kênh = tên + loa thành viên + kiểu (``ptt`` bấm-để-nói hoặc ``voice`` tự bật
khi có tiếng). Tiếng đi: mic loa nguồn (PCM16 16 kHz, đã qua khuếch đại/DSP của
``R1Mic``) → hạ tần số về 8 kHz → ``R1Intercom.feed`` của từng loa đích (cổng
thoại ``Gate`` + phát qua ``R1Playback`` + giữ mic chống vọng, y như bộ đàm
thẻ→loa). KHÔNG dựng giao thức tiếng thứ hai, KHÔNG dùng bộ trộn song công
(``hoi_thoai``/``tron_tieng``) — kênh này là bộ đàm nhiều loa, không phải phòng
trộn.

* Cấu hình ở tuỳ chọn từng loa (``kenh`` + ``kenh_kieu``): các loa khai cùng
  tên thì thành một kênh; loa vào kênh theo mục cấu hình của tích hợp, không
  theo IP gõ tay. Một loa chỉ ở một kênh (v1; muốn nhiều kênh thì tách loa).
* Mở kênh = công tắc kênh bật (mặc định TẮT, riêng tư) + một tiếng bip ngắn tới
  các loa thành viên. Đóng kênh = công tắc tắt hoặc hết 30 phút hoặc còn dưới
  2 loa.
* Một người nói một lúc trong mỗi kênh. Loa đích đang bận (Assist, bộ đàm, kênh
  khác) thì toàn bộ lượt nói bị từ chối bằng câu nêu rõ AI đang giữ (cơ chế
  nhãn NV291 trong ``dam_thoai``: nhãn = tên loa nguồn, không biết thì «một
  thiết bị không xác định», không bịa). Nhạc ở loa đích được tạm dừng rồi trả
  lại đúng như NV287 — dùng ``MusicKeeper.hold()`` sẵn có, KHÔNG sửa ``giu_nhac``.
* Giới hạn tài nguyên (quy tắc kho docs/PHAT-TRIEN.md): hàng đợi tiếng có trần
  sẵn trong ``R1Intercom`` (``PLAY_QUEUE_CHUNKS`` + ``hang_doi.day_bo_cu_nhat``);
  tối đa 8 kênh, mỗi kênh tối đa 6 loa; kênh mở tối đa 30 phút; nguồn mất mic
  thì dừng nói; nguồn im quá ``silence_s`` (kiểu voice) thì nhả quyền nói.
* Độ trễ mong đợi (CHƯA ĐO trên loa thật): mic chảy theo khúc 64 ms + hàng đợi
  bộ đàm + kênh phát TCP/APK — ước tính một chiều khoảng 0,2–0,5 giây, chưa gồm
  trễ mạng LAN. Con số này là ước tính từ kích thước khúc, không phải số đo.
"""

from __future__ import annotations

import array
import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (CONF_KENH, CONF_KENH_KIEU, DEFAULT_KENH_KIEU,
                    DEFAULT_TALK_SILENCE, DEFAULT_TALK_THRESHOLD_DB, DOMAIN,
                    EVENT_KENH, INTERCOM_RATE, KENH_KIEU, KENH_MO_TOI_DA_S,
                    KENH_TOI_DA_KENH, KENH_TOI_DA_LOA)
from .intercom import level_db
from .settings import kenh_kieu, kenh_ten

_LOGGER = logging.getLogger(__name__)

#: Tần số tiếng bip khi kênh mở (Hz) và độ dài (giây).
BIP_TAN_SO = 880.0
BIP_GIAY = 0.2
BIP_BIEN_DO = 12000


def ha_tan_so(pcm: bytes) -> bytes:
    """PCM16 mono 16 kHz → 8 kHz: lấy mẫu chẵn (đủ cho giọng bộ đàm; ``R1Intercom``
    nâng lại lên 16 kHz khi phát). Khúc lẻ byte cuối bị bỏ như mọi chỗ khác."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    return array.array("h", a[::2]).tobytes()


def bip_pcm() -> bytes:
    """Một tiếng bip sine ngắn ở tần số bộ đàm (8 kHz) để báo kênh vừa mở."""
    n = int(BIP_GIAY * INTERCOM_RATE)
    return array.array("h", (int(BIP_BIEN_DO * math.sin(2 * math.pi * BIP_TAN_SO * i / INTERCOM_RATE))
                             for i in range(n))).tobytes()


def slug(ten: str) -> str:
    """Tên kênh → hậu tố gợi ý cho entity_id (chỉ giữ chữ/số/gạch dưới)."""
    return "".join(ch if ch.isalnum() else "_" for ch in ten.strip().lower()) or "kenh"


def _muc(entry: Any, key: str) -> Any:
    """Đọc options của một mục: nhận cả ConfigEntry thật lẫn dict giả trong test."""
    if isinstance(entry, dict):
        return entry.get("options", {}).get(key)
    return entry.options.get(key)


def _ma(entry: Any) -> str:
    return entry["entry_id"] if isinstance(entry, dict) else entry.entry_id


def _tieu_de(entry: Any) -> str:
    return entry.get("title", "") if isinstance(entry, dict) else entry.title


def nhom_kenh(entries: Any) -> dict[str, dict[str, Any]]:
    """Gộp định nghĩa kênh từ tuỳ chọn của mọi loa: cùng tên → cùng kênh.

    Tên trống thì bỏ; kiểu trống thì về mặc định ``ptt``; kiểu lạ (có giá trị
    nhưng không thuộc ``KENH_KIEU``) thì bỏ cả định nghĩa (không tự đổi thành
    kiểu khác); trùng tên khác kiểu thì định nghĩa đầu thắng và ghi cảnh báo. Quá
    8 kênh thì giữ 8 kênh đầu theo thứ tự gặp, bỏ phần còn lại (ghi cảnh báo).
    Số loa mỗi kênh KHÔNG cắt ở đây: mở kênh quá 6 loa sẽ báo lỗi rõ ràng."""
    nhom: dict[str, dict[str, Any]] = {}
    for e in entries:
        ten = str(_muc(e, CONF_KENH) or "").strip()
        if not ten:
            continue
        kieu = str(_muc(e, CONF_KENH_KIEU) or "").strip() or DEFAULT_KENH_KIEU
        if kieu not in KENH_KIEU:
            _LOGGER.warning("kenh: loa %s khai kiểu kênh lạ %r cho kênh %r — bỏ định nghĩa",
                            _ma(e), kieu, ten)
            continue
        if ten in nhom:
            if nhom[ten]["kieu"] != kieu:
                _LOGGER.warning("kenh: kênh %r khai hai kiểu (%s và %s) — giữ kiểu đầu",
                                ten, nhom[ten]["kieu"], kieu)
            if _ma(e) not in nhom[ten]["thanh_vien"]:
                nhom[ten]["thanh_vien"].append(_ma(e))
            continue
        if len(nhom) >= KENH_TOI_DA_KENH:
            _LOGGER.warning("kenh: quá %d kênh — bỏ kênh %r", KENH_TOI_DA_KENH, ten)
            continue
        nhom[ten] = {"ten": ten, "thanh_vien": [_ma(e)], "kieu": kieu}
    return nhom


class Kenh:
    """Trạng thái chạy của một kênh."""

    def __init__(self, dinh_nghia: dict[str, Any]) -> None:
        self.ten = dinh_nghia["ten"]
        self.kieu = dinh_nghia["kieu"]
        self.thanh_vien: list[str] = list(dinh_nghia["thanh_vien"])
        self.mo = False
        self.nguoi_noi: str | None = None
        self.noi_tu = 0.0
        self._dang_mo_noi = False
        self._huy_mic_kenh: list[Callable[[], None]] = []
        self._huy_mic_noi: list[Callable[[], None]] = []
        self._nha_phien: dict[str, Callable[[], None]] = {}
        self._giu_nhac: dict[str, Any] = {}
        self._cho: asyncio.Task | None = None

    def mo_ta(self, lay_ten: Callable[[str], str]) -> dict[str, Any]:
        return {"ten": self.ten, "kieu": self.kieu, "mo": self.mo,
                "thanh_vien": [lay_ten(e) for e in self.thanh_vien],
                "nguoi_noi": lay_ten(self.nguoi_noi) if self.nguoi_noi else None}


class KenhManager:
    """Quản lý mọi kênh đàm thoại loa–loa của cả HA (nằm ở cấp miền, như phòng
    ``hoi_thoai``). Điều khiển loa lấy qua hàm phân giải để test không cần mục thật."""

    def __init__(self, hass: HomeAssistant,
                 lay_dieu_khien: Callable[[str], Any | None],
                 lay_ten: Callable[[str], str],
                 *, silence_s: float = DEFAULT_TALK_SILENCE,
                 threshold_db: float = DEFAULT_TALK_THRESHOLD_DB,
                 dong_ho: Callable[[], float] = time.monotonic) -> None:
        self.hass = hass
        self._lay_dk = lay_dieu_khien
        self._lay_ten = lay_ten
        self.silence_s = silence_s
        self.threshold_db = threshold_db
        self._dong_ho = dong_ho
        self.dinh_nghia: dict[str, dict[str, Any]] = {}
        self._kenh: dict[str, Kenh] = {}
        self._cb: list[Callable[[], None]] = []

    # ── Người nghe ───────────────────────────────────────────────────────────

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._cb.append(cb)
        return lambda: self._cb.remove(cb) if cb in self._cb else None

    def _bao(self) -> None:
        for cb in list(self._cb):
            try:
                cb()
            except Exception:  # noqa: BLE001 — thực thể hỏng không được phá kênh
                _LOGGER.exception("kenh: listener failed")

    # ── Tra cứu ─────────────────────────────────────────────────────────────

    def kenh(self, ten: str) -> Kenh:
        if ten not in self.dinh_nghia:
            raise HomeAssistantError(f"Chưa có kênh đàm thoại tên «{ten}».")
        return self._kenh.setdefault(ten, Kenh(self.dinh_nghia[ten]))

    def _dk(self, entry_id: str) -> Any:
        dk = self._lay_dk(entry_id)
        if dk is None:
            raise HomeAssistantError(f"Loa {self._lay_ten(entry_id)} chưa nạp xong.")
        return dk

    def trang_thai(self, ten: str) -> dict[str, Any]:
        return self.kenh(ten).mo_ta(self._lay_ten)

    # ── Định nghĩa ──────────────────────────────────────────────────────────

    def lam_moi(self, entries: Any) -> None:
        """Gộp lại định nghĩa từ tuỳ chọn mọi loa. Kênh đang mở mà mất định
        nghĩa thì đóng; loa bị gỡ khỏi định nghĩa thì rời kênh đang mở."""
        moi = nhom_kenh(entries)
        for ten, k in list(self._kenh.items()):
            if not k.mo:
                continue
            if ten not in moi or moi[ten]["kieu"] != k.kieu:
                self.hass.async_create_background_task(
                    self.dong(ten), f"r1_speaker kenh {ten} dong do doi dinh nghia")
                continue
            for eid in list(k.thanh_vien):
                if eid not in moi[ten]["thanh_vien"]:
                    self._loai_loa_khoi_kenh(k, eid)
            for eid in moi[ten]["thanh_vien"]:
                if eid not in k.thanh_vien:
                    k.thanh_vien.append(eid)
            if len(k.thanh_vien) < 2:
                self.hass.async_create_background_task(
                    self.dong(ten), f"r1_speaker kenh {ten} dong do thieu loa")
        # Kênh ĐÓNG giữ trạng thái dựng lười từ định nghĩa cũ (các loa nạp lần lượt nên định nghĩa đổi mỗi lần một loa nạp xong): bỏ để lần tra cứu sau
        # dựng lại từ định nghĩa mới. Nếu không, kênh dựng lúc mới có một loa sẽ kẹt «chỉ có 1 loa» dù hai loa đã khai cùng tên.
        self._kenh = {ten: k for ten, k in self._kenh.items() if k.mo}
        self.dinh_nghia = moi
        self._bao()

    def loai_loa(self, entry_id: str) -> None:
        """Một loa bị gỡ tích hợp: rời mọi kênh đang mở; kênh còn dưới 2 loa thì đóng."""
        for k in list(self._kenh.values()):
            if not k.mo or entry_id not in k.thanh_vien:
                continue
            self._loai_loa_khoi_kenh(k, entry_id)
            if len(k.thanh_vien) < 2:
                self.hass.async_create_background_task(
                    self.dong(k.ten), f"r1_speaker kenh {k.ten} dong do thieu loa")

    def _loai_loa_khoi_kenh(self, k: Kenh, entry_id: str) -> None:
        if k.nguoi_noi == entry_id:
            self._ket_thuc_noi_dong_bo(k)
        k.thanh_vien = [e for e in k.thanh_vien if e != entry_id]

    # ── Mở / đóng kênh ──────────────────────────────────────────────────────

    async def async_mo(self, ten: str) -> None:
        k = self.kenh(ten)
        if k.mo:
            return
        if len(k.thanh_vien) < 2:
            raise HomeAssistantError(f"Kênh «{ten}» cần ít nhất 2 loa, hiện chỉ có "
                                     f"{len(k.thanh_vien)} loa.")
        if len(k.thanh_vien) > KENH_TOI_DA_LOA:
            raise HomeAssistantError(f"Kênh «{ten}» có {len(k.thanh_vien)} loa, vượt tối đa "
                                     f"{KENH_TOI_DA_LOA} loa.")
        for eid in k.thanh_vien:
            self._dk(eid)                       # loa nào chưa nạp thì báo ngay, chưa mở gì
        k.mo = True
        if k.kieu == "voice":
            self._dang_ky_mic_kenh(k)
        k._cho = self.hass.async_create_background_task(
            self._cho_het_han(k), f"r1_speaker kenh {ten} het han")
        bip = bip_pcm()
        for eid in k.thanh_vien:
            dk = self._dk(eid)
            if dk.intercom.playback.configured:  # chưa có kênh phát thì bỏ bip, không lỗi
                with contextlib.suppress(Exception):
                    dk.intercom.feed(bip)
        self.hass.bus.async_fire(EVENT_KENH, {"su_kien": "mo", "kenh": ten,
                                              "loa": [self._lay_ten(e) for e in k.thanh_vien]})
        self._bao()

    async def _cho_het_han(self, k: Kenh) -> None:
        try:
            await asyncio.sleep(KENH_MO_TOI_DA_S)
        except asyncio.CancelledError:
            return
        if k.mo:
            await self.dong(k.ten)

    async def dong(self, ten: str) -> None:
        k = self._kenh.get(ten)
        if k is None or not k.mo:
            return
        if k.nguoi_noi is not None:
            await self._dung_noi(k)
        self._huy_mic_kenh(k)
        if k._cho is not None:
            k._cho.cancel()
            k._cho = None
        k.mo = False
        self.hass.bus.async_fire(EVENT_KENH, {"su_kien": "dong", "kenh": ten})
        self._bao()

    def dong_het(self) -> None:
        for ten, k in list(self._kenh.items()):
            if k.mo:
                self.hass.async_create_background_task(
                    self.dong(ten), f"r1_speaker kenh {ten} dong het")

    # ── Nói ─────────────────────────────────────────────────────────────────

    async def async_noi(self, ten: str, nguon: str) -> None:
        """Bắt đầu nói vào kênh từ loa ``nguon`` (dịch vụ ``noi_kenh`` hoặc tự bật
        kiểu voice). Loa đích nào bận thì toàn bộ lượt nói bị từ chối, chưa chiếm gì."""
        k = self.kenh(ten)
        if not k.mo:
            raise HomeAssistantError(f"Kênh «{ten}» chưa mở (bật công tắc kênh trước).")
        if nguon not in k.thanh_vien:
            raise HomeAssistantError(f"Loa {self._lay_ten(nguon)} không ở trong kênh «{ten}».")
        if k.nguoi_noi is not None:
            if k.nguoi_noi == nguon:
                return                          # bấm lại khi đang nói: không làm gì thêm
            raise HomeAssistantError(
                f"Kênh «{ten}» đang có người nói là {self._lay_ten(k.nguoi_noi)}: "
                "chờ người đó dừng rồi nói.")
        dk_nguon = self._dk(nguon)
        if not dk_nguon.mic.available:
            raise HomeAssistantError(f"Mic của loa {self._lay_ten(nguon)} chưa sẵn sàng.")
        dinh = [e for e in k.thanh_vien if e != nguon]
        # Giai đoạn 1 (đồng bộ, chưa await): kiểm tra rồi chiếm chỗ mọi loa đích.
        # Loa đích bận → ``tu_choi`` ném câu nêu rõ ai đang giữ, chưa chiếm loa nào.
        for eid in dinh:
            dk = self._dk(eid)
            if dk.talk.session is not None:
                raise dk.talk.tu_choi("kenh", self._lay_ten(nguon))
        nhan = self._lay_ten(nguon)
        try:
            for eid in dinh:
                k._nha_phien[eid] = self._dk(eid).talk.claim("kenh", nhan)
        except BaseException:
            for nha in list(k._nha_phien.values()):
                nha()
            k._nha_phien.clear()
            raise
        # Giai đoạn 2: giữ nhạc ở loa đích (tạm dừng rồi trả lại như NV287).
        try:
            for eid in dinh:
                k._giu_nhac[eid] = await self._dk(eid).music.hold()
        except BaseException:
            for nha in list(k._nha_phien.values()):
                nha()
            k._nha_phien.clear()
            raise
        # Giai đoạn 3: nghe mic nguồn (kiểu ptt; kiểu voice đã nghe từ lúc mở kênh).
        if k.kieu == "ptt":
            k._huy_mic_noi = [
                dk_nguon.mic.add_chunk_listener(
                    lambda pcm, _k=k, _n=nguon: self._mic_chunk(_k, _n, pcm)),
                dk_nguon.mic.add_state_listener(
                    lambda _k=k, _n=nguon: self._mic_doi(_k, _n)),
            ]
        else:
            k._huy_mic_noi = [dk_nguon.mic.add_state_listener(
                lambda _k=k, _n=nguon: self._mic_doi(_k, _n))]
        k.nguoi_noi = nguon
        k.noi_tu = self._dong_ho()
        self.hass.bus.async_fire(EVENT_KENH, {"su_kien": "noi", "kenh": ten, "nguon": nhan})
        self._bao()

    async def dung_noi(self, ten: str, nguon: str | None = None) -> None:
        """Dừng nói (dịch vụ ``dung_kenh``). Không ai nói thì im lặng, không lỗi;
        ``nguon`` khác người đang nói thì bỏ qua (không cướp quyền dừng của người khác)."""
        k = self._kenh.get(ten)
        if k is None or k.nguoi_noi is None:
            return
        if nguon is not None and nguon != k.nguoi_noi:
            return
        await self._dung_noi(k)

    async def _dung_noi(self, k: Kenh) -> None:
        giu, nha = self._nha_noi_dong_bo(k)
        for g in giu:
            with contextlib.suppress(Exception):
                await g.release()
        self.hass.bus.async_fire(EVENT_KENH, {"su_kien": "dung", "kenh": k.ten})
        self._bao()

    def _nha_noi_dong_bo(self, k: Kenh) -> tuple[list[Any], list[Callable[[], None]]]:
        """Phần đồng bộ của dừng nói: nhả phiên, dừng phát ở loa đích, huỷ nghe mic.
        Trả (danh sách giữ nhạc, danh sách hàm nhả phiên) để bên gọi tự nhả nhạc —
        riêng hàm nhả phiên đã gọi ngay ở đây."""
        for eid in list(k._nha_phien):
            dk = self._dk_noi(eid)
            if dk is not None:
                with contextlib.suppress(Exception):
                    dk.intercom.stop_talking()
        giu = list(k._giu_nhac.values())
        k._giu_nhac.clear()
        for nha in list(k._nha_phien.values()):
            nha()
        k._nha_phien.clear()
        for huy in k._huy_mic_noi:
            with contextlib.suppress(Exception):
                huy()
        k._huy_mic_noi = []
        k.nguoi_noi = None
        return giu, []

    def _ket_thuc_noi_dong_bo(self, k: Kenh) -> None:
        """Dừng nói từ callback đồng bộ (mic đứt, im quá lâu): phần đồng bộ chạy
        ngay, nhả nhạc chạy nền (không chờ)."""
        giu, _ = self._nha_noi_dong_bo(k)
        if giu:
            self.hass.async_create_background_task(
                self._nha_nhac(giu), f"r1_speaker kenh {k.ten} nha nhac")
        self._bao()

    async def _nha_nhac(self, giu: list[Any]) -> None:
        for g in giu:
            with contextlib.suppress(Exception):
                await g.release()

    def _dk_noi(self, entry_id: str) -> Any | None:
        """Điều khiển loa, None nếu loa đã bị gỡ (dừng nói không được lỗi vì loa mất)."""
        try:
            return self._lay_dk(entry_id)
        except Exception:  # noqa: BLE001 — loa mất giữa chừng thì bỏ qua
            return None

    # ── Mic ─────────────────────────────────────────────────────────────────

    def _dang_ky_mic_kenh(self, k: Kenh) -> None:
        """Kiểu voice: nghe mic mọi loa từ lúc mở kênh để tự bật khi có tiếng."""
        for eid in k.thanh_vien:
            dk = self._dk(eid)
            k._huy_mic_kenh.append(dk.mic.add_chunk_listener(
                lambda pcm, _k=k, _n=eid: self._mic_chunk(_k, _n, pcm)))

    def _huy_mic_kenh(self, k: Kenh) -> None:
        for huy in k._huy_mic_kenh:
            with contextlib.suppress(Exception):
                huy()
        k._huy_mic_kenh = []

    def _mic_doi(self, k: Kenh, nguon: str) -> None:
        """Mic nguồn đổi trạng thái: không sẵn sàng nữa thì dừng nói ngay."""
        if k.nguoi_noi == nguon:
            try:
                if not self._dk(nguon).mic.available:
                    self._ket_thuc_noi_dong_bo(k)
            except HomeAssistantError:
                self._ket_thuc_noi_dong_bo(k)

    def _mic_chunk(self, k: Kenh, nguon: str, pcm: bytes) -> None:
        if not k.mo or not pcm:
            return
        nay = self._dong_ho()
        if k.nguoi_noi is not None and k.kieu == "voice" and nay - k.noi_tu > self.silence_s:
            # Người đang nói đã im quá lâu: nhả quyền rồi xét khúc này như người mới.
            self._ket_thuc_noi_dong_bo(k)
        if k.nguoi_noi is None:
            if k.kieu != "voice" or k._dang_mo_noi:
                return
            if level_db(pcm) <= self.threshold_db:
                return                          # im lặng: chưa mở nói
            k._dang_mo_noi = True
            self.hass.async_create_background_task(
                self._mo_noi_tu_tieng(k, nguon), f"r1_speaker kenh {k.ten} voice start")
            return
        if k.nguoi_noi != nguon:
            return                              # một người nói một lúc: bỏ tiếng người khác
        if k.kieu == "voice" and level_db(pcm) > self.threshold_db:
            k.noi_tu = nay
        self._dua_tieng(k, nguon, pcm)

    async def _mo_noi_tu_tieng(self, k: Kenh, nguon: str) -> None:
        try:
            await self.async_noi(k.ten, nguon)
        except HomeAssistantError as exc:
            # Tự bật hỏng (đích bận, mic chưa sẵn): chỉ ghi debug, không phá kênh.
            _LOGGER.debug("kenh %s: tự bật khi có tiếng không được: %s", k.ten, exc)
        finally:
            k._dang_mo_noi = False

    def _dua_tieng(self, k: Kenh, nguon: str, pcm: bytes) -> None:
        """Đưa một khúc mic nguồn tới mọi loa đích (trừ nguồn) qua bộ đàm của đích."""
        pcm8 = ha_tan_so(pcm)
        for eid in k.thanh_vien:
            if eid == nguon:
                continue
            dk = self._dk_noi(eid)
            if dk is None:
                continue
            try:
                dk.intercom.feed(pcm8)
            except Exception:  # noqa: BLE001 — một đích hỏng không được giết tiếng các đích khác
                _LOGGER.exception("kenh %s: đưa tiếng tới %s lỗi", k.ten, self._lay_ten(eid))


def hub(hass: HomeAssistant) -> KenhManager:
    """Quản lý kênh dùng chung cả HA (tạo một lần ở ``async_setup``)."""
    if f"{DOMAIN}_kenh" not in hass.data:
        def lay_dk(entry_id: str) -> Any | None:
            entry = hass.config_entries.async_get_entry(entry_id)
            return getattr(entry, "runtime_data", None) if entry is not None else None

        def lay_ten(entry_id: str) -> str:
            entry = hass.config_entries.async_get_entry(entry_id)
            return entry.title if entry is not None else entry_id

        hass.data[f"{DOMAIN}_kenh"] = KenhManager(hass, lay_dk, lay_ten)
    return hass.data[f"{DOMAIN}_kenh"]


def dieu_khien_tu_thuc_the(hass: HomeAssistant, entity_id: str) -> tuple[str, Any]:
    """(entry_id, điều khiển) từ một thực thể bất kỳ của loa (kiểu ``hoi_thoai``)."""
    rec = er.async_get(hass).async_get(entity_id)
    entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
    c = getattr(entry, "runtime_data", None) if entry is not None and entry.domain == DOMAIN else None
    if c is None:
        raise ServiceValidationError(
            f"{entity_id} không phải thực thể của r1_speaker, hoặc loa chưa nạp xong")
    return entry.entry_id, c


def dang_ky_dich_vu(hass: HomeAssistant) -> None:
    async def _noi(call) -> None:
        eid, _c = dieu_khien_tu_thuc_the(hass, call.data["nguon"])
        try:
            await hub(hass).async_noi(call.data["kenh"], eid)
        except HomeAssistantError as exc:
            raise ServiceValidationError(str(exc)) from exc

    async def _dung(call) -> None:
        nguon = call.data.get("nguon")
        eid = dieu_khien_tu_thuc_the(hass, nguon)[0] if nguon else None
        await hub(hass).dung_noi(call.data["kenh"], eid)

    hass.services.async_register(DOMAIN, "noi_kenh", _noi, schema=vol.Schema({
        vol.Required("kenh"): str,
        vol.Required("nguon"): cv.entity_id}))
    hass.services.async_register(DOMAIN, "dung_kenh", _dung, schema=vol.Schema({
        vol.Required("kenh"): str,
        vol.Optional("nguon"): cv.entity_id}))
