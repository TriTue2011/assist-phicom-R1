"""Việc A: phát qua ``media_player.r1_loa`` → Set_DLNA_Open → dlna_dmr thật của HA → renderer
giả. SSDP bị chặn (không phát multicast ra LAN thật); entry dlna_dmr trỏ tay vào renderer giả."""

from unittest import mock

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import media_player as r1_mp

from .fake_dmr import UDN, FakeDMR
from .test_r1 import _them

URL = "http://stream.example/tts.mp3"


@pytest.fixture
async def dmr(r1):
    """Renderer giả, chỉ lên khi loa giả đã nhận Set_DLNA_Open(open=true)."""
    d = FakeDMR(lambda: any(m.get("open") is True for m in r1.commands("Set_DLNA_Open")))
    await d.start()
    yield d
    await d.stop()


@pytest.fixture(autouse=True)
def _khong_ssdp(hass):
    """Coi ssdp đã nạp (khỏi bind multicast) và vô hiệu đăng ký callback của dlna_dmr."""
    hass.config.components.add("ssdp")
    with mock.patch("homeassistant.components.dlna_dmr.media_player.ssdp."
                    "async_register_callback", new=mock.AsyncMock(return_value=lambda: None)):
        yield


@pytest.fixture(autouse=True)
async def _homeassistant(hass):
    """Dịch vụ homeassistant.update_entity có sẵn trong HA thật; test phải nạp nó."""
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture(autouse=True)
def _nhanh_hon():
    with mock.patch.object(r1_mp, "READY_POLL", 0.05):
        yield


async def _them_dmr(hass, dmr) -> MockConfigEntry:
    e = MockConfigEntry(
        domain="dlna_dmr", title="R1 giả", unique_id=UDN,
        data={"url": dmr.location, "device_id": UDN,
              "type": "urn:schemas-upnp-org:device:MediaRenderer:1", "mac": None},
        options={"poll_availability": True})
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


async def _phat(hass, **extra):
    await hass.services.async_call(
        "media_player", "play_media",
        {"entity_id": "media_player.r1_loa", "media_content_id": URL,
         "media_content_type": "music", **extra}, blocking=True)


async def test_ten_thuc_the_theo_mau_camera(hass, r1):
    await _them(hass, r1)
    assert hass.states.get("media_player.r1_loa") is not None
    assert hass.states.get("media_player.phicomm_r1_loa") is None


async def test_dlna_tat_bat_roi_phat(hass, r1, dmr):
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _them_dmr(hass, dmr)
    # DLNA tắt → renderer chưa lên → thực thể dlna_dmr không dùng được
    assert hass.states.get("media_player.r1_gia").state == "unavailable"

    await _phat(hass)

    assert [m["open"] for m in r1.commands("Set_DLNA_Open")] == [True]
    # đúng thứ tự: bật DLNA trước, rồi SetAVTransportURI với đúng URL, rồi Play
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL]
    assert len(dmr.called("Play")) == 1
    names = [n for n, _ in dmr.actions]
    assert names.index("SetAVTransportURI") < names.index("Play")


async def test_dlna_dang_bat_khong_gui_lai_set_dlna_open(hass, r1, dmr):
    r1.state["dlna_open"] = True
    r1.received.append({"type": "Set_DLNA_Open", "open": True})  # renderer giả coi là đã bật
    await _them(hass, r1)
    await _them_dmr(hass, dmr)
    n = len(r1.commands("Set_DLNA_Open"))
    await _phat(hass)
    assert len(r1.commands("Set_DLNA_Open")) == n
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [URL]


async def test_khong_co_dlna_dmr_bao_loi_ro(hass, r1):
    await _them(hass, r1)
    with pytest.raises(HomeAssistantError, match="dlna_dmr"):
        await _phat(hass)
    assert r1.commands("Set_DLNA_Open") == []  # chưa có đích thì không đụng DLNA của loa


async def test_dlna_khong_len_het_gio_bao_loi(hass, r1, dmr):
    r1.state["dlna_open"] = False
    dmr.enabled = lambda: False  # loa nhận lệnh bật nhưng renderer không lên
    await _them(hass, r1)
    await _them_dmr(hass, dmr)
    with mock.patch.object(r1_mp, "DLNA_READY_TIMEOUT", 0.3), \
            pytest.raises(HomeAssistantError, match="chưa sẵn sàng"):
        await _phat(hass)
    assert dmr.called("SetAVTransportURI") == []


async def test_dlna_dmr_cua_may_khac_khong_bi_chon(hass, r1, dmr):
    await _them(hass, r1)
    e = MockConfigEntry(domain="dlna_dmr", title="Khác", unique_id="uuid:khac",
                        data={"url": "http://192.0.2.99:1/desc.xml", "device_id": "uuid:khac",
                              "type": "x", "mac": None})
    e.add_to_hass(hass)
    comp = hass.states.get("media_player.r1_loa")
    assert comp is not None
    player = er.async_get(hass).async_get("media_player.r1_loa")
    assert player is not None
    with pytest.raises(HomeAssistantError, match="dlna_dmr"):
        await _phat(hass)


async def test_nhac_youtube_di_qua_dlna_cua_loa(hass, r1, dmr):
    """Nhạc YouTube: tích hợp YouTube của HA (tritue_youtube_player) gọi ``media_player.play_media``
    lên đích với ``stream_url`` http(s) và kiểu ``audio/*`` (luồng do HA ký, qua proxy của HA).
    r1_speaker không có mã YouTube nào: URL đó phải tới ``SetAVTransportURI`` của renderer, rồi
    ``Play`` — KHÔNG đi cổng 8082 (AI box đã gỡ). Không import gói YouTube vào test."""
    yt = "http://ha.example:8123/api/tritue_youtube_player/proxy/TOKEN-GIA-123"
    r1.state["dlna_open"] = False
    await _them(hass, r1)
    await _them_dmr(hass, dmr)
    await hass.services.async_call("media_player", "play_media", {
        "entity_id": "media_player.r1_loa", "media_content_id": yt,
        "media_content_type": "audio/mpeg"}, blocking=True)
    assert [d["CurrentURI"] for d in dmr.called("SetAVTransportURI")] == [yt]
    assert len(dmr.called("Play")) == 1
    assert [m["open"] for m in r1.commands("Set_DLNA_Open")] == [True]
    # Không có dịch vụ nhạc cổng 8082 nào được đăng ký (đã gỡ).
    assert not hass.services.has_service("r1_speaker", "music_play")
