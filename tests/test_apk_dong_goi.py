"""Gói APK đi kèm: phiên bản khớp ở mọi nơi, hai bản sao giống hệt, mã băm khớp; khung APK↔HA khai trong tài liệu hợp đồng."""

import hashlib
import json
import re
from pathlib import Path

GOC = Path(__file__).parents[1]


def _doc(p):
    return (GOC / p).read_text(encoding="utf-8")


def test_phien_ban_apk_khop_manifest_ma_bao_cao_va_bo_cai():
    manifest = re.search(r'android:versionName="([^"]+)"', _doc("apk/nguon/AndroidManifest-release.xml")).group(1)
    kiemthu = re.search(r'android:versionName="([^"]+)"', _doc("apk/nguon/AndroidManifest-kiemthu.xml")).group(1)
    bao_cao = re.search(r'PHIEN_BAN = "([^"]+)"', _doc("apk/nguon/src/vn/r1/bodam/BaoCao.java")).group(1)
    bo_cai = next(u for u in json.loads(_doc("custom_components/r1_speaker/apk/bo-cai.json"))["ung_dung"] if u["id"] == "bodam")
    assert manifest == kiemthu == bao_cao == bo_cai["phien_ban"], (manifest, kiemthu, bao_cao, bo_cai["phien_ban"])


def test_hai_ban_sao_apk_giong_nhau_va_ma_bam_khop():
    a = (GOC / "apk/vn-r1-bodam.apk").read_bytes()
    b = (GOC / "custom_components/r1_speaker/apk/vn-r1-bodam.apk").read_bytes()
    assert a == b
    sha = hashlib.sha256(a).hexdigest()
    assert _doc("apk/vn-r1-bodam.apk.sha256").split()[0] == sha
    bo_cai = next(u for u in json.loads(_doc("custom_components/r1_speaker/apk/bo-cai.json"))["ung_dung"] if u["id"] == "bodam")
    assert bo_cai["sha256"] == sha


def test_khung_apk_va_ha_deu_co_trong_tai_lieu_hop_dong():
    hd = _doc("docs/HOP-DONG-PHIA-LOA.md")
    for khung in ("apk", "he_thong", "he_thong_hoi", "bluetooth", "bluetooth_trang_thai", "phim", "phim_cau_hinh"):
        assert f"`{khung}`" in hd, f"thiếu khung {khung} trong docs/HOP-DONG-PHIA-LOA.md"
