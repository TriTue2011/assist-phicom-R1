"""Cài ứng dụng lên loa R1 qua ADB: loa mới tinh cũng cài được toàn bộ ứng dụng cần thiết bằng tích hợp này.

Danh sách ứng dụng là DỮ LIỆU (``apk/bo-cai.json``): gói, tệp (có thể chia nhiều phần vì GitHub giới hạn 25 MB khi tải
lên), sha256 SAU KHI ghép, phiên bản, thứ tự cài, bước sau cài. Mọi tên gói và tên tệp đều qua bộ lọc trước khi vào lệnh
shell; tệp luôn được kiểm sha256 trước khi đẩy lên loa.

Một lần cài một ứng dụng: ghép các phần và kiểm sha256 → đẩy vào ``/data/local/tmp/r1-<id>.apk`` → ``pm install -r`` →
(nếu báo khác chữ ký và người dùng cho phép gỡ bản cũ) ``pm uninstall`` rồi cài lại → xoá tệp tạm → bước sau cài (APK mic
``vn.r1.bodam``: chạy lệnh cấu hình MỘT lần để nối về HA). Không có đường nào đưa chuỗi tuỳ ý vào shell của loa.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .adb_client import AdbDevice, AdbError

_LOGGER = logging.getLogger(__name__)

APK_DIR = Path(__file__).with_name("apk")
BO_CAI = APK_DIR / "bo-cai.json"
TMP = "/data/local/tmp"
_GOI = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
_ID = re.compile(r"^[a-z0-9_]{1,24}$")
_TEP = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_KHOA = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_VERSION = re.compile(r"^[0-9A-Za-z._+-]{1,40}$")
#: Thời gian chờ tối đa cho một lệnh ``pm install`` (đẩy và cài hai chục MB trên Wi-Fi yếu có thể mất cả phút).
CAI_TOI_DA_S = 240
CACHE_S = 30


@dataclass(frozen=True)
class UngDung:
    id: str
    ten: str
    goi: str
    tep: tuple[str, ...]
    sha256: str
    phien_ban: str
    thu_tu: int
    mac_dinh: bool
    mo_ta: str = ""
    sau_cai: str | None = None
    canh_bao: str = ""             # có chữ = ghi đè ứng dụng hệ thống: hiện cảnh báo trong ghi chú bản phát hành
    an_sau_cai: bool = False       # cài xong thì pm hide ngay (công thức của Bo Cai R1: device cài rồi ẩn)
    tu_go_neu_khac_chu_ky: bool = False   # khác chữ ký thì tự gỡ bản cũ rồi cài (Bo Cai R1 làm với bodam; HA tự cấu hình lại bodam sau khi cài nên không mất gì)


#: «Chuẩn bị loa»: quy trình đã chạy tốt bằng chương trình *Bo Cai R1* trên máy tính (24/10/2026, loa vừa reset: sau đó cổng 8080 trả lời, 100 giây sau khi bật).
#: Ẩn (pm hide, đảo được bằng pm unhide) các ứng dụng gốc của hãng vốn gây nhiễu khi máy chủ của hãng không còn: systemtool tắt/bật Wi-Fi, otaservice, device chờ đám
#: mây, bugreport/productiontest/airskill/exceptionreporter; giữ và hiện lại ijetty (máy chủ cổng 8080) và netctl.
AN_KHI_CHUAN_BI = ("com.phicomm.speaker.airskill", "com.phicomm.speaker.exceptionreporter", "com.phicomm.speaker.systemtool",
                   "com.phicomm.speaker.device", "com.phicomm.speaker.otaservice", "com.phicomm.speaker.productiontest",
                   "com.phicomm.speaker.bugreport")
HIEN_KHI_CHUAN_BI = ("com.phicomm.speaker.ijetty", "com.phicomm.speaker.netctl")
#: Dọn trước khi cài (đúng như Bo Cai R1): tệp cập nhật OTA dở và dữ liệu của otaservice (OTA dở có thể làm loa vào chế độ phục hồi/khởi động lại), cho phép cài ngoài chợ.
DON_TRUOC_KHI_CAI = ("rm -f /sdcard/otaprop.txt", "rm -f /sdcard/incremental*.zip",
                     "pm clear com.phicomm.speaker.otaservice", "settings put secure install_non_market_apps 1")
KHOI_CHAY_KHI_CHUAN_BI = ("am startservice -a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
                          "-n com.phicomm.speaker.player/.EchoService")


@dataclass(frozen=True)
class TrangThai:
    """Ứng dụng trên loa: ``cai`` đã cài chưa, ``phien_ban`` đang cài, ``giong_di_kem`` md5 trùng bản đi kèm,
    ``an`` gói có trên loa nhưng đang bị ẩn (``pm hide``: ``pm path`` trả rỗng, ``pm list packages`` không liệt kê)."""

    cai: bool
    phien_ban: str | None = None
    giong_di_kem: bool | None = None
    duong_dan: str | None = None
    an: bool = False


_BAN_GHI_AN = "Hidden system packages:"


def phan_tich_goi(out: str, goi: str) -> tuple[bool, bool, str | None, str | None]:
    """Đọc đầu ra ``dumpsys package <goi>`` đã lọc: ``(có trên loa, bị ẩn, versionName, codePath)``.

    Chỉ đọc bản ghi ĐANG HIỆU LỰC (trước mục «Hidden system packages:», là bản gốc trong /system mà bản cập nhật
    đè lên): một gói hệ thống có bản cập nhật trong /data xuất hiện hai lần với phiên bản khác nhau. «Có trên loa» là
    ``installed=true`` của người dùng 0, KHÔNG phụ thuộc ``pm path`` (rỗng với gói bị ẩn). Định dạng đo trên loa thật
    (Android 5.1): ``User 0:  installed=true hidden=true stopped=false ...``."""
    khoi = out.replace("\r", "").split(_BAN_GHI_AN, 1)[0]
    if f"Package [{goi}]" not in khoi:
        return False, False, None, None
    m = re.search(r"^\s*User 0:.*?\binstalled=(true|false)\b.*?\bhidden=(true|false)\b", khoi, re.M)
    co, an = (m.group(1) == "true", m.group(2) == "true") if m else (True, False)
    ver = re.search(r"^\s*versionName=(.*?)\s*$", khoi, re.M)
    duong = re.search(r"^\s*codePath=(\S+)", khoi, re.M)
    return co, an, (ver.group(1) or None) if ver else None, duong.group(1) if duong else None


@dataclass
class KetQua:
    id: str
    ok: bool
    thong_bao: str
    buoc: list[str] = field(default_factory=list)


def doc_bo_cai(duong: Path = BO_CAI) -> list[UngDung]:
    """Đọc và KIỂM danh sách; sai định dạng thì ``ValueError`` (không cài gì)."""
    data = json.loads(duong.read_text(encoding="utf-8"))
    ra, thay = [], set()
    for d in data["ung_dung"]:
        ud = UngDung(id=d["id"], ten=d["ten"], goi=d["goi"], tep=tuple(d["tep"]), sha256=d["sha256"].lower(),
                     phien_ban=str(d["phien_ban"]), thu_tu=int(d["thu_tu"]), mac_dinh=bool(d.get("mac_dinh", True)),
                     mo_ta=d.get("mo_ta", ""), sau_cai=d.get("sau_cai"), canh_bao=d.get("canh_bao", ""), an_sau_cai=bool(d.get("an_sau_cai", False)),
                     tu_go_neu_khac_chu_ky=bool(d.get("tu_go_neu_khac_chu_ky", False)))
        if not _ID.match(ud.id) or ud.id in thay:
            raise ValueError(f"mã ứng dụng không hợp lệ hoặc trùng: {ud.id!r}")
        if not _GOI.match(ud.goi) or not _VERSION.match(ud.phien_ban) or not re.match(r"^[0-9a-f]{64}$", ud.sha256):
            raise ValueError(f"{ud.id}: gói, phiên bản hoặc sha256 không hợp lệ")
        if not ud.tep or any(not _TEP.match(t) for t in ud.tep) or ud.sau_cai not in (None, "cau_hinh_bodam"):
            raise ValueError(f"{ud.id}: danh sách tệp hoặc bước sau cài không hợp lệ")
        thay.add(ud.id)
        ra.append(ud)
    return sorted(ra, key=lambda u: u.thu_tu)


def ghep_va_kiem(ud: UngDung, thu_muc: Path = APK_DIR) -> bytes:
    """Ghép các phần của ứng dụng và kiểm sha256; sai thì ``ValueError`` (không đẩy tệp hỏng lên loa)."""
    buf = b"".join((thu_muc / t).read_bytes() for t in ud.tep)
    if hashlib.sha256(buf).hexdigest() != ud.sha256:
        raise ValueError(f"{ud.id}: sha256 của tệp ghép không khớp danh sách (tệp hỏng hoặc thiếu phần)")
    return buf


class BoCai:
    """Cài / kiểm tra ứng dụng của MỘT loa qua một ``AdbDevice`` (dùng chung với đường đèn)."""

    def __init__(self, dev: AdbDevice, *, thu_muc: Path = APK_DIR, danh_sach: list[UngDung] | None = None,
                 cau_hinh_bodam: Callable[[], tuple[str, int, str] | None] | None = None) -> None:
        self.dev = dev
        self.thu_muc = thu_muc
        self.ung_dung = danh_sach if danh_sach is not None else doc_bo_cai(thu_muc / "bo-cai.json")
        #: Trả ``(host HA, cổng nghe mic, khoá)`` cho lệnh cấu hình APK; None = chưa đủ thông tin (bỏ bước).
        self._cau_hinh = cau_hinh_bodam
        self._khoa = asyncio.Lock()
        self._nho: dict[str, tuple[float, TrangThai]] = {}
        self.dang_cai: str | None = None
        self.khi_doi: Callable[[], None] | None = None

    def tim(self, ma: str) -> UngDung:
        for u in self.ung_dung:
            if u.id == ma:
                return u
        raise ValueError(f"không có ứng dụng «{ma}»")

    # ── trạng thái ────────────────────────────────────────────

    async def trang_thai(self, ud: UngDung, *, moi: bool = False) -> TrangThai:
        """Một lệnh shell: đường dẫn gói, md5 tệp đã cài, versionName. Nhớ ``CACHE_S`` giây để nhiều thực thể dùng chung."""
        c = self._nho.get(ud.id)
        if c and not moi and time.monotonic() - c[0] < CACHE_S:
            return c[1]
        # ``pm path`` rỗng với gói bị ẩn nên KHÔNG dùng nó để kết luận «chưa cài»: bản ghi trong ``dumpsys package`` mới
        # là nguồn sự thật (``phan_tich_goi``). Phần sau ``---dump`` chỉ giữ vài dòng cần đọc (loa không có ``head``).
        out = await self.dev.shell(
            f'P=$(pm path {ud.goi} 2>/dev/null); P=${{P#package:}}; echo "duong=$P"; '
            f'[ -n "$P" ] && busybox md5sum "$P"; echo "---dump"; dumpsys package {ud.goi} | '
            f'busybox grep -E "Package \\[|codePath=|versionName=|User 0:|{_BAN_GHI_AN}"; true')
        pm, _, dump = out.partition("---dump")
        duong = ma = None
        for dong in pm.replace("\r", "").splitlines():
            dong = dong.strip()
            if dong.startswith("duong="):
                duong = dong[6:] or None
            elif re.match(r"^[0-9a-f]{32}\s", dong):
                ma = dong[:32]
        co, an, ver, code_path = phan_tich_goi(dump, ud.goi)
        giong = None
        if duong and ma:
            # md5 chỉ để so với `md5sum` có sẵn trên loa (nhận biết «cùng tệp»), không dùng cho bảo mật: tính toàn vẹn là sha256 ở ghep_va_kiem.
            giong = ma == hashlib.md5(await asyncio.get_running_loop().run_in_executor(
                None, ghep_va_kiem, ud, self.thu_muc), usedforsecurity=False).hexdigest()
        tt = TrangThai(cai=bool(duong) or co, phien_ban=ver, giong_di_kem=giong, duong_dan=duong or code_path, an=an)
        self._nho[ud.id] = (time.monotonic(), tt)
        return tt

    # ── cài ──────────────────────────────────────────────────

    @staticmethod
    def _ket_qua_pm(out: str) -> tuple[bool, str]:
        """``pm install`` in ``Success`` hoặc ``Failure [MÃ_LỖI]``."""
        out = out.replace("\r", "")
        if re.search(r"^Success\b", out, re.M):
            return True, "Success"
        m = re.search(r"Failure \[([A-Z0-9_:. -]+)\]", out)
        return False, (m.group(1) if m else (out.strip().splitlines() or ["không có phản hồi"])[-1][:120])

    async def cai(self, ud: UngDung, *, go_ban_cu: bool = False, cau_hinh: bool = True, go_truoc: bool = False) -> KetQua:
        """Cài một ứng dụng. Không ném lỗi ADB: trả ``KetQua`` có thông điệp và các bước đã làm."""
        kq = KetQua(ud.id, False, "")
        viec = "chuẩn bị"                       # việc đang làm: để thông báo lỗi chỉ đúng bước và đúng lệnh
        async with self._khoa:
            self.dang_cai = ud.id
            self._bao()
            tep_loa = f"{TMP}/r1-{ud.id}.apk"
            try:
                viec = "ghép và kiểm sha256 tệp APK"
                buf = await asyncio.get_running_loop().run_in_executor(None, ghep_va_kiem, ud, self.thu_muc)
                kq.buoc.append(f"đã kiểm sha256 ({len(buf) // 1024} KB)")
                viec = f"đẩy tệp lên loa ({tep_loa})"
                await self.dev.push(buf, tep_loa, 0o644)
                kq.buoc.append("đã đẩy lên loa")
                if ud.goi in AN_KHI_CHUAN_BI:       # gói đã bị ẩn (lần cài/chuẩn bị trước): hiện lại để cài ghi đè được, lát nữa «chuẩn bị» sẽ ẩn lại
                    viec = f"chạy «pm unhide {ud.goi}»"
                    kq.buoc.append(f"pm unhide {ud.goi}: {(await self.dev.shell(f'pm unhide {ud.goi}', timeout=30)).strip()[-40:] or 'xong'}")
                if go_truoc:                        # «gỡ rồi cài lại»: ứng dụng hệ thống thì gỡ bản cập nhật về bản gốc; lỗi gỡ (chưa cài) thì bỏ qua như Bo Cai R1
                    viec = f"chạy «pm uninstall {ud.goi}»"
                    kq.buoc.append(f"pm uninstall {ud.goi}: {(await self.dev.shell(f'pm uninstall {ud.goi}', timeout=60)).strip()[-50:] or 'xong'}")
                viec = f"chạy «pm install -r {tep_loa}»"
                ok, ma = self._ket_qua_pm(await self.dev.shell(f"pm install -r {tep_loa}", timeout=CAI_TOI_DA_S))
                kq.buoc.append(f"pm install -r: {ma}")
                if not ok and ma == "INSTALL_FAILED_UPDATE_INCOMPATIBLE" and (go_ban_cu or ud.tu_go_neu_khac_chu_ky):
                    kq.buoc.append("khác chữ ký: gỡ bản cũ (mất cấu hình của ứng dụng đó)")
                    viec = f"chạy «pm uninstall {ud.goi}»"
                    await self.dev.shell(f"pm uninstall {ud.goi}", timeout=60)
                    viec = f"chạy «pm install {tep_loa}»"
                    ok, ma = self._ket_qua_pm(await self.dev.shell(f"pm install {tep_loa}", timeout=CAI_TOI_DA_S))
                    kq.buoc.append(f"pm install: {ma}")
                if ok and ud.an_sau_cai:
                    viec = f"chạy «pm hide {ud.goi}»"
                    kq.buoc.append(f"pm hide {ud.goi}: {(await self.dev.shell(f'pm hide {ud.goi}', timeout=30)).strip()[-40:] or 'xong'}")
                if ok and ud.sau_cai == "cau_hinh_bodam" and cau_hinh:
                    viec = "cấu hình ứng dụng vừa cài"
                    kq.buoc.append(await self._cau_hinh_bodam())
                kq.ok = ok
                kq.thong_bao = "Đã cài" if ok else f"Cài thất bại: {ma}"
            except ValueError as exc:
                kq.thong_bao = str(exc)
            except (AdbError, OSError, asyncio.TimeoutError) as exc:
                kq.thong_bao = f"Lỗi ADB khi {viec}: {exc or type(exc).__name__}"
            finally:
                try:
                    await self.dev.shell(f"rm -f {tep_loa}", timeout=20)
                except (AdbError, OSError, asyncio.TimeoutError):
                    pass
                self._nho.pop(ud.id, None)
                self.dang_cai = None
                self._bao()
        (_LOGGER.info if kq.ok else _LOGGER.warning)("cài %s: %s | các bước đã xong: %s", ud.id, kq.thong_bao, "; ".join(kq.buoc) or "chưa có")
        return kq

    async def _cau_hinh_bodam(self) -> str:
        """Chạy lệnh cấu hình APK MỘT lần (app vừa cài đang ``stopped``: lệnh này vừa lưu cấu hình vừa mở app lần đầu nên
        từ đó nó tự chạy khi loa khởi động). Cài đè bản cũ đã cấu hình thì APK bỏ qua lệnh đổi cấu hình (an toàn)."""
        cfg = self._cau_hinh() if self._cau_hinh else None
        if not cfg:
            return "chưa đủ thông tin để cấu hình APK (bỏ qua)"
        host, cong, khoa = cfg
        if not _HOST.match(host) or not isinstance(cong, int) or not 1 <= cong <= 65535 or not _KHOA.match(khoa):
            return "thông tin cấu hình APK không hợp lệ (bỏ qua)"
        await self.dev.shell(f"am start -n vn.r1.bodam/.ManHinhChinh --es host {host} --ei port {cong} "
                             f"--es khoa {khoa} --ez bat true", timeout=30)
        return "đã chạy lệnh cấu hình APK"

    async def don_ota(self, kq: KetQua) -> None:
        """Chạy ``DON_TRUOC_KHI_CAI``; lệnh nào báo lỗi (ví dụ tệp không có) chỉ ghi lại, không dừng. Lỗi ADB thì ném lên."""
        for lenh in DON_TRUOC_KHI_CAI:
            out = (await self.dev.shell(lenh, timeout=30)).strip()
            kq.buoc.append(f"dọn «{lenh}»: {out.splitlines()[-1][:60] if out else 'xong'}")

    async def chuan_bi_loa(self) -> KetQua:
        """Ẩn các ứng dụng gốc gây nhiễu, hiện lại ijetty/netctl, khởi chạy EchoService. Không cài, không gỡ, không khởi động lại loa; ADB hỏng thì ``kq.ok`` False."""
        kq = KetQua("chuan_bi", False, "")
        async with self._khoa:
            try:
                await self.don_ota(kq)
                for goi, an in [(g, True) for g in AN_KHI_CHUAN_BI] + [(g, False) for g in HIEN_KHI_CHUAN_BI]:
                    out = (await self.dev.shell(f"pm {'hide' if an else 'unhide'} {goi}", timeout=30)).strip()
                    xong = f"new hidden state: {'true' if an else 'false'}" in out
                    kq.buoc.append(f"{'ẩn' if an else 'hiện'} {goi}: {'xong' if xong else (out.splitlines()[-1][:80] if out else 'không phản hồi')}")
                kq.buoc.append("khởi chạy EchoService: " + ("xong" if "Starting service" in await self.dev.shell(KHOI_CHAY_KHI_CHUAN_BI, timeout=30) else "không rõ"))
                self._nho.clear()
                kq.ok, kq.thong_bao = True, "Đã chuẩn bị loa (nên khởi động lại loa rồi cài «APK mic bộ đàm»)"
            except (AdbError, OSError, asyncio.TimeoutError) as exc:
                kq.thong_bao = f"Lỗi ADB khi chuẩn bị loa (bước «{kq.buoc[-1] if kq.buoc else 'đầu tiên'}» xong trước đó): {exc or type(exc).__name__}"
        (_LOGGER.info if kq.ok else _LOGGER.warning)("chuẩn bị loa: %s | %s", kq.thong_bao, "; ".join(kq.buoc))
        return kq

    async def cai_nhieu(self, ma: list[str] | None = None, *, go_ban_cu: bool = False,
                        cau_hinh: bool = True, chuan_bi: bool = True, go_truoc: bool = False) -> list[KetQua]:
        """Cài các ứng dụng (mặc định: những cái ``mac_dinh``) theo ``thu_tu``; một cái hỏng không chặn cái sau. Cài xong ít nhất một cái thì chạy
        «Chuẩn bị loa» (ẩn ứng dụng gốc): cài ứng dụng hệ thống mà không ẩn thì loa hỏng (24/10/2026), nên đây là mặc định."""
        chon = [self.tim(m) for m in ma] if ma else [u for u in self.ung_dung if u.mac_dinh]
        if chuan_bi:                                       # dọn OTA TRƯỚC khi cài (cài lâu, OTA dở có thể khởi động lại loa giữa chừng)
            truoc = KetQua("don_ota", False, "")
            try:
                async with self._khoa:
                    await self.don_ota(truoc)
            except (AdbError, OSError, asyncio.TimeoutError) as exc:
                _LOGGER.warning("dọn OTA trước khi cài lỗi (bỏ qua, vẫn cài): %s", exc or type(exc).__name__)
        ra = [await self.cai(u, go_ban_cu=go_ban_cu, cau_hinh=cau_hinh, go_truoc=go_truoc) for u in sorted(chon, key=lambda u: u.thu_tu)]
        if chuan_bi and any(k.ok for k in ra):
            ra.append(await self.chuan_bi_loa())
        return ra

    def _bao(self) -> None:
        if self.khi_doi is not None:
            self.khi_doi()


# ── Phần gắn với HA: dịch vụ ``install_apps`` ─────────────────────────────

def dang_ky_dich_vu(hass, ma_ung_dung: list[str]) -> None:  # noqa: ANN001 - tránh import HA ở đầu tệp lõi
    """``ma_ung_dung``: mã các ứng dụng hợp lệ, đọc từ ``bo-cai.json`` ngoài vòng lặp sự kiện (đọc tệp là việc chặn)."""
    import voluptuous as vol
    from homeassistant.core import ServiceCall, SupportsResponse
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers import entity_registry as er

    from .const import DOMAIN

    async def _cai(call: ServiceCall) -> dict:
        rec = er.async_get(hass).async_get(call.data["entity_id"])
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN or getattr(entry, "runtime_data", None) is None:
            raise ServiceValidationError(f"{call.data['entity_id']} không phải thực thể r1_speaker đã nạp")
        bo = entry.runtime_data.apps
        try:
            kq = await bo.cai_nhieu(call.data.get("apps") or None, go_ban_cu=call.data.get("force", False),
                                    cau_hinh=call.data.get("configure", True), chuan_bi=call.data.get("prepare", True),
                                    go_truoc=call.data.get("reinstall", False))
        except ValueError as exc:
            raise ServiceValidationError(str(exc)) from exc
        ra = {"ket_qua": [{"id": k.id, "ok": k.ok, "thong_bao": k.thong_bao, "buoc": k.buoc} for k in kq]}
        if not any(k.ok for k in kq):
            raise HomeAssistantError("Không cài được ứng dụng nào: " + "; ".join(f"{k.id}: {k.thong_bao}" for k in kq))
        return ra

    async def _chuan_bi(call: ServiceCall) -> dict:
        rec = er.async_get(hass).async_get(call.data["entity_id"])
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN or getattr(entry, "runtime_data", None) is None:
            raise ServiceValidationError(f"{call.data['entity_id']} không phải thực thể r1_speaker đã nạp")
        bo = entry.runtime_data.apps
        kq = await bo.chuan_bi_loa()
        if not kq.ok:
            raise HomeAssistantError(kq.thong_bao)
        if call.data.get("reboot"):
            await bo.dev.reboot()
        return {"thong_bao": kq.thong_bao, "buoc": kq.buoc, "da_khoi_dong_lai": bool(call.data.get("reboot"))}

    hass.services.async_register(DOMAIN, "prepare_speaker", _chuan_bi, supports_response=SupportsResponse.OPTIONAL,
                                 schema=vol.Schema({vol.Required("entity_id"): cv.entity_id, vol.Optional("reboot"): cv.boolean}))
    hass.services.async_register(DOMAIN, "install_apps", _cai, supports_response=SupportsResponse.OPTIONAL,
                                 schema=vol.Schema({
                                     vol.Required("entity_id"): cv.entity_id,
                                     vol.Optional("apps"): [vol.In(ma_ung_dung)],
                                     vol.Optional("force"): cv.boolean,
                                     vol.Optional("configure"): cv.boolean,
                                     vol.Optional("prepare"): cv.boolean,
                                     vol.Optional("reinstall"): cv.boolean}))
