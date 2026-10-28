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
    assert 'customElements.define("r1-talk-card"' in js and "customCards.push" not in js   # chỉ r1-card khai báo vào bộ chọn thẻ
    assert TALK_CARD_URL == "/r1_speaker/r1-talk-card.js"
    assert "innerHTML" in js and "esc(" in js                    # dữ liệu ngoài đều qua esc()
    # Thẻ chỉ gọi dịch vụ HA, không đụng loa. Ngoại lệ DUY NHẤT: mic điện thoại mở một WebSocket về chính HA
    # (cùng nguồn gốc, đường dẫn do HA ký ``auth/sign_path``), không bao giờ tới địa chỉ nào khác.
    for cam in ("fetch(", "XMLHttpRequest", "ws://", "http://", "192.168"):
        assert cam not in js, cam
    assert js.count("new WebSocket(") == 2                          # mic điện thoại + kênh nghe, cùng một dạng địa chỉ
    assert js.count('new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + r.path)') == 2
    assert '"auth/sign_path"' in js and "/api/r1_speaker/dam_thoai/" in js and "/api/r1_speaker/nghe/" in js


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
add("media_player.r1_loa","speaker","playing",{media_title:"<img src=x onerror=alert(1)>",supported_features:8,is_volume_muted:false});
add("switch.r1_tat_mic","mute","off");
let loi=null; try{ card.hass=mk(); }catch(e){ loi=String(e); }
const sr=card.shadowRoot, q=s=>sr.querySelector(s);
const nghe={mic:q("[data-mic-text]").textContent, status:q("[data-mic]").dataset.status,
 holdDisabled:q("[data-hold]").disabled, alwaysDisabled:q("[data-always]").disabled,
 ppDisabled:q("[data-pp]").disabled, ppIcon:q("[data-pp] ha-icon").getAttribute("icon"),
 noTalkButton:!q("[data-talk]") && !q("[data-end]"), tipLoa:q("[data-mic-tip]").textContent};
states["sensor.r1_trang_thai_mic"]={state:"nghe",attributes:{phien:null,che_do_tu_danh_thuc:"ha"}}; card.hass=mk();   // chế độ HA dò từ đánh thức
nghe.tipHa=q("[data-mic-tip]").textContent;
states["sensor.r1_trang_thai_mic"]={state:"nghe",attributes:{phien:null,che_do_tu_danh_thuc:"speaker",phia_loa:"da_ket_noi",so_lan_tu_choi:0}}; card.hass=mk();
q("[data-pp]").click();                                             // đang phát: nút chính là Tạm dừng (nút mic điện thoại có test riêng)
// 3) Đang có phiên, mic đang gửi.
states["sensor.r1_trang_thai_mic"]={state:"gui",attributes:{phien:"button",so_lan_tu_choi:1,tu_choi_gan_nhat:"x"}};
states["media_player.r1_loa"]={state:"paused",attributes:{}};
card.hass=mk();
const gui={mic:q("[data-mic-text]").textContent, status:q("[data-mic]").dataset.status,
 holdDisabled:q("[data-hold]").disabled, alwaysDisabled:q("[data-always]").disabled,
 holdTitle:q("[data-hold]").title, refused:q("[data-refused]").style.display!=="none",
 ppDisabled:q("[data-pp]").disabled, ppIcon:q("[data-pp] ha-icon").getAttribute("icon")};
q("[data-pp]").click();                                             // đang tạm dừng: nút chính là Phát
// 4) Trạng thái mic không đọc được: KHÔNG hiện như «Tắt».
states["sensor.r1_trang_thai_mic"]={state:"unavailable",attributes:{}}; card.hass=mk();
const lạ={mic:q("[data-mic-text]").textContent, status:q("[data-mic]").dataset.status};
// 5) Loa im: thẻ nói VÌ SAO (hết bài / đã dừng / lỗi) thay vì chỉ «không có nhạc»; đang phát thì hiện thời lượng.
states["media_player.r1_loa"]={state:"idle",attributes:{idle_reason:"finished"}}; card.hass=mk();
const tx=()=>({t:q("[data-music-text]").textContent, tip:q("[data-music-text]").title});
const het=tx();
states["media_player.r1_loa"]={state:"idle",attributes:{idle_reason:"error"}}; card.hass=mk();
const hong=tx();
states["media_player.r1_loa"]={state:"playing",attributes:{media_title:"A",media_duration:185}}; card.hass=mk();
const dai=tx();
states["media_player.r1_loa"]={state:"idle",attributes:{}}; card.hass=mk();
const rong=tx();
// 7) Nút Dừng (media_stop) và «Tắt tiếng loa» (volume_mute) cho loa R1.
states["media_player.r1_loa"]={state:"playing",attributes:{media_title:"A",supported_features:8,is_volume_muted:false}}; card.hass=mk();
const ap=()=>q("[data-spk-mute]").getAttribute("aria-pressed")==="true";
const stop={disabled:q("[data-stop]").disabled, hang:q("[data-spk-mute]").style.display!=="none", bat:ap()};
const a0=calls.length; q("[data-stop]").click(); q("[data-spk-mute]").click();
stop.goi=JSON.stringify(calls.slice(a0)); calls.length=a0;
states["media_player.r1_loa"]={state:"idle",attributes:{supported_features:8,is_volume_muted:true}}; card.hass=mk();
stop.dungKhiIdle=q("[data-stop]").disabled; stop.tat=ap(); stop.icon=q("[data-spk-mute] ha-icon").getAttribute("icon");
states["media_player.r1_loa"]={state:"playing",attributes:{supported_features:0}}; card.hass=mk();
stop.anKhiKhongHoTro=q("[data-spk-mute]").style.display==="none";
setTimeout(()=>{document.getElementById("out").textContent=JSON.stringify({truoc,loi,nghe,gui,la:lạ,calls,het,hong,dai,rong,stop,
 eq:!!q("[data-eq] r1-eq-card"), xss:sr.innerHTML.includes("<img src=x"), title:q("[data-music-text]").textContent});},150);
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
    nghe = {k: v for k, v in r["nghe"].items() if k not in ("tipLoa", "tipHa")}
    assert nghe == {"mic": "Đang nghe", "status": "listening", "holdDisabled": False,
                         "alwaysDisabled": False, "ppDisabled": False, "ppIcon": "mdi:pause",
                         "noTalkButton": True}                  # không còn nút «Đàm thoại» / «Kết thúc»
    assert "chưa gửi tiếng nào" in r["nghe"]["tipLoa"]           # từ đánh thức trên loa: đúng là chưa gửi
    assert "LIÊN TỤC" in r["nghe"]["tipHa"] and "dò từ đánh thức" in r["nghe"]["tipHa"]   # chế độ HA: luồng chảy liên tục
    assert r["gui"]["mic"] == "Đang gửi" and r["gui"]["status"] == "sending"
    assert r["gui"]["holdDisabled"] is True and r["gui"]["alwaysDisabled"] is True
    assert r["gui"]["holdTitle"] == "Đang có phiên" and r["gui"]["refused"]
    assert r["gui"]["ppDisabled"] is False and r["gui"]["ppIcon"] == "mdi:play"      # một nút, đổi biểu tượng như thẻ YouTube
    assert r["la"] == {"mic": "Không rõ", "status": "unknown"}   # không đọc được ≠ «Tắt»
    # Mic đi bằng ĐIỆN THOẠI (WebSocket) nên bấm «Giữ để nói»/«Bật mic luôn» không còn gọi dịch vụ đàm thoại của HA;
    # chỉ nút nhạc gọi dịch vụ. Khi có phiên Assist chiếm chỗ thì các nút mic không làm gì.
    assert r["calls"] == [["media_player", "media_pause", {"entity_id": "media_player.r1_loa"}],
                          ["media_player", "media_play", {"entity_id": "media_player.r1_loa"}]]
    assert r["eq"] is True and r["xss"] is False                # nhúng thẻ EQ; tên bài không thành HTML
    # Chữ hiện chỉ là tên bài (hoặc «Lỗi phát»); lý do loa im và thời lượng (185 giây = 3:05) nằm ở dấu chỉ khi rê chuột
    assert r["het"] == {"t": "", "tip": "Bài vừa rồi đã hết bài"} and r["hong"]["t"] == "Lỗi phát" and "lỗi phát" in r["hong"]["tip"]
    assert r["dai"] == {"t": "A", "tip": "Đang phát (3:05)"} and r["rong"] == {"t": "", "tip": "Không có nhạc đang phát"}
    sp = r["stop"]
    assert sp["disabled"] is False and sp["hang"] is True and sp["bat"] is False
    assert json.loads(sp["goi"]) == [["media_player", "media_stop", {"entity_id": "media_player.r1_loa"}],
                                     ["media_player", "volume_mute", {"entity_id": "media_player.r1_loa", "is_volume_muted": True}]]
    assert sp["dungKhiIdle"] is True and sp["tat"] is True and sp["icon"] == "mdi:volume-off" and sp["anKhiKhongHoTro"] is True


def _chay_chrome_den_khi_xong(page, thoi_gian=40):
    """Chrome THẬT (mic giả) mở trang, chờ tới khi ``#out`` khác «CHUA CHAY». Mic giả mở bất đồng bộ trong thời
    gian thật nên ``--dump-dom --virtual-time-budget`` không chờ được: dùng giao thức điều khiển từ xa."""
    import asyncio
    import socket
    import time
    import urllib.request

    import aiohttp

    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        cong = sk.getsockname()[1]
    tmp = page.parent / "hoso"
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
         "--autoplay-policy=no-user-gesture-required", f"--remote-debugging-port={cong}",
         f"--user-data-dir={tmp}", f"file://{page}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        han = time.time() + 15
        while time.time() < han and ws_url is None:
            try:
                ds = json.load(urllib.request.urlopen(f"http://127.0.0.1:{cong}/json", timeout=1))
                ws_url = next((d["webSocketDebuggerUrl"] for d in ds if d.get("type") == "page"), None)
            except OSError:
                time.sleep(0.2)
        assert ws_url, "Chrome không mở cổng điều khiển"

        async def doc():
            async with aiohttp.ClientSession() as ss, ss.ws_connect(ws_url) as ws:
                for i in range(int(thoi_gian / 0.25)):
                    await ws.send_json({"id": i + 1, "method": "Runtime.evaluate", "params": {
                        "expression": "document.getElementById('out') && document.getElementById('out').textContent"}})
                    while True:
                        r = await ws.receive_json()
                        if r.get("id") == i + 1:
                            break
                    v = r.get("result", {}).get("result", {}).get("value")
                    if v and v != "CHUA CHAY":
                        return v
                    await asyncio.sleep(0.25)
            return "CHUA CHAY"

        return asyncio.run(doc())
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


PAGE_DT = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@EQ@"></script><script src="file://@CARD@"></script>
<script>(async () => {
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const choDen = async (dk) => { for (let i = 0; i < 400 && !dk(); i++) await sleep(50); };   // mic giả mở bất đồng bộ thật
const entities = {}, states = {};
const add = (id, tk, state, attrs) => { entities[id] = {platform: "r1_speaker", translation_key: tk, device_id: "d1"}; states[id] = {state, attributes: attrs || {}}; };
add("switch.r1_dam_thoai", "intercom_open", "off", {giu_mo: false, huong: null});
add("switch.r1_mic_loa_song_song", "song_song", "on");
add("sensor.r1_trang_thai_mic", "mic_status", "nghe", {phien: null});
const wsList = [], callws = [], calls = []; let moTre = 20, trongCuChi = false; const acTao = [];
window.WebSocket = class { constructor(url) { this.url = url; this.readyState = 0; this.sent = []; wsList.push(this);
  setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, moTre); }
  send(d) { this.sent.push(d); } close() { this.readyState = 3; this.closed = true; } };
let gmCalls = 0; const gm0 = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia = (c) => { gmCalls++; return gm0(c); };
const AC0 = window.AudioContext;
window.AudioContext = class extends AC0 { constructor(o) { super(o); acTao.push({trongCuChi, rate: o && o.sampleRate}); } };
const hass = {entities, states, language: "vi", callService: (d, s, x) => { calls.push([d, s, x]); return Promise.resolve(); },
  callWS: (m) => { callws.push(m); return Promise.resolve({path: m.path + "?authSig=x"}); }};
const tao = () => { const c = document.createElement("r1-talk-card"); document.body.appendChild(c); c.setConfig({show_eq: false}); c.hass = hass; return c; };
const pe = (t) => new PointerEvent(t, {pointerId: 3, bubbles: true, cancelable: true});
const nhiPhan = (w) => w.sent.filter((x) => typeof x !== "string").length;
const chuoi = (w) => w.sent.filter((x) => typeof x === "string");
const kq = {secure: window.isSecureContext};
let card = tao(); let sr = card.shadowRoot, q = (s) => sr.querySelector(s);
const h = q("[data-hold]");
kq.dau = {bat: q("[data-dt-bat]").textContent, callWS: callws.length, hold: h.textContent, gain: q("[data-gain-val]").textContent,
  note: q("[data-ss-note]").textContent, ssBat: q("[data-song-song]").checked};
// A) «Bật đàm thoại» một mình: mở kênh NGHE loa, KHÔNG xin mic, KHÔNG gửi tiếng
trongCuChi = true; q("[data-dt-bat]").click(); trongCuChi = false;
await choDen(() => wsList.length > 0 && wsList[0].readyState === 1); await sleep(300);
const w0 = wsList[0];
kq.chiNghe = {acTrongCuChi: acTao.map((a) => [a.trongCuChi, a.rate]), xinMic: gmCalls, tiengDi: nhiPhan(w0), chuoi: chuoi(w0),
  nut: q("[data-dt-bat]").textContent, trangThai: q("[data-dt-status]").textContent,
  sign: callws.map((m) => [m.type, m.path])};
// hướng từ HA hiển thị theo thuộc tính của công tắc
states["switch.r1_dam_thoai"] = {state: "on", attributes: {giu_mo: false, huong: "dien_thoai"}}; card.hass = {...hass, states: {...states}};
kq.huongDienThoai = q("[data-dt-status]").textContent;
states["switch.r1_dam_thoai"] = {state: "on", attributes: {giu_mo: false, huong: "song_song"}}; card.hass = {...hass, states: {...states}};
kq.huongSongSong = q("[data-dt-status]").textContent;
// B) Giữ để nói khi kênh đã mở: xin mic LẦN ĐẦU, báo «noi», gửi tiếng, thả thì «het»
h.dispatchEvent(pe("pointerdown")); await choDen(() => nhiPhan(w0) > 0);
kq.giu = {khoa: h.disabled, chu: h.textContent, mau: h.classList.contains("noi"), xinMic: gmCalls, chuoi: chuoi(w0), kieu: Object.prototype.toString.call(w0.sent.find((x) => typeof x !== "string"))};
card.hass = {...hass, states: {...states}};                         // HA đổi trạng thái giữa chừng: nút không bị khoá/dựng lại
kq.sauDoiTrangThai = {khoa: q("[data-hold]").disabled, giong: q("[data-hold]") === h};
h.dispatchEvent(pe("pointerleave")); await sleep(300); const n1 = nhiPhan(w0); await sleep(400); kq.vanNoiKhiRaNgoai = nhiPhan(w0) > n1;
h.dispatchEvent(pe("pointerup")); await sleep(300);
kq.sauTha = {chuoi: chuoi(w0), chu: h.textContent}; const n2 = nhiPhan(w0); await sleep(600); kq.imSauTha = nhiPhan(w0) === n2;
// C) giữ lần hai (mic đã có, không xin lại), pointercancel = thả
h.dispatchEvent(pe("pointerdown")); await choDen(() => nhiPhan(w0) > n2);
kq.lanHai = {xinMic: gmCalls, chuoi: chuoi(w0).join(","), kenh: wsList.length};
h.dispatchEvent(pe("pointercancel")); await sleep(300); kq.sauCancel = chuoi(w0).join(",");
// D) «Bật mic luôn»: VOX (không gửi «noi»), bấm lần nữa thì dừng
const al = q("[data-always]"); const n3 = nhiPhan(w0); const c3 = chuoi(w0).length;
al.click(); await choDen(() => nhiPhan(w0) > n3 + 1);
kq.luon = {chu: q("[data-always]").textContent, dang: nhiPhan(w0) > n3 + 1, chuoiThem: chuoi(w0).slice(c3)};
q("[data-always]").click(); await sleep(300); const n4 = nhiPhan(w0); await sleep(600);
kq.luonTat = {im: nhiPhan(w0) === n4, chu: q("[data-always]").textContent};
// E) công tắc «Song song» gọi dịch vụ công tắc của HA
const ss = q("[data-song-song]"); ss.checked = false; ss.dispatchEvent(new Event("change"));
kq.songSong = calls.filter((c) => c[2].entity_id === "switch.r1_mic_loa_song_song");
// F) âm lượng nghe: nhãn thời gian thực, nhớ lại, áp vào GainNode
const gs = q("[data-nghe-gain]"); gs.value = "500"; gs.dispatchEvent(new Event("input"));
kq.gain = {nhan: q("[data-gain-val]").textContent, nho: localStorage.getItem("r1_nghe_gain"), node: card._dt && card._dt.gain && card._dt.gain.gain.value};
// G) tắt đàm thoại bằng chính nút bật
q("[data-dt-bat]").click(); await sleep(200);
kq.tat = {ws: !!w0.closed, nut: q("[data-dt-bat]").textContent};
card.remove();
// H) Nhấn rồi thả TRƯỚC khi kênh sẵn sàng: mic không được đi
moTre = 1500; card = tao(); sr = card.shadowRoot; q = (s) => sr.querySelector(s);
const hb = q("[data-hold]"); hb.dispatchEvent(pe("pointerdown")); await sleep(100); hb.dispatchEvent(pe("pointerup"));
await choDen(() => wsList.length > 1 && wsList[1].readyState === 1); await sleep(800);
kq.thaTruocKhiSan = {khongGui: nhiPhan(wsList[1]) === 0, chuoi: chuoi(wsList[1])};
// I) Ẩn tab: đóng hẳn
Object.defineProperty(document, "visibilityState", {value: "hidden", configurable: true});
document.dispatchEvent(new Event("visibilitychange")); await sleep(200);
kq.anTab = {wsDong: !!wsList[1].closed, nut: q("[data-dt-bat]").textContent};
Object.defineProperty(document, "visibilityState", {value: "visible", configurable: true});
card.remove();
// J) Không có ngữ cảnh an toàn (http): vẫn NGHE được; mic thì báo https và không xin
Object.defineProperty(window, "isSecureContext", {value: false, configurable: true});
const gm1 = gmCalls; card = tao(); sr = card.shadowRoot; q = (s) => sr.querySelector(s);
q("[data-dt-bat]").click(); await choDen(() => wsList.length > 2 && wsList[2].readyState === 1);
const hh = q("[data-hold]"); hh.dispatchEvent(pe("pointerdown")); await sleep(300); hh.dispatchEvent(pe("pointerup"));
kq.http = {kenhNgheMo: wsList.length > 2, loi: q("[data-dt-err]").textContent, xinMic: gmCalls - gm1, dichVu: calls.filter((c) => c[1] !== "turn_off" && c[1] !== "turn_on").length};
document.getElementById("out").textContent = JSON.stringify(kq);
})();</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_dam_thoai_bat_nghe_giu_noi_mic_luon_song_song_va_gain(tmp_path):
    """«Bật đàm thoại» mở kênh nghe loa (không xin mic); giữ để nói = mic điện thoại (báo «noi»/«het»); bật mic luôn = VOX;
    công tắc Song song; âm lượng nghe có nhãn thời gian thực. Lỗi cũ «nhấn vào mất luôn» cũng được giữ chặt ở đây."""
    page = tmp_path / "dt.html"
    page.write_text(PAGE_DT.replace("@EQ@", str(EQ)).replace("@CARD@", str(CARD)), encoding="utf-8")
    r = json.loads(_chay_chrome_den_khi_xong(page))
    d = r["dau"]
    assert d["bat"] == "📞 Bật đàm thoại" and d["callWS"] == 0 and d["hold"] == "Giữ để nói"   # chưa bấm: chưa nối gì
    assert d["gain"] == "300%" and "Song song" in d["note"] and d["ssBat"] is True
    c = r["chiNghe"]
    assert c["acTrongCuChi"] == [[True, 16000]]                           # AudioContext tạo NGAY trong cử chỉ bấm
    assert c["xinMic"] == 0 and c["tiengDi"] == 0 and c["chuoi"] == []    # chỉ NGHE: không xin mic, không gửi gì
    assert c["nut"] == "Tắt đàm thoại" and "Đang nghe loa" in c["trangThai"] and "Assist tạm nghỉ" in c["trangThai"]
    assert c["sign"] == [["auth/sign_path", "/api/r1_speaker/dam_thoai/sensor.r1_trang_thai_mic/ws"]]
    assert "Điện thoại đang nói" in r["huongDienThoai"] and "Song song" in r["huongSongSong"]
    g = r["giu"]
    assert g["xinMic"] == 1 and g["khoa"] is False and g["mau"] is True and "Đang nói" in g["chu"]
    assert g["chuoi"] == ["noi"] and "ArrayBuffer" in g["kieu"]            # giữ nút → báo «noi» rồi gửi tiếng
    assert r["sauDoiTrangThai"] == {"khoa": False, "giong": True}          # không bị khoá/dựng lại giữa chừng
    assert r["vanNoiKhiRaNgoai"] is True                                    # kéo ngón ra ngoài nút: vẫn đang giữ
    assert r["sauTha"]["chuoi"] == ["noi", "het"] and r["sauTha"]["chu"] == "Giữ để nói" and r["imSauTha"] is True
    assert r["lanHai"]["xinMic"] == 1 and r["lanHai"]["kenh"] == 1          # mic xin MỘT lần; kênh mở sẵn thì nói liền
    assert r["sauCancel"] == "noi,het,noi,het"                              # pointercancel = thả
    assert r["luon"]["dang"] is True and r["luon"]["chu"].endswith("✓") and r["luon"]["chuoiThem"] == []   # VOX: không «noi»
    assert r["luonTat"]["im"] is True and r["luonTat"]["chu"] == "Bật mic luôn"
    assert r["songSong"] == [["switch", "turn_off", {"entity_id": "switch.r1_mic_loa_song_song"}]]
    assert r["gain"] == {"nhan": "500%", "nho": "500", "node": 5}           # nhãn thời gian thực, nhớ lại, áp vào GainNode
    assert r["tat"] == {"ws": True, "nut": "📞 Bật đàm thoại"}
    assert r["thaTruocKhiSan"]["khongGui"] is True                          # thả tay trước khi kênh sẵn sàng: không rò tiếng
    assert r["anTab"] == {"wsDong": True, "nut": "📞 Bật đàm thoại"}        # ẩn tab: đóng hẳn
    h = r["http"]
    assert h["kenhNgheMo"] is True and "https" in h["loi"] and h["xinMic"] == 0   # http: vẫn NGHE; mic báo https, không xin


PAGE_NGHE = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@EQ@"></script><script src="file://@CARD@"></script>
<script>(async () => {
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const entities = {}, states = {};
const add = (id, tk, state, attrs) => { entities[id] = {platform: "r1_speaker", translation_key: tk, device_id: "d1"}; states[id] = {state, attributes: attrs || {}}; };
add("switch.r1_dam_thoai", "intercom_open", "off", {giu_mo: false});
add("sensor.r1_trang_thai_mic", "mic_status", "nghe", {phien: null});
const wsList = [], callws = []; let gmCalls = 0;
navigator.mediaDevices.getUserMedia = () => { gmCalls++; return Promise.reject(new Error("khong duoc xin mic de nghe")); };
window.WebSocket = class { constructor(url) { this.url = url; this.readyState = 0; wsList.push(this);
  setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, 20); }
  send() {} close() { this.readyState = 3; this.closed = true; } };
const mk = (admin) => ({entities, states, language: "vi", user: {is_admin: admin}, callService: () => Promise.resolve(),
  callWS: (m) => { callws.push(m); return Promise.resolve({path: m.path + "?authSig=x"}); }});
const tao = (admin) => { const c = document.createElement("r1-talk-card"); document.body.appendChild(c); c.setConfig({show_eq: false}); c.hass = mk(admin); return c; };
const kq = {};
let card = tao(false); let q = (s) => card.shadowRoot.querySelector(s);
kq.nguoiThuong = q("[data-ng-row]").style.display;                 // KHÔNG phải quản trị: nút bị ẩn
card.remove();
card = tao(true); q = (s) => card.shadowRoot.querySelector(s);
kq.quanTri = q("[data-ng-row]").style.display; kq.dau = q("[data-nghe]").textContent;
q("[data-nghe]").click(); await sleep(300);
kq.sign = callws.map((m) => [m.type, m.path]); kq.ws = wsList.map((w) => w.url.replace(/^wss?:\/\/[^/]*/, ""));
kq.dangNghe = {chu: q("[data-ng-status]").textContent, nut: q("[data-nghe]").textContent, xinMic: gmCalls};
wsList[0].onmessage({data: new Int16Array(1600).fill(20000).buffer}); await sleep(50);   // tiếng to → thanh mức dài
kq.muc = q("[data-ng-muc]").textContent.length;
wsList[0].onmessage({data: new Int16Array(1600).fill(10).buffer}); kq.mucNho = q("[data-ng-muc]").textContent.length;
q("[data-nghe]").click(); await sleep(100);                          // bấm lần nữa: dừng
kq.dung = {ws: !!wsList[0].closed, nut: q("[data-nghe]").textContent, chu: q("[data-ng-status]").textContent};
// mic loa bị tắt giữa chừng: HA đóng 4405 → thẻ nói rõ
q("[data-nghe]").click(); await sleep(200);
wsList[1].onclose({code: 4405}); await sleep(50);
kq.micTat = {chu: q("[data-ng-status]").textContent, nut: q("[data-nghe]").textContent};
// ẩn tab: đóng hẳn
q("[data-nghe]").click(); await sleep(200);
Object.defineProperty(document, "visibilityState", {value: "hidden", configurable: true});
document.dispatchEvent(new Event("visibilitychange")); await sleep(150);
kq.anTab = {wsDong: !!wsList[2].closed, nut: q("[data-nghe]").textContent};
document.getElementById("out").textContent = JSON.stringify(kq);
})();</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_nghe_tieng_trong_nha_chi_quan_tri_khong_xin_mic_dien_thoai(tmp_path):
    page = tmp_path / "nghe.html"
    page.write_text(PAGE_NGHE.replace("@EQ@", str(EQ)).replace("@CARD@", str(CARD)), encoding="utf-8")
    r = json.loads(_chay_chrome_den_khi_xong(page))
    assert r["nguoiThuong"] == "none" and r["quanTri"] == ""            # chỉ quản trị viên thấy nút
    assert r["sign"] == [["auth/sign_path", "/api/r1_speaker/nghe/sensor.r1_trang_thai_mic/ws"]]
    assert r["ws"] == ["/api/r1_speaker/nghe/sensor.r1_trang_thai_mic/ws?authSig=x"]
    d = r["dangNghe"]
    assert "ĐANG NGHE" in d["chu"] and d["nut"] == "Dừng nghe" and d["xinMic"] == 0   # KHÔNG xin mic điện thoại
    assert r["muc"] >= 6 and r["mucNho"] <= 1                           # thanh mức tiếng phản ánh âm lượng
    assert r["dung"]["ws"] is True and "Nghe tiếng trong nhà" in r["dung"]["nut"]
    assert "không có gì để nghe" in r["micTat"]["chu"]
    assert r["anTab"]["wsDong"] is True                                 # ẩn tab: ngừng nghe
