"""Tập lệnh gui-wifi-r1.py và trang HTML phải gửi đúng những gì chương trình Bo Cai R1 gửi (đọc từ bytecode, 24/10/2026)."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

GOC = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("gui_wifi", GOC / "gui-wifi-r1.py")
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


@pytest.fixture
def loa_gia():
    nhan = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            nhan.update(path=self.path, ctype=self.headers.get("Content-Type"), body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], nhan
    srv.shutdown()


def test_gui_dung_duong_dan_kieu_json_va_khoa_nhu_bo_cai_r1(loa_gia):
    cong, nhan = loa_gia
    ok, tb = gui.gui_cau_hinh("Nha Toi", "mat-khau", "WPA", host="127.0.0.1", cong=cong)
    assert ok and "200" in tb
    assert nhan["path"] == "/api/configwifi" and nhan["ctype"] == "application/json"
    assert nhan["body"] == {"ssid": "Nha Toi", "secure": "WPA", "password": "mat-khau", "mac": ""}
    gui.gui_cau_hinh("Mo", "bo-qua", "INSECURE", host="127.0.0.1", cong=cong)
    assert nhan["body"]["password"] == "" and nhan["body"]["secure"] == "INSECURE"


def test_loi_mang_tra_false_khong_nem_va_ma_hoa_la_bi_tu_choi():
    ok, tb = gui.gui_cau_hinh("a", "b", host="127.0.0.1", cong=1, timeout=1)
    assert ok is False and tb
    with pytest.raises(ValueError):
        gui.gui_cau_hinh("a", "b", "WPA3")


def test_trang_html_cung_dia_chi_khoa_json_va_buoc_giu_nut():
    html = (GOC / "Trang kết nối WiFi cho loa R1.html").read_text(encoding="utf-8")
    assert f"{gui.HOST}:{gui.CONG}{gui.DUONG}" in html
    for k in ("ssid", "secure", "password", "mac"):
        assert k in html
    assert "giữ nút trên loa 5–10 giây" in html
