"""Thẻ gộp ``r1-card`` chạy trong Chrome không đầu (bỏ qua nếu máy không có Chrome).

Yêu cầu chủ máy: thẻ và các tab con ĐÓNG mặc định; mỗi cài đặt chỉ nằm ở MỘT chỗ — EQ và âm lượng
ở tab EQ, «Tắt mic» ở tab Đàm thoại, tab Cài đặt chỉ giữ phần còn lại; tab Đàm thoại có
«Giữ để nói» và «Bật mic luôn».
"""

import html as html_lib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WWW = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")

PAGE = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script>
// Bản CŨ còn trong bộ nhớ đệm trình duyệt đã đăng ký sẵn các tên cố định (không có nút mới):
// thẻ gộp KHÔNG được dùng chúng.
["r1-eq-card", "r1-talk-card", "r1-settings-card", "r1-chucnang-card"].forEach((t) => customElements.define(t,
  class extends HTMLElement { setConfig() { this.old = true; } set hass(h) {} }));
window.R1_NAP = () => Promise.resolve();      // test: ba thẻ con nạp bằng <script> bên dưới
</script>
<script src="file://@EQ@"></script><script src="file://@TALK@"></script>
<script src="file://@SETTINGS@"></script><script src="file://@CHUCNANG@"></script><script src="file://@GOP@"></script>
<script>(async () => {
const FN=["cho","nghe","nghi","phan_hoi","dam_thoai","phat_nhac","loi","tat_mic"];
const prof={}; FN.forEach(k=>prof[k]={enabled:true,rim:false,color:"#0000ff",effect:"none",brightness:60,mac_dinh:true});
const entities={}, states={}, calls=[];
function add(id,tk,state,attrs){entities[id]={platform:"r1_speaker",translation_key:tk,device_id:"d1"};states[id]={state,attributes:attrs||{}};}
add("sensor.r1_cai_dat","settings","cho",{anh_sang:{chuc_nang:prof,dang_ap_dung:"nghe",dich_vu_den:"CHO_PHIA_LOA",loi_dich_vu:null,
 hieu_ung:[],den_nhac_firmware:{bat:true,luma:50,chroma:60}},
 am_thanh:{khu_tap:{bat:false},agc:{bat:false},han_dinh:{bat:false}},
 ket_noi:{host:"h",cong:1,khoa_bo_dam:"da_co",tuy_chon:"/config/x"}});
add("number.r1_am_luong","volume","7",{min:0,max:15,step:1});
add("number.r1_tang_mic","mic_gain","12",{min:0,max:30,step:1});
add("switch.r1_tat_mic","mute","off");
add("switch.r1_dam_thoai","intercom_open","off",{giu_mo:false});
add("sensor.r1_mic","mic_status","nghe",{phien:null});
add("media_player.r1_loa","speaker","idle");
["a","b"].forEach((k,i)=>add("number.eq_"+k,"eq_band","0",{band:i,label:"B"+i,min:-1500,max:1500,step:10}));
const hass={entities,states,language:"vi",callService:(d,s,x)=>calls.push([d,s,x])};
const card=document.createElement("r1-card"); document.body.appendChild(card);
card.setConfig({}); card.hass=hass; await card._san;
const sr=card.shadowRoot, q=s=>sr.querySelector(s);
const vis=el=>!!el && el.style.display!=="none";
const tabs=[...sr.querySelectorAll(".tabs .tab")];
const trang=()=>({thanVao:vis(card._body), talk:vis(card._parts.talk), eq:vis(card._parts.eq), settings:vis(card._parts.settings)});
const dau=trang();
const moThe=trang();                                              // tên loa + hàng tab LUÔN hiện; nội dung vẫn đóng
const tenLoa=q(".tieude").textContent, tenTab=tabs.map(b=>b.textContent), soTab=tenTab.length;
tabs.find(b=>b.textContent==="Đàm thoại").click();
const t=card._parts.talk.shadowRoot;
const talk={...trang(), giu:!!t.querySelector("[data-hold]"), luon:!!t.querySelector("[data-always]"),
  mute:!!t.querySelector("[data-mute]"), eqNhung:!!t.querySelector("[data-eq] r1-eq-card")};
tabs.find(b=>b.textContent==="Cài đặt").click();
const s=card._parts.settings.shadowRoot;
const caiDat={...trang(), vol:!!s.querySelector("[data-vol]"), eq:s.querySelectorAll("[data-eq]").length,
  mute:!!s.querySelector("[data-mute]"), micGain:!!s.querySelector("[data-mic-gain]"),
  nutDong:!!s.querySelector("[data-open]"), tabCon:s.querySelectorAll("[data-tab]").length};
tabs.find(b=>b.textContent==="EQ").click();
const eq=trang();
tabs.find(b=>b.textContent==="EQ").click();                       // bấm lại: đóng
const dongLai=trang();
const ver=q(".ver").textContent;
document.getElementById("out").textContent=JSON.stringify({dau,moThe,talk,caiDat,eq,dongLai,ver,tenLoa,soTab,tenTab});
})();</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_gop_dong_mac_dinh_va_khong_trung_cai_dat(tmp_path):
    # r1-card nạp ba thẻ con bằng import động tới URL tuyệt đối của HA; trong trang file:// không tới
    # được, nên test thay bằng ``window.R1_NAP`` và nạp ba thẻ con bằng <script>.
    (tmp_path / "gop.js").write_text((WWW / "r1-card.js").read_text(encoding="utf-8"), encoding="utf-8")
    page = tmp_path / "gop.html"
    page.write_text(PAGE.replace("@EQ@", str(WWW / "r1-eq-card.js")).replace(
        "@TALK@", str(WWW / "r1-talk-card.js")).replace(
        "@SETTINGS@", str(WWW / "r1-settings-card.js")).replace("@CHUCNANG@", str(WWW / "r1-chucnang-card.js")).replace("@GOP@", str(tmp_path / "gop.js")),
        encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=3000", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    assert r["dau"] == {"thanVao": True, "talk": False, "eq": False, "settings": False}    # hàng tab hiện, NỘI DUNG đóng hết
    assert r["moThe"] == r["dau"]                                                           # chưa bấm tab nào: vẫn đóng
    assert r["tenLoa"] == "Loa R1" and r["tenTab"] == ["Đàm thoại", "EQ", "Chức năng", "Cài đặt"]   # tên loa và bốn tab luôn hiện
    assert r["talk"]["talk"] and not r["talk"]["eq"] and not r["talk"]["settings"]        # chỉ một tab
    assert r["talk"]["giu"] and r["talk"]["luon"] and r["talk"]["mute"]                  # nút mới + Tắt mic
    assert not r["talk"]["eqNhung"]                                                       # EQ không nhúng
    c = r["caiDat"]
    assert c["settings"] and not c["talk"] and not c["eq"]
    assert not c["vol"] and c["eq"] == 0 and not c["mute"]                               # không trùng
    assert c["micGain"] and not c["nutDong"] and c["tabCon"] == 3                        # mở sẵn, ba nhóm
    assert r["eq"] == {"thanVao": True, "talk": False, "eq": True, "settings": False}
    assert r["dongLai"] == {"thanVao": True, "talk": False, "eq": False, "settings": False}
    assert "r1-card 2026-" in r["ver"] and "đàm thoại 2026-" in r["ver"]       # ghi phiên bản để đối chiếu


PAGE_LUI = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script>
// Lớp đệm vẫn trả BẢN CŨ: không thẻ con nào xuất lớp mới (window.R1_THE trống), chỉ có thẻ cũ đã đăng ký.
["r1-eq-card", "r1-talk-card", "r1-settings-card", "r1-chucnang-card"].forEach((t) => customElements.define(t,
  class extends HTMLElement { setConfig() {} set hass(h) {} }));
window.R1_NAP = () => Promise.resolve();
</script>
<script src="file://@GOP@"></script>
<script>(async () => {
const card=document.createElement("r1-card"); document.body.appendChild(card);
let loi=null; try { card.setConfig({}); card.hass={entities:{},states:{}}; await card._san; } catch (e) { loi=String(e); }
const sr=card.shadowRoot;
document.getElementById("out").textContent=JSON.stringify({loi, ver:sr.querySelector(".ver")?.textContent,
  tabs:sr.querySelectorAll(".tabs .tab").length});
})();</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_gop_dung_tam_the_cu_va_noi_ro_khi_lop_dem_chan_ban_moi(tmp_path):
    (tmp_path / "gop.js").write_text((WWW / "r1-card.js").read_text(encoding="utf-8"), encoding="utf-8")
    page = tmp_path / "lui.html"
    page.write_text(PAGE_LUI.replace("@GOP@", str(tmp_path / "gop.js")), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=3000", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    assert r["loi"] is None and r["tabs"] == 4                        # thẻ vẫn dựng được, không hỏng
    assert "DÙNG BẢN CŨ của: talk, eq, chucnang, settings" in r["ver"]           # và nói rõ đang dùng bản cũ


PAGE_NHIEU_LOA = PAGE.split("<script>(async () => {")[0] + """<script>(async () => {
const entities={}, states={}, calls=[];
const add=(id,tk,dev)=>{entities[id]={platform:"r1_speaker",translation_key:tk,device_id:dev};states[id]={state:"7",attributes:{min:0,max:15,step:1}};};
["d1","d2"].forEach(d=>{add("number.r1_am_luong_"+d,"volume",d); add("sensor.r1_cai_dat_"+d,"settings",d);});
const devices={d1:{name:"Phicomm R1"},d2:{name:"Phicomm R1",name_by_user:"Bếp"}};
const hass={entities,states,devices,language:"vi",callService:(d,s,x)=>calls.push([d,s,x])};
const tao=async (cfg)=>{const c=document.createElement("r1-card"); document.body.appendChild(c); c.setConfig(cfg); c.hass=hass; await c._san; return c;};
const chips=(c)=>[...c.shadowRoot.querySelectorAll(".tabs.loa .tab")].map(b=>b.textContent+(b.classList.contains("sel")?"*":""));
const dev=(c)=>({eq:c._parts.eq._config.device_id||null, settings:c._parts.settings._config.device_id||null, chucnang:c._parts.chucnang._config.device_id||null, talk:c._parts.talk._config.device_id||null});
const c=await tao({});
const dau={chips:chips(c), dev:dev(c)};
c.shadowRoot.querySelectorAll(".tabs.loa .tab")[1].click();
const sau={chips:chips(c), dev:dev(c)};
const tabBtn=(c,ten)=>[...c.shadowRoot.querySelectorAll(".tabs:not(.loa) .tab")].find(b=>b.textContent===ten);
const hien=(c)=>c.shadowRoot.querySelector(".tabs.loa").style.display!=="none";
const hienLoa={dau:hien(c)}; tabBtn(c,"Đàm thoại").click(); hienLoa.talk=hien(c); tabBtn(c,"EQ").click(); hienLoa.eq=hien(c);
const ghim=await tao({device_id:"d2"});
const g={chips:chips(ghim), dev:dev(ghim)};
document.getElementById("out").textContent=JSON.stringify({dau,sau,g,hienLoa});
})();</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_the_gop_co_hai_loa_thi_chon_loa_cho_eq_va_cai_dat_con_ghim_device_id_thi_khong_hien_hang_chon(tmp_path):
    (tmp_path / "gop.js").write_text((WWW / "r1-card.js").read_text(encoding="utf-8"), encoding="utf-8")
    page = tmp_path / "nhieu.html"
    page.write_text(PAGE_NHIEU_LOA.replace("@EQ@", str(WWW / "r1-eq-card.js")).replace(
        "@TALK@", str(WWW / "r1-talk-card.js")).replace(
        "@SETTINGS@", str(WWW / "r1-settings-card.js")).replace("@CHUCNANG@", str(WWW / "r1-chucnang-card.js")).replace("@GOP@", str(tmp_path / "gop.js")), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=3000", "--dump-dom", f"file://{page}"], capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    # Tên là tên thiết bị trong HA (đổi tên ở trang thiết bị thì thẻ theo); loa đầu được chọn sẵn
    assert r["dau"]["chips"] == ["Phicomm R1*", "Bếp"] and r["dau"]["dev"] == {"eq": "d1", "settings": "d1", "chucnang": "d1", "talk": None}
    # Chọn loa 2: EQ, Chức năng và Cài đặt đổi theo; Đàm thoại giữ cách chọn riêng
    assert r["sau"]["chips"] == ["Phicomm R1", "Bếp*"] and r["sau"]["dev"] == {"eq": "d2", "settings": "d2", "chucnang": "d2", "talk": None}
    # Mở tab Đàm thoại thì ẩn hàng chọn MỘT loa (tab đó có hàng chọn nhiều loa riêng); mở tab khác thì hiện lại
    assert r["hienLoa"] == {"dau": True, "talk": False, "eq": True}
    # Ghim device_id trong cấu hình thẻ: không hiện hàng chọn, cả ba tab theo loa đó
    assert r["g"]["chips"] == [] and r["g"]["dev"] == {"eq": "d2", "settings": "d2", "chucnang": "d2", "talk": "d2"}
