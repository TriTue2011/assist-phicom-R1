"""Sink đèn thật: lệnh đèn của HA đi qua kết nối mic đã xác thực tới APK trên loa, APK gọi hiệu ứng CÓ SẴN của firmware
(``msgcenter.sendMsg(0x1000, ID, 0)``) — cách app AI box làm, KHÔNG cần máy chủ quyền shell hay máy ngoài.
Firmware chỉ chạy MỘT hiệu ứng tại một thời điểm: đèn đáy và đèn viền KHÔNG sáng đồng thời (xem ``_ap``).

``available`` = APK đang nối VÀ APK báo ``che_do = firmware`` với ``san_sang`` (lấy được dịch vụ msgcenter). APK bản cũ
(đèn qua máy chủ shell) không báo ``che_do`` nên coi là chưa sẵn sàng thay vì gửi vào hư không."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Sequence

from . import den_firmware as fw
from .den_port import RGB, LightsError, Step, run_steps


class ApkLights:
    name = "apk_firmware"
    firmware = True
    #: Hiệu ứng firmware tự chạy bằng một ID; các hiệu ứng khác chạy bằng chuỗi ID (``play_effect``).
    hieu_ung_goc = fw.HIEU_UNG_GOC
    hieu_ung_ho_tro = None            # None = mọi hiệu ứng của tích hợp (màu làm tròn về bảng của firmware)

    def __init__(self, mic_server) -> None:
        self._server = mic_server
        self._task: asyncio.Task | None = None
        #: Đáy / viền đang MUỐN (ID hiệu ứng). Firmware chỉ giữ MỘT hiệu ứng chạy cùng lúc, nên hai ô này chung một lần gửi.
        self._day = fw.DAY_TAT
        self._rim = fw.RIM_TAT
        self._cuoi: int | None = None           # ID đã gửi gần nhất (tránh dội lệnh thừa)

    @property
    def available(self) -> bool:
        return bool(self._server.receiving and self._server.den_san_sang)

    @property
    def ly_do(self) -> str:
        """Vì sao chưa sáng: loa chưa nối (``mat_ket_noi``) hay APK chưa hỗ trợ đèn firmware (``CHO_DICH_VU_DEN``)."""
        return "CHO_DICH_VU_DEN" if self._server.receiving else "mat_ket_noi"

    async def _gui(self, coro) -> None:
        try:
            await coro
        except (ConnectionError, OSError, TimeoutError) as exc:
            raise LightsError(f"loa chưa nối về HA: {exc}") from exc

    async def _ap(self, day: int, rim: int, *, ep: bool = False) -> None:
        """Áp đèn bằng ĐÚNG MỘT ID. ``LightsEffectService`` của firmware chỉ giữ một hiệu ứng đang chạy: bật cái mới là
        đóng cái cũ (log ``close light X`` / ``show light Y``). Gửi đáy rồi gửi ngay ID tắt viền 505 sẽ đóng luôn hiệu ứng
        đáy vừa bật — lỗi «đèn đáy không sáng, viền thì sáng» (22/10/2026). Nên: đáy đang sáng thì ưu tiên đáy; không thì
        viền; không thì tắt cả hai (504 rồi 505)."""
        self._day, self._rim = day, rim
        if day != fw.DAY_TAT:
            ids = (day,)
        elif rim != fw.RIM_TAT:
            ids = (rim,)
        else:
            ids = (fw.DAY_TAT, fw.RIM_TAT)
        if not ep and self._cuoi == ids[-1]:
            return
        for i in ids:
            await self._gui(self._server.gui_hieu_ung(i))
        self._cuoi = ids[-1]

    async def ap_dung_ham(self, *, rim: bool, color: RGB, effect: str, sang: float) -> None:
        """Áp MỘT chức năng đèn bằng hiệu ứng gốc: màu đáy (sáng cố định/thở/nháy) nếu có, không thì viền trắng."""
        if effect == "chay_duoi":                       # viền chạy đuổi: một ID firmware, không đáy
            await self._ap(fw.DAY_TAT, fw.id_chay_duoi(rim, sang), ep=True)
            return
        if effect.startswith("vien_"):                 # 24 chế độ viền: đúng ID firmware của chế độ
            await self._ap(fw.DAY_TAT, fw.id_vien_fw(effect, rim, sang), ep=True)
            return
        await self._ap(fw.id_day(color, effect, sang), fw.id_vien(rim, sang), ep=True)

    async def tat(self) -> None:
        await self._ap(fw.DAY_TAT, fw.RIM_TAT, ep=True)

    # Giao diện LightsSink gốc: viền theo mức trắng, đáy theo RGB (làm tròn về màu gần nhất của firmware).
    async def set_rim(self, level: int) -> None:
        await self._ap(self._day, fw.id_vien(level > 0, level))

    async def set_base(self, rgb: RGB) -> None:
        await self._ap(fw.id_day(rgb, "none", 100 if max(rgb) else 0), self._rim)

    async def play_effect(self, steps: Sequence[Step], *, repeat: bool) -> None:
        await self.stop_effect()
        self._task = asyncio.get_running_loop().create_task(self._chay(steps, repeat))

    async def _chay(self, steps: Sequence[Step], repeat: bool) -> None:
        try:
            await run_steps(self, steps, repeat=repeat)
        except LightsError:
            pass                                # mất kết nối giữa hiệu ứng: dừng, lần áp sau sẽ chạy lại

    async def stop_effect(self) -> None:
        t, self._task = self._task, None
        if t is not None and not t.done():
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
