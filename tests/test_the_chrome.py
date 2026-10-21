"""Thẻ r1-eq-card trong Chrome không đầu (nếu có): dựng thẻ với `hass` giả, kéo thanh, bật công
tắc, đối chiếu lệnh gọi dịch vụ. Tên chứa «giao_dien» để bộ không-Chrome bỏ qua. Không chạm loa."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CARD = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www" / "r1-eq-card.js"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

PAGE = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@CARD@"></script>
@SCRIPT@"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_dung_thanh_tuong_tac_va_goi_dich_vu(tmp_path):
    page = tmp_path / "the.html"
    page.write_text(PAGE.replace("@CARD@", str(CARD)).replace("@SCRIPT@", SCRIPT), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=2000", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(m.group(1).replace("&quot;", '"'))
    assert r["bands"] == 5 and (r["min"], r["max"]) == ("-1500", "1500")
    assert r["values"] == ["900", "-400", "-100", "-500", "100"]    # thanh 0 vừa kéo lên 900
    assert r["vals"][1:] == ["-400", "-100", "-500", "+100"]
    assert r["badges"] == 4            # EQ, loudness, cường độ bass, preset: chưa xác nhận
    assert r["presetDisabled"] is True  # chưa có lệnh đặt preset đã xác nhận
    assert r["calls"] == [
        ["number", "set_value", {"entity_id": "number.phicomm_r1_eq_60_hz", "value": 900}],
        ["switch", "turn_on", {"entity_id": "switch.phicomm_r1_bass_boost"}]]


SCRIPT = r'''<script>
const ids = ["60_hz","230_hz","910_hz","3_6_khz","14_khz"];
const labels = ["60 Hz","230 Hz","910 Hz","3.6 kHz","14 kHz"];
const vals = [200,-400,-100,-500,100];
const entities = {}, states = {};
ids.forEach((k,i)=>{const id="number.phicomm_r1_eq_"+k;
 entities[id]={platform:"r1_speaker",translation_key:"eq_band",device_id:"d1"};
 states[id]={state:String(vals[i]),attributes:{band:i,label:labels[i],min:-1500,max:1500,step:10,confirmed:true}};});
function add(id,tk,state,attrs){entities[id]={platform:"r1_speaker",translation_key:tk,device_id:"d1"};states[id]={state,attributes:attrs};}
add("switch.phicomm_r1_eq","eq_enable","on",{confirmed:false});
add("switch.phicomm_r1_bass_boost","bass","off",{confirmed:true});
add("switch.phicomm_r1_loudness","loudness","off",{confirmed:false});
add("number.phicomm_r1_bass_strength","bass_strength","200",{min:0,max:1000,step:10,confirmed:false});
add("select.phicomm_r1_eq_preset","eq_preset","unknown",{options:["Normal","Jazz"],selectable:false,confirmed:false});
const calls=[];
const card=document.createElement("r1-eq-card");
document.body.appendChild(card);
card.setConfig({});
card.hass={entities,states,language:"vi",callService:(d,s,x)=>calls.push([d,s,x])};
const sr=card.shadowRoot;
const sl=[...sr.querySelectorAll("input[data-b]")];
sl[0].value=900; sl[0].dispatchEvent(new Event("change"));
const sw=sr.querySelector('[data-s="bass"]'); sw.checked=true; sw.dispatchEvent(new Event("change"));
const sel=sr.querySelector("select[data-p]");
document.getElementById("out").textContent=JSON.stringify({
 bands:sl.length, values:sl.map(i=>i.value), min:sl[0].min, max:sl[0].max,
 vals:[...sr.querySelectorAll('.band .val')].map(e=>e.textContent),
 badges:sr.querySelectorAll(".badge").length, presetDisabled:sel.disabled, calls});
</script>
'''
