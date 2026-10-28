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

    call = await chay({"type": "al_them", "form": {"gio": "06:30", "ngay": ["mon", "fri", "x"], "nhan": "Dậy", "loai": "tts", "noi_dung": "Đến giờ dậy"}})
    assert call[1] == "bao_thuc_dat" and call[2]["ngay"] == ["mon", "fri"]                      # ngày lạ bị bỏ ở thẻ
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
