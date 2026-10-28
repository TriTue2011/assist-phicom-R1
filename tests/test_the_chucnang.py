"""Thẻ ``r1-chucnang-card`` (tab «Chức năng»): bật/tắt kết nối DLNA/AirPlay/Bluetooth, «Đóng ADB mạng…» và đặt báo thức.
Mô hình chạy bằng Node trên trạng thái THẬT của tích hợp, và lệnh thẻ dựng được gọi thẳng vào dịch vụ HA thật (hợp đồng hai phía);
phần DOM chạy trong Chrome không đầu (nếu có; tên chứa «giao_dien» để bộ không-Chrome bỏ qua)."""

import html as html_lib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from custom_components.r1_speaker.const import CHUCNANG_CARD_URL

from .test_bo_dam import _them
from .test_the_cai_dat import _hass_gia

CARD = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www" / "r1-chucnang-card.js"
need_node = pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy mô hình thẻ")
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
SENSOR = "sensor.r1_bao_thuc_ke_tiep"


def _node(expr, **payload):
    script = ("const c=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',"
              "()=>{const i=JSON.parse(s);console.log(JSON.stringify((" + expr + ")))})")
    out = subprocess.run(["node", "-e", script, str(CARD)], input=json.dumps(payload), capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _mo_hinh(hass):
    return _node("c.buildModel(i.hass,{})", hass=_hass_gia(hass))


def test_tep_the_chi_goi_dich_vu_ha_va_dang_ky_dung_ten():
    js = CARD.read_text(encoding="utf-8")
    assert 'customElements.define("r1-chucnang-card"' in js and "customCards.push" not in js     # chỉ r1-card nạp thẻ con
    assert CHUCNANG_CARD_URL == "/r1_speaker/r1-chucnang-card.js"
    assert "innerHTML" in js and "esc(" in js                                                    # dữ liệu ngoài đều qua esc()
    for cam in ("fetch(", "XMLHttpRequest", "WebSocket(", "ws://", "http://", "https://", "192.168", "172.16", "10.0.", "sendBeacon", "eval("):
        assert cam not in js, cam


async def test_the_duoc_phuc_vu_khong_nap_rieng(hass, r1, hass_client_no_auth):
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    await _them(hass, r1)
    assert CHUCNANG_CARD_URL not in hass.data[DATA_EXTRA_MODULE_URL]
    r = await (await hass_client_no_auth()).get(CHUCNANG_CARD_URL)
    assert r.status == 200 and "r1-chucnang-card" in await r.text()
    r2 = await (await hass_client_no_auth()).get(CHUCNANG_CARD_URL.replace("/r1_speaker/", "/r1_speaker/b/12345/"))
    assert r2.status == 200 and r2.headers["Cache-Control"] == "no-store"


@need_node
async def test_lenh_cua_the_chay_dung_dich_vu_that_them_tat_xoa_bao_thuc_va_cong_tat_ket_noi(hass, r1):
    await _them(hass, r1)
    m = _mo_hinh(hass)
    assert m["found"] and m["alarms"]["entity"] == SENSOR and m["alarms"]["list"] == []
    assert [k for k in ("dlna", "airplay", "bluetooth") if m["links"][k]["present"]] == ["dlna", "airplay", "bluetooth"]
    assert m["adbDong"]["entity"] == "button.r1_dong_adb"

    async def chay(a):
        call = _node("c.makeCall(i.m,i.a)", m=_mo_hinh(hass), a=a)
        assert call, a
        await hass.services.async_call(call[0], call[1], call[2], blocking=True)
        await hass.async_block_till_done()
        return call

    call = await chay({"type": "al_them", "form": {"gio": "06:30", "ngay": ["mon", "fri", "x"], "nhan": "Dậy", "loai": "tts", "noi_dung": "Đến giờ dậy",
                                                    "tts": "tts.google_vi"}})
    assert call[1] == "bao_thuc_dat" and call[2]["ngay"] == ["mon", "fri"]                      # ngày lạ bị bỏ ở thẻ
    assert call[2]["tts"] == "tts.google_vi"                                                      # máy TTS đi kèm và dịch vụ HA thật nhận
    (a,) = _mo_hinh(hass)["alarms"]["list"]
    assert (a["gio"], a["ngay"], a["nhan"], a["bat"]) == ("06:30", ["mon", "fri"], "Dậy", True)
    await chay({"type": "al_bat", "id": a["id"], "on": False})
    assert _mo_hinh(hass)["alarms"]["list"][0]["bat"] is False
    await chay({"type": "al_xoa", "id": a["id"]})
    assert _mo_hinh(hass)["alarms"]["list"] == []
    h = m["alarms"]["hoan"]
    assert h["entity"] == "number.r1_hoan_bao_thuc" and h["value"] == 9                       # mặc định 9 phút
    await chay({"type": "hoan_dat", "value": "15"})
    assert _mo_hinh(hass)["alarms"]["hoan"]["value"] == 15
    assert _node("c.makeCall(i.m,{type:'hoan_dat',value:0})", m=m) is None and _node("c.makeCall(i.m,{type:'hoan_dat',value:121})", m=m) is None
    # máy TTS chỉ đi kèm loại «đọc lời nhắn» và phải đúng dạng tts.<tên>
    def them(**f):
        return _node("c.makeCall(i.m,{type:'al_them',form:Object.assign({gio:'07:00',ngay:[]},i.f)})", m=m, f=f)[2]
    assert them(loai="tts", tts="tts.piper").get("tts") == "tts.piper"
    assert "tts" not in them(loai="media", tts="tts.piper", noi_dung="media-source://media_source/local/a.mp3")     # âm thanh: không kèm máy TTS
    assert them(loai="media", noi_dung="media-source://media_source/local/a.mp3")["noi_dung"] == "media-source://media_source/local/a.mp3"
    for sai in ("", "light.den", "tts.", "tts.a b", "TTS.x"):
        assert "tts" not in them(loai="tts", tts=sai), sai
    # giờ sai: thẻ KHÔNG gọi gì
    assert _node("c.makeCall(i.m,{type:'al_them',form:{gio:'25:00',ngay:[],loai:'tts'}})", m=m) is None
    # công tắc kết nối và nút Đóng ADB
    assert _node("c.makeCall(i.m,{type:'link',key:'airplay',on:true})", m=m) == ["switch", "turn_on", {"entity_id": m["links"]["airplay"]["entity"]}]
    assert _node("c.makeCall(i.m,{type:'adb_dong'})", m=m) == ["button", "press", {"entity_id": "button.r1_dong_adb"}]


PAGE = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@CARD@"></script>
<script>
const entities={}, states={}, calls=[];
const add=(id,tk,state,attrs)=>{entities[id]={platform:"r1_speaker",translation_key:tk,device_id:"d1"}; states[id]={state,attributes:attrs||{}};};
add("switch.r1_dlna","dlna","on",{renderer:"đã nối (SSDP unicast)"});
add("switch.r1_airplay","airplay","off");
add("switch.r1_bluetooth","bluetooth","unknown");
add("button.r1_dong_adb","dong_adb","unknown");
add("number.r1_hoan_bao_thuc","hoan_phut","9",{min:1,max:120});
const DS=[{id:"a1",gio:"06:30",ngay:["mon","fri"],nhan:"Dậy",loai:"tts",bat:true,ke_tiep:"2026-10-30T06:30:00"},
          {id:"r1",ngay:[],nhan:"<img src=x onerror=alert(1)>",loai:"tts",bat:true,ke_tiep:"2026-10-29T08:05:00"}];
const dat=(dangKeu)=>{states["sensor.r1_bao_thuc_ke_tiep"]={state:"2026-10-29T06:30:00+00:00",attributes:{bao_thuc:DS,dang_keu:dangKeu}};};
add("sensor.r1_bao_thuc_ke_tiep","bao_thuc_ke_tiep","2026-10-29T06:30:00+00:00"); dat(null);
const mk=()=>({entities:{...entities},states:{...states},language:"vi",callService:(d,s,x)=>calls.push([d,s,x])});
const card=document.createElement("r1-chucnang-card"); document.body.appendChild(card); card.setConfig({}); card.hass=mk();
const sr=card.shadowRoot, q=s=>sr.querySelector(s), qa=s=>[...sr.querySelectorAll(s)];
const ghi=(f)=>{const n=calls.length; f(); return JSON.stringify(calls.slice(n));};
const hien={dlna:q("[data-link=dlna]").checked, airplay:q("[data-link=airplay]").checked, btKhoa:q("[data-link=bluetooth]").disabled,
  note:q(".note").textContent, gio:qa(".al .gio").map(e=>e.textContent), mo:qa(".al .mt").map(e=>e.textContent),
  xss:sr.innerHTML.includes("<img src=x"), dangKeu:!!q(".ring")};
const lienKet=ghi(()=>{const e=q("[data-link=airplay]"); e.checked=true; e.dispatchEvent(new Event("change"));});
let hoi=""; window.confirm=(m)=>{hoi=m; return false;};
const adbHuy=ghi(()=>q("[data-adb-dong]").click());
window.confirm=()=>true;
const adbDong=ghi(()=>q("[data-adb-dong]").click());
const bat=ghi(()=>{const e=q("[data-al-bat=a1]"); e.checked=false; e.dispatchEvent(new Event("change"));});
const xoa=ghi(()=>q("[data-al-xoa=a1]").click());
// biểu mẫu thêm báo thức: bản nháp sống qua các lần dựng lại khi bấm chọn ngày
const nhap=(sel,v)=>{const e=q(sel); e.value=v; e.dispatchEvent(new Event("input"));};
nhap("[data-f=gio]","07:15"); q("[data-day=mon]").click(); q("[data-day=wed]").click(); nhap("[data-f=nhan]","Đi học");
const nhap2={gio:q("[data-f=gio]").value, ngay:qa(".day.on").map(e=>e.dataset.day), nhan:q("[data-f=nhan]").value};
const them=ghi(()=>q("[data-al-them]").click());
const saiGio=ghi(()=>{nhap("[data-f=gio]",""); q("[data-al-them]").click();});
dat("a1"); card.hass=mk();
const dangKeu=!!q(".ring");
const dung=ghi(()=>q("[data-ring-stop]").click());
const hoan=ghi(()=>q("[data-ring-snooze]").click());
const hoanTitle=q("[data-ring-snooze]").title, hoanGiaTri=q("[data-hoan]").value;
const hoanDat=ghi(()=>{const e=q("[data-hoan]"); e.value="5"; e.dispatchEvent(new Event("change"));});
const hoanSai=ghi(()=>{const e=q("[data-hoan]"); e.value="0"; e.dispatchEvent(new Event("change"));});
setTimeout(()=>{document.getElementById("out").textContent=JSON.stringify({hien,lienKet,adbHuy,adbDong,hoi,bat,xoa,nhap2,them,saiGio,dangKeu,dung,hoan,hoanTitle,hoanGiaTri,hoanDat,hoanSai});},100);
</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_chucnang_hien_ket_noi_va_bao_thuc_va_moi_thao_tac_chi_la_lenh_dich_vu(tmp_path):
    page = tmp_path / "chucnang.html"
    page.write_text(PAGE.replace("@CARD@", str(CARD)), encoding="utf-8")
    out = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                          "--virtual-time-budget=2000", "--dump-dom", f"file://{page}"], capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    h = r["hien"]
    assert h["dlna"] is True and h["airplay"] is False and h["btKhoa"] is False, "Bluetooth «unknown» (ADB chưa đọc được) vẫn phải bấm được"
    assert "đã nối (SSDP unicast)" in h["note"] and "Bluetooth chưa đọc được" in h["note"]
    assert h["gio"] == ["06:30", "08:05"]                                      # báo thức theo giờ; nhắc nhở một lần lấy giờ lần kêu kế tiếp
    assert h["mo"][0] == "T2 T6 · Dậy" and h["mo"][1].startswith("Một lần")
    assert h["xss"] is False and h["dangKeu"] is False                        # nhãn không thành HTML
    assert json.loads(r["lienKet"]) == [["switch", "turn_on", {"entity_id": "switch.r1_airplay"}]]
    assert json.loads(r["adbHuy"]) == []                                       # huỷ ở hộp xác nhận: KHÔNG gọi gì
    assert all(k in r["hoi"] for k in ("ƯU", "NHƯỢC", "MỞ LẠI", "rút điện"))
    assert json.loads(r["adbDong"]) == [["button", "press", {"entity_id": "button.r1_dong_adb"}]]
    sid = "sensor.r1_bao_thuc_ke_tiep"
    assert json.loads(r["bat"]) == [["r1_speaker", "bao_thuc_bat_tat", {"entity_id": sid, "id": "a1", "bat": False}]]
    assert json.loads(r["xoa"]) == [["r1_speaker", "bao_thuc_xoa", {"entity_id": sid, "id": "a1"}]]
    assert r["nhap2"] == {"gio": "07:15", "ngay": ["mon", "wed"], "nhan": "Đi học"}   # bản nháp không mất khi dựng lại
    assert json.loads(r["them"]) == [["r1_speaker", "bao_thuc_dat", {"entity_id": sid, "gio": "07:15", "ngay": ["mon", "wed"], "loai": "tts", "bat": True,
                                                                      "nhan": "Đi học"}]]
    assert json.loads(r["saiGio"]) == []                                       # giờ trống: không gọi dịch vụ
    assert r["dangKeu"] is True
    assert json.loads(r["dung"]) == [["r1_speaker", "bao_thuc_tat", {"entity_id": sid}]]
    assert json.loads(r["hoan"]) == [["r1_speaker", "bao_thuc_hoan", {"entity_id": sid}]]      # không nêu số phút: dùng cài đặt «Hoãn (phút)»
    assert r["hoanGiaTri"] == "9" and r["hoanTitle"] == "Hoãn 9"
    assert json.loads(r["hoanDat"]) == [["number", "set_value", {"entity_id": "number.r1_hoan_bao_thuc", "value": 5}]]
    assert json.loads(r["hoanSai"]) == []                                       # 0 phút: không gọi dịch vụ


PAGE_MEDIA = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@CARD@"></script>
<script>
const entities={}, states={}, calls=[], ws=[];
const add=(id,tk,state,attrs)=>{entities[id]={platform:"r1_speaker",translation_key:tk,device_id:"d1"}; states[id]={state,attributes:attrs||{}};};
add("sensor.r1_bao_thuc_ke_tiep","bao_thuc_ke_tiep","unknown",{bao_thuc:[],dang_keu:null});
states["tts.piper"]={state:"unknown",attributes:{friendly_name:"Piper"}};
states["tts.google_vi"]={state:"unknown",attributes:{friendly_name:"Google VI"}};
const MP3={title:"chuong.mp3",media_content_id:"media-source://media_source/local/chuong.mp3",can_play:true,can_expand:false};
const CAY={
 "":{title:"Phương tiện",media_content_id:"media-source://",children:[{title:"Phương tiện của tôi",media_content_id:"media-source://media_source",can_play:false,can_expand:true},
   {title:"Mục lạ không phát được",media_content_id:"x",can_play:false,can_expand:false}]},
 "media-source://media_source":{title:"Phương tiện của tôi",media_content_id:"media-source://media_source",children:[{title:"local",media_content_id:"media-source://media_source/local",can_play:false,can_expand:true}]},
 "media-source://media_source/local":{title:"local",media_content_id:"media-source://media_source/local",children:[MP3]},
};
let hong=false;
const hass={entities,states,language:"vi",callService:(d,s,x)=>calls.push([d,s,x]),
  callWS:async (m)=>{ ws.push(JSON.stringify(m)); if (hong) throw new Error("không có quyền"); return CAY[m.media_content_id||""]; }};
const card=document.createElement("r1-chucnang-card"); document.body.appendChild(card); card.setConfig({}); card.hass=hass;
const sr=card.shadowRoot, q=s=>sr.querySelector(s), qa=s=>[...sr.querySelectorAll(s)];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const nhap=(sel,v)=>{const e=q(sel); e.value=v; e.dispatchEvent(new Event("input"));};
const chon=(sel,v)=>{const e=q(sel); e.value=v; e.dispatchEvent(new Event("change"));};
(async()=>{
 const tts={oTts:!!q("[data-f=tts]"), oPick:!!q("[data-media-pick]"), oNoiDung:!!q("[data-f=noi_dung]"),
   tuyChon:qa("[data-f=tts] option").map(o=>o.value+"|"+o.textContent)};
 chon("[data-f=tts]","tts.piper"); nhap("[data-f=noi_dung]","Dậy đi"); nhap("[data-f=gio]","06:30");
 q("[data-al-them]").click();
 const themTts=JSON.stringify(calls.splice(0));
 chon("[data-f=loai]","media");
 nhap("[data-f=link]","https://youtu.be/cu");                                   // link gõ trước, rồi chọn tệp: tệp thay link
 const media={oTts:!!q("[data-f=tts]"), oPick:!!q("[data-media-pick]"), oNoiDung:!!q("[data-f=noi_dung]"), tuyChonRong:q("[data-media-pick]").value, docChi:q("[data-media-pick]").readOnly, oLink:!!q("[data-f=link]")};
 q("[data-media-pick]").click(); await sleep(30);
 const goc={ten:q(".mb .mt").textContent, muc:qa("[data-mb-i]").map(b=>b.textContent.trim()), lui:!!q("[data-mb-back]")};
 q('[data-mb-i="0"]').click(); await sleep(30);
 const trongTmuc={ten:q(".mb .mt").textContent, muc:qa("[data-mb-i]").map(b=>b.textContent.trim()), lui:!!q("[data-mb-back]")};
 q("[data-mb-back]").click(); await sleep(30);
 const quayLai={ten:q(".mb .mt").textContent, muc:qa("[data-mb-i]").map(b=>b.textContent.trim())};
 q('[data-mb-i="0"]').click(); await sleep(30);
 q('[data-mb-i="0"]').click(); await sleep(30);                    // vào local
 q('[data-mb-i="0"]').click(); await sleep(30);                    // chọn chuong.mp3
 const chonXong={hop:!!q(".mb"), truong:q("[data-media-pick]").value, link:q("[data-f=link]").value};
 nhap("[data-f=gio]","07:15");
 q("[data-al-them]").click();
 const themMedia=JSON.stringify(calls.splice(0));
 // Dán link YouTube thì bỏ tệp đã chọn; link hợp lệ đi thẳng làm nội dung; link sai không gọi gì
 for (let i=0;i<4;i++){ q(i===0?"[data-media-pick]":'[data-mb-i="0"]').click(); await sleep(30); }
 const truocLink=q("[data-media-pick]").value;
 nhap("[data-f=link]","https://youtu.be/dQw4w9WgXcQ"); nhap("[data-f=gio]","08:00");
 const sauLink=q("[data-media-pick]").value;
 nhap("[data-f=link]",""); q("[data-day=mon]").click(); const sauXoaLink=q("[data-media-pick]").value; q("[data-day=mon]").click();   // xoá link rồi dựng lại: tệp cũ KHÔNG hiện lại
 nhap("[data-f=link]","https://youtu.be/dQw4w9WgXcQ"); nhap("[data-f=gio]","08:00");
 q("[data-al-them]").click(); const themLink=JSON.stringify(calls.splice(0));
 nhap("[data-f=link]","khong phai link"); nhap("[data-f=gio]","08:00"); q("[data-al-them]").click(); const linkSai=calls.length;
 nhap("[data-f=link]","www.youtube.com/watch?v=abc"); q("[data-al-them]").click(); const linkKhongScheme=JSON.stringify(calls.splice(0));
 hong=true; q("[data-media-pick]").click(); await sleep(30);
 const loi={hop:!!q(".mb"), chu:(q(".mb .warn")||{}).textContent, muc:qa("[data-mb-i]").length};
 q("[data-mb-close]").click();
 document.getElementById("out").textContent=JSON.stringify({tts,themTts,media,goc,trongTmuc,quayLai,chonXong,themMedia,truocLink,sauLink,sauXoaLink,themLink,linkSai,linkKhongScheme,loi,dongHop:!q(".mb"),ws});
})();
</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_chucnang_chon_may_tts_cho_loi_nhac_va_duyet_media_cho_am_thanh(tmp_path):
    page = tmp_path / "media.html"
    page.write_text(PAGE_MEDIA.replace("@CARD@", str(CARD)), encoding="utf-8")
    out = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                          "--virtual-time-budget=4000", "--dump-dom", f"file://{page}"], capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m and m.group(1) != "CHUA CHAY", out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    sid = "sensor.r1_bao_thuc_ke_tiep"
    # Loại «đọc lời nhắn»: có ô chọn máy TTS (mặc định + các máy tts của HA, xếp theo tên), không có ô chọn âm thanh
    assert r["tts"]["oTts"] and r["tts"]["oNoiDung"] and not r["tts"]["oPick"]
    assert r["tts"]["tuyChon"] == ["|Mặc định (Assist của loa)", "tts.google_vi|Google VI", "tts.piper|Piper"]
    assert json.loads(r["themTts"]) == [["r1_speaker", "bao_thuc_dat", {"entity_id": sid, "gio": "06:30", "ngay": [], "loai": "tts", "bat": True,
                                                                         "noi_dung": "Dậy đi", "tts": "tts.piper"}]]
    # Loại «phát âm thanh»: không có ô máy TTS, ô chọn âm thanh chỉ đọc và bấm vào thì mở thư viện media của HA
    assert not r["media"]["oTts"] and r["media"]["oPick"] and not r["media"]["oNoiDung"] and r["media"]["tuyChonRong"] == "" and r["media"]["docChi"] is True
    assert r["goc"] == {"ten": "Phương tiện", "muc": ["Phương tiện của tôi"], "lui": False}          # mục không phát được, không mở được bị ẩn
    assert r["trongTmuc"] == {"ten": "Phương tiện của tôi", "muc": ["local"], "lui": True}
    assert r["quayLai"] == {"ten": "Phương tiện", "muc": ["Phương tiện của tôi"]}                        # Quay lại về thư mục trước, không gọi lại HA
    assert r["media"]["oLink"] is True
    assert r["chonXong"] == {"hop": False, "truong": "chuong.mp3", "link": ""}                      # chọn tệp thì ô link trống (chỉ một nguồn)                                      # chọn tệp: đóng hộp, ô hiện tên tệp
    assert json.loads(r["themMedia"]) == [["r1_speaker", "bao_thuc_dat", {"entity_id": sid, "gio": "07:15", "ngay": [], "loai": "media", "bat": True,
                                                                           "noi_dung": "media-source://media_source/local/chuong.mp3"}]]
    assert r["truocLink"] == "chuong.mp3" and r["sauLink"] == "" and r["sauXoaLink"] == ""                                     # dán link thì bỏ tệp đã chọn
    assert json.loads(r["themLink"]) == [["r1_speaker", "bao_thuc_dat", {"entity_id": sid, "gio": "08:00", "ngay": [], "loai": "media", "bat": True,
                                                                          "noi_dung": "https://youtu.be/dQw4w9WgXcQ"}]]
    assert r["linkSai"] == 0                                                                          # link không hợp lệ: không gọi dịch vụ
    assert json.loads(r["linkKhongScheme"])[0][2]["noi_dung"] == "www.youtube.com/watch?v=abc"        # link YouTube dán không kèm https vẫn nhận
    assert r["loi"]["hop"] and "không có quyền" in r["loi"]["chu"] and r["loi"]["muc"] == 0         # HA từ chối: báo lỗi rõ, không treo
    assert r["dongHop"]
    assert [json.loads(x) for x in r["ws"]][:2] == [{"type": "media_source/browse_media"},
                                                       {"type": "media_source/browse_media", "media_content_id": "media-source://media_source"}]
