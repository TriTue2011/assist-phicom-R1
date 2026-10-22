"""Thẻ Lovelace r1-eq-card: tệp được phục vụ + nạp, dữ liệu thực thể đúng hợp đồng với thẻ, và
mô hình dữ liệu của thẻ (chạy bằng Node trên trạng thái thật của tích hợp).

Thẻ KHÔNG gọi loa: chỉ đọc thực thể HA. Test không chạm loa thật."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.helpers import entity_registry as er

from custom_components.r1_speaker.const import CARD_URL, CONFIRMED_COMMANDS

from .du_lieu_that import GET_EQ_CONFIG
from .test_bo_dam import _them

CARD = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www" / "r1-eq-card.js"
BANDS = [f"number.phicomm_r1_eq_{n}" for n in ("60_hz", "230_hz", "910_hz", "3_6_khz", "14_khz")]
need_node = pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy mô hình thẻ")


def test_tep_the_ton_tai_va_dang_ky_dung_ten():
    js = CARD.read_text(encoding="utf-8")
    assert 'customElements.define("r1-eq-card"' in js
    assert "customCards.push" not in js and "r1_speaker" in js   # thẻ con không tự khai báo: bộ chọn chỉ còn r1-card
    assert CARD_URL == "/r1_speaker/r1-eq-card.js"


async def test_the_duoc_nap_vao_giao_dien_va_phuc_vu(hass, r1, hass_client_no_auth):
    hass.data[DATA_EXTRA_MODULE_URL] = set()          # như khi component frontend đã chạy
    await _them(hass, r1)
    assert CARD_URL not in hass.data[DATA_EXTRA_MODULE_URL]   # KHÔNG nạp sớm làm module phụ (HA không thấy phần tử)
    cl = await hass_client_no_auth()
    r = await cl.get(CARD_URL)
    assert r.status == 200
    assert "r1-eq-card" in await r.text()


async def test_thuoc_tinh_thuc_the_cho_the(hass, r1):
    await _them(hass, r1)
    for i, eid in enumerate(BANDS):
        st = hass.states.get(eid)
        assert st.attributes["band"] == i
        assert st.attributes["confirmed"] is True and st.attributes["command"] == "set_eq_bandlevel"
        assert st.attributes["min"] == -1500 and st.attributes["max"] == 1500   # từ loa báo
    assert [float(hass.states.get(e).state) for e in BANDS] == [
        b["BandLevel"] for b in GET_EQ_CONFIG["eq"]["Bands"]["list"]]
    # Chỉ các lệnh đã xác nhận bằng ghi thật (set_volume: chủ máy nghe xác nhận 22/10/2026, qua APK AudioManager).
    assert CONFIRMED_COMMANDS == {"set_eq_bandlevel", "set_bass_enable", "set_volume"}
    assert hass.states.get("switch.phicomm_r1_bass_boost").attributes["confirmed"] is True
    for eid in ("switch.phicomm_r1_eq", "switch.phicomm_r1_loudness",
                "number.phicomm_r1_bass_strength", "number.phicomm_r1_loudness_gain"):
        assert hass.states.get(eid).attributes["confirmed"] is False, eid
    preset = hass.states.get("select.phicomm_r1_eq_preset")
    assert preset.attributes["selectable"] is True         # chọn preset = ghi 5 dải đã xác nhận
    assert len(preset.attributes["options"]) == 10 and preset.state == "unknown"  # -1


def _hass_gia(hass, ghi_chu_mat_thuoc_tinh=False):
    """Đối tượng `hass` rút gọn như frontend thấy: entities (đăng ký) + states."""
    reg = er.async_get(hass)
    ents, states = {}, {}
    for e in reg.entities.values():
        if e.platform != "r1_speaker":
            continue
        ents[e.entity_id] = {"entity_id": e.entity_id, "platform": e.platform,
                             "translation_key": e.translation_key, "device_id": e.device_id}
        st = hass.states.get(e.entity_id)
        states[e.entity_id] = ({"state": "unavailable", "attributes": {}}
                               if ghi_chu_mat_thuoc_tinh
                               else {"state": st.state, "attributes": dict(st.attributes)})
    return {"entities": ents, "states": states, "language": "vi"}


def _mo_hinh(hass_gia, config=None):
    script = ("const c=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',"
              "()=>{const i=JSON.parse(s);console.log(JSON.stringify(c.buildModel(i.hass,i.config)))})")
    out = subprocess.run(["node", "-e", script, str(CARD)], input=json.dumps(
        {"hass": hass_gia, "config": config or {}}), capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@need_node
async def test_mo_hinh_the_tu_trang_thai_that(hass, r1):
    await _them(hass, r1)
    m = _mo_hinh(_hass_gia(hass))
    eq = GET_EQ_CONFIG["eq"]
    assert m["found"] and not m["offline"]
    assert [b["value"] for b in m["bands"]] == [b["BandLevel"] for b in eq["Bands"]["list"]]
    assert [b["label"] for b in m["bands"]] == ["60 Hz", "230 Hz", "910 Hz", "3.6 kHz", "14 kHz"]
    assert (m["bandMin"], m["bandMax"]) == (-1500, 1500)
    assert m["eq"]["on"] is True and m["bass"]["on"] is False and m["loudness"]["on"] is False
    assert m["bassStrength"]["value"] == 200 and m["loudnessGain"]["value"] == 200
    # nhãn «chưa xác nhận»: chỉ băng EQ và bass_enable đã xác nhận
    assert all(b["confirmed"] for b in m["bands"]) and m["bass"]["confirmed"]
    assert not any(m[k]["confirmed"] for k in ("eq", "loudness", "bassStrength", "loudnessGain"))
    # preset: chọn được (ghi 5 dải theo bảng firmware); 5 dải thử nghiệm không trùng preset nào
    assert m["preset"]["options"][:3] == ["Normal", "Classical", "Dance"]
    assert m["preset"]["current"] is None and m["preset"]["selectable"] is True


@need_node
async def test_mo_hinh_the_loa_mat_ket_noi_van_dung_thu_tu_bang(hass, r1):
    await _them(hass, r1)
    gia = _hass_gia(hass, ghi_chu_mat_thuoc_tinh=True)          # unavailable → mất thuộc tính
    # đảo thứ tự khoá để chứng minh thẻ tự sắp theo tần số trong entity_id
    gia["entities"] = dict(reversed(list(gia["entities"].items())))
    m = _mo_hinh(gia)
    assert m["offline"] is True
    assert [b["entity"] for b in m["bands"]] == BANDS
    assert all(b["available"] is False and b["value"] is None for b in m["bands"])
    assert m["preset"]["selectable"] is False and m["preset"]["current"] is None


@need_node
async def test_mo_hinh_the_thieu_thuoc_tinh_coi_la_chua_xac_nhan(hass, r1):
    """Thực thể không báo `confirmed` (bản tích hợp cũ/khác) → thẻ coi là chưa xác nhận."""
    await _them(hass, r1)
    gia = _hass_gia(hass)
    for st in gia["states"].values():
        st["attributes"].pop("confirmed", None)
        st["attributes"].pop("selectable", None)
    m = _mo_hinh(gia)
    assert not any(b["confirmed"] for b in m["bands"]) and not m["bass"]["confirmed"]
    assert m["preset"]["selectable"] is False


@need_node
async def test_mo_hinh_the_cau_hinh_tay_de_len_tu_dong(hass, r1):
    await _them(hass, r1)
    gia = _hass_gia(hass)
    m = _mo_hinh(gia, {"entities": {"eq_enable": "switch.phicomm_r1_loudness"}})
    assert m["eq"]["entity"] == "switch.phicomm_r1_loudness"
    assert _mo_hinh({"entities": {}, "states": {}})["found"] is False     # không có gì: báo rõ
    assert _mo_hinh(gia, {"device_id": "khong-co"})["found"] is False
