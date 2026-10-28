"""Thêm loa R1: nhập IP + cổng, kiểm bằng một lần get_info."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (ConfigEntry, ConfigFlow, ConfigFlowResult,
                                          OptionsFlowWithReload)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .adb_client import AdbDevice, AdbError
from .client import R1Client, R1Error
from .const import ADB_PORT, CONF_MIC_CHUA_GHEP
from .cong_vao import kiem_tra_ha_url, xoa_canh_bao_khoa
from .const import (CONF_AGC_ENABLE, CONF_AGC_MAX_GAIN_DB, CONF_AGC_SILENCE_DB, CONF_AGC_TARGET_DB,
                    CONF_DUPLEX_DUCK, CONF_DUPLEX_DUCK_DB, CONF_DUPLEX_HANGOVER,
                    CONF_DUPLEX_MAX_S, CONF_DUPLEX_PREROLL, CONF_DUPLEX_VAD_THRESHOLD,
                    DEFAULT_DUPLEX_DUCK, DEFAULT_DUPLEX_DUCK_DB, DEFAULT_DUPLEX_HANGOVER,
                    DEFAULT_DUPLEX_MAX_S, DEFAULT_DUPLEX_PREROLL, DEFAULT_DUPLEX_VAD_THRESHOLD,
                    CONF_LIMITER_CEILING, CONF_LIMITER_ENABLE, CONF_NOISE_ENABLE,
                    CONF_NOISE_STRENGTH_DB, CONF_NOISE_VOICE_DB, DEFAULT_AGC_ENABLE,
                    DEFAULT_AGC_MAX_GAIN_DB, DEFAULT_AGC_SILENCE_DB, DEFAULT_AGC_TARGET_DB,
                    DEFAULT_LIMITER_CEILING, DEFAULT_LIMITER_ENABLE, DEFAULT_NOISE_ENABLE,
                    DEFAULT_NOISE_STRENGTH_DB, DEFAULT_NOISE_VOICE_DB,
                    CONF_HA_URL, CONF_WAKE_MODE, DEFAULT_WAKE_MODE, WAKE_HA, WAKE_SPEAKER, CONF_HOST, CONF_INTERCOM_KEY, CONF_MIC_HOST, CONF_MIC_LISTEN_KEY, CONF_MIC_LISTEN_PORT, CONF_MIC_PORT,
                    CONF_PLAY_HOST, CONF_PLAY_PORT, CONF_PORT, CONF_TALK_PREROLL,
                    CONF_TALK_SILENCE, CONF_TALK_TAIL, CONF_TALK_THRESHOLD_DB, DEFAULT_HOST,
                    DEFAULT_MIC_LISTEN_PORT, DEFAULT_MIC_PORT, DEFAULT_PLAY_PORT, DEFAULT_PORT, DEFAULT_TALK_PREROLL,
                    DEFAULT_TALK_SILENCE, DEFAULT_TALK_TAIL, DEFAULT_TALK_THRESHOLD_DB, DOMAIN)
from .settings import (adb_settings, adb_tu_dong_dong, DuplexSettings, TalkSettings, agc_settings, conf, limiter_settings, noise_settings, wake_settings, ha_url, mic_address, mic_listen, play_address, speaker_host,
                       speaker_port, wake_mode)
from .const import CONF_ADB_MODE, CONF_ADB_SERVER, CONF_ADB_TU_DONG, DEFAULT_ADB_MODE, DEFAULT_ADB_SERVER
from .const import (CONF_WAKE_ENABLE, CONF_WAKE_SENSITIVITY, CONF_WAKE_WORD,
                    DEFAULT_WAKE_ENABLE, DEFAULT_WAKE_SENSITIVITY, DEFAULT_WAKE_WORD)

CONF_ROTATE_KEY = "rotate_intercom_key"
CONF_NANG_CAO = "nang_cao"
CONF_GHEP_LAI = "ghep_lai_apk"


async def _thu_adb(host: str) -> bool:
    """ADB của loa (cổng 5555) có trả lời không. Loa mới reset chưa có ứng dụng phục vụ cổng điều khiển (8080) nhưng vẫn trả lời ADB:
    khi đó vẫn phải thêm được tích hợp để cài các ứng dụng đó qua ADB."""
    dev = AdbDevice(host, ADB_PORT, "", "direct")
    try:
        return (await dev.shell("echo r1", timeout=8)).strip() == "r1"
    except (AdbError, OSError, asyncio.TimeoutError):
        return False
    finally:
        try:
            await dev.close()                 # nhả kết nối ngay: adbd chỉ phục vụ một kết nối, tích hợp sắp cần nó
        except Exception:                     # noqa: BLE001 - dọn dẹp, không để che kết quả
            pass


class R1ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "R1OptionsFlow":
        return R1OptionsFlow()

    async def async_step_chua_co_dich_vu(self, user_input: dict[str, Any] | None = None
                                         ) -> ConfigFlowResult:
        """Loa trả lời ADB nhưng chưa trả lời cổng điều khiển (loa mới reset hoặc vừa khởi động): cho thêm để cài ứng dụng qua ADB."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Phicomm R1 ({self._host})", data={CONF_HOST: self._host, CONF_PORT: self._port})
        return self.async_show_form(
            step_id="chua_co_dich_vu", data_schema=vol.Schema({}),
            description_placeholders={"host": self._host, "port": str(self._port), "adb_port": str(ADB_PORT)})

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            try:
                await R1Client(async_get_clientsession(self.hass), host, port).async_fetch()
            except R1Error:
                if await _thu_adb(host):                       # loa mới reset: ADB sống, cổng điều khiển chưa có
                    self._host, self._port = host, port
                    return await self.async_step_chua_co_dich_vu()
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Phicomm R1 ({host})", data={CONF_HOST: host, CONF_PORT: port})
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    int, vol.Range(min=1, max=65535)),
            }))


#: Giá trị gốc của từng khoá tuỳ chọn: nhập đúng giá trị gốc thì KHÔNG lưu (xem ``_overrides``).
_GOC = {
    CONF_MIC_HOST: "", CONF_MIC_PORT: DEFAULT_MIC_PORT,
    CONF_MIC_LISTEN_PORT: DEFAULT_MIC_LISTEN_PORT, CONF_MIC_LISTEN_KEY: "",
    CONF_PLAY_HOST: "",
    CONF_PLAY_PORT: DEFAULT_PLAY_PORT, CONF_TALK_THRESHOLD_DB: DEFAULT_TALK_THRESHOLD_DB,
    CONF_TALK_SILENCE: DEFAULT_TALK_SILENCE, CONF_TALK_PREROLL: DEFAULT_TALK_PREROLL,
    CONF_TALK_TAIL: DEFAULT_TALK_TAIL, CONF_WAKE_MODE: DEFAULT_WAKE_MODE, CONF_HA_URL: "",
    CONF_NOISE_ENABLE: DEFAULT_NOISE_ENABLE, CONF_NOISE_STRENGTH_DB: DEFAULT_NOISE_STRENGTH_DB,
    CONF_NOISE_VOICE_DB: DEFAULT_NOISE_VOICE_DB, CONF_AGC_ENABLE: DEFAULT_AGC_ENABLE,
    CONF_AGC_TARGET_DB: DEFAULT_AGC_TARGET_DB, CONF_AGC_MAX_GAIN_DB: DEFAULT_AGC_MAX_GAIN_DB,
    CONF_AGC_SILENCE_DB: DEFAULT_AGC_SILENCE_DB, CONF_LIMITER_ENABLE: DEFAULT_LIMITER_ENABLE,
    CONF_LIMITER_CEILING: DEFAULT_LIMITER_CEILING,
    CONF_DUPLEX_VAD_THRESHOLD: DEFAULT_DUPLEX_VAD_THRESHOLD,
    CONF_DUPLEX_PREROLL: DEFAULT_DUPLEX_PREROLL, CONF_DUPLEX_HANGOVER: DEFAULT_DUPLEX_HANGOVER,
    CONF_DUPLEX_MAX_S: DEFAULT_DUPLEX_MAX_S, CONF_DUPLEX_DUCK: DEFAULT_DUPLEX_DUCK,
    CONF_DUPLEX_DUCK_DB: DEFAULT_DUPLEX_DUCK_DB,
    CONF_WAKE_ENABLE: DEFAULT_WAKE_ENABLE, CONF_WAKE_WORD: DEFAULT_WAKE_WORD,
    CONF_WAKE_SENSITIVITY: DEFAULT_WAKE_SENSITIVITY,
    CONF_ADB_SERVER: DEFAULT_ADB_SERVER, CONF_ADB_MODE: DEFAULT_ADB_MODE, CONF_ADB_TU_DONG: False,
}


_DSP_GOC = {k: _GOC[k] for k in (
    CONF_NOISE_ENABLE, CONF_NOISE_STRENGTH_DB, CONF_NOISE_VOICE_DB, CONF_AGC_ENABLE,
    CONF_AGC_TARGET_DB, CONF_AGC_MAX_GAIN_DB, CONF_AGC_SILENCE_DB, CONF_LIMITER_ENABLE,
    CONF_LIMITER_CEILING, CONF_WAKE_ENABLE, CONF_WAKE_WORD, CONF_WAKE_SENSITIVITY)}


#: Khoá tuỳ chọn KHÔNG còn hiện ở form nào (tự cấp hoặc chưa có dịch vụ phía loa) nhưng vẫn phải giữ nguyên
#: nếu đã có sẵn trong options — lưu form không được làm rơi khoá đầu nhận mic người dùng đã đặt từ trước.
_AN = (CONF_MIC_HOST, CONF_MIC_PORT, CONF_MIC_LISTEN_PORT, CONF_MIC_LISTEN_KEY, CONF_PLAY_HOST,
       CONF_PLAY_PORT, CONF_WAKE_MODE, CONF_WAKE_ENABLE, CONF_WAKE_WORD, CONF_WAKE_SENSITIVITY)


def _overrides(entry: ConfigEntry, chosen: dict[str, Any]) -> dict[str, Any]:
    """Chỉ giữ giá trị KHÁC giá trị gốc (host/cổng: khác lúc thêm loa). Lý do: mặc định của
    bộ đàm còn CHƯA ĐO — khi có số đo và đổi mặc định, các mục chưa chỉnh tay tự theo mặc
    định mới thay vì kẹt ở số cũ."""
    goc = {**_GOC, CONF_HOST: entry.data.get(CONF_HOST), CONF_PORT: entry.data.get(CONF_PORT)}
    return {k: v for k, v in chosen.items() if k not in goc or v != goc[k]}


class R1OptionsFlow(OptionsFlowWithReload):
    """Chỉnh loa sau khi thêm (HA nạp lại mục khi lưu). Form chính chỉ còn thứ người dùng thật sự biết:

    * ``host`` + ``port`` — địa chỉ và cổng WebSocket điều khiển / EQ (đổi thì kiểm lại bằng get_info);
    * ``ha_url`` — địa chỉ HA mà loa / go2rtc gọi tới (trống = tự đoán). KIỂM NGAY khi lưu: sai dạng,
      trỏ về 127.0.0.1/localhost, hay HA không tự gọi được ``/api/r1_speaker/ping`` thì báo lỗi cụ thể
      và KHÔNG lưu gì;
    * ``rotate_intercom_key`` — sinh khoá URL bộ đàm / trigger mới;
    * ``nang_cao`` — tích để sang bước thứ hai chỉnh thông số âm thanh.

    Khoá và cổng nghe mic KHÔNG hỏi: ``async_setup_entry`` tự sinh khoá và cấp cổng riêng cho từng loa,
    IP mic lấy theo IP loa; lệnh cấu hình APK có sẵn khoá được thẻ «Kết nối» hiện cho quản trị viên.

    Bước nâng cao (mặc định CHƯA đo trên loa R1, đa số người dùng không cần đụng): bốn tham số cổng thoại
    nửa công, khử tạp / AGC / hạn đỉnh phía HA (mặc định TẮT), sáu tham số đàm thoại song công.
    """

    def __init__(self) -> None:
        self._co_ban: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            if not host:
                errors[CONF_HOST] = "invalid_host"
            elif (host, port) != (speaker_host(entry), speaker_port(entry)):
                try:
                    await R1Client(async_get_clientsession(self.hass), host, port).async_fetch()
                except R1Error:
                    if not await _thu_adb(host):               # loa mới reset (ADB sống, cổng điều khiển chưa có) vẫn lưu được
                        errors["base"] = "cannot_connect"
            url = (user_input.get(CONF_HA_URL) or "").strip()
            if not errors and url:
                loi = await kiem_tra_ha_url(
                    self.hass, url, entry.entry_id, str(entry.data.get(CONF_INTERCOM_KEY) or ""),
                    host)
                if loi:
                    errors[CONF_HA_URL] = loi
            if not errors:
                if user_input.pop(CONF_ROTATE_KEY, False):
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data,
                                     CONF_INTERCOM_KEY: secrets.token_urlsafe(24)})
                    xoa_canh_bao_khoa(self.hass, entry.entry_id)
                if user_input.pop(CONF_GHEP_LAI, False):
                    # Khoá nghe mic mới + mở lại cửa ghép: APK tự xin khoá mới, không phải copy tay.
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_MIC_LISTEN_KEY: secrets.token_urlsafe(24),
                                     CONF_MIC_CHUA_GHEP: True})
                    # Chỉ DỮ LIỆU đổi (tuỳ chọn không đổi) nên HA không tự nạp lại mục: máy chủ nghe mic đang chạy phải
                    # được nạp khoá mới tại chỗ, nếu không APK xin được khoá mới rồi bị chính HA từ chối hello.
                    may_chu = getattr(getattr(entry, "runtime_data", None), "mic_server", None)
                    if may_chu is not None:
                        may_chu.dat_khoa(entry.data[CONF_MIC_LISTEN_KEY])
                self._co_ban = {CONF_HOST: host, CONF_PORT: port, CONF_HA_URL: url.rstrip("/"),
                                CONF_ADB_SERVER: (user_input.get(CONF_ADB_SERVER) or DEFAULT_ADB_SERVER).strip(),
                                CONF_ADB_MODE: user_input.get(CONF_ADB_MODE, DEFAULT_ADB_MODE),
                                CONF_ADB_TU_DONG: user_input.get(CONF_ADB_TU_DONG, False)}
                if user_input.get(CONF_NANG_CAO):
                    return await self.async_step_nang_cao()
                return self._luu({})
        v = user_input or {}
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=v.get(CONF_HOST, speaker_host(entry))): str,
            vol.Required(CONF_PORT, default=v.get(CONF_PORT, speaker_port(entry))): vol.All(
                int, vol.Range(min=1, max=65535)),
            vol.Optional(CONF_HA_URL, description={
                "suggested_value": v.get(CONF_HA_URL, ha_url(entry))}): str,
            vol.Optional(CONF_ADB_SERVER, default=v.get(CONF_ADB_SERVER, adb_settings(entry)[0])): str,
            vol.Optional(CONF_ADB_MODE, default=v.get(CONF_ADB_MODE, adb_settings(entry)[1])): vol.In(
                ["auto", "server", "direct"]),
            vol.Optional(CONF_ADB_TU_DONG, default=v.get(CONF_ADB_TU_DONG, adb_tu_dong_dong(entry))): bool,
            vol.Optional(CONF_ROTATE_KEY, default=False): bool,
            vol.Optional(CONF_GHEP_LAI, default=False): bool,
            vol.Optional(CONF_NANG_CAO, default=False): bool,
        }))

    def _luu(self, nang_cao: dict[str, Any]) -> ConfigFlowResult:
        """Gộp: khoá ẩn đang có + bước nâng cao (nếu đã qua) + bước chính. Bước nâng cao bị bỏ qua thì giữ nguyên
        các số nâng cao đang lưu, không đặt lại về mặc định."""
        entry = self.config_entry
        giu = {k: v for k, v in entry.options.items() if k in _AN}
        if not nang_cao:
            giu.update({k: v for k, v in entry.options.items() if k in _GOC and k not in _AN
                        and k != CONF_HA_URL})
        return self.async_create_entry(data=_overrides(entry, {**giu, **nang_cao, **self._co_ban}))

    async def async_step_nang_cao(self, user_input: dict[str, Any] | None = None
                                  ) -> ConfigFlowResult:
        entry = self.config_entry
        if user_input is not None:
            return self._luu({
                CONF_TALK_THRESHOLD_DB: user_input[CONF_TALK_THRESHOLD_DB],
                CONF_TALK_SILENCE: user_input[CONF_TALK_SILENCE],
                CONF_TALK_PREROLL: user_input[CONF_TALK_PREROLL],
                CONF_TALK_TAIL: user_input[CONF_TALK_TAIL],
                **{k: user_input.get(k, d) for k, d in _DSP_GOC.items()
                   if k in (CONF_NOISE_ENABLE, CONF_NOISE_STRENGTH_DB, CONF_NOISE_VOICE_DB,
                            CONF_AGC_ENABLE, CONF_AGC_TARGET_DB, CONF_AGC_MAX_GAIN_DB,
                            CONF_AGC_SILENCE_DB, CONF_LIMITER_ENABLE, CONF_LIMITER_CEILING)},
                CONF_DUPLEX_VAD_THRESHOLD: user_input[CONF_DUPLEX_VAD_THRESHOLD],
                CONF_DUPLEX_PREROLL: user_input[CONF_DUPLEX_PREROLL],
                CONF_DUPLEX_HANGOVER: user_input[CONF_DUPLEX_HANGOVER],
                CONF_DUPLEX_MAX_S: user_input[CONF_DUPLEX_MAX_S],
                CONF_DUPLEX_DUCK: user_input.get(CONF_DUPLEX_DUCK, DEFAULT_DUPLEX_DUCK),
                CONF_DUPLEX_DUCK_DB: user_input[CONF_DUPLEX_DUCK_DB]})
        v = {}
        talk = TalkSettings.from_entry(entry)
        duplex = DuplexSettings.from_entry(entry)
        noise, agc, lim = noise_settings(entry), agc_settings(entry), limiter_settings(entry)
        dsp = {
            CONF_NOISE_ENABLE: (noise.enabled, bool),
            CONF_NOISE_STRENGTH_DB: (noise.strength_db, vol.All(
                vol.Coerce(float), vol.Range(min=0, max=40))),
            CONF_NOISE_VOICE_DB: (noise.voice_db, vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=12))),
            CONF_AGC_ENABLE: (agc.enabled, bool),
            CONF_AGC_TARGET_DB: (agc.target_db, vol.All(
                vol.Coerce(float), vol.Range(min=-50, max=-3))),
            CONF_AGC_MAX_GAIN_DB: (agc.max_gain_db, vol.All(
                vol.Coerce(float), vol.Range(min=0, max=40))),
            CONF_AGC_SILENCE_DB: (agc.silence_db, vol.All(
                vol.Coerce(float), vol.Range(min=-90, max=-20))),
            CONF_LIMITER_ENABLE: (lim.enabled, bool),
            CONF_LIMITER_CEILING: (lim.ceiling, vol.All(
                vol.Coerce(float), vol.Range(min=0.1, max=1.0))),
        }
        return self.async_show_form(step_id="nang_cao", data_schema=vol.Schema({
            vol.Required(CONF_TALK_THRESHOLD_DB,
                         default=v.get(CONF_TALK_THRESHOLD_DB, talk.threshold_db)): vol.All(
                             vol.Coerce(float), vol.Range(min=-90, max=-5)),
            vol.Required(CONF_TALK_SILENCE, default=v.get(CONF_TALK_SILENCE, talk.silence_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0.2, max=10)),
            vol.Required(CONF_TALK_PREROLL, default=v.get(CONF_TALK_PREROLL, talk.preroll_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=2)),
            vol.Required(CONF_TALK_TAIL, default=v.get(CONF_TALK_TAIL, talk.tail_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=5)),
            **{vol.Required(k, default=v.get(k, cur)): typ for k, (cur, typ) in dsp.items()},
            vol.Required(CONF_DUPLEX_VAD_THRESHOLD,
                         default=v.get(CONF_DUPLEX_VAD_THRESHOLD, duplex.vad_threshold)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=0.95)),
            vol.Required(CONF_DUPLEX_PREROLL,
                         default=v.get(CONF_DUPLEX_PREROLL, duplex.preroll_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=2)),
            vol.Required(CONF_DUPLEX_HANGOVER,
                         default=v.get(CONF_DUPLEX_HANGOVER, duplex.hangover_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=5)),
            vol.Required(CONF_DUPLEX_MAX_S, default=v.get(CONF_DUPLEX_MAX_S, duplex.max_s)):
                vol.All(vol.Coerce(float), vol.Range(min=60, max=86400)),
            vol.Required(CONF_DUPLEX_DUCK, default=v.get(CONF_DUPLEX_DUCK, duplex.duck)): bool,
            vol.Required(CONF_DUPLEX_DUCK_DB,
                         default=v.get(CONF_DUPLEX_DUCK_DB, duplex.duck_db)):
                vol.All(vol.Coerce(float), vol.Range(min=-90, max=-5)),
        }))
