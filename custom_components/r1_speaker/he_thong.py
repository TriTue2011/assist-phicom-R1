"""Thông tin hệ thống của loa (CPU, RAM, bộ nhớ trong, WiFi, thời gian chạy, tiến trình nặng nhất) đọc qua ADB.

MỘT lệnh shell chỉ đọc cho mọi cảm biến, mỗi ``CHU_KY_S`` giây (``DataUpdateCoordinator`` chỉ chạy khi có thực thể đang bật).
Phần phân tích là hàm thuần (``phan_tich``) có test với đầu ra thật của loa R1 (Android 5.1, toolbox + busybox).
Không đọc hay hiển thị số sê-ri, địa chỉ MAC hay BSSID của loa."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adb_client import AdbDevice, AdbError

_LOGGER = logging.getLogger(__name__)

CHU_KY_S = 60
#: Có hiệu ứng đèn đang chạy: đọc thưa hơn (chu kỳ này) và bằng lệnh nhẹ.
CHU_KY_NHE_S = 300
#: Đèn đang được áp: chờ tối đa ngần này giây cho đèn xong rồi mới đọc; quá hạn thì bỏ lượt này (đèn luôn đi trước).
CHO_DEN_S = 8.0

#: Một lệnh: bộ nhớ, tải, hai mẫu /proc/stat cách 1 giây (để tính CPU), nhân và tần số, dung lượng /data, WiFi, uptime, top.
LENH = (
    "cat /proc/meminfo | busybox head -n 4; echo ---load; cat /proc/loadavg; echo ---s1; busybox head -n 1 /proc/stat; "
    "sleep 1; echo ---s2; busybox head -n 1 /proc/stat; echo ---cpu; cat /sys/devices/system/cpu/online; "
    "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null; echo ---df; df /data 2>/dev/null; "
    "echo ---wifi; dumpsys wifi 2>/dev/null | busybox grep -m1 mWifiInfo; echo ---bt; settings get global bluetooth_on 2>/dev/null; "
    "echo ---up; cat /proc/uptime; "
    "echo ---top; top -n 1 -m 8 2>/dev/null | busybox tail -n 9"
)

#: Chế độ NHẸ (khi hiệu ứng đèn đang chạy): không ``top``, không ``dumpsys wifi``, không ``sleep``; CPU tính theo mẫu /proc/stat
#: của lần đọc trước.
LENH_NHE = (
    "cat /proc/meminfo | busybox head -n 4; echo ---load; cat /proc/loadavg; echo ---s2; busybox head -n 1 /proc/stat; "
    "echo ---cpu; cat /sys/devices/system/cpu/online; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null; "
    "echo ---df; df /data 2>/dev/null; echo ---bt; settings get global bluetooth_on 2>/dev/null; echo ---up; cat /proc/uptime"
)

_TOP = re.compile(r"^\s*(\d+)\s+\d+\s+(\d+)%\s+\w\s+\d+\s+\d+K\s+(\d+)K\s+\w+\s+(\S+)\s+(.+?)\s*$")


@dataclass
class HeThong:
    cpu_pct: float | None = None
    ram_pct: float | None = None
    ram: dict[str, float] = field(default_factory=dict)
    tai: tuple[float, float, float] | None = None
    so_nhan: int | None = None
    tan_so_mhz: int | None = None
    bo_nho_pct: float | None = None
    bo_nho: dict[str, float] = field(default_factory=dict)
    wifi_dbm: int | None = None
    wifi_mbps: int | None = None
    wifi_ssid: str | None = None
    wifi_tan_so_mhz: int | None = None
    #: Bluetooth của loa bật/tắt (``settings get global bluetooth_on``); None = không đọc được. Phục vụ công tắc Bluetooth.
    bluetooth: bool | None = None
    chay_s: int | None = None
    top: list[dict[str, Any]] = field(default_factory=list)
    #: Mẫu /proc/stat cuối (tổng, rảnh) để lần đọc nhẹ sau tính CPU; None nếu không đọc được.
    mau_cpu: tuple[int, int] | None = None
    nhe: bool = False


def _khoi(txt: str, ten: str) -> str:
    m = re.search(rf"---{ten}\n(.*?)(?=\n---|\Z)", txt, re.S)
    return m.group(1) if m else ""


def _kb(txt: str, khoa: str) -> int | None:
    m = re.search(rf"^{khoa}:\s+(\d+)\s*kB", txt, re.M)
    return int(m.group(1)) if m else None


def _cpu_dong(dong: str) -> tuple[int, int] | None:
    """(tổng, rảnh) từ dòng ``cpu  user nice system idle iowait irq softirq ...``."""
    p = dong.split()
    if len(p) < 5 or p[0] != "cpu":
        return None
    v = [int(x) for x in p[1:] if x.isdigit()]
    return (sum(v[:8]), v[3] + (v[4] if len(v) > 4 else 0)) if len(v) >= 4 else None


def phan_tich(txt: str, truoc: tuple[int, int] | None = None) -> HeThong:
    """``truoc`` = mẫu /proc/stat của lần đọc trước (cho lệnh nhẹ chỉ có một mẫu)."""
    txt = txt.replace("\r", "")
    h = HeThong()
    tong, trong, dem, cache = (_kb(txt, k) for k in ("MemTotal", "MemFree", "Buffers", "Cached"))
    if tong and trong is not None:
        dung = tong - trong - (dem or 0) - (cache or 0)
        h.ram_pct = round(100 * dung / tong, 1)
        h.ram = {"tong_mb": round(tong / 1024, 1), "dung_mb": round(dung / 1024, 1),
                 "kha_dung_mb": round((trong + (dem or 0) + (cache or 0)) / 1024, 1), "dem_mb": round(((dem or 0) + (cache or 0)) / 1024, 1)}
    t = _khoi(txt, "load").split()
    if len(t) >= 3:
        try:
            h.tai = (float(t[0]), float(t[1]), float(t[2]))
        except ValueError:
            pass
    a, b = _cpu_dong(_khoi(txt, "s1").strip()), _cpu_dong(_khoi(txt, "s2").strip())
    h.mau_cpu = b or a
    if a is None and truoc is not None:
        a = truoc                                         # lệnh nhẹ: so với mẫu lần đọc trước
    if a and b and b[0] > a[0]:
        h.cpu_pct = round(100 * ((b[0] - a[0]) - (b[1] - a[1])) / (b[0] - a[0]), 1)
    cpu = _khoi(txt, "cpu").split()
    if cpu:
        m = re.match(r"^(\d+)-(\d+)$", cpu[0])
        h.so_nhan = int(m.group(2)) - int(m.group(1)) + 1 if m else (1 if cpu[0].isdigit() else None)
        if len(cpu) > 1 and cpu[1].isdigit():
            h.tan_so_mhz = round(int(cpu[1]) / 1000)
    for dong in _khoi(txt, "df").splitlines():
        m = re.match(r"^/data\s+([\d.]+)([KMG])\s+([\d.]+)([KMG])\s+([\d.]+)([KMG])", dong.strip())
        if m:
            mb = lambda v, u: float(v) * {"K": 1 / 1024, "M": 1, "G": 1024}[u]
            tg, dg = mb(m.group(1), m.group(2)), mb(m.group(3), m.group(4))
            h.bo_nho_pct = round(100 * dg / tg, 1) if tg else None
            h.bo_nho = {"tong_mb": round(tg, 1), "dung_mb": round(dg, 1), "trong_mb": round(mb(m.group(5), m.group(6)), 1)}
    w = _khoi(txt, "wifi")
    for khoa, bien in (("RSSI", "wifi_dbm"), ("Link speed", "wifi_mbps"), ("Frequency", "wifi_tan_so_mhz")):
        m = re.search(rf"{khoa}:\s*(-?\d+)", w)
        if m:
            setattr(h, bien, int(m.group(1)))
    m = re.search(r"SSID:\s*([^,]+),", w)
    h.wifi_ssid = m.group(1).strip() if m else None
    bt = _khoi(txt, "bt").strip()
    h.bluetooth = True if bt == "1" else (False if bt == "0" else None)
    u = _khoi(txt, "up").split()
    if u:
        try:
            h.chay_s = int(float(u[0]))
        except ValueError:
            pass
    for dong in _khoi(txt, "top").splitlines():
        m = _TOP.match(dong)
        if m and m.group(4) != "shell" and not m.group(5).strip().endswith("top"):
            h.top.append({"ten": m.group(5).strip(), "cpu_pct": int(m.group(2)), "ram_mb": round(int(m.group(3)) / 1024, 1)})
    h.top = h.top[:5]
    return h


class HeThongLoa(DataUpdateCoordinator[HeThong]):
    """Đọc thông tin hệ thống của loa qua ADB (dùng chung ``AdbDevice`` với đèn và bộ cài ứng dụng).

    **Đèn là ưu tiên số 1, đọc thông tin là số 2** (``den`` = sink đèn): đang áp đèn thì chờ cho đèn xong (tối đa
    ``CHO_DEN_S`` giây, quá hạn thì bỏ lượt, giữ số cũ); đang có hiệu ứng đèn chạy thì đọc nhẹ và thưa."""

    def __init__(self, hass, entry, dev: AdbDevice, den=None) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name="r1_he_thong",
                         update_interval=timedelta(seconds=CHU_KY_S))
        self.dev, self.den = dev, den
        self._mau: tuple[int, int] | None = None
        self._lan_cuoi = 0.0

    async def _async_update_data(self) -> HeThong:
        den = self.den
        if den is not None:
            t0 = time.monotonic()
            while den.dang_ap_dung() and time.monotonic() - t0 < CHO_DEN_S:
                await asyncio.sleep(0.25)
            if den.dang_ap_dung():
                _LOGGER.debug("đèn đang bận: bỏ lượt đọc hệ thống")
                return self.data if self.data is not None else HeThong()
            if den.hieu_ung_chay() and self.data is not None and time.monotonic() - self._lan_cuoi < CHU_KY_NHE_S:
                return self.data                           # hiệu ứng đang chạy: đọc thưa
        nhe = bool(den is not None and den.hieu_ung_chay())
        try:
            txt = await self.dev.shell(LENH_NHE if nhe else LENH, timeout=20)
        except (AdbError, OSError, TimeoutError) as exc:
            raise UpdateFailed(f"ADB: {exc or type(exc).__name__}") from exc
        h = phan_tich(txt, self._mau)
        h.nhe = nhe
        if nhe and self.data is not None:                   # lệnh nhẹ không có WiFi/top: giữ giá trị lần đọc đầy đủ gần nhất
            h.wifi_dbm, h.wifi_mbps, h.wifi_ssid, h.wifi_tan_so_mhz, h.top = (
                self.data.wifi_dbm, self.data.wifi_mbps, self.data.wifi_ssid, self.data.wifi_tan_so_mhz, self.data.top)
        self._mau = h.mau_cpu or self._mau
        self._lan_cuoi = time.monotonic()
        return h
