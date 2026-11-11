# Phát đồng bộ nhiều loa R1 bằng Snapcast (thiết kế, chưa cài)

**Trạng thái:** chỉ là thiết kế. Chưa có mã nào chạm vào loa. Việc này phải **do người dùng bật chủ động** trong thẻ R1, mặc định TẮT,
và không tự bật ở bất kỳ phiên bản nào.

## Mục tiêu

1. Nhạc phát từ loa này sang loa kia **đồng bộ** (lệch dưới vài mili giây).
2. Nhiều loa thành một hệ loa: **2 loa = stereo trái/phải**, **3 loa = 2.1** (một loa lo tiếng trầm), mở rộng thêm.

Bluetooth **không** dùng được cho hai mục tiêu này: mỗi loa Bluetooth có độ trễ riêng, lệch hàng chục đến hàng trăm mili giây và không có cách đồng bộ
giữa hai loa. AirPlay (RAOP) đồng bộ được nhưng không chia kênh. Snapcast đồng bộ theo đồng hồ chung và chia kênh được ở phía máy chủ.

## Kiến trúc đề xuất

```
nguồn nhạc (Music Assistant / MPD / YouTube) ──► snapserver (máy .200, Docker)
                                                   │  mỗi «luồng» (stream) là một đường ống PCM
                          ┌────────────────────────┼────────────────────────┐
                     luồng TRÁI (mono)        luồng PHẢI (mono)        luồng TRẦM (lọc thông thấp)
                          │                        │                        │
                  snapclient trên R1 #1    snapclient trên R1 #2    snapclient trên R1 #3
```

- **Chia kênh ở máy chủ:** Snapcast không chọn kênh theo từng máy khách, nên máy chủ tạo thêm các luồng đã chia sẵn bằng `ffmpeg`
  (ví dụ trái: `-af pan=mono|c0=c0`, phải: `pan=mono|c0=c1`, trầm: `lowpass=f=120,pan=mono|c0=0.5*c0+0.5*c1`) và mỗi loa R1 nghe đúng một luồng.
  Loa chạy chế độ «đồng bộ» đơn giản thì nghe luồng stereo đầy đủ.
- **Máy khách trên R1:** R1 chạy Android 5.1 (API 22). Cần một bản `snapclient` chạy được trên đó (APK Snapdroid hoặc nhị phân ARM chạy qua ADB).
  Tích hợp đã có bộ cài ứng dụng qua ADB (`cai_ung_dung.py`) để dùng lại.
- **Thực thể trong HA (đề xuất):**
  - `switch.<loa>_phat_dong_bo` — «Phát đồng bộ nhiều loa»: BẬT thì khởi động snapclient trên loa và trỏ về máy chủ; TẮT thì dừng. Mặc định TẮT,
    trạng thái nhớ qua khởi động lại nhưng **không tự bật** sau khi cài.
  - `select.<loa>_vai_tro_loa` — «Vai trò»: Đầy đủ / Trái / Phải / Trầm.
  - `number.<loa>_do_tre_dong_bo` — chỉnh độ trễ từng loa (mili giây) để các loa khớp tai.
  - Thẻ R1 có công tắc «Phát đồng bộ» và chọn vai trò; tuỳ chọn tích hợp có địa chỉ snapserver.

## Cần đo trên loa thật TRƯỚC khi viết mã (đo ban ngày, cùng chủ máy)

| # | Phép đo | Cách đo | Quyết định |
|---|---|---|---|
| 1 | Snapclient có chạy được trên Android 5.1 của R1 không | cài APK thử qua ADB lên một loa, mở, nối snapserver thử | không chạy được thì cân nhắc cách khác (RAOP nhiều loa, xem `docs/PHAT-RA-LOA.md`) |
| 2 | Đường âm thanh của snapclient có qua cùng đường ra S/PDIF như DLNA không, âm lượng chỉnh bằng gì | phát bíp, đo qua mic loa (cách đã dùng ở ghi chú đo âm lượng) | quyết định có dùng `tinymix`/âm lượng Android để chỉnh âm lượng hệ |
| 3 | Độ trễ khởi động và độ ổn định qua Wi-Fi 2,4 GHz (loa đo được sóng khoảng −30 dBm) | phát liên tục 30 phút, ghi số lần mất đồng bộ | đặt kích thước đệm (`--buffer`) |
| 4 | Hai loa thật cùng nghe có khớp không | phát bíp xung từ hai loa, đo chênh lệch bằng mic | giá trị độ trễ mặc định từng loa |
| 5 | CPU/RAM của R1 khi chạy snapclient cùng bộ đàm/APK `bodam` | xem `sensor.r1_cpu`, `sensor.r1_ram` | có cần tắt bớt dịch vụ không |

Chủ máy hiện chỉ có **một** loa R1, nên phép đo 4 chưa làm được; phép đo 1, 2, 3, 5 làm được với một loa (nối snapclient vào snapserver trên .200 và phát
cho một loa) và đủ để quyết định có làm tiếp hay không.

## Ràng buộc an toàn

- Không tự bật; không đổi cấu hình loa đang phục vụ Zalo/HA khi chưa có chủ máy bên cạnh.
- Cài và thử bằng ADB chỉ khi chủ máy đồng ý từng bước (loa chỉ chấp nhận một khách ADB; xem ghi chú «adbd chỉ 1 client»).
- Có nút tắt khẩn cấp (`switch` TẮT) trả loa về đường phát cũ (DLNA/AirPlay) trong vài giây.
