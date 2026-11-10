"""``r1_speaker.play_group``: phát nhóm chỉ qua AirPlay, một bộ giải mã chia cho mọi loa, cùng một mốc bắt đầu.

Hai loa giả (``FakeR1`` + ``FakeRaop`` mỗi loa) ở 127.0.0.1; nguồn tiếng giả thay ffmpeg (``airplay.tao_nguon``)."""

import array
import asyncio
from unittest import mock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import airplay as ap_mod
from custom_components.r1_speaker.const import DOMAIN

from .conftest import FakeR1
from .fake_raop import FakeRaop

URL = "http://stream.example/bai.mp3"
LOA1, LOA2 = "media_player.r1_loa", "media_player.r1_loa_2"


def pcm(so_goi: int) -> bytes:
    return array.array("h", [1] * (ap_mod.KHUNG_MOI_GOI * 2 * so_goi)).tobytes()


@pytest.fixture
def nguon():
    goi = []

    def tao(url, bat_dau=0.0, ffmpeg=None):
        goi.append(url)

        async def gen():
            await asyncio.sleep(0.15)                       # ffmpeg khởi động chậm: khúc đầu phải sẵn khi điểm hẹn mở
            yield pcm(100)
        return gen
    with mock.patch.object(ap_mod, "tao_nguon", new=tao):
        yield goi


@pytest.fixture
async def hai_loa(hass):
    r1a, r1b, ra, rb = FakeR1(), FakeR1(), FakeRaop(do_tre=2205), FakeRaop(do_tre=2205)
    for f in (r1a, r1b, ra, rb):
        await f.start()
    r1a.state["dlna_open"] = r1b.state["dlna_open"] = False
    for r1, raop in ((r1a, ra), (r1b, rb)):
        e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": r1.port}, unique_id=f"127.0.0.1:{r1.port}",
                            options={"airplay_port": raop.port})
        e.add_to_hass(hass)
        assert await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
    yield ra, rb
    for f in (r1a, r1b, ra, rb):
        await f.stop()


async def phat_nhom(hass, ids, **kw):
    await hass.services.async_call(DOMAIN, "play_group", {"entity_id": ids, "media_content_id": URL, **kw}, blocking=True)


async def test_phat_nhom_mot_bo_giai_ma_cung_moc_bat_dau(hass, hai_loa, nguon):
    ra, rb = hai_loa
    await phat_nhom(hass, [LOA1, LOA2])
    assert nguon == [URL]                                    # MỘT lần giải mã cho cả nhóm
    assert ra.audio and rb.audio
    lech = abs(ra.audio[0][0] - rb.audio[0][0])
    assert lech < 0.05, f"gói đầu hai loa lệch {lech * 1000:.0f} ms"
    assert hass.states.get(LOA1).state == "playing" and hass.states.get(LOA2).state == "playing"
    assert hass.states.get(LOA1).attributes["duong_phat"] == hass.states.get(LOA2).attributes["duong_phat"] == "airplay"
    ga, gb = len(ra.audio), len(rb.audio)
    await asyncio.sleep(0.3)
    assert len(ra.audio) > ga and len(rb.audio) > gb         # cả hai đang nhận đều (không loa nào bị bỏ đói)


async def test_mot_loa_hong_thi_cac_loa_con_lai_van_phat_va_bao_loi_ten_loa_hong(hass, hai_loa, nguon):
    ra, rb = hai_loa
    rb.tra_ma["ANNOUNCE"] = 453                              # loa 2 từ chối bắt tay
    with pytest.raises(HomeAssistantError, match=rf"(?s)Một số loa.*{LOA2}"):
        await phat_nhom(hass, [LOA1, LOA2])
    assert ra.audio and not rb.audio                         # loa 1 không phải chờ loa hỏng mãi
    assert hass.states.get(LOA1).state == "playing"


async def test_thuc_the_la_thi_bao_loi_ro(hass, hai_loa, nguon):
    with pytest.raises(ServiceValidationError, match="media_player.khong_co"):
        await phat_nhom(hass, [LOA1, "media_player.khong_co"])
    assert nguon == []                                       # không giải mã gì khi nhóm sai


async def test_nguon_hong_thi_moi_loa_nhan_loi_khong_ai_cho_mai(hass, hai_loa):
    async def hong():
        raise ap_mod.LoiAirPlay("ffmpeg thoát mã 1 (giả)")
        yield b""
    with mock.patch.object(ap_mod, "tao_nguon", new=lambda *a, **k: hong):
        with pytest.raises(HomeAssistantError, match="Cả nhóm không phát được"):
            async with asyncio.timeout(20):
                await phat_nhom(hass, [LOA1, LOA2])
