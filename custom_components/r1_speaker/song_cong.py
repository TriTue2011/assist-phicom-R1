"""Đàm thoại SONG CÔNG kích hoạt từ HA (NV246): mic mở liên tục + loa phát đồng thời,
mic về phía điện thoại chỉ còn TIẾNG NGƯỜI (lọc bằng VAD).

Khác bộ đàm nửa công (``intercom.py``): bên kia đang phát xuống loa thì mic KHÔNG bị giữ —
hai bên nói/nghe cùng lúc. Chấp nhận vọng nhẹ theo yêu cầu của chủ máy (loa R1 không có mạch
khử tiếng vọng); chỉ có cắt vọng TUỲ CHỌN (mặc định TẮT): HA đang phát mà khung mic nhỏ hơn
ngưỡng cấu hình thì bỏ.

* **Mở phiên từ HA**: dịch vụ ``r1_speaker.start_duplex`` / ``stop_duplex`` hoặc POST vào
  ``DuplexView`` (điện thoại). Phiên chiếm chỗ qua ``R1Talk.claim("song_cong")`` — Assist
  (giữ nguyên, không đụng) và bộ đàm đang bận thì phiên song công bị từ chối rõ, và ngược lại.
* **Mic liên tục**: phiên đăng ký ``R1Mic.add_chunk_listener`` suốt phiên (tiếng về từ đường
  client ``mic.py`` hoặc đầu nhận NV244 — cùng một chuỗi listener). KHÔNG có ngưỡng im lặng
  tự đóng: phiên chỉ đóng khi HA kết thúc, mất kết nối mic/kênh phát, hoặc quá
  ``duplex_max_s`` (mặc định 30 phút, CHƯA ĐO).
* **Lọc tiếng người**: ``VadGate`` chạy microVAD (``pymicro_vad.MicroVad`` — đúng bộ VAD
  Assist của HA dùng trong ``assist_pipeline.audio_enhancer``) theo khung 10 ms; chỉ khung
  được đánh là tiếng người mới chuyển cho phía điện thoại (``add_audio_listener``;
  ``MicView`` tự chuyển sang luồng đã lọc khi phiên đang mở), kèm đệm trước/sau để không
  cắt đầu/cuối câu. Tiếng nền/sự kiện không có giọng không qua.
* **HA → loa**: ``feed_playback`` bơm PCM16 16 kHz mono vào ``R1Playback`` LIÊN TỤC (không
  cổng thoại, không chờ hết khúc).
* **Trạng thái**: thuộc tính ``song_cong*`` trên ``sensor.r1_trang_thai_mic`` (phiên mở /
  đang nghe / đang phát / số khung vào-chuyển-bỏ) + sự kiện ``r1_speaker_duplex``; thẻ đàm
  thoại sẵn có đọc chính các thuộc tính này nên đèn đàm thoại hiện khi phiên mở.

Mất kết nối giữa chừng (mic đứt sau khi đã nối, kênh phát lỗi): phiên đóng sạch, mở lại
được, không treo, không sập HA.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncIterator, Callable

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from . import const
from .hang_doi import day_bo_cu_nhat
from .cong_vao import tu_choi_401, xac_thuc
from .dam_thoai import R1SessionBusy, R1Talk
from .intercom import level_db
from .mic import R1Mic
from .playback import R1PlayError, R1Playback
from .khu_vong import KhuVong

#: Khử vọng cho đàm thoại song công (mặc định BẬT). Trễ loa→mic CHƯA ĐO trên R1.
AEC_BAT = True
AEC_DO_TRE_MS = 300
from .settings import DuplexSettings

_LOGGER = logging.getLogger(__name__)

#: microVAD xử lý từng 10 ms: 160 mẫu PCM16 mono 16 kHz = 320 byte/khung.
VAD_FRAME = 320
#: Sau khi HA ngừng bơm tiếng xuống loa ngần này giây thì hết coi là «đang phát» cho khâu
#: cắt vọng (tiếng loa còn vang một lúc sau khúc cuối).
DUCK_GRACE_S = 0.5
#: «Quyền nói» của điện thoại (VOX): khúc từ điện thoại có mức tiếng ≥ ngưỡng này là ĐANG NÓI; im quá
#: ``PHONE_HANG_S`` thì quyền nói trả về loa. Mức mặc định CHƯA ĐO trên mic điện thoại thật.
PHONE_VOX_DB = -42.0
PHONE_HANG_S = 0.8


def _vad_that():
    """microVAD thật của HA (nạp lười: chỉ cần khi mở cổng lọc)."""
    from pymicro_vad import MicroVad

    return MicroVad()


class VadGate:
    """Cổng lọc tiếng người bằng VAD cho luồng mic. Thuần luồng byte + một đối tượng VAD
    (tiêm được để test); VAD chạy theo khung 10 ms như Assist.

    ``feed`` nhận khúc PCM16 mono 16 kHz bất kỳ độ dài, trả danh sách khung 10 ms được
    chuyển tiếp: khung tiếng người (xác suất >= ``vad_threshold``), kèm tối đa
    ``preroll_s`` giây khung ngay trước nó và ``hangover_s`` giây khung ngay sau nó.
    Khung còn lại bị bỏ tại đây."""

    def __init__(self, settings: DuplexSettings, vad=None) -> None:
        self.s = settings
        #: Ngưỡng 0 = không lọc: chuyển mọi khung, KHÔNG nạp và không gọi VAD (đỡ CPU trong vòng lặp sự kiện của HA).
        self._loc = settings.vad_threshold > 0
        self._vad = (vad if vad is not None else _vad_that()) if self._loc else None
        self._du = b""                       # phần dư chưa đủ một khung 10 ms
        self._dem: deque[bytes] = deque()    # đệm trước: các khung chưa phải tiếng người
        self._dem_toi_da = max(0, round(settings.preroll_s * 100))
        self._duoi_toi_da = max(0, round(settings.hangover_s * 100))
        self._duoi = 0                       # số khung đệm sau còn lại
        self.seen = 0                        # tổng khung 10 ms đã xét
        self.passed = 0                      # tổng khung 10 ms đã chuyển

    def reset(self) -> None:
        self._du, self._dem, self._duoi = b"", deque(), 0
        self.seen = self.passed = 0
        reset = getattr(self._vad, "reset", None)
        if reset is not None and self._vad is not None:
            reset()

    def _la_tieng_nguoi(self, khung: bytes) -> bool:
        fn = getattr(self._vad, "process_10ms", None) or self._vad.Process10ms
        return float(fn(khung)) >= self.s.vad_threshold

    def feed(self, pcm: bytes) -> list[bytes]:
        ra: list[bytes] = []
        buf = self._du + pcm
        n = len(buf) // VAD_FRAME * VAD_FRAME
        self._du = buf[n:]
        for i in range(0, n, VAD_FRAME):
            khung = buf[i:i + VAD_FRAME]
            self.seen += 1
            if not self._loc:
                self.passed += 1
                ra.append(khung)
            elif self._la_tieng_nguoi(khung):
                self.passed += len(self._dem) + 1
                ra.extend(self._dem)
                self._dem.clear()
                ra.append(khung)
                self._duoi = self._duoi_toi_da
            elif self._duoi > 0:
                ra.append(khung)
                self.passed += 1
                self._duoi -= 1
            else:
                self._dem.append(khung)
                while len(self._dem) > self._dem_toi_da:
                    self._dem.popleft()
        return ra


class R1Duplex:
    """Một phiên song công của một loa. Vòng đời: ``async_start()`` → ``end(ly_do)``;
    ``async_close()`` khi tắt tích hợp."""

    def __init__(self, hass: HomeAssistant, talk: R1Talk, mic: R1Mic, playback: R1Playback,
                 settings: DuplexSettings, vad_factory: Callable | None = None) -> None:
        self.hass, self.talk, self.mic, self.playback = hass, talk, mic, playback
        self.settings = settings
        self._vad_factory = vad_factory      # None = microVAD thật; test tiêm VAD giả
        self.active = False
        self.downlink_busy = False           # đang có một POST DuplexView bơm xuống loa
        self.started_at: float | None = None
        self.last_end: str | None = None
        self.play_seconds = 0.0
        self.duck_dropped = 0                # số khung bị cắt vọng (chỉ khi tuỳ chọn bật)
        self._gate: VadGate | None = None
        self._release: Callable[[], None] | None = None
        self._unsub_mic: Callable[[], None] | None = None
        self._unsub_link: Callable[[], None] | None = None
        self._watchdog: asyncio.Task | None = None
        self._hang: asyncio.Queue[bytes | None] | None = None
        self._play_task: asyncio.Task | None = None
        self._last_play = 0.0                # lần cuối có tiếng bơm xuống loa (monotonic)
        self.ptt = False                     # điện thoại đang GIỮ nút nói (báo qua WebSocket): luôn có quyền nói
        self._phone_noi_den = 0.0            # điện thoại có tiếng (VOX) tới thời điểm này
        self._huong_da_bao = "loa"
        self._aec = None                     # khử vọng (tạo khi mở phiên)
        self.half_duplex = False             # bật = luân phiên (bỏ mic khi loa phát); tắt = song công
        self.luon = False                    # «Bật mic luôn»: giữ phiên mở, không cần giữ nút
        self._last_forward = 0.0
        self._mic_seen = False               # phiên đã thấy mic nối thật chưa (để biết «đứt»)
        self._audio: list[Callable[[bytes], None]] = []
        self._on_change: list[Callable[[], None]] = []
        self.phong = None                    # phòng đàm thoại nhiều loa đang dùng phiên này (hoi_thoai.Phong), None = không

    def dat_phong(self, phong) -> None:
        """Phòng đàm thoại nhiều loa (``hoi_thoai``) nhận/trả phiên này: báo trạng thái lên cảm biến mic."""
        self.phong = phong
        self._notify()

    # ── Người nghe ────────────────────────────────────────────────────────────

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._on_change.append(cb)
        return lambda: self._on_change.remove(cb)

    # ── Quyền nói: loa hay điện thoại ─────────────────────────────

    @property
    def phone_floor(self) -> bool:
        """Điện thoại đang giữ quyền nói: đang giữ nút, hoặc vừa có tiếng (VOX) trong ``PHONE_HANG_S`` giây."""
        return self.ptt or time.monotonic() < self._phone_noi_den

    @property
    def huong(self) -> str:
        """``song_song`` (hai bên cùng nghe), ``dien_thoai`` (nửa công: điện thoại đang nói, mic loa tạm bỏ) hoặc
        ``loa`` (nửa công, mặc định: im lặng thì quyền nói về loa)."""
        if not self.half_duplex:
            return "song_song"
        return "dien_thoai" if self.phone_floor else "loa"

    def phone_noi(self, dang_giu: bool) -> None:
        """Điện thoại báo giữ/thả nút nói (không dựa vào mức tiếng)."""
        if dang_giu == self.ptt:
            return
        self.ptt = dang_giu
        if not dang_giu:
            self._phone_noi_den = time.monotonic() + PHONE_HANG_S   # thả nút: giữ quyền thêm một nhịp cho khỏi cụt đuôi
        self._cap_nhat_huong()

    def _cap_nhat_huong(self) -> None:
        h = self.huong
        if h != self._huong_da_bao:
            self._huong_da_bao = h
            self._notify()

    @callback
    def _notify(self) -> None:
        for cb in list(self._on_change):
            try:
                cb()
            except Exception:  # noqa: BLE001 — thực thể hỏng không được phá phiên
                _LOGGER.exception("R1 duplex: listener failed")

    def add_audio_listener(self, cb: Callable[[bytes], None]) -> Callable[[], None]:
        """Đăng ký nhận khung mic ĐÃ QUA VAD (khung 10 ms, PCM16 16 kHz)."""
        self._audio.append(cb)
        return lambda: self._audio.remove(cb)

    # ── Trạng thái ────────────────────────────────────────────────────────────

    @property
    def dang_nghe(self) -> bool:
        """Phiên mở và luồng mic đang nối (tiếng đang về HA)."""
        return self.active and self.mic.connected

    @property
    def dang_phat(self) -> bool:
        """Phiên mở và bơm phát xuống loa đang chạy."""
        return self.active and self._play_task is not None

    def as_attributes(self) -> dict:
        g = self._gate
        vao = g.seen if g else 0
        chuyen = g.passed if g else 0
        return {
            "song_cong": self.active,
            "song_cong_dang_nghe": self.dang_nghe,
            "song_cong_dang_phat": self.dang_phat,
            "song_cong_khung_vao": vao,
            "song_cong_khung_chuyen": chuyen,
            "song_cong_khung_bo": max(0, vao - chuyen) + self.duck_dropped,
            "song_cong_ket_thuc_gan_nhat": self.last_end,
            "hoi_thoai": self.phong.mo_ta() if self.phong is not None else None,
        }

    # ── Mở / đóng phiên ───────────────────────────────────────────────────────

    async def async_start(self) -> None:
        """Mở phiên song công: mic mở liên tục, KHÔNG ngưỡng im lặng tự đóng."""
        if self.active:
            raise HomeAssistantError("Phiên đàm thoại song công đang mở.")
        if not self.mic.configured:
            raise HomeAssistantError(
                "Chưa cấu hình mic của loa (mic_host trong tuỳ chọn): chưa mở được phiên "
                "song công.")
        if self.mic.muted:
            raise HomeAssistantError("Mic đang tắt (switch.r1_tat_mic): bật mic rồi thử lại.")
        if not self.playback.configured:
            raise HomeAssistantError(
                "Chưa có kênh phát về loa (APK loa chưa nối về HA, hoặc chưa cấu hình play_port): "
                "chưa mở được phiên song công.")
        # Chiếm chỗ phiên NGAY (đồng bộ): Assist/bộ đàm đang bận → R1SessionBusy.
        self._release = self.talk.claim("song_cong")
        try:
            vad = self._vad_factory() if self._vad_factory is not None else None
            self._gate = VadGate(self.settings, vad)
            self._aec = KhuVong(do_tre_mau=int(AEC_DO_TRE_MS * 16)) if AEC_BAT else None
        except BaseException:
            self._release()
            self._release = None
            raise
        self.active = True
        self.started_at = time.monotonic()
        self.play_seconds = 0.0
        self.duck_dropped = 0
        self._last_play = 0.0
        self.ptt = False
        self._phone_noi_den = 0.0
        self._huong_da_bao = self.huong
        self._mic_seen = self.mic.connected
        self._unsub_mic = self.mic.add_chunk_listener(self._on_mic_chunk)
        self._unsub_link = self.mic.add_link_listener(self._on_link)
        self._watchdog = self.hass.async_create_background_task(
            self._canh_gio(), "r1_speaker duplex watchdog")
        self.hass.bus.async_fire(const.EVENT_DUPLEX, {"su_kien": "mo"})
        self._notify()
        _LOGGER.debug("song công: phiên mở (hạn %.0f giây)", self.settings.max_s)

    async def _canh_gio(self) -> None:
        """Chỉ có MỘT hạn: quá thời gian tối đa thì đóng. Không đóng theo im lặng."""
        try:
            await asyncio.sleep(self.settings.max_s)
        except asyncio.CancelledError:
            raise
        if self.active:
            _LOGGER.warning("song công: quá %.0f giây — đóng phiên", self.settings.max_s)
            self.end("het_gio")

    @callback
    def end(self, reason: str) -> None:
        """Đóng phiên sạch (gọi lại không sao). Bơm phát được báo kết thúc; nhạc/phiên của
        ``R1Talk`` được nhả qua chính hàm claim đã giữ."""
        if not self.active:
            return
        self.active = False
        self.luon = False                    # phiên đóng thì «giữ mở» cũng hết
        self.ptt = False
        self._aec = None
        self.last_end = reason
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None
        if self._unsub_mic is not None:
            self._unsub_mic()
            self._unsub_mic = None
        if self._unsub_link is not None:
            self._unsub_link()
            self._unsub_link = None
        if self._hang is not None:
            day_bo_cu_nhat(self._hang, None)      # bơm phát kết thúc → async_play đóng kênh
            self._hang = None
        if self._release is not None:
            self._release()
            self._release = None
        if self._gate is not None:
            self._gate.reset()
        self.hass.bus.async_fire(const.EVENT_DUPLEX, {"su_kien": "dong", "ly_do": reason})
        self._notify()

    async def async_settle(self) -> None:
        """Chờ bơm phát kết thúc hẳn (test, tắt tích hợp)."""
        if self._play_task is not None:
            await asyncio.gather(self._play_task, return_exceptions=True)

    async def async_close(self) -> None:
        self.end("tat_tich_hop")
        await self.async_settle()

    # ── Mic → điện thoại (qua VAD) ────────────────────────────────────────────

    def _on_link(self) -> None:
        """Luồng mic đứt SAU KHI đã nối trong phiên → đóng phiên sạch, mở lại được."""
        if not self.active:
            return
        if self.mic.muted:
            # Tắt mic giữa phiên: trước đây nhờ HA ngắt kết nối loa nên phiên đóng; nay kết nối được GIỮ (còn mang âm lượng, đèn) nên phải đóng
            # phiên rõ ràng, tiếng không còn tới điện thoại.
            _LOGGER.info("song công: mic bị tắt — đóng phiên")
            self.end("mic_tat")
            return
        if self.mic.connected:
            self._mic_seen = True
            self._notify()
        elif self._mic_seen:
            _LOGGER.warning("song công: luồng mic mất kết nối — đóng phiên")
            self.end("mat_ket_noi")

    def _duck_applies(self, chunk: bytes) -> bool:
        """Cắt vọng (tuỳ chọn, mặc định tắt): HA đang phát xuống loa và khúc mic nhỏ hơn
        ngưỡng → bỏ cả khúc (không cho qua VAD)."""
        if not self.settings.duck:
            return False
        if time.monotonic() - self._last_play >= DUCK_GRACE_S:
            return False
        return level_db(chunk) < self.settings.duck_db

    def _on_mic_chunk(self, chunk: bytes) -> None:
        if not self.active or self._gate is None:
            return
        self._cap_nhat_huong()
        if self.half_duplex and self.phone_floor:
            self.duck_dropped += len(chunk) // VAD_FRAME   # nửa công: điện thoại đang nói thì không gửi mic loa
            return
        if self._aec is not None:
            chunk = self._aec.xu_ly(chunk)   # trừ tiếng HA đã phát xuống loa khỏi mic
        if self._duck_applies(chunk):
            self.duck_dropped += len(chunk) // VAD_FRAME
            return
        for khung in self._gate.feed(chunk):
            self._last_forward = time.monotonic()
            for cb in list(self._audio):
                try:
                    cb(khung)
                except Exception:  # noqa: BLE001 — bên nghe hỏng không được phá phiên
                    _LOGGER.exception("R1 duplex: audio listener failed")

    # ── HA / điện thoại → loa ─────────────────────────────────────────────────

    def feed_playback(self, pcm: bytes, *, vox: bool = True) -> None:
        """Bơm một khúc PCM16 16 kHz mono xuống loa. Phát LIÊN TỤC: khúc vào hàng là bơm
        phát ghi ngay, không chờ, không cổng thoại, không giữ mic.

        ``vox=False``: tiếng KHÔNG phải của điện thoại (phòng đàm thoại nhiều loa đã trộn và lọc riêng từng nguồn): bỏ cổng VOX và không đụng tới
        «quyền nói» của điện thoại; khử vọng (tham chiếu tiếng đã phát) vẫn áp dụng."""
        if not self.active:
            raise HomeAssistantError("Chưa mở phiên song công.")
        # VOX: «bật mic luôn» trên điện thoại gửi tiếng LIÊN TỤC, kể cả im lặng. Chỉ khúc có tiếng (hoặc đang giữ nút)
        # mới xuống loa và mới giữ quyền nói; im lặng thì bỏ (không xì xào ra loa, không chặn mic loa).
        bay_gio = time.monotonic()
        if not vox:
            pass
        elif self.ptt or level_db(pcm) >= PHONE_VOX_DB:
            self._phone_noi_den = bay_gio + PHONE_HANG_S
            self._cap_nhat_huong()
        elif bay_gio >= self._phone_noi_den:
            return
        if self._hang is None:
            self._hang = asyncio.Queue(maxsize=const.PLAY_QUEUE_CHUNKS)
            self._play_task = self.hass.async_create_background_task(
                self._phat(), "r1_speaker duplex play")
        self._last_play = time.monotonic()
        if self._aec is not None:
            self._aec.day_ref(pcm)           # tham chiếu cho khử vọng
        day_bo_cu_nhat(self._hang, pcm)

    async def _nguon(self, hang: asyncio.Queue) -> AsyncIterator[bytes]:
        while (khuc := await hang.get()) is not None:
            self._last_play = time.monotonic()
            yield khuc

    async def _phat(self) -> None:
        hang = self._hang
        if hang is None:
            return
        try:
            self.play_seconds += await self.playback.async_play(self._nguon(hang))
        except R1PlayError as exc:
            _LOGGER.warning("song công: kênh phát về loa lỗi (%s) — đóng phiên", exc)
            self.end("mat_ket_noi_phat")
        except Exception:  # noqa: BLE001 — một lượt phát hỏng không được sập HA
            _LOGGER.exception("song công: lỗi không ngờ ở kênh phát")
            self.end("loi_phat")
        finally:
            if self._play_task is asyncio.current_task():
                self._play_task = None
            self._notify()


class DuplexView(HomeAssistantView):
    """Điện thoại/HA POST PCM16 16 kHz thô vào đây trong phiên song công (khoá riêng từng
    loa trong URL, như ``IntercomView``). Chưa mở phiên thì POST tự mở; POST đóng thì
    phiên đóng. Khúc vào được phát xuống loa NGAY, đồng thời mic vẫn chảy ngược lên."""

    url = "/api/r1_speaker/duplex/{entry_id}"
    name = "api:r1_speaker:duplex"
    requires_auth = False

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        found = xac_thuc(hass, entry_id, request.query.get("k", ""))
        if found is None:
            return tu_choi_401()
        _entry, coordinator = found
        duplex: R1Duplex = coordinator.duplex
        if duplex.downlink_busy:
            return web.Response(status=409, text="duplex downlink already in use")
        try:
            if not duplex.active:
                await duplex.async_start()
        except (R1SessionBusy, HomeAssistantError) as exc:
            return web.Response(status=409, text=str(exc))
        duplex.downlink_busy = True
        ly_do = "nguoi_dung_ket_thuc"
        _LOGGER.debug("duplex %s: open", _entry.title)
        try:
            while khuc := await request.content.readany():
                duplex.feed_playback(khuc)
        except ConnectionResetError:
            ly_do = "mat_ket_noi"
        finally:
            duplex.downlink_busy = False
            duplex.end(ly_do)
            await duplex.async_settle()
            _LOGGER.debug("duplex %s: closed, %.1f s played", _entry.title,
                          duplex.play_seconds)
        return web.json_response({"seconds": round(duplex.play_seconds, 1)})
