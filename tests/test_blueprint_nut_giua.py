"""Mẫu tự động hoá «nút giữa nghe máy hoặc gọi đi»: nạp được như một blueprint của HA và mọi đầu vào được dùng đều đã khai báo."""
import os

from homeassistant.components.blueprint import models, schemas
from homeassistant.util import yaml as hass_yaml

DUONG = os.path.join(os.path.dirname(__file__), "..", "blueprints", "automation", "r1_speaker", "nut_giua_nghe_hoac_goi_zalo.yaml")


def test_blueprint_nap_duoc_va_dau_vao_khop_voi_cho_dung():
    raw = hass_yaml.load_yaml(DUONG)
    bp = models.Blueprint(raw, expected_domain="automation", schema=schemas.BLUEPRINT_SCHEMA)
    khai_bao = set(raw["blueprint"]["input"])
    assert khai_bao == {"nut", "cam_bien", "nguoi_nhan", "loai_goi", "cup_khi_dang_goi"}
    dung = set(hass_yaml.extract_inputs(raw))
    assert dung <= khai_bao and dung == khai_bao, (dung, khai_bao)         # khai báo mà không dùng, hoặc dùng mà không khai báo, đều là lỗi
    assert bp.domain == "automation"
    # ba trường hợp: nghe máy / cúp / gọi đi (mặc định)
    choose = raw["actions"][0]["choose"]
    assert [c["sequence"][0]["action"] for c in choose] == ["zalo_call.answer_call", "zalo_call.end_call"]
    assert raw["actions"][0]["default"][0]["action"] == "zalo_call.make_call"
