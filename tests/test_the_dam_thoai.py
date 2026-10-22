"""Thẻ ``r1-talk-card``: được phục vụ + nạp, mô hình dữ liệu (chạy bằng Node trên trạng thái thật
của tích hợp): trạng thái mic luôn hiện, nút đàm thoại, nút nhạc. Thẻ KHÔNG gọi loa."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.helpers import entity_registry as er

from custom_components.r1_speaker.const import CARD_URL, TALK_CARD_URL

from .test_dam_thoai_ha import (INTERCOM, MICST, _cho, _nuoi_mic, _san_sang, _them,  # noqa: F401
                                _dung_nuoi, nhac)
from .test_mic import _nhanh, pcm_server, pipeline  # noqa: F401
from .memory_port import them_dmr_gia  # noqa: F401

CARD = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www" / "r1-talk-card.js"
need_node = pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy mô hình thẻ")


def test_tep_the_ton_tai_va_dang_ky_dung_ten():
    js = CARD.read_text(encoding="utf-8")
    assert 'customElements.define("r1-talk-card"' in js and "window.customCards" in js
    assert TALK_CARD_URL == "/r1_speaker/r1-talk-card.js"
    assert "innerHTML" in js and "esc(" in js                    # dữ liệu ngoài đều qua esc()
    # Thẻ chỉ gọi dịch vụ HA, không đụng loa / mạng.
    for cam in ("fetch(", "XMLHttpRequest", "WebSocket(", "ws://", "http://", "192.168"):
        assert cam not in js, cam


async def test_hai_the_duoc_nap_va_phuc_vu(hass, r1, hass_client_no_auth):
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    await _them(hass, r1)
    assert not {CARD_URL, TALK_CARD_URL} & hass.data[DATA_EXTRA_MODULE_URL]   # chỉ nạp qua tài nguyên Lovelace
    r = await (await hass_client_no_auth()).get(TALK_CARD_URL)
    assert r.status == 200 and "r1-talk-card" in await r.text()


def _hass_gia(hass, ghi_de=None):
    reg = er.async_get(hass)
    ents, states = {}, {}
    for e in reg.entities.values():
        if e.platform != "r1_speaker":
            continue
        ents[e.entity_id] = {"entity_id": e.entity_id, "platform": e.platform,
                             "translation_key": e.translation_key, "device_id": e.device_id}
        st = hass.states.get(e.entity_id)
        states[e.entity_id] = {"state": st.state, "attributes": dict(st.attributes)}
    for eid, (state, attrs) in (ghi_de or {}).items():
        states[eid] = {"state": state, "attributes": attrs}
    return {"entities": ents, "states": states, "language": "vi"}


def _mo_hinh(hass_gia, config=None):
    script = ("const c=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',"
              "()=>{const i=JSON.parse(s);console.log(JSON.stringify(c.buildModel(i.hass,i.config)))})")
    out = subprocess.run(["node", "-e", script, str(CARD)], input=json.dumps(
        {"hass": hass_gia, "config": config or {}}), capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@need_node
async def test_mo_hinh_the_trang_thai_mic_luon_hien(hass, r1, pcm_server, pipeline):
    """Bài học camera (k): thẻ không có chỉ báo mic thì người dùng không biết mic đang mở."""
    await _them(hass, r1, mic_host="127.0.0.1", mic_port=pcm_server.port)
    m = _mo_hinh(_hass_gia(hass))
    assert m["found"] and m["mic"]["present"] and m["mic"]["entity"] == MICST
    assert m["mic"]["status"] == "off"                          # chưa có luồng
    assert m["talk"]["entity"] == INTERCOM and m["talk"]["enabled"] is False
    assert m["talk"]["reason"] == "no_mic"                      # nút không bấm được: nói rõ vì sao
    # Trạng thái lạ / không đọc được KHÔNG được hiện như «tắt».
    for st in ("unavailable", "unknown", "la-hoac"):
        g = _hass_gia(hass, {MICST: (st, {})})
        assert _mo_hinh(g)["mic"]["status"] == "unknown", st
    g = _hass_gia(hass, {MICST: ("nghe", {})})
    assert _mo_hinh(g)["mic"]["status"] == "listening"
    g = _hass_gia(hass, {MICST: ("gui", {"phien": "button"}), INTERCOM: ("off", {"giu_mo": False})})
    m = _mo_hinh(g)
    assert m["mic"]["status"] == "sending" and m["mic"]["session"] == "button"
    assert m["talk"]["enabled"] is False and m["talk"]["reason"] == "busy"   # phiên Assist đang chiếm chỗ
    # Phiên là của chính đàm thoại (công tắc bật): không tính là bận; «Bật mic luôn» chỉ sáng khi giữ mở.
    g = _hass_gia(hass, {MICST: ("gui", {"phien": "song_cong"}), INTERCOM: ("on", {"giu_mo": False})})
    m = _mo_hinh(g)
    assert m["talk"]["enabled"] is True and m["intercom"]["on"] is True and m["always"]["on"] is False
    g = _hass_gia(hass, {MICST: ("gui", {"phien": "song_cong"}), INTERCOM: ("on", {"giu_mo": True})})
    assert _mo_hinh(g)["always"]["on"] is True


@need_node
async def test_mo_hinh_the_nut_dam_thoai_bam_duoc_va_nhac(hass, r1, pcm_server, pipeline, nhac):
    e = await _san_sang(hass, r1, pcm_server, pipeline)
    dmr = await nhac()
    dmr.start_music("http://nhac.example/a.mp3")
    g = _hass_gia(hass, {"media_player.r1_loa": ("playing", {"media_title": "Bài <b>A</b>"})})
    m = _mo_hinh(g)
    assert m["talk"]["enabled"] is True and m["talk"]["reason"] is None   # công tắc tắt nhưng sẵn sàng
    assert m["mic"]["status"] == "sending"
    assert m["music"]["canPause"] is True and m["music"]["canPlay"] is False
    assert m["music"]["title"] == "Bài <b>A</b>"                # thô; thẻ escape khi hiển thị
    await e.runtime_data.talk.async_start("button")
    await hass.async_block_till_done()
    m = _mo_hinh(_hass_gia(hass))
    assert m["music"]["canPause"] is False and m["music"]["canPlay"] is True   # nhạc đã tạm dừng
    assert m["mic"]["session"] == "button" and m["talk"]["enabled"] is False
    assert m["talk"]["reason"] == "busy" and m["showEq"] is True
    assert _mo_hinh(_hass_gia(hass), {"show_eq": False})["showEq"] is False
    assert _mo_hinh({"entities": {}, "states": {}})["found"] is False


# ── Giao diện thật trong Chrome không đầu (tên chứa «giao_dien» để bộ không-Chrome bỏ qua) ──

EQ = CARD.parent / "r1-eq-card.js"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
PAGE = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@EQ@"></script><script src="file://@CARD@"></script>
<script>
const entities={}, states={}, calls=[];
function add(id,tk,state,attrs){entities[id]={platform:"r1_speaker",translation_key:tk,device_id:"d1"};
 states[id]={state,attributes:attrs||{}};}
const card=document.createElement("r1-talk-card"); document.body.appendChild(card); card.setConfig({});
const mk=()=>({entities:{...entities},states:{...states},language:"vi",callService:(d,s,x)=>calls.push([d,s,x])});
// 1) HA vừa khởi động: chưa thấy thực thể nào. Thẻ phải báo rõ, KHÔNG được hỏng.
card.hass=mk();
const truoc=card.shadowRoot.textContent.includes("Không tìm thấy");
// 2) Thực thể đến muộn → thẻ dựng lại, không ném lỗi.
add("switch.r1_dam_thoai","intercom_open","off",{giu_mo:false});
add("sensor.r1_trang_thai_mic","mic_status","nghe",{phien:null,che_do_tu_danh_thuc:"speaker",phia_loa:"da_ket_noi",so_lan_tu_choi:0});
add("media_player.r1_loa","speaker","playing",{media_title:"<img src=x onerror=alert(1)>"});
add("switch.r1_tat_mic","mute","off");
let loi=null; try{ card.hass=mk(); }catch(e){ loi=String(e); }
const sr=card.shadowRoot, q=s=>sr.querySelector(s);
const nghe={mic:q("[data-mic-text]").textContent, status:q("[data-mic]").dataset.status,
 holdDisabled:q("[data-hold]").disabled, alwaysDisabled:q("[data-always]").disabled,
 pauseDisabled:q("[data-pause]").disabled, playDisabled:q("[data-play]").disabled,
 noTalkButton:!q("[data-talk]") && !q("[data-end]")};
q("[data-always]").click(); q("[data-pause]").click();             // bật mic luôn; tạm dừng nhạc
q("[data-hold]").dispatchEvent(new Event("pointerdown")); q("[data-hold]").dispatchEvent(new Event("pointerup"));
// 3) Đang có phiên, mic đang gửi.
states["sensor.r1_trang_thai_mic"]={state:"gui",attributes:{phien:"button",so_lan_tu_choi:1,tu_choi_gan_nhat:"x"}};
states["media_player.r1_loa"]={state:"paused",attributes:{}};
card.hass=mk();
const gui={mic:q("[data-mic-text]").textContent, status:q("[data-mic]").dataset.status,
 holdDisabled:q("[data-hold]").disabled, alwaysDisabled:q("[data-always]").disabled,
 holdTitle:q("[data-hold]").title, refused:q("[data-refused]").style.display!=="none",
 pauseDisabled:q("[data-pause]").disabled, playDisabled:q("[data-play]").disabled};
q("[data-always]").click(); q("[data-hold]").dispatchEvent(new Event("pointerdown")); q("[data-play]").click();
// 4) Trạng thái mic không đọc được: KHÔNG hiện như «Tắt».
states["sensor.r1_trang_thai_mic"]={state:"unavailable",attributes:{}}; card.hass=mk();
const lạ={mic:q("[data-mic-text]").textContent, status:q("[data-mic]").dataset.status};
document.getElementById("out").textContent=JSON.stringify({truoc,loi,nghe,gui,la:lạ,calls,
 eq:!!q("[data-eq] r1-eq-card"), xss:sr.innerHTML.includes("<img src=x"), title:q("[data-music-text]").textContent});
</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_dam_thoai_trang_thai_mic_nut_va_thuc_the_den_muon(tmp_path):
    page = tmp_path / "talk.html"
    page.write_text(PAGE.replace("@EQ@", str(EQ)).replace("@CARD@", str(CARD)), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=2000", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=60)
    import html
    import re
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html.unescape(m.group(1)))
    assert r["truoc"] is True and r["loi"] is None              # thực thể đến muộn không làm hỏng thẻ
    assert r["nghe"] == {"mic": "Đang nghe", "status": "listening", "holdDisabled": False,
                         "alwaysDisabled": False, "pauseDisabled": False, "playDisabled": True,
                         "noTalkButton": True}                  # không còn nút «Đàm thoại» / «Kết thúc»
    assert r["gui"]["mic"] == "Đang gửi" and r["gui"]["status"] == "sending"
    assert r["gui"]["holdDisabled"] is True and r["gui"]["alwaysDisabled"] is True
    assert r["gui"]["holdTitle"] == "Đang có phiên" and r["gui"]["refused"]
    assert r["gui"]["pauseDisabled"] is True and r["gui"]["playDisabled"] is False
    assert r["la"] == {"mic": "Không rõ", "status": "unknown"}   # không đọc được ≠ «Tắt»
    assert r["calls"] == [                                      # bấm khi đang rảnh; khi có phiên Assist thì không gọi gì
        ["switch", "turn_on", {"entity_id": "switch.r1_dam_thoai"}],
        ["media_player", "media_pause", {"entity_id": "media_player.r1_loa"}],
        ["r1_speaker", "start_duplex", {"entity_id": "sensor.r1_trang_thai_mic"}],   # giữ nút
        ["r1_speaker", "stop_duplex", {"entity_id": "sensor.r1_trang_thai_mic"}],    # thả nút
        ["media_player", "media_play", {"entity_id": "media_player.r1_loa"}]]
    assert r["eq"] is True and r["xss"] is False                # nhúng thẻ EQ; tên bài không thành HTML
