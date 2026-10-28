# Dành cho người phát triển

Nội dung chuyển từ README: trạng thái đã kiểm, chạy test, cấu trúc kho, việc còn thiếu.

## 7. Trạng thái: đã kiểm trên loa thật và chỉ kiểm bằng mock

**Đã kiểm trên loa thật (do chủ dự án thực hiện, theo tài liệu và báo cáo đo):**

- Cổng 8080 trả `get_info` và `get_eq_config`; cấu trúc dữ liệu EQ đã đọc thật (5 dải, giới hạn ±1500 mB).
- Ghi thật và đọc lại: `set_eq_bandlevel` (dải 0) và `set_bass_enable`.
- Mã phím nút giữa = 195 (đọc từ `/dev/input/event0`).
- Đèn viền chỉ trắng; đèn đáy xanh lá và xanh dương (xem mắt) — mục 5.
- Phần cứng/hệ điều hành (RK3229, Android 5.1.1, card âm thanh AK7755, shell uid 2000).

**CHỈ kiểm bằng mock/loa giả (chưa thử trên loa thật hoặc HA thật cùng loa):**

- Toàn bộ tích hợp HA: **316 ca test** với loa giả ở `127.0.0.1` (WebSocket giả, renderer UPnP giả, client TCP giả), xem mục 9.
- **Âm lượng** đã xác nhận (nghe thật 22/10/2026): đặt qua APK bằng `AudioManager.setStreamVolume`, không qua cổng 8080. Các lệnh còn lại: bật/tắt EQ, cường độ bass, loudness, DLNA/AirPlay (viết theo tài liệu dịch ngược, **chưa ghi thử**; thực thể mang
  thuộc tính `confirmed: false`, thẻ ghi «chưa xác nhận»). Preset EQ chỉ hiển thị.
- Phát TTS/nhạc qua DLNA (`Set_DLNA_Open`, cổng của renderer, định dạng âm thanh nhận được).
- **Đầu nhận mic của HA** (`mic_server.py`) với **client TCP giả** theo giao thức APK; **APK chưa từng nối vào HA thật**.
- APK: build thành công (aapt/javac/d8/zipalign/apksigner mã thoát 0), **30 ca test Java thuần** (khung gói, khuếch đại dB, máy ghi với vận chuyển giả,
  logic nút với đồng hồ giả) — báo cáo của người build; **mã nguồn không có trong kho nên người nhận không chạy lại được**. Khi đóng gói đã
  đối chiếu bytecode của APK: khung giao thức, mã 195, `repeatCount==0`, manifest khớp báo cáo.
- **Chưa kiểm trên loa thật**: cài APK; mic qua `AudioRecord` có ra tiếng không và ai đang giữ mic (ứng dụng giọng nói gốc của loa có thể giữ); độ trễ; nút giữa
  có tới được app; Bluetooth bật/tắt; `pm hide`; mọi đèn do HA điều khiển; thẻ trong trình duyệt thật ngoài Chrome không đầu.
- **Chưa có**: dịch vụ phát PCM thô ra loa (bộ đàm nói vào loa), từ đánh thức chạy trên loa (đèn đã có bằng hiệu ứng firmware; đàm thoại hai chiều đã có ở thẻ)
  (việc này đang được làm, chưa hoàn thành).


## 8b. Quy tắc tài nguyên (RAM, CPU, kết nối, luồng)

Tích hợp chạy **trong tiến trình Home Assistant dùng chung**: một chỗ ngốn tài nguyên là cả Home Assistant đầy RAM rồi bị khởi
động lại (đã xảy ra thật: vòng nghe quay không nghỉ, PCM tích tụ). Mọi mã mới phải theo các quy tắc sau; ba quy tắc đầu có
test canh bằng AST (`tests/test_quy_tac_tai_nguyen.py`).

1. **Hàng đợi luôn có trần.** Mọi `asyncio.Queue` phải có `maxsize`; đầy thì bỏ khúc **cũ nhất** (`hang_doi.day_bo_cu_nhat`),
   không chặn bên đẩy và không để RAM tăng. Tiếng PCM 16 kHz mono ≈ 32 KB/giây: hàng đợi không trần phình vài chục MB mỗi
   phút nếu kênh phát tắc. Luồng ADB ghép kênh có trần riêng (`ADB_QUEUE_TOI_DA_KHUC`, vượt thì đóng luồng).
2. **Không chặn vòng lặp sự kiện.** Không `time.sleep`, `requests`, `urllib.request`, `subprocess.run/call/check_*` trong mã
   bất đồng bộ. Đọc tệp và việc nặng đi qua `hass.async_add_executor_job` hoặc `loop.run_in_executor`.
3. **Không tự mở luồng.** Không `threading.Thread(...)` hay `ThreadPoolExecutor`: dùng luồng có trần của Home Assistant
   (executor), và chỉ cho việc thật sự chặn.
4. **Mở nhanh, đóng nhanh.** Kết nối tới loa (ADB, TCP phát tiếng) mở khi cần, đóng ngay khi xong, đóng trong `finally`; không
   giữ kết nối rảnh. Kết nối ADB chỉ giữ ngắn (nhả sau vài giây không dùng); mỗi lượt phát tiếng mở một kết nối rồi đóng khi hết
   tiếng. Ngoại lệ có chủ đích và ghi rõ: máy chủ nghe mic (loa nối vào, một luồng).
5. **Lỗi lặp thì nghỉ tăng dần.** Việc lặp lại khi lỗi (nối lại, chạy lượt pipeline…) phải nghỉ giữa các lần và tăng khoảng
   nghỉ (2, 4, 8… có trần); không thử lại liên tục, không bật đèn hay gọi ADB mỗi vòng, chỉ báo lỗi một lần cho cả chuỗi.
   Mọi vòng `while True` phải có chỗ `await` thật (nhường vòng lặp sự kiện).
6. **Tác vụ nền có chủ.** Tạo bằng `async_create_background_task`, lưu tham chiếu, huỷ khi gỡ tích hợp/đóng phiên; không để tác
   vụ mồ côi.
7. **Dữ liệu tích luỹ có trần.** Danh sách, từ điển, bộ đệm giữ theo thời gian phải có giới hạn số mục hoặc tuổi; nhật ký chỉ
   ghi **kiểu lỗi** một lần, không ghi mỗi vòng.

## 9. Chạy test

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest                                  # toàn bộ; loa giả ở 127.0.0.1, KHÔNG chạm loa thật
.venv/bin/python -m pytest tests/test_mic_server.py -q      # riêng đầu nhận mic (khoá sai, đứt giữa chừng, tắt mic, khung lẻ...)
.venv/bin/python -m bandit -r custom_components -lll -q     # quét bảo mật mức cao
```

Mọi khoá/token/địa chỉ trong `tests/` là **chuỗi giả** (địa chỉ ví dụ ở dải `192.0.2.0/24`
của RFC 5737 hoặc `127.0.0.1`); không có bí mật thật. Bộ test nặng khoảng 1,5 phút; xét **mã thoát** vì cấu hình có thể nén dòng tổng kết.

## 10. Cấu trúc kho

```
custom_components/r1_speaker/   tích hợp HA (mã, translations/, www/ chứa 3 thẻ Lovelace)
apk/                            vn-r1-bodam.apk + .sha256; nguon/ = mã nguồn APK + test Java + README-BUILD
docs/                           HUONG-DAN-CAI-DAT.md, HOP-DONG-PHIA-LOA.md, DEN-LED.md, PHAT-RA-LOA.md, THIET-KE-MIC.md, BAI-HOC-TU-CAMERA.md
tests/                          test pytest (loa giả)
requirements-test.txt  pytest.ini  hacs.json
```

`docs/HUONG-DAN-CAI-DAT.md` là hướng dẫn HA đầy đủ (tuỳ chọn, thẻ, Assist, bộ đàm); `docs/HOP-DONG-PHIA-LOA.md` là hợp đồng giao thức HA ↔ loa. Hai tài liệu này đã được
đồng bộ với README; nếu thấy mâu thuẫn thì README (mục 7) là bản trạng thái mới nhất.

## 11. Việc còn thiếu đã biết

- **Nút giữa chỉ chạy khi app ở tiền cảnh**, hoặc khi bật dịch vụ tiếp cận phím (mặc định tắt).
- Cấu hình APK không cần màn hình chỉ làm được LẦN ĐẦU bằng `am start` (mục 3); đổi về sau phải `pm clear`.
- APK ký bằng khoá debug; mic tự bật sau khi loa khởi động lại (đã viết, **chưa kiểm** bằng khởi động lại thật).
- `mic_host` đóng hai vai (mục 6; `docs/HOP-DONG-PHIA-LOA.md` 2b).
- Giấy phép: **CHỦ MÁY CHỌN GIẤY PHÉP** (chưa có `LICENSE`).
- Chưa có: từ đánh thức phát hiện NGAY TRÊN loa (từ đánh thức đang chạy ở phía HA bằng openWakeWord khi mic gửi liên tục), dịch vụ đèn trên loa (xem `docs/DEN-LED.md`).
- Các giá trị mặc định đánh dấu «CHƯA ĐO» trong tuỳ chọn (ngưỡng bộ đàm, +12 dB mic, cổng 18765, 8765…) là số đề xuất.
