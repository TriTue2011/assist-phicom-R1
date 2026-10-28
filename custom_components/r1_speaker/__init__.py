"""Phicomm R1 Speaker — điều khiển loa R1 qua WebSocket trong mạng LAN, không cần add-on.

Gồm: thực thể điều khiển (EQ, âm lượng, DLNA, AirPlay), vệ tinh Assist (``assist_satellite.r1``),
bộ đàm nửa công (``intercom.py``) và thẻ Lovelace chỉnh EQ (``www/r1-eq-card.js``).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from datetime import timedelta
from pathlib import Path

import voluptuous as vol
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from . import cai_ung_dung, den_chinh, giao_dien, lenh_apk, media_player, nang_cao
from .client import R1Client
from .const import ADB_PORT
from .const import (CARD_GOP_URL, CARD_URL, CONF_INTERCOM_KEY, CONF_MIC_CHUA_GHEP, CONF_MIC_LISTEN_KEY, CONF_MIC_LISTEN_PORT, DOMAIN, SETTINGS_CARD_URL, TALK_CARD_URL,
                    WAKE_SPEAKER)
from .cong_vao import PingView, WakeView
from .dam_thoai_ws import DamThoaiWsView
from .ghep_khoa import GhepKhoaView
from .nghe_ws import NgheWsView
from .den import R1Lights, dang_ky_dich_vu as dang_ky_dich_vu_den
from .adb_client import AdbDevice
from .cai_ung_dung import BoCai
from .he_thong import HeThongLoa
from .bao_thuc import BaoThuc, dang_ky_dich_vu as dang_ky_dich_vu_bao_thuc
from .den_apk import ApkLights, LightsRouter
from .tu_dong_dong_adb import TuDongDongAdb
from .tu_ket_noi import TuKetNoi
from .den_adb import AdbLights
from .dam_thoai import R1Talk
from .dmr import R1Dmr
from .giu_nhac import MusicKeeper
from .coordinator import R1ConfigEntry, R1Coordinator
from .intercom import IntercomView, MicView, R1Intercom, go2rtc_source, wake_endpoint
from .mic import R1Mic
from .mic_server import R1MicServer
from .playback import R1Playback
from .phim import Phim, dang_ky_dich_vu as dang_ky_dich_vu_phim
from .settings import (adb_settings, adb_tu_dong_dong, phim_ma, DuplexSettings, TalkSettings, agc_settings, cong_nghe_trong, limiter_settings, mic_host_hieu_luc, noise_settings, ha_url, mic_address, mic_listen, play_address, speaker_host,
                       speaker_port, wake_mode)
from .song_cong import DuplexView, R1Duplex

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.ASSIST_SATELLITE, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT, Platform.MEDIA_PLAYER,
             Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.UPDATE]

_WWW = Path(__file__).parent / "www"
_CARDS = ((CARD_URL, _WWW / "r1-eq-card.js"), (TALK_CARD_URL, _WWW / "r1-talk-card.js"),
          (SETTINGS_CARD_URL, _WWW / "r1-settings-card.js"),
          (CARD_GOP_URL, _WWW / "r1-card.js"))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.http.register_view(IntercomView())
    hass.http.register_view(MicView())
    hass.http.register_view(DuplexView())
    hass.http.register_view(DamThoaiWsView())
    hass.http.register_view(GhepKhoaView())
    hass.http.register_view(NgheWsView())
    hass.http.register_view(WakeView())
    hass.http.register_view(PingView())
    await _register_card(hass)
    await giao_dien.dang_ky_tai_nguyen(hass)
    dang_ky_dich_vu_den(hass)
    dang_ky_dich_vu_bao_thuc(hass)
    dang_ky_dich_vu_phim(hass)
    den_chinh.dang_ky_dich_vu(hass)
    lenh_apk.dang_ky(hass)
    nang_cao.dang_ky_dich_vu(hass)
    ds_apk = await hass.async_add_executor_job(cai_ung_dung.doc_bo_cai)         # đọc tệp: ngoài vòng lặp sự kiện
    cai_ung_dung.dang_ky_dich_vu(hass, [u.id for u in ds_apk])

    def _entry_va_goc(call: ServiceCall):
        entity_id = call.data["entity_id"]
        rec = er.async_get(hass).async_get(entity_id)
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker")
        # Thứ tự: tham số dịch vụ → ha_url đã kiểm ở tuỳ chọn → đoán (127.0.0.1 chỉ đúng khi
        # bên gọi chạy CÙNG máy với HA).
        goc = call.data.get("ha_url", "").strip() or ha_url(entry)
        if not goc:
            http = getattr(hass, "http", None)
            cong = getattr(http, "server_port", None) or 8123
            kieu = "https" if getattr(http, "ssl_certificate", None) else "http"
            goc = f"{kieu}://127.0.0.1:{cong}"
        return entry, goc

    async def _nguon_bo_dam(call: ServiceCall) -> ServiceResponse:
        entry, goc = _entry_va_goc(call)
        return go2rtc_source(goc, entry.entry_id, entry.data[CONF_INTERCOM_KEY])

    async def _diem_cuoi_wake(call: ServiceCall) -> ServiceResponse:
        entry, goc = _entry_va_goc(call)
        return wake_endpoint(goc, entry.entry_id, entry.data[CONF_INTERCOM_KEY])

    schema = vol.Schema({
        vol.Required("entity_id"): cv.entity_id,
        # Địa chỉ HA mà loa / máy chạy go2rtc gọi tới được; bỏ trống thì dùng ``ha_url`` của
        # tuỳ chọn (nếu đã đặt), rồi mới đoán.
        vol.Optional("ha_url"): vol.All(str, vol.Match(
            r"^https?://[^\s#]+$",
            msg="ha_url phải dạng http(s)://địa-chỉ:cổng, không dấu cách hay #")),
    })
    hass.services.async_register(DOMAIN, "get_intercom_source", _nguon_bo_dam, schema=schema,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "get_wake_endpoint", _diem_cuoi_wake, schema=schema,
                                 supports_response=SupportsResponse.ONLY)

    def _coordinator(call: ServiceCall) -> R1Coordinator:
        entity_id = call.data["entity_id"]
        rec = er.async_get(hass).async_get(entity_id)
        entry = hass.config_entries.async_get_entry(rec.config_entry_id) if rec else None
        if entry is None or entry.domain != DOMAIN or getattr(entry, "runtime_data", None) is None:
            raise ServiceValidationError(f"{entity_id} không phải thực thể của r1_speaker")
        return entry.runtime_data

    async def _mo_song_cong(call: ServiceCall) -> None:
        await _coordinator(call).duplex.async_start()

    async def _dong_song_cong(call: ServiceCall) -> None:
        _coordinator(call).duplex.end("nguoi_dung_ket_thuc")

    schema_phien = vol.Schema({vol.Required("entity_id"): cv.entity_id})
    hass.services.async_register(DOMAIN, "start_duplex", _mo_song_cong, schema=schema_phien)
    hass.services.async_register(DOMAIN, "stop_duplex", _dong_song_cong, schema=schema_phien)
    return True


class _TheView(HomeAssistantView):
    """Phục vụ một tệp thẻ và bắt trình duyệt luôn hỏi lại (ETag). Đường tĩnh mặc định không có
    ``Cache-Control``, nên trình duyệt tự đoán và giữ bản thẻ cũ nhiều giờ sau khi cập nhật."""

    requires_auth = False

    def __init__(self, url: str, path: Path) -> None:
        self.url = url
        # Cùng tệp còn phục vụ ở ``/r1_speaker/b/<bất kỳ>/<tên>.js``: thẻ gộp nạp thẻ con bằng đoạn
        # ``<bất kỳ>`` đổi mỗi lần mở trang, để proxy/CDN bỏ qua tham số ``?...`` cũng không giữ bản cũ.
        self.extra_urls = [f"/{DOMAIN}/b/{{ban}}/{path.name}"]
        self.name = f"{DOMAIN}:the:{path.stem}"
        self._path = path

    async def get(self, request: web.Request, ban: str | None = None) -> web.StreamResponse:
        # Đường dẫn đổi mỗi lần: không lớp đệm nào được giữ (no-store); đường cố định: luôn hỏi lại.
        kieu = "no-store" if ban is not None else "no-cache"
        # Đọc thẳng tệp ``.js`` rồi trả về. KHÔNG dùng ``web.FileResponse``: nó tự chọn tệp ``.js.gz``
        # đứng cạnh cho trình duyệt nhận gzip, nên một bản nén cũ còn sót che mọi bản cập nhật (22/10/2026:
        # điện thoại và Cloudflare thấy thẻ cũ suốt ngày, còn curl không nén thì thấy bản mới).
        noi_dung = await asyncio.get_running_loop().run_in_executor(None, self._path.read_bytes)
        return web.Response(body=noi_dung, content_type="text/javascript", charset="utf-8",
                            headers={"Cache-Control": kieu})


async def _register_card(hass: HomeAssistant) -> None:
    """Chỉ PHỤC VỤ các tệp thẻ. KHÔNG gắn chúng vào danh sách module phụ của giao diện
    (``add_extra_js_url``): module phụ chạy rất sớm, trước khi giao diện HA cài xong bộ đăng ký phần
    tử riêng, nên thẻ đăng ký ở bộ gốc mà HA không thấy → «Custom element not found» dù tệp đúng
    (đo 22/10/2026: cùng tệp nạp sớm thì HA không thấy, nạp muộn thì thấy). Thẻ nạp qua TÀI NGUYÊN
    Lovelace như mọi thẻ HACS: cần thêm ``/r1_speaker/r1-card.js`` (loại Mô-đun JavaScript); thẻ gộp
    tự nạp ba thẻ con."""
    for url, path in _CARDS:
        hass.http.register_view(_TheView(url, path))


#: Thực thể đã bỏ ở bản này (gộp hoặc thay): (nền tảng, khoá). Dọn khỏi sổ đăng ký để trang thiết bị
#: không còn dòng «không có sẵn» bỏ lại. Nút Đàm thoại/Kết thúc và «Bật mic luôn» → công tắc «Đàm
#: thoại»; công tắc «song song (cho phép)» và «nửa công» → MỘT công tắc «Mic loa song song»; hai
#: cảm biến đèn nhạc → hai số điều khiển.
_THUC_THE_DA_BO = (("button", "talk"), ("button", "end_talk"), ("switch", "always_on"),
                   ("switch", "half_duplex"), ("switch", "duplex_enable"), ("select", "intercom_mode"),
                   ("sensor", "music_light_luma"), ("sensor", "music_light_chroma"))


def _don_thuc_the_cu(hass: HomeAssistant, entry: R1ConfigEntry) -> None:
    registry = er.async_get(hass)
    for domain, key in _THUC_THE_DA_BO:
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
        if entity_id is not None:
            registry.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: R1ConfigEntry) -> bool:
    if not entry.data.get(CONF_INTERCOM_KEY):
        # Khoá bộ đàm riêng loa này, sinh một lần rồi giữ: dòng đã dán vào go2rtc.yaml phải
        # còn đúng sau mỗi lần khởi động lại HA.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_INTERCOM_KEY: secrets.token_urlsafe(24)})
    if not mic_listen(entry)[1] and not mic_address(entry)[0]:
        # Đường mic mới (APK nối vào HA): tự sinh khoá và cấp cổng riêng cho loa này, sinh một lần rồi giữ
        # (APK đã cài khoá này phải còn đúng sau mỗi lần HA khởi động lại). Không bắt người dùng nhập gì.
        cap = {CONF_MIC_LISTEN_KEY: secrets.token_urlsafe(24), CONF_MIC_CHUA_GHEP: True}
        if CONF_MIC_LISTEN_PORT not in entry.options and CONF_MIC_LISTEN_PORT not in entry.data:
            cap[CONF_MIC_LISTEN_PORT] = cong_nghe_trong(hass.config_entries.async_entries(DOMAIN), entry)
        hass.config_entries.async_update_entry(entry, data={**entry.data, **cap})
    client = R1Client(async_get_clientsession(hass), speaker_host(entry), speaker_port(entry))
    coordinator = R1Coordinator(hass, entry, client)
    # Loa tắt lúc khởi động HA vẫn được thêm: thực thể unavailable, tự hồi phục sau.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    # Nguồn mic: host trống (mặc định) thì không nối gì, thực thể assist_satellite unavailable.
    modo = wake_mode(entry)
    # Từ đánh thức trên loa: mic chỉ nối khi có phiên (on_demand). Chế độ ``ha``: nối liên tục.
    coordinator.mic = R1Mic(mic_host_hieu_luc(entry), mic_address(entry)[1], on_demand=modo == WAKE_SPEAKER)
    coordinator.mic.set_dsp(noise_settings(entry), agc_settings(entry), limiter_settings(entry))
    # Đầu nhận mic NV244: APK trên loa nối VÀO HA (mic.py là chiều ngược). Chỉ mở khi đã
    # đặt khoá + IP loa; start() không ném lỗi ra ngoài.
    listen_port, listen_key = mic_listen(entry)
    coordinator.mic_server = R1MicServer(
        coordinator.mic, listen_port, listen_key, mic_host_hieu_luc(entry))
    def _dong_cua_ghep() -> None:
        # APK đã chứng minh biết khoá: khoá không còn cần trao nữa, đóng cửa ghép (app khác trên loa không xin được).
        if entry.data.get(CONF_MIC_CHUA_GHEP):
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MIC_CHUA_GHEP: False})

    def _mo_cua_ghep() -> None:
        # APK gửi khoá sai = nó đã mất khoá (xoá/thêm lại tích hợp, cài lại APK): mở lại cửa ghép để nó tự xin khoá
        # (chỉ với khoá do HA sinh; khoá người dùng tự đặt không có cờ nên không bao giờ mở).
        if entry.data.get(CONF_MIC_CHUA_GHEP) is False:
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MIC_CHUA_GHEP: True})

    coordinator.mic_server.khi_xac_thuc = _dong_cua_ghep
    coordinator.mic_server.khi_sai_khoa = _mo_cua_ghep
    await coordinator.mic_server.start()
    coordinator.playback = R1Playback(*play_address(entry), via=coordinator.mic_server)
    coordinator.dmr = R1Dmr(hass, speaker_host(entry))

    async def _lam_moi_loa() -> None:
        if coordinator.lam_moi_loa is not None:
            await coordinator.lam_moi_loa()

    coordinator.music = MusicKeeper(
        hass, lambda: er.async_get(hass).async_get_entity_id("media_player", DOMAIN, f"{entry.entry_id}_speaker"),
        refresh=_lam_moi_loa)
    coordinator.talk = R1Talk(hass, coordinator.mic, coordinator.music, modo)
    coordinator.intercom = R1Intercom(hass, coordinator.playback, coordinator.mic,
                                      TalkSettings.from_entry(entry))
    # Đàm thoại SONG CÔNG (NV246): phiên riêng, dùng chung mic/playback/talk; Assist không đụng.
    coordinator.duplex = R1Duplex(hass, coordinator.talk, coordinator.mic,
                                  coordinator.playback, DuplexSettings.from_entry(entry))
    # Có khoá đầu nhận: APK loa tự nối VÀO HA, nên KHÔNG chạy vòng nối ra (cổng 8765 cũ trên loa không
    # còn ai nghe: cứ 2 giây một lượt nối hỏng và một dòng cảnh báo trong log).
    if not listen_key:
        entry.async_create_background_task(hass, coordinator.mic.run(), "r1_speaker mic")
    # Đèn: hiệu ứng chạy trên loa qua ADB (adb-server nếu có, không thì nối thẳng); xem den_adb.py.
    adb_server, adb_mode = adb_settings(entry)
    adb_dev = AdbDevice(speaker_host(entry), ADB_PORT, adb_server, adb_mode)
    # Đèn: ADB (hiệu ứng tự do) hoặc APK (hiệu ứng firmware, không cần ADB) theo chế độ «đóng ADB» người dùng chọn; ADB lỗi thì APK dự phòng.
    sink = LightsRouter(AdbLights(adb_dev), ApkLights(coordinator.mic_server), lambda: adb_tu_dong_dong(entry))
    # Bộ cài ứng dụng dùng CHUNG AdbDevice với đèn (adbd của loa chỉ nhận một kết nối: dùng chung kết nối đã mở).
    def _cau_hinh_apk():
        cong, khoa = mic_listen(entry)
        return (lenh_apk._host_ha(hass, entry), cong, khoa) if khoa else None
    coordinator.apps = BoCai(adb_dev, danh_sach=await hass.async_add_executor_job(cai_ung_dung.doc_bo_cai),
                             cau_hinh_bodam=_cau_hinh_apk)
    # APK cài NGOÀI tích hợp (máy tính, adb tay) chưa biết HA ở đâu: HA tự cấu hình khi thấy APK đã cài mà chưa nối về.
    coordinator.tu_ket_noi = TuKetNoi(coordinator.apps, coordinator.mic_server)
    entry.async_create_background_task(hass, coordinator.tu_ket_noi.chay(), "r1_speaker tự kết nối APK")
    # Phím trên loa: cử chỉ (firmware nhận diện hoặc HA nhận diện từ phím thô) → hành động người dùng chọn + sự kiện event.r1_phim.
    coordinator.phim = Phim(hass, entry, coordinator, lambda: phim_ma(entry))
    for go in coordinator.phim.noi(coordinator.mic_server):
        entry.async_on_unload(go)

    async def _bao_cau_hinh_phim() -> None:
        await coordinator.mic_server.gui_phim_cau_hinh(sorted(phim_ma(entry)), False)
    coordinator.mic_server.khi_ket_noi = _bao_cau_hinh_phim            # APK nối vào thì báo mã phím do HA xử lý
    # Chế độ «đóng ADB» (người dùng chọn ở tuỳ chọn): chỉ đóng khi APK đã nối ổn định; đọc tuỳ chọn mỗi nhịp nên bật/tắt có hiệu lực ngay.
    entry.async_create_background_task(
        hass, TuDongDongAdb(adb_dev, coordinator.mic_server, lambda: adb_tu_dong_dong(entry)).chay(), "r1_speaker tự đóng ADB")
    # Đèn ưu tiên số 1, đọc thông tin số 2; số liệu ưu tiên do APK báo (chạy cả khi đóng ADB), ADB dự phòng.
    coordinator.he_thong = HeThongLoa(hass, entry, adb_dev, sink, coordinator.mic_server, lambda: adb_tu_dong_dong(entry))
    coordinator.lights = R1Lights(hass, entry, sink=sink)
    sink.khi_roi = coordinator.lights.ap_dung_lai        # phiên đèn đứt (loa khởi động lại, ADB rớt) thì áp lại
    await coordinator.lights.async_load()
    # Báo thức / nhắc nhở / hẹn giờ tắt nhạc chạy bằng HA (không cần đám mây của hãng); lưu qua khởi động lại.
    coordinator.bao_thuc = BaoThuc(hass, entry, coordinator)
    await coordinator.bao_thuc.async_load()
    entry.async_on_unload(coordinator.bao_thuc.huy)
    _don_thuc_the_cu(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.lights.start()
    # Loa nối lại vào HA (vừa khởi động lại) → áp lại đèn hiện tại.
    entry.async_on_unload(coordinator.mic_server.add_state_listener(coordinator.lights.ap_dung_lai))
    return True


async def async_remove_entry(hass: HomeAssistant, entry: R1ConfigEntry) -> None:
    """Xoá mục: nhả cổng nghe mic nếu máy chủ của mục còn giữ (mục xoá lúc «chưa nạp» thì HA không dỡ tải)."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None and getattr(coordinator, "mic_server", None) is not None:
        await coordinator.mic_server.async_close()


async def async_unload_entry(hass: HomeAssistant, entry: R1ConfigEntry) -> bool:
    coordinator = entry.runtime_data
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await coordinator.lights.async_close()
        await coordinator.mic_server.async_close()
        await coordinator.duplex.async_close()
        await coordinator.intercom.async_close()
        await coordinator.talk.async_close()
    return ok
