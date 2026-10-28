"""Bộ cài ứng dụng lên loa qua ADB: danh sách, toàn vẹn tệp, trình tự lệnh, lỗi chữ ký, cấu hình APK, thực thể Cập nhật."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.r1_speaker import cai_ung_dung as cu
from custom_components.r1_speaker.adb_client import AdbError
from custom_components.r1_speaker.cai_ung_dung import APK_DIR, BoCai, doc_bo_cai, ghep_va_kiem

from .test_bo_dam import _them

GOC = Path(__file__).parent.parent


class FakeDev:
    """Thiết bị ADB giả: ghi lại lệnh/tệp đẩy và trả phản hồi theo kịch bản."""

    def __init__(self, *, pm="Success", khac_chu_ky=False, cai_san=None):
        self.cmds: list[str] = []
        self.pushed: list[tuple[str, int, str]] = []
        self.pm = pm
        self.khac_chu_ky = khac_chu_ky          # pm install -r (lần đầu) báo UPDATE_INCOMPATIBLE
        self.cai_san = cai_san or {}            # goi -> (đường dẫn, md5, versionName[, bị ẩn])
        self.fail: str | None = None
        self.host, self.port, self.server, self.mode, self.duong = "127.0.0.1", 5555, "", "direct", None

    async def shell(self, cmd, *, limit=0, timeout=30):
        if self.fail:
            raise AdbError(self.fail)
        self.cmds.append(cmd)
        if cmd.startswith("P=$(pm path "):
            goi = re.match(r"P=\$\(pm path (\S+) ", cmd).group(1)
            if goi not in self.cai_san:
                return "duong=\n---dump\n"
            duong, md5, ver, *them = self.cai_san[goi]
            an = bool(them and them[0])
            dump = (f"  Package [{goi}] (e068c0c):\n    codePath=/data/app/{goi}-1\n    versionName={ver}\n"
                    f"    User 0:  installed=true hidden={'true' if an else 'false'} stopped=false notLaunched=false enabled=0\n"
                    f"Hidden system packages:\n  Package [{goi}] (259fc5b):\n    codePath=/system/app/Goc\n"
                    f"    versionName=BAN-GOC\n    User 0:  installed=true hidden=false stopped=false notLaunched=false enabled=0\n")
            if an:                                                          # pm path rỗng với gói bị ẩn
                return f"duong=\n---dump\n{dump}"
            return f"duong={duong}\n{md5}  {duong}\n---dump\n{dump}"
        if cmd.startswith("pm install"):
            if self.khac_chu_ky and " -r " in cmd:
                return "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n"
            return "pkg: /data/local/tmp/x.apk\n" + (self.pm if self.pm == "Success" else f"Failure [{self.pm}]") + "\n"
        if cmd.startswith("pm uninstall"):
            return "Success\n"
        if cmd.startswith("pm clear"):
            return "Success\n"
        if cmd.startswith("pm hide") or cmd.startswith("pm unhide"):
            return f"Package {cmd.split()[-1]} new hidden state: {'true' if cmd.startswith('pm hide') else 'false'}\n"
        if cmd.startswith("am startservice"):
            return "Starting service: Intent { cmp=com.phicomm.speaker.player/.EchoService }\n"
        return ""

    async def push(self, data, remote, mode=0o755):
        if self.fail:
            raise AdbError(self.fail)
        self.pushed.append((remote, len(data), hashlib.sha256(data).hexdigest()))


def _bo(dev=None, cfg=("192.0.2.10", 18765, "KHOA-GIA-0123456789")):
    return BoCai(dev or FakeDev(), cau_hinh_bodam=lambda: cfg), (dev or None)


# ── danh sách và toàn vẹn ─────────────────────────────────────────

def test_danh_sach_dung_ba_ung_dung_va_tep_that_khop_sha256():
    ds = doc_bo_cai()
    assert [(u.id, u.goi, u.phien_ban) for u in ds] == [
        ("player", "com.phicomm.speaker.player", "0.2.5"), ("unisound", "com.phicomm.speaker.device", "V3.2.5.2-"),
        ("bodam", "vn.r1.bodam", "1.3")]
    for u in ds:
        assert hashlib.sha256(ghep_va_kiem(u)).hexdigest() == u.sha256       # tệp thật, kể cả ghép 2 phần của unisound
    assert doc_bo_cai()[1].tep == ("unisound.apk.00", "unisound.apk.01")


def test_apk_mic_dong_goi_giong_ban_build_trong_kho():
    """Hai bản (apk/ cho người build, custom_components/.../apk/ cho HACS) không được lệch nhau."""
    assert (GOC / "apk" / "vn-r1-bodam.apk").read_bytes() == (APK_DIR / "vn-r1-bodam.apk").read_bytes()


def test_tep_hong_hoac_thieu_phan_bi_chan_truoc_khi_day_len_loa(tmp_path):
    for f in APK_DIR.iterdir():
        if f.suffix != ".json":
            shutil.copy(f, tmp_path / f.name)
    shutil.copy(APK_DIR / "bo-cai.json", tmp_path / "bo-cai.json")
    ds = doc_bo_cai(tmp_path / "bo-cai.json")
    uni = next(u for u in ds if u.id == "unisound")
    (tmp_path / "unisound.apk.01").write_bytes(b"x" + (tmp_path / "unisound.apk.01").read_bytes()[1:])
    with pytest.raises(ValueError, match="sha256"):
        ghep_va_kiem(uni, tmp_path)
    (tmp_path / "unisound.apk.01").unlink()
    with pytest.raises(FileNotFoundError):
        ghep_va_kiem(uni, tmp_path)


def test_danh_sach_tu_choi_ten_goi_hoac_tep_nguy_hiem(tmp_path):
    goc = json.loads((APK_DIR / "bo-cai.json").read_text(encoding="utf-8"))
    for sua in ({"goi": "a.b; reboot"}, {"tep": ["../x.apk"]}, {"id": "A B"}, {"sha256": "zz"}, {"sau_cai": "rm"},
                {"phien_ban": "1 2;"}):
        d = json.loads(json.dumps(goc))
        d["ung_dung"][0].update(sua)
        (tmp_path / "bad.json").write_text(json.dumps(d), encoding="utf-8")
        with pytest.raises(ValueError):
            doc_bo_cai(tmp_path / "bad.json")


# ── trình tự cài ────────────────────────────────────────────────

async def test_cai_player_day_len_cai_re_roi_xoa_tep_tam():
    dev = FakeDev()
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai(bo.tim("player"))
    assert kq.ok and kq.thong_bao == "Đã cài"
    assert dev.pushed == [("/data/local/tmp/r1-player.apk", 7262014, bo.tim("player").sha256)]
    assert dev.cmds == ["pm install -r /data/local/tmp/r1-player.apk", "rm -f /data/local/tmp/r1-player.apk"]


async def test_khac_chu_ky_bao_ro_va_chi_go_ban_cu_khi_duoc_phep():
    dev = FakeDev(khac_chu_ky=True)
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai(bo.tim("unisound"))
    assert not kq.ok and "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in kq.thong_bao
    assert not any(c.startswith("pm uninstall") for c in dev.cmds)              # KHÔNG tự gỡ khi chưa cho phép
    dev2 = FakeDev(khac_chu_ky=True)
    kq2 = await BoCai(dev2, cau_hinh_bodam=lambda: None).cai(bo.tim("unisound"), go_ban_cu=True)
    assert kq2.ok and [c.split()[1] for c in dev2.cmds if c.startswith("pm")] == ["unhide", "install", "uninstall", "install", "hide"]
    assert "pm uninstall com.phicomm.speaker.device" in dev2.cmds


async def test_apk_mic_cai_xong_tu_cau_hinh_mot_lan_khong_log_khoa(caplog):
    dev = FakeDev()
    bo = BoCai(dev, cau_hinh_bodam=lambda: ("192.0.2.10", 18765, "KHOA-GIA-0123456789"))
    with caplog.at_level("DEBUG"):
        kq = await bo.cai(bo.tim("bodam"))
    am = [c for c in dev.cmds if c.startswith("am start")]
    assert kq.ok and am == ["am start -n vn.r1.bodam/.ManHinhChinh --es host 192.0.2.10 --ei port 18765 "
                            "--es khoa KHOA-GIA-0123456789 --ez bat true"]
    assert "KHOA-GIA" not in caplog.text and "KHOA-GIA" not in json.dumps(kq.__dict__)    # khoá không vào log/kết quả
    # không cấu hình khi bị tắt, khi cài hỏng, hoặc khi thông tin không hợp lệ
    for dev2, cfg, ch in ((FakeDev(), ("192.0.2.10", 18765, "KHOA-GIA-0123456789"), False),
                          (FakeDev(pm="INSTALL_FAILED_X"), ("192.0.2.10", 18765, "KHOA-GIA-0123456789"), True),
                          (FakeDev(), ("192.0.2.10; reboot", 18765, "KHOA-GIA-0123456789"), True),
                          (FakeDev(), ("192.0.2.10", 18765, "ngắn"), True), (FakeDev(), None, True)):
        await BoCai(dev2, cau_hinh_bodam=lambda c=cfg: c).cai(bo.tim("bodam"), cau_hinh=ch)
        assert not any(c.startswith("am start") for c in dev2.cmds), cfg


async def test_cai_nhieu_theo_thu_tu_mot_cai_hong_khong_chan_cai_sau():
    dev = FakeDev()
    n = {"i": 0}
    goc = dev.shell

    async def shell(cmd, **kw):
        if cmd.startswith("pm install") and "unisound" in cmd:
            return "Failure [INSTALL_FAILED_DEXOPT]\n"
        return await goc(cmd, **kw)

    dev.shell = shell
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai_nhieu()
    assert [(k.id, k.ok) for k in kq] == [("player", True), ("unisound", False), ("bodam", True), ("chuan_bi", True)]
    assert "INSTALL_FAILED_DEXOPT" in kq[1].thong_bao
    assert [k.id for k in await bo.cai_nhieu(["bodam", "player"], chuan_bi=False)] == ["player", "bodam"]    # luôn theo thứ tự
    with pytest.raises(ValueError):
        await bo.cai_nhieu(["khong_co"])


async def test_cai_du_ba_ung_dung_roi_chuan_bi_loa_giong_bo_cai_r1():
    """Công thức đã chạy tốt trên loa vừa reset (Bo Cai R1, 24/10/2026): cài player, device(unisound), bodam rồi ẨN bảy ứng dụng gốc, hiện ijetty/netctl,
    khởi chạy EchoService. Cài ứng dụng hệ thống mà không ẩn thì loa hỏng."""
    from custom_components.r1_speaker.cai_ung_dung import AN_KHI_CHUAN_BI, HIEN_KHI_CHUAN_BI
    dev = FakeDev()
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai_nhieu()
    assert [k.id for k in kq] == ["player", "unisound", "bodam", "chuan_bi"] and all(k.ok for k in kq)
    lenh = dev.cmds
    i_cuoi_cai = max(i for i, c in enumerate(lenh) if c.startswith("pm install"))
    hide = [c for c in lenh if c.startswith("pm hide")]
    assert [c.split()[-1] for c in hide[1:]] == list(AN_KHI_CHUAN_BI)                     # hide[0] là unisound tự ẩn ngay sau khi cài
    assert hide[0] == "pm hide com.phicomm.speaker.device"
    assert [c.split()[-1] for c in lenh if c.startswith("pm unhide")] == ["com.phicomm.speaker.device", *HIEN_KHI_CHUAN_BI]    # device hiện lại TRƯỚC khi cài ghi đè
    assert any(c.startswith("am startservice") and "EchoService" in c for c in lenh)
    i_don = lenh.index("pm clear com.phicomm.speaker.otaservice")
    assert i_don < lenh.index("pm install -r /data/local/tmp/r1-player.apk")                  # dọn OTA TRƯỚC khi cài, như Bo Cai R1
    assert "rm -f /sdcard/otaprop.txt" in lenh and "settings put secure install_non_market_apps 1" in lenh
    assert not any("rm -rf" in c for c in lenh)
    assert min(i for i, c in enumerate(lenh) if c.startswith("pm hide")) > lenh.index(f"pm install -r /data/local/tmp/r1-player.apk")   # ẩn SAU khi cài
    assert i_cuoi_cai < max(i for i, c in enumerate(lenh) if c.startswith("pm hide"))
    assert all("không phản hồi" not in b and "xong" in b for b in kq[-1].buoc if b.startswith(("ẩn", "hiện", "khởi chạy")))


async def test_chuan_bi_loa_loi_adb_bao_ro_buoc_va_khong_nem():
    dev = FakeDev()
    goc = dev.shell
    n = {"i": 0}

    async def shell(cmd, **kw):
        if cmd.startswith("pm hide"):
            n["i"] += 1
            if n["i"] == 3:
                raise AdbError("adbd của loa từ chối ngay dịch vụ «shell:pm hide x»")
        return await goc(cmd, **kw)

    dev.shell = shell
    kq = await BoCai(dev).chuan_bi_loa()
    assert not kq.ok and "Lỗi ADB khi chuẩn bị loa" in kq.thong_bao and "từ chối" in kq.thong_bao and len(kq.buoc) == 6      # 4 bước dọn + 2 lần ẩn xong trước lần thứ 3 hỏng


async def test_cai_mot_ung_dung_he_thong_co_canh_bao_va_van_co_nut_cai(hass, ha_cai):
    e, bo, dev = ha_cai
    from homeassistant.helpers.entity_component import async_update_entity
    for khoa in ("trinh_phat", "unisound"):
        eid = next(i for i in _ud_ids(hass) if khoa in i)
        await async_update_entity(hass, eid)
        st = hass.states.get(eid)
        assert st.attributes["supported_features"] & 1                       # có nút cài (UpdateEntityFeature.INSTALL)
        assert "ẩn" in st.attributes["release_summary"]


async def test_loi_adb_thanh_ket_qua_co_thong_diep_va_khong_nem():
    dev = FakeDev()
    dev.fail = "adbd của loa không trả lời"
    kq = await BoCai(dev).cai(doc_bo_cai()[0])
    assert not kq.ok and "Lỗi ADB" in kq.thong_bao and "adbd của loa" in kq.thong_bao


async def test_trang_thai_chua_cai_giong_ban_di_kem_va_khac_ban_di_kem():
    ds = {u.id: u for u in doc_bo_cai()}
    md5_player = hashlib.md5(ghep_va_kiem(ds["player"])).hexdigest()
    dev = FakeDev(cai_san={"com.phicomm.speaker.player": ("/data/app/p-1/base.apk", md5_player, "0.2.5"),
                           "vn.r1.bodam": ("/data/app/b-1/base.apk", "0" * 32, "1.1")})
    bo = BoCai(dev)
    tp = await bo.trang_thai(ds["player"], moi=True)
    assert (tp.cai, tp.phien_ban, tp.giong_di_kem) == (True, "0.2.5", True)
    tb = await bo.trang_thai(ds["bodam"], moi=True)
    assert (tb.cai, tb.phien_ban, tb.giong_di_kem) == (True, "1.1", False)
    tu = await bo.trang_thai(ds["unisound"], moi=True)
    assert (tu.cai, tu.phien_ban) == (False, None)
    n = len(dev.cmds)
    await bo.trang_thai(ds["player"])                                      # trong 30 giây: dùng bộ nhớ, không gọi lại
    assert len(dev.cmds) == n


#: Đầu ra THẬT của `dumpsys package com.phicomm.speaker.device | busybox grep -E ...` trên loa R1 (24/10/2026): gói hệ thống
#: bị ẩn, có bản cập nhật trong /data đè lên bản gốc trong /system.
DUMP_THAT_AN = """  Package [com.phicomm.speaker.device] (e068c0c):
    codePath=/data/app/com.phicomm.speaker.device-1
    versionName=V3.2.5.2-
    User 0:  installed=true hidden=true stopped=false notLaunched=false enabled=0
Hidden system packages:
  Package [com.phicomm.speaker.device] (259fc5b):
    codePath=/system/app/Unisound
    versionName=V3.1.6.2-pandora_v3_rk_phicomm_hotfix
    User 0:  installed=true hidden=false stopped=false notLaunched=false enabled=0
"""


def test_phan_tich_goi_doc_ban_dang_hieu_luc_va_co_an_tu_dau_ra_that():
    assert cu.phan_tich_goi(DUMP_THAT_AN, "com.phicomm.speaker.device") == (
        True, True, "V3.2.5.2-", "/data/app/com.phicomm.speaker.device-1")          # KHÔNG lấy V3.1.6.2 của bản gốc
    thuong = DUMP_THAT_AN.replace("hidden=true", "hidden=false")
    assert cu.phan_tich_goi(thuong, "com.phicomm.speaker.device")[:2] == (True, False)
    assert cu.phan_tich_goi("", "com.phicomm.speaker.device") == (False, False, None, None)      # không có bản ghi: chưa cài
    assert cu.phan_tich_goi(DUMP_THAT_AN, "vn.r1.bodam")[0] is False                              # bản ghi của gói khác không tính
    go_giu_du_lieu = DUMP_THAT_AN.replace("installed=true hidden=true", "installed=false hidden=false", 1)
    assert cu.phan_tich_goi(go_giu_du_lieu, "com.phicomm.speaker.device")[0] is False              # gỡ nhưng giữ dữ liệu


async def test_goi_bi_an_van_la_da_cai_du_pm_path_rong():
    ds = {u.id: u for u in doc_bo_cai()}
    dev = FakeDev(cai_san={"com.phicomm.speaker.device": ("", "", "V3.2.5.2-", True)})
    tt = await BoCai(dev).trang_thai(ds["unisound"], moi=True)
    assert (tt.cai, tt.an, tt.phien_ban, tt.giong_di_kem) == (True, True, "V3.2.5.2-", None)
    assert tt.duong_dan == "/data/app/com.phicomm.speaker.device-1"


# ── Tích hợp HA: thực thể Cập nhật và dịch vụ ─────────────────────────

@pytest.fixture
async def ha_cai(hass, r1):
    e = await _them(hass, r1)
    bo = e.runtime_data.apps
    bo.dev = FakeDev()
    bo._cau_hinh = lambda: None
    await hass.async_block_till_done()
    return e, bo, bo.dev


def _ud_ids(hass):
    return sorted(s.entity_id for s in hass.states.async_all("update") if "ung_dung" in s.entity_id)


async def test_moi_ung_dung_co_mot_thuc_the_cap_nhat_va_cai_bang_nut(hass, ha_cai):
    e, bo, dev = ha_cai
    ids = _ud_ids(hass)
    assert len(ids) == 3, ids
    pl = next(i for i in ids if "apk_mic" in i)
    from homeassistant.helpers.entity_component import async_update_entity
    await async_update_entity(hass, pl)
    st = hass.states.get(pl)
    assert st.attributes["installed_version"] == "chưa cài" and st.attributes["latest_version"] == "1.3"
    assert st.state == "on" and st.attributes["title"].startswith("APK mic")
    await hass.services.async_call("update", "install", {"entity_id": pl}, blocking=True)
    assert any(c.startswith("pm install -r") and "r1-bodam" in c for c in dev.cmds)
    dev.cai_san["vn.r1.bodam"] = ("/data/app/p-1/base.apk",
                                                 hashlib.md5(ghep_va_kiem(bo.tim("bodam"))).hexdigest(), "1.3")
    bo._nho.clear()                                                          # bỏ bộ nhớ 30 giây của lần đọc trước
    await async_update_entity(hass, pl)
    assert hass.states.get(pl).state == "off"                              # đã cài đúng bản đi kèm: hết «có cập nhật»
    with pytest.raises(HomeAssistantError, match="No update available"):    # HA chặn nút khi đã đúng bản: cài lại dùng install_apps
        await hass.services.async_call("update", "install", {"entity_id": pl}, blocking=True)
    dev.pm = "INSTALL_FAILED_X"
    dev.cai_san.clear()                                                      # loa lại «chưa cài»: nút cài hiện, cài hỏng thì báo lỗi
    bo._nho.clear()
    await async_update_entity(hass, pl)
    with pytest.raises(HomeAssistantError, match="INSTALL_FAILED_X"):
        await hass.services.async_call("update", "install", {"entity_id": pl}, blocking=True)


async def test_thuc_the_goi_bi_an_khong_moi_cap_nhat_va_noi_ro_dang_an(hass, ha_cai):
    e, bo, dev = ha_cai
    dev.cai_san["com.phicomm.speaker.device"] = ("", "", "V3.2.5.2-", True)
    uni = next(i for i in _ud_ids(hass) if "unisound" in i)
    from homeassistant.helpers.entity_component import async_update_entity
    await async_update_entity(hass, uni)
    st = hass.states.get(uni)
    assert st.attributes["installed_version"] == "V3.2.5.2- (đang ẩn)" and st.state == "off"      # không «Có bản cập nhật»
    assert st.attributes["an"] is True and st.attributes["ban_di_kem"] == "V3.2.5.2-"


async def test_dich_vu_install_apps_tra_ket_qua_tung_ung_dung(hass, ha_cai):
    e, bo, dev = ha_cai
    r = await hass.services.async_call("r1_speaker", "install_apps", {
        "entity_id": "sensor.r1_cai_dat", "apps": ["bodam", "player"]}, blocking=True, return_response=True)
    assert [(k["id"], k["ok"]) for k in r["ket_qua"]] == [("player", True), ("bodam", True), ("chuan_bi", True)]
    dev.fail = "ADB hỏng"
    with pytest.raises(HomeAssistantError, match="Không cài được"):
        await hass.services.async_call("r1_speaker", "install_apps", {"entity_id": "sensor.r1_cai_dat"}, blocking=True)
    import voluptuous as vol
    with pytest.raises(vol.Invalid):
        await hass.services.async_call("r1_speaker", "install_apps", {"entity_id": "sensor.r1_cai_dat", "apps": ["x"]},
                                       blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("r1_speaker", "install_apps", {"entity_id": "sensor.khong_phai"}, blocking=True)


async def test_nut_khoi_dong_lai_loa_goi_adb_reboot_adb_hong_thi_qua_cong_8080_ca_hai_hong_thi_bao_ca_hai_loi(hass, ha_cai, r1):
    e, bo, dev = ha_cai
    goi = []

    async def reboot():
        goi.append(1)
        if dev.fail:
            raise AdbError(dev.fail)

    dev.reboot = reboot
    nut = [s.entity_id for s in hass.states.async_all("button") if "khoi_dong_lai" in s.entity_id]
    assert nut == ["button.r1_khoi_dong_lai"] and hass.states.get(nut[0]).attributes["device_class"] == "restart"
    await hass.services.async_call("button", "press", {"entity_id": nut[0]}, blocking=True)
    assert goi == [1] and r1.commands("shell") == []                    # ADB chạy được: không đụng cổng 8080
    dev.fail = "adbd của loa không trả lời"
    await hass.services.async_call("button", "press", {"entity_id": nut[0]}, blocking=True)
    assert goi == [1, 1]
    (shell,) = r1.commands("shell")                                      # đúng khung đã thử trên loa thật, không kèm "data"
    assert shell == {"type": "shell", "type_id": "ha", "shell": "stop adbd&&start adbd&&adb reboot"}
    await r1.stop()
    with pytest.raises(HomeAssistantError, match=r"ADB: adbd của loa không trả lời; cổng 8080: "):
        await hass.services.async_call("button", "press", {"entity_id": nut[0]}, blocking=True)


async def test_nut_dong_adb_goi_dong_adb_mang_bao_thanh_cong_bang_thong_bao_va_loi_ro(hass, ha_cai):
    """Nút «Đóng ADB mạng»: thành công thì có thông báo nói rõ cách mở lại; thất bại thì báo lỗi, KHÔNG có thông báo «đã đóng»."""
    e, bo, dev = ha_cai
    goi = []

    async def dong_adb_mang():
        goi.append(1)
        if dev.fail:
            raise AdbError(dev.fail)

    dev.dong_adb_mang = dong_adb_mang
    nut = [s.entity_id for s in hass.states.async_all("button") if "dong_adb" in s.entity_id]
    assert nut == ["button.r1_dong_adb"]
    await hass.services.async_call("button", "press", {"entity_id": nut[0]}, blocking=True)
    assert goi == [1]
    tb = [n for n in hass.data.get("persistent_notification", {}).values() if "đóng ADB" in (n.get("title") or "")]
    assert tb and "rút điện" in tb[0]["message"]
    hass.data["persistent_notification"].clear()
    dev.fail = "adbd vẫn còn nghe cổng mạng"
    with pytest.raises(HomeAssistantError, match="Chưa đóng được ADB mạng"):
        await hass.services.async_call("button", "press", {"entity_id": nut[0]}, blocking=True)
    assert not any("đóng ADB" in (n.get("title") or "") for n in hass.data.get("persistent_notification", {}).values())


async def test_loi_o_buoc_pm_install_thi_thong_bao_neu_dung_buoc_va_lenh(caplog):
    """Lỗi thật 24/10/2026: thông báo chỉ có «loa từ chối dịch vụ shell», không biết bước nào, lệnh nào."""
    dev = FakeDev()
    goc = dev.shell

    async def shell(cmd, **kw):
        if cmd.startswith("pm install"):
            raise AdbError("adbd của loa từ chối ngay dịch vụ «shell:pm install -r x»")
        return await goc(cmd, **kw)

    dev.shell = shell
    with caplog.at_level("WARNING"):
        kq = await BoCai(dev).cai(doc_bo_cai()[0])
    assert not kq.ok and "Lỗi ADB khi chạy «pm install -r /data/local/tmp/r1-" in kq.thong_bao and "từ chối" in kq.thong_bao
    assert any("các bước đã xong" in r.message and "đã đẩy lên loa" in r.message for r in caplog.records if r.levelname == "WARNING")


async def test_loi_o_buoc_day_tep_noi_ro_dang_day_tep():
    dev = FakeDev()

    async def push(data, remote, mode=0o755):
        raise AdbError("kết nối TCP tới loa bị đóng khi mở «sync:»")

    dev.push = push
    kq = await BoCai(dev).cai(doc_bo_cai()[0])
    assert not kq.ok and "Lỗi ADB khi đẩy tệp lên loa" in kq.thong_bao and "sync:" in kq.thong_bao


async def test_nut_va_dich_vu_chuan_bi_loa(hass, ha_cai):
    e, bo, dev = ha_cai
    eid = next(i for i in hass.states.async_entity_ids("button") if "chuan_bi" in i)
    await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)
    assert sum(1 for c in dev.cmds if c.startswith("pm hide")) == 7 and sum(1 for c in dev.cmds if c.startswith("pm unhide")) == 2
    goi = []

    async def reboot():
        goi.append(1)

    dev.reboot = reboot
    r = await hass.services.async_call("r1_speaker", "prepare_speaker", {"entity_id": "sensor.r1_cai_dat", "reboot": True},
                                       blocking=True, return_response=True)
    assert r["da_khoi_dong_lai"] is True and goi == [1] and len(r["buoc"]) == 14
    dev.fail = "ADB hỏng"
    with pytest.raises(HomeAssistantError, match="Lỗi ADB khi chuẩn bị loa"):
        await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)


async def test_bodam_khac_chu_ky_tu_go_ban_cu_nhu_bo_cai_r1_con_unisound_van_can_cho_phep():
    dev = FakeDev(khac_chu_ky=True)
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai(bo.tim("bodam"))                                             # KHÔNG truyền go_ban_cu
    assert kq.ok and [c.split()[1] for c in dev.cmds if c.startswith("pm") and "bodam" in c or c.startswith("pm install")] == ["install", "uninstall", "install"]
    dev2 = FakeDev(khac_chu_ky=True)
    kq2 = await BoCai(dev2, cau_hinh_bodam=lambda: None).cai(bo.tim("unisound"))   # ứng dụng hệ thống của hãng: vẫn phải được phép mới gỡ
    assert not kq2.ok and not any(c.startswith("pm uninstall") for c in dev2.cmds)


async def test_cai_ghi_de_len_loa_da_cai_va_da_an_device_hien_lai_roi_cai_roi_an_lai():
    """Người cài bằng bản tích hợp cũ (hoặc đã chạy Bo Cai R1) có gói device đang ẨN: cài ghi đè phải hiện lại trước khi cài, rồi ẩn lại."""
    dev = FakeDev(cai_san={"com.phicomm.speaker.device": ("", "", "V3.2.5.2-", True)})
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai(bo.tim("unisound"))
    assert kq.ok
    thu_tu = [c for c in dev.cmds if "com.phicomm.speaker.device" in c or c.startswith("pm install")]
    assert thu_tu[0] == "pm unhide com.phicomm.speaker.device" and thu_tu[1].startswith("pm install -r") and thu_tu[2] == "pm hide com.phicomm.speaker.device"


async def test_cong_dieu_khien_im_lang_lau_thi_hien_muc_sua_chua_va_tu_het_khi_loa_tra_loi(hass, ha_cai):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.r1_speaker.client import R1Error, R1State
    from custom_components.r1_speaker.coordinator import LAN_HONG_DE_BAO
    from homeassistant.helpers.update_coordinator import UpdateFailed
    e, bo, dev = ha_cai
    co = e.runtime_data
    goc = co.client.async_fetch
    iid = f"cong_dieu_khien_{e.entry_id}"

    async def hong():
        raise R1Error("8080 im lặng")

    co.client.async_fetch = hong
    co._lan_hong = 0
    for _ in range(LAN_HONG_DE_BAO - 1):
        with pytest.raises(UpdateFailed):
            await co._async_update_data()
    assert ir.async_get(hass).async_get_issue("r1_speaker", iid) is None                 # chưa đủ lâu: loa khởi động lại không báo
    with pytest.raises(UpdateFailed):
        await co._async_update_data()
    assert ir.async_get(hass).async_get_issue("r1_speaker", iid) is not None
    co.client.async_fetch = goc
    await co._async_update_data()
    assert ir.async_get(hass).async_get_issue("r1_speaker", iid) is None and co._lan_hong == 0


async def test_go_roi_cai_lai_thu_tu_hien_go_cai_an_va_bo_qua_loi_go():
    dev = FakeDev(cai_san={"com.phicomm.speaker.device": ("", "", "V3.2.5.2-", True)})
    bo = BoCai(dev, cau_hinh_bodam=lambda: None)
    kq = await bo.cai(bo.tim("unisound"), go_truoc=True)
    assert kq.ok
    pm = [c for c in dev.cmds if c.startswith("pm ")]
    assert [c.split()[1] for c in pm] == ["unhide", "uninstall", "install", "hide"]
    kq2 = await bo.cai(bo.tim("bodam"), go_truoc=True)                          # bodam: gỡ rồi cài (không có unhide/hide)
    assert kq2.ok and [c.split()[1] for c in dev.cmds if c.startswith("pm ") and ("bodam" in c or "r1-bodam" in c)][-2:] == ["uninstall", "install"]
    r = await bo.cai_nhieu(["player"], go_truoc=True, chuan_bi=False)
    assert r[0].ok and any(c == "pm uninstall com.phicomm.speaker.player" for c in dev.cmds)


async def test_cau_hinh_bodam_bat_tro_nang_phim_giu_dich_vu_khac_va_khong_lap():
    """Cấu hình APK lần đầu bật dịch vụ trợ năng nhận phím; có dịch vụ trợ năng khác thì nối thêm; đã bật sẵn thì không đụng lại."""
    bo, _ = _bo(FakeDev())
    dev = bo.dev
    kq = await bo.cau_hinh_lai()
    assert "đã bật trợ năng nhận phím" in kq
    assert "settings put secure enabled_accessibility_services vn.r1.bodam/vn.r1.bodam.TiepCanPhim" in dev.cmds
    assert "settings put secure accessibility_enabled 1" in dev.cmds

    goc = dev.shell

    async def shell(cmd, **kw):
        if cmd == "settings get secure enabled_accessibility_services":
            return "com.khac/com.khac.DichVu\n"
        return await goc(cmd, **kw)
    dev.shell = shell
    dev.cmds.clear()
    await bo._bat_tro_nang_phim()
    assert "settings put secure enabled_accessibility_services com.khac/com.khac.DichVu:vn.r1.bodam/vn.r1.bodam.TiepCanPhim" in dev.cmds

    async def shell2(cmd, **kw):
        if cmd == "settings get secure enabled_accessibility_services":
            return "vn.r1.bodam/vn.r1.bodam.TiepCanPhim\n"
        return await goc(cmd, **kw)
    dev.shell = shell2
    dev.cmds.clear()
    assert "đã bật sẵn" in await bo._bat_tro_nang_phim()
    assert not any(c.startswith("settings put") for c in dev.cmds)

    async def shell3(cmd, **kw):
        if cmd == "settings get secure enabled_accessibility_services":
            return "x; reboot\n"                                            # chuỗi lạ đọc từ loa: không được đưa lại vào shell
        return await goc(cmd, **kw)
    dev.shell = shell3
    dev.cmds.clear()
    assert "bỏ qua" in await bo._bat_tro_nang_phim()
    assert not any(c.startswith("settings put") for c in dev.cmds)
