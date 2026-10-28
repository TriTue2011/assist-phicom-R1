"""Hàng đợi có trần cho luồng tiếng: đầy thì bỏ khúc CŨ NHẤT, luôn giữ tiếng mới nhất và dấu kết thúc.

Quy tắc tài nguyên của kho (docs/PHAT-TRIEN.md, «Quy tắc tài nguyên»): hàng đợi KHÔNG BAO GIỜ không có trần. Tiếng PCM
16 kHz mono là khoảng 32 KB mỗi giây; nếu kênh phát về loa tắc mà bên đẩy vẫn đẩy thì hàng đợi không trần sẽ phình
vài chục MB mỗi phút và làm Home Assistant đầy RAM."""

from __future__ import annotations

import asyncio
from typing import Any


def day_bo_cu_nhat(hang: "asyncio.Queue[Any]", muc: Any) -> bool:
    """Đẩy ``muc`` vào ``hang``; đầy thì bỏ phần tử cũ nhất trước. Trả True nếu phải bỏ khúc cũ."""
    da_bo = False
    while hang.full():
        try:
            hang.get_nowait()
        except asyncio.QueueEmpty:      # bên đọc vừa lấy hết: còn chỗ
            break
        da_bo = True
    hang.put_nowait(muc)
    return da_bo
