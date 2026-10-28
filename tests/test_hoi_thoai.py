"""Phòng đàm thoại nhiều loa (``hoi_thoai``): vòng đời trọn gói/rollback, loa rớt, giữ nhạc, điện thoại, và cả bộ trộn gắn với phiên song công.

Phần logic dùng loa GIẢ có tính xác định (mỗi bên nói tín hiệu hằng số, gọi thẳng ``nhip()`` không ngủ); cuối file là ca hai mục cấu hình THẬT
với máy chủ mic/phát giả ở 127.0.0.1 (tiếng đi từ mic loa A qua HA tới kênh phát loa B)."""

import array

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.r1_speaker import hoi_thoai as H
from custom_components.r1_speaker.dam_thoai import R1SessionBusy


def khung(v: int, n: int = 1) -> bytes:
    return array.array("h", [v] * 160 * n).tobytes()


def gia_tri(b: bytes) -> int:
    a = array.array("h")
    a.frombytes(b)
    assert len(a) == 160 and len(set(a)) == 1, list(a[:4])
    return a[0]


class GiuGia:
    def __init__(self, nhac):
        self.nhac, self.xong = nhac, False

    async def release(self):
        self.xong = True
        self.nhac.nha += 1


class NhacGia:
    def __init__(self):
        self.giu = self.nha = 0

    async def hold(self):
        self.giu += 1
        return GiuGia(self)


class DuplexGia:
    """Thay ``R1Duplex``: chỉ đúng phần phòng đàm thoại dùng."""

    def __init__(self, loi_mo=None):
        self.active = self.downlink_busy = False
        self.phong = None
        self.loi_mo, self.ly_do_end = loi_mo, None
        self._audio, self._doi = [], []
        self.da_phat = []                      # [(pcm, vox)]

    async def async_start(self):
        if self.loi_mo:
            raise self.loi_mo
        self.active = True

    def end(self, ly_do):
        if not self.active:
            return
        self.active, self.ly_do_end = False, ly_do
        for cb in list(self._doi):
            cb()

    def add_audio_listener(self, cb):
        self._audio.append(cb)
        return lambda: self._audio.remove(cb)

    def add_listener(self, cb):
        self._doi.append(cb)
        return lambda: self._doi.remove(cb)

    def feed_playback(self, pcm, *, vox=True):
        if not self.active:
            raise HomeAssistantError("Chưa mở phiên song công.")
        self.da_phat.append((pcm, vox))

    def dat_phong(self, p):
        self.phong = p

    def mic(self, pcm):
        for cb in list(self._audio):
            cb(pcm)


def loa(ma, **kw):
    d = DuplexGia(**kw)
    return H.LoaCuaPhong(ma, f"Loa {ma}", d, NhacGia()), d


async def mo(hass, *ds, **kw):
    hub = H.HoiThoai(hass)
    p = await hub.mo(list(ds), **kw)
    return hub, p


# ── Trộn ─────────────────────────────────────────────────────────

async def test_hai_loa_va_dien_thoai_moi_ben_nghe_dung_tong_cac_ben_khac_va_loa_nhan_tieng_khong_qua_vox(hass):
    a, da = loa("A")
    b, db = loa("B")
    hub, p = await mo(hass, a, b)
    nhan = []
    dt = p.gan_dien_thoai(nhan.append)
    da.mic(khung(1000))
    db.mic(khung(2000))
    dt.feed(khung(3000))
    p.nhip(1)
    assert da.da_phat == [(khung(2000 + 3000), False)]                    # vox=False: tiếng đã trộn không bị cổng VOX của điện thoại chặn
    assert db.da_phat == [(khung(1000 + 3000), False)]
    assert nhan == [khung(1000 + 2000)]                                   # điện thoại nghe hai loa
    p.end("xong")


async def test_giua_cac_loa_tat_thi_loa_chi_nghe_dien_thoai(hass):
    a, da = loa("A")
    b, db = loa("B")
    hub, p = await mo(hass, a, b, giua_cac_loa=False)
    nhan = []
    dt = p.gan_dien_thoai(nhan.append)
    da.mic(khung(1000))
    db.mic(khung(2000))
    dt.feed(khung(3000))
    p.nhip(1)
    assert da.da_phat == [(khung(3000), False)] and db.da_phat == [(khung(3000), False)] and nhan == [khung(3000)]
    p.end("xong")


async def test_hai_loa_khong_dien_thoai_nghe_nhau_im_lang_thi_khong_phat_gi(hass):
    a, da = loa("A")
    b, db = loa("B")
    hub, p = await mo(hass, a, b)
    da.mic(khung(1000))
    p.nhip(1)
    assert da.da_phat == [] and db.da_phat == [(khung(1000), False)]       # A nói: chỉ B nghe
    p.nhip(5)                                                              # không ai nói: không bơm gì xuống loa
    assert len(db.da_phat) == 1 and da.da_phat == []
    p.end("xong")


async def test_nhip_nhieu_buoc_gop_thanh_mot_khuc_phat(hass):
    a, da = loa("A")
    b, db = loa("B")
    hub, p = await mo(hass, a, b)
    da.mic(khung(1000, 4))
    p.nhip(3)
    assert len(db.da_phat) == 1 and len(db.da_phat[0][0]) == 3 * 320     # 3 khung 10 ms gộp một lần gọi
    p.end("xong")


# ── Vòng đời ─────────────────────────────────────────────────────

async def test_mo_tron_goi_mot_loa_ban_thi_dong_lai_cac_loa_da_mo_va_khong_giu_nhac(hass):
    a, da = loa("A")
    b, db = loa("B", loi_mo=R1SessionBusy("Assist đang giữ phiên"))
    hub = H.HoiThoai(hass)
    with pytest.raises(R1SessionBusy):
        await hub.mo([a, b])
    assert da.active is False and da.ly_do_end == "hoi_thoai_loi"          # loa A đã mở được rồi bị đóng lại
    assert da.downlink_busy is False and da.phong is None
    assert a.music.giu == 0 and hub.phong_cua("A") is None and hub._phong == {}
    # mở lại sau khi hết bận: được
    db.loi_mo = None
    p = await hub.mo([a, b])
    assert da.active and db.active
    p.end("xong")


async def test_trong_phong_loa_bi_danh_dau_ban_nhac_duoc_giu_va_dong_phong_nha_het(hass):
    a, da = loa("A")
    b, db = loa("B")
    hub, p = await mo(hass, a, b)
    assert da.downlink_busy and db.downlink_busy and da.phong is p       # các đường đàm thoại riêng của loa phải từ chối
    assert a.music.giu == 1 and b.music.giu == 1
    c, dc = loa("C")
    with pytest.raises(HomeAssistantError, match="phòng đàm thoại khác"):
        await hub.mo([c, a])                                              # loa A đã ở trong phòng
    assert dc.active is False                                             # và C không bị mở nửa chừng
    p.end("nguoi_dung_ket_thuc")
    await hass.async_block_till_done()
    assert not da.active and not db.active and da.ly_do_end == "nguoi_dung_ket_thuc"
    assert not da.downlink_busy and da.phong is None and hub._phong == {}
    assert a.music.nha == 1 and b.music.nha == 1                          # nhạc được nhả (phát lại)
    assert da._audio == [] and da._doi == []                              # không còn nghe loa nào
    p.end("lan_hai")                                                      # đóng lại lần nữa không sao


async def test_mot_loa_rot_giua_chung_thi_chi_loa_do_roi_con_du_ben_thi_phong_chay_tiep(hass):
    a, da = loa("A")
    b, db = loa("B")
    c, dc = loa("C")
    hub, p = await mo(hass, a, b, c)
    db.end("mat_ket_noi")                                                 # mic loa B đứt: phiên song công của B tự đóng
    assert p.dang and sorted(x.ma for x in p.loa) == ["A", "C"]
    dc.mic(khung(1000))
    p.nhip(1)
    assert da.da_phat == [(khung(1000), False)] and db.da_phat == []     # A vẫn nghe C; B không còn nhận gì
    dc.end("het_gio")                                                     # tới C rớt nữa: chỉ còn A, không điện thoại → phòng đóng
    assert not p.dang and p.ly_do_dong == "het_ben" and da.ly_do_end == "het_ben"
    assert hub._phong == {}
    await hass.async_block_till_done()
    assert a.music.nha == 1 and b.music.nha == 1 and c.music.nha == 1


async def test_phong_mot_loa_cung_dien_thoai_chay_cho_toi_khi_dien_thoai_ngat(hass):
    a, da = loa("A")
    hub, p = await mo(hass, a)
    nhan = []
    dt = p.gan_dien_thoai(nhan.append)
    with pytest.raises(HomeAssistantError, match="đã có một điện thoại"):
        p.gan_dien_thoai(lambda pcm: None)                                # điện thoại thứ hai bị từ chối
    da.mic(khung(1000))
    dt.feed(khung(3000) + b"\x01")                                        # độ dài lẻ: bỏ cả khúc
    p.nhip(1)
    assert nhan == [khung(1000)] and da.da_phat == []                     # không có điện thoại nói thì loa không nghe gì
    dt.feed(khung(3000))
    p.nhip(1)
    assert da.da_phat == [(khung(3000), False)]
    dt.roi()                                                              # điện thoại ngắt: còn một loa, không điện thoại → đóng
    assert not p.dang and p.ly_do_dong == "het_ben"


async def test_loa_dong_phien_giua_luc_phat_thi_roi_phong_khong_nem_loi(hass):
    a, da = loa("A")
    b, db = loa("B")
    c, dc = loa("C")
    hub, p = await mo(hass, a, b, c)
    da.mic(khung(1000))
    db.active = False                                                     # phiên B đóng mà chưa kịp báo: lần phát sau mới biết
    p.nhip(1)
    assert sorted(x.ma for x in p.loa) == ["A", "C"] and dc.da_phat == [(khung(1000), False)]
    p.end("xong")


async def test_che_do_quyen_noi_qua_hub_chi_loa_giu_quyen_duoc_nghe(hass):
    a, da = loa("A")
    b, db = loa("B")
    c, dc = loa("C")
    hub, p = await mo(hass, a, b, c, che_do="quyen_noi")
    da.mic(khung(3000))
    db.mic(khung(1000))
    p.nhip(1)
    assert db.da_phat == [(khung(3000), False)] and dc.da_phat == [(khung(3000), False)] and da.da_phat == []   # A giữ quyền: B bị bỏ
    assert p.mo_ta()["che_do"] == "quyen_noi"
    p.end("xong")
    with pytest.raises(HomeAssistantError, match="Chế độ không hợp lệ"):
        await hub.mo([a, b], che_do="xx")
    with pytest.raises(HomeAssistantError, match="trùng"):
        await hub.mo([a, a])


async def test_nhip_that_chay_nen_bang_dong_ho_va_dung_khi_dong_phong(hass):
    a, da = loa("A")
    b, db = loa("B")
    hub, p = await mo(hass, a, b)
    da.mic(khung(1000, 6))
    for _ in range(200):                                                  # nhịp 20 ms thật: đợi tối đa ~2 giây
        if len(db.da_phat) >= 1 and sum(len(x[0]) for x in db.da_phat) >= 6 * 320:
            break
        await hass.async_block_till_done()
        import asyncio
        await asyncio.sleep(0.01)
    assert sum(len(x[0]) for x in db.da_phat) == 6 * 320
    tick = p._tick
    p.end("xong")
    await hass.async_block_till_done()
    assert tick.cancelled() or tick.done()


# ── Hai mục cấu hình THẬT, mic và kênh phát giả ở 127.0.0.1 ────────

import asyncio  # noqa: E402

from homeassistant.helpers import entity_registry as er  # noqa: E402

from custom_components.r1_speaker.const import DOMAIN  # noqa: E402

from .conftest import FakeR1  # noqa: E402
from .test_mic import PcmServer  # noqa: E402
from .test_song_cong import PlayServer, _them, cho, khung10  # noqa: E402


@pytest.fixture
async def hai_loa(hass, r1):
    """Hai loa thật (mỗi loa: một FakeR1, một mic giả, một kênh phát giả) → [(mục, máy chủ phát, thực thể media_player)]."""
    r2 = FakeR1()
    await r2.start()
    mics, phats, cac = [], [], []
    try:
        for fake in (r1, r2):
            m, p = PcmServer(), PlayServer()
            await m.start()
            await p.start()
            mics.append(m)
            phats.append(p)
            e = await _them(hass, fake, mic_host="127.0.0.1", mic_port=m.port, play_port=p.port)
            reg = er.async_get(hass)
            ent = next(x.entity_id for x in reg.entities.values() if x.config_entry_id == e.entry_id and x.domain == "media_player")
            cac.append((e, p, ent))
        yield cac
    finally:
        for m, p in zip(mics, phats):
            await m.stop()
            await p.stop()
        await r2.stop()


def _tieng_loa(c, v, so_khung):
    """Tiếng mic của một loa (như APK gửi về): đi qua đúng chuỗi listener của R1Mic → phiên song công → phòng."""
    c.mic.note_inbound(True)
    c.mic.feed_inbound(khung10(v) * so_khung)


def _muc(b: bytes) -> float:
    a = array.array("h")
    a.frombytes(b[: len(b) // 2 * 2])
    return sum(abs(x) for x in a) / max(len(a), 1)


async def test_dich_vu_noi_hai_loa_that_tieng_mic_loa_a_toi_kenh_phat_loa_b_va_khong_doi_lai_a(hass, hai_loa):
    (ea, pa, ent_a), (eb, pb, ent_b) = hai_loa
    ca, cb = ea.runtime_data, eb.runtime_data
    assert hass.services.has_service(DOMAIN, "start_conference")
    await hass.services.async_call(DOMAIN, "start_conference", {"entity_ids": [ent_a, ent_b]}, blocking=True)
    assert ca.duplex.active and cb.duplex.active and ca.duplex.downlink_busy and cb.duplex.downlink_busy
    assert ca.music.holds == 1 and cb.music.holds == 1                            # nhạc của cả hai loa được giữ
    mo_ta = hass.states.get("sensor.r1_trang_thai_mic").attributes["hoi_thoai"]
    assert mo_ta["loa"] == [ea.title, eb.title] and mo_ta["che_do"] == "tron" and mo_ta["dien_thoai"] is False
    _tieng_loa(ca, 4000, 30)                                                       # loa A có người nói (0,3 giây)
    await cho(lambda: len(pb.data) >= 2 * 3200)
    assert _muc(bytes(pb.data)) > 3000                                             # loa B nhận đúng tiếng loa A (mức ~4000)
    await asyncio.sleep(0.3)
    assert len(pa.data) == 0                                                       # loa A KHÔNG nghe lại chính mình
    with pytest.raises(Exception, match="phòng đàm thoại khác|đang"):              # loa đã trong phòng: không mở phòng thứ hai
        await hass.services.async_call(DOMAIN, "start_conference", {"entity_ids": [ent_a, ent_b]}, blocking=True)
    await hass.services.async_call(DOMAIN, "stop_conference", {"entity_id": ent_b}, blocking=True)   # gọi bằng loa nào trong phòng cũng đóng cả phòng
    await hass.async_block_till_done()
    assert not ca.duplex.active and not cb.duplex.active and ca.talk.session is None and cb.talk.session is None
    assert not ca.duplex.downlink_busy and ca.music.holds == 0 and cb.music.holds == 0
    assert hass.states.get("sensor.r1_trang_thai_mic").attributes["hoi_thoai"] is None
    await hass.services.async_call(DOMAIN, "stop_conference", {"entity_id": ent_a}, blocking=True)    # không còn phòng: không lỗi


async def test_mot_loa_bi_assist_giu_thi_khong_mo_phong_va_loa_kia_khong_bi_mo_nua_chung(hass, hai_loa):
    (ea, pa, ent_a), (eb, pb, ent_b) = hai_loa
    ca, cb = ea.runtime_data, eb.runtime_data
    thua = cb.talk.claim("bo_dam")                                                 # loa B đang có phiên khác (bộ đàm)
    with pytest.raises(Exception, match="bận|đang|phiên"):
        await hass.services.async_call(DOMAIN, "start_conference", {"entity_ids": [ent_a, ent_b]}, blocking=True)
    assert not ca.duplex.active and not ca.duplex.downlink_busy and ca.talk.session is None   # A được mở rồi đóng lại sạch
    assert ca.music.holds == 0
    thua()
    await hass.services.async_call(DOMAIN, "start_conference", {"entity_ids": [ent_a, ent_b], "che_do": "quyen_noi", "giua_cac_loa": False}, blocking=True)   # hết bận: mở được
    mo_ta = hass.states.get("sensor.r1_trang_thai_mic").attributes["hoi_thoai"]
    assert mo_ta["che_do"] == "quyen_noi" and mo_ta["giua_cac_loa"] is False                  # tham số của dịch vụ tới được phòng
    await hass.services.async_call(DOMAIN, "stop_conference", {"entity_id": ent_a}, blocking=True)


async def test_ws_dien_thoai_voi_hai_loa_dien_thoai_noi_ca_hai_nghe_va_dien_thoai_nghe_mic_loa(hass, hai_loa, hass_client):
    (ea, pa, ent_a), (eb, pb, ent_b) = hai_loa
    ca, cb = ea.runtime_data, eb.runtime_data
    client = await hass_client()
    ws = await client.ws_connect(f"/api/r1_speaker/hoi_thoai/ws?e={ent_a}&e={ent_b}")
    await cho(lambda: ca.duplex.active and cb.duplex.active)
    await ws.send_str("noi")                                                       # giữ nút nói
    await ws.send_bytes(khung10(3000) * 30)                                       # điện thoại nói 0,3 giây
    await cho(lambda: len(pa.data) >= 3200 and len(pb.data) >= 3200)               # CẢ HAI loa phát tiếng điện thoại
    assert _muc(bytes(pa.data)) > 2500 and _muc(bytes(pb.data)) > 2500
    # Đang giữ nút: khung im (kể cả sau 50 khung giữ đuôi của cổng mức tiếng) vẫn tới loa, vì người dùng chủ động nói
    await cho(lambda: len(pa.data) >= 30 * 320 and len(pb.data) >= 30 * 320)       # đoạn nói to phát hết (đệm mỗi nguồn có trần 60 khung: gửi dồn sẽ bị bỏ khung cũ)
    await ws.send_bytes(khung10(20) * 60)
    await cho(lambda: len(pa.data) >= 90 * 320 and len(pb.data) >= 90 * 320)
    assert 0 < _muc(bytes(pa.data[-3200:])) < 100
    await ws.send_str("het")
    _tieng_loa(ca, 4000, 30)                                                       # loa A nói: điện thoại nghe qua WebSocket
    nhan = b""
    for _ in range(40):
        msg = await ws.receive(timeout=3)
        nhan += msg.data if msg.type.name == "BINARY" else b""
        if len(nhan) >= 3200:
            break
    assert _muc(nhan) > 3000
    assert len(pb.data) < 3200 * 200                                              # giua mặc định TẮT: loa B không nghe loa A (chỉ nghe điện thoại)
    b_nghe_a = _muc(bytes(pb.data[-6400:]))
    assert b_nghe_a < 3500, b_nghe_a                                              # (tiếng điện thoại ~3000, tiếng A ~4000: nếu trộn sẽ vượt)
    await ws.close()
    await cho(lambda: not ca.duplex.active and not cb.duplex.active)               # điện thoại ngắt thì phòng do nó mở đóng theo
    assert ca.talk.session is None and not ca.duplex.downlink_busy


async def test_ws_tu_choi_khi_tham_so_sai_loa_khong_co_hay_phong_da_co_dien_thoai(hass, hai_loa, hass_client):
    (ea, pa, ent_a), (eb, pb, ent_b) = hai_loa
    client = await hass_client()
    ws = await client.ws_connect("/api/r1_speaker/hoi_thoai/ws")                   # không nêu loa
    msg = await ws.receive(timeout=3)
    assert "Tham số" in msg.json()["loi"]
    assert (await ws.receive(timeout=3)).type.name in ("CLOSE", "CLOSING", "CLOSED") and ws.close_code == 4400
    ws = await client.ws_connect("/api/r1_speaker/hoi_thoai/ws?e=light.khong_phai_loa")
    assert "không phải thực thể" in (await ws.receive(timeout=3)).json()["loi"]
    ws1 = await client.ws_connect(f"/api/r1_speaker/hoi_thoai/ws?e={ent_a}&e={ent_b}")
    await cho(lambda: ea.runtime_data.duplex.active)
    ws2 = await client.ws_connect(f"/api/r1_speaker/hoi_thoai/ws?e={ent_a}&e={ent_b}")        # điện thoại thứ hai vào cùng bộ loa
    assert "đã có một điện thoại" in (await ws2.receive(timeout=3)).json()["loi"]
    assert ea.runtime_data.duplex.active                                           # phòng của điện thoại thứ nhất vẫn chạy
    ws3 = await client.ws_connect(f"/api/r1_speaker/hoi_thoai/ws?e={ent_a}")       # bộ loa khác (chỉ loa A) khi A đang ở phòng kia: bận
    assert "phòng đàm thoại khác" in (await ws3.receive(timeout=3)).json()["loi"]
    await ws1.close()
    await cho(lambda: not ea.runtime_data.duplex.active)
