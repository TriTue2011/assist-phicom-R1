"""NV302 — cài đặt mới của 0.12.0 và cài đặt khởi động lại (NV288) trên THẺ «Cài đặt»; mỗi cài đặt là MỘT thực thể chuẩn
(switch / select / number / time) lưu vào ``entry.options`` — cùng nguồn với hộp tuỳ chọn HA. Thẻ chỉ gọi dịch vụ chuẩn của thực thể.

Phần Python dựng tích hợp thật (hass thật của bộ test); phần thẻ chạy mô hình bằng Node trên trạng thái THẬT của các thực thể; phần
giao diện chạy trong Chrome không đầu ở bề rộng 375 px: không tràn ngang, chữ ≥ 14 px, vùng chạm ≥ 44 px."""

import html as html_lib
import json
import re
import subprocess

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.r1_speaker import const

from .test_bo_dam import _them
from .test_nv288_khoi_dong_lai import DevGia, _mui_gio, dung, gio, tien  # noqa: F401
from .test_the_cai_dat import CARD, CHROME, _hass_gia, _html, _mo_hinh, _node, need_node
from .test_tuy_chon import _luu

SW = "switch.{}"
THU = ["t2", "t3", "t4", "t5", "t6", "t7", "cn"]


def _eid(hass, domain, khoa):
    """Thực thể của tích hợp theo khoá dịch (đúng cách thẻ tìm)."""
    kq = [e.entity_id for e in er.async_get(hass).entities.values()
          if e.platform == const.DOMAIN and e.domain == domain and e.translation_key == khoa]
    assert len(kq) == 1, (domain, khoa, kq)
    return kq[0]


async def _goi(hass, domain, dich_vu, **dl):
    await hass.services.async_call(domain, dich_vu, dl, blocking=True)


# ── Thực thể chuẩn ──────────────────────────────────────────────────────────────

async def test_du_thuc_the_chuan_va_gia_tri_mac_dinh(hass, r1):
    await _them(hass, r1)
    mong = {("switch", "tin_nguoc_nhac"): "off", ("switch", "ha_nhac_xuong"): "off", ("switch", "kdl_bat"): "off",
            ("switch", "kdl_khi_treo"): "off", ("number", "ha_nhac_nac"): "5", ("number", "cong_airplay"): "5012", ("select", "duong_phat"): "dlna",
            ("time", "kdl_gio"): "04:00:00", **{("switch", f"kdl_ngay_{m}"): "on" for m in THU}}
    for (domain, khoa), trang_thai in mong.items():
        assert hass.states.get(_eid(hass, domain, khoa)).state == trang_thai, (domain, khoa)
    assert hass.states.get(_eid(hass, "select", "duong_phat")).attributes["options"] == list(const.DUONG_PHAT_GIA_TRI)


async def test_doi_qua_thuc_the_ghi_vao_tuy_chon_va_gia_tri_mac_dinh_thi_bo_khoa(hass, r1):
    e = await _them(hass, r1)
    await _goi(hass, "select", "select_option", entity_id=_eid(hass, "select", "duong_phat"), option="airplay_truoc")
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "tin_nguoc_nhac"))
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "ha_nhac_xuong"))
    await _goi(hass, "number", "set_value", entity_id=_eid(hass, "number", "ha_nhac_nac"), value=9)
    await _goi(hass, "number", "set_value", entity_id=_eid(hass, "number", "cong_airplay"), value=5013)
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_bat"))
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_khi_treo"))
    await _goi(hass, "time", "set_value", entity_id=_eid(hass, "time", "kdl_gio"), time="05:30:00")
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_ngay_t3"))
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_ngay_cn"))
    assert dict(e.options) == {
        "duong_phat": "airplay_truoc", "tts_song_song_airplay": True, "ha_nhac_xuong": True, "ha_nhac_nac": 9, "airplay_port": 5013,
        "khoi_dong_lai_bat": True, "khoi_dong_lai_khi_treo": True, "khoi_dong_lai_gio": "05:30",
        "khoi_dong_lai_ngay": ["t2", "t4", "t5", "t6", "t7"]}
    assert hass.states.get(_eid(hass, "switch", "kdl_ngay_t3")).state == "off"
    assert hass.states.get(_eid(hass, "time", "kdl_gio")).state == "05:30:00"
    # đưa về mặc định hết: khoá biến mất khỏi tuỳ chọn (như hộp tuỳ chọn)
    await _goi(hass, "select", "select_option", entity_id=_eid(hass, "select", "duong_phat"), option="dlna")
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "tin_nguoc_nhac"))
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "ha_nhac_xuong"))
    await _goi(hass, "number", "set_value", entity_id=_eid(hass, "number", "ha_nhac_nac"), value=5)
    await _goi(hass, "number", "set_value", entity_id=_eid(hass, "number", "cong_airplay"), value=5012)
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_bat"))
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_khi_treo"))
    await _goi(hass, "time", "set_value", entity_id=_eid(hass, "time", "kdl_gio"), time="04:00:00")
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_ngay_t3"))
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_ngay_cn"))
    assert dict(e.options) == {}


async def test_doi_o_hop_tuy_chon_thuc_the_thay_ngay(hass, r1):
    e = await _them(hass, r1)
    _res, kq = await _luu(hass, e, host="127.0.0.1", port=r1.port, duong_phat="airplay", tts_song_song_airplay=True,
                          ha_nhac_xuong=True, ha_nhac_nac=3, khoi_dong_lai_bat=True, khoi_dong_lai_gio="23:15:00",
                          khoi_dong_lai_ngay=["t7", "cn"], khoi_dong_lai_khi_treo=True)
    assert kq["type"].value == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get(_eid(hass, "select", "duong_phat")).state == "airplay"
    assert hass.states.get(_eid(hass, "switch", "tin_nguoc_nhac")).state == "on"
    assert hass.states.get(_eid(hass, "switch", "ha_nhac_xuong")).state == "on"
    assert float(hass.states.get(_eid(hass, "number", "ha_nhac_nac")).state) == 3
    assert hass.states.get(_eid(hass, "switch", "kdl_bat")).state == "on"
    assert hass.states.get(_eid(hass, "switch", "kdl_khi_treo")).state == "on"
    assert hass.states.get(_eid(hass, "time", "kdl_gio")).state == "23:15:00"
    assert [hass.states.get(_eid(hass, "switch", f"kdl_ngay_{m}")).state for m in THU] == ["off"] * 5 + ["on", "on"]


async def test_luu_hop_tuy_chon_khong_lam_roi_cai_dat_da_dat_bang_the(hass, r1):
    """Đổi ở thẻ (thực thể) rồi mở hộp tuỳ chọn và lưu một ô khác: cài đặt từ thẻ phải còn."""
    e = await _them(hass, r1)
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_bat"))
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_ngay_t3"))
    await _goi(hass, "time", "set_value", entity_id=_eid(hass, "time", "kdl_gio"), time="02:45:00")
    _res, kq = await _luu(hass, e, host="127.0.0.1", port=r1.port, ha_url="")
    assert kq["type"].value == "create_entry"
    assert e.options["khoi_dong_lai_bat"] is True and e.options["khoi_dong_lai_gio"] == "02:45"
    assert e.options["khoi_dong_lai_ngay"] == ["t2", "t4", "t5", "t6", "t7", "cn"]


async def test_cong_tac_the_dieu_khien_lich_that_su(hass, r1, freezer):
    """Đường đầu-cuối: bật lịch + chọn giờ + bỏ một thứ BẰNG THỰC THỂ rồi cho giờ giả trôi; loa khởi động lại đúng ngày đúng giờ."""
    e, dev = await dung(hass, r1, freezer, gio("2026-11-03", 1, 0))
    await _goi(hass, "time", "set_value", entity_id=_eid(hass, "time", "kdl_gio"), time="02:00:00")
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_ngay_t3"))      # 03/11/2026 là thứ ba
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_bat"))
    t = await tien(hass, freezer, gio("2026-11-03", 1, 0), gio("2026-11-03", 3, 0))
    assert dev.reboot_goi == 0                                           # thứ ba đã bỏ chọn
    await tien(hass, freezer, t, gio("2026-11-04", 2, 5))
    assert dev.reboot_goi == 1                                           # thứ tư thì chạy


async def test_chon_duong_phat_lam_thay_doi_hanh_vi_phat(hass, r1):
    from custom_components.r1_speaker.settings import duong_phat, ha_nhac_nac, ha_nhac_xuong, tts_song_song_airplay
    e = await _them(hass, r1)
    await _goi(hass, "select", "select_option", entity_id=_eid(hass, "select", "duong_phat"), option="airplay")
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "ha_nhac_xuong"))
    await _goi(hass, "number", "set_value", entity_id=_eid(hass, "number", "ha_nhac_nac"), value=7)
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "tin_nguoc_nhac"))
    # đúng các hàm đọc mà media_player dùng khi phát
    assert (duong_phat(e), ha_nhac_xuong(e), ha_nhac_nac(e), tts_song_song_airplay(e)) == ("airplay", True, 7, True)
    with pytest.raises(Exception):
        await _goi(hass, "select", "select_option", entity_id=_eid(hass, "select", "duong_phat"), option="bluetooth")
    with pytest.raises(Exception):
        await _goi(hass, "number", "set_value", entity_id=_eid(hass, "number", "ha_nhac_nac"), value=15)


# ── Thẻ: mô hình + lệnh gọi (Node, trạng thái thật) ────────────────────────────────

@need_node
async def test_mo_hinh_the_doc_dung_thuc_the_va_lenh_goi_la_dich_vu_chuan(hass, r1):
    await _them(hass, r1)
    await _goi(hass, "switch", "turn_on", entity_id=_eid(hass, "switch", "kdl_bat"))
    await _goi(hass, "switch", "turn_off", entity_id=_eid(hass, "switch", "kdl_ngay_t3"))
    m = _mo_hinh(_hass_gia(hass))
    S = m["sys"]
    assert S["play"]["path"]["value"] == "dlna" and S["play"]["path"]["options"] == list(const.DUONG_PHAT_GIA_TRI)
    assert S["play"]["parallel"]["on"] is False and S["play"]["duck"]["on"] is False and S["play"]["duckNac"]["value"] == 5
    R = S["restart"]
    assert R["enabled"]["on"] is True and R["onHang"]["on"] is False and R["time"]["value"] == "04:00"
    assert [(d["code"], d["on"]) for d in R["days"]] == [(m_, m_ != "t3") for m_ in THU]
    assert R["button"]["entity"] == "button.r1_khoi_dong_lai" and R["resp"]["reason"] in ("phan_hoi", "chua_biet")
    ids = S["entities"]
    assert len(ids) == len(set(ids)) == 9 + 7 and all(i.split(".")[0] in ("switch", "select", "number", "time", "button") for i in ids)

    def goi(a):
        return _node("c.makeCall(i.m,i.a)", m=m, a=a)

    assert goi({"type": "sw", "entity": R["enabled"]["entity"], "on": False}) == ["switch", "turn_off", {"entity_id": R["enabled"]["entity"]}]
    assert goi({"type": "sel", "entity": S["play"]["path"]["entity"], "value": "airplay"}) == [
        "select", "select_option", {"entity_id": S["play"]["path"]["entity"], "option": "airplay"}]
    assert goi({"type": "sysnum", "entity": S["play"]["duckNac"]["entity"], "value": "8"}) == [
        "number", "set_value", {"entity_id": S["play"]["duckNac"]["entity"], "value": 8}]
    assert goi({"type": "time", "entity": R["time"]["entity"], "value": "06:15"}) == [
        "time", "set_value", {"entity_id": R["time"]["entity"], "time": "06:15:00"}]
    assert goi({"type": "reboot", "entity": R["button"]["entity"]}) == ["button", "press", {"entity_id": "button.r1_khoi_dong_lai"}]
    # chỉ thực thể của thẻ này: không thể mượn thẻ để bật/tắt thứ khác
    assert goi({"type": "sw", "entity": "switch.nha_bep_den", "on": True}) is None
    assert goi({"type": "time", "entity": R["time"]["entity"], "value": "6h15"}) is None
    assert goi({"type": "sel", "entity": "light.x", "value": "a"}) is None


@need_node
async def test_html_the_co_muc_phat_va_khoi_dong_lai_voi_chu_thich_va_khong_chen_ma(hass, r1):
    await _them(hass, r1)
    g = _hass_gia(hass)
    sid = _eid(hass, "sensor", "khoi_dong_lai_cuoi")
    g["states"][sid] = {"state": "2026-11-04T04:00:05+07:00", "attributes": {
        "ly_do": "lich", "ket_qua": "ok", "ke_tiep": "2026-11-05T04:00:00+07:00", "dang_hoan": '"><script>alert(1)</script>'}}
    ui = _node("c.reduceUi({open:true,tab:'audio',thu:{zone:'day',effect:null,params:{},secs:8}},{type:'tab',tab:'sys'})")
    h = _html(_mo_hinh(g), ui)
    assert 'data-panel="sys"' in h and "Phát nhạc &amp; tin báo" in h and "Khởi động lại loa" in h
    assert h.count("data-day=") == 7 and 'aria-pressed="true"' in h and "data-reboot=" in h and 'type="time"' in h
    assert "Chưa đo trên loa thật: chỉ bật khi muốn thử" in h                 # mỗi mục một dòng giải thích bằng tiếng thường
    assert "lý do: lịch" in h and "data-next" in h and "<script" not in h
    en = _html(_mo_hinh(g), ui, "en")
    assert "Restart now" in en and "Playback path" in en
    assert 'data-tab="sys"' in h and '"sys"' in json.dumps(_node("c.TABS"))


# ── Giao diện thật trong Chrome không đầu, 375 px ─────────────────────────────────

PAGE = """<!doctype html><meta name="viewport" content="width=375"><body style="margin:0"><div id="out">CHUA CHAY</div><div id="khung" style="width:375px"></div>
<script src="file://@CARD@"></script>
<script>
const G=@GIA@, calls=[];
const card=document.createElement("r1-settings-card"); document.getElementById("khung").appendChild(card); card.setConfig({});
card.hass={entities:G.entities,states:G.states,language:"vi",callService:(d,s,x)=>calls.push([d,s,x])};
const sr=card.shadowRoot, q=s=>sr.querySelector(s);
q("[data-open]").click(); q('[data-tab="sys"]').click();
const kt=[]; const nho=(m)=>kt.push(m);
// Chrome không đầu không thu cửa sổ dưới 500 px: đo trong khung cố định 375 px (cùng bề rộng điện thoại).
const W=document.getElementById("khung").getBoundingClientRect().width;
const tran=Math.max(card.scrollWidth, q("ha-card").scrollWidth)>W;
const nho_=[]; let n=0;
sr.querySelectorAll("*").forEach(el=>{
  const cs=getComputedStyle(el), r=el.getBoundingClientRect();
  if(r.width===0||r.height===0||cs.display==="none") return;
  n++;
  if(r.right>W+1||r.left<-1) nho_.push("tran:"+el.tagName+"."+el.className+":"+Math.round(r.right));
  const coChu=[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
  if(coChu&&parseFloat(cs.fontSize)<14) nho_.push("chu:"+el.tagName+":"+cs.fontSize+":"+el.textContent.trim().slice(0,20));
  if(el.matches("button,select,input[type=time],input[type=range],summary,input[type=number]")&&r.height<44) nho_.push("chamH:"+el.tagName+":"+Math.round(r.height));
  if(el.matches("button")&&r.width<44) nho_.push("chamW:"+el.className+":"+Math.round(r.width));
  if(el.matches("input[type=checkbox]")&&el.closest(".row").getBoundingClientRect().height<44) nho_.push("chamRow");
});
const dem={ngay:sr.querySelectorAll("[data-day]").length, sw:sr.querySelectorAll("[data-sys-sw]").length};
const cl=(s)=>{q(s).click();};
q('[data-day]').click();
const sel=q("[data-sys-sel]"); sel.value="airplay"; sel.dispatchEvent(new Event("change"));
const tm=q("[data-sys-time]"); tm.value="05:10"; tm.dispatchEvent(new Event("change"));
const nb=q("[data-sys-num]"); nb.value="5099"; nb.dispatchEvent(new Event("change"));
const sw0=q("[data-sys-sw]"); sw0.checked=!sw0.checked; sw0.dispatchEvent(new Event("change"));
window.confirm=()=>true; q("[data-reboot]").click();
document.getElementById("out").textContent=JSON.stringify({tran,vande:nho_,dem,calls,n,W});
</script>"""


@pytest.mark.skipif(CHROME is None, reason="cần Chrome/Chromium")
async def test_giao_dien_375px_khong_tran_chu_14_cham_44_va_goi_dich_vu(hass, r1, tmp_path):
    await _them(hass, r1)
    page = tmp_path / "sys.html"
    page.write_text(PAGE.replace("@CARD@", str(CARD)).replace("@GIA@", json.dumps(_hass_gia(hass))), encoding="utf-8")
    out = subprocess.run(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--window-size=375,1400",
         "--virtual-time-budget=3000", "--dump-dom", f"file://{page}"], capture_output=True, text=True, timeout=60)
    m = re.search(r'<div id="out">(.*?)</div>', out.stdout, re.S)
    assert m, out.stderr[-500:]
    r = json.loads(html_lib.unescape(m.group(1)))
    assert r["vande"] == [] and r["tran"] is False, r["vande"]
    assert r["W"] == 375 and r["n"] > 40                                   # thật sự đã đo trong khung 375 px
    assert r["dem"] == {"ngay": 7, "sw": 4}
    loai = [c[:2] for c in r["calls"]]
    assert loai == [["switch", "turn_off"], ["select", "select_option"], ["time", "set_value"], ["number", "set_value"], ["switch", "turn_on"], ["button", "press"]]
    assert r["calls"][1][2]["option"] == "airplay" and r["calls"][2][2]["time"] == "05:10:00" and r["calls"][3][2]["value"] == 5099
