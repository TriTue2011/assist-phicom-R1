"""NV292 — kênh đàm thoại giữa loa với loa (nửa công, qua đường bộ đàm ``intercom``).

ĐỎ-TRƯỚC-XANH: các test này đòi module ``kenh`` + nhãn người giữ phiên trong
``dam_thoai`` (phần nhãn của NV291 mà NV292 cần để câu từ chối nêu rõ ai đang giữ).
Test ở tầng quản lý kênh bằng loa giả trong bộ nhớ (không TCP, không loa thật);
đường thẻ→loa cũ được giữ nguyên bởi các test bộ đàm sẵn có (test_bo_dam.py).

Quy ước tiếng: mic loa 16 kHz → hạ tần số về 8 kHz → ``R1Intercom.feed`` (cổng
thoại + phát qua ``R1Playback``) → phát lại 16 kHz ra loa đích. Nguồn không bao
giờ nhận lại chính tiếng của mình.
"""

import array
import asyncio
import math
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.r1_speaker import const, dam_thoai
from custom_components.r1_speaker.dam_thoai import R1SessionBusy, R1Talk
from custom_components.r1_speaker.giu_nhac import MusicKeeper
from custom_components.r1_speaker.intercom import level_db
from custom_components.r1_speaker import kenh as kenh_mod
from custom_components.r1_speaker.kenh import KenhManager, nhom_kenh

from .memory_port import FakeDriver, MemorySource


# ── Loa giả ───────────────────────────────────────────────────────────────────

def pcm16(gia_tri: int, mau: int = 1024) -> bytes:
    return array.array("h", [gia_tri] * mau).tobytes()


class MicGia:
    """Mic giả: chỉ phát khúc cho listener, không TCP."""

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self._chunks: list = []
        self._states: list = []

    @property
    def available(self) -> bool:
        return self._available

    def add_chunk_listener(self, cb):
        self._chunks.append(cb)
        return lambda: self._chunks.remove(cb)

    def add_state_listener(self, cb):
        self._states.append(cb)
        return lambda: self._states.remove(cb)

    def set_available(self, value: bool) -> None:
        if value != self._available:
            self._available = value
            for cb in list(self._states):
                cb()

    def phat(self, pcm: bytes) -> None:
        for cb in list(self._chunks):
            cb(pcm)


class IntercomGia:
    """Bộ đàm giả: ghi lại tiếng được đưa vào (đã qua cổng thoại ở tầng thật)."""

    def __init__(self, configured: bool = True) -> None:
        self.playback = SimpleNamespace(configured=configured)       # đúng đường thật: R1Intercom.playback.configured
        self.nhan: list[bytes] = []
        self.dung = 0

    def feed(self, pcm: bytes) -> None:
        self.nhan.append(pcm)

    def stop_talking(self) -> None:
        self.dung += 1


class GiuGia:
    def __init__(self) -> None:
        self.nha = 0

    async def release(self) -> None:
        self.nha += 1


class NhacGia:
    def __init__(self) -> None:
        self.giu: list[GiuGia] = []

    async def hold(self) -> GiuGia:
        g = GiuGia()
        self.giu.append(g)
        return g


class TalkGia:
    """Phiên giả: chiếm chỗ đồng bộ như ``R1Talk.claim`` (không giữ nhạc)."""

    def __init__(self) -> None:
        self.session = None

    def claim(self, kind: str, nhan=None):
        if self.session is not None:
            raise R1SessionBusy(f"đang có phiên {self.session['kind']}")
        self.session = {"kind": kind, "holder": nhan}

        def nha() -> None:
            if self.session is not None and self.session["kind"] == kind:
                self.session = None

        return nha

    def tu_choi(self, kind: str, nhan=None):
        cur = self.session or {}
        giu = cur.get("holder") or "một thiết bị không xác định"
        return R1SessionBusy(f"Loa R1 đang được dùng bởi {giu} ({cur.get('kind')} — đã mở 0 giây)")


class DieuKhienGia:
    def __init__(self, mic=None, intercom=None, music=None, talk=None) -> None:
        self.mic = mic if mic is not None else MicGia()
        self.intercom = intercom if intercom is not None else IntercomGia()
        self.music = music if music is not None else NhacGia()
        self.talk = talk if talk is not None else TalkGia()


def lam_quan_ly(hass, cac_loa: dict, **kw):
    """cac_loa: {entry_id: (tieu_de, DieuKhienGia)}."""
    ten = {eid: t for eid, (t, _c) in cac_loa.items()}
    dk = {eid: c for eid, (_t, c) in cac_loa.items()}
    return KenhManager(hass, lambda eid: dk.get(eid), lambda eid: ten.get(eid, eid), **kw)


def dinh_nghia(ten_kenh: str, thanh_vien, kieu: str = "ptt"):
    return {"ten": ten_kenh, "thanh_vien": list(thanh_vien), "kieu": kieu}


async def mo_kenh(ql: KenhManager, ten_kenh: str, thanh_vien, kieu: str = "ptt"):
    ql.dinh_nghia = {ten_kenh: dinh_nghia(ten_kenh, thanh_vien, kieu)}
    await ql.async_mo(ten_kenh)
    return ql.kenh(ten_kenh)


# ── Hàm thuần ─────────────────────────────────────────────────────────────────

def test_ha_tan_so_16k_xuong_8k_lay_mau_chan():
    pcm = array.array("h", [1000, 2000, 3000, 4000]).tobytes()
    ra = kenh_mod.ha_tan_so(pcm)
    assert list(array.array("h", ra)) == [1000, 3000]


def test_bip_la_tieng_sine_khong_im():
    bip = kenh_mod.bip_pcm()
    assert len(bip) == int(0.2 * 8000) * 2
    mau = array.array("h", bip)
    assert max(abs(x) for x in mau) > 8000
    assert level_db(bip) > -45.0


def test_nhom_kenh_tu_tuy_chon_theo_ten():
    entries = [
        {"entry_id": "a", "title": "Loa 1", "options": {"kenh": "cap-1-2", "kenh_kieu": "ptt"}},
        {"entry_id": "b", "title": "Loa 2", "options": {"kenh": "cap-1-2"}},
        {"entry_id": "c", "title": "Loa 3", "options": {"kenh": "cap-3-4", "kenh_kieu": "voice"}},
        {"entry_id": "d", "title": "Loa 4", "options": {"kenh": "cap-3-4"}},
        {"entry_id": "e", "title": "Loa 5", "options": {}},
    ]
    nhom = nhom_kenh(entries)
    assert set(nhom) == {"cap-1-2", "cap-3-4"}
    assert nhom["cap-1-2"]["thanh_vien"] == ["a", "b"]
    assert nhom["cap-1-2"]["kieu"] == "ptt"
    assert nhom["cap-3-4"]["kieu"] == "voice"
    assert len(nhom["cap-3-4"]["thanh_vien"]) == 2


def test_nhom_kenh_bo_ten_rong_va_kieu_la():
    entries = [
        {"entry_id": "a", "title": "Loa 1", "options": {"kenh": "  ", "kenh_kieu": "ptt"}},
        {"entry_id": "b", "title": "Loa 2", "options": {"kenh": "nhom", "kenh_kieu": "la"}},
    ]
    # Tên trống bị bỏ; kiểu lạ không tự đổi thành kiểu khác mà bỏ cả định nghĩa.
    assert nhom_kenh(entries) == {}


# ── Nhãn người giữ phiên (phần NV291 mà NV292 cần) ────────────────────────────

def make_talk(hass, src):
    talk = R1Talk(hass, src, MusicKeeper(hass, lambda: None), const.WAKE_HA)
    talk.driver = FakeDriver()
    return talk


async def test_phien_kenh_mang_nhan_la_ten_loa_nguon_va_nguoi_khac_nghe_dung_cau(hass):
    talk = make_talk(hass, MemorySource())
    nha = talk.claim("kenh", "Loa 1")
    with pytest.raises(R1SessionBusy) as exc:
        talk.claim("button", "iPad bếp")
    assert "đang được dùng bởi Loa 1" in str(exc.value) and "iPad bếp" in str(exc.value)
    nha()
    await talk.async_settle()


# ── Mở / đóng kênh ────────────────────────────────────────────────────────────

async def test_mo_kenh_doi_it_nhat_hai_loa(hass):
    ql = lam_quan_ly(hass, {"a": ("Loa 1", DieuKhienGia())})
    ql.dinh_nghia = {"mot": dinh_nghia("mot", ["a"])}
    with pytest.raises(HomeAssistantError):
        await ql.async_mo("mot")


async def test_mo_kenh_phat_bip_cho_thanh_vien_co_kenh_phat(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    k = await mo_kenh(ql, "cap", ["a", "b"])
    assert k.mo is True
    assert a.intercom.nhan and b.intercom.nhan  # bip tới cả hai loa
    assert a.intercom.nhan[0] == kenh_mod.bip_pcm()


async def test_mo_kenh_khong_co_kenh_phat_thi_bo_bip_khong_loi(hass):
    a = DieuKhienGia(intercom=IntercomGia(configured=False))
    b = DieuKhienGia(intercom=IntercomGia(configured=False))
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    k = await mo_kenh(ql, "cap", ["a", "b"])
    assert k.mo is True
    assert a.intercom.nhan == [] and b.intercom.nhan == []


async def test_dong_kenh_dung_noi_va_nha_nhac(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    await mo_kenh(ql, "cap", ["a", "b"])
    await ql.async_noi("cap", "a")
    assert b.music.giu and b.talk.session is not None
    await ql.dong("cap")
    assert b.talk.session is None and b.music.giu[0].nha == 1
    assert ql.kenh("cap").mo is False


# ── Nói kiểu bấm-để-nói ──────────────────────────────────────────────────────

async def test_ptt_tieng_tu_nguon_toi_dich_khong_ve_nguon(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    await mo_kenh(ql, "cap", ["a", "b"])
    a.intercom.nhan.clear()
    b.intercom.nhan.clear()
    await ql.async_noi("cap", "a")
    a.mic.phat(pcm16(3000, 1024))
    assert a.intercom.nhan == []                       # nguồn không nghe lại chính mình
    assert len(b.intercom.nhan) == 1                   # đích nhận đúng một khúc đã hạ tần số
    mau = array.array("h", b.intercom.nhan[0])
    assert len(mau) == 512 and set(mau) == {3000}
    assert b.music.giu and b.talk.session["kind"] == "kenh"
    assert b.talk.session["holder"] == "Loa 1"
    await ql.dung_noi("cap", "a")
    assert b.talk.session is None and b.music.giu[0].nha == 1


async def test_ptt_nhom_ba_loa_deu_nghe(hass):
    a, b, c = DieuKhienGia(), DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b), "c": ("Loa 3", c)})
    await mo_kenh(ql, "nhom", ["a", "b", "c"])
    await ql.async_noi("nhom", "a")
    a.mic.phat(pcm16(2000, 1024))
    assert b.intercom.nhan and c.intercom.nhan
    await ql.dung_noi("nhom", "a")


async def test_chua_mo_kenh_thi_khong_noi_duoc(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    ql.dinh_nghia = {"cap": dinh_nghia("cap", ["a", "b"])}
    with pytest.raises(HomeAssistantError):
        await ql.async_noi("cap", "a")


async def test_mot_luc_chi_mot_nguoi_noi(hass):
    a, b, c = DieuKhienGia(), DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b), "c": ("Loa 3", c)})
    await mo_kenh(ql, "nhom", ["a", "b", "c"])
    await ql.async_noi("nhom", "a")
    with pytest.raises(HomeAssistantError) as exc:
        await ql.async_noi("nhom", "b")
    assert "Loa 1" in str(exc.value)
    assert ql.kenh("nhom").nguoi_noi == "a"
    await ql.dung_noi("nhom", "a")
    await ql.async_noi("nhom", "b")                     # người trước dừng thì người sau nói được
    assert ql.kenh("nhom").nguoi_noi == "b"
    await ql.dung_noi("nhom", "b")


async def test_dich_ban_thi_tu_choi_neu_ro_ai_giu_va_khong_dung_phien_cu(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    b.talk.session = {"kind": "assist", "holder": "Loa 2"}  # giả lập phiên Assist đang giữ loa đích
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    await mo_kenh(ql, "cap", ["a", "b"])
    with pytest.raises(HomeAssistantError) as exc:
        await ql.async_noi("cap", "a")
    assert "Loa 2" in str(exc.value) or "assist" in str(exc.value)
    assert b.talk.session["kind"] == "assist"           # phiên cũ còn nguyên
    assert ql.kenh("cap").nguoi_noi is None


async def test_dich_ban_bang_phien_that_thi_cau_tu_choi_dung_dang(hass):
    a = DieuKhienGia()
    talk_b = make_talk(hass, MemorySource())
    s = await asyncio.wait_for(talk_b.async_start("assist"), 2)
    b = DieuKhienGia(talk=talk_b)
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    await mo_kenh(ql, "cap", ["a", "b"])
    with pytest.raises(R1SessionBusy) as exc:
        await ql.async_noi("cap", "a")
    msg = str(exc.value)
    assert "đang được dùng bởi" in msg and "assist" in msg
    assert talk_b.session is s
    talk_b.end(s, "xong")
    await talk_b.async_settle()


async def test_mic_nguon_mat_thi_tu_dung_noi(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    await mo_kenh(ql, "cap", ["a", "b"])
    await ql.async_noi("cap", "a")
    a.mic.set_available(False)                          # luồng mic nguồn đứt
    await hass.async_block_till_done()
    assert ql.kenh("cap").nguoi_noi is None
    assert b.talk.session is None and b.music.giu[0].nha == 1


async def test_dung_kenh_khi_khong_ai_noi_khong_loi(hass):
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)})
    await mo_kenh(ql, "cap", ["a", "b"])
    await ql.dung_noi("cap", "a")                        # không ai nói: im lặng, không ném lỗi
    assert ql.kenh("cap").nguoi_noi is None


# ── Nói kiểu tự bật khi có tiếng ──────────────────────────────────────────────

async def test_voice_tieng_lon_tu_mo_noi_tieng_nho_khong(hass):
    dong_ho = [1000.0]
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)},
                     silence_s=1.5, dong_ho=lambda: dong_ho[0])
    await mo_kenh(ql, "cap", ["a", "b"], kieu="voice")
    b.intercom.nhan.clear()
    a.mic.phat(pcm16(0, 1024))                           # im lặng: không mở nói
    await hass.async_block_till_done()
    assert ql.kenh("cap").nguoi_noi is None
    a.mic.phat(pcm16(3000, 1024))                        # có tiếng: tự mở nói (khúc này mở phiên)
    await hass.async_block_till_done()
    assert ql.kenh("cap").nguoi_noi == "a"
    a.mic.phat(pcm16(3000, 1024))                        # khúc tiếp theo mới được đưa đi
    assert b.intercom.nhan
    await ql.dung_noi("cap", "a")


async def test_voice_im_du_lau_thi_nha_quyen_noi(hass):
    dong_ho = [1000.0]
    a, b = DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b)},
                     silence_s=1.5, dong_ho=lambda: dong_ho[0])
    await mo_kenh(ql, "cap", ["a", "b"], kieu="voice")
    await ql.async_noi("cap", "a")                       # mở nói trực tiếp rồi để im
    dong_ho[0] += 10.0
    a.mic.phat(pcm16(0, 1024))                           # khúc im sau hạn: quyền nói được nhả
    await hass.async_block_till_done()
    assert ql.kenh("cap").nguoi_noi is None


async def test_gioi_han_so_loa_moi_kenh(hass):
    loa = {eid: (f"Loa {i}", DieuKhienGia()) for i, eid in enumerate("abcdefg")}
    ql = lam_quan_ly(hass, loa)
    with pytest.raises(HomeAssistantError):
        ql.dinh_nghia = {"lon": dinh_nghia("lon", list(loa))}
        await ql.async_mo("lon")


async def test_loai_loa_khi_go_tich_hop(hass):
    a, b, c = DieuKhienGia(), DieuKhienGia(), DieuKhienGia()
    ql = lam_quan_ly(hass, {"a": ("Loa 1", a), "b": ("Loa 2", b), "c": ("Loa 3", c)})
    await mo_kenh(ql, "nhom", ["a", "b", "c"])
    await ql.async_noi("nhom", "a")
    ql.loai_loa("a")                                     # nguồn bị gỡ: kênh còn 2 loa, hết người nói
    assert ql.kenh("nhom").nguoi_noi is None
    ql.loai_loa("b")                                     # còn 1 loa: kênh tự đóng
    assert ql.kenh("nhom").mo is False


async def test_hop_dong_giao_dien_kenh_dung_voi_doi_tuong_that_cua_loa(hass, r1):
    """Bộ test dùng điều khiển GIẢ; ca này ghim rằng đúng các thuộc tính mà ``kenh.py`` dùng CÓ THẬT trên ``runtime_data`` của một loa thật
    (đã có lần ``intercom.configured`` không tồn tại trên lớp thật mà test giả vẫn xanh)."""
    from .test_bo_dam import _them
    e = await _them(hass, r1)
    c = e.runtime_data
    assert isinstance(c.intercom.playback.configured, bool)
    for ten in ("feed", "stop_talking"):
        assert callable(getattr(c.intercom, ten))
    for ten in ("add_chunk_listener", "add_state_listener"):
        assert callable(getattr(c.mic, ten))
    assert isinstance(c.mic.available, bool)
    for ten in ("claim", "tu_choi", "nhan_cua"):
        assert callable(getattr(c.talk, ten))
    assert c.talk.session is None and callable(c.music.hold)


async def test_hai_loa_that_mo_kenh_bang_cong_tac_va_dich_vu_noi_bao_loi_ro_khi_mic_chua_noi(hass, r1):
    """Đường THẬT (hai mục tích hợp + công tắc + dịch vụ HA, không điều khiển giả): mở kênh không lỗi dù loa chưa có kênh phát; nói khi mic nguồn
    chưa nối thì báo lỗi rõ chứ không văng AttributeError."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.exceptions import ServiceValidationError
    from .conftest import FakeR1
    from custom_components.r1_speaker.const import DOMAIN
    r2 = FakeR1()
    await r2.start()
    try:
        for f in (r1, r2):
            e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": f.port}, options={"kenh": "nha"},
                                unique_id=f"127.0.0.1:{f.port}")
            e.add_to_hass(hass)
            assert await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
        cong_tat = sorted(s.entity_id for s in hass.states.async_all("switch") if "kenh" in s.entity_id)
        assert cong_tat == ["switch.r1_kenh", "switch.r1_kenh_2"]        # loa nạp lần lượt: kênh dựng lúc mới có một loa phải cập nhật khi loa thứ hai nạp xong
        await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.r1_kenh"}, blocking=True)
        assert hass.states.get("switch.r1_kenh").state == "on" and hass.states.get("switch.r1_kenh_2").state == "on"   # đồng bộ giữa các loa cùng kênh
        with pytest.raises(ServiceValidationError, match="Mic của loa"):
            await hass.services.async_call("r1_speaker", "noi_kenh", {"kenh": "nha", "nguon": "sensor.r1_trang_thai_mic"}, blocking=True)
        await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.r1_kenh_2"}, blocking=True)
        assert hass.states.get("switch.r1_kenh").state == "off"
    finally:
        await r2.stop()
