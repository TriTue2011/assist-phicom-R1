"""Thông tin hệ thống của loa (CPU, RAM, bộ nhớ trong, WiFi, thời gian chạy): phân tích đầu ra THẬT của loa R1 và thực thể HA."""

import json

import pytest

from custom_components.r1_speaker.adb_client import AdbError
from custom_components.r1_speaker.he_thong import LENH, phan_tich

from .test_bo_dam import _them

# Đầu ra thật của loa (23/10/2026, Android 5.1.1, toolbox + busybox) theo đúng khuôn của LENH.
THAT = """MemTotal:         501444 kB
MemFree:           14640 kB
Buffers:           13764 kB
Cached:           275308 kB
---load
0.80 0.77 0.75 1/502 27148
---s1
cpu  232522 2216 265027 3486837 594 8 8106 0 0 0
---s2
cpu  232539 2217 265058 3487185 594 8 8107 0 0 0
---cpu
0-3
1008000
---df
Filesystem               Size     Used     Free   Blksize
/data                  988.0M   224.6M   763.4M   4096
---wifi
    mWifiInfo: [SSID: Nha Mau, BSSID: 02:00:00:aa:bb:01, MAC: 02:00:00:cc:dd:02, Supplicant state: COMPLETED, RSSI: -32, Link speed: 65Mbps, Frequency: 2412MHz, Net ID: 0]
---up
10177.57 35616.88
---top
User 5%, System 6%, IOW 0%, IRQ 0%
User 69 + Nice 0 + Sys 78 + Idle 1048 + IOW 0 + IRQ 0 + SIRQ 4 = 1199

  PID PR CPU% S  #THR     VSS     RSS PCY UID      Name
  181  3   6% S     5  28764K  23208K  fg logd     /system/bin/logd
  209  2   6% S    16  65460K  16024K  fg system   /system/bin/mediaserver
27153  2   0% R     1   2480K    952K  fg shell    top
   19  2   0% S     1      0K      0K  fg root     ksoftirqd/2
  876  1   0% S    21 574696K  28712K  fg u0_a10   vn.r1.bodam
  187  3   0% S    18  44568K   4668K  fg system   /system/bin/surfaceflinger
"""


def test_phan_tich_dau_ra_that_cua_loa():
    h = phan_tich(THAT)
    assert h.ram_pct == 39.4 and h.ram == {"tong_mb": 489.7, "dung_mb": 193.1, "kha_dung_mb": 296.6, "dem_mb": 282.3}
    assert h.cpu_pct == 12.6                                                   # (398 - 348) / 398 giữa hai mẫu /proc/stat
    assert h.tai == (0.80, 0.77, 0.75) and h.so_nhan == 4 and h.tan_so_mhz == 1008
    assert h.bo_nho_pct == 22.7 and h.bo_nho == {"tong_mb": 988.0, "dung_mb": 224.6, "trong_mb": 763.4}
    assert (h.wifi_dbm, h.wifi_mbps, h.wifi_tan_so_mhz, h.wifi_ssid) == (-32, 65, 2412, "Nha Mau")
    assert h.chay_s == 10177
    assert [(t["ten"], t["cpu_pct"], t["ram_mb"]) for t in h.top] == [
        ("/system/bin/logd", 6, 22.7), ("/system/bin/mediaserver", 6, 15.6), ("ksoftirqd/2", 0, 0.0),
        ("vn.r1.bodam", 0, 28.0), ("/system/bin/surfaceflinger", 0, 4.6)]      # bỏ chính lệnh top (uid shell)


def test_phan_tich_chiu_dau_ra_thieu_hoac_rac_khong_nem_loi():
    for rac in ("", "lỗi gì đó", "---load\nabc\n---s1\ncpu x\n---s2\ncpu y\n", THAT.split("---s2")[0]):
        h = phan_tich(rac)                                   # không ném; chỗ nào thiếu thì None
        assert h.cpu_pct is None
    h = phan_tich(THAT.replace("RSSI: -32, ", ""))
    assert h.wifi_dbm is None and h.wifi_mbps == 65
    assert phan_tich("---s1\ncpu  1 1 1 10 0 0 0\n---s2\ncpu  1 1 1 10 0 0 0\n").cpu_pct is None   # hai mẫu giống nhau: không chia cho 0


def test_lenh_chi_doc_khong_ghi_khong_dung_tham_so_ngoai():
    for cam in (">", "rm ", "reboot", "pm ", "am ", "setprop", "kill", "{", "$("):
        assert cam not in LENH.replace("2>/dev/null", ""), cam


@pytest.fixture
async def ht(hass, r1):
    e = await _them(hass, r1)
    he = e.runtime_data.he_thong

    class Dev:
        host, port, server, mode, duong = "127.0.0.1", 5555, "", "direct", None
        fail = None

        async def shell(self, cmd, *, limit=0, timeout=30):
            if self.fail:
                raise AdbError(self.fail)
            assert cmd == LENH
            return THAT

    he.dev = Dev()
    return e, he


async def test_nam_cam_bien_he_thong_hien_gia_tri_va_thuoc_tinh(hass, ht):
    e, he = ht
    await he.async_refresh()
    await hass.async_block_till_done()
    g = lambda i: hass.states.get(i)
    cpu, ram, bo = g("sensor.r1_cpu"), g("sensor.r1_ram"), g("sensor.r1_bo_nho")
    wifi, up = g("sensor.r1_song_wifi"), g("sensor.r1_thoi_gian_chay")
    assert float(cpu.state) in (12.6, 13.0) and cpu.attributes["so_nhan"] == 4 and cpu.attributes["tan_so_mhz"] == 1008
    assert cpu.attributes["tai_1_phut"] == 0.8 and cpu.attributes["tien_trinh_nang_nhat"][0]["ten"] == "/system/bin/logd"
    assert float(ram.state) in (39.4, 39.0) and ram.attributes["tong_mb"] == 489.7 and ram.attributes["kha_dung_mb"] == 296.6
    assert float(bo.state) in (22.7, 23.0) and bo.attributes["trong_mb"] == 763.4
    assert wifi.state == "-32" and wifi.attributes["ten_wifi"] == "Nha Mau" and wifi.attributes["toc_do_mbps"] == 65
    assert up.state in ("10177", "10177.0", "2.8") and up.attributes["device_class"] == "duration"
    dump = json.dumps([s.as_dict() for s in (cpu, ram, bo, wifi, up)], default=str)
    for bi_mat in ("02:00:00:aa", "02:00:00:cc"):
        assert bi_mat not in dump                                # không lộ BSSID hay MAC


async def test_adb_loi_thi_cam_bien_khong_kha_dung_roi_hoi_phuc(hass, ht):
    e, he = ht
    await he.async_refresh()
    he.dev.fail = "adbd của loa không trả lời"
    await he.async_refresh()
    await hass.async_block_till_done()
    cpu = hass.states.get("sensor.r1_cpu")
    assert cpu.state == "unavailable"
    he.dev.fail = None
    await he.async_refresh()
    await hass.async_block_till_done()
    cpu = hass.states.get("sensor.r1_cpu")
    assert cpu.state != "unavailable"


# ── Đèn ưu tiên số 1, đọc thông tin số 2 ─────────────────────────────

class DenGia:
    def __init__(self):
        self.ap = False
        self.chay = False

    def dang_ap_dung(self, yen_s=2.0):
        return self.ap

    def hieu_ung_chay(self):
        return self.chay


class DevGhi:
    def __init__(self, ra=THAT):
        self.cmds, self.ra = [], ra

    async def shell(self, cmd, *, limit=0, timeout=30):
        self.cmds.append(cmd)
        return self.ra


def _tao(hass, e, den, dev):
    from custom_components.r1_speaker.he_thong import HeThongLoa
    return HeThongLoa(hass, e, dev, den)


async def test_dang_ap_den_thi_cho_den_xong_roi_moi_doc(hass, ht, monkeypatch):
    import asyncio
    from custom_components.r1_speaker import he_thong
    e, _ = ht
    den, dev = DenGia(), DevGhi()
    he = _tao(hass, e, den, dev)
    den.ap = True

    async def tha():
        await asyncio.sleep(0.6)
        den.ap = False

    t = asyncio.create_task(tha())
    h = await he._async_update_data()
    await t
    assert dev.cmds == [LENH] and h.ram_pct == 39.4                           # đã chờ đèn xong, rồi đọc đầy đủ


async def test_den_ban_qua_han_thi_bo_luot_va_giu_so_cu(hass, ht, monkeypatch):
    from custom_components.r1_speaker import he_thong
    monkeypatch.setattr(he_thong, "CHO_DEN_S", 0.5)
    e, _ = ht
    den, dev = DenGia(), DevGhi()
    he = _tao(hass, e, den, dev)
    he.data = phan_tich(THAT)
    den.ap = True
    h = await he._async_update_data()
    assert dev.cmds == [] and h is he.data                                     # đèn đi trước: KHÔNG gọi ADB, giữ số cũ


async def test_hieu_ung_chay_thi_doc_nhe_va_thua_cpu_theo_mau_truoc(hass, ht):
    from custom_components.r1_speaker import he_thong
    e, _ = ht
    den, dev = DenGia(), DevGhi()
    he = _tao(hass, e, den, dev)
    h1 = await he._async_update_data()                                         # chưa có hiệu ứng: đọc đầy đủ
    assert dev.cmds == [LENH] and h1.cpu_pct == 12.6 and h1.nhe is False
    he.data = h1
    den.chay = True
    h2 = await he._async_update_data()
    assert dev.cmds == [LENH] and h2 is h1                                     # hiệu ứng chạy + chưa đủ 5 phút: không gọi gì
    he._lan_cuoi -= he_thong.CHU_KY_NHE_S + 1
    nhe = THAT.split("---s1")[0] + "---s2\ncpu  232600 2217 265100 3487260 594 8 8107 0 0 0\n---cpu\n0-3\n1008000\n---df\n" + \
        "Filesystem Size Used Free Blksize\n/data                  988.0M   224.6M   763.4M   4096\n---up\n10237.57 35616.88\n"
    dev.ra = nhe
    h3 = await he._async_update_data()
    assert dev.cmds[-1] == he_thong.LENH_NHE and "dumpsys" not in he_thong.LENH_NHE and "top " not in he_thong.LENH_NHE
    assert "sleep" not in he_thong.LENH_NHE and h3.nhe is True
    assert h3.cpu_pct == 57.9                                                    # (178 - 75) / 178 so với mẫu /proc/stat của lần đọc trước
    assert h3.wifi_dbm == -32 and h3.top == h1.top                              # WiFi và top giữ từ lần đọc đầy đủ
