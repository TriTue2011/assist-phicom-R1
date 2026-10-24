# assist-phicom-R1 — loa Phicomm R1 trong Home Assistant

Kho này biến loa **Phicomm R1** thành một thiết bị đầy đủ của Home Assistant (HA), gồm hai phần chạy cùng nhau:

1. **Tích hợp HA `r1_speaker`** (`custom_components/r1_speaker/`): EQ, âm lượng, DLNA/AirPlay; phát tiếng của HA (TTS, nhạc) ra loa; vệ tinh Assist với từ đánh thức;
   bộ đàm; **đèn LED** (13 hiệu ứng, mỗi hiệu ứng có thông số riêng, mục Thử riêng); **cài ứng dụng lên loa qua ADB** (kể cả loa mới tinh); nút khởi động lại loa;
   cảm biến CPU/RAM/bộ nhớ/WiFi của loa; thẻ Lovelace `r1-card` (đàm thoại, EQ, cài đặt); icon riêng (`brand/`; HA có hỗ trợ thư mục này tự nạp, đã thấy trong 2026.10.3, bản cũ hơn chưa kiểm).
2. **APK `vn.r1.bodam`** (`apk/`): ứng dụng Android nhỏ trên loa, lấy tiếng mic gửi về HA **chỉ khi người dùng bật**; nút giữa bật/tắt mic.

> **Đọc trước khi làm theo.** Đây là dự án thử nghiệm. Phần lớn mã được kiểm bằng loa giả trên máy phát triển; các điểm đã kiểm trên **loa thật** và điểm **chưa kiểm** được ghi rõ ở từng mục và ở
> [docs/PHAT-TRIEN.md](docs/PHAT-TRIEN.md). Cài ứng dụng lên loa và dùng ADB là việc **khó đảo ngược** với thiết bị của bạn: đọc phần *Quyền riêng tư và bảo mật* trước.

**Giấy phép: CHỦ KHO CHỌN GIẤY PHÉP.** Kho chưa có tệp `LICENSE`; chủ kho phải chọn giấy phép trước khi công khai hoặc phân phối.

## Mục lục

1. [Yêu cầu](#1-yêu-cầu) · 2. [**Loa mới tinh: từ đầu đến dùng được**](#2-loa-mới-tinh-từ-đầu-đến-dùng-được) · 3. [Cài tích hợp HA](#3-cài-tích-hợp-ha) ·
4. [Kết nối WiFi cho loa](#4-kết-nối-wifi-cho-loa-mới-hoặc-vừa-reset) · 5. [Đèn](#5-đèn) · 6. [Ứng dụng trên loa](#6-ứng-dụng-trên-loa-cài-qua-adb) ·
7. [Thông tin hệ thống](#7-thông-tin-hệ-thống-của-loa) · 8. [Nút giữa](#8-nút-giữa) · 9. [Mic về HA](#9-nối-mic-loa-về-ha) · 10. [Từ đánh thức](#10-từ-đánh-thức-và-chỉnh-mic) ·
11. [Gỡ rối](#11-gỡ-rối) · 12. [Quyền riêng tư và bảo mật](#12-quyền-riêng-tư-và-bảo-mật) · 13. [Phát triển và kiểm thử](#13-phát-triển-và-kiểm-thử)

## 1. Yêu cầu

| Thứ | Ghi chú |
|---|---|
| Home Assistant **2026.2 trở lên** | thử trên **2026.2.3**; `hacs.json` ghi tối thiểu 2026.2.0. Chưa thử bản cũ hơn. |
| Loa Phicomm R1 cùng mạng LAN với HA | đặt **IP tĩnh hoặc giữ chỗ DHCP** cho loa. Cổng điều khiển/EQ mặc định **8080**. |
| **ADB tới loa** (cổng mạng `5555` của loa) | **đèn, cài ứng dụng, đọc thông tin và khởi động lại đều đi qua ADB.** Tích hợp tự nói ADB: dùng `adb-server` nếu có, **không có thì nối thẳng loa** (tự nhận diện). Không cần cài `adb` trên máy bạn. |
| `adb` (Android platform-tools) trên máy bạn | chỉ cần nếu muốn cài APK bằng tay hoặc gỡ rối ngoài HA. |

**Chỉ cần để kiểm thử hoặc tự build lại APK (không cần để dùng):** Python **3.13** và `requirements-test.txt` (chạy test và `bandit`), `chromium` hoặc `google-chrome` (test thẻ trong trình duyệt không đầu), `node`, JDK **17** + Android SDK **platform 22** + **build-tools 30.0.3** (build APK).

## 2. Loa mới tinh: từ đầu đến dùng được

Trình tự cho loa **mới hoặc vừa reset**:

1. **Kết nối WiFi cho loa** bằng tệp `Trang kết nối WiFi cho loa R1.html` (mục 4, chi tiết ở [docs/KET-NOI-WIFI.md](docs/KET-NOI-WIFI.md)). Xong, tìm **IP của loa** trong router và đặt IP tĩnh/giữ chỗ DHCP.
2. **Cài tích hợp trong HA** (HACS hoặc chép thư mục, mục 3) rồi **thêm loa** với IP đó.
3. **Cài ứng dụng lên loa** ngay từ HA (không cần máy tính): vào thiết bị **Phicomm R1** → các thực thể **«Ứng dụng: …»** → bấm **Cài đặt**, hoặc gọi dịch vụ `r1_speaker.install_apps`
   (mục 6, [docs/CAI-UNG-DUNG.md](docs/CAI-UNG-DUNG.md)). APK mic `vn.r1.bodam` cài xong **được HA tự cấu hình** (host HA, cổng, khoá nghe mic); không cần chạy lệnh nào.
4. Bấm nút **Khởi động lại loa** một lần (để các ứng dụng hệ thống nạp bản mới). Sau khoảng nửa phút `sensor.r1_trang_thai_mic` phải lên `nghe`/`gui` (APK đã nối về HA).
5. Mở thẻ `r1-card` → **Cài đặt → Ánh sáng**: dùng mục **Thử đèn** để thử hiệu ứng, rồi chỉnh đèn theo từng chức năng (mục 5).
6. Chọn pipeline Assist cho loa (thực thể **Trợ lý**), nói từ đánh thức (mục 10).

**Điều kiện và điều CHƯA kiểm với loa mới tinh:** cả bước 3 lẫn đèn cần **cổng ADB mạng `5555` của loa mở**. Trên loa của chủ kho cổng này mở sẵn và còn sau khi khởi động lại; **chưa kiểm trên một loa vừa reset**.
Nếu cổng đóng, tích hợp báo lỗi ADB rõ ràng và không làm gì; khi đó bật ADB mạng theo cách của chương trình *Bo Cai R1* (xem `ghep-bo-cai-r1.bat`) rồi thử lại.

## 3. Cài tích hợp HA

**Qua HACS (khuyến nghị):** thêm kho này làm *Custom repository* (loại *Integration*), cài **Phicomm R1 Speaker**, khởi động lại HA.
**Bằng tay:** chép thư mục `custom_components/r1_speaker` vào `<thư mục cấu hình HA>/custom_components/` (giữ nguyên `www/`, `translations/`, `apk/`), khởi động lại HA.

Sau đó: Cài đặt → Thiết bị & dịch vụ → **Thêm tích hợp** → **Phicomm R1 Speaker**:

- **Địa chỉ IP của loa** (không có giá trị mặc định; ví dụ `192.0.2.10` là địa chỉ ví dụ);
- **Cổng điều khiển/EQ**: mặc định `8080`.

Khoá và cổng nghe mic **do HA tự cấp** cho từng loa. Muốn thêm loa thứ hai: thêm tích hợp lần nữa với IP khác.

**Loa mới reset:** nếu cổng điều khiển 8080 chưa có nhưng ADB (5555) trả lời, bước thêm tích hợp vẫn cho thêm («Loa chưa có dịch vụ điều khiển»); sau đó vào thiết bị «Phicomm R1» → «Ứng dụng: …» → Cài đặt để cài ứng dụng qua ADB, điều khiển và EQ tự hiện khi loa có dịch vụ này.

**Tuỳ chọn** (Cấu hình tích hợp): IP/cổng loa; `ha_url` (địa chỉ HA mà loa gọi tới, dạng `http://<IP của HA>:8123`); **`adb_server`** (mặc định để trống = nối thẳng tới IP của loa, cổng 5555; chỉ điền khi thật sự có adb-server) và **`adb_mode`**
(`auto` tự nhận diện, `server` chỉ qua adb-server, `direct` nối thẳng loa); *Ghép lại APK* (sinh khoá mới); thông số nâng cao (bộ đàm, khử tạp, song công).
Từng cài đặt giải thích ở [docs/CAI-DAT-CHI-TIET.md](docs/CAI-DAT-CHI-TIET.md); cài đặt cụ thể và gỡ rối xem [docs/HUONG-DAN-CAI-DAT.md](docs/HUONG-DAN-CAI-DAT.md).

**Kiểm nhanh:** có thiết bị **Phicomm R1** với 5 thực thể EQ, `number.phicomm_r1_volume`, `media_player.r1_loa`, `assist_satellite.r1`, `sensor.r1_trang_thai_mic`, các cảm biến hệ thống,
nút **Khởi động lại loa** và các thực thể **Ứng dụng**. Thẻ: tích hợp **tự đăng ký** tài nguyên; chỉ cần thêm thẻ `type: custom:r1-card` (3 tab Đàm thoại / EQ / Cài đặt).
Phát tiếng ra loa (TTS/nhạc) cần thêm tích hợp **DLNA Digital Media Renderer** của HA cho loa: xem [docs/PHAT-RA-LOA.md](docs/PHAT-RA-LOA.md).

## 4. Kết nối WiFi cho loa mới hoặc vừa reset

Loa mới (hoặc vừa reset) chưa biết WiFi nhà: nó **tự phát WiFi `Phicomm_R1_XXXX`** khi chờ cấu hình. Tệp **`Trang kết nối WiFi cho loa R1.html`** (ở gốc kho) chạy **hoàn toàn offline** và gửi tên + mật khẩu WiFi nhà thẳng tới loa.

1. Cắm điện loa, chờ đèn **nhấp nháy**.
2. **Tải sẵn** tệp HTML về điện thoại/máy tính (vì sau khi nối WiFi của loa sẽ không có Internet).
3. Nối thiết bị vào WiFi **`Phicomm_R1_XXXX`**; tắt dữ liệu di động và VPN.
4. Mở tệp HTML **trực tiếp** trong trình duyệt → **Kiểm tra kết nối tới loa** (phải báo tới được `192.168.43.1:8989`).
5. Điền **tên WiFi**, **mật khẩu**, **loại mã hoá** (WPA/WPA2 hầu hết các nhà; WEP; hoặc không mật khẩu) → **Gửi cấu hình**.
6. Chờ **10–20 giây**: mạng `Phicomm_R1_XXXX` biến mất là loa đã nhận và đang vào WiFi nhà. Nối thiết bị lại WiFi nhà, tìm IP loa trong router, **đặt IP tĩnh**.

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

## 6. Ứng dụng trên loa (cài qua ADB)

Tích hợp mang theo các ứng dụng cần cho loa và **tự cài qua ADB** (`custom_components/r1_speaker/apk/`, danh sách `bo-cai.json`):

| Mã | Gói | Phiên bản | Là gì |
|---|---|---|---|
| `player` | `com.phicomm.speaker.player` | 0.2.5 | trình phát DLNA / AirPlay (bản cập nhật của EchoService) |
| `unisound` | `com.phicomm.speaker.device` | 25.3.1 | ứng dụng thiết bị của hãng (**có thể chiếm mic**, xem gỡ rối) |
| `bodam` | `vn.r1.bodam` | 1.2 | APK mic của tích hợp; cài xong HA **tự cấu hình** |

* Mỗi ứng dụng là một thực thể **Cập nhật**. Chỉ **APK mic bộ đàm** có nút **Cài đặt**; **`player` (autodlna.apk) và `unisound`** ghi đè ứng dụng HỆ THỐNG của hãng nên **không** nằm trong «cài mặc định» và không có nút cài một chạm: loa vừa reset đã hỏng sau khi cài chúng (24/10/2026, chưa rõ cái nào). Muốn cài thì gọi `install_apps` với `apps: [player]` (hoặc `[unisound]`), từng cái một, khởi động lại loa rồi kiểm cổng 8080 (xem `docs/CAI-UNG-DUNG.md`). Hoặc dịch vụ `r1_speaker.install_apps` (cài nhiều cái một lượt, theo thứ tự, trả kết quả từng cái).
* Tệp lớn được **chia phần** (GitHub giới hạn 25 MB khi tải lên) và **kiểm sha256** trước khi đẩy; sai thì không đẩy gì.
* `INSTALL_FAILED_UPDATE_INCOMPATIBLE` (loa đang có bản cùng gói ký khác): chỉ khi bạn đặt `force: true` tích hợp mới gỡ bản cũ rồi cài lại.
* **Nút Khởi động lại loa** (`button.r1_khoi_dong_lai`) gửi lệnh `reboot` qua ADB.

Chi tiết và gỡ rối: **[docs/CAI-UNG-DUNG.md](docs/CAI-UNG-DUNG.md)**. Cài APK `vn.r1.bodam` **bằng tay** (cách cũ, khi không dùng bộ cài): `adb install`, xem [docs/CAI-APK.md](docs/CAI-APK.md).
**Đã kiểm trên loa thật:** cài đè APK mic 1.2, tự chạy sau khởi động lại loa, tự nối lại HA. **Chưa kiểm trên loa thật:** bấm «Cài đặt» cho `unisound` từ HA, toàn bộ trình tự trên loa mới tinh.
**Gói bị ẩn:** trên loa của chủ kho, `com.phicomm.speaker.device` **đã có** (ứng dụng hệ thống `/system/app/Unisound` V3.1.6.2, kèm bản cập nhật V3.2.5.2 trong `/data`, đang bị **ẩn**; `pm path` trả rỗng với gói ẩn).
Bộ dò đọc bản ghi `dumpsys package` nên thực thể «Ứng dụng: Thiết bị và giọng nói» hiện **«V3.2.5.2- (đang ẩn)»** và **không mời cập nhật**. Số phiên bản `25.3.1` trong `bo-cai.json` chưa được đối chiếu với tệp.
Tệp `autodlna.apk` đi kèm trùng từng byte với `base.apk` của trình phát đang chạy trên loa của chủ kho, nên thực thể trình phát hiện đúng «Mới nhất».

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
