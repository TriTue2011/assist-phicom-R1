"""Thêm loa R1: nhập IP + cổng, kiểm bằng một lần get_info."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (ConfigEntry, ConfigFlow, ConfigFlowResult,
                                          OptionsFlowWithReload)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import R1Client, R1Error
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
from .settings import (DuplexSettings, TalkSettings, agc_settings, conf, limiter_settings, noise_settings, wake_settings, ha_url, mic_address, mic_listen, play_address, speaker_host,
                       speaker_port, wake_mode)
from .const import (CONF_WAKE_ENABLE, CONF_WAKE_SENSITIVITY, CONF_WAKE_WORD,
                    DEFAULT_WAKE_ENABLE, DEFAULT_WAKE_SENSITIVITY, DEFAULT_WAKE_WORD)

CONF_ROTATE_KEY = "rotate_intercom_key"


class R1ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "R1OptionsFlow":
        return R1OptionsFlow()

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
}


_DSP_GOC = {k: _GOC[k] for k in (
    CONF_NOISE_ENABLE, CONF_NOISE_STRENGTH_DB, CONF_NOISE_VOICE_DB, CONF_AGC_ENABLE,
    CONF_AGC_TARGET_DB, CONF_AGC_MAX_GAIN_DB, CONF_AGC_SILENCE_DB, CONF_LIMITER_ENABLE,
    CONF_LIMITER_CEILING, CONF_WAKE_ENABLE, CONF_WAKE_WORD, CONF_WAKE_SENSITIVITY)}


def _overrides(entry: ConfigEntry, chosen: dict[str, Any]) -> dict[str, Any]:
    """Chỉ giữ giá trị KHÁC giá trị gốc (host/cổng: khác lúc thêm loa). Lý do: mặc định của
    bộ đàm còn CHƯA ĐO — khi có số đo và đổi mặc định, các mục chưa chỉnh tay tự theo mặc
    định mới thay vì kẹt ở số cũ."""
    goc = {**_GOC, CONF_HOST: entry.data.get(CONF_HOST), CONF_PORT: entry.data.get(CONF_PORT)}
    return {k: v for k, v in chosen.items() if v != goc[k]}


class R1OptionsFlow(OptionsFlowWithReload):
    """Mọi thứ chỉnh được sau khi thêm loa (HA nạp lại mục khi lưu):

    * ``host`` + ``port`` — địa chỉ và cổng WebSocket điều khiển / EQ (đổi thì kiểm lại bằng
      một lần get_info);
    * ``mic_host`` + ``mic_port`` — luồng mic của loa (host trống = tắt phần nghe);
    * ``mic_listen_port`` + ``mic_listen_key`` — đầu NHẬN mic NV244 (APK loa nối vào HA);
      khoá trống = đầu nhận không mở. Khoá chỉ nằm ở options, không ghi log;
    * ``play_host`` + ``play_port`` — kênh phát về loa của bộ đàm (cổng 0 = chưa có kênh);
    * bốn tham số cổng thoại của bộ đàm nửa công (mặc định CHƯA đo trên loa R1);
    * ``wake_mode`` — ``ha`` (từ đánh thức do pipeline HA dò, mic về HA liên tục) hoặc
      ``speaker`` (từ đánh thức TRÊN LOA, HA chỉ nhận luồng sau trigger; phía loa CHƯA có);
    * ``noise_suppress`` + ``noise_strength_db`` + ``noise_voice_db`` — khử tạp âm phía HA
      (``noise_suppress.py``; MẶC ĐỊNH TẮT, số CHƯA ĐO trên mic loa);
    * ``agc_*`` + ``limiter_*`` — AGC và bộ hạn đỉnh (``agc.py``; MẶC ĐỊNH TẮT, CHƯA ĐO). Cả
      năm khoá trên áp dụng từ lần nối mic kế (HA nạp lại mục khi lưu);
    * ``duplex_*`` — đàm thoại SONG CÔNG (NV246): ngưỡng VAD, đệm trước/sau, hạn phiên,
      cắt vọng tuỳ chọn (mặc định TẮT; mọi số CHƯA ĐO trên loa R1);
    * ``ha_url`` — địa chỉ HA mà loa / go2rtc gọi tới. KIỂM NGAY khi lưu: sai dạng, trỏ về
      127.0.0.1/localhost, hay HA không tự gọi được ``/api/r1_speaker/ping`` thì báo lỗi cụ thể
      và KHÔNG lưu gì (cả form);
    * ``rotate_intercom_key`` — sinh khoá URL bộ đàm / trigger mới (cấu hình cũ trên loa/go2rtc
      ngừng chạy, thông báo «khoá sai» được gỡ).
    """

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
                return self.async_create_entry(data=_overrides(entry, {
                    CONF_HOST: host, CONF_PORT: port,
                    CONF_MIC_HOST: user_input.get(CONF_MIC_HOST, "").strip(),
                    CONF_MIC_PORT: user_input[CONF_MIC_PORT],
                    CONF_MIC_LISTEN_PORT: user_input.get(
                        CONF_MIC_LISTEN_PORT, mic_listen(entry)[0]),
                    CONF_MIC_LISTEN_KEY: user_input.get(CONF_MIC_LISTEN_KEY, "").strip(),
                    CONF_PLAY_HOST: user_input.get(CONF_PLAY_HOST, "").strip(),
                    CONF_PLAY_PORT: user_input[CONF_PLAY_PORT],
                    CONF_TALK_THRESHOLD_DB: user_input[CONF_TALK_THRESHOLD_DB],
                    CONF_TALK_SILENCE: user_input[CONF_TALK_SILENCE],
                    CONF_TALK_PREROLL: user_input[CONF_TALK_PREROLL],
                    CONF_TALK_TAIL: user_input[CONF_TALK_TAIL],
                    CONF_WAKE_MODE: user_input.get(CONF_WAKE_MODE, DEFAULT_WAKE_MODE),
                    **{k: user_input.get(k, d) for k, d in _DSP_GOC.items()},
                    CONF_DUPLEX_VAD_THRESHOLD: user_input[CONF_DUPLEX_VAD_THRESHOLD],
                    CONF_DUPLEX_PREROLL: user_input[CONF_DUPLEX_PREROLL],
                    CONF_DUPLEX_HANGOVER: user_input[CONF_DUPLEX_HANGOVER],
                    CONF_DUPLEX_MAX_S: user_input[CONF_DUPLEX_MAX_S],
                    CONF_DUPLEX_DUCK: user_input.get(CONF_DUPLEX_DUCK, DEFAULT_DUPLEX_DUCK),
                    CONF_DUPLEX_DUCK_DB: user_input[CONF_DUPLEX_DUCK_DB],
                    CONF_HA_URL: url.rstrip("/")}))
        v = user_input or {}
        talk = TalkSettings.from_entry(entry)
        duplex = DuplexSettings.from_entry(entry)
        mic_host, mic_port = mic_address(entry)
        listen_port, listen_key = mic_listen(entry)
        play_host = str(conf(entry, CONF_PLAY_HOST, "") or "")
        port_range = vol.All(int, vol.Range(min=1, max=65535))
        noise, agc, lim = noise_settings(entry), agc_settings(entry), limiter_settings(entry)
        wake = wake_settings(entry)
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
            CONF_WAKE_ENABLE: (wake["bat"], bool),
            CONF_WAKE_WORD: (wake["tu_khoa"], vol.All(str, vol.Length(max=40))),
            CONF_WAKE_SENSITIVITY: (wake["do_nhay"], vol.All(
                vol.Coerce(float), vol.Range(min=0, max=1))),
        }
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=v.get(CONF_HOST, speaker_host(entry))): str,
            vol.Required(CONF_PORT, default=v.get(CONF_PORT, speaker_port(entry))): port_range,
            vol.Optional(CONF_MIC_HOST, description={
                "suggested_value": v.get(CONF_MIC_HOST, mic_host)}): str,
            vol.Required(CONF_MIC_PORT, default=v.get(CONF_MIC_PORT, mic_port)): port_range,
            vol.Required(CONF_MIC_LISTEN_PORT,
                         default=v.get(CONF_MIC_LISTEN_PORT, listen_port)): port_range,
            vol.Optional(CONF_MIC_LISTEN_KEY, description={
                "suggested_value": v.get(CONF_MIC_LISTEN_KEY, listen_key)}): str,
            vol.Optional(CONF_PLAY_HOST, description={
                "suggested_value": v.get(CONF_PLAY_HOST, play_host)}): str,
            vol.Required(CONF_PLAY_PORT, default=v.get(
                CONF_PLAY_PORT, play_address(entry)[1])): vol.All(
                    int, vol.Range(min=0, max=65535)),
            vol.Required(CONF_TALK_THRESHOLD_DB,
                         default=v.get(CONF_TALK_THRESHOLD_DB, talk.threshold_db)): vol.All(
                             vol.Coerce(float), vol.Range(min=-90, max=-5)),
            vol.Required(CONF_TALK_SILENCE, default=v.get(CONF_TALK_SILENCE, talk.silence_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0.2, max=10)),
            vol.Required(CONF_TALK_PREROLL, default=v.get(CONF_TALK_PREROLL, talk.preroll_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=2)),
            vol.Required(CONF_TALK_TAIL, default=v.get(CONF_TALK_TAIL, talk.tail_s)):
                vol.All(vol.Coerce(float), vol.Range(min=0, max=5)),
            vol.Required(CONF_WAKE_MODE, default=v.get(CONF_WAKE_MODE, wake_mode(entry))):
                vol.In([WAKE_HA, WAKE_SPEAKER]),
            **{vol.Required(k, default=v.get(k, cur)): typ for k, (cur, typ) in dsp.items()},
            vol.Required(CONF_DUPLEX_VAD_THRESHOLD,
                         default=v.get(CONF_DUPLEX_VAD_THRESHOLD, duplex.vad_threshold)):
                vol.All(vol.Coerce(float), vol.Range(min=0.05, max=0.95)),
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
            vol.Optional(CONF_HA_URL, description={
                "suggested_value": v.get(CONF_HA_URL, ha_url(entry))}): str,
            vol.Optional(CONF_ROTATE_KEY, default=False): bool,
        }))
