"""Sink đèn thật ``AdbLights`` với thiết bị ADB giả: lệnh gửi đi, đẩy script, giữ/nhả phiên, thay hiệu ứng, lỗi."""

import asyncio

import pytest

from custom_components.r1_speaker import den_adb
from custom_components.r1_speaker.adb_client import AdbError
from custom_components.r1_speaker.den_adb import SCRIPT_LOCAL, SCRIPT_REMOTE, AdbLights
from custom_components.r1_speaker.den_port import LightsError

PHIEN_BAN = den_adb.AdbLights._phien_ban(SCRIPT_LOCAL.read_text(encoding="utf-8"))
TINH = {"co_dinh", "sang", "tat"}


class FakeStream:
    def __init__(self, service: str, tu_thoat: bool) -> None:
        self.service, self.da_dong = service, False
        self.ended = asyncio.Event()
        if tu_thoat:
            self.ended.set()

    async def read_all(self, limit: int = 0) -> bytes:
        await self.ended.wait()
        return b""

    async def close(self) -> None:
        self.da_dong = True
        self.ended.set()

    def tu_dut(self) -> None:
        self.ended.set()


class FakeDev:
    host, port, server, mode = "127.0.0.1", 5555, "", "direct"

    def __init__(self, header: str | None = None) -> None:
        self.duong = None
        self.header = f"# r1den.sh ... ({PHIEN_BAN})" if header is None else header
        self.push_log: list[tuple[str, int]] = []
        self.streams: list[FakeStream] = []
        self.fail: str | None = None

    async def shell(self, cmd: str, *, limit: int = 0) -> str:
        if self.fail:
            raise AdbError(self.fail)
        assert cmd.startswith("grep -m1 r1den-v ")
        return self.header

    async def push(self, data: bytes, remote: str, mode: int = 0o755) -> None:
        self.push_log.append((remote, len(data)))
        self.header = f"# r1den.sh ... ({PHIEN_BAN})"

    async def open(self, service: str) -> FakeStream:
        if self.fail:
            raise AdbError(self.fail)
        self.duong = "direct"
        s = FakeStream(service, tu_thoat=service.split()[3] in TINH)
        self.streams.append(s)
        return s


async def test_day_script_khi_chua_co_hoac_khac_phien_ban_va_bo_qua_khi_da_dung():
    dev = FakeDev(header="")
    sink = AdbLights(dev)
    await sink.ap_dung("day", "co_dinh", {"mau": "#0000ff", "do_sang": 60})
    assert dev.push_log == [(SCRIPT_REMOTE, len(SCRIPT_LOCAL.read_bytes()))]
    await sink.ap_dung("day", "co_dinh", {"mau": "#00ff00"})
    assert len(dev.push_log) == 1                                       # đã đúng phiên bản: không đẩy lại
    dev2 = FakeDev()
    await AdbLights(dev2).ap_dung("vien", "sang", {})
    assert dev2.push_log == []


async def test_lenh_gui_di_dung_dang_va_chi_gom_phan_da_kiem():
    dev = FakeDev()
    sink = AdbLights(dev)
    await sink.ap_dung("day", "co_dinh", {"mau": "#0000FF", "do_sang": 60, "la": "; rm -rf /"})
    await sink.ap_dung("vien", "chay_duoi", {"toc_do": 250, "chieu": "nguoc", "dai_duoi": 3, "do_sang": 80}, master=50)
    await sink.ap_dung("day", "tat", {})
    assert [s.service for s in dev.streams] == [
        f"shell:sh {SCRIPT_REMOTE} day co_dinh mau=0000ff do_sang=60",
        f"shell:sh {SCRIPT_REMOTE} vien chay_duoi do_sang=40 toc_do=250 chieu=nguoc dai_duoi=3",
        f"shell:sh {SCRIPT_REMOTE} day tat"]
    with pytest.raises(LightsError):
        await sink.ap_dung("day", "chay_duoi", {})                      # hiệu ứng của vùng khác
    with pytest.raises(LightsError):
        await sink.ap_dung("khac", "tho", {})


async def test_hieu_ung_tinh_khong_giu_phien_hieu_ung_lap_giu_den_khi_thay_hoac_dung():
    dev = FakeDev()
    sink = AdbLights(dev)
    await sink.ap_dung("day", "co_dinh", {})
    assert dev.streams[0].da_dong and not sink._streams                 # tĩnh: script tự thoát, đã nhả
    await sink.ap_dung("day", "nhip_tim", {})
    nhip = dev.streams[-1]
    assert not nhip.da_dong and sink._streams["day"] is nhip
    await sink.ap_dung("vien", "tho", {})                                # vùng kia độc lập: đáy vẫn chạy
    assert not nhip.da_dong and set(sink._streams) == {"day", "vien"}
    await sink.ap_dung("day", "chop", {})                                # thay hiệu ứng cùng vùng: mới mở trước, cũ đóng sau
    assert nhip.da_dong and not dev.streams[-1].da_dong
    await sink.dung()
    assert all(s.da_dong for s in dev.streams) and not sink._streams


async def test_phien_dut_ngoai_y_muon_bao_va_buoc_day_lai_script():
    dev = FakeDev()
    sink = AdbLights(dev)
    goi = []
    sink.khi_roi = lambda: goi.append(1)
    await sink.ap_dung("day", "tho", {})
    dev.streams[-1].tu_dut()                                             # loa khởi động lại / ADB rớt
    await asyncio.sleep(0.05)
    assert goi == [1] and sink._script_ok is False and "day" not in sink._streams
    await sink.dung()
    assert goi == [1]                                                    # đóng chủ động không phải «đứt»


async def test_loi_adb_thanh_lightserror_co_thong_diep_va_hoi_phuc():
    dev = FakeDev()
    sink = AdbLights(dev)
    dev.fail = "adbd của loa không trả lời"
    with pytest.raises(LightsError, match="adbd của loa"):
        await sink.ap_dung("day", "tho", {})
    assert sink.loi and sink.available                                   # vẫn thử lại được ở lần sau
    dev.fail = None
    await sink.ap_dung("day", "tho", {})
    assert sink.loi is None


async def test_thong_so_khong_an_toan_bi_chan_truoc_khi_vao_shell(monkeypatch):
    dev = FakeDev()
    sink = AdbLights(dev)
    monkeypatch.setattr(den_adb, "doi_so", lambda *a, **k: ["mau=ff;reboot"])
    with pytest.raises(LightsError, match="không hợp lệ"):
        await sink.ap_dung("day", "co_dinh", {})
    assert dev.streams == []
