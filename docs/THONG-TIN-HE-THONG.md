# Thông tin hệ thống của loa (CPU, RAM, bộ nhớ, WiFi...)

Tích hợp đọc thông tin chạy của loa qua **ADB** (cùng đường với đèn, không cần APK) và đưa lên HA thành cảm biến. Mã: `custom_components/r1_speaker/he_thong.py`.

## Cảm biến

| Thực thể | Giá trị | Thuộc tính |
|---|---|---|
| `sensor.r1_cpu` — CPU của loa | % CPU đang dùng (đo giữa hai mẫu `/proc/stat` cách 1 giây) | `so_nhan`, `tan_so_mhz`, `tai_1_phut`, `tai_5_phut`, `tai_15_phut`, `tien_trinh_nang_nhat` (tên, % CPU, RAM MB) |
| `sensor.r1_ram` — RAM của loa | % RAM đang dùng, **không tính** bộ nhớ đệm (Android luôn dùng hết RAM trống làm đệm nên «MemFree» thấp là bình thường) | `tong_mb`, `dung_mb`, `kha_dung_mb`, `dem_mb` |
| `sensor.r1_bo_nho` — Bộ nhớ trong | % phân vùng `/data` đã dùng | `tong_mb`, `dung_mb`, `trong_mb` |
| `sensor.r1_song_wifi` — Sóng WiFi | cường độ tín hiệu (dBm) | `ten_wifi`, `toc_do_mbps`, `tan_so_mhz` |
| `sensor.r1_thoi_gian_chay` — Thời gian đã chạy | giờ kể từ lần khởi động gần nhất | |

Các cảm biến đều ở nhóm *chẩn đoán*. Loa R1 này **không có cảm biến nhiệt** (không có `thermal_zone`) và **không có pin**, nên không có số đo nhiệt độ hay pin.
**Không** đọc hay hiển thị số sê-ri, địa chỉ MAC hay BSSID của loa.

Số đo mẫu trên loa thật (23/10/2026): RAM 501 MB (khả dụng khoảng 297 MB gồm 282 MB đệm), 4 nhân ARMv7 ở 1,008 GHz, bộ nhớ trong 988 MB (dùng 22,7 %), WiFi −32 dBm / 65 Mbps.

## Đèn là ưu tiên số 1, đọc thông tin là số 2

Loa chỉ có 4 nhân 1 GHz và adbd chỉ có một kết nối, nên khi hai việc trùng nhau **đèn đi trước**:

1. **Đang áp đèn** (hoặc vừa xong trong 2 giây): việc đọc thông tin **chờ** cho đèn xong (tối đa 8 giây); quá hạn thì **bỏ lượt đó**, giữ số cũ, lượt sau đọc lại.
2. **Có hiệu ứng đèn lặp đang chạy** (cầu vồng, sao chổi, chạy đuổi...): việc đọc chuyển sang **chế độ nhẹ** và **thưa**: mỗi 5 phút, bằng lệnh không có `top`, không có `dumpsys wifi`, không có `sleep`;
   CPU tính theo mẫu `/proc/stat` của lần đọc trước; tên WiFi và danh sách tiến trình giữ từ lần đọc đầy đủ gần nhất.
3. Không có hiệu ứng chạy: đọc đầy đủ mỗi 60 giây (một lệnh shell chỉ đọc, khoảng 1,3 giây).

Bộ đọc chỉ chạy khi **có ít nhất một cảm biến đang bật**; tắt hết các cảm biến này thì HA không đọc gì.

## Đọc được thêm gì (chưa làm thành cảm biến)

Qua ADB còn đọc được: phiên bản Android (5.1.1), kernel, tên model (`rk322x-box`), Bluetooth (bật/tắt, tên), âm lượng, bộ nhớ đổi `zram` (64 MB), số dịch vụ đang chạy, `logcat`,
lưu lượng mạng (`/proc/net/dev`). Nói nếu muốn thêm cảm biến nào.
