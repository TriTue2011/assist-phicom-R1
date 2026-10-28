"""Bộ trộn tiếng nhiều bên cho phòng đàm thoại (nhiều loa R1 và điện thoại): MÃ THUẦN, không HA, không asyncio, không đồng hồ.

Mọi bên đều là PCM16 16 kHz mono, chia khung 10 ms (320 byte): đúng định dạng ``PhatAm`` trên loa phát được, không đổi tốc độ lấy mẫu,
không cần đổi APK. ``Phong`` (``hoi_thoai.py``) gọi ``BoTron.buoc()`` theo nhịp thời gian thật; test gọi thẳng, không cần ngủ.

Luật nghe (mỗi bên nghe tổng của những bên khác, KHÔNG nghe lại chính mình):

* loa nghe điện thoại; loa nghe loa khác nếu ``giua_cac_loa``;
* điện thoại nghe mọi loa.

Tính theo nhóm nên tốn O(N) chứ không O(N²): tổng các loa trừ chính loa đó.

Hai chế độ khi loa nói chuyện với loa:

* ``tron`` (mặc định): ai nói cũng nghe, như nhiều người ngồi cùng bàn. Hợp khi mỗi loa một phòng (tiếng loa này không lọt vào mic loa kia).
* ``quyen_noi``: mỗi lúc chỉ MỘT loa giữ quyền nói (loa to nhất khi chưa ai giữ); loa khác bị bỏ tiếng tới khi người giữ im ``QUYEN_GIU_KHUNG``
  khung. Dùng khi hai loa đặt CHUNG một phòng, để tiếng loa này phát ra rồi lọt vào mic loa kia không thành vòng hú. CHƯA KIỂM trên loa thật
  (chủ máy chỉ có một loa).

Mic cho qua mọi khung kể cả tạp âm (ngưỡng VAD mặc định là 0), nên MỖI nguồn có cổng theo mức tiếng ``CongVox`` (đệm đầu câu, giữ đuôi)."""

from __future__ import annotations

import array
from collections import deque

from .intercom import level_db

KHUNG_BYTE = 320                      # 10 ms PCM16 mono 16 kHz
KHUNG_S = 0.01
#: Trần đệm mỗi nguồn (khung). Phải lớn hơn đệm đầu câu của VadGate (mặc định 0,3 s = 30 khung): bộ lọc đổ cả cụm đầu câu một lúc, ít hơn thì cắt mất đầu từ.
DEM_TOI_DA = 60
#: CHƯA ĐO trên mic loa thật (cùng giá trị khởi đầu với VOX của điện thoại).
NGUONG_VOX_DB = -42.0
GIU_KHUNG = 50                        # giữ đuôi 0,5 s sau tiếng cuối
TIEN_KHUNG = 20                       # đệm đầu câu 0,2 s
QUYEN_GIU_KHUNG = 50                  # loa giữ quyền im 0,5 s thì nhả

CHE_DO = ("tron", "quyen_noi")
LOA, DIEN_THOAI = "loa", "dt"


class CongVox:
    """Cổng theo mức tiếng cho MỘT nguồn: khung có mức >= ``nguong_db`` là có tiếng; trước nó đẩy kèm tối đa ``tien`` khung vừa qua, sau nó
    giữ ``giu`` khung. Khung im (và nằm ngoài hai khoảng đó) bị bỏ."""

    def __init__(self, nguong_db: float = NGUONG_VOX_DB, giu: int = GIU_KHUNG, tien: int = TIEN_KHUNG) -> None:
        self.nguong_db, self._giu_toi_da, self._tien_toi_da = nguong_db, giu, tien
        self._tien: deque[bytes] = deque(maxlen=max(tien, 1) if tien > 0 else 1)
        self._con = 0

    def feed(self, khung: bytes) -> tuple[list[bytes], bool]:
        """Trả (các khung chuyển tiếp, khung này có tiếng không)."""
        if level_db(khung) >= self.nguong_db:
            ra = list(self._tien) if self._tien_toi_da > 0 else []
            self._tien.clear()
            ra.append(khung)
            self._con = self._giu_toi_da
            return ra, True
        if self._con > 0:
            self._con -= 1
            return [khung], False
        if self._tien_toi_da > 0:
            self._tien.append(khung)
        return [], False


def _mang(khung: bytes) -> array.array:
    a = array.array("h")
    a.frombytes(khung)
    return a


def _bytes(tong: list[int]) -> bytes:
    return array.array("h", [32767 if v > 32767 else -32768 if v < -32768 else v for v in tong]).tobytes()


class _Nguon:
    __slots__ = ("loai", "du", "dem", "vox", "ptt", "tran", "bo")

    def __init__(self, loai: str, vox: CongVox | None) -> None:
        self.loai, self.vox = loai, vox
        self.du = b""
        self.dem: deque[bytes] = deque()
        self.ptt = False                   # đang GIỮ nút nói: cho qua mọi khung, không cần mức tiếng
        self.tran = 0                      # số khung cũ nhất bị bỏ vì đệm đầy
        self.bo = 0                        # số khung bị cổng mức tiếng bỏ


class BoTron:
    """Các bên trong một phòng và phép trộn từng khung 10 ms. ``dua`` nhận tiếng của một bên; ``buoc`` lấy MỘT khung từ mỗi bên rồi trả khung
    cho từng bên nghe (chỉ những bên nghe được tiếng)."""

    def __init__(self, *, giua_cac_loa: bool = True, che_do: str = "tron", nguong_db: float = NGUONG_VOX_DB) -> None:
        if che_do not in CHE_DO:
            raise ValueError(f"chế độ không hợp lệ: {che_do}")
        self.giua_cac_loa, self.che_do, self._nguong_db = giua_cac_loa, che_do, nguong_db
        self._nguon: dict[str, _Nguon] = {}
        self._giu_quyen: str | None = None
        self._im = 0                       # số bước người giữ quyền đã im

    # ── Bên tham gia ─────────────────────────────────────────────

    def them(self, ma: str, loai: str) -> None:
        if loai not in (LOA, DIEN_THOAI):
            raise ValueError(f"loại không hợp lệ: {loai}")
        if ma in self._nguon:
            raise ValueError(f"đã có bên {ma}")
        self._nguon[ma] = _Nguon(loai, CongVox(self._nguong_db))

    def bo(self, ma: str) -> None:
        self._nguon.pop(ma, None)
        if self._giu_quyen == ma:
            self._giu_quyen, self._im = None, 0

    @property
    def ds(self) -> list[str]:
        return list(self._nguon)

    def dat_ptt(self, ma: str, giu: bool) -> None:
        if ma in self._nguon:
            self._nguon[ma].ptt = giu

    def thong_ke(self) -> dict[str, dict[str, int]]:
        return {m: {"dem": len(n.dem), "tran": n.tran, "bo": n.bo} for m, n in self._nguon.items()}

    # ── Vào ──────────────────────────────────────────────────────

    def dua(self, ma: str, pcm: bytes) -> None:
        """Nhận tiếng của bên ``ma`` (độ dài bất kỳ, chẵn byte): cắt khung 10 ms, qua cổng mức tiếng, vào đệm có trần (đầy thì bỏ khung CŨ nhất)."""
        n = self._nguon.get(ma)
        if n is None or not pcm:
            return
        buf = n.du + pcm
        so = len(buf) // KHUNG_BYTE * KHUNG_BYTE
        n.du = buf[so:]
        for i in range(0, so, KHUNG_BYTE):
            khung = buf[i:i + KHUNG_BYTE]
            if n.ptt or n.vox is None:
                ra = [khung]
            else:
                ra, co = n.vox.feed(khung)
                if not co and not ra:
                    n.bo += 1
            for k in ra:
                if len(n.dem) >= DEM_TOI_DA:
                    n.dem.popleft()
                    n.tran += 1
                n.dem.append(k)

    # ── Ra: trộn một khung ───────────────────────────────────────

    def _quyen_noi(self, khung: dict[str, bytes]) -> dict[str, bytes]:
        """Chế độ ``quyen_noi``: chỉ một LOA có tiếng ở mỗi bước. Điện thoại luôn qua."""
        loa = {m: k for m, k in khung.items() if self._nguon[m].loai == LOA}
        if self._giu_quyen in loa:
            self._im = 0
        elif self._giu_quyen is not None:
            self._im += 1
            if self._im >= QUYEN_GIU_KHUNG:
                self._giu_quyen, self._im = None, 0
        if self._giu_quyen is None and loa:
            self._giu_quyen = max(loa, key=lambda m: level_db(loa[m]))
            self._im = 0
        return {m: k for m, k in khung.items() if self._nguon[m].loai == DIEN_THOAI or m == self._giu_quyen}

    def buoc(self) -> dict[str, bytes]:
        """Lấy một khung (hoặc im lặng) từ mỗi bên rồi trộn cho từng bên nghe. Bên không có gì để nghe thì không có trong kết quả."""
        khung = {m: n.dem.popleft() for m, n in self._nguon.items() if n.dem}
        if self.che_do == "quyen_noi":
            khung = self._quyen_noi(khung)
        if not khung:
            return {}
        so_mau = KHUNG_BYTE // 2
        mang = {m: _mang(k) for m, k in khung.items()}
        loa = [m for m in mang if self._nguon[m].loai == LOA]
        dt = [m for m in mang if self._nguon[m].loai == DIEN_THOAI]
        tong_loa = [0] * so_mau
        for m in loa:
            tong_loa = [x + y for x, y in zip(tong_loa, mang[m])]
        tong_dt = [0] * so_mau
        for m in dt:
            tong_dt = [x + y for x, y in zip(tong_dt, mang[m])]
        ra: dict[str, bytes] = {}
        for ma, n in self._nguon.items():
            if n.loai == LOA:
                nghe = tong_dt
                co = bool(dt)
                if self.giua_cac_loa:
                    khac = [m for m in loa if m != ma]
                    if khac:
                        nghe = [a + b - c for a, b, c in zip(nghe, tong_loa, mang[ma])] if ma in mang else [a + b for a, b in zip(nghe, tong_loa)]
                        co = True
            else:
                nghe, co = tong_loa, bool(loa)
            if co:
                ra[ma] = _bytes(nghe)
        return ra
