# assist-phicom-R1 — loa Phicomm R1 trong Home Assistant

[![Mở kho này trong HACS của bạn.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TriTue2011&repository=assist-phicom-R1&category=integration)

Kho này biến loa **Phicomm R1** thành một thiết bị đầy đủ của Home Assistant (HA), gồm hai phần chạy cùng nhau:

1. **Tích hợp HA `r1_speaker`** (`custom_components/r1_speaker/`): EQ, âm lượng, DLNA/AirPlay; phát tiếng của HA (TTS, nhạc) ra loa; vệ tinh Assist với từ đánh thức;
   bộ đàm; **đèn LED** (13 hiệu ứng, mỗi hiệu ứng có thông số riêng, mục Thử riêng); **cài ứng dụng lên loa qua ADB** (kể cả loa mới tinh); nút khởi động lại loa;
   cảm biến CPU/RAM/bộ nhớ/WiFi của loa; thẻ Lovelace `r1-card` (đàm thoại, EQ, chức năng, cài đặt); icon riêng (`brand/`; HA có hỗ trợ thư mục này tự nạp, đã thấy trong 2026.10.3, bản cũ hơn chưa kiểm).
2. **APK `vn.r1.bodam`** (`apk/`): ứng dụng Android nhỏ trên loa, lấy tiếng mic gửi về HA **chỉ khi người dùng bật**; nút giữa bật/tắt mic.

> **Đọc trước khi làm theo.** Đây là dự án thử nghiệm. Phần lớn mã được kiểm bằng loa giả trên máy phát triển; các điểm đã kiểm trên **loa thật** và điểm **chưa kiểm** được ghi rõ ở từng mục và ở
> [docs/PHAT-TRIEN.md](docs/PHAT-TRIEN.md). Cài ứng dụng lên loa và dùng ADB là việc **khó đảo ngược** với thiết bị của bạn: đọc phần *Quyền riêng tư và bảo mật* trước.

**Giấy phép: [MIT](LICENSE)** cho mã của kho này (tích hợp `r1_speaker`, APK `vn.r1.bodam`, trang kết nối WiFi). Các ứng dụng gốc của hãng Phicomm đi kèm trong `custom_components/r1_speaker/apk/` (`autodlna.apk`, `unisound.apk.*`) **không** thuộc giấy phép này: chúng thuộc bản quyền của hãng, kho chỉ mang theo để cài lên loa của chính bạn.

## Ưu điểm và nhược điểm

**Ưu điểm**

- Đủ bộ thực thể HA cho loa: EQ, âm lượng, DLNA/AirPlay, phát TTS/nhạc, vệ tinh Assist, đèn LED (13 hiệu ứng), nút khởi động lại, cảm biến CPU/RAM/WiFi.
- **Chỉ cần HACS**: tích hợp tự cài ứng dụng lên loa qua mạng (kể cả loa mới tinh), không phải cài `adb` hay chạy lệnh trên máy tính.
- Báo thức, nhắc nhở, hẹn giờ tắt nhạc chạy bằng HA (không phụ thuộc máy chủ của hãng); thêm được nhiều loa độc lập, đàm thoại giữa các loa.
- Mic loa chỉ về HA khi bật; tắt bằng `switch.r1_tat_mic` là dừng.

**Nhược điểm**

- **Dự án thử nghiệm**: phần lớn kiểm bằng loa giả; nhiều điểm chưa kiểm trên loa thật ([docs/PHAT-TRIEN.md](docs/PHAT-TRIEN.md)).
- Cài đặt dựa vào **ADB mạng (cổng 5555) không mã hoá, không xác thực**: phải khoá cổng hoặc đóng ADB sau khi cài (xem [Hạn chế bị tấn công qua ADB](#hạn-chế-bị-tấn-công-qua-adb-với-modem-hoặc-router-bất-kỳ)).
- Cài ứng dụng và ẩn ứng dụng gốc của hãng là việc **khó đảo ngược** với thiết bị của bạn.
- Đóng ADB thì mất đèn tự do, cài/cập nhật ứng dụng, thông tin hệ thống, công tắc Bluetooth; mở lại phải rút điện loa.
- Tiếng và khoá mic đi qua TCP trơn trong LAN (chỉ dùng mạng tin cậy); loa cần IP tĩnh và cổng `18765` thông từ loa về HA.
- Cần Home Assistant **2026.2 trở lên**.

## Cài đặt nhanh (chỉ cần HACS)

Không cần cài `adb` hay chạy lệnh nào trên máy tính: tích hợp tự nói chuyện với loa qua mạng.

1. **Reset loa vào chế độ chờ WiFi** (loa cần reset hoặc chưa biết WiFi nhà): **rút điện** loa → **giữ nút nguồn** → vẫn giữ, **cắm điện** → khi đèn hiện **đen, trắng, hồng** thì **nhả tay**. Loa phát WiFi `Phicomm_R1_XXXX` (chi tiết và cách khác cho loa mới tinh: [mục 4](#4-kết-nối-wifi-cho-loa-mới-hoặc-vừa-reset)).
2. **Cho loa vào WiFi nhà bằng trang HTML:** tải sẵn `Trang kết nối WiFi cho loa R1.html`, nối điện thoại/máy tính vào WiFi `Phicomm_R1_XXXX` (tắt VPN và dữ liệu di động), mở tệp HTML, điền WiFi nhà → **Gửi cấu hình**, chờ 10–20 giây. Nối lại WiFi nhà, rồi đặt **IP tĩnh** (hoặc giữ chỗ DHCP) cho loa trong router.
3. **Mở cổng `18765`** từ loa tới máy chạy Home Assistant (xem *Tường lửa và Docker* bên dưới).
4. **HACS → ⋮ → Custom repositories** → dán địa chỉ kho này, loại **Integration** → cài **Phicomm R1 Speaker** → **khởi động lại Home Assistant**.
5. **Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp → Phicomm R1 Speaker** → nhập **IP của loa** (cổng điều khiển để mặc định `8080`).
6. **Cài ứng dụng lên loa:** **Công cụ nhà phát triển → Hành động** → chọn `r1_speaker.install_apps` → ở `entity_id` chọn một thực thể của loa (ví dụ `sensor.r1_cai_dat`), **để mặc định** các tuỳ chọn → **Thực hiện hành động**. Nó cài đủ ba ứng dụng (trình phát, thiết bị và giọng nói, APK mic `vn.r1.bodam`), cấu hình APK mic, rồi **tự chạy «Chuẩn bị loa»** (ẩn các ứng dụng gốc của hãng).
   - Cài từng ứng dụng bằng nút **Cài đặt** ở các thực thể **«Ứng dụng: …»** thì chỉ cài ứng dụng đó, **không** ẩn ứng dụng gốc: phải bấm thêm nút **«Chuẩn bị loa (ẩn ứng dụng gốc)»** ở cuối. Bỏ bước này thì loa hỏng (cổng `8080` không trả lời, loa tự khởi động lại).
7. Bấm nút **Khởi động lại loa** (cả «Chuẩn bị loa» lẫn `install_apps` đều **không** tự khởi động lại), đợi **1–2 phút** (cổng điều khiển trên loa lên sau khoảng 100 giây).
8. **Kiểm:** nói gần loa, `sensor.r1_trang_thai_mic` phải chuyển **«gui»**. Rồi thêm thẻ `type: custom:r1-card` vào bảng điều khiển (4 tab: Đàm thoại, EQ, Chức năng, Cài đặt).
9. **Chọn cách điều khiển loa: dùng APK (đóng ADB) hay dùng ADB (giữ ADB).** Đây là lựa chọn quan trọng nhất sau khi cài, xem bảng dưới.

> Loa vừa reset: cổng ADB mạng `5555` của loa phải mở thì bước 6 mới chạy được (chưa kiểm trên loa vừa reset). Mở rồi mà báo bận thì tắt mọi công cụ `adb` khác: loa chỉ nhận **một** kết nối ADB một lúc.

### Chọn: dùng APK hay dùng ADB

Bạn chọn **một** cách (ô **«Chế độ đóng ADB»** ở **Cài đặt → Thiết bị & dịch vụ → Phicomm R1 Speaker → Cấu hình**, hoặc nút **«Đóng ADB mạng…»** để đóng ngay một lần):

| | **Dùng APK** (đóng ADB) | **Dùng ADB** (giữ ADB, mặc định) |
|---|---|---|
| An ninh | Không máy nào trong mạng nối được cổng `5555` | Cổng `5555` mở không xác thực cho cả LAN; phải tự bảo vệ (phần cuối trang) |
| Chạy được | Mic, đàm thoại, Assist, âm lượng, phát nhạc DLNA/AirPlay, Dừng, Tắt tiếng, nút giữa (APK 1.3) | Tất cả |
| Đèn | Chỉ hiệu ứng có sẵn của firmware (màu cố định, thở, hướng đánh thức) | Đèn tự do 13 hiệu ứng, màu RGB tuỳ ý |
| Mất | Cài/cập nhật ứng dụng, «Chuẩn bị loa», thông tin hệ thống, công tắc Bluetooth | — |
| Mở lại ADB | Rút điện loa rồi cắm lại (làm xong thì đóng lại) | — |
| Rủi ro | Phải cài xong và APK đã nối về HA trước khi đóng | ADB bị chiếm thì loa mất kiểm soát |

- **Chọn APK:** bật «Chế độ đóng ADB» (tự đóng khi APK đã nối ổn định 2 phút; không bao giờ đóng khi APK chưa nối) hoặc bấm «Đóng ADB mạng…», rồi đặt **«Nguồn phím» = `apk`** (nếu để `adb` thì nút giữa ngừng chạy khi ADB đóng). Nút «Khởi động lại loa» tự đi qua cổng `8080` (đã thử khi ADB còn mở, **chưa thử khi đã đóng**).
- **Chọn ADB:** giữ mặc định, rồi làm phần **«Hạn chế bị tấn công qua ADB»** ở cuối trang. Loa chỉ nhận **một** kết nối ADB một lúc: đừng chạy `adb` từ máy khác khi HA đang dùng.
- **Gợi ý:** cài xong và kiểm xong (bước 8) mới đóng ADB, vì khi đóng không cài/cập nhật được ứng dụng.

**Các lựa chọn khác** (đều ở **Cài đặt → Thiết bị & dịch vụ → Phicomm R1 Speaker → Cấu hình**, trừ hành động phím):

| Lựa chọn | Giá trị | Chọn khi |
|---|---|---|
| **Nguồn phím** (nút giữa) | `adb` (mặc định): HA đọc phím qua ADB, không cần APK mới, nhưng cần ADB mở và giữ một luồng ADB liên tục<br>`apk`: APK 1.3 báo phím qua dịch vụ trợ năng, chạy được cả khi ADB đóng<br>`tat`: không nhận phím | Giữ ADB → `adb`; đóng ADB → `apk` |
| **Cách nối ADB** (`adb_mode`) | `auto` (tự nhận), `server` (qua adb-server container), `direct` (nối thẳng loa) | Thường để `auto`; có adb-server riêng thì `server` |
| **Hành động nút giữa** (bốn ô chọn: nhấn 1, 2, 3 lần, giữ) | Mặc định theo app AI box: 1 lần tắt báo thức/đàm thoại, 2 lần Assist, 3 lần Bluetooth, giữ đèn theo nhạc | Muốn như APK cũ (đơn = tắt mic, đúp = Bluetooth) thì đổi ở bốn ô này |
| **Mic** | «Tăng mic» khoảng **18 dB** và bật **hạn đỉnh**; **đừng bật AGC** với mặc định hiện tại (mục 10) | Từ đánh thức không nhận |
| **Từ đánh thức** | Do HA dò trong luồng mic (có); chạy trên loa **chưa có** | — |

### Tường lửa và Docker

Loa gọi ngược về Home Assistant ở **cổng 18765** (mỗi loa thêm một cổng kế tiếp: 18766…). Cổng này phải thông từ loa tới máy chạy Home Assistant:

- **Máy có tường lửa** (ví dụ `ufw`): mở cổng.
  ```
  ufw allow 18765 comment "R1 Speaker Port"
  ```
- **Home Assistant chạy bằng Docker:** dùng `network_mode: host`, hoặc công bố cổng trong compose (`ports: - "18765:18765"`). Docker **tự mở** cổng khi công bố, **không cần** thêm luật `ufw`.
- Home Assistant OS / Supervised: không cần làm gì thêm.

## Sửa lỗi

| Thấy | Làm |
|---|---|
| Nhật ký `8080 ConnectionRefused` hoặc `TimeoutError` lặp lại, loa chập chờn | Chưa ẩn ứng dụng gốc: bấm **«Chuẩn bị loa (ẩn ứng dụng gốc)»**, rồi **Khởi động lại loa** |
| `ADB … đang bận phục vụ một client ADB khác` | Tắt công cụ `adb` khác (`adb disconnect`, `adb kill-server`) rồi thử lại |
| Thẻ Đàm thoại báo «Chưa có kênh phát về loa», mic chỉ «nghe», không lên «gui» | Mở cổng 18765 (mục trên), tích **«Ghép lại APK»** trong Tuỳ chọn, khởi động lại loa |
| Sau khi cài, mic không tự chạy lại sau khởi động | APK chưa từng được mở một lần: bấm **Cài đặt** lại ở «Ứng dụng: …» (mic) rồi khởi động lại loa |
| Không thấy WiFi `Phicomm_R1_XXXX` | Loa chưa ở chế độ chờ: làm lại bước 1 (rút điện, giữ nút nguồn, cắm điện, nhả khi đèn đen–trắng–hồng) |
| Cần cài/cập nhật ứng dụng nhưng ADB đã đóng | **Rút điện loa rồi cắm lại** (ADB mở lại), làm xong thì đóng lại |
| Nút giữa không chạy sau khi đóng ADB | Đổi **«Nguồn phím»** thành `apk` (cần APK 1.3), hoặc mở lại ADB |
| Đèn không sáng | Xem `binary_sensor.r1_dich_vu_den` (thuộc tính `loi`); tự thử lại sau 15 giây. ADB đóng thì đèn chạy qua APK |

Chi tiết: [mục 11 (gỡ rối)](#11-gỡ-rối), [docs/CAI-UNG-DUNG.md](docs/CAI-UNG-DUNG.md), [docs/HUONG-DAN-CAI-DAT.md](docs/HUONG-DAN-CAI-DAT.md).

## Hạn chế bị tấn công qua ADB với modem hoặc router bất kỳ

**Vì sao cần:** ADB mạng của loa (cổng `5555`) không mã hoá và không đòi mật khẩu; máy nào nối được cổng này đều chạy được lệnh trên loa, và loa có `ro.debuggable=1` nên có thể là quyền root. Botnet quét cổng ADB trên Internet và từ các thiết bị đã bị nhiễm ngay trong mạng nhà (TV box giá rẻ…). Làm theo thứ tự; **bước 1 và 2 làm được với mọi modem/router**:

1. **Đóng ADB ngay trên loa** (không phụ thuộc router): chọn «Dùng APK» ở bước 9. Kiểm từ một máy khác trong mạng: `nc -zv <IP-loa> 5555` (Windows PowerShell: `Test-NetConnection <IP-loa> -Port 5555`) phải **không nối được**.
2. **Không để cổng ra Internet:** vào trang quản trị router và kiểm
   - **Port Forwarding / Virtual Server / NAT:** không có luật nào chuyển cổng `5555` về IP loa;
   - **DMZ:** không đặt IP loa làm DMZ host;
   - **UPnP:** tắt (thiết bị trong nhà không được tự mở cổng);
   - **Quản trị từ xa (Remote Management)** của router: tắt hoặc giới hạn;
   - **IPv6:** nếu router cấp IPv6 công khai cho thiết bị trong nhà, bật tường lửa IPv6 chặn kết nối từ ngoài vào (chưa kiểm loa có nghe ADB trên IPv6).

   Kiểm từ ngoài: tắt WiFi, dùng 4G, quét cổng `5555` của IP công khai nhà bạn: phải đóng.
3. **Tách thiết bị không tin cậy:** đặt TV box giá rẻ, thiết bị của khách, camera không rõ nguồn gốc vào **mạng khách (Guest) có bật cách ly thiết bị (Client/AP Isolation)** hoặc một VLAN riêng. Đừng đưa mật khẩu WiFi chính cho người lạ: ai vào được mạng nhà là chạm được cổng ADB nếu còn mở.
4. **Nếu phải giữ ADB:** chỉ cho IP Home Assistant vào `<IP-loa>:5555` và chặn mọi nguồn khác (ví dụ RouterOS ở [mục 12](#12-quyền-riêng-tư-và-bảo-mật)). Việc này chỉ làm được trên router lọc được **giữa các thiết bị trong cùng LAN** (OpenWrt, MikroTik, UniFi, pfSense/OPNsense…, thường kèm một VLAN riêng cho loa). Modem/router phổ thông của nhà mạng thường chỉ lọc giữa Internet và LAN, **không chặn được LAN↔LAN**: khi đó chỉ có bước 1 là chắc chắn.
5. **Giữ router an toàn:** cập nhật firmware, đổi mật khẩu quản trị mặc định, dùng WPA2/WPA3 với mật khẩu mạnh, tắt WPS.
6. **Cần cập nhật ứng dụng trên loa:** rút điện loa để mở lại ADB, làm xong đóng lại ngay.

## Mục lục

Cài đặt nhanh, Sửa lỗi, Hạn chế bị tấn công qua ADB ở trên · [4. WiFi cho loa](#4-kết-nối-wifi-cho-loa-mới-hoặc-vừa-reset) · [5. Đèn](#5-đèn) · [6. Ứng dụng trên loa](#6-ứng-dụng-trên-loa-cài-từ-ha) ·
[7. Thông tin hệ thống](#7-thông-tin-hệ-thống-của-loa) · [8. Nút giữa](#8-nút-giữa) · [9. Mic về HA](#9-nối-mic-loa-về-ha) · [10. Từ đánh thức](#10-từ-đánh-thức-và-chỉnh-mic) ·
[11. Gỡ rối](#11-gỡ-rối) · [12. Quyền riêng tư và bảo mật](#12-quyền-riêng-tư-và-bảo-mật) · [13. Phát triển và kiểm thử](#13-phát-triển-và-kiểm-thử)

**Yêu cầu:** Home Assistant **2026.2 trở lên**; loa R1 cùng mạng LAN (IP tĩnh); ADB mạng của loa (cổng `5555`). Để chạy test hoặc build APK mới cần thêm Python 3.13, `node`, JDK 17 và Android SDK ([mục 13](#13-phát-triển-và-kiểm-thử)), người dùng bình thường **không cần**.

## 4. Kết nối WiFi cho loa mới hoặc vừa reset

Loa mới (hoặc vừa reset) chưa biết WiFi nhà: nó **tự phát WiFi `Phicomm_R1_XXXX`** khi chờ cấu hình. Tệp **`Trang kết nối WiFi cho loa R1.html`** (ở gốc kho) chạy **hoàn toàn offline** và gửi tên + mật khẩu WiFi nhà thẳng tới loa.

0. **Đưa loa vào chế độ chờ cấu hình** (làm một trong hai cách):
   - **Loa cần reset** (theo chủ kho): **rút điện** → **giữ nút nguồn** → vẫn giữ, **cắm điện** → khi đèn hiện **đen, trắng, hồng** thì **nhả tay**.
   - **Loa mới tinh**: cắm điện, **giữ nút trên loa 5–10 giây** cho đèn **nhấp nháy** và loa phát âm thanh.
1. Loa phát WiFi **`Phicomm_R1_XXXX`** (XXXX là mã riêng của loa): chờ tới khi thấy mạng này.
2. **Tải sẵn** tệp HTML về điện thoại/máy tính (vì sau khi nối WiFi của loa sẽ không có Internet).
3. Nối thiết bị vào WiFi **`Phicomm_R1_XXXX`**; tắt dữ liệu di động và VPN.
4. Mở tệp HTML **trực tiếp** trong trình duyệt → **Kiểm tra kết nối tới loa** (phải báo tới được `192.168.43.1:8989`).
5. Điền **tên WiFi**, **mật khẩu**, **loại mã hoá** (WPA/WPA2 hầu hết các nhà; WEP; hoặc không mật khẩu) → **Gửi cấu hình**.
6. Chờ **10–20 giây**: mạng `Phicomm_R1_XXXX` biến mất là loa đã nhận và đang vào WiFi nhà. Nối thiết bị lại WiFi nhà, tìm IP loa trong router, **đặt IP tĩnh**.

**Nhớ giữ nút trên loa 5–10 giây** cho đèn nhấp nháy rồi loa mới phát `Phicomm_R1_XXXX` (chỉ cắm điện thì loa đã có WiFi nhà không phát mạng này). Trình duyệt có thể chặn việc gửi: khi đó dùng **`python gui-wifi-r1.py "Tên WiFi" "Mật khẩu"`** (gửi đúng như chương trình *Bo Cai R1*, kiểu JSON) hoặc mục [1] của chương trình đó.

Chi tiết cách trang làm việc, bảng gỡ rối và lưu ý bảo mật: **[docs/KET-NOI-WIFI.md](docs/KET-NOI-WIFI.md)**. Chưa chạy lại bước này trên một loa vừa reset trong lúc viết tài liệu.

## 5. Đèn

Loa có **15 đèn đáy RGB** và **24 đèn viền chỉ trắng**. HA điều khiển bằng **hiệu ứng chạy ngay trên loa**: tích hợp nói **ADB** tới loa (qua adb-server nếu có, **không thì nối thẳng**, tự nhận diện) và chạy script `r1den.sh` ghi thẳng vào đèn.
Không cần APK, không cần máy chủ quyền shell, **không bắt buộc có adb-server**.

* **Đèn viền (chỉ trắng):** `sang` (sáng liên tục: độ sáng), `chay_duoi` (chạy đuổi 24 đèn: độ sáng, tốc độ, chiều, độ dài đuôi), `tho` (thở: độ sáng, tốc độ, độ sâu).
* **Đèn đáy:** `co_dinh`, `tho`, `nhap_nhay`, `nhip_tim`, `chop`, `phao_hoa`, `cau_vong` (12 sắc), `cau_vong_fw` (6 màu), `cau_vong_xoay` (mỗi đèn một màu), `sao_choi`.
  **Mỗi hiệu ứng có bộ thông số riêng** (màu, độ sáng, tốc độ, chiều...); cầu vồng, pháo hoa và sao chổi nhiều màu **không** bắt chọn màu.
* **Tám chức năng** (chờ, nghe, nghĩ, trả lời, đàm thoại, phát nhạc, lỗi, tắt mic): mỗi cái có bật/tắt và chọn hiệu ứng riêng cho đáy và viền.
* Thẻ **Cài đặt → Ánh sáng** có mục **Thử đèn riêng**: chọn vùng, hiệu ứng, thông số rồi bấm *Thử* (tự trả đèn về trạng thái thật sau vài giây, không lưu gì); trong từng cài đặt **không có nút Thử**.
* **Đèn ưu tiên số 1:** khi hai việc trùng nhau (đang áp đèn và đang đọc thông tin hệ thống), đèn đi trước (mục 7).
* Điều kiện: **adbd của loa chỉ phục vụ một kết nối TCP tại một thời điểm**; nếu client ADB khác đang giữ loa, dùng chế độ `server` với một adb-server duy nhất hoặc ngắt client kia.
  Tích hợp tự thử lại mỗi 15 giây khi mất ADB.

Chi tiết, danh mục thông số đầy đủ, dịch vụ, gỡ rối: **[docs/DEN-LED.md](docs/DEN-LED.md)**. **Đã xem bằng mắt trên loa thật** với bản nguyên mẫu của script: cả 13 hiệu ứng; bản cuối chạy sạch lỗi shell trên loa, **chưa xem lại bằng mắt từng thông số**.

## 6. Ứng dụng trên loa (cài từ HA)

Tích hợp mang sẵn 3 ứng dụng (`custom_components/r1_speaker/apk/`, danh sách `bo-cai.json`) và cài qua ADB ngay từ HA. Mỗi ứng dụng là một thực thể **Cập nhật** (bấm **Cài đặt**), hoặc gọi dịch vụ `r1_speaker.install_apps`.

| Mã | Gói | Là gì |
|---|---|---|
| `player` | `com.phicomm.speaker.player` | trình phát DLNA / AirPlay |
| `unisound` | `com.phicomm.speaker.device` | ứng dụng thiết bị của hãng (**có thể chiếm mic**, xem gỡ rối) |
| `bodam` | `vn.r1.bodam` | APK mic của tích hợp; cài xong HA **tự cấu hình** |

- Cài xong tích hợp tự **«Chuẩn bị loa»**: ẩn các ứng dụng gốc gây nhiễu (giống chương trình *Bo Cai R1*). Cũng có nút **«Chuẩn bị loa (ẩn ứng dụng gốc)»** nếu cần chạy riêng. Cài mà không ẩn thì loa chập chờn (cổng 8080 không trả lời, tự khởi động lại).
- Tệp được kiểm **sha256** trước khi đẩy; sai thì không đẩy gì.
- `INSTALL_FAILED_UPDATE_INCOMPATIBLE` (loa đang có bản ký khác): chỉ khi đặt `force: true` tích hợp mới gỡ bản cũ rồi cài lại.
- Nút **Khởi động lại loa** (`button.r1_khoi_dong_lai`) gửi lệnh `reboot` qua ADB; ADB hỏng hoặc đóng thì qua cổng 8080 (tin `shell`, như app AI box; đã thử khi ADB còn mở, chưa thử khi đã đóng).

Chi tiết: [docs/CAI-UNG-DUNG.md](docs/CAI-UNG-DUNG.md). Cài APK bằng tay (cách cũ, không cần nữa): [docs/CAI-APK.md](docs/CAI-APK.md).
**Đã kiểm trên loa thật:** cài đè APK mic 1.2, tự chạy sau khởi động lại, tự nối lại HA. **Chưa kiểm trên loa thật:** bấm «Cài đặt» cho `unisound` từ HA, và toàn bộ trình tự trên loa vừa reset.

## 7. Thông tin hệ thống của loa

Cảm biến (qua ADB, mỗi 60 giây, chỉ chạy khi có cảm biến bật): **CPU**, **RAM**, **bộ nhớ trong**, **sóng WiFi**, **thời gian chạy**, kèm tải, tần số và **tiến trình nặng nhất** ở thuộc tính.
**Đèn là ưu tiên số 1, đọc thông tin là số 2:** đang áp đèn thì việc đọc chờ (quá 8 giây thì bỏ lượt); đang có hiệu ứng đèn lặp chạy thì đọc **nhẹ** (không `top`, không `dumpsys wifi`) và **thưa** (5 phút).
Loa R1 không có cảm biến nhiệt và không có pin. Chi tiết: [docs/THONG-TIN-HE-THONG.md](docs/THONG-TIN-HE-THONG.md).

## 8. Nút giữa

- Mã phím nút giữa trên loa là **195** (`0x00c3`), **đã đo thật** (thiết bị `/dev/input/event0`, `rk29-keypad`, có đủ sự kiện nhấn và nhả). APK NV245 đặt
  sẵn mặc định 195.
- **Nhấn đơn** = bật/tắt mic (quyết định sau khoảng chờ nhấn đôi, mặc định 500 ms). **Nhấn đôi** trong khoảng đó = bật/tắt Bluetooth. Nhấn giữ lâu
  được tính là một nhấn đơn. Mã phím khác 195 không làm gì. Logic này đã kiểm bằng test Java thuần (đồng hồ giả), **chưa kiểm trên loa thật**.
- **Giới hạn quan trọng:** mặc định APK chỉ nhận phím qua `Activity.dispatchKeyEvent` của màn hình chính, nghĩa là **chỉ khi app đang ở tiền cảnh**.
  Muốn nhận nút giữa khi app chạy nền, APK có dịch vụ trợ năng `TiepCanPhim` (**mặc định TẮT**, chỉ phản ứng đúng mã phím đã cấu hình); bật nó là quyết định của bạn
  và **chưa kiểm trên loa thật**.
- Nếu nút giữa trên loa của bạn không phải 195: dùng nút *Dò mã phím* trong app (ghi logcat tag `NV243Phim` và hiện mã trên màn hình), rồi điền mã thập phân vào ô *Keycode nút giữa*. Đặt `-1` = tắt xử lý nút.

## 9. Nối mic loa về HA

Đường mic: **APK trên loa nối VÀO HA** (loa là máy khách TCP, HA là máy chủ, loa không mở cổng nghe).

1. Trong HA: Cấu hình tích hợp → đặt **Máy chủ mic = IP của loa** (đây là IP duy nhất được phép nối vào), **Khoá luồng mic** = một chuỗi dài ngẫu
   nhiên do bạn tự đặt, **Cổng nghe mic** (mặc định `18765`, chưa đo). Đầu nhận chỉ mở khi đã đặt cả khoá lẫn IP loa.
2. Trong APK: *Host HA* = IP của HA, *Port* = cổng nghe mic ở trên, *Khoá* = đúng chuỗi trên.
3. Giao thức (4 byte độ dài big-endian + nội dung; khung `hello` có khoá → PCM16 mono 16 kHz → khung `end`): `docs/HOP-DONG-PHIA-LOA.md` mục 2b.
4. Trạng thái nhìn ở `sensor.r1_trang_thai_mic`: `tat` / `nghe` (cổng mở, chưa có tiếng) / `gui` (đang nhận tiếng).
5. `switch.r1_tat_mic` bật: HA **đóng kết nối** của loa và từ chối nối lại cho tới khi tắt công tắc (có test).

## 10. Từ đánh thức và chỉnh mic

* Từ đánh thức do **HA dò** (pipeline Assist) trong luồng mic chảy liên tục; mô hình hiện dùng là `okay_nabu` (openWakeWord, ngưỡng 0,35 theo cấu hình của chủ kho).
* Mức tiếng mic thô của loa khá nhỏ (nền ≈ −56 dBFS, giọng nói ≈ −45…−30 dBFS). Nên đặt **«Tăng mic» khoảng 18 dB** và bật **hạn đỉnh**.
* **Đừng bật AGC với mặc định hiện tại:** ngưỡng «im lặng» của AGC (−55 dBFS) so với mức tiếng SAU khi đã cộng «Tăng mic», nền ồn sau khuếch đại cao hơn ngưỡng nên AGC khuếch đại cả nền ồn (đo thật: nền từ −45 lên −31 dBFS) và từ đánh thức không nhận.
* Đếm số lần từ đánh thức được nhận khi gọi 10 lần từ cùng chỗ là cách kiểm đơn giản nhất sau mỗi lần chỉnh. Từ đánh thức chạy trên loa **chưa có**.

## 11. Gỡ rối

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mọi thứ qua ADB lỗi, thẻ báo *adbd của loa không trả lời (đang bận…)* | adbd chỉ nhận một kết nối; adb-server hoặc máy tính của bạn đang giữ loa | `adb disconnect <IP-loa>:5555` trên máy kia, hoặc dùng `adb_mode: server` với một adb-server duy nhất |
| `adb-server: device offline` | server giữ kết nối hỏng tới loa | tích hợp tự ngắt và nối lại; nếu vẫn lỗi, khởi động lại adb-server |
| Đèn không sáng sau khi bấm | ADB lỗi, loa mất mạng | xem `binary_sensor.r1_dich_vu_den` (thuộc tính `loi`); tự thử lại sau 15 giây |
| Lưu tuỳ chọn mà tích hợp báo «đã dỡ tải» | (đã sửa ở 0.3.7) vòng nghe của Assist không dừng | cập nhật tích hợp; nếu còn, khởi động lại HA và báo kèm log |
| APK không nối về HA sau khi cài | APK đã cài nhưng chưa được cấu hình/mở lần đầu (ứng dụng ở trạng thái *stopped* không nhận lệnh khởi động) | bộ cài tự chạy lệnh cấu hình; nếu bạn cài tay, chạy lệnh ở thẻ → Cài đặt → Kết nối |
| «Ghép lại APK» không có tác dụng | (đã sửa ở 0.3.6) khoá mới không vào máy chủ nghe mic | cập nhật tích hợp |
| Từ đánh thức không nhận | AGC bật, hoặc mic nhỏ | mục 10 |
| Mic về HA bị tranh sau khi cài `unisound` | ứng dụng thiết bị của hãng chiếm mic | gỡ `com.phicomm.speaker.device` rồi khởi động lại loa |
| Lệnh `pm` trần bị chặn khi gõ tay | trên loa phải dùng đường dẫn đầy đủ | `/system/bin/pm …` |

## 12. Quyền riêng tư và bảo mật

- **APK tự chạy lại sau khi loa khởi động lại và TỰ BẬT mic nếu đã được cấu hình** (host HA, cổng, khoá): có receiver khởi động (`BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`; không exported, chỉ hệ thống gọi được).
  Đây là chủ ý để loa nối về HA ngay sau reboot, nhưng nghĩa là **mic loa chảy về HA liên tục khi loa lên**; HA từ chối khi `switch.r1_tat_mic` bật. Chưa cấu hình thì APK không làm gì.
  APK không ghi âm ra bộ nhớ hay log, không có wake-word. Tắt là dừng ghi, gửi khung `end` và đóng kết nối.
- **Báo hiệu khi đang gửi:** APK chạy dịch vụ tiền cảnh với thông báo «Đang gửi mic về Home Assistant»; trong HA, `sensor.r1_trang_thai_mic` hiện `gui`.
  **Nhưng:** loa không có màn hình nên thông báo gần như không ai thấy, và đèn báo chạy qua ADB (mục 5; màu CHƯA xác nhận bằng mắt). Đừng coi hai thứ này
  là chỉ báo đủ cho người đứng cạnh loa.
- Tắt mic bằng `switch.r1_tat_mic` trong HA đóng kết nối của loa (mục 9).
- **Đường truyền không mã hoá**: khoá và tiếng đi qua TCP trơn trong LAN. Chỉ dùng trong mạng tin cậy; đầu nhận lọc theo IP loa và khoá nhưng IP có thể bị giả mạo trong LAN.
- **Khoá nằm dạng chữ thường trong SharedPreferences của app** (`allowBackup=false`, dữ liệu riêng của app).
- **Bản kiểm thử (`apk/nguon`, biến thể kiemthu) có receiver exported** (`KIEM_MIC`, `KIEM_DEN_NHAC`): bất kỳ app nào trên loa gửi được lệnh bật mic tới
  host bất kỳ. **Bản phát hành `custom_components/r1_speaker/apk/vn-r1-bodam.apk` (bản sao ở `apk/`) không có chúng**, và cửa cấu hình bằng intent của `ManHinhChinh` chỉ nhận khi app CHƯA cấu hình.
- Đừng đặt loa ở nơi người ngoài ra lệnh được cho nhà (mic + từ đánh thức); đừng dán URL bộ đàm (chứa khoá) ra ngoài.

Bộ cài ứng dụng và đèn chạy qua **ADB, không mã hoá và không xác thực** (loa `ro.adb.secure=0`): **bất kỳ máy nào trong mạng LAN nối được cổng 5555 đều chạy được lệnh shell trên loa.**
Chỉ dùng trong mạng tin cậy, **không mở cổng 5555 ra Internet**; nếu dùng adb-server dạng container, chỉ mở nó ở `127.0.0.1` của máy HA. Phía tích hợp, lệnh gửi lên loa luôn có dạng cố định
(script `r1den.sh` với tham số đã lọc; `pm install`/`pm uninstall` với tên gói và tệp trong danh sách; `reboot`), không có đường nào cho chuỗi tuỳ ý vào shell của loa.
**Nên khoá cổng 5555 chỉ cho Home Assistant** (botnet nhắm cổng ADB không xác thực của TV box đã lây qua đường này; kho này đo thấy loa có `ro.debuggable=1`
nên `adb root` nhiều khả năng chạy được, tức là cổng mở có thể là quyền root; chưa thử). Ở router/tường lửa: cho phép `<IP-HA>` → `<IP-loa>:5555`, chặn mọi nguồn khác
tới cổng đó. Ví dụ RouterOS: `/ip firewall filter add chain=forward action=accept protocol=tcp src-address=<IP-HA> dst-address=<IP-loa> dst-port=5555 place-before=0`
rồi `add chain=forward action=drop protocol=tcp dst-address=<IP-loa> dst-port=5555 place-before=1`. Nếu loa và HA cùng một bridge/VLAN thì gói không đi qua
firewall của router: bật `use-ip-firewall` của bridge hoặc đặt loa ở VLAN IoT riêng. Kiểm bằng `nc -zv <IP-loa> 5555` từ một máy khác (phải bị chặn) và
xem đèn vẫn điều khiển được từ HA. Đèn tự do, khởi động lại, trạng thái Bluetooth và cài ứng dụng còn phụ thuộc ADB nên chưa tắt hẳn ADB được.
Trang kết nối WiFi gửi mật khẩu WiFi qua HTTP thường tới loa trong mạng riêng của loa: làm bước này ở nhà.

## 13. Phát triển và kiểm thử

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
python -m pytest tests -q           # toàn bộ test tích hợp
bandit -q -r custom_components      # phân tích bảo mật tĩnh
```

Tài liệu cho người phát triển (trạng thái đã kiểm, cấu trúc kho, việc còn thiếu): [docs/PHAT-TRIEN.md](docs/PHAT-TRIEN.md). Cấu trúc chính: `den.py`/`den_hieu_ung.py`/`den_adb.py`/`r1den.sh` (đèn),
`adb_client.py` (máy khách ADB tự viết, hai đường), `cai_ung_dung.py` + `apk/` (bộ cài), `he_thong.py` (cảm biến hệ thống), `mic_server.py` (đầu nhận mic từ APK), `www/` (thẻ).
