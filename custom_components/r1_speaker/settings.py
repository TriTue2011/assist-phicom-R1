"""Cấu hình của một loa: ``entry.options`` đè lên ``entry.data`` (hai nơi cùng khoá).

Nhập ở config flow (host, cổng EQ) nằm trong ``data``; options flow ghi cùng khoá vào
``options`` nên đổi IP / cổng không cần xoá rồi thêm lại loa. Không số nào mã cứng ở nơi dùng:
mọi chỗ đọc qua đây, mặc định lấy từ ``const.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .agc import AgcSettings, LimiterSettings
from .noise_suppress import NoiseSettings
from .const import ADB_SERVER_LOCAL, CONF_ADB_MODE, CONF_ADB_SERVER, CONF_ADB_TU_DONG, CONF_PHIM_MA, CONF_PHIM_NGUON, DEFAULT_ADB_MODE, DEFAULT_ADB_SERVER, DEFAULT_PHIM_MA, DEFAULT_PHIM_NGUON
from .const import CONF_KENH, CONF_KENH_KIEU, DEFAULT_KENH_KIEU, KENH_KIEU
from .const import CONF_AIRPLAY_PORT, CONF_DUONG_PHAT, DEFAULT_AIRPLAY_PORT, DEFAULT_DUONG_PHAT, DUONG_PHAT_GIA_TRI
from .const import (CONF_KDL_BAT, CONF_KDL_GIO, CONF_KDL_NGAY, CONF_KDL_TU_PHUC_HOI, DEFAULT_KDL_BAT, DEFAULT_KDL_GIO,
                    DEFAULT_KDL_NGAY, DEFAULT_KDL_TU_PHUC_HOI, KDL_NGAY_MA)
from .const import CONF_TTS_SONG_SONG, DEFAULT_TTS_SONG_SONG, CONF_HA_NHAC_XUONG, DEFAULT_HA_NHAC_XUONG, CONF_HA_NHAC_NAC, DEFAULT_HA_NHAC_NAC
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


def kenh_ten(entry: ConfigEntry) -> str:
    """Tên kênh đàm thoại mà loa này tham gia (trống = không tham gia kênh nào)."""
    return str(conf(entry, CONF_KENH, "") or "").strip()


def kenh_kieu(entry: ConfigEntry) -> str:
    """Kiểu kênh: ``ptt`` hoặc ``voice``; giá trị lạ → mặc định ``ptt``."""
    kieu = str(conf(entry, CONF_KENH_KIEU, DEFAULT_KENH_KIEU) or "").strip()
    return kieu if kieu in KENH_KIEU else DEFAULT_KENH_KIEU


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


def phim_ma(entry: ConfigEntry) -> set[int]:
    """Mã phím được chạy hành động theo cử chỉ: chuỗi «195,116» → {195, 116}; phần sai (không phải số 1–999) bị bỏ, tối đa 16 mã."""
    ra: set[int] = set()
    for p in str(conf(entry, CONF_PHIM_MA, DEFAULT_PHIM_MA) or "").split(","):
        p = p.strip()
        if p.isdigit() and 1 <= int(p) <= 999 and len(ra) < 16:
            ra.add(int(p))
    return ra


def phim_nguon(entry: ConfigEntry) -> str:
    """``adb`` / ``apk`` / ``tat``; giá trị lạ rơi về mặc định."""
    v = str(conf(entry, CONF_PHIM_NGUON, DEFAULT_PHIM_NGUON))
    return v if v in ("adb", "apk", "tat") else DEFAULT_PHIM_NGUON


def duong_phat(entry: ConfigEntry) -> str:
    """``dlna`` / ``dlna_truoc`` / ``airplay_truoc`` / ``airplay``; giá trị lạ rơi về mặc định (chỉ DLNA, như trước khi có AirPlay)."""
    v = str(conf(entry, CONF_DUONG_PHAT, DEFAULT_DUONG_PHAT))
    return v if v in DUONG_PHAT_GIA_TRI else DEFAULT_DUONG_PHAT


def tts_song_song_airplay(entry: ConfigEntry) -> bool:
    """NV287: tin báo đi AirPlay song song trong khi nhạc ở DLNA. Mặc định TẮT
    (chưa đo trên loa thật xem loa có trộn được hai luồng hay không)."""
    return conf(entry, CONF_TTS_SONG_SONG, DEFAULT_TTS_SONG_SONG) is True


def ha_nhac_xuong(entry: ConfigEntry) -> bool:
    """NV287: hạ nhạc nền trong lúc tin song song phát. Mặc định TẮT; chỉ có
    tác dụng khi ``tts_song_song_airplay`` bật (tin đi đường thường thì nhạc đã
    tạm dừng, hạ âm lượng không còn ý nghĩa)."""
    return conf(entry, CONF_HA_NHAC_XUONG, DEFAULT_HA_NHAC_XUONG) is True


def ha_nhac_nac(entry: ConfigEntry) -> int:
    """NV287: số nấc hạ khi ducking (thang 0–15 của loa). Giá trị lạ rơi về mặc định."""
    try:
        v = int(conf(entry, CONF_HA_NHAC_NAC, DEFAULT_HA_NHAC_NAC))
    except (TypeError, ValueError):
        return DEFAULT_HA_NHAC_NAC
    return v if 1 <= v <= 14 else DEFAULT_HA_NHAC_NAC


def airplay_port(entry: ConfigEntry) -> int:
    """Cổng RAOP của loa; số hỏng hoặc ngoài 1..65535 rơi về mặc định."""
    try:
        v = int(conf(entry, CONF_AIRPLAY_PORT, DEFAULT_AIRPLAY_PORT))
    except (TypeError, ValueError):
        return DEFAULT_AIRPLAY_PORT
    return v if 1 <= v <= 65535 else DEFAULT_AIRPLAY_PORT


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


def khoi_dong_lai_bat(entry: ConfigEntry) -> bool:
    """NV288: loa tự khởi động lại theo lịch. Mặc định TẮT."""
    return conf(entry, CONF_KDL_BAT, DEFAULT_KDL_BAT) is True


def khoi_dong_lai_gio(entry: ConfigEntry) -> time:
    """Giờ lịch (giờ địa phương). Nhận «HH:MM» hoặc «HH:MM:SS» (bộ chọn giờ của HA trả giây); giá trị hỏng rơi về mặc định."""
    for gia_tri in (conf(entry, CONF_KDL_GIO, DEFAULT_KDL_GIO), DEFAULT_KDL_GIO):
        try:
            return time.fromisoformat(str(gia_tri).strip()).replace(second=0, microsecond=0)
        except ValueError:
            continue
    raise AssertionError("DEFAULT_KDL_GIO không hợp lệ")          # pragma: no cover — hằng số trong mã


def khoi_dong_lai_ngay(entry: ConfigEntry) -> frozenset[str]:
    """Mã các thứ được chọn (``t2``…``cn``). Danh sách rỗng là một lựa chọn hợp lệ (không ngày nào); không phải danh sách hoặc có mã lạ
    thì bỏ mã lạ, kiểu hỏng hẳn rơi về mặc định (mọi ngày)."""
    v = conf(entry, CONF_KDL_NGAY, DEFAULT_KDL_NGAY)
    if not isinstance(v, (list, tuple, set, frozenset)):
        return frozenset(DEFAULT_KDL_NGAY)
    return frozenset(m for m in v if m in KDL_NGAY_MA)


def khoi_dong_lai_khi_treo(entry: ConfigEntry) -> bool:
    """NV288: HA được phép khởi động lại loa MỘT lần khi loa «treo» (mạng thông, ứng dụng im). Mặc định TẮT."""
    return conf(entry, CONF_KDL_TU_PHUC_HOI, DEFAULT_KDL_TU_PHUC_HOI) is True
