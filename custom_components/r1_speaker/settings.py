"""Cấu hình của một loa: ``entry.options`` đè lên ``entry.data`` (hai nơi cùng khoá).

Nhập ở config flow (host, cổng EQ) nằm trong ``data``; options flow ghi cùng khoá vào
``options`` nên đổi IP / cổng không cần xoá rồi thêm lại loa. Không số nào mã cứng ở nơi dùng:
mọi chỗ đọc qua đây, mặc định lấy từ ``const.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .agc import AgcSettings, LimiterSettings
from .noise_suppress import NoiseSettings
from .const import ADB_SERVER_LOCAL, CONF_ADB_MODE, CONF_ADB_SERVER, CONF_ADB_TU_DONG, DEFAULT_ADB_MODE, DEFAULT_ADB_SERVER
from .const import (CONF_WAKE_ENABLE, CONF_WAKE_SENSITIVITY, CONF_WAKE_WORD,
                    DEFAULT_WAKE_ENABLE, DEFAULT_WAKE_SENSITIVITY, DEFAULT_WAKE_WORD)
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
                    CONF_HA_URL, CONF_WAKE_MODE, DEFAULT_WAKE_MODE, WAKE_HA, WAKE_SPEAKER, CONF_HOST, CONF_MIC_HOST, CONF_MIC_LISTEN_KEY, CONF_MIC_LISTEN_PORT, CONF_MIC_PORT, CONF_PLAY_HOST, CONF_PLAY_PORT,
                    CONF_PORT, CONF_TALK_PREROLL, CONF_TALK_SILENCE, CONF_TALK_TAIL,
                    CONF_TALK_THRESHOLD_DB, DEFAULT_MIC_LISTEN_PORT, DEFAULT_MIC_PORT, DEFAULT_PLAY_PORT, DEFAULT_PORT,
                    DEFAULT_TALK_PREROLL, DEFAULT_TALK_SILENCE, DEFAULT_TALK_TAIL,
                    DEFAULT_TALK_THRESHOLD_DB)


def conf(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Tuỳ chọn → dữ liệu ban đầu → mặc định."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def speaker_host(entry: ConfigEntry) -> str:
    return str(conf(entry, CONF_HOST, "")).strip()


def speaker_port(entry: ConfigEntry) -> int:
    return int(conf(entry, CONF_PORT, DEFAULT_PORT))


def mic_address(entry: ConfigEntry) -> tuple[str, int]:
    """(host, cổng) luồng mic. Host trống = tắt phần nghe."""
    return (str(conf(entry, CONF_MIC_HOST, "") or "").strip(),
            int(conf(entry, CONF_MIC_PORT, DEFAULT_MIC_PORT)))


def mic_listen(entry: ConfigEntry) -> tuple[int, str]:
    """(cổng nghe, khoá) của đầu nhận mic NV244. Khoá trống = đầu nhận KHÔNG mở (an toàn
    mặc định); khoá chỉ nằm trong options, không ghi log, không mã cứng."""
    return (int(conf(entry, CONF_MIC_LISTEN_PORT, DEFAULT_MIC_LISTEN_PORT)),
            str(conf(entry, CONF_MIC_LISTEN_KEY, "") or ""))


def mic_host_hieu_luc(entry: ConfigEntry) -> str:
    """IP loa dùng cho mic: ô «máy chủ mic» nếu có (chế độ nối ra cũ), không thì CHÍNH IP loa khi đã có khoá
    đầu nhận (APK nối vào HA) — người dùng không phải nhập lại một địa chỉ đã biết."""
    host = mic_address(entry)[0]
    return host or (speaker_host(entry) if mic_listen(entry)[1] else "")


def cong_nghe_trong(entries, entry: ConfigEntry) -> int:
    """Cổng nghe mic nhỏ nhất từ ``DEFAULT_MIC_LISTEN_PORT`` mà loa khác chưa dùng: mỗi loa một cổng, khỏi đụng nhau."""
    dung = {mic_listen(e)[0] for e in entries if e.entry_id != entry.entry_id and mic_listen(e)[1]}
    cong = DEFAULT_MIC_LISTEN_PORT
    while cong in dung:
        cong += 1
    return cong


def wake_mode(entry: ConfigEntry) -> str:
    """``ha`` (từ đánh thức do pipeline HA dò, mic về HA liên tục) hoặc ``speaker`` (từ đánh
    thức trên loa, HA chỉ nhận luồng sau trigger). Giá trị lạ → mặc định."""
    v = str(conf(entry, CONF_WAKE_MODE, DEFAULT_WAKE_MODE))
    return v if v in (WAKE_HA, WAKE_SPEAKER) else DEFAULT_WAKE_MODE


def ha_url(entry: ConfigEntry) -> str:
    """Địa chỉ HA mà loa / go2rtc gọi tới (đã kiểm ở options flow); trống = chưa đặt."""
    return str(conf(entry, CONF_HA_URL, "") or "").strip().rstrip("/")


def play_address(entry: ConfigEntry) -> tuple[str, int]:
    """(host, cổng) kênh phát PCM về loa. Host trống = cùng máy với loa; cổng 0 = chưa có kênh
    (bộ đàm tắt)."""
    host = str(conf(entry, CONF_PLAY_HOST, "") or "").strip() or speaker_host(entry)
    return host, int(conf(entry, CONF_PLAY_PORT, DEFAULT_PLAY_PORT))


@dataclass(frozen=True)
class TalkSettings:
    """Tham số cổng mở loa của bộ đàm nửa công. Mặc định CHƯA ĐO trên loa R1 (xem const.py)."""

    threshold_db: float = DEFAULT_TALK_THRESHOLD_DB
    silence_s: float = DEFAULT_TALK_SILENCE
    preroll_s: float = DEFAULT_TALK_PREROLL
    tail_s: float = DEFAULT_TALK_TAIL

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> "TalkSettings":
        return cls(
            threshold_db=float(conf(entry, CONF_TALK_THRESHOLD_DB, DEFAULT_TALK_THRESHOLD_DB)),
            silence_s=float(conf(entry, CONF_TALK_SILENCE, DEFAULT_TALK_SILENCE)),
            preroll_s=float(conf(entry, CONF_TALK_PREROLL, DEFAULT_TALK_PREROLL)),
            tail_s=float(conf(entry, CONF_TALK_TAIL, DEFAULT_TALK_TAIL)))


def noise_settings(entry: ConfigEntry) -> NoiseSettings:
    return NoiseSettings(
        enabled=bool(conf(entry, CONF_NOISE_ENABLE, DEFAULT_NOISE_ENABLE)),
        strength_db=float(conf(entry, CONF_NOISE_STRENGTH_DB, DEFAULT_NOISE_STRENGTH_DB)),
        voice_db=float(conf(entry, CONF_NOISE_VOICE_DB, DEFAULT_NOISE_VOICE_DB)))


def agc_settings(entry: ConfigEntry) -> AgcSettings:
    return AgcSettings(
        enabled=bool(conf(entry, CONF_AGC_ENABLE, DEFAULT_AGC_ENABLE)),
        target_db=float(conf(entry, CONF_AGC_TARGET_DB, DEFAULT_AGC_TARGET_DB)),
        max_gain_db=float(conf(entry, CONF_AGC_MAX_GAIN_DB, DEFAULT_AGC_MAX_GAIN_DB)),
        silence_db=float(conf(entry, CONF_AGC_SILENCE_DB, DEFAULT_AGC_SILENCE_DB)))


def limiter_settings(entry: ConfigEntry) -> LimiterSettings:
    return LimiterSettings(
        enabled=bool(conf(entry, CONF_LIMITER_ENABLE, DEFAULT_LIMITER_ENABLE)),
        ceiling=float(conf(entry, CONF_LIMITER_CEILING, DEFAULT_LIMITER_CEILING)))


@dataclass(frozen=True)
class DuplexSettings:
    """Tham số phiên đàm thoại SONG CÔNG (NV246). Mọi mặc định CHƯA ĐO trên loa R1
    (xem const.py): ngưỡng VAD, đệm trước/sau, hạn phiên, cắt vọng tuỳ chọn."""

    vad_threshold: float = DEFAULT_DUPLEX_VAD_THRESHOLD
    preroll_s: float = DEFAULT_DUPLEX_PREROLL
    hangover_s: float = DEFAULT_DUPLEX_HANGOVER
    max_s: float = DEFAULT_DUPLEX_MAX_S
    duck: bool = DEFAULT_DUPLEX_DUCK
    duck_db: float = DEFAULT_DUPLEX_DUCK_DB

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> "DuplexSettings":
        return cls(
            vad_threshold=float(conf(entry, CONF_DUPLEX_VAD_THRESHOLD,
                                     DEFAULT_DUPLEX_VAD_THRESHOLD)),
            preroll_s=float(conf(entry, CONF_DUPLEX_PREROLL, DEFAULT_DUPLEX_PREROLL)),
            hangover_s=float(conf(entry, CONF_DUPLEX_HANGOVER, DEFAULT_DUPLEX_HANGOVER)),
            max_s=float(conf(entry, CONF_DUPLEX_MAX_S, DEFAULT_DUPLEX_MAX_S)),
            duck=bool(conf(entry, CONF_DUPLEX_DUCK, DEFAULT_DUPLEX_DUCK)),
            duck_db=float(conf(entry, CONF_DUPLEX_DUCK_DB, DEFAULT_DUPLEX_DUCK_DB)))


def duplex_settings(entry: ConfigEntry) -> DuplexSettings:
    return DuplexSettings.from_entry(entry)


def wake_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Cài đặt từ đánh thức (đọc từ tuỳ chọn). Chỉ là cấu hình: loa chưa có dịch vụ đánh thức."""
    return {
        "bat": bool(conf(entry, CONF_WAKE_ENABLE, DEFAULT_WAKE_ENABLE)),
        "tu_khoa": str(conf(entry, CONF_WAKE_WORD, DEFAULT_WAKE_WORD) or ""),
        "do_nhay": float(conf(entry, CONF_WAKE_SENSITIVITY, DEFAULT_WAKE_SENSITIVITY)),
    }


def adb_tu_dong_dong(entry: ConfigEntry) -> bool:
    """Chủ máy chọn chế độ «đóng ADB»: tự đóng ADB mạng của loa khi APK đã nối về HA."""
    return conf(entry, CONF_ADB_TU_DONG, False) is True


def adb_settings(entry: ConfigEntry) -> tuple[str, str]:
    """(địa chỉ adb-server, chế độ ``auto``/``server``/``direct``). Chế độ lạ rơi về ``auto``."""
    mode = str(conf(entry, CONF_ADB_MODE, DEFAULT_ADB_MODE))
    mode = mode if mode in ("auto", "server", "direct") else DEFAULT_ADB_MODE
    server = str(conf(entry, CONF_ADB_SERVER, DEFAULT_ADB_SERVER) or "").strip()
    if mode == "server" and not server:                # chọn tay «server» mà bỏ trống ô: dùng adb-server cục bộ
        server = ADB_SERVER_LOCAL
    return server, mode
