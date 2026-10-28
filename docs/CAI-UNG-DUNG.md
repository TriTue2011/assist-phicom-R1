# Cài ứng dụng lên loa R1 qua tích hợp (kể cả loa mới tinh)

Tích hợp `r1_speaker` tự cài các ứng dụng cần thiết lên loa bằng **ADB** (cùng đường với đèn). Không cần máy tính, không cần gõ lệnh `adb`.

## Ứng dụng đi kèm

Danh sách nằm trong `custom_components/r1_speaker/apk/bo-cai.json` (dữ liệu, thêm ứng dụng = thêm một mục). Hiện có:

| Mã | Gói trên loa | Phiên bản | Là gì |
|---|---|---|---|
| `player` | `com.phicomm.speaker.player` | 0.2.5 | Trình phát nhạc DLNA / AirPlay / mạng. Bản cập nhật của ứng dụng hệ thống EchoService (cùng chữ ký Phicomm, `sharedUserId` system). |
| `unisound` | `com.phicomm.speaker.device` | V3.2.5.2- | Ứng dụng thiết bị của hãng. **Có thể chiếm mic của loa**: nếu mic về HA bị tranh, gỡ bằng `pm uninstall com.phicomm.speaker.device` (xem *Gỡ rối*). |
| `bodam` | `vn.r1.bodam` | 1.3 | APK của tích hợp: đẩy tiếng mic về HA, âm lượng, nút giữa (qua dịch vụ trợ năng), Bluetooth, thông tin hệ thống, đèn bằng hiệu ứng firmware. Cài xong HA **tự chạy lệnh cấu hình một lần** (đã có host HA, cổng và khoá nghe mic). |

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
  # apps: [bodam]   # bỏ trống = chỉ những ứng dụng «mặc định» (hiện là bodam); player và unisound phải ghi tên và cài từng cái một
  # force: true                       # gỡ bản cũ nếu khác chữ ký (mất cấu hình của ứng dụng đó)
  # configure: false                  # không tự cấu hình APK mic sau khi cài
```

Một ứng dụng hỏng **không chặn** các ứng dụng sau. Lỗi thường gặp: `INSTALL_FAILED_UPDATE_INCOMPATIBLE` nghĩa là loa đang có bản cùng gói **ký khác**; chỉ khi bạn đặt `force: true` tích hợp mới `pm uninstall` rồi cài lại
(ví dụ APK `vn.r1.bodam` bản 1.1 cũ ký bằng khoá debug khác).

## Trình tự một lần cài

ghép phần và kiểm sha256 → đẩy `/data/local/tmp/r1-<mã>.apk` → `pm install -r` → (nếu cho phép và báo khác chữ ký) `pm uninstall` + cài lại → **xoá tệp tạm** → bước sau cài (chỉ `bodam`: `am start … --es host … --ei port … --es khoa … --ez bat true`).
Tên gói và tên tệp đều qua bộ lọc trước khi vào lệnh; khoá nghe mic **không** ghi vào log hay kết quả trả về.

## Tự kết nối về HA sau khi cài APK

- **Cài qua tích hợp** (nút **Cài đặt** ở thực thể «Ứng dụng: …», hoặc dịch vụ `install_apps`): ngay sau khi cài xong bodam, HA chạy lệnh cấu hình để APK nối về HA, không cần nhập gì.
- **Cài ngoài tích hợp** (chương trình Bo Cai R1 trên máy tính, `adb install` tay): APK chưa biết HA ở đâu nên trước đây phải tự nhập. Từ 0.5.11, HA tự đối chiếu: nếu APK bodam **đã cài trên loa** mà **chưa nối về HA sau 90 giây**, HA tự chạy lại đúng lệnh cấu hình đó.
- Lệnh an toàn khi lặp: APK đã cấu hình thì bỏ qua phần đổi cấu hình, chỉ mở app (cũng đánh thức dịch vụ đang dừng).
- Giới hạn: tối đa 3 lần cho một đợt mất kết nối, cách nhau 10 phút. APK nối lại được thì bộ đếm về 0. ADB bận hoặc loa chưa sẵn sàng thì không tính là một lần.
- Điều kiện: tích hợp đã có khoá và cổng nghe mic (HA tự sinh khi thêm loa) và HA nối được ADB tới loa.

## Nút khởi động lại loa

Thực thể `button.r1_khoi_dong_lai` («Khởi động lại loa») gửi lệnh `reboot` qua ADB; ADB mạng hỏng hoặc đóng thì nút tự chuyển sang cổng 8080 (tin `shell` với lệnh `stop adbd&&start adbd&&adb reboot` của app AI box). Đã thử trên loa thật 28/10/2026 khi ADB mạng còn mở (loa tắt sau ~10 giây, lên lại sau ~30 giây); **chưa thử khi ADB mạng đã đóng**. `reboot` và `setprop sys.powerctl reboot` qua cổng 8080 KHÔNG có hiệu lực (lệnh chạy dưới uid `system`, không phải root). Sau khi loa lên lại, APK tự nối về HA (đã kiểm) và HA tự áp lại đèn.

## Loa mới tinh: thứ tự đề nghị

1. Kết nối WiFi cho loa: [KET-NOI-WIFI.md](KET-NOI-WIFI.md).
2. Thêm tích hợp trong HA với IP loa.
3. Chạy `install_apps` (cài đủ ba ứng dụng rồi tự «Chuẩn bị loa»; hoặc bấm Cài đặt ở từng thực thể «Ứng dụng: …» rồi nút «Chuẩn bị loa (ẩn ứng dụng gốc)»), rồi bấm **Khởi động lại loa** một lần để các ứng dụng hệ thống nạp bản mới.

**Điều kiện:** cổng ADB mạng của loa (`5555`) phải mở. Trên loa của chủ kho cổng này mở sẵn và còn sau khi khởi động lại; **chưa kiểm trên loa mới tinh** (nếu 5555 đóng, tích hợp báo lỗi ADB rõ ràng và không cài được gì).

## Gỡ rối

| Hiện tượng | Xử lý |
|---|---|
| Thực thể «Ứng dụng: …» báo không khả dụng (`ADB: …`) | xem `docs/DEN-LED.md` mục 2 và 10: adbd của loa chỉ nhận **một** kết nối, client ADB khác có thể đang giữ loa |
| `Cài thất bại: INSTALL_FAILED_UPDATE_INCOMPATIBLE` | loa đang có bản ký khác; dùng `force: true` nếu chấp nhận mất cấu hình ứng dụng đó |
| `sha256 … không khớp` | tệp APK trong tích hợp hỏng hoặc thiếu phần: cài lại tích hợp từ HACS |
| Thực thể hiện «(đang ẩn)» | gói có trên loa nhưng bị ẩn (`pm hide`): `pm path` rỗng, tích hợp đọc `dumpsys package` (dòng `hidden=true`) | bình thường, không mời cập nhật; muốn cài đè vẫn gọi `install_apps` |
| Mic về HA bị tranh sau khi cài `unisound` | `adb shell pm uninstall com.phicomm.speaker.device` (hoặc ngắt ứng dụng đó), rồi khởi động lại loa |


## Công thức đúng: cài đủ rồi «Chuẩn bị loa» (ẩn ứng dụng gốc)

Chương trình *Bo Cai R1* trên máy tính (đã chạy tốt trên loa vừa reset, 24/10/2026) làm: cài `player` (autodlna.apk), `unisound` (gói `com.phicomm.speaker.device`) và `bodam`;
**ẩn** (`pm hide`) bảy ứng dụng gốc của hãng (`airskill`, `exceptionreporter`, `systemtool`, `device`, `otaservice`, `productiontest`, `bugreport`); **hiện lại** `ijetty` (máy chủ
cổng 8080) và `netctl`; khởi chạy `EchoService`; ghi dấu bản; khởi động lại loa. Sau đó cổng 8080 trả lời `get_info` ngay (100 giây sau khi bật).

Cài các APK **mà không ẩn** thì loa hỏng (cổng 8080 không trả lời, ứng dụng mất, loa tự khởi động lại): các ứng dụng gốc nhiễu khi máy chủ của hãng không còn (`systemtool` tắt/bật
Wi-Fi, `device` chờ đám mây…). Vì vậy tích hợp làm đúng như chương trình đó:
- `install_apps` cài xong tự chạy «Chuẩn bị loa» (tắt bằng `prepare: false`); `unisound` được ẩn ngay sau khi cài.
- Nút **«Chuẩn bị loa (ẩn ứng dụng gốc)»** và dịch vụ `r1_speaker.prepare_speaker` (`reboot: true` để khởi động lại luôn) chạy riêng bước ẩn/hiện, đảo được bằng `pm unhide`.
- Sau cùng **khởi động lại loa** một lần.


## Sửa loa đã cài bằng bản tích hợp cũ (cổng 8080 không trả lời)

Bản tích hợp cũ (trước 0.5.5) không chạy được lệnh `pm` trên loa này (loa từ chối), không dọn dữ liệu OTA và không ẩn các ứng dụng gốc, nên loa vừa reset hay loa đã cài
theo cách đó có thể không mở/trả lời cổng điều khiển 8080. Sau khi cập nhật tích hợp (HACS) và khởi động lại Home Assistant:
1. Gọi dịch vụ `r1_speaker.install_apps` với giá trị mặc định (hoặc bấm «Cài đặt» ở từng thực thể «Ứng dụng: …» rồi nút «Chuẩn bị loa»).
   Muốn **gỡ rồi cài lại** thì thêm `reinstall: true` (ứng dụng hệ thống về bản gốc rồi cài lại; mất dữ liệu ứng dụng).
   Cài **ghi đè** (`pm install -r`) giữ nguyên dữ liệu ứng dụng; gói `device` đang bị ẩn được hiện lại trước khi cài và ẩn lại sau đó; `bodam` khác chữ ký thì tự gỡ rồi cài.
2. Bấm **Khởi động lại loa**, chờ 30–60 giây.
3. Khi cổng 8080 im lặng liên tục khoảng 5 phút, Home Assistant hiện mục «Sửa chữa» với đúng các bước này; mục tự biến mất khi loa trả lời lại.
