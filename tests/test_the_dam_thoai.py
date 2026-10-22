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
    # Thẻ chỉ gọi dịch vụ HA, không đụng loa. Ngoại lệ DUY NHẤT: mic điện thoại mở một WebSocket về chính HA
    # (cùng nguồn gốc, đường dẫn do HA ký ``auth/sign_path``), không bao giờ tới địa chỉ nào khác.
    for cam in ("fetch(", "XMLHttpRequest", "ws://", "http://", "192.168"):
        assert cam not in js, cam
    assert js.count("new WebSocket(") == 1
    assert 'new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + r.path)' in js
    assert '"auth/sign_path"' in js and "/api/r1_speaker/dam_thoai/" in js


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
setTimeout(()=>{document.getElementById("out").textContent=JSON.stringify({truoc,loi,nghe,gui,la:lạ,calls,
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
    assert r["nghe"] == {"mic": "Đang nghe", "status": "listening", "holdDisabled": False,
                         "alwaysDisabled": False, "pauseDisabled": False, "playDisabled": True,
                         "noTalkButton": True}                  # không còn nút «Đàm thoại» / «Kết thúc»
    assert r["gui"]["mic"] == "Đang gửi" and r["gui"]["status"] == "sending"
    assert r["gui"]["holdDisabled"] is True and r["gui"]["alwaysDisabled"] is True
    assert r["gui"]["holdTitle"] == "Đang có phiên" and r["gui"]["refused"]
    assert r["gui"]["pauseDisabled"] is True and r["gui"]["playDisabled"] is False
    assert r["la"] == {"mic": "Không rõ", "status": "unknown"}   # không đọc được ≠ «Tắt»
    calls = r["calls"]                                          # bấm khi đang rảnh; khi có phiên Assist thì không gọi gì
    assert calls[:2] == [["switch", "turn_on", {"entity_id": "switch.r1_dam_thoai"}],
                         ["media_player", "media_pause", {"entity_id": "media_player.r1_loa"}]]
    con_lai = [c[1] for c in calls[2:]]            # giữ/thả chạy bất đồng bộ (xếp hàng) nên chen với lệnh nhạc
    assert sorted(con_lai) == ["media_play", "start_duplex", "stop_duplex"]
    assert con_lai.index("start_duplex") < con_lai.index("stop_duplex")
    assert all(c[2] == {"entity_id": "sensor.r1_trang_thai_mic"} for c in calls if c[0] == "r1_speaker")
    assert r["eq"] is True and r["xss"] is False                # nhúng thẻ EQ; tên bài không thành HTML


PAGE_GIU = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@EQ@"></script><script src="file://@CARD@"></script>
<script>(async () => {
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const entities = {}, states = {};
const add = (id, tk, state, attrs) => { entities[id] = {platform: "r1_speaker", translation_key: tk, device_id: "d1"}; states[id] = {state, attributes: attrs || {}}; };
add("switch.r1_dam_thoai", "intercom_open", "off", {giu_mo: false});
add("sensor.r1_trang_thai_mic", "mic_status", "nghe", {phien: null});
const log = []; let startXong = false;
const mk = () => ({entities: {...entities}, states: {...states}, language: "vi", callService: (d, s, x) => {
  log.push(s + (s === "stop_duplex" ? (startXong ? ":sau-start" : ":TRUOC-start") : ""));
  if (s === "start_duplex") return new Promise((r) => setTimeout(() => { startXong = true; r(); }, 120));   // dịch vụ mở phiên chậm
  return Promise.resolve(); }});
const card = document.createElement("r1-talk-card"); document.body.appendChild(card); card.setConfig({show_eq: false}); card.hass = mk();
const sr = card.shadowRoot, h = sr.querySelector("[data-hold]");
const pe = (t) => new PointerEvent(t, {pointerId: 7, bubbles: true, cancelable: true});
const kq = {touchAction: getComputedStyle(h).touchAction};
// 1) nhấn rồi thả NGAY (trước khi dịch vụ mở phiên xong): «dừng» phải chạy SAU «bắt đầu»
h.dispatchEvent(pe("pointerdown")); h.dispatchEvent(pe("pointerup")); await sleep(400);
kq.nhanNhanh = log.splice(0);
// 2) pointercancel (trình duyệt điện thoại huỷ cử chỉ) cũng phải dừng phiên, không để mic kẹt mở
startXong = false; h.dispatchEvent(pe("pointerdown")); await sleep(200); h.dispatchEvent(pe("pointercancel")); await sleep(300);
kq.huy = log.splice(0);
// 3) giữ rồi kéo ngón RA NGOÀI nút (pointerleave) không được dừng; chỉ dừng khi thả
startXong = false; h.dispatchEvent(pe("pointerdown")); await sleep(200); h.dispatchEvent(pe("pointerleave")); await sleep(100);
kq.raNgoai = log.slice(); h.dispatchEvent(pe("pointerup")); await sleep(300); kq.sauThaRaNgoai = log.splice(0);
// 4a) LỖI «nhấn vào mất luôn»: đang giữ thì phiên vừa mở làm trạng thái HA đổi (có phiên mà công tắc chưa kịp
// bật = «bận»). Nút KHÔNG được bị khoá giữa chừng (trình duyệt sẽ huỷ cử chỉ giữ), và phải báo «Đang nói».
startXong = false; h.dispatchEvent(pe("pointerdown")); await sleep(200);
states["sensor.r1_trang_thai_mic"] = {state: "nghe", attributes: {phien: "dam_thoai"}}; card.hass = mk();
kq.giuKhiTrangThaiDoi = {khoa: h.disabled, chu: h.textContent, mau: h.classList.contains("noi"), lenh: log.slice()};
h.dispatchEvent(pe("pointerup")); await sleep(300);
kq.thaSauDoiTrangThai = log.splice(0);
kq.sauKhiTha = {khoa: h.disabled, chu: h.textContent, mau: h.classList.contains("noi")};
states["sensor.r1_trang_thai_mic"] = {state: "nghe", attributes: {phien: null}}; card.hass = mk();
// 4) đã «Bật mic luôn»: nhấn giữ không làm gì
states["switch.r1_dam_thoai"] = {state: "on", attributes: {giu_mo: true}}; card.hass = mk();
h.dispatchEvent(pe("pointerdown")); h.dispatchEvent(pe("pointerup")); await sleep(200);
kq.daBatLuon = log.splice(0);
// 5) menu ngữ cảnh khi giữ lâu bị chặn
const cm = new Event("contextmenu", {cancelable: true, bubbles: true}); h.dispatchEvent(cm); kq.menuBiChan = cm.defaultPrevented;
document.getElementById("out").textContent = JSON.stringify(kq);
})();</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_nut_giu_de_noi_chiu_duoc_man_hinh_cam_ung(tmp_path):
    """Lỗi từng gặp: «Giữ để nói» không giữ được trên điện thoại (trình duyệt huỷ cử chỉ, kéo ngón ra
    ngoài là dừng, lệnh dừng chạy trước lệnh bắt đầu làm mic kẹt mở)."""
    page = tmp_path / "giu.html"
    page.write_text(PAGE_GIU.replace("@EQ@", str(EQ)).replace("@CARD@", str(CARD)), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=6000", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=60)
    import html
    import re
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html.unescape(m.group(1)))
    assert r["touchAction"] == "none"                                    # không để trình duyệt cuộn/huỷ cử chỉ
    assert r["nhanNhanh"] == ["start_duplex", "stop_duplex:sau-start"]   # dừng luôn SAU bắt đầu
    assert r["huy"] == ["start_duplex", "stop_duplex:sau-start"]         # pointercancel cũng dừng
    assert r["raNgoai"] == ["start_duplex"]                              # kéo ngón ra ngoài: vẫn giữ
    assert r["sauThaRaNgoai"] == ["start_duplex", "stop_duplex:sau-start"]
    assert r["daBatLuon"] == [] and r["menuBiChan"] is True
    # Lỗi «nhấn vào mất luôn»: giữ mà trạng thái HA đổi thì nút không bị khoá, không gửi lệnh dừng sớm, hiện «Đang nói».
    g = r["giuKhiTrangThaiDoi"]
    assert g["khoa"] is False and g["mau"] is True and "Đang nói" in g["chu"] and g["lenh"] == ["start_duplex"]
    assert r["thaSauDoiTrangThai"] == ["start_duplex", "stop_duplex:sau-start"]
    assert r["sauKhiTha"]["mau"] is False and r["sauKhiTha"]["chu"] == "Giữ để nói"


PAGE_DT = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@EQ@"></script><script src="file://@CARD@"></script>
<script>(async () => {
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const choDen = async (dk) => { for (let i = 0; i < 400 && !dk(); i++) await sleep(50); };   // mic giả mở bất đồng bộ thật
const entities = {}, states = {};
const add = (id, tk, state, attrs) => { entities[id] = {platform: "r1_speaker", translation_key: tk, device_id: "d1"}; states[id] = {state, attributes: attrs || {}}; };
add("switch.r1_dam_thoai", "intercom_open", "off", {giu_mo: false});
add("sensor.r1_trang_thai_mic", "mic_status", "nghe", {phien: null});
const wsList = [], ws_sent = [], callws = [];
window.WebSocket = class { constructor(url) { this.url = url; this.readyState = 0; this.sent = []; wsList.push(this);
  setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, 20); }
  send(d) { this.sent.push(d); } close() { this.readyState = 3; this.closed = true; } };
const hass = {entities, states, language: "vi", callService: () => Promise.resolve(),
  callWS: (m) => { callws.push(m); return Promise.resolve({path: m.path + "?authSig=x"}); }};
const card = document.createElement("r1-talk-card"); document.body.appendChild(card); card.setConfig({show_eq: false}); card.hass = hass;
const sr = card.shadowRoot, q = (s) => sr.querySelector(s);
const kq = {secure: window.isSecureContext, panelDau: q("[data-dt-panel]").style.display};
const pe = (t) => new PointerEvent(t, {pointerId: 3, bubbles: true, cancelable: true});
q("[data-dt-open]").click(); await choDen(() => wsList.length > 0 && wsList[0].readyState === 1);
kq.sign = callws.map((m) => [m.type, m.path]);
kq.ws = wsList.map((w) => w.url.replace(/^wss?:\/\/[^/]*/, ""));
kq.panelMo = q("[data-dt-panel]").style.display; kq.nutDong = q("[data-dt-open]").textContent; kq.trangThai = q("[data-dt-status]").textContent;
const w = wsList[0]; const h = q("[data-dt-hold]");
await sleep(500); kq.guiKhiChuaGiu = w.sent.filter((x) => typeof x !== "string").length;   // chưa giữ: KHÔNG gửi mic
h.dispatchEvent(pe("pointerdown")); await choDen(() => w.sent.some((x) => typeof x !== "string"));
kq.khiGiu = {khoa: h.disabled, chu: h.textContent, nhiPhan: w.sent.filter((x) => typeof x !== "string").length,
  kieu: w.sent.filter((x) => typeof x !== "string").map((x) => Object.prototype.toString.call(x))[0]};
card.hass = {...hass, states: {...states}};                   // HA đổi trạng thái giữa chừng: nút không bị khoá/dựng lại
kq.sauDoiTrangThai = {khoa: q("[data-dt-hold]").disabled, chu: q("[data-dt-hold]").textContent};
h.dispatchEvent(pe("pointerup")); await sleep(300);
kq.het = w.sent.filter((x) => typeof x === "string"); const n = w.sent.length; await sleep(500); kq.guiSauThaTay = w.sent.length - n;
w.onmessage({data: new Int16Array(1600).fill(3000).buffer});   // tiếng loa về: không ném lỗi
w.onmessage({data: JSON.stringify({loi: "loi thu"})}); kq.loiHienRa = q("[data-dt-err]").textContent;
document.dispatchEvent(new Event("visibilitychange"));        // tab vẫn hiện: không đóng
kq.vanMo = !w.closed;
Object.defineProperty(document, "visibilityState", {value: "hidden", configurable: true});
document.dispatchEvent(new Event("visibilitychange")); await sleep(200);
kq.dongKhiAnTab = {wsDong: !!w.closed, panelAn: q("[data-dt-panel]").style.display === "none"};
document.getElementById("out").textContent = JSON.stringify(kq);
})();</script>"""


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


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_mic_dien_thoai_chi_gui_khi_giu_va_dong_khi_an_tab(tmp_path):
    page = tmp_path / "dt.html"
    page.write_text(PAGE_DT.replace("@EQ@", str(EQ)).replace("@CARD@", str(CARD)), encoding="utf-8")
    r = json.loads(_chay_chrome_den_khi_xong(page))
    assert r["panelDau"] == "none"                                       # đóng mặc định
    assert r["sign"] == [["auth/sign_path", "/api/r1_speaker/dam_thoai/sensor.r1_trang_thai_mic/ws"]]
    assert r["ws"] == ["/api/r1_speaker/dam_thoai/sensor.r1_trang_thai_mic/ws?authSig=x"]
    assert r["panelMo"] == "" and "Đóng" in r["nutDong"] and "Đang nghe loa" in r["trangThai"]
    assert r["guiKhiChuaGiu"] == 0                                       # chưa giữ nút thì mic điện thoại KHÔNG đi
    k = r["khiGiu"]
    assert k["khoa"] is False and "Đang nói" in k["chu"] and k["nhiPhan"] > 0 and "ArrayBuffer" in k["kieu"]
    assert r["sauDoiTrangThai"]["khoa"] is False and "Đang nói" in r["sauDoiTrangThai"]["chu"]
    assert r["het"] == ["het"] and r["guiSauThaTay"] == 0                # thả tay: báo «het», rồi im
    assert r["loiHienRa"] == "loi thu" and r["vanMo"] is True
    assert r["dongKhiAnTab"] == {"wsDong": True, "panelAn": True}        # ẩn tab: đóng hẳn, mic không chạy ngầm
