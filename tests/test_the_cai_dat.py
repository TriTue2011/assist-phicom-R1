"""Thẻ ``r1-settings-card``: được phục vụ + nạp; mục cài đặt ẨN mặc định và chỉ hiện khi bấm nút mở;
ba nhóm Âm thanh / Ánh sáng / Kết nối; mọi thao tác chỉ là lệnh gọi dịch vụ HA (không gọi loa).
Chạy mô hình bằng Node trên trạng thái thật của tích hợp; phần DOM chạy trong Chrome không đầu
(nếu có; tên chứa «giao_dien» để bộ không-Chrome bỏ qua)."""

import html as html_lib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.helpers import entity_registry as er

from custom_components.r1_speaker.const import CONF_INTERCOM_KEY, SETTINGS_CARD_URL

from .test_bo_dam import _them

CARD = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www" / "r1-settings-card.js"
need_node = pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy mô hình thẻ")
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
SID = "sensor.r1_cai_dat"


def test_tep_the_ton_tai_dang_ky_dung_ten_va_khong_goi_loa():
    js = CARD.read_text(encoding="utf-8")
    assert 'customElements.define("r1-settings-card"' in js and "window.customCards" in js
    assert SETTINGS_CARD_URL == "/r1_speaker/r1-settings-card.js"
    assert "innerHTML" in js and "esc(" in js                    # dữ liệu ngoài đều qua esc()
    # Thẻ chỉ gọi dịch vụ HA: không mạng, không địa chỉ cứng, không đụng loa.
    for cam in ("fetch(", "XMLHttpRequest", "WebSocket(", "ws://", "http://", "https://",
                "192.168", "172.16", "10.0.", "sendBeacon", "eval("):
        assert cam not in js, cam


async def test_the_duoc_nap_vao_giao_dien_va_phuc_vu(hass, r1, hass_client_no_auth):
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    await _them(hass, r1)
    assert SETTINGS_CARD_URL not in hass.data[DATA_EXTRA_MODULE_URL]   # chỉ nạp qua tài nguyên Lovelace
    r = await (await hass_client_no_auth()).get(SETTINGS_CARD_URL)
    assert r.status == 200 and "r1-settings-card" in await r.text()
    assert r.headers["Cache-Control"] == "no-cache"             # cập nhật thẻ có hiệu lực ngay
    r2 = await (await hass_client_no_auth()).get(SETTINGS_CARD_URL.replace("/r1_speaker/", "/r1_speaker/b/12345/"))
    assert r2.status == 200 and await r2.text() == await r.text()           # đường dẫn đổi mỗi lần mở trang
    assert r2.headers["Cache-Control"] == "no-store"


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


def _node(expr, **payload):
    script = ("const c=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',"
              "()=>{const i=JSON.parse(s);console.log(JSON.stringify((" + expr + ")))})")
    out = subprocess.run(["node", "-e", script, str(CARD)], input=json.dumps(payload),
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _mo_hinh(gia, config=None):
    return _node("c.buildModel(i.hass,i.config)", hass=gia, config=config or {})


def _html(model, ui, lang="vi"):
    return _node("c.renderHtml(i.m,i.ui,c.TEXT[i.l],i.l)", m=model, ui=ui, l=lang)


CAI_DAT_AN = {"open": False, "tab": "audio"}


@need_node
async def test_mo_hinh_tu_trang_thai_that_ba_nhom(hass, r1):
    e = await _them(hass, r1, ha_url="http://ha.example:8123")
    m = _mo_hinh(_hass_gia(hass))
    assert m["found"] and not m["offline"] and m["settings"]["entity"] == SID
    a = m["audio"]
    assert a["volume"]["present"] and a["volume"]["entity"].startswith("number.")
    assert [b["label"] for b in a["bands"]] == ["60 Hz", "230 Hz", "910 Hz", "3.6 kHz", "14 kHz"]
    assert a["micGain"]["entity"] == "number.r1_tang_mic" and a["mute"]["entity"] == "switch.r1_tat_mic"
    assert a["noise"]["bat"] is False and a["agc"]["bat"] is False and a["limiter"]["bat"] is False
    li = m["light"]
    assert [f["key"] for f in li["functions"]] == [
        "cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi", "tat_mic"]
    assert li["sink"] == {"state": "mat_ket_noi", "ready": False, "lost": True, "svc": False, "error": None}
    assert [x["id"] for x in li["effects"]] == ["tho", "cau_vong", "nhap_nhay", "nhip_tim",
                                                "phao_hoa", "chop"]
    assert li["music"]["key"] == "phat_nhac" and li["music"]["enabled"] is False
    assert li["firmware"] == {"on": True, "luma": 50, "chroma": 60}
    c = m["conn"]
    assert (c["host"], c["port"], c["haUrl"], c["keySet"]) == ("127.0.0.1", r1.port,
                                                               "http://ha.example:8123", True)
    assert e.data[CONF_INTERCOM_KEY] not in json.dumps(m)         # mô hình KHÔNG chứa khoá


@need_node
async def test_muc_cai_dat_an_mac_dinh_va_chi_hien_khi_bam(hass, r1):
    await _them(hass, r1)
    m = _mo_hinh(_hass_gia(hass))
    ui = _node("c.initialUi()")
    assert ui == CAI_DAT_AN                                       # mặc định ĐÓNG
    dong = _html(m, ui)
    assert 'data-open' in dong and 'aria-expanded="false"' in dong
    for dau in ("data-panel", "data-tab", "data-vol", "data-eq", 'type="range"', "data-fn=",
                "data-apk-state", "data-music"):
        assert dau not in dong, dau                               # không có gì của bảng cài đặt
    ui = _node("c.reduceUi(i.ui,{type:'toggle'})", ui=ui)         # bấm nút mở
    assert ui["open"] is True
    mo = _html(m, ui)
    assert 'aria-expanded="true"' in mo and 'data-panel="audio"' in mo
    assert [t for t in ("audio", "light", "conn") if f'data-tab="{t}"' in mo] == ["audio", "light", "conn"]
    assert mo.count("data-eq=") == 5 and "data-vol" in mo and "data-mic-gain" in mo and "data-mute" in mo
    assert _node("c.reduceUi(i.ui,{type:'toggle'})", ui=ui) == {"open": False, "tab": "audio"}   # bấm lần nữa: ẩn
    # chọn nhóm: chỉ hiện nhóm đó; tab lạ bị bỏ qua
    anh = _html(m, _node("c.reduceUi(i.ui,{type:'tab',tab:'light'})", ui=ui))
    assert 'data-panel="light"' in anh and 'data-panel="audio"' not in anh
    assert _node("c.reduceUi(i.ui,{type:'tab',tab:'bay'})", ui=ui) == ui
    kn = _html(m, _node("c.reduceUi(i.ui,{type:'tab',tab:'conn'})", ui=ui))
    assert 'data-panel="conn"' in kn and "127.0.0.1" in kn


@need_node
async def test_nhom_anh_sang_hien_du_chuc_nang_hieu_ung_nhac_va_noi_ro_chua_co_dich_vu(hass, r1):
    await _them(hass, r1)
    m = _mo_hinh(_hass_gia(hass))
    h = _html(m, {"open": True, "tab": "light"})
    for fn in ("cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "loi", "tat_mic"):
        assert f'data-fn-block="{fn}"' in h, fn
        for field in ("enabled", "rim", "color", "effect", "brightness"):
            assert f'data-fn="{fn}" data-field="{field}"' in h, (fn, field)
        assert f'data-preview="{fn}"' in h
    assert 'data-fn-block="phat_nhac"' not in h and "data-music" in h   # nhạc có mục riêng
    for field in ("enabled", "effect", "brightness"):
        assert f'data-music-field="{field}"' in h
    assert "không trả lời" in h and 'class="sink warn"' in h          # nói thật: loa chưa nối (mat_ket_noi)
    assert h.count("kno.wled.ge") == 6                                # nguồn của từng hiệu ứng
    # Đèn firmware (mặc định): màu chọn trong bảng của firmware, có lời nhắn về làm tròn màu và độ sáng
    assert 'data-fn="cho" data-field="color"' in h and "<select data-fn=\"cho\" data-field=\"color\">" in h
    assert "Màu làm tròn về bảng màu của firmware" in h
    for ten in ("Đỏ", "Xanh lá", "Xanh dương", "Cam", "Tím", "Lục lam", "Trắng"):
        assert f">{ten}</option>" in h, ten
    assert "mặc định đề xuất, chưa đo" in h
    assert "Đèn theo nhạc của firmware" in h and "luma=50" in h       # đèn nhạc firmware: số đo; chỉnh ở thực thể
    # loa nối nhưng APK chưa báo đèn firmware (APK bản cũ): nói rõ và chỉ cách xử lý
    g = _hass_gia(hass)
    g["states"][SID]["attributes"]["anh_sang"]["dich_vu_den"] = "CHO_DICH_VU_DEN"
    h2 = _html(_mo_hinh(g), {"open": True, "tab": "light"})
    assert "APK mới nhất" in h2 and "den_loa.sh" not in h2 and 'class="sink warn"' in h2
    # đèn sẵn sàng thì không còn cảnh báo
    g = _hass_gia(hass)
    g["states"][SID]["attributes"]["anh_sang"]["dich_vu_den"] = "san_sang"
    assert 'class="sink ok"' in _html(_mo_hinh(g), {"open": True, "tab": "light"})


@need_node
async def test_nhom_ket_noi_khong_bao_gio_hien_khoa(hass, r1):
    e = await _them(hass, r1, ha_url="http://ha.example:8123")
    h = _html(_mo_hinh(_hass_gia(hass)), {"open": True, "tab": "conn"})
    assert e.data[CONF_INTERCOM_KEY] not in h and e.data["mic_listen_key"] not in h
    assert "HA tự sinh" in h and "http://ha.example:8123" in h and str(r1.port) in h
    assert str(e.data["mic_listen_port"]) in h                     # cổng nghe tự cấp có hiện
    assert "data-apk-show" not in h                                # người xem không phải quản trị: không có nút lệnh
    assert "Chưa nối" in h                                         # APK chưa nối vào HA


@need_node
async def test_hanh_dong_thanh_lenh_goi_dich_vu_ha_khong_goi_loa(hass, r1):
    await _them(hass, r1)
    m = _mo_hinh(_hass_gia(hass))

    def call(**a):
        return _node("c.makeCall(i.m,i.a)", m=m, a=a)

    assert call(type="vol", value="9") == ["number", "set_value",
                                           {"entity_id": m["audio"]["volume"]["entity"], "value": 9}]
    assert call(type="eq", entity="number.phicomm_r1_eq_60_hz", value="-200") == [
        "number", "set_value", {"entity_id": "number.phicomm_r1_eq_60_hz", "value": -200}]
    assert call(type="micgain", value="15") == ["number", "set_value", {
        "entity_id": "number.r1_tang_mic", "value": 15}]
    assert call(type="mute", on=True) == ["switch", "turn_on", {"entity_id": "switch.r1_tat_mic"}]
    assert call(type="mute", on=False)[1] == "turn_off"
    assert call(type="fn", key="nghe", field="color", value="#00FF00") == [
        "r1_speaker", "set_light_function", {"entity_id": SID, "function": "nghe", "color": "#00FF00"}]
    assert call(type="fn", key="loi", field="brightness", value="35")[2]["brightness"] == 35
    assert call(type="fn", key="loi", field="rim", value=False)[2]["rim"] is False
    assert call(type="fn", key="loi", field="enabled", value=True)[2]["enabled"] is True
    assert call(type="music", field="effect", value="tho") == [
        "r1_speaker", "set_music_light", {"entity_id": SID, "effect": "tho"}]
    assert call(type="preview", key="tat_mic") == [
        "r1_speaker", "preview_light", {"entity_id": SID, "function": "tat_mic"}]
    assert call(type="fn", key="khong_co", field="rim", value=True) is None   # chức năng lạ: không gọi
    assert call(type="bay") is None
    # không thấy sensor cài đặt → không gửi lệnh đèn nào
    sans = _node("c.makeCall(i.m,i.a)", m={**m, "settings": {"entity": None, "present": False}},
                 a={"type": "preview", "key": "nghe"})
    assert sans is None


@need_node
async def test_the_escape_du_lieu_ngoai_va_chiu_thuc_the_mat_thuoc_tinh(hass, r1):
    await _them(hass, r1)
    g = _hass_gia(hass)
    bay = '<img src=x onerror=alert(1)>'
    at = g["states"][SID]["attributes"]
    at["anh_sang"]["hieu_ung"][0]["ten"] = bay
    at["anh_sang"]["hieu_ung"][0]["nguon"] = bay
    at["anh_sang"]["loi_dich_vu"] = bay
    at["ket_noi"]["host"] = bay
    at["anh_sang"]["chuc_nang"]["nghe"]["color"] = '"><script>alert(1)</script>'
    m = _mo_hinh(g)
    for tab in ("audio", "light", "conn"):
        h = _html(m, {"open": True, "tab": tab})
        assert "<img" not in h and "<script" not in h, tab
    # loa mất kết nối: các thực thể unavailable, thuộc tính biến mất — thẻ vẫn dựng được
    g2 = _hass_gia(hass)
    for st in g2["states"].values():
        st["state"], st["attributes"] = "unavailable", {}
    m2 = _mo_hinh(g2)
    assert m2["found"] and m2["offline"] and m2["audio"]["volume"]["available"] is False
    assert m2["light"]["functions"] == [] and m2["light"]["sink"]["ready"] is False
    for tab in ("audio", "light", "conn"):
        assert "data-panel" in _html(m2, {"open": True, "tab": tab})
    assert _mo_hinh({"entities": {}, "states": {}})["found"] is False
    assert "Không tìm thấy" in _html(_mo_hinh({"entities": {}, "states": {}}), CAI_DAT_AN)
    assert _mo_hinh(_hass_gia(hass), {"device_id": "khong-co"})["found"] is False


# ── Giao diện thật trong Chrome không đầu ──────────────────────────────────────

PAGE = """<!doctype html><meta charset="utf-8"><body><div id="out">CHUA CHAY</div>
<script src="file://@CARD@"></script>
<script>
const FN=["cho","nghe","nghi","phan_hoi","dam_thoai","phat_nhac","loi","tat_mic"];
const prof={}; FN.forEach(k=>prof[k]={enabled:k!=="cho",rim:k==="nghe",color:"#0000ff",effect:"none",brightness:60,mac_dinh:true});
const entities={}, states={}, calls=[];
function add(id,tk,state,attrs){entities[id]={platform:"r1_speaker",translation_key:tk,device_id:"d1"};states[id]={state,attributes:attrs||{}};}
add("sensor.r1_cai_dat","settings","cho",{anh_sang:{chuc_nang:prof,dang_ap_dung:"nghe",dich_vu_den:"CHO_PHIA_LOA",loi_dich_vu:null,
 hieu_ung:[{id:"tho",ten:"Thở",ten_en:"Breathe",nguon:"U1",vien:""}],den_nhac_firmware:{bat:true,luma:50,chroma:60}},
 am_thanh:{khu_tap:{bat:false},agc:{bat:false},han_dinh:{bat:false}},
 ket_noi:{host:"h",cong:1,khoa_bo_dam:"da_co",khoa_nghe_mic:"da_co",cong_nghe_mic:18765,apk_dang_noi:true,tuy_chon:"/config/x"}});
add("number.r1_am_luong","volume","7",{min:0,max:15,step:1});
add("number.r1_tang_mic","mic_gain","12",{min:0,max:30,step:1});
add("switch.r1_tat_mic","mute","off");
["a","b"].forEach((k,i)=>add("number.eq_"+k,"eq_band","0",{band:i,label:"B"+i,min:-1500,max:1500,step:10}));
const mk=()=>({entities:{...entities},states:{...states},language:"vi",callService:(d,s,x)=>calls.push([d,s,x])});
const card=document.createElement("r1-settings-card"); document.body.appendChild(card); card.setConfig({});
card.hass=mk();
const sr=card.shadowRoot, q=s=>sr.querySelector(s);
const dau={panel:!!q("[data-panel]"), tabs:sr.querySelectorAll("[data-tab]").length, nut:q("[data-open]").getAttribute("aria-expanded")};
q("[data-open]").click();                       // mở
const mo={panel:q("[data-panel]").dataset.panel, tabs:sr.querySelectorAll("[data-tab]").length,
 eq:sr.querySelectorAll("[data-eq]").length, nut:q("[data-open]").getAttribute("aria-expanded")};
q("[data-vol]").value="11"; q("[data-vol]").dispatchEvent(new Event("change"));
q("[data-mute]").checked=true; q("[data-mute]").dispatchEvent(new Event("change"));
q('[data-tab="light"]').click();                // sang nhóm Ánh sáng
const anh={panel:q("[data-panel]").dataset.panel, blocks:sr.querySelectorAll("[data-fn-block]").length,
 sink:q("[data-sink]").textContent};
const c=q('[data-fn="nghe"][data-field="color"]'); c.value="#00ff00"; c.dispatchEvent(new Event("change"));
const b=q('[data-fn="loi"][data-field="brightness"]'); b.value="35"; b.dispatchEvent(new Event("change"));
const r=q('[data-fn="nghe"][data-field="rim"]'); r.checked=false; r.dispatchEvent(new Event("change"));
q('[data-music-field="enabled"]').checked=true; q('[data-music-field="enabled"]').dispatchEvent(new Event("change"));
q('[data-preview="tat_mic"]').click();
q('[data-tab="conn"]').click();
const kn={panel:q("[data-panel]").dataset.panel, apk:q("[data-apk-state]").textContent, nutLenh:!!q("[data-apk-show]")};
q("[data-open]").click();                       // đóng lại
const cuoi={panel:!!q("[data-panel]"), nut:q("[data-open]").getAttribute("aria-expanded")};
document.getElementById("out").textContent=JSON.stringify({dau,mo,anh,kn,cuoi,calls});
</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
def test_giao_dien_the_cai_dat_an_hien_ba_nhom_va_goi_dich_vu(tmp_path):
    page = tmp_path / "cai_dat.html"
    page.write_text(PAGE.replace("@CARD@", str(CARD)), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
         "--virtual-time-budget=3000", "--dump-dom", f"file://{page}"],
        capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    assert r["dau"] == {"panel": False, "tabs": 0, "nut": "false"}          # mặc định ẨN
    assert r["mo"] == {"panel": "audio", "tabs": 3, "eq": 2, "nut": "true"}   # bấm → hiện, ba nhóm
    assert r["anh"]["panel"] == "light" and r["anh"]["blocks"] == 7
    assert "CHƯA sáng" in r["anh"]["sink"]
    assert r["kn"] == {"panel": "conn", "apk": "Đang nối vào HA", "nutLenh": False}   # hass giả không phải quản trị
    assert r["cuoi"] == {"panel": False, "nut": "false"}                    # bấm lại → ẩn
    sid = "sensor.r1_cai_dat"
    assert r["calls"] == [
        ["number", "set_value", {"entity_id": "number.r1_am_luong", "value": 11}],
        ["switch", "turn_on", {"entity_id": "switch.r1_tat_mic"}],
        ["r1_speaker", "set_light_function", {"entity_id": sid, "function": "nghe", "color": "#00ff00"}],
        ["r1_speaker", "set_light_function", {"entity_id": sid, "function": "loi", "brightness": 35}],
        ["r1_speaker", "set_light_function", {"entity_id": sid, "function": "nghe", "rim": False}],
        ["r1_speaker", "set_music_light", {"entity_id": sid, "enabled": True}],
        ["r1_speaker", "preview_light", {"entity_id": sid, "function": "tat_mic"}]]


async def test_the_khong_bao_gio_phuc_vu_tep_nen_gz_dung_canh(tmp_path):
    """Một ``.js.gz`` cũ còn sót cạnh tệp thẻ từng che mọi bản cập nhật (điện thoại thấy thẻ cũ):
    máy chủ phải luôn trả nội dung của chính tệp ``.js`` dù trình duyệt nhận gzip."""
    import gzip

    from aiohttp.test_utils import make_mocked_request

    from custom_components.r1_speaker import _TheView
    js = tmp_path / "r1-the.js"
    js.write_text("console.log('MOI');", encoding="utf-8")
    (tmp_path / "r1-the.js.gz").write_bytes(gzip.compress(b"console.log('CU');"))
    view = _TheView("/r1_speaker/r1-the.js", js)
    for ban in (None, "123"):
        r = await view.get(make_mocked_request("GET", "/x", headers={"Accept-Encoding": "gzip, br"}), ban)
        assert r.body == b"console.log('MOI');" and "Content-Encoding" not in r.headers
        assert r.content_type == "text/javascript"


def test_thu_muc_the_khong_co_tep_nen_bo_roi():
    www = CARD.parent
    assert not list(www.glob("*.gz")) and not list(www.glob("*.br")), "tệp nén cũ sẽ che bản cập nhật"


@need_node
async def test_quan_tri_thay_nut_lenh_apk_va_lenh_chi_hien_khi_da_lay(hass, r1):
    e = await _them(hass, r1)
    g = _hass_gia(hass)
    g["user"] = {"is_admin": True}
    m = _mo_hinh(g)
    assert m["conn"]["admin"] is True and m["conn"]["listenKeySet"] is True
    h = _html(m, {"open": True, "tab": "conn"})
    assert "data-apk-show" in h and "data-apk-cmd" not in h        # chưa bấm: chưa có lệnh (khoá chưa rời HA)
    m["conn"]["lenh"] = "adb ... --es khoa KHOA-GIA"
    h = _html(m, {"open": True, "tab": "conn"})
    assert "data-apk-cmd" in h and "KHOA-GIA" in h and "Ẩn lệnh" in h
    assert e.data["mic_listen_key"] not in json.dumps(_mo_hinh(g))  # mô hình sinh từ trạng thái không chứa khoá


@need_node
async def test_cai_dat_chi_tiet_chinh_duoc_o_the_va_thanh_lenh_dich_vu(hass, r1):
    e = await _them(hass, r1)
    g = _hass_gia(hass)
    m = _mo_hinh(g)
    adv = m["audio"]["adv"]
    assert len(adv) == 19 and {o["nhom"] for o in adv} == {"thoai", "khu_tap", "agc", "han_dinh", "song_cong"}
    h = _html(m, {"open": True, "tab": "audio"})
    assert h.count('data-opt="') == 19 and h.count('data-bool="1"') == 4      # 4 công tắc, 15 ô số
    assert "Ngưỡng có tiếng người" in h and "Cắt vọng" in h or "cắt vọng" in h
    assert 'min="0.2" max="10" step="0.1"' in h                              # khoảng lấy từ HA, không mã cứng ở thẻ
    sid = m["settings"]["entity"]

    def call(**a):
        return _node("c.makeCall(i.m,i.a)", m=m, a=a)

    assert call(type="opt", key="talk_silence_s", bool=False, value="0.8") == [
        "r1_speaker", "set_advanced_option", {"entity_id": sid, "key": "talk_silence_s", "value": 0.8}]
    assert call(type="opt", key="noise_suppress", bool=True, value=True) == [
        "r1_speaker", "set_advanced_option", {"entity_id": sid, "key": "noise_suppress", "value": True}]
    assert call(type="opt", key="talk_silence_s", bool=False, value="abc") is None      # không phải số: không gọi gì
    # mục đã chỉnh khác mặc định được đánh dấu *
    g["states"][sid]["attributes"]["am_thanh"]["nang_cao"][1]["v"] = 0.8
    assert " *" in _html(_mo_hinh(g), {"open": True, "tab": "audio"})
