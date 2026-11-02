"""Bộ gửi AirPlay 1 riêng (``airplay.py``) chạy với loa RAOP giả ở 127.0.0.1 (``fake_raop.py``, viết độc lập theo đặc tả).

Đồng hồ thật nhưng đoạn tiếng ngắn (≤ ~0,5 giây) và Audio-Latency giả nhỏ nên mỗi test chạy dưới vài giây."""

import array
import asyncio
import struct
import time

import pytest

from custom_components.r1_speaker import airplay as A

from .fake_raop import FakeRaop

GIAY = A.SAMPLE_RATE * A.BYTE_MAU       # byte PCM mỗi giây


def pcm_hang(v: int, so_goi: int) -> bytes:
    """PCM LE 16 bit, mọi mẫu bằng ``v``, đúng ``so_goi`` gói."""
    return array.array("h", [v] * (A.KHUNG_MOI_GOI * 2 * so_goi)).tobytes()


def nguon(*khuc: bytes, cho: float = 0.0):
    async def gen():
        for k in khuc:
            yield k
            if cho:
                await asyncio.sleep(cho)
    return gen


@pytest.fixture
async def loa():
    f = FakeRaop(do_tre=2205)
    await f.start()
    yield f
    await f.stop()


def phien(loa, tai, **kw):
    return A.PhienAirPlay("127.0.0.1", loa.port, tai, **kw)


# ── hàm thuần ────────────────────────────────────────────────────────────────

def test_am_luong_theo_thang_raop():
    assert A.tu_am_luong(0) == -144.0
    assert A.tu_am_luong(1) == 0.0
    assert A.tu_am_luong(0.5) == -15.0
    assert A.tu_am_luong(7) == 0.0 and A.tu_am_luong(-3) == -144.0


def test_goi_am_thanh_big_endian_va_marker():
    pcm = struct.pack("<hh", 0x0102, -2) + b"\x00" * (A.BYTE_MOI_GOI - 4)
    g = A.goi_am_thanh(65535, 0xFFFFFFFF, 7, pcm, True)
    assert g[:12] == bytes([0x80, 0xE0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 7])
    assert g[12:16] == bytes([0x01, 0x02, 0xFF, 0xFE])          # 0x0102 và -2 đảo sang big-endian
    assert A.goi_am_thanh(1, 1, 7, pcm, False)[1] == 0x60
    assert len(g) == 12 + A.BYTE_MOI_GOI


def test_goi_dong_bo_20_byte():
    g = A.goi_dong_bo(10_000, 2205, 1_000_000_000.5, True)
    assert len(g) == 20 and g[0] == 0x90 and g[1] == 0xD4
    assert struct.unpack(">I", g[4:8])[0] == 10_000 - 2205
    assert struct.unpack(">I", g[8:12])[0] == 1_000_000_000 + A.NTP_LECH
    assert struct.unpack(">I", g[12:16])[0] == 1 << 31             # nửa giây
    assert struct.unpack(">I", g[16:20])[0] == 10_000
    assert A.goi_dong_bo(1, 0, 0.0, False)[0] == 0x80


def test_timing_tra_loi_dung_tham_chieu():
    yc = struct.pack(">BBH4x", 0x80, 0xD2, 7) + b"\x00" * 16 + b"ABCDEFGH"
    tl = A.tra_loi_timing(yc, 5.0)
    assert len(tl) == 32 and tl[1] == 0xD3 and tl[8:16] == b"ABCDEFGH"
    assert tl[16:24] == tl[24:32]
    assert A.tra_loi_timing(b"x" * 32, 1.0) is None and A.tra_loi_timing(yc[:20], 1.0) is None


def test_doc_yeu_cau_gui_lai():
    assert A.doc_yeu_cau_gui_lai(struct.pack(">BBHHH", 0x80, 0xD5, 1, 500, 3)) == (500, 3)
    assert A.doc_yeu_cau_gui_lai(struct.pack(">BBHHH", 0x80, 0xD4, 1, 500, 3)) is None
    assert A.doc_yeu_cau_gui_lai(b"\x80\xd5") is None


# ── bắt tay ──────────────────────────────────────────────────────────────────

async def test_bat_tay_dung_thu_tu_va_sdp_pcm_khong_ma_hoa(loa):
    kq = await phien(loa, nguon(pcm_hang(5, 4))).chay()
    assert kq == "finished"
    assert loa.phuong_thuc() == ["OPTIONS", "ANNOUNCE", "SETUP", "RECORD", "TEARDOWN"]
    ann = next(r for r in loa.yeu_cau if r[1] == "ANNOUNCE")
    sdp = ann[4].decode()
    assert "a=rtpmap:96 L16/44100/2" in sdp and "m=audio 0 RTP/AVP 96" in sdp
    assert "aeskey" not in sdp and "aesiv" not in sdp and "fpaeskey" not in sdp
    assert ann[3]["content-type"] == "application/sdp" and int(ann[3]["content-length"]) == len(ann[4])
    setup = next(r for r in loa.yeu_cau if r[1] == "SETUP")
    assert "mode=record" in setup[3]["transport"] and "control_port=" in setup[3]["transport"] and "timing_port=" in setup[3]["transport"]
    rec = next(r for r in loa.yeu_cau if r[1] == "RECORD")
    assert rec[3]["session"] == "1" and rec[3]["rtp-info"].startswith("seq=") and ";rtptime=" in rec[3]["rtp-info"]
    cseq = [int(r[3]["cseq"]) for r in loa.yeu_cau]
    assert cseq == sorted(set(cseq))                                 # CSeq tăng dần, không trùng


async def test_goi_am_thanh_lien_tuc_marker_dau_va_dung_noi_dung(loa):
    ph = phien(loa, nguon(pcm_hang(0x0102, 6)))
    await ph.chay()
    g = [d for _, d, _ in loa.audio]
    assert len(g) == 6
    assert g[0][1] == 0xE0 and all(x[1] == 0x60 for x in g[1:])
    seq = [struct.unpack(">H", x[2:4])[0] for x in g]
    ts = [struct.unpack(">I", x[4:8])[0] for x in g]
    assert seq == [(seq[0] + i) & 0xFFFF for i in range(6)]
    assert ts == [(ts[0] + i * A.KHUNG_MOI_GOI) & 0xFFFFFFFF for i in range(6)]
    assert len({x[8:12] for x in g}) == 1                           # cùng SSRC
    assert all(x[12:16] == b"\x01\x02\x01\x02" for x in g) and all(len(x) == 12 + A.BYTE_MOI_GOI for x in g)
    rec = next(r for r in loa.yeu_cau if r[1] == "RECORD")
    assert rec[3]["rtp-info"] == f"seq={seq[0]};rtptime={ts[0]}"     # gói đầu khớp RTP-Info của RECORD


async def test_gui_theo_nhip_thoi_gian_thuc_khong_xa_het_mot_luc(loa):
    so_goi = 90                                                     # ~0,72 giây tiếng
    t0 = time.monotonic()
    ph = phien(loa, nguon(pcm_hang(1, so_goi)))
    await ph.chay()
    tong = time.monotonic() - t0
    gui = [t for t, _, _ in loa.audio]
    assert len(gui) == so_goi
    assert gui[-1] - gui[0] > so_goi * A.GOI_S - A.DAN_DAU - 0.1      # gói cuối không đến sớm hơn nhịp cho phép
    assert tong > so_goi * A.GOI_S                                   # còn chờ phát nốt phần đệm rồi mới TEARDOWN
    teardown = next(r[0] for r in loa.yeu_cau if r[1] == "TEARDOWN")
    assert teardown - gui[-1] >= loa.do_tre / A.SAMPLE_RATE         # đóng sau khi phần đệm phát xong


async def test_goi_dong_bo_dau_tien_truoc_goi_am_thanh_dau_va_khop_dau_thoi_gian(loa):
    ph = phien(loa, nguon(pcm_hang(1, 5)))
    await ph.chay()
    assert loa.ctrl, "không có gói đồng bộ nào"
    t, g, _ = loa.ctrl[0]
    assert g[0] == 0x90 and g[1] == 0xD4 and len(g) == 20
    assert t <= loa.audio[0][0]                                      # đồng bộ đầu đến trước âm thanh đầu
    ts0 = struct.unpack(">I", loa.audio[0][1][4:8])[0]
    assert struct.unpack(">I", g[16:20])[0] == ts0 or abs(struct.unpack(">I", g[16:20])[0] - ts0) < 100
    assert struct.unpack(">I", g[4:8])[0] == (struct.unpack(">I", g[16:20])[0] - 2205) & 0xFFFFFFFF


async def test_gui_lai_goi_khi_loa_yeu_cau(loa):
    ph = phien(loa, nguon(pcm_hang(3, 40)))
    tac_vu = asyncio.create_task(ph.chay())
    await asyncio.wait_for(ph.da_bat_dau.wait(), 3)
    await asyncio.sleep(0.15)
    seq0 = struct.unpack(">H", loa.audio[0][1][2:4])[0]
    loa.gui_yeu_cau_gui_lai(seq0 + 1, 2)
    await asyncio.sleep(0.2)
    lai = [d for _, d, _ in loa.ctrl if d[1] == 0xD6]
    assert len(lai) == 2 and ph.thong_ke["goi_gui_lai"] == 2
    goc = {struct.unpack(">H", d[2:4])[0]: d for _, d, _ in loa.audio}
    assert lai[0][4:] == goc[seq0 + 1] and lai[1][4:] == goc[seq0 + 2]
    loa.gui_yeu_cau_gui_lai(60000, 3)                                # gói không có trong bộ đệm: bỏ qua, không lỗi
    await asyncio.sleep(0.05)
    await tac_vu


async def test_tra_loi_timing_cua_loa(loa):
    ph = phien(loa, nguon(pcm_hang(1, 40)))
    tac_vu = asyncio.create_task(ph.chay())
    await asyncio.wait_for(ph.da_bat_dau.wait(), 3)
    gio = loa.gui_hoi_timing(b"12345678")
    await asyncio.sleep(0.15)
    tl = [d for _, d, _ in loa.timing if len(d) == 32 and d[1] == 0xD3]
    assert len(tl) == 1 and tl[0][8:16] == gio
    await tac_vu


async def test_am_luong_gui_sau_record_va_nho_truoc_khi_mo(loa):
    ph = phien(loa, nguon(pcm_hang(1, 30)))
    await ph.dat_am_luong(0.5)                                       # chưa mở: chỉ nhớ
    assert loa.yeu_cau == []
    tac_vu = asyncio.create_task(ph.chay())
    await asyncio.wait_for(ph.da_bat_dau.wait(), 3)
    await ph.dat_am_luong(0)
    sp = [r for r in loa.yeu_cau if r[1] == "SET_PARAMETER"]
    assert [r[4].decode().strip() for r in sp] == ["volume: -15.000000", "volume: -144.000000"]
    assert all(r[3]["content-type"] == "text/parameters" for r in sp)
    assert loa.phuong_thuc().index("SET_PARAMETER") > loa.phuong_thuc().index("RECORD")
    await tac_vu


# ── lỗi: «không bắt đầu được» phải ném LoiAirPlay, chưa đặt da_bat_dau ───────

@pytest.mark.parametrize("buoc", ["OPTIONS", "ANNOUNCE", "SETUP", "RECORD"])
async def test_loa_tu_choi_buoc_nao_cung_la_loi_airplay(buoc):
    f = FakeRaop(tra_ma={buoc: 453})
    await f.start()
    try:
        ph = phien(f, nguon(pcm_hang(1, 4)))
        with pytest.raises(A.LoiAirPlay, match=buoc):
            await ph.chay()
        assert not ph.da_bat_dau.is_set() and f.audio == []
        assert ph.trang_thai == "xong"
    finally:
        await f.stop()


async def test_khong_noi_duoc_cong():
    f = FakeRaop()
    await f.start()
    cong = f.port
    await f.stop()
    ph = A.PhienAirPlay("127.0.0.1", cong, nguon(pcm_hang(1, 2)))
    with pytest.raises(A.LoiAirPlay, match="không nối được"):
        await ph.chay()
    assert not ph.da_bat_dau.is_set()


async def test_nguon_rong_va_nguon_hong_la_loi(loa):
    ph = phien(loa, nguon())
    with pytest.raises(A.LoiAirPlay, match="không có tiếng"):
        await ph.chay()
    assert not ph.da_bat_dau.is_set()

    async def hong():
        yield pcm_hang(1, 2)
        raise RuntimeError("ffmpeg chết")

    ph2 = phien(loa, hong)
    with pytest.raises(A.LoiAirPlay, match="RuntimeError"):
        await ph2.chay()
    assert ph2.da_bat_dau.is_set()                                   # đã phát được một đoạn rồi mới hỏng


async def test_mat_ket_noi_rtsp_giua_chung_lam_hong_luot_phat(monkeypatch):
    monkeypatch.setattr(A, "GIU_KET_NOI_S", 0.05)
    f = FakeRaop(dong_sau_record=True)
    await f.start()
    try:
        ph = phien(f, nguon(pcm_hang(1, 300)))
        with pytest.raises(A.LoiAirPlay, match="mất kết nối"):
            await asyncio.wait_for(ph.chay(), 5)
    finally:
        await f.stop()


# ── dừng / tạm dừng ──────────────────────────────────────────────────────────

async def test_huy_giua_chung_van_teardown_va_dong_cong(loa):
    ph = phien(loa, nguon(pcm_hang(1, 400)))
    tac_vu = asyncio.create_task(ph.chay())
    await asyncio.wait_for(ph.da_bat_dau.wait(), 3)
    tac_vu.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tac_vu
    assert loa.phuong_thuc()[-1] == "TEARDOWN" and ph.trang_thai == "xong"
    await asyncio.sleep(0.05)                                        # gói đã gửi trước (đẩy sớm DAN_DAU giây) còn đang bay tới loa giả
    n = len(loa.audio)
    await asyncio.sleep(0.2)
    assert len(loa.audio) == n                                       # không còn gói nào sau khi huỷ


async def test_tam_dung_flush_roi_tiep_phat_lai_phan_chua_nghe(loa):
    so_goi = 100                                                     # ~0,8 giây
    ph = phien(loa, nguon(pcm_hang(2, so_goi)))
    tac_vu = asyncio.create_task(ph.chay())
    await asyncio.wait_for(ph.da_bat_dau.wait(), 3)
    await asyncio.sleep(0.2)
    await ph.tam_dung()
    assert ph.trang_thai == "tam_dung"
    fl = [r for r in loa.yeu_cau if r[1] == "FLUSH"]
    assert len(fl) == 1 and fl[0][3]["rtp-info"].startswith("seq=") and ";rtptime=" in fl[0][3]["rtp-info"]
    vt = ph.vi_tri
    n = len(loa.audio)
    await asyncio.sleep(0.3)
    assert len(loa.audio) == n and ph.vi_tri == vt                   # đứng yên: không gửi, không tính giờ
    await ph.tiep()
    assert ph.trang_thai == "phat"
    await asyncio.wait_for(tac_vu, 8)
    g = [d for _, d, _ in loa.audio]
    assert g[n][1] == 0xE0                                           # sau FLUSH, gói đầu lại có marker
    assert len(g) >= so_goi                                          # đủ cả bài
    seq = [struct.unpack(">H", x[2:4])[0] for x in g]
    assert seq == [(seq[0] + i) & 0xFFFF for i in range(len(g))]     # số thứ tự liền mạch xuyên qua lần dừng
    assert any(d[0] == 0x90 for _, d, _ in loa.ctrl[1:]) or len([1 for _, d, _ in loa.ctrl if d[0] == 0x90]) >= 2


async def test_tam_dung_khi_chua_phat_la_khong_lam_gi(loa):
    ph = phien(loa, nguon(pcm_hang(1, 4)))
    await ph.tam_dung()
    await ph.tiep()
    assert ph.trang_thai == "ket_noi" and loa.yeu_cau == []


async def test_vi_tri_tang_theo_gio_nghe_tru_do_tre_dem(loa):
    ph = phien(loa, nguon(pcm_hang(1, 200), cho=0))
    tac_vu = asyncio.create_task(ph.chay())
    await asyncio.wait_for(ph.da_bat_dau.wait(), 3)
    assert ph.vi_tri < 0.1
    await asyncio.sleep(0.3)
    assert 0.2 < ph.vi_tri < 0.4
    tac_vu.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tac_vu


async def test_tren_doi_duoc_goi_ket_noi_phat_xong(loa):
    ds = []
    ph = phien(loa, nguon(pcm_hang(1, 4)), tren_doi=ds.append)
    await ph.chay()
    assert ds == ["phat", "xong"]


async def test_ben_nghe_trang_thai_hong_khong_pha_luong_phat(loa):
    def hong(_):
        raise ValueError("x")

    ph = phien(loa, nguon(pcm_hang(1, 4)), tren_doi=hong)
    assert await ph.chay() == "finished"


# ── nguồn ffmpeg (ffmpeg giả là một script Python) ───────────────────────────

FFMPEG_GIA = '''#!{py}
import json, os, sys, time
d = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(d, "args.json"), "w").write(json.dumps(sys.argv[1:]))
open(os.path.join(d, "pid"), "w").write(str(os.getpid()))
url = sys.argv[sys.argv.index("-i") + 1]
if "treo" in url:
    time.sleep(60)
if "loi" in url:
    sys.exit(3)
sys.stdout.buffer.write(b"\\x01\\x00" * (352 * 2 * int(url.rsplit("/", 1)[-1] or 5)))
'''


@pytest.fixture
def ffmpeg_gia(tmp_path):
    import os
    import stat
    import sys
    p = tmp_path / "ffmpeg"
    p.write_text(FFMPEG_GIA.format(py=sys.executable))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def doc_args(ffmpeg_gia):
    import json
    return json.loads((ffmpeg_gia.parent / "args.json").read_text())


async def test_ffmpeg_dong_lenh_dung_va_phat_het_bai(loa, ffmpeg_gia):
    ph = phien(loa, A.tao_nguon("http://nguon.example/nhac/6", bat_dau=12.5, ffmpeg=str(ffmpeg_gia)))
    assert await ph.chay() == "finished"
    a = doc_args(ffmpeg_gia)
    assert a[a.index("-protocol_whitelist") + 1] == A.GIAO_THUC_CHO_PHEP and "file" not in A.GIAO_THUC_CHO_PHEP
    assert a.index("-protocol_whitelist") < a.index("-i") and a[a.index("-ss") + 1] == "12.500" and a.index("-ss") < a.index("-i")
    assert a[a.index("-i") + 1] == "http://nguon.example/nhac/6" and a[-1] == "-"
    assert a[a.index("-f") + 1] == "s16le" and a[a.index("-ac") + 1] == "2" and a[a.index("-ar") + 1] == "44100" and "-vn" in a
    assert "-nostdin" in a
    assert len(loa.audio) == 6                                    # 6 gói × 1408 byte đúng bằng lượng PCM script ghi ra
    assert loa.audio[0][1][12:16] == b"\x00\x01\x00\x01"          # 0x0001 little-endian → big-endian trên dây


async def test_ffmpeg_khong_dung_ss_khi_bat_dau_tu_dau(loa, ffmpeg_gia):
    await phien(loa, A.tao_nguon("http://nguon.example/nhac/2", ffmpeg=str(ffmpeg_gia))).chay()
    assert "-ss" not in doc_args(ffmpeg_gia)


async def test_ffmpeg_thoat_loi_la_loi_airplay_chua_bat_dau(loa, ffmpeg_gia):
    ph = phien(loa, A.tao_nguon("http://nguon.example/loi", ffmpeg=str(ffmpeg_gia)))
    with pytest.raises(A.LoiAirPlay, match="mã 3"):
        await ph.chay()
    assert not ph.da_bat_dau.is_set()


@pytest.mark.parametrize("url", ["file:///etc/passwd", "concat:a|b", "rtsp://x/y", "/etc/passwd", "ftp://x/y"])
async def test_ffmpeg_chi_nhan_http_va_khong_chay_gi_voi_dia_chi_khac(loa, ffmpeg_gia, url):
    ph = phien(loa, A.tao_nguon(url, ffmpeg=str(ffmpeg_gia)))
    with pytest.raises(A.LoiAirPlay, match="http"):
        await ph.chay()
    assert not (ffmpeg_gia.parent / "args.json").exists()           # ffmpeg chưa hề được chạy


async def test_khong_co_ffmpeg_la_loi_ro_rang(loa, monkeypatch):
    monkeypatch.setattr(A.shutil, "which", lambda _: None)
    with pytest.raises(A.LoiAirPlay, match="không có ffmpeg"):
        await phien(loa, A.tao_nguon("http://nguon.example/x")).chay()


async def test_huy_luot_phat_thi_ffmpeg_bi_giet(loa, ffmpeg_gia):
    import os
    ph = phien(loa, A.tao_nguon("http://nguon.example/treo", ffmpeg=str(ffmpeg_gia)))
    tac = asyncio.create_task(ph.chay())
    for _ in range(100):
        if (ffmpeg_gia.parent / "pid").exists():
            break
        await asyncio.sleep(0.05)
    pid = int((ffmpeg_gia.parent / "pid").read_text())
    tac.cancel()
    await asyncio.wait({tac}, timeout=3)
    assert tac.done(), "huỷ xong phải nhanh: ffmpeg phải bị giết chứ không chờ nó tự thoát"
    assert tac.cancelled()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)                                           # tiến trình không còn (không để ffmpeg mồ côi)
