"""Bộ đàm nửa công cho loa R1, theo khuôn ``dahua_talk/intercom.py`` (bộ đàm camera Imou).

Hai chiều, luân phiên (không song công):

* **Người nói → loa**: thẻ WebRTC Camera (mic điện thoại) → go2rtc → lệnh ``exec`` (ffmpeg)
  POST A-law 8 kHz vào ``IntercomView`` → ``Gate`` chỉ MỞ khi có tiếng người → nâng lên PCM16
  16 kHz → ``R1Playback`` (kênh phát về loa; PHÍA LOA CHƯA CÓ, xem playback.py).
* **Loa → người nghe**: ``MicView`` đẩy luồng mic của loa (``R1Mic``) ra HTTP cho go2rtc.

Nửa công: suốt lúc cổng mở, ``R1Mic.hold()`` BỎ tiếng mic (không phát cho Assist lẫn
``MicView``), khỏi để loa tự nghe tiếng mình; sau khi im đủ ``silence_s`` cổng đóng, chờ thêm
``tail_s`` cho tiếng loa tắt hẳn rồi mới nhả mic. Cả bốn số (ngưỡng, im, giữ đầu câu, đuôi) là
THAM SỐ cấu hình, mặc định mượn từ bộ đàm camera và CHƯA ĐO trên loa R1.

go2rtc không gửi được header ``Authorization`` từ lệnh exec nên khoá ngẫu nhiên riêng từng loa
nằm trong URL (``?k=``); khoá chỉ dùng được cho đúng loa ấy.
"""

from __future__ import annotations

import array
import asyncio
import logging
import math
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, INTERCOM_RATE, MIC_QUEUE_CHUNKS, MIC_RATE, PLAY_QUEUE_CHUNKS
from .hang_doi import day_bo_cu_nhat
from .cong_vao import tu_choi_401, xac_thuc
from .dam_thoai import R1SessionBusy
from .mic import R1Mic
from .playback import R1Playback, R1PlayError
from .settings import TalkSettings

_LOGGER = logging.getLogger(__name__)

#: Cờ bắt buộc cho ffmpeg đọc ống dẫn theo luồng (đo 24/09/2026 ở bộ đàm camera: thiếu chúng
#: thì ffmpeg gom tiếng để dò định dạng, 2,5 giây vào mà 0 byte ra).
_FFMPEG_TRUC_TIEP = "-probesize 32 -analyzeduration 0 -fflags nobuffer"


def _bang_alaw() -> list[int]:
    """G.711 A-law → PCM16 (bản mẫu ITU ``alaw2linear``)."""
    bang = []
    for a in range(256):
        a ^= 0x55
        t = (a & 0x0F) << 4
        seg = (a & 0x70) >> 4
        t = t + 8 if seg == 0 else (t + 0x108) << (seg - 1)
        bang.append(t if a & 0x80 else -t)
    return bang


_ALAW = _bang_alaw()


def alaw_to_pcm(b: bytes) -> bytes:
    return array.array("h", (_ALAW[x] for x in b)).tobytes()


def upsample2x(pcm: bytes) -> bytes:
    """PCM16 mono 8 kHz → 16 kHz: chèn trung bình hai mẫu liền kề (mẫu cuối lặp lại). Đủ cho
    giọng nói; mỗi khúc xử lý riêng nên ranh giới khúc có thể lệch một mẫu."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    out = array.array("h")
    n = len(a)
    for i, s in enumerate(a):
        out.append(s)
        out.append((s + a[i + 1]) // 2 if i + 1 < n else s)
    return out.tobytes()


def level_db(pcm: bytes) -> float:
    """RMS của khúc PCM16 theo dBFS; khúc rỗng / toàn 0 → -120."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    if not a:
        return -120.0
    tong = sum(x * x for x in a)
    return 10 * math.log10(tong / len(a) / 32768.0 ** 2) if tong else -120.0


@dataclass(frozen=True)
class GateStep:
    opened: bool = False      # khúc này vừa mở cổng
    closed: bool = False      # khúc này vừa đóng cổng
    audio: bytes = b""        # tiếng cần phát ra loa (kèm phần giữ đầu câu khi vừa mở)


class Gate:
    """Cổng thoại: mở khi có tiếng người, đóng sau một quãng im. Thuần tính toán, không I/O.

    ``feed`` nhận một khúc PCM16 mono ở ``rate`` Hz. Đóng cổng xảy ra ở khúc làm tổng thời
    gian im liên tiếp đạt ``silence_s`` (khúc ấy vẫn được phát). Khi cổng đóng, tiếng yên được
    giữ lại tối đa ``preroll_s`` giây để đưa kèm khi cổng mở (không mất âm đầu câu)."""

    def __init__(self, rate: int, settings: TalkSettings) -> None:
        self.rate = rate
        self.s = settings
        self.is_open = False
        self._dem = b""
        self._im = 0.0

    def reset(self) -> None:
        self.is_open = False
        self._dem, self._im = b"", 0.0

    def feed(self, pcm: bytes) -> GateStep:
        pcm = pcm[: len(pcm) // 2 * 2]
        if not pcm:
            return GateStep()
        co_tieng = level_db(pcm) > self.s.threshold_db
        self._im = 0.0 if co_tieng else self._im + len(pcm) / (2 * self.rate)
        if not self.is_open:
            if not co_tieng:
                giu = int(self.s.preroll_s * self.rate) * 2
                self._dem = (self._dem + pcm)[-giu:] if giu > 0 else b""
                return GateStep()
            self.is_open = True
            audio, self._dem = self._dem + pcm, b""
            return GateStep(opened=True, audio=audio)
        if self._im >= self.s.silence_s:
            self.reset()
            return GateStep(closed=True, audio=pcm)
        return GateStep(audio=pcm)


class R1Intercom:
    """Một loa, một bộ đàm: ``feed`` nhận PCM16 ở ``INTERCOM_RATE``; mở/đóng kênh phát về
    loa theo ``Gate`` và giữ/nhả mic cho đúng nửa công."""

    def __init__(self, hass: HomeAssistant, playback: R1Playback, mic: R1Mic,
                 settings: TalkSettings) -> None:
        self.hass, self.playback, self.mic, self.settings = hass, playback, mic, settings
        self.seconds = 0.0                 # tổng số giây đã phát ra loa
        self.busy = False                  # có một phiên POST đang nối
        self._gate = Gate(INTERCOM_RATE, settings)
        self._hang: asyncio.Queue[bytes | None] | None = None
        self._viec: set[asyncio.Task] = set()

    @property
    def talking(self) -> bool:
        return self._hang is not None

    async def _nguon(self, hang: asyncio.Queue) -> AsyncIterator[bytes]:
        while (khuc := await hang.get()) is not None:
            yield upsample2x(khuc)

    async def _phat(self, hang: asyncio.Queue, nha_mic: Callable[[], None]) -> None:
        try:
            self.seconds += await self.playback.async_play(self._nguon(hang))
        except R1PlayError as exc:
            _LOGGER.debug("intercom: phát về loa lỗi: %s", exc)
        except Exception:  # noqa: BLE001 — một lượt hỏng không được giết cả phiên bộ đàm
            _LOGGER.exception("intercom: lỗi không ngờ khi phát về loa")
        finally:
            # Phát hỏng / xong: ngừng nhận thêm vào hàng này (cổng có thể còn mở, tiếng bị bỏ
            # tới khi cổng đóng), rút cạn phần còn lại để bộ nhớ không phình.
            if self._hang is hang:
                self._hang = None
            while not hang.empty():
                hang.get_nowait()
            # Tiếng loa còn vang: chờ rồi mới mở mic (mở lại sau im lặng đủ lâu).
            await asyncio.sleep(self.settings.tail_s)
            nha_mic()

    def feed(self, pcm: bytes) -> None:
        """Nhận một khúc PCM16 mono ở ``INTERCOM_RATE``."""
        step = self._gate.feed(pcm)
        if step.opened:
            self._hang = asyncio.Queue(maxsize=PLAY_QUEUE_CHUNKS)
            nha_mic = self.mic.hold()
            # Tác vụ NỀN (không để async_block_till_done / khởi động HA chờ cả cuộc nói).
            self._viec.add(t := self.hass.async_create_background_task(
                self._phat(self._hang, nha_mic), "r1_speaker intercom play"))
            t.add_done_callback(self._viec.discard)
        if step.audio and self._hang is not None:
            day_bo_cu_nhat(self._hang, step.audio)
        if step.closed:
            self.stop_talking()

    def stop_talking(self) -> None:
        """Đóng kênh phát (mic nhả sau ``tail_s``). Có tiếng tiếp thì mở lại."""
        if self._hang is not None:
            day_bo_cu_nhat(self._hang, None)
            self._hang = None
        self._gate.reset()

    async def async_close(self) -> None:
        self.stop_talking()
        if self._viec:
            await asyncio.gather(*self._viec, return_exceptions=True)


def _runtime(hass: HomeAssistant, entry_id: str, key: str):
    """(entry, coordinator) nếu khoá đúng, ngược lại None (khoá sai được ghi nhận + báo một lần,
    xem ``cong_vao.xac_thuc``)."""
    return xac_thuc(hass, entry_id, key)


class IntercomView(HomeAssistantView):
    """go2rtc POST luồng A-law 8 kHz vào đây (khoá riêng từng loa trong URL)."""

    url = "/api/r1_speaker/intercom/{entry_id}"
    name = "api:r1_speaker:intercom"
    requires_auth = False

    async def post(self, request: web.Request, entry_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        found = _runtime(hass, entry_id, request.query.get("k", ""))
        if found is None:
            return tu_choi_401()
        entry, coordinator = found
        phien: R1Intercom = coordinator.intercom
        if not phien.playback.configured:
            return web.Response(status=503, text="no playback channel configured")
        if phien.busy:
            return web.Response(status=409, text="intercom already in use")
        try:
            # Một phiên một lúc: đang có phiên đàm thoại Assist thì bộ đàm cũng bị từ chối rõ.
            nha_cho = coordinator.talk.claim("bo_dam")
        except R1SessionBusy as exc:
            return web.Response(status=409, text=str(exc))
        phien.busy = True
        _LOGGER.debug("intercom %s: open", entry.title)
        try:
            while khuc := await request.content.readany():
                phien.feed(alaw_to_pcm(khuc))
        finally:
            await phien.async_close()
            phien.busy = False
            nha_cho()
            _LOGGER.debug("intercom %s: closed, %.1f s played", entry.title, phien.seconds)
        return web.json_response({"seconds": round(phien.seconds, 1)})


#: Cứ ngần này giây không có khúc mic (đang nửa công / luồng chậm) thì ghi một khúc im để
#: bên nghe không đứng luồng và để phát hiện bên nghe đã đóng.
_MIC_IM_SAU = 1.0


class MicView(HomeAssistantView):
    """Luồng mic của loa dạng PCM16 mono 16 kHz thô cho go2rtc (chiều loa → người nghe)."""

    url = "/api/r1_speaker/mic/{entry_id}"
    name = "api:r1_speaker:mic"
    requires_auth = False

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        found = _runtime(hass, entry_id, request.query.get("k", ""))
        if found is None:
            return tu_choi_401()
        _entry, coordinator = found
        mic: R1Mic = coordinator.mic
        if not mic.available or mic.muted:
            return web.Response(status=503, text="microphone not available")
        # Phiên song công (NV246) đang mở: phía điện thoại chỉ nghe TIẾNG NGƯỜI đã qua VAD
        # của phiên đó, không nghe luồng mic thô. Không có phiên → hành vi cũ nguyên vẹn.
        duplex = getattr(coordinator, "duplex", None)
        loc_vad = duplex if duplex is not None and duplex.active else None
        hang: asyncio.Queue[bytes] = asyncio.Queue(maxsize=MIC_QUEUE_CHUNKS)

        def nhan(khuc: bytes) -> None:
            if hang.full():
                hang.get_nowait()
            hang.put_nowait(khuc)

        resp = web.StreamResponse(headers={
            "Content-Type": f"audio/L16;rate={MIC_RATE};channels=1", "Cache-Control": "no-store"})
        await resp.prepare(request)
        huy = (loc_vad.add_audio_listener(nhan) if loc_vad is not None
               else mic.add_chunk_listener(nhan))
        try:
            while mic.available and not mic.muted and (loc_vad is None or loc_vad.active):
                try:
                    khuc = await asyncio.wait_for(hang.get(), _MIC_IM_SAU)
                except TimeoutError:
                    khuc = bytes(int(MIC_RATE * 0.1) * 2)
                await resp.write(khuc)
        except ConnectionResetError:
            pass                       # bên nghe đã đóng
        finally:
            huy()
        return resp


def go2rtc_source(base_url: str, entry_id: str, key: str) -> dict[str, str]:
    """Hai dòng nguồn cho go2rtc.yaml.

    ``talk``: giống hệt dòng đã chạy thật ở bộ đàm camera (A-law 8 kHz, ba cờ không-đệm).
    ``listen``: CHƯA thử với go2rtc thật; ffmpeg đọc PCM thô từ ``MicView``.
    URL không được chứa dấu cách hay '#' (khoá là token_urlsafe, không có)."""
    goc = base_url.strip().rstrip("/")
    talk_url = f"{goc}/api/{DOMAIN}/intercom/{entry_id}?k={key}"
    mic_url = f"{goc}/api/{DOMAIN}/mic/{entry_id}?k={key}"
    return {
        "talk": (f"exec:ffmpeg -hide_banner -loglevel error {_FFMPEG_TRUC_TIEP} "
                 f"-f alaw -ar {INTERCOM_RATE} -ac 1 -i - -c:a copy -f alaw -flush_packets 1 "
                 f"-method POST {talk_url}#backchannel=1#audio=alaw/{INTERCOM_RATE}"),
        "listen": (f"exec:ffmpeg -hide_banner -loglevel error -f s16le -ar {MIC_RATE} -ac 1 "
                   f"-i {mic_url} -c:a libopus -f rtsp {{output}}"),
    }


def wake_endpoint(base_url: str, entry_id: str, key: str) -> dict[str, str]:
    """Địa chỉ mà dịch vụ từ đánh thức TRÊN LOA sẽ POST tới. **PHÍA LOA CHƯA CÓ (CHỜ)** — trả
    sẵn để cấu hình khi có. Thân JSON ``{"event": "wake", "word": "<từ>"}`` hoặc nhịp tim
    ``{"event": "alive"}``; mã trả lời xem ``cong_vao.WakeView``."""
    goc = base_url.strip().rstrip("/")
    return {"url": f"{goc}/api/{DOMAIN}/wake/{entry_id}?k={key}", "method": "POST",
            "trang_thai": "CHO_PHIA_LOA"}
