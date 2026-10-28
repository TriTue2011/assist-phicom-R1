"""Máy khách WebSocket (RFC 6455) cho loa Phicomm R1.

Mỗi thao tác mở một kết nối ngắn rồi đóng: loa không cần giữ phiên, và lỗi mạng chỉ làm
hỏng đúng thao tác đó. Mọi lỗi mạng / sai định dạng được gói thành ``R1Error``.

Nguồn lệnh: tài liệu dịch ngược (bảng lệnh, các dòng "Đã chứng minh bằng mã"). Các điểm
CHƯA kiểm trên loa thật được đánh dấu ``CHƯA KIỂM`` bên dưới.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

import aiohttp

from .const import EQ_BANDS, RESPONSE_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class R1Error(Exception):
    """Không nói chuyện được với loa (mất kết nối, hết giờ, phản hồi sai định dạng)."""


@dataclass(frozen=True)
class R1State:
    """Ảnh chụp trạng thái loa. Trường ``None`` = loa không báo (thực thể thành unavailable)."""

    vol: int
    dlna_open: bool | None = None
    airplay_open: bool | None = None
    device_state: int | None = None
    music_light_enable: bool | None = None
    music_light_luma: int | None = None
    music_light_chroma: int | None = None
    #: Phần từ get_eq_config; ``None`` khi loa không trả hoặc trả sai định dạng.
    bass_enable: bool | None = None
    bass_strength: int | None = None
    loudness_enable: bool | None = None
    loudness_gain: int | None = None
    bands: tuple[int | None, ...] = (None,) * EQ_BANDS
    #: Giới hạn mức một dải (mB) do loa báo (eq.Bands.minBandLevel / maxBandLevel).
    eq_min: int | None = None
    eq_max: int | None = None
    #: eq.Eq_Enable: EQ đang bật hay tắt.
    eq_enable: bool | None = None
    #: eq.Preset_list: ((số Preset, tên), ...); ``eq_preset`` = eq.Current_Preset (-1 = không
    #: preset nào, tức đang chỉnh tay).
    eq_presets: tuple[tuple[int, str], ...] | None = None
    eq_preset: int | None = None


#: Lệnh khởi động lại loa của app AI box (``cj.java:39``): khởi động lại adbd cục bộ rồi ``adb reboot`` ngay trên loa.
REBOOT_SHELL = "stop adbd&&start adbd&&adb reboot"


def build_message(msg_type: str, params: dict[str, Any] | None = None) -> str:
    """Dựng khung JSON gửi loa.

    Hợp đồng giao việc: ``{"type": ..., "data": {...}}``. Mã nguồn web của loa lại gửi
    tham số phẳng ở cấp ngoài (``{"type": "set_bass_enable", "enable": true}``). Chưa biết
    loa nhận kiểu nào (CHƯA KIỂM) nên gửi cả hai; trường thừa bị bỏ qua. Khi đã đo được
    thì chỉ giữ một kiểu, sửa đúng ở đây.
    """
    params = dict(params or {})
    return json.dumps({"type": msg_type, **params, "data": params})


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise R1Error(f"{name} không phải số: {value!r}")
    return int(value)


def _as_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise R1Error(f"{name} không phải boolean: {value!r}")


def _opt(payload: dict, key: str, conv) -> Any:
    return None if key not in payload else conv(payload[key], key)


def _payload(msg: dict) -> dict:
    """Lấy phần dữ liệu: ``data`` là object, chuỗi JSON (như web của loa), hoặc phẳng."""
    if "data" not in msg:
        return msg
    data = msg["data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError as exc:
            raise R1Error(f"data không phải JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise R1Error(f"data không phải object: {type(data).__name__}")
    return data


def parse_info(msg: dict) -> dict[str, Any]:
    """get_info → các trường của R1State. ``vol`` bắt buộc."""
    p = _payload(msg)
    if "vol" not in p:
        raise R1Error("get_info thiếu vol")
    return {
        "vol": _as_int(p["vol"], "vol"),
        "dlna_open": _opt(p, "dlna_open", _as_bool),
        "airplay_open": _opt(p, "airplay_open", _as_bool),
        "device_state": _opt(p, "device_state", _as_int),
        "music_light_enable": _opt(p, "music_light_enable", _as_bool),
        "music_light_luma": _opt(p, "music_light_luma", _as_int),
        "music_light_chroma": _opt(p, "music_light_chroma", _as_int),
    }


def _flag(payload: dict, *keys: str) -> bool | None:
    """Cờ bật/tắt: lấy khoá đầu tiên có mặt (loa báo cả ``Xxx_Enable`` lẫn
    ``sound_effects_xxx_enable``; đo trên loa thật, hai cờ đổi cùng nhau)."""
    for key in keys:
        if key in payload:
            return _as_bool(payload[key], key)
    return None


def _parse_presets(eq: dict) -> tuple[tuple[int, str], ...] | None:
    lst = eq.get("Preset_list")
    if lst is None:
        return None
    if not isinstance(lst, list):
        raise R1Error("get_eq_config: Preset_list không phải danh sách")
    out = []
    for i, item in enumerate(lst):
        if not isinstance(item, dict) or "Preset" not in item or not isinstance(
                item.get("Name"), str):
            raise R1Error(f"get_eq_config: preset {i} sai định dạng")
        out.append((_as_int(item["Preset"], f"Preset[{i}]"), item["Name"]))
    return tuple(out)


def parse_eq(msg: dict) -> dict[str, Any]:
    """get_eq_config → trường EQ. Cấu trúc ĐO trên loa thật (cổng 8080, mã 200, ``data`` là
    chuỗi JSON): ``eq.{Eq_Enable,Current_Preset,Preset_list,Bands.{list[i].BandLevel,
    minBandLevel,maxBandLevel}}``, ``bass.{Bass_Enable,Current_Strength}``,
    ``loudness.{Loudness_Enable,Current_Gain}``. Khoá vắng → None."""
    p = _payload(msg)
    out: dict[str, Any] = {}
    bass, loud, eq = p.get("bass") or {}, p.get("loudness") or {}, p.get("eq") or {}
    if not all(isinstance(x, dict) for x in (bass, loud, eq)):
        raise R1Error("get_eq_config: bass/loudness/eq sai kiểu")
    out["bass_enable"] = _flag(bass, "Bass_Enable", "sound_effects_bass_enable")
    out["bass_strength"] = _opt(bass, "Current_Strength", _as_int)
    out["loudness_enable"] = _flag(loud, "Loudness_Enable", "sound_effects_loudness_enable")
    out["loudness_gain"] = _opt(loud, "Current_Gain", _as_int)
    out["eq_enable"] = _flag(eq, "Eq_Enable", "sound_effects_eq_enable")
    out["eq_preset"] = _opt(eq, "Current_Preset", _as_int)
    out["eq_presets"] = _parse_presets(eq)
    band_block = eq.get("Bands") or {}
    if not isinstance(band_block, dict):
        raise R1Error("get_eq_config: eq.Bands sai kiểu")
    out["eq_min"] = _opt(band_block, "minBandLevel", _as_int)
    out["eq_max"] = _opt(band_block, "maxBandLevel", _as_int)
    lst = band_block.get("list")
    bands: list[int | None] = [None] * EQ_BANDS
    if isinstance(lst, list):
        for i, band in enumerate(lst[:EQ_BANDS]):
            if not isinstance(band, dict) or "BandLevel" not in band:
                raise R1Error(f"get_eq_config: dải {i} sai định dạng")
            bands[i] = _as_int(band["BandLevel"], f"BandLevel[{i}]")
    out["bands"] = tuple(bands)
    return out


class R1Client:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session, self.host, self.port = session, host, port

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def _open(self) -> aiohttp.ClientWebSocketResponse:
        return await self._session.ws_connect(
            self.url, timeout=aiohttp.ClientWSTimeout(ws_close=RESPONSE_TIMEOUT))

    async def async_fetch(self) -> R1State:
        """Hỏi get_info + get_eq_config. get_info bắt buộc; EQ hỏng thì chỉ phần EQ là None."""
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT * 2):
                ws = await self._open()
                try:
                    return await self._fetch_on(ws)
                finally:
                    await ws.close()
        except R1Error:
            raise
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as exc:
            raise R1Error(f"{self.url}: {exc!r}") from exc

    async def _fetch_on(self, ws: aiohttp.ClientWebSocketResponse) -> R1State:
        await ws.send_str(build_message("get_info"))
        await ws.send_str(build_message("get_eq_config"))
        info: dict | None = None
        eq: dict | None = None
        eq_loi: str | None = None
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                while info is None or (eq is None and eq_loi is None):
                    raw = await ws.receive()
                    if raw.type != aiohttp.WSMsgType.TEXT:
                        raise R1Error(f"kết nối đóng / khung lạ: {raw.type!r}")
                    try:
                        msg = json.loads(raw.data)
                    except ValueError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == "get_info":
                        info = parse_info(msg)
                    elif msg.get("type") == "get_eq_config":
                        try:
                            eq = parse_eq(msg)
                        except R1Error as exc:
                            eq_loi = str(exc)
        except TimeoutError:
            if info is None:
                raise R1Error("hết giờ chờ get_info") from None
        if eq_loi or eq is None:
            _LOGGER.warning("R1 %s: get_eq_config lỗi, bỏ qua EQ (%s)", self.host,
                            eq_loi or "không phản hồi")
            eq = {}
        return R1State(**info, **eq)

    async def async_send(self, msg_type: str, params: dict[str, Any] | None = None) -> None:
        """Gửi một lệnh (loa không trả xác nhận). Lỗi mạng → R1Error."""
        await self._send_raw(build_message(msg_type, params))

    async def _send_raw(self, khung: str) -> None:
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT * 2):
                ws = await self._open()
                try:
                    await ws.send_str(khung)
                finally:
                    await ws.close()
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as exc:
            raise R1Error(f"{self.url}: {exc!r}") from exc

    async def reboot_shell(self) -> None:
        """Khởi động lại loa qua tin ``shell`` của cổng 8080 (không cần ADB mạng). ĐÃ KIỂM trên loa thật 28/10/2026: loa tắt sau
        khoảng 10 giây, lên lại sau khoảng nửa phút, thời gian bật máy về 32 giây. Lệnh chạy dưới uid ``system`` (không phải root),
        nên ``reboot`` và ``setprop sys.powerctl reboot`` bị bỏ qua lặng lẽ; chỉ lệnh dưới đây (do app AI box dùng) có hiệu lực.
        Khung gửi phẳng, đúng như đã thử (không kèm ``data``)."""
        await self._send_raw(json.dumps({"type": "shell", "type_id": "ha", "shell": REBOOT_SHELL}))

    # ── lệnh đã chứng minh bằng mã ──────────────────────────────────────────
    # Đã XÁC NHẬN bằng ghi thật trên loa (21/10/2026, đọc lại bằng get_eq_config, đã trả về
    # giá trị gốc): set_eq_bandlevel (band 0) và set_bass_enable. Còn lại (set_eq_enable,
    # set_bass_strength, set_loudness_enable, set_loudness_gain) CHỈ có trong tài liệu dịch
    # ngược, chưa ghi thử.

    async def set_eq_enable(self, on: bool) -> None:
        """Có trong bảng lệnh dịch ngược (AudioControl.js:107); CHƯA xác nhận bằng ghi thật."""
        await self.async_send("set_eq_enable", {"enable": on})

    async def set_bass_enable(self, on: bool) -> None:
        await self.async_send("set_bass_enable", {"enable": on})

    async def set_bass_strength(self, strength: int) -> None:
        await self.async_send("set_bass_strength", {"strength": strength})

    async def set_loudness_enable(self, on: bool) -> None:
        await self.async_send("set_loudness_enable", {"enable": on})

    async def set_loudness_gain(self, gain: int) -> None:
        await self.async_send("set_loudness_gain", {"gain": gain})

    async def set_eq_bandlevel(self, band: int, level: int) -> None:
        await self.async_send("set_eq_bandlevel", {"band": band, "level": level})

    async def set_eq_bands(self, levels: Sequence[int]) -> None:
        """Ghi cả 5 dải trên MỘT kết nối (chọn preset). Cùng lệnh ``set_eq_bandlevel`` đã xác nhận."""
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT * 2):
                ws = await self._open()
                try:
                    for band, level in enumerate(levels):
                        await ws.send_str(build_message("set_eq_bandlevel", {"band": band, "level": level}))
                finally:
                    await ws.close()
        except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as exc:
            raise R1Error(f"{self.url}: {exc!r}") from exc

    async def set_dlna_open(self, on: bool) -> None:
        await self.async_send("Set_DLNA_Open", {"open": on, "type_id": "ha"})

    async def set_airplay_open(self, on: bool) -> None:
        await self.async_send("Set_AirPlay_Open", {"open": on, "type_id": "ha"})

    # ── send_message: CHƯA KIỂM trên thiết bị ───────────────────────────────

    async def set_volume(self, vol: int) -> None:
        """CHƯA KIỂM: ``send_message`` what=4, arg1=5, arg2=âm lượng (0–15)."""
        await self.async_send("send_message", {"what": 4, "arg1": 5, "arg2": vol})

    async def set_bluetooth(self, on: bool) -> None:
        """CHƯA KIỂM: ``send_message`` what=64, arg1=1 (bật) / 2 (tắt). Chưa có thực thể
        vì get_info không báo trạng thái Bluetooth."""
        await self.async_send("send_message", {"what": 64, "arg1": 1 if on else 2})


def with_overrides(state: R1State, **changes: Any) -> R1State:
    """Trạng thái lạc quan sau lệnh; lần hỏi kế tiếp sẽ đối chiếu lại với loa."""
    return replace(state, **changes)
