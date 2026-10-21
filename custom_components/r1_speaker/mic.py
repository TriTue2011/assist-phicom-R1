"""Nguồn mic của loa R1: đọc luồng PCM thô từ dịch vụ trên loa qua TCP, khuếch đại, phát cho
thực thể.

Hợp đồng luồng: PCM16 mono 16 kHz little-endian, loa là máy chủ TCP, ta là máy khách. Dịch vụ
phía loa CHƯA có; lớp này chỉ giả định đúng hợp đồng trên.

Lỗi (host trống, không nối được, luồng đứt, luồng đứng im) KHÔNG bao giờ ném ra ngoài: trạng
thái ``available`` thành False, ghi log cảnh báo một lần cho mỗi đợt mất, rồi tự nối lại.
Tắt mic thì ĐÓNG kết nối (không đọc byte nào), mở lại thì nối lại.

``on_demand`` (từ đánh thức chạy TRÊN LOA): không nối khi chưa ai xin. ``want()`` xin luồng
(đếm số bên xin); hết bên xin thì ĐÓNG kết nối — phía loa không có gì để gửi cho tới lúc có phiên.

Lớp này là một bản cài của ``audio_port.PcmSource``.
"""

from __future__ import annotations

import array
import asyncio
import contextlib
import logging
from collections.abc import Callable

from .agc import AgcSettings, LimiterSettings
from .chuoi_mic import MicChain
from .const import MIC_CHUNK
from .noise_suppress import NoiseSettings

_LOGGER = logging.getLogger(__name__)

#: Chờ nối tối đa ngần này giây.
CONNECT_TIMEOUT = 5.0
#: Luồng im quá ngần này giây (không đủ một khúc) thì coi như đứt.
READ_TIMEOUT = 5.0
#: Nghỉ giữa hai lần thử nối lại.
RETRY_DELAY = 2.0


def amplify(pcm: bytes, gain_db: float) -> bytes:
    """Nhân biên độ PCM16 theo ``gain_db``, chặn cứng ở ±32767 (không tràn số)."""
    if gain_db <= 0:
        return pcm
    factor = 10 ** (gain_db / 20)
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    return array.array("h", (max(-32768, min(32767, int(s * factor))) for s in a)).tobytes()


class R1Mic:
    def __init__(self, host: str, port: int, on_demand: bool = False) -> None:
        self.host = (host or "").strip()
        self.port = port
        self.on_demand = on_demand
        self.gain_db = 0.0
        #: Chuỗi xử lý sau amplify (khử tạp → AGC → hạn đỉnh). Mặc định cả ba TẮT = khúc đi
        #: nguyên như trước. Đổi thì có hiệu lực từ lần nối mic kế (mỗi luồng một chuỗi mới).
        self.noise = NoiseSettings()
        self.agc = AgcSettings()
        self.limiter = LimiterSettings()
        self.muted = False
        #: Số bên đang xin luồng chạy (chỉ có nghĩa khi ``on_demand``).
        self._wants = 0
        #: Số bên đang giữ mic (bộ đàm đang phát ra loa…): > 0 thì BỎ khúc đọc được, không
        #: phát cho ai. Luồng TCP vẫn được đọc để loa khỏi nghẽn.
        self._holds = 0
        self._connected = False
        #: Đầu nhận NV244 (``mic_server.R1MicServer``): loa nối VÀO HA. ``_inbound`` = đang
        #: có phiên nhận tiếng; ``_listening`` = cổng nghe đang mở. Hai đường (client nối ra
        #: / server nhận vào) dùng CHUNG ``_on_chunk`` — không có đường mic thứ hai.
        self._inbound = False
        self._listening = False
        self._inbound_chain: MicChain | None = None
        #: Hàm của đầu nhận để NGẮT kết nối loa khi tắt mic (không chỉ bỏ khung): tắt mic phải
        #: làm loa thôi gửi, giống đường client đóng ``_writer``.
        self._inbound_closer: Callable[[], None] | None = None
        self._warned = False
        self._writer: asyncio.StreamWriter | None = None
        self._kick = asyncio.Event()
        self._on_chunk: list[Callable[[bytes], None]] = []
        self._on_state: list[Callable[[], None]] = []
        self._on_link: list[Callable[[], None]] = []

    # ── Trạng thái ────────────────────────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return bool(self.host)

    @property
    def connected(self) -> bool:
        """Đang có luồng byte thật từ loa về HA (đường client nối ra HOẶC đầu nhận NV244)."""
        return self._connected or self._inbound

    @property
    def listening(self) -> bool:
        """Đầu nhận NV244 đang mở cổng chờ loa nối vào (chưa có tiếng)."""
        return self._listening

    @property
    def available(self) -> bool:
        """Host trống → False. Đang tắt mic thì vẫn True (chủ động không nghe, không phải lỗi).
        ``on_demand`` thì luôn True khi đã cấu hình: không nối là chủ ý, không phải lỗi."""
        return self.configured and (self.muted or self.connected or self.on_demand)

    def _should_connect(self) -> bool:
        return not self.muted and (not self.on_demand or self._wants > 0)

    def _set_connected(self, value: bool) -> None:
        if value != self._connected:
            was = self.available
            self._connected = value
            if was != self.available:
                self._notify()
            self._notify_link()

    def _notify_link(self) -> None:
        for cb in list(self._on_link):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("R1 mic: link listener failed")

    def _notify(self) -> None:
        for cb in list(self._on_state):
            try:
                cb()
            except Exception:  # noqa: BLE001 — người nghe hỏng không được giết vòng đọc
                _LOGGER.exception("R1 mic: state listener failed")

    # ── Đầu nhận NV244 (mic_server gọi) ───────────────────────────────────────

    def note_inbound(self, active: bool) -> None:
        """Đầu nhận báo phiên loa bắt đầu/kết thúc: trạng thái nối dùng chung với đường
        client, nên sensor / phiên đàm thoại thấy đúng như luồng nối ra."""
        if active == self._inbound:
            return
        was = self.available
        self._inbound = active
        if not active:
            self._inbound_chain = None
        if was != self.available:
            self._notify()
        self._notify_link()

    def set_inbound_closer(self, closer: Callable[[], None] | None) -> None:
        self._inbound_closer = closer

    def note_listening(self, listening: bool) -> None:
        if listening == self._listening:
            return
        self._listening = listening
        self._notify_link()

    def feed_inbound(self, chunk: bytes) -> None:
        """Một khung PCM từ đầu nhận: qua ĐÚNG khâu khuếch đại + DSP + phát cho listener
        như khúc đọc ở đường client (``_session``). Đang giữ mic (nửa công) hoặc mic tắt
        thì bỏ khúc, không phát cho ai."""
        if self._holds or self.muted:
            return
        if self._inbound_chain is None:
            self._inbound_chain = MicChain(self.noise, self.agc, self.limiter)
        self._inbound_chain = self._phat(chunk, self._inbound_chain)

    def _phat(self, chunk: bytes, chain: MicChain) -> MicChain:
        """Khuếch đại → DSP → phát cho mọi chunk listener. Trả chuỗi DSP đang dùng (bộ lọc
        hỏng thì thay chuỗi mới và phát khúc gốc, không đứt luồng)."""
        chunk = amplify(chunk, self.gain_db)
        if chain.active:
            try:
                chunk = chain.process(chunk)
            except Exception:  # noqa: BLE001 — bộ lọc hỏng thì phát khúc gốc, không đứt luồng
                _LOGGER.exception("R1 mic: DSP chain failed — passing raw chunk")
                chain = MicChain()
        for cb in list(self._on_chunk):
            try:
                cb(chunk)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("R1 mic: chunk listener failed")
        return chain

    def add_chunk_listener(self, cb: Callable[[bytes], None]) -> Callable[[], None]:
        self._on_chunk.append(cb)
        return lambda: self._on_chunk.remove(cb)

    def add_state_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._on_state.append(cb)
        return lambda: self._on_state.remove(cb)

    def add_link_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        """Gọi khi luồng nối/đứt hoặc trạng thái giữ mic đổi (khác ``add_state_listener``:
        cái đó chỉ báo khi ``available`` đổi)."""
        self._on_link.append(cb)
        return lambda: self._on_link.remove(cb)

    # ── Điều khiển ────────────────────────────────────────────────────────────

    @property
    def holding(self) -> bool:
        return self._holds > 0

    def hold(self) -> Callable[[], None]:
        """Nửa công: bỏ tiếng mic cho tới khi gọi hàm trả về. Gọi nhiều lần được (đếm số
        bên giữ); hàm trả về gọi lần hai không có tác dụng."""
        self._holds += 1
        released = False
        self._notify_link()

        def release() -> None:
            nonlocal released
            if not released:
                released = True
                self._holds -= 1
                self._notify_link()

        return release

    def want(self) -> Callable[[], None]:
        """Xin luồng mic chạy (đếm số bên xin). Hàm trả về nhả lời xin; hết bên xin thì với
        ``on_demand`` luồng bị ĐÓNG. Không ``on_demand`` thì chỉ đếm (luồng chạy liên tục)."""
        self._wants += 1
        released = False
        self._kick.set()

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            self._wants -= 1
            if self.on_demand and self._wants == 0 and self._writer is not None:
                self._writer.close()       # ngắt luồng: loa không còn gì để gửi
            self._kick.set()

        return release

    def set_gain(self, db: float) -> None:
        self.gain_db = float(db)

    def set_dsp(self, noise: NoiseSettings | None = None, agc: AgcSettings | None = None,
                limiter: LimiterSettings | None = None) -> None:
        """Đặt cấu hình khử tạp / AGC / hạn đỉnh (None = giữ nguyên)."""
        self.noise = noise or self.noise
        self.agc = agc or self.agc
        self.limiter = limiter or self.limiter

    def set_muted(self, muted: bool) -> None:
        if muted == self.muted:
            return
        was = self.available
        self.muted = muted
        if muted and self._writer is not None:
            self._writer.close()           # ngắt luồng: không nhận byte nào nữa
        if muted and self._inbound_closer is not None:
            self._inbound_closer()         # đầu nhận NV244: ngắt cả luồng loa nối vào
        self._kick.set()                   # đánh thức vòng đang chờ (nối lại khi bật)
        # Tắt/bật mic là sự kiện người dùng thấy (trạng thái mic, phiên đang mở) dù ``available``
        # không đổi: báo cả hai loại người nghe.
        self._notify()
        self._notify_link()

    # ── Vòng đọc ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Chạy mãi cho tới khi bị huỷ. Không ném lỗi nào khác ngoài CancelledError."""
        if not self.configured:
            _LOGGER.debug("R1 mic: no host configured — satellite stays unavailable")
            return
        while True:
            self._kick.clear()            # xoá TRƯỚC khi xét: lời xin đến sau vẫn đánh thức được
            if self._should_connect():
                try:
                    await self._session()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 — tai hỏng không được làm sập HA
                    self._lost(f"{type(exc).__name__}: {exc}")
                finally:
                    self._writer = None
                    self._set_connected(False)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._kick.wait(),
                                       RETRY_DELAY if self._should_connect() else None)

    def _lost(self, why: str) -> None:
        if not self._should_connect():
            return
        if not self._warned:
            self._warned = True
            _LOGGER.warning("R1 mic %s:%s unavailable (%s) — retrying every %.1f s",
                            self.host, self.port, why, RETRY_DELAY)
        else:
            _LOGGER.debug("R1 mic %s:%s still down (%s)", self.host, self.port, why)

    async def _session(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT)
        self._writer = writer
        chain = MicChain(self.noise, self.agc, self.limiter)
        try:
            while True:
                chunk = await asyncio.wait_for(reader.readexactly(MIC_CHUNK), READ_TIMEOUT)
                if not self._should_connect():
                    return
                if not self._connected:
                    # Chỉ coi là có luồng khi đã nhận trọn một khúc (nối được mà không có
                    # tiếng thì vẫn unavailable).
                    self._warned = False
                    _LOGGER.debug("R1 mic %s:%s streaming", self.host, self.port)
                    self._set_connected(True)
                if self._holds:
                    continue          # nửa công: luồng sống nhưng không phát cho ai
                chain = self._phat(chunk, chain)
        except asyncio.IncompleteReadError:
            self._lost("stream ended")
        except TimeoutError:
            self._lost(f"no audio for {READ_TIMEOUT:.0f} s")
        finally:
            writer.close()

