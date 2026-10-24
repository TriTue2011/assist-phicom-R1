#!/usr/bin/env python3
"""Gửi cấu hình WiFi nhà cho loa Phicomm R1 đang ở chế độ chờ cấu hình (WiFi riêng «Phicomm_R1_XXXX»).

Làm ĐÚNG như mục [1] của chương trình Bo Cai R1 (đã đọc bytecode của chương trình, 24/10/2026):
  1. kiểm kết nối TCP tới 192.168.43.1:8989 (3 giây);
  2. POST http://192.168.43.1:8989/api/configwifi, thân JSON {"ssid","secure","password","mac":""},
     Content-Type: application/json, chờ tối đa 10 giây. Loa đổi mạng ngay khi nhận nên lỗi/timeout KHÔNG chắc là thất bại.

Chỉ dùng thư viện chuẩn, chạy được trên Windows, Linux, macOS, Termux. Cách dùng:
    python gui-wifi-r1.py "Tên WiFi" "Mật khẩu"            # WPA/WPA2 (thông dụng)
    python gui-wifi-r1.py "Tên WiFi" "" --ma-hoa INSECURE   # WiFi không mật khẩu
Trước đó: giữ nút trên loa 5–10 giây (đèn nhấp nháy, loa phát âm thanh) và nối máy vào WiFi Phicomm_R1_XXXX (tắt VPN, dữ liệu di động).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request

HOST, CONG, DUONG = "192.168.43.1", 8989, "/api/configwifi"
MA_HOA = ("WPA", "WEP", "INSECURE")


def kiem_tcp(host: str = HOST, cong: int = CONG, timeout: float = 3) -> bool:
    try:
        with socket.create_connection((host, cong), timeout=timeout):
            return True
    except OSError:
        return False


def gui_cau_hinh(ssid: str, password: str, secure: str = "WPA", host: str = HOST, cong: int = CONG, timeout: float = 10) -> tuple[bool, str]:
    """(đã nhận phản hồi, thông điệp). Lỗi mạng trả (False, ...) nhưng nhiều khả năng loa vẫn đã nhận."""
    if secure not in MA_HOA:
        raise ValueError(f"loại mã hoá phải là một trong {MA_HOA}")
    thân = json.dumps({"ssid": ssid, "secure": secure, "password": "" if secure == "INSECURE" else password, "mac": ""}).encode("utf-8")
    req = urllib.request.Request(f"http://{host}:{cong}{DUONG}", data=thân, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}: {r.read().decode('utf-8', 'replace')[:200]}"
    except urllib.error.HTTPError as e:
        return True, f"HTTP {e.code} (loa đã trả lời)"
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return False, f"{e}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ssid"), ap.add_argument("password")
    ap.add_argument("--ma-hoa", choices=MA_HOA, default="WPA")
    a = ap.parse_args(argv)
    if not kiem_tcp():
        print(f"Không nối được {HOST}:{CONG}. Kiểm tra: đã nối WiFi Phicomm_R1_XXXX chưa; loa đã nhấp nháy (giữ nút 5–10 giây) chưa; tắt VPN/dữ liệu di động.")
        return 2
    ok, tb = gui_cau_hinh(a.ssid, a.password, a.ma_hoa)
    if ok:
        print(f"Đã gửi cấu hình ({tb}). Chờ 10–20 giây: loa tự nối WiFi nhà; mạng Phicomm_R1_XXXX sẽ biến mất.")
        return 0
    print(f"Lỗi/timeout khi gửi: {tb}\nCó thể loa đã nhận cấu hình và đang chuyển mạng. Chờ 10–20 giây rồi quét lại; nếu mạng Phicomm_R1_XXXX còn sau 30 giây thì gửi lại.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
