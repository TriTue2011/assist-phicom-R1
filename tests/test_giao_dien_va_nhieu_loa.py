"""Cài tích hợp là tự thêm thẻ (MỘT thẻ duy nhất ``r1-card``), và thêm được nhiều loa R1 độc lập nhau.

Tài nguyên Lovelace là danh sách thật trong chế độ lưu trữ; test dùng danh sách giả cùng giao diện (``async_items``,
``async_create_item``, ``async_update_item``, ``async_delete_item``). Nhiều loa: mỗi loa một mục cấu hình, tự được cấp
khoá + cổng nghe riêng, thực thể không đè nhau, âm lượng của loa này không chạm loa kia.
"""

import asyncio
from pathlib import Path

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.r1_speaker import giao_dien
from custom_components.r1_speaker.const import DOMAIN
from custom_components.r1_speaker.settings import mic_listen

from .conftest import FakeR1
from .test_mic_server import cho, hello, khung_json

WWW = Path(__file__).parent.parent / "custom_components" / "r1_speaker" / "www"
GOP = "/r1_speaker/r1-card.js"


class _TaiNguyen:
    """Danh sách tài nguyên Lovelace giả (chế độ lưu trữ, có ghi được)."""

    def __init__(self, items):
        self.items = [dict(i, id=f"id{n}") for n, i in enumerate(items)]
        self.nhat_ky = []

    async def async_get_info(self):
        return {}

    def async_items(self):
        return [dict(i) for i in self.items]

    async def async_create_item(self, data):
        self.items.append({**data, "id": f"moi{len(self.items)}"})
        self.nhat_ky.append(("tao", data["url"]))

    async def async_update_item(self, item_id, data):
        for i in self.items:
            if i["id"] == item_id:
                i.update(data)
        self.nhat_ky.append(("sua", data["url"]))

    async def async_delete_item(self, item_id):
        self.items = [i for i in self.items if i["id"] != item_id]
        self.nhat_ky.append(("xoa", item_id))


class _Lovelace:
    def __init__(self, resources):
        self.resources = resources


async def test_tu_them_tai_nguyen_the_gop_co_phien_ban(hass):
    ds = _TaiNguyen([{"res_type": "module", "url": "/local/the-khac.js"}])
    hass.data["lovelace"] = _Lovelace(ds)
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")
    assert [i["url"] for i in ds.items] == ["/local/the-khac.js", GOP + "?v=0.3.0"]      # thẻ của người khác giữ nguyên
    assert ds.items[1]["res_type"] == "module"
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")
    assert [n for n, _ in ds.nhat_ky] == ["tao"]                                          # chạy lại: không thêm trùng


async def test_doi_phien_ban_thi_cap_nhat_dung_muc_cu(hass):
    ds = _TaiNguyen([{"res_type": "module", "url": GOP + "?v=0.2.0"}])
    hass.data["lovelace"] = _Lovelace(ds)
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")
    assert [i["url"] for i in ds.items] == [GOP + "?v=0.3.0"] and ds.nhat_ky == [("sua", GOP + "?v=0.3.0")]


async def test_go_ba_tai_nguyen_the_con_cu_cua_chinh_tich_hop_nhung_khong_dung_the_khac(hass):
    ds = _TaiNguyen([{"res_type": "module", "url": "/r1_speaker/r1-eq-card.js"},
                     {"res_type": "module", "url": "/r1_speaker/r1-talk-card.js?v=1"},
                     {"res_type": "module", "url": "/r1_speaker/r1-settings-card.js"},
                     {"res_type": "module", "url": "/local/youtube.js"}])
    hass.data["lovelace"] = _Lovelace(ds)
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")
    assert sorted(i["url"] for i in ds.items) == sorted(["/local/youtube.js", GOP + "?v=0.3.0"])


async def test_che_do_yaml_chi_doc_thi_khong_doi_gi_va_khong_nem_loi(hass):
    class ChiDoc:
        def async_items(self):
            return []
    hass.data["lovelace"] = _Lovelace(ChiDoc())
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")          # không có async_create_item: chỉ ghi log
    hass.data.pop("lovelace")
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")          # chưa có lovelace: cũng yên


async def test_loi_khi_ghi_khong_lam_hong_viec_cai_tich_hop(hass):
    class Hong(_TaiNguyen):
        async def async_create_item(self, data):
            raise RuntimeError("kho hỏng")
    hass.data["lovelace"] = _Lovelace(Hong([]))
    await giao_dien._dang_ky(hass, GOP + "?v=0.3.0")          # nuốt lỗi, chỉ cảnh báo


def test_chi_the_gop_hien_trong_bo_chon_the():
    """Ba thẻ con không tự khai báo vào ``window.customCards``: trong bộ chọn thẻ chỉ có ``r1-card``."""
    for f in ("r1-eq-card.js", "r1-talk-card.js", "r1-settings-card.js"):
        assert "customCards.push" not in (WWW / f).read_text(encoding="utf-8"), f
    assert (WWW / "r1-card.js").read_text(encoding="utf-8").count("customCards.push") == 1


async def test_them_hai_loa_moi_loa_khoa_cong_thuc_the_rieng_va_am_luong_khong_chay_lan(hass, r1):
    r2 = FakeR1()
    await r2.start()
    try:
        entries = []
        for loa in (r1, r2):
            e = MockConfigEntry(domain=DOMAIN, data={"host": "127.0.0.1", "port": loa.port},
                                unique_id=f"127.0.0.1:{loa.port}")
            e.add_to_hass(hass)
            assert await hass.config_entries.async_setup(e.entry_id)
            await hass.async_block_till_done()
            entries.append(e)
        (c1, k1), (c2, k2) = (mic_listen(e) for e in entries)
        assert c1 and c2 and c1 != c2 and k1 and k2 and k1 != k2           # cổng + khoá nghe tự cấp, khác nhau
        reg = er.async_get(hass)
        theo_entry = [[x for x in reg.entities.values() if x.config_entry_id == e.entry_id] for e in entries]
        assert len(theo_entry[0]) == len(theo_entry[1]) > 20
        assert len({x.entity_id for ds in theo_entry for x in ds}) == len(theo_entry[0]) + len(theo_entry[1])
        so = [next(x.entity_id for x in ds if x.domain == "number" and x.unique_id.endswith("_volume")) for ds in theo_entry]
        assert so[0] != so[1]
        # APK của loa 1 báo âm lượng 5: chỉ number của loa 1 có giá trị, loa 2 vẫn không khả dụng
        reader, writer = await asyncio.open_connection("127.0.0.1", c1)
        writer.write(hello(k1))
        await writer.drain()
        await cho(lambda: entries[0].runtime_data.mic_server.receiving)
        writer.write(khung_json({"type": "am_luong_trang_thai", "muc": 5, "toi_da": 15}))
        await writer.drain()
        await cho(lambda: hass.states.get(so[0]).state not in ("unavailable", "unknown"))
        assert float(hass.states.get(so[0]).state) == 5 and hass.states.get(so[1]).state == "unavailable"
        # Gỡ loa 2: loa 1 vẫn chạy
        assert await hass.config_entries.async_remove(entries[1].entry_id)
        await hass.async_block_till_done()
        assert float(hass.states.get(so[0]).state) == 5
        writer.close()
    finally:
        await r2.stop()
