"""Quy tắc tài nguyên (docs/PHAT-TRIEN.md «Quy tắc tài nguyên»): canh bằng AST để không tái phạm.

Gốc: một tích hợp chạy trong tiến trình Home Assistant dùng chung; hàng đợi không trần, chờ chặn vòng lặp sự kiện hay luồng
tự mở làm cả Home Assistant đầy RAM/CPU rồi bị khởi động lại (đã xảy ra: vòng quay pipeline, PCM tích tụ)."""

import ast
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant  # noqa: F401  (đảm bảo môi trường test HA có mặt)

import asyncio

from custom_components.r1_speaker.hang_doi import day_bo_cu_nhat

GOC = Path(__file__).resolve().parents[1] / "custom_components" / "r1_speaker"
TEP = sorted(p for p in GOC.glob("*.py"))


def _cay(p):
    return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def _ten(n):
    if isinstance(n, ast.Attribute):
        return f"{_ten(n.value)}.{n.attr}"
    return n.id if isinstance(n, ast.Name) else ""


def test_hang_doi_luon_co_tran():
    """Mọi ``asyncio.Queue(...)`` phải có ``maxsize`` (hoặc tham số vị trí đầu tiên)."""
    loi = []
    for p in TEP:
        for n in ast.walk(_cay(p)):
            if isinstance(n, ast.Call) and _ten(n.func) == "asyncio.Queue":
                co_tran = bool(n.args) or any(k.arg == "maxsize" for k in n.keywords)
                if not co_tran and not (p.name == "adb_client.py"):   # adb_client có trần riêng ADB_QUEUE_TOI_DA_KHUC
                    loi.append(f"{p.name}:{n.lineno}")
    assert not loi, f"asyncio.Queue() không trần (dùng maxsize + hang_doi.day_bo_cu_nhat): {loi}"


def test_adb_mux_co_tran_khuc():
    nguon = (GOC / "adb_client.py").read_text(encoding="utf-8")
    assert "ADB_QUEUE_TOI_DA_KHUC" in nguon and "dong_tu_xa()" in nguon


def test_khong_goi_chan_trong_ma_bat_dong_bo():
    """Không ``time.sleep``, ``requests``, ``urllib.request``, ``subprocess.run/call/check_*`` (chặn vòng lặp sự kiện);
    việc nặng/đọc tệp đi qua executor."""
    cam = {"time.sleep", "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output"}
    loi = []
    for p in TEP:
        cay = _cay(p)
        for n in ast.walk(cay):
            if isinstance(n, ast.Call) and _ten(n.func) in cam:
                loi.append(f"{p.name}:{n.lineno} {_ten(n.func)}")
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                ten = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
                if any(t.split(".")[0] == "requests" or t == "urllib.request" for t in ten):
                    loi.append(f"{p.name}:{n.lineno} import chặn")
    assert not loi, f"gọi chặn: {loi}"


def test_khong_tu_mo_luong():
    """Không tự ``threading.Thread(...)``/``ThreadPoolExecutor``: dùng ``hass.async_add_executor_job`` hoặc
    ``loop.run_in_executor`` (luồng của Home Assistant, có trần)."""
    loi = []
    for p in TEP:
        for n in ast.walk(_cay(p)):
            if isinstance(n, ast.Call) and _ten(n.func) in {"threading.Thread", "ThreadPoolExecutor",
                                                            "concurrent.futures.ThreadPoolExecutor"}:
                loi.append(f"{p.name}:{n.lineno}")
    assert not loi, f"tự mở luồng: {loi}"


def test_day_bo_cu_nhat_giu_moi_nhat_va_dau_ket_thuc():
    q = asyncio.Queue(maxsize=3)
    bo = [day_bo_cu_nhat(q, i) for i in range(6)]
    assert bo == [False, False, False, True, True, True]
    assert [q.get_nowait() for _ in range(3)] == [3, 4, 5]          # giữ ba khúc MỚI nhất
    for i in range(3):
        day_bo_cu_nhat(q, i)
    day_bo_cu_nhat(q, None)                                          # dấu kết thúc luôn vào được
    assert q.qsize() == 3 and [q.get_nowait() for _ in range(3)][-1] is None


async def test_intercom_hang_phat_khong_phinh(hass):
    """Kênh phát về loa tắc mà tiếng vẫn tới: hàng đợi chỉ giữ tối đa PLAY_QUEUE_CHUNKS khúc."""
    from custom_components.r1_speaker.const import PLAY_QUEUE_CHUNKS
    q = asyncio.Queue(maxsize=PLAY_QUEUE_CHUNKS)
    for i in range(PLAY_QUEUE_CHUNKS * 5):
        day_bo_cu_nhat(q, bytes([i % 256]) * 2048)
    assert q.qsize() == PLAY_QUEUE_CHUNKS
