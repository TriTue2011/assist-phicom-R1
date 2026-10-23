# Cài ứng dụng lên loa R1 qua tích hợp (kể cả loa mới tinh)

Tích hợp `r1_speaker` tự cài các ứng dụng cần thiết lên loa bằng **ADB** (cùng đường với đèn). Không cần máy tính, không cần gõ lệnh `adb`.

## Ứng dụng đi kèm

Danh sách nằm trong `custom_components/r1_speaker/apk/bo-cai.json` (dữ liệu, thêm ứng dụng = thêm một mục). Hiện có:

| Mã | Gói trên loa | Phiên bản | Là gì |
|---|---|---|---|
| `player` | `com.phicomm.speaker.player` | 0.2.5 | Trình phát nhạc DLNA / AirPlay / mạng. Bản cập nhật của ứng dụng hệ thống EchoService (cùng chữ ký Phicomm, `sharedUserId` system). |
| `unisound` | `com.phicomm.speaker.device` | 25.3.1 | Ứng dụng thiết bị của hãng. **Có thể chiếm mic của loa**: nếu mic về HA bị tranh, gỡ bằng `pm uninstall com.phicomm.speaker.device` (xem *Gỡ rối*). |
| `bodam` | `vn.r1.bodam` | 1.2 | APK của tích hợp: đẩy tiếng mic về HA, âm lượng, nút giữa. Cài xong HA **tự chạy lệnh cấu hình một lần** (đã có host HA, cổng và khoá nghe mic). |

Tệp APK nằm cùng thư mục (`apk/`); `unisound` được **chia hai phần** (`unisound.apk.00`, `.01`) vì GitHub giới hạn 25 MB khi tải lên: tích hợp tự ghép và **kiểm sha256** trước khi đẩy
(sai sha256 thì không đẩy gì lên loa).

## Cách cài

**Cách 1: thực thể Cập nhật.** Mỗi ứng dụng có một thực thể `update.*` («Ứng dụng: …»): *đã cài* là phiên bản đang trên loa (hoặc «chưa cài»), *mới nhất* là phiên bản đi kèm tích hợp
(bản trùng từng byte với bản đi kèm thì coi là mới nhất). Bấm **Cài đặt** để cài. Có bản mới (tích hợp cập nhật qua HACS) thì HA tự báo «có cập nhật».

**Cách 2: dịch vụ `r1_speaker.install_apps`** (cài nhiều ứng dụng một lượt, theo thứ tự, trả kết quả từng cái):

```yaml
action: r1_speaker.install_apps
data:
  entity_id: sensor.r1_cai_dat
  # apps: [player, unisound, bodam]   # bỏ trống = tất cả
  # force: true                       # gỡ bản cũ nếu khác chữ ký (mất cấu hình của ứng dụng đó)
  # configure: false                  # không tự cấu hình APK mic sau khi cài
```

Một ứng dụng hỏng **không chặn** các ứng dụng sau. Lỗi thường gặp: `INSTALL_FAILED_UPDATE_INCOMPATIBLE` nghĩa là loa đang có bản cùng gói **ký khác**; chỉ khi bạn đặt `force: true` tích hợp mới `pm uninstall` rồi cài lại
(ví dụ APK `vn.r1.bodam` bản 1.1 cũ ký bằng khoá debug khác).

## Trình tự một lần cài

ghép phần và kiểm sha256 → đẩy `/data/local/tmp/r1-<mã>.apk` → `pm install -r` → (nếu cho phép và báo khác chữ ký) `pm uninstall` + cài lại → **xoá tệp tạm** → bước sau cài (chỉ `bodam`: `am start … --es host … --ei port … --es khoa … --ez bat true`).
Tên gói và tên tệp đều qua bộ lọc trước khi vào lệnh; khoá nghe mic **không** ghi vào log hay kết quả trả về.

## Nút khởi động lại loa

Thực thể `button.r1_khoi_dong_lai` («Khởi động lại loa») gửi lệnh `reboot` qua ADB. Sau khi loa lên lại, APK tự nối về HA (đã kiểm) và HA tự áp lại đèn.

## Loa mới tinh: thứ tự đề nghị

1. Kết nối WiFi cho loa: [KET-NOI-WIFI.md](KET-NOI-WIFI.md).
2. Thêm tích hợp trong HA với IP loa.
3. Chạy `install_apps` (hoặc bấm Cài đặt ở từng thực thể «Ứng dụng: …»), rồi bấm **Khởi động lại loa** một lần để các ứng dụng hệ thống nạp bản mới.

**Điều kiện:** cổng ADB mạng của loa (`5555`) phải mở. Trên loa của chủ kho cổng này mở sẵn và còn sau khi khởi động lại; **chưa kiểm trên loa mới tinh** (nếu 5555 đóng, tích hợp báo lỗi ADB rõ ràng và không cài được gì).

## Gỡ rối

| Hiện tượng | Xử lý |
|---|---|
| Thực thể «Ứng dụng: …» báo không khả dụng (`ADB: …`) | xem `docs/DEN-LED.md` mục 2 và 10: adbd của loa chỉ nhận **một** kết nối, client ADB khác có thể đang giữ loa |
| `Cài thất bại: INSTALL_FAILED_UPDATE_INCOMPATIBLE` | loa đang có bản ký khác; dùng `force: true` nếu chấp nhận mất cấu hình ứng dụng đó |
| `sha256 … không khớp` | tệp APK trong tích hợp hỏng hoặc thiếu phần: cài lại tích hợp từ HACS |
| Thực thể Unisound báo «chưa cài» dù loa có ứng dụng này | gói đang bị **ẩn** (`pm hide`): `pm path` trả rỗng, nên bộ dò coi là chưa cài (lỗi đã biết) | đừng bấm «Cập nhật»; kiểm bằng `dumpsys package com.phicomm.speaker.device` (dòng `hidden=true`) |
| Mic về HA bị tranh sau khi cài `unisound` | `adb shell pm uninstall com.phicomm.speaker.device` (hoặc ngắt ứng dụng đó), rồi khởi động lại loa |
