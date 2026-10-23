# assist-phicom-R1 — loa Phicomm R1 trong Home Assistant

Kho này gồm hai phần chạy cùng nhau để biến loa **Phicomm R1** thành một thiết bị của Home Assistant (HA):

1. **Tích hợp HA `r1_speaker`** (`custom_components/r1_speaker/`): chỉnh EQ, âm lượng, DLNA/AirPlay của loa; phát tiếng của HA
   (TTS, nhạc) ra loa; vệ tinh Assist; bộ đàm; cài đặt đèn; một thẻ Lovelace `r1-card` (đàm thoại, EQ, cài đặt).
2. **APK `vn.r1.bodam`** (`apk/`): ứng dụng Android nhỏ cài lên loa, lấy tiếng từ micro của loa gửi về HA, **chỉ khi người dùng bật**.
   Nút giữa của loa bật/tắt mic (nhấn đôi bật/tắt Bluetooth).

> **Đọc trước khi làm theo.** Đây là dự án thử nghiệm. Phần lớn mã đã được kiểm bằng **loa giả** (mock) trên máy phát triển; chỉ
> một số điểm được kiểm trên loa thật. Phần đã kiểm trên loa thật nằm trong [docs/PHAT-TRIEN.md](docs/PHAT-TRIEN.md); không hứa hơn những gì đã đo. Cài APK lên loa là việc **khó đảo và chạm vào phần mềm gốc của loa**: chỉ làm khi bạn chủ động quyết định.

**Giấy phép: CHỦ MÁY CHỌN GIẤY PHÉP.** Kho chưa có tệp `LICENSE`; chủ kho phải chọn giấy phép trước khi công khai/phân phối.

## Mục lục

1. [Yêu cầu](#1-yêu-cầu-phần-mềm) · 2. [Cài tích hợp HA](#2-cài-tích-hợp-ha) · 3. [Cài APK lên loa](#3-cài-apk-lên-loa-chỉ-khi-bạn-đã-quyết-định) ·
4. [Nút giữa](#4-nút-giữa) · 5. [Đèn](#5-đèn) · 6. [Cấu hình mic về HA](#6-nối-mic-loa-về-ha) · 7. [Quyền riêng tư](#7-quyền-riêng-tư)

Dành cho người phát triển (trạng thái đã kiểm, chạy test, cấu trúc kho, việc còn thiếu): [docs/PHAT-TRIEN.md](docs/PHAT-TRIEN.md).

## 1. Yêu cầu phần mềm

**Bắt buộc để dùng:**

| Thứ | Ghi chú |
|---|---|
| Home Assistant **2026.2 trở lên** | bản thử nghiệm là **2026.2.3**; `hacs.json` ghi tối thiểu 2026.2.0. Chưa thử bản cũ hơn. |
| Loa Phicomm R1 cùng mạng LAN với HA | nên đặt IP tĩnh/giữ chỗ DHCP cho loa. Cổng điều khiển/EQ mặc định **8080**. |
| ADB tới loa (cổng `5555`) | **đèn chạy qua ADB**: custom tự nối thẳng loa, hoặc dùng `adb-server` (`127.0.0.1:5037`) nếu có. Cần `adb` trên máy bạn chỉ khi cài APK lần đầu. |

**Chỉ cần để kiểm thử hoặc tự build lại APK (không cần để dùng):**

| Thứ | Dùng để |
|---|---|
| Python **3.13** + các gói trong `requirements-test.txt` | chạy test của tích hợp và `bandit`. Gồm `pytest-homeassistant-custom-component==0.13.316` (kéo theo HA 2026.2.3), `ha-ffmpeg`, `hassil`, `home-assistant-intents`, `mutagen`, `async-upnp-client`, `getmac`, `pymicro-vad`, `pyspeex-noise`, `bandit`. |
| `chromium` hoặc `google-chrome` | test thẻ trong trình duyệt không đầu (`tests/test_the_chrome.py`); không có thì test tự bỏ qua. |
| `node` | một số test mô hình thẻ (`tests/test_the_dam_thoai.py`); không có thì tự bỏ qua. |
| JDK **17**, Android SDK **platform 22** (android-22) và **build-tools 30.0.3** | chỉ để tự build lại APK từ mã nguồn (`aapt`, `javac -source 8`, `d8`, `zipalign`, `apksigner`). **Mã nguồn APK chưa nằm trong kho này** (xem mục 11). |

## 2. Cài tích hợp HA

1. Chép thư mục `custom_components/r1_speaker` của kho này vào `<thư mục cấu hình HA>/custom_components/` (ví dụ
   `/config/custom_components/r1_speaker`). Giữ nguyên các thư mục con `www/` (thẻ) và `translations/`.
2. **Khởi động lại Home Assistant.**
3. Cài đặt → Thiết bị & dịch vụ → **Thêm tích hợp** → **Phicomm R1 Speaker**. Điền:
   - **Địa chỉ IP của loa** — *không có giá trị mặc định* (ô để trống); tự điền IP loa của bạn, ví dụ `192.0.2.10` (địa chỉ ví dụ);
   - **Cổng điều khiển/EQ** — mặc định `8080`.
4. Khoá và cổng nghe mic **do HA tự cấp** cho từng loa, không phải nhập. Muốn thêm loa thứ hai: thêm tích hợp
   lần nữa với IP khác. Tuỳ chọn đổi sau ở *Cấu hình*: IP/cổng loa, `ha_url` (địa chỉ HA mà loa/go2rtc gọi tới, dạng
   `http://<IP của HA>:8123`), và «thông số nâng cao» (ngưỡng bộ đàm, khử tạp, song công). Lệnh cài APK đã kèm khoá
   hiện ở thẻ → Cài đặt → Kết nối (quản trị viên). Chi tiết: `docs/HUONG-DAN-CAI-DAT.md`; **từng cài đặt giải thích riêng ở `docs/CAI-DAT-CHI-TIET.md`**.

**Kiểm nhanh:**

- Nếu báo «Không đọc được loa»: sai IP/cổng, hoặc cổng 8080 bị chặn. Tích hợp thử bằng một lần `get_info` khi bạn bấm Gửi.
- Sau khi thêm: có thiết bị **Phicomm R1** với 5 thực thể EQ (`number.phicomm_r1_eq_60_hz` … `_14_khz`), `number.phicomm_r1_volume`,
  `media_player.r1_loa`, `assist_satellite.r1`, `sensor.r1_trang_thai_mic`…
- Kéo thử một dải EQ: lệnh ghi dải EQ đã được xác nhận trên loa thật; các lệnh khác xem `docs/PHAT-TRIEN.md`.
- Thẻ: tích hợp **tự đăng ký** tài nguyên `/r1_speaker/r1-card.js`; chỉ cần thêm thẻ `type: custom:r1-card`
  (thẻ gộp, 3 tab Đàm thoại / EQ / Cài đặt; tên loa và hàng tab luôn hiện, nội dung đóng sẵn). Chi tiết: `docs/HUONG-DAN-CAI-DAT.md` mục 2.
- Phát tiếng ra loa (TTS/nhạc) cần thêm tích hợp **DLNA Digital Media Renderer** của HA cho loa — xem `docs/PHAT-RA-LOA.md`.

## 3. Cài APK lên loa (chỉ khi bạn đã quyết định)

APK: `apk/vn-r1-bodam.apk` (gói `vn.r1.bodam`, versionName 1.1, minSdk/targetSdk 22, ký bằng khoá debug),
dựng từ mã nguồn trong `apk/nguon/` (xem `apk/nguon/README-BUILD.md`). Đây là **bản phát hành**: không có
receiver kiểm thử.

**Đã chạy trên loa thật (22/10/2026):** mic về HA, tự nối lại khi HA khởi động lại, phát tiếng từ HA xuống loa
qua cùng kết nối, đèn theo nhạc của firmware (độ sáng/sắc độ/bật tắt), lệnh đổi cấu hình giả bị bỏ qua khi đã
cấu hình. **Chưa kiểm:** tự bật mic sau khi loa khởi động lại (cần khởi động lại loa để chứng minh).

**Đọc cảnh báo trước:**

- **Mic tự bật khi loa khởi động** nếu app đã cấu hình (host + port + khoá), và luôn gửi về HA đã cấu hình khi đang chạy.
  HA từ chối kết nối khi bạn tắt mic (`switch.r1_tat_mic`), nhưng loa vẫn thử nối lại mỗi 2–30 giây (mỗi lần
  chỉ mở mic rất ngắn, tiếng bị bỏ ở phía HA).
- Shell trên loa là `uid=2000` (không root, không `su`).

Các bước (chạy trên máy tính cùng mạng với loa; cần ADB qua mạng của loa đang mở — xem `docs/CAI-APK.md`).
Thay `<IP-loa>` bằng IP loa của bạn:

```bash
adb connect <IP-loa>:5555
adb -s <IP-loa>:5555 push apk/vn-r1-bodam.apk /data/local/tmp/
adb -s <IP-loa>:5555 shell /system/bin/pm install -r /data/local/tmp/vn-r1-bodam.apk
```

**Cấu hình lần đầu và bật mic làm qua tích hợp**: mở thẻ R1 → Cài đặt → Kết nối → «Hiện lệnh cài APK» (chỉ quản trị viên). Thẻ tạo sẵn MỘT lệnh đã điền IP HA, cổng và khoá; bạn chỉ copy và chạy, không tự gõ host/khoá.

Dùng đường dẫn đầy đủ `/system/bin/pm` (lệnh `pm` trần bị chặn trên loa). Muốn đổi cấu hình về sau: `adb -s <IP-loa>:5555 shell /system/bin/pm clear vn.r1.bodam` rồi chạy lại lệnh do thẻ hiển thị; app đã cấu hình thì bỏ qua lệnh đổi từ bên ngoài, để app khác trên loa không đổi được đích tiếng mic.

**Gỡ / hoàn tác:**

```bash
adb -s <IP-loa>:5555 shell /system/bin/pm uninstall vn.r1.bodam
```

Chi tiết từng bước và kiểm tra sau cài: `docs/CAI-APK.md`.

**Cấu hình APK** làm qua tích hợp (xem các bước ở trên): thẻ tạo sẵn lệnh có host, cổng và khoá; loa R1 không có màn hình nên không có ô nhập trên loa.

## 4. Nút giữa

- Mã phím nút giữa trên loa là **195** (`0x00c3`), **đã đo thật** (thiết bị `/dev/input/event0`, `rk29-keypad`, có đủ sự kiện nhấn và nhả). APK NV245 đặt
  sẵn mặc định 195.
- **Nhấn đơn** = bật/tắt mic (quyết định sau khoảng chờ nhấn đôi, mặc định 500 ms). **Nhấn đôi** trong khoảng đó = bật/tắt Bluetooth. Nhấn giữ lâu
  được tính là một nhấn đơn. Mã phím khác 195 không làm gì. Logic này đã kiểm bằng test Java thuần (đồng hồ giả), **chưa kiểm trên loa thật**.
- **Giới hạn quan trọng:** APK hiện chỉ nhận phím qua `Activity.dispatchKeyEvent` của màn hình chính, nghĩa là **chỉ khi app đang ở tiền cảnh**.
  Chưa có cách nhận nút giữa khi app chạy nền.
  phím* trong app (ghi logcat tag `NV243Phim` và hiện mã trên màn hình); (b) điền mã thập phân vào ô *Keycode nút giữa*. Đặt `-1` = tắt xử lý nút.

## 5. Đèn

Loa có **15 đèn đáy RGB** và **24 đèn viền chỉ trắng**. HA điều khiển bằng **hiệu ứng chạy ngay trên loa**: custom nói
**ADB** tới loa (qua adb-server nếu có, **không thì nối thẳng**, tự nhận diện) và chạy script `r1den.sh` ghi thẳng vào đèn.
Không cần APK, không cần máy chủ quyền shell, **không bắt buộc có adb-server**.

* **Đèn viền (chỉ trắng):** `sang` (sáng liên tục: độ sáng), `chay_duoi` (chạy đuổi 24 đèn: độ sáng, tốc độ, chiều, độ dài đuôi),
  `tho` (thở: độ sáng, tốc độ, độ sâu).
* **Đèn đáy:** `co_dinh`, `tho`, `nhap_nhay`, `nhip_tim`, `chop`, `phao_hoa`, `cau_vong` (12 sắc), `cau_vong_fw` (6 màu),
  `cau_vong_xoay` (mỗi đèn một màu), `sao_choi`. **Mỗi hiệu ứng có bộ thông số riêng** (màu, độ sáng, tốc độ, chiều...); cầu vồng,
  pháo hoa và sao chổi nhiều màu **không** bắt chọn màu.
* **Tám chức năng** (chờ, nghe, nghĩ, trả lời, đàm thoại, phát nhạc, lỗi, tắt mic) mỗi cái có bật/tắt và chọn hiệu ứng riêng cho
  đáy và viền. Trên thẻ **Cài đặt → Ánh sáng** có mục **Thử đèn** riêng: chọn vùng, hiệu ứng, thông số rồi bấm *Thử* (tự
  trả đèn về trạng thái thật sau vài giây, không lưu gì); trong từng cài đặt **không có nút Thử**.
* Điều kiện: **adbd của loa chỉ phục vụ một kết nối TCP tại một thời điểm**; nếu client ADB khác đang giữ loa, dùng chế độ `server`
  với một adb-server duy nhất hoặc ngắt client kia. Chi tiết, danh mục thông số, dịch vụ và gỡ rối: **[docs/DEN-LED.md](docs/DEN-LED.md)**;
  bảng cài đặt: [docs/CAI-DAT-CHI-TIET.md](docs/CAI-DAT-CHI-TIET.md) mục 5.

## 6. Nối mic loa về HA

Đường mic: **APK trên loa nối VÀO HA** (loa là máy khách TCP, HA là máy chủ, loa không mở cổng nghe).

1. Trong HA: Cấu hình tích hợp → đặt **Máy chủ mic = IP của loa** (đây là IP duy nhất được phép nối vào), **Khoá luồng mic** = một chuỗi dài ngẫu
   nhiên do bạn tự đặt, **Cổng nghe mic** (mặc định `18765`, chưa đo). Đầu nhận chỉ mở khi đã đặt cả khoá lẫn IP loa.
2. Trong APK: *Host HA* = IP của HA, *Port* = cổng nghe mic ở trên, *Khoá* = đúng chuỗi trên.
3. Giao thức (4 byte độ dài big-endian + nội dung; khung `hello` có khoá → PCM16 mono 16 kHz → khung `end`): `docs/HOP-DONG-PHIA-LOA.md` mục 2b.
4. Trạng thái nhìn ở `sensor.r1_trang_thai_mic`: `tat` / `nghe` (cổng mở, chưa có tiếng) / `gui` (đang nhận tiếng).
5. `switch.r1_tat_mic` bật: HA **đóng kết nối** của loa và từ chối nối lại cho tới khi tắt công tắc (có test).


## 7. Quyền riêng tư

- **Mic chỉ gửi khi được bật.** APK không ghi âm ra bộ nhớ hay log, không tự khởi động cùng máy (không có receiver khởi động), không có wake-word, chỉ ghi
  khi bạn bật bằng nút trên màn hình, nút giữa, hoặc lệnh kiểm thử. Tắt là dừng ghi, gửi khung `end` và đóng kết nối.
- **Báo hiệu khi đang gửi:** APK chạy dịch vụ tiền cảnh với thông báo «Đang gửi mic về Home Assistant»; trong HA, `sensor.r1_trang_thai_mic` hiện `gui`.
  **Nhưng:** loa không có màn hình nên thông báo gần như không ai thấy, và đèn báo chạy qua ADB (mục 5; màu CHƯA xác nhận bằng mắt). Đừng coi hai thứ này
  là chỉ báo đủ cho người đứng cạnh loa.
- Tắt mic bằng `switch.r1_tat_mic` trong HA đóng kết nối của loa (mục 6).
- **Đường truyền không mã hoá**: khoá và tiếng đi qua TCP trơn trong LAN. Chỉ dùng trong mạng tin cậy; đầu nhận lọc theo IP loa và khoá nhưng IP có thể bị giả mạo trong LAN.
- **Khoá nằm dạng chữ thường trong SharedPreferences của app** (`allowBackup=false`, dữ liệu riêng của app).
- **Bản kiểm thử (`apk/nguon`, biến thể kiemthu) có receiver exported** (`KIEM_MIC`, `KIEM_DEN_NHAC`): bất kỳ app nào trên loa gửi được lệnh bật mic tới
  host bất kỳ. **Bản phát hành `apk/vn-r1-bodam.apk` không có chúng**, và cửa cấu hình bằng intent của `ManHinhChinh` chỉ nhận khi app CHƯA cấu hình.
- Đừng đặt loa ở nơi người ngoài ra lệnh được cho nhà (mic + từ đánh thức); đừng dán URL bộ đàm (chứa khoá) ra ngoài.
