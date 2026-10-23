# Cài APK cho loa R1 (đầy đủ)

APK `apk/vn-r1-bodam.apk` là ứng dụng trên loa giữ đường mic, đèn (viền chạy đuổi, cầu vồng firmware, đèn chính) và
âm lượng nhạc. Tích hợp HA **không** cài APK; bạn cài một lần bằng `adb` từ máy tính cùng mạng với loa.

## Điều kiện
- Máy tính có `adb` (Android platform-tools).
- Loa cùng mạng LAN với HA, có IP cố định hoặc giữ chỗ DHCP.
- Cổng ADB qua mạng (5555) của loa đang mở. Cách bật tuỳ bạn đã làm trước đây: `<cách bật ADB qua mạng của bạn>`.
- Khoá nghe mic của loa (lấy trong HA: thẻ R1 → Cài đặt → Kết nối → «Hiện lệnh cài APK», chỉ quản trị viên).

## Kiểm tra file APK
```
sha256sum apk/vn-r1-bodam.apk
```
Giá trị phải là `7a8b94a0bad1bb600f3e461c6d2b0c909627ff355c5d46e9854e8b79ba090be1`.

## Các bước (chạy trên máy tính)
Thay `<IP-loa>`, `<IP-HA>`, `<khoá>` bằng giá trị của bạn.

1. Kết nối loa:
   ```
   adb connect <IP-loa>:5555
   ```
2. Đưa APK lên loa và cài (dùng đường dẫn đầy đủ `/system/bin/pm`, lệnh `pm` trần bị chặn trên loa):
   ```
   adb -s <IP-loa>:5555 push apk/vn-r1-bodam.apk /data/local/tmp/
   adb -s <IP-loa>:5555 shell /system/bin/pm install -r /data/local/tmp/vn-r1-bodam.apk
   ```
   Kết quả phải có dòng `Success`.
3. Cấu hình lần đầu (chỉ nhận khi app chưa cấu hình), rồi bật mic:
   ```
   adb -s <IP-loa>:5555 shell /system/bin/am start -n vn.r1.bodam/.ManHinhChinh --es host <IP-HA> --ei port 18765 --es khoa <khoá>
   adb -s <IP-loa>:5555 shell /system/bin/am start -n vn.r1.bodam/.ManHinhChinh --ez bat true
   ```
4. Dọn file tạm:
   ```
   adb -s <IP-loa>:5555 shell rm /data/local/tmp/vn-r1-bodam.apk
   ```

## Kiểm tra sau khi cài
- App đang chạy: `adb -s <IP-loa>:5555 shell /system/bin/ps | grep bodam` có tiến trình `vn.r1.bodam`.
- Trong HA: cảm biến «Trạng thái mic» chuyển sang đang nghe, và «Dịch vụ đèn» là «sẵn sàng».
- Thẻ R1 → Cài đặt có «Đèn RGB chính» và mục «Kiểu viền» đã gỡ.

## Đổi cấu hình về sau
Chạy lại bước 3 với giá trị mới chỉ khi app chưa cấu hình. Nếu cần xoá cấu hình, dùng `pm clear vn.r1.bodam` rồi làm lại bước 3.

## Sau khi xong
Tắt cổng ADB qua mạng theo cách bạn đã bật, để loa không mở cổng 5555 trong mạng nhà.
