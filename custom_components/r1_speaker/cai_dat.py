"""``sensor.r1_cai_dat``: bản tóm tắt cài đặt của loa cho thẻ ``r1-settings-card`` (ba nhóm).

Thẻ KHÔNG gọi loa: nó đọc thuộc tính của thực thể này (và các thực thể EQ / âm lượng / mic sẵn
có) rồi gọi dịch vụ HA. Ba nhóm thuộc tính:

* ``am_thanh`` — khử tạp, AGC, bộ hạn đỉnh (là TUỲ CHỌN của mục cài đặt, không phải thực thể,
  nên thẻ chỉ ĐỌC; sửa ở Tuỳ chọn của tích hợp, vì lưu tuỳ chọn nạp lại cả mục);
* ``anh_sang`` — cài đặt đèn theo chức năng, danh mục hiệu ứng, trạng thái dịch vụ đèn
  (``R1Lights.attributes``);
* ``ket_noi`` — host, cổng, ha_url, chế độ từ đánh thức, và **khoá bộ đàm chỉ hiện «đã có/chưa
  có»**: giá trị khoá KHÔNG BAO GIỜ đưa vào thuộc tính (recorder lưu thuộc tính, mọi người dùng HA
  đọc được).

Trạng thái của sensor là chức năng đèn đang hiệu lực (``cho``, ``nghe``…).
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory

from .const import CONF_INTERCOM_KEY, DEFAULT_PORT
from .coordinator import R1ConfigEntry
from .entity import R1MicEntity
from . import nang_cao
from .settings import (wake_settings, agc_settings, conf, ha_url, limiter_settings, mic_address, mic_listen, noise_settings,
                       play_address, speaker_host, speaker_port, wake_mode)

#: Đường tới trang tuỳ chọn của tích hợp trong giao diện HA (thẻ dẫn người dùng tới đó).
OPTIONS_PATH = "/config/integrations/integration/r1_speaker"


def am_thanh(entry: R1ConfigEntry) -> dict:
    n, a, lim = noise_settings(entry), agc_settings(entry), limiter_settings(entry)
    return {
        "tu_danh_thuc": wake_settings(entry),
        "khu_tap": {"bat": n.enabled, "do_giam_db": n.strength_db, "nguong_giong_db": n.voice_db},
        "agc": {"bat": a.enabled, "dich_db": a.target_db, "tang_toi_da_db": a.max_gain_db,
                "im_lang_db": a.silence_db},
        "han_dinh": {"bat": lim.enabled, "tran": lim.ceiling},
        "sua_o": "the",          # chỉnh trực tiếp ở thẻ (dịch vụ set_advanced_option)
        "nang_cao": nang_cao.thuoc_tinh(entry),
    }


def ket_noi(entry: R1ConfigEntry) -> dict:
    mic_host, mic_port = mic_address(entry)
    play_host, play_port = play_address(entry)
    return {
        "host": speaker_host(entry), "cong": speaker_port(entry), "cong_mac_dinh": DEFAULT_PORT,
        "mic_host": mic_host, "mic_cong": mic_port,
        "phat_host": play_host, "phat_cong": play_port,
        "che_do_tu_danh_thuc": wake_mode(entry),
        "ha_url": ha_url(entry),
        # Chỉ có/không: KHÔNG đưa giá trị khoá vào thuộc tính.
        "khoa_bo_dam": "da_co" if conf(entry, CONF_INTERCOM_KEY) else "chua_co",
        # Đường mic mới: khoá và cổng nghe do HA tự cấp cho từng loa (giá trị khoá KHÔNG đưa vào đây).
        "cong_nghe_mic": mic_listen(entry)[0],
        "khoa_nghe_mic": "da_co" if mic_listen(entry)[1] else "chua_co",
        "apk_dang_noi": bool(getattr(getattr(getattr(entry, "runtime_data", None), "mic_server", None),
                                     "receiving", False)),
        "tuy_chon": OPTIONS_PATH,
    }


class R1Settings(R1MicEntity, SensorEntity):
    _attr_translation_key = "settings"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    #: Bản tóm tắt lớn và ít đổi: không đưa vào lịch sử recorder.
    _unrecorded_attributes = frozenset({"am_thanh", "anh_sang", "ket_noi"})

    def __init__(self, entry: R1ConfigEntry) -> None:
        super().__init__(entry, "settings")

    @property
    def _lights(self):
        return self._entry.runtime_data.lights

    @property
    def native_value(self) -> str:
        return self._lights.current or "cho"

    @property
    def extra_state_attributes(self) -> dict:
        return {"am_thanh": am_thanh(self._entry), "anh_sang": self._lights.attributes(),
                "ket_noi": ket_noi(self._entry)}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._lights.add_listener(self.async_write_ha_state))
        # Thẻ «Kết nối» hiện APK đang nối hay chưa: cập nhật khi APK nối/đứt.
        self.async_on_remove(self._entry.runtime_data.mic_server.add_state_listener(self.async_write_ha_state))
