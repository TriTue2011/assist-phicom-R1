"""Cổng HTTP mà LOA (hoặc go2rtc) gọi vào HA, khoá ngẫu nhiên riêng từng loa trong URL (``?k=``).

* ``WakeView`` — loa báo từ đánh thức (``event`` = ``wake``) hoặc còn sống (``alive``).
  **PHÍA LOA CHƯA CÓ**: đường này là hợp đồng phía HA, test bằng POST giả (docs/HOP-DONG-PHIA-LOA.md).
* ``PingView`` — để options flow kiểm ``ha_url`` có thật sự trỏ về HA này hay không.
* ``xac_thuc`` — kiểm khoá cho mọi đường. Khoá SAI (thường: khoá đã bị đổi mà dòng cấu hình
  cũ trên loa/go2rtc còn nguyên) → 401 kèm lời nhắn rõ + MỘT thông báo trong HA cho tới khi có
  lần gọi đúng hoặc khoá được đổi. Gọi sai lặp lại chỉ đếm, KHÔNG sinh thêm thông báo/log.
"""

from __future__ import annotations

import hmac
import ipaddress
import logging
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from homeassistant.components import persistent_notification
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_INTERCOM_KEY, DOMAIN
from .dam_thoai import R1SessionBusy

_LOGGER = logging.getLogger(__name__)

#: Gợi ý cho bên gọi lặp: đừng dồn dập khi khoá sai.
RETRY_AFTER_S = "60"
PING_TIMEOUT = 5.0
_FAILS = f"{DOMAIN}_khoa_sai"


def _notification_id(entry_id: str) -> str:
    return f"{DOMAIN}_khoa_sai_{entry_id}"


def xoa_canh_bao_khoa(hass: HomeAssistant, entry_id: str) -> None:
    """Gỡ thông báo «khoá sai» (khoá vừa được đổi / có lần gọi đúng)."""
    if hass.data.get(_FAILS, {}).pop(entry_id, None):
        persistent_notification.async_dismiss(hass, _notification_id(entry_id))


def so_lan_khoa_sai(hass: HomeAssistant, entry_id: str) -> int:
    return hass.data.get(_FAILS, {}).get(entry_id, 0)


def _khoa_sai(hass: HomeAssistant, entry) -> None:
    dem = hass.data.setdefault(_FAILS, {})
    dem[entry.entry_id] = dem.get(entry.entry_id, 0) + 1
    if dem[entry.entry_id] > 1:
        _LOGGER.debug("%s: lại có lời gọi sai khoá (%d)", entry.title, dem[entry.entry_id])
        return
    _LOGGER.warning("%s: có lời gọi vào loa R1 với khoá SAI (khoá đã bị đổi?) — "
                    "cập nhật cấu hình trên loa/go2rtc", entry.title)
    persistent_notification.async_create(
        hass,
        message=("Loa hoặc go2rtc đang gọi vào Home Assistant bằng khoá cũ hoặc sai nên bị từ "
                 "chối (401). Lấy cấu hình mới bằng dịch vụ r1_speaker.get_intercom_source / "
                 "r1_speaker.get_wake_endpoint rồi dán lại vào loa/go2rtc. Thông báo này tự "
                 "mất khi có lời gọi đúng."),
        title=f"{entry.title}: khoá bị đổi hoặc sai", notification_id=_notification_id(entry.entry_id))


def tu_choi_401() -> web.Response:
    return web.Response(status=401, text="bad or outdated key (r1_speaker)",
                        headers={"Retry-After": RETRY_AFTER_S})


def xac_thuc(hass: HomeAssistant, entry_id: str, key: str):
    """``(entry, coordinator)`` nếu khoá đúng, ngược lại None (và ghi nhận khoá sai)."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or getattr(entry, "runtime_data", None) is None:
        return None
    khoa = str(entry.data.get(CONF_INTERCOM_KEY) or "")
    if not khoa or not hmac.compare_digest(khoa.encode(), key.encode()):
        _khoa_sai(hass, entry)
        return None
    xoa_canh_bao_khoa(hass, entry_id)
    return entry, entry.runtime_data


class PingView(HomeAssistantView):
    url = "/api/r1_speaker/ping/{entry_id}"
    name = "api:r1_speaker:ping"
    requires_auth = False

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        if xac_thuc(request.app["hass"], entry_id, request.query.get("k", "")) is None:
            return tu_choi_401()
        return web.json_response({"r1_speaker": True})


class WakeView(HomeAssistantView):
    """Loa POST vào đây. Thân JSON tuỳ chọn: ``{"event": "wake"|"alive", "word": "<từ>"}``;
    thân rỗng = ``wake``. 200 phiên đã mở (hoặc nhịp tim đã nhận); 409 đang có phiên khác;
    503 mic chưa cấu hình / đang tắt; 401 khoá sai."""

    url = "/api/r1_speaker/wake/{entry_id}"
    name = "api:r1_speaker:wake"
    requires_auth = False

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        found = xac_thuc(hass, entry_id, request.query.get("k", ""))
        if found is None:
            return tu_choi_401()
        _entry, coordinator = found
        talk = coordinator.talk
        try:
            body = await request.json() if request.can_read_body else {}
        except ValueError:
            return web.json_response({"loi": "thân yêu cầu không phải JSON"}, status=400)
        if not isinstance(body, dict) or body.get("event", "wake") not in ("wake", "alive"):
            return web.json_response({"loi": "event phải là wake hoặc alive"}, status=400)
        if body.get("event", "wake") == "alive":
            talk.alive()
            return web.json_response({"nhan": "alive"})
        word = body.get("word")
        word = word[:64] if isinstance(word, str) else None
        # Lỗi thiếu mic / bận phải trả về loa kèm lý do (không im lặng):
        try:
            await talk.trigger(word)
        except HomeAssistantError as exc:
            return web.json_response({"loi": str(exc)},
                                     status=409 if isinstance(exc, R1SessionBusy) else 503)
        return web.json_response({"phien": "mo"})


# ── Kiểm ha_url khi cấu hình ────────────────────────────────────────────────────

def la_loopback(host: str) -> bool:
    host = (host or "").strip().strip("[]").lower()
    if host in ("localhost", "ip6-localhost", ""):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".localhost")
    return ip.is_loopback or ip.is_unspecified


async def kiem_tra_ha_url(hass: HomeAssistant, url: str, entry_id: str, key: str,
                          speaker_host: str) -> str | None:
    """None nếu ``url`` dùng được; ngược lại KHOÁ LỖI (khớp strings.json) của options flow.

    * ``invalid_ha_url``: không phải http(s)://máy[:cổng] hợp lệ.
    * ``ha_url_loopback``: 127.0.0.1 / localhost / 0.0.0.0 — loa và go2rtc nằm máy khác nên
      địa chỉ này trỏ về chính chúng chứ không phải HA. (Chỉ chấp nhận khi chính loa cũng ở
      loopback, tức chạy thử trên một máy.)
    * ``ha_url_unreachable``: HA không gọi được ``<url>/api/r1_speaker/ping`` hoặc đầu kia
      không phải HA này (khoá không khớp).
    HA tự gọi chính nó chỉ chứng minh địa chỉ có đáp, KHÔNG chứng minh loa với tới được —
    vì thế phép thử loopback đứng riêng ở trên."""
    url = (url or "").strip().rstrip("/")
    try:
        p = urlsplit(url)
        host, _port = p.hostname, p.port
    except ValueError:
        return "invalid_ha_url"
    if (p.scheme not in ("http", "https") or not host or p.username or p.password
            or p.path or p.query or p.fragment or any(c.isspace() for c in url)):
        return "invalid_ha_url"
    if la_loopback(host) and not la_loopback(speaker_host):
        return "ha_url_loopback"
    try:
        async with async_get_clientsession(hass).get(
                f"{url}/api/{DOMAIN}/ping/{entry_id}", params={"k": key},
                timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT), allow_redirects=False) as r:
            if r.status != 200 or (await r.json(content_type=None)).get("r1_speaker") is not True:
                return "ha_url_unreachable"
    except (aiohttp.ClientError, TimeoutError, ValueError, AttributeError):
        return "ha_url_unreachable"
    return None
