"""Máy khách ADB: hai đường (adb-server / nối thẳng) và tự nhận diện, thử với máy chủ giả."""

import asyncio
import re
import struct

import pytest

from custom_components.r1_speaker import adb_client

from custom_components.r1_speaker.adb_client import (A_AUTH, A_CLSE, A_CNXN, A_OKAY, A_OPEN, A_WRTE, AdbDevice,
                                                     AdbError, _HDR)


async def _cong_nghe(handler):
    srv = await asyncio.start_server(handler, "127.0.0.1", 0)
    return srv, srv.sockets[0].getsockname()[1]


class FakeServer:
    """adb-server giả: ``host:connect`` rồi ``host:transport``; dịch vụ ``shell:`` và ``sync:``."""

    def __init__(self, *, da_noi: bool = True):
        self.da_noi = da_noi
        self.offline = False            # server giữ kết nối HỎNG tới loa: transport báo «device offline» tới khi ngắt rồi nối lại
        self.nhat_ky: list[str] = []
        self.lenh: list[str] = []
        self.tep: dict[str, bytes] = {}
        self.chay = lambda cmd: f"ra:{cmd}".encode()

    async def handle(self, r, w):
        try:
            while True:
                n = int(await r.readexactly(4), 16)
                req = (await r.readexactly(n)).decode()
                self.nhat_ky.append(req)
                if req.startswith("host:disconnect:"):
                    self.da_noi = False
                    w.write(b"OKAY" + b"%04x" % 12 + b"disconnected")
                    await w.drain()
                    return
                if req.startswith("host:connect:"):
                    self.da_noi, self.offline = True, False
                    w.write(b"OKAY" + b"%04x" % 12 + b"connected to")
                    await w.drain()
                    return
                if req.startswith("host:transport:"):
                    if not self.da_noi or self.offline:
                        msg = b"device offline" if self.offline else b"device not found"
                        w.write(b"FAIL" + b"%04x" % len(msg) + msg)
                        await w.drain()
                        return
                    w.write(b"OKAY")
                    continue
                self.lenh.append(req)
                w.write(b"OKAY")
                if req.startswith("shell:"):
                    w.write(self.chay(req[6:]))
                    await w.drain()
                    return
                if req == "sync:":
                    await w.drain()
                    await self._sync(r, w)
                    return
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            w.close()

    async def _sync(self, r, w):
        dang = b""
        path = ""
        while True:
            tag = await r.readexactly(4)
            (ln,) = struct.unpack("<I", await r.readexactly(4))
            if tag == b"SEND":
                path = (await r.readexactly(ln)).decode().rsplit(",", 1)[0]
            elif tag == b"DATA":
                dang += await r.readexactly(ln)
            elif tag == b"DONE":
                self.tep[path] = dang
                w.write(b"OKAY" + struct.pack("<I", 0))
                await w.drain()
                return


class FakeAdbd:
    """adbd giả giống loa thật: CHỈ MỘT kết nối TCP tại một thời điểm (kết nối thứ hai không được trả lời), nhiều luồng
    ghép trên kết nối đó. Dịch vụ: ``shell:<lệnh>`` (trả ``ra:<lệnh>`` rồi đóng), ``dai:`` (giữ mở tới khi client đóng),
    ``sync:``."""

    def __init__(self, *, auth: bool = False):
        self.auth = auth
        self.tep: dict[str, bytes] = {}
        self.lenh: list[str] = []
        self.dang_noi = 0
        self.so_ket_noi = 0
        self.dong_luong: list[str] = []

    @staticmethod
    def _gui(w, cmd, a0, a1, data=b""):
        w.write(_HDR.pack(cmd, a0, a1, len(data), sum(data) & 0xFFFFFFFF, cmd ^ 0xFFFFFFFF) + data)

    @staticmethod
    async def _nhan(r):
        cmd, a0, a1, ln, _c, _m = _HDR.unpack(await r.readexactly(_HDR.size))
        return cmd, a0, a1, (await r.readexactly(ln) if ln else b"")

    @staticmethod
    def _giai_sync(dang: bytes):
        tep, i, path, buf, xong = {}, 0, "", b"", False
        while i + 8 <= len(dang):
            tag, (ln,) = dang[i:i + 4], struct.unpack("<I", dang[i + 4:i + 8])
            if tag == b"SEND":
                path = dang[i + 8:i + 8 + ln].decode().rsplit(",", 1)[0]
                i += 8 + ln
            elif tag == b"DATA":
                buf += dang[i + 8:i + 8 + ln]
                i += 8 + ln
            elif tag == b"DONE":
                xong = True
                i += 8
            else:
                break
        return path, buf, xong

    async def handle(self, r, w):
        self.so_ket_noi += 1
        if self.dang_noi:                                # loa thật: kết nối thứ hai im lặng
            await r.read()                               # giữ tới khi client bỏ cuộc
            w.close()
            return
        self.dang_noi += 1
        luong: dict[int, dict] = {}                       # local_id của client -> trạng thái
        try:
            cmd, *_ = await self._nhan(r)
            assert cmd == A_CNXN
            if self.auth:
                self._gui(w, A_AUTH, 1, 0, b"x" * 20)
                await w.drain()
                await asyncio.sleep(0.2)
                return
            self._gui(w, A_CNXN, 0x01000000, 4096, b"device::")
            nxt = 100
            while True:
                cmd, a0, a1, d = await self._nhan(r)
                if cmd == A_OPEN:
                    nxt += 1
                    dich = d.rstrip(b"\x00").decode()
                    self.lenh.append(dich)
                    if re.match(r"shell:pm(\s|$)", dich):          # adbd của loa thật: đóng NGAY dịch vụ shell có lệnh bắt đầu bằng pm
                        self._gui(w, A_CLSE, 0, a0)
                        await w.drain()
                        continue
                    luong[a0] = {"remote": nxt, "dich": dich, "sync": b""}
                    self._gui(w, A_OKAY, nxt, a0)
                    if dich.startswith("shell:"):
                        self._gui(w, A_WRTE, nxt, a0, f"ra:{dich[6:]}".encode())
                        self._gui(w, A_CLSE, nxt, a0)
                elif cmd == A_WRTE:
                    st = luong.get(a0)
                    self._gui(w, A_OKAY, a1, a0)
                    if st and st["dich"] == "sync:":
                        st["sync"] += d
                        path, buf, xong = self._giai_sync(st["sync"])
                        if xong:
                            self.tep[path] = buf
                            self._gui(w, A_WRTE, st["remote"], a0, b"OKAY" + struct.pack("<I", 0))
                elif cmd == A_CLSE:
                    st = luong.pop(a0, None)
                    if st:
                        self.dong_luong.append(st["dich"])
                        self._gui(w, A_CLSE, st["remote"], a0)
                await w.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.dang_noi -= 1
            w.close()


@pytest.fixture(autouse=True)
def _nhanh(monkeypatch):
    monkeypatch.setattr(adb_client, "TIMEOUT_S", 1.5)
    monkeypatch.setattr(adb_client, "IDLE_S", 0.2)
    monkeypatch.setattr(adb_client, "THU_LAI_S", 0.05)


@pytest.fixture
async def may():
    """(adb-server giả, cổng server, adbd giả, cổng adbd)."""
    fs, fa = FakeServer(), FakeAdbd()
    s1, p1 = await _cong_nghe(fs.handle)
    s2, p2 = await _cong_nghe(fa.handle)
    yield fs, p1, fa, p2
    for s in (s1, s2):
        s.close()
        await s.wait_closed()


def _loa(p_adbd, p_server=None, mode="auto"):
    return AdbDevice("127.0.0.1", p_adbd, f"127.0.0.1:{p_server}" if p_server else "", mode)


async def test_qua_server_chay_lenh_va_tu_noi_lai_khi_chua_noi(may):
    fs, p1, fa, p2 = may
    fs.da_noi = False                                  # server chưa thấy loa: phải gọi host:connect rồi thử lại
    d = _loa(p2, p1, "server")
    assert await d.shell("echo hi") == "ra:echo hi"
    assert d.duong == "server" and fs.da_noi


async def test_nối_thang_chay_lenh(may):
    _fs, _p1, fa, p2 = may
    d = _loa(p2, None, "direct")
    assert await d.shell("echo hi") == "ra:echo hi"
    assert d.duong == "direct" and fa.lenh == ["shell:echo hi"]


async def test_day_tep_qua_server_va_noi_thang_nhieu_doan(may):
    fs, p1, fa, p2 = may
    lon = bytes(range(256)) * 400                      # 102400 byte: nhiều đoạn DATA và nhiều đoạn WRTE
    await _loa(p2, p1, "server").push(lon, "/data/local/tmp/a.sh")
    assert fs.tep["/data/local/tmp/a.sh"] == lon
    await _loa(p2, None, "direct").push(lon, "/data/local/tmp/b.sh")
    assert fa.tep["/data/local/tmp/b.sh"] == lon


async def test_auto_dung_server_neu_co_khong_thi_noi_thang(may):
    fs, p1, fa, p2 = may
    d = _loa(p2, p1)
    await d.shell("x")
    assert d.duong == "server"
    cong_chet = 1                                      # không ai nghe: bị từ chối ngay
    d2 = _loa(p2, cong_chet)
    assert await d2.shell("y") == "ra:y"
    assert d2.duong == "direct"


async def test_che_do_server_khong_co_server_thi_bao_loi(may):
    _fs, _p1, _fa, p2 = may
    d = _loa(p2, 1, "server")
    with pytest.raises(AdbError):
        await d.shell("x")
    assert d.duong is None


async def test_noi_thang_adbd_doi_xac_thuc_thi_bao_ro():
    fa = FakeAdbd(auth=True)
    srv, p = await _cong_nghe(fa.handle)
    try:
        with pytest.raises(AdbError, match="xác thực"):
            await _loa(p, None, "direct").shell("x")
    finally:
        srv.close()
        await srv.wait_closed()


async def test_noi_thang_ghep_nhieu_luong_tren_mot_ket_noi_va_nha_khi_het(may):
    """Đáy và viền chạy cùng lúc: hai luồng dài trên MỘT kết nối; hết luồng thì nhả kết nối cho client ADB khác."""
    _fs, _p1, fa, p2 = may
    d = _loa(p2, None, "direct")
    s1 = await d.open("dai:day")
    s2 = await d.open("dai:vien")
    assert fa.so_ket_noi == 1 and fa.dang_noi == 1
    assert await d.shell("x") == "ra:x"                  # lệnh ngắn xen giữa, vẫn một kết nối
    assert fa.so_ket_noi == 1
    await s1.close()
    assert fa.dang_noi == 1                              # còn luồng viền
    await s2.close()
    assert fa.dang_noi == 1                              # vừa hết luồng: còn giữ IDLE_S giây (lệnh sát nhau dùng lại kết nối)
    assert await d.shell("y") == "ra:y" and fa.so_ket_noi == 1   # lệnh đến trong lúc giữ: KHÔNG nối lại
    await asyncio.sleep(0.5)
    assert fa.dang_noi == 0 and sorted(fa.dong_luong)[:2] == ["dai:day", "dai:vien"]   # rảnh đủ lâu: nhả cho client khác
    assert await d.shell("z") == "ra:z" and fa.so_ket_noi == 2   # nối lại khi cần


async def test_adbd_dang_ban_voi_client_khac_thi_bao_ro(may):
    _fs, _p1, fa, p2 = may
    giu = await _loa(p2, None, "direct").open("dai:x")       # client khác đang giữ chỗ duy nhất
    try:
        with pytest.raises(AdbError, match="bận"):
            await _loa(p2, None, "direct").shell("z")
    finally:
        await giu.close()


async def test_server_giu_ket_noi_hong_thi_ngat_va_noi_lai_roi_chay_duoc(may):
    """Tình huống thật: adb-server báo «device offline» (giữ kết nối hỏng, chiếm chỗ duy nhất của adbd)."""
    fs, p1, fa, p2 = may
    fs.offline = True
    d = _loa(p2, p1, "auto")
    assert await d.shell("echo hi") == "ra:echo hi"
    assert d.duong == "server" and not fs.offline
    assert [x.split(":")[1] for x in fs.nhat_ky if x.startswith("host:") and "transport" not in x] == ["disconnect", "connect"]


async def test_reboot_gui_dich_vu_reboot_qua_ca_hai_duong(may):
    fs, p1, fa, p2 = may
    await _loa(p2, p1, "server").reboot()
    assert "reboot:" in fs.lenh
    d = _loa(p2, None, "direct")
    await d.reboot()
    assert "reboot:" in fa.lenh and d.duong is None


async def test_adbd_im_lang_luc_dau_roi_tra_loi_thi_thu_lai_dung_mot_lan(may):
    """Quan sát thật: mở kết nối NGAY sau khi đóng kết nối trước, adbd bỏ im; thử lại sau một lát thì chạy."""
    _fs, _p1, fa, p2 = may
    giu = await _loa(p2, None, "direct").open("dai:x")           # client khác đang giữ chỗ duy nhất
    d = _loa(p2, None, "direct")

    async def tha():
        await asyncio.sleep(1.0)                                  # sau khi lần bắt tay thứ nhất đã hết giờ (1,5 s: chưa) ...
        await giu.close()                                         # ... chỗ trống trước lần thử lại (khoảng 1,55 s)

    t = asyncio.create_task(tha())
    assert await d.shell("q") == "ra:q"                           # lần thử lại thành công
    await t
    assert fa.so_ket_noi >= 3


@pytest.mark.parametrize("vao,ra", [
    ("pm install -r /data/local/tmp/r1-x.apk", "/system/bin/pm install -r /data/local/tmp/r1-x.apk"),
    ("pm uninstall vn.r1.bodam", "/system/bin/pm uninstall vn.r1.bodam"),
    ("  pm path a.b", "/system/bin/pm path a.b"),
    ("pm", "/system/bin/pm"),
    ("P=$(pm path a.b 2>/dev/null); echo $P", "P=$(pm path a.b 2>/dev/null); echo $P"),   # không đứng đầu lệnh thì loa không chặn
    ("pmx --x", "pmx --x"),                                                              # không phải lệnh pm
    ("am start -n a/.b", "am start -n a/.b"),
    ("rm -f /data/local/tmp/r1-x.apk", "rm -f /data/local/tmp/r1-x.apk"),
    ("sh /data/local/tmp/r1den.sh day sang", "sh /data/local/tmp/r1den.sh day sang"),
])
def test_chuan_hoa_shell_goi_pm_bang_duong_dan_day_du(vao, ra):
    """Lỗi thật 24/10/2026: loa từ chối dịch vụ ``shell:pm …`` nên cài APK qua nối thẳng luôn hỏng sau khi đã đẩy tệp xong."""
    assert adb_client.chuan_hoa_shell(vao) == ra


async def test_nối_thang_lenh_pm_duoc_gui_bang_duong_dan_day_du(may):
    _fs, _p1, fa, p2 = may
    d = _loa(p2, None, "direct")
    assert await d.shell("pm install -r /data/local/tmp/r1-x.apk") == "ra:/system/bin/pm install -r /data/local/tmp/r1-x.apk"
    assert fa.lenh == ["shell:/system/bin/pm install -r /data/local/tmp/r1-x.apk"]


def _cong_dong():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_auto_server_vang_mat_khong_nhac_adb_server_trong_loi():
    """Máy không có adb-server (lỗi 111 chỉ là «không có»): thông báo chỉ nói về đường nối thẳng, không đẩy người dùng đi tìm adb-server."""
    d = AdbDevice("127.0.0.1", _cong_dong(), f"127.0.0.1:{_cong_dong()}", "auto")
    with pytest.raises(AdbError) as e:
        await d.shell("echo hi")
    assert "adb-server" not in str(e.value) and "nối thẳng" in str(e.value)


async def test_che_do_server_chon_tay_van_bao_loi_adb_server():
    d = AdbDevice("127.0.0.1", _cong_dong(), f"127.0.0.1:{_cong_dong()}", "server")
    with pytest.raises(AdbError) as e:
        await d.shell("echo hi")
    assert "adb-server" in str(e.value)


async def test_loa_tu_choi_thi_thong_bao_chi_ra_lenh_bi_tu_choi(may, monkeypatch):
    """Lỗi cũ chỉ nói «loa từ chối dịch vụ shell» nên phải đo cả buổi mới biết là lệnh pm; giờ thông báo nêu đúng lệnh."""
    _fs, _p1, fa, p2 = may
    monkeypatch.setattr(adb_client, "chuan_hoa_shell", lambda lenh: lenh)           # tắt chuẩn hoá để thấy lỗi thô
    d = _loa(p2, None, "direct")
    with pytest.raises(AdbError) as e:
        await d.shell("pm path vn.r1.bodam")
    assert "từ chối" in str(e.value) and "shell:pm path vn.r1.bodam" in str(e.value)


async def test_bo_loc_pm_cua_adbd_that_khong_chan_lenh_da_chuan_hoa(may):
    _fs, _p1, fa, p2 = may
    d = _loa(p2, None, "direct")
    assert (await d.shell("pm path vn.r1.bodam")).startswith("ra:/system/bin/pm path")


async def test_mo_luong_bi_tu_choi_van_nha_ket_noi_cho_client_khac(may, monkeypatch):
    """adbd của loa chỉ phục vụ MỘT kết nối: sau khi loa từ chối một dịch vụ (không còn luồng nào), kết nối phải được nhả
    (trước đây giữ mãi nên adb của người dùng không nối được)."""
    _fs, _p1, fa, p2 = may
    monkeypatch.setattr(adb_client, "chuan_hoa_shell", lambda lenh: lenh)
    d = _loa(p2, None, "direct")
    with pytest.raises(AdbError):
        await d.shell("pm path vn.r1.bodam")
    for _ in range(40):
        if fa.dang_noi == 0:
            break
        await asyncio.sleep(0.05)
    assert fa.dang_noi == 0
