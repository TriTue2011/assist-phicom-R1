# assist-phicom-R1 — loa Phicomm R1 trong Home Assistant

Kho này gồm hai phần chạy cùng nhau để biến loa **Phicomm R1** thành một thiết bị của Home Assistant (HA):

1. **Tích hợp HA `r1_speaker`** (`custom_components/r1_speaker/`): chỉnh EQ, âm lượng, DLNA/AirPlay của loa; phát tiếng của HA
   (TTS, nhạc) ra loa; vệ tinh Assist; bộ đàm; cài đặt đèn; ba thẻ Lovelace (`r1-eq-card`, `r1-talk-card`, `r1-settings-card`).
2. **APK `vn.r1.bodam`** (`apk/`): ứng dụng Android nhỏ cài lên loa, lấy tiếng từ micro của loa gửi về HA, **chỉ khi người dùng bật**.
   Nút giữa của loa bật/tắt mic (nhấn đôi bật/tắt Bluetooth).

> **Đọc trước khi làm theo.** Đây là dự án thử nghiệm. Phần lớn mã đã được kiểm bằng **loa giả** (mock) trên máy phát triển; chỉ
> một số điểm được kiểm trên loa thật. Mục [7. Trạng thái](#7-trạng-thái-đã-kiểm-trên-loa-thật-và-chỉ-kiểm-bằng-mock) liệt kê rõ,
> không hứa hơn những gì đã đo. Cài APK lên loa là việc **khó đảo và chạm vào phần mềm gốc của loa**: chỉ làm khi bạn chủ động quyết định.

**Giấy phép: CHỦ MÁY CHỌN GIẤY PHÉP.** Kho chưa có tệp `LICENSE`; chủ kho phải chọn giấy phép trước khi công khai/phân phối.

## Mục lục

1. [Yêu cầu](#1-yêu-cầu-phần-mềm) · 2. [Cài tích hợp HA](#2-cài-tích-hợp-ha) · 3. [Cài APK lên loa](#3-cài-apk-lên-loa-chỉ-khi-bạn-đã-quyết-định) ·
4. [Nút giữa](#4-nút-giữa) · 5. [Đèn](#5-đèn) · 6. [Cấu hình mic về HA](#6-nối-mic-loa-về-ha) · 7. [Trạng thái](#7-trạng-thái-đã-kiểm-trên-loa-thật-và-chỉ-kiểm-bằng-mock) ·
8. [Quyền riêng tư](#8-quyền-riêng-tư) · 9. [Chạy test](#9-chạy-test) · 10. [Cấu trúc kho](#10-cấu-trúc-kho) · 11. [Việc còn thiếu](#11-việc-còn-thiếu-đã-biết)

## 1. Yêu cầu phần mềm

**Bắt buộc để dùng:**

| Thứ | Ghi chú |
|---|---|
| Home Assistant **2026.2 trở lên** | bản thử nghiệm là **2026.2.3**; `hacs.json` ghi tối thiểu 2026.2.0. Chưa thử bản cũ hơn. |
| Loa Phicomm R1 cùng mạng LAN với HA | nên đặt IP tĩnh/giữ chỗ DHCP cho loa. Cổng điều khiển/EQ mặc định **8080**. |
| `adb` (Android platform-tools) | chỉ khi cài APK hoặc đo/thử đèn, phím trên loa. |

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
   hiện ở thẻ → Cài đặt → Kết nối (quản trị viên). Chi tiết: `docs/HUONG-DAN-CAI-DAT.md`.

**Kiểm nhanh:**

- Nếu báo «Không đọc được loa»: sai IP/cổng, hoặc cổng 8080 bị chặn. Tích hợp thử bằng một lần `get_info` khi bạn bấm Gửi.
- Sau khi thêm: có thiết bị **Phicomm R1** với 5 thực thể EQ (`number.phicomm_r1_eq_60_hz` … `_14_khz`), `number.phicomm_r1_volume`,
  `media_player.r1_loa`, `assist_satellite.r1`, `sensor.r1_trang_thai_mic`…
- Kéo thử một dải EQ: lệnh ghi dải EQ đã được xác nhận trên loa thật; các lệnh khác xem bảng ở mục 7.
- Thẻ: thêm tài nguyên Lovelace `/r1_speaker/r1-card.js` (loại Mô-đun JavaScript), rồi thêm thẻ `type: custom:r1-card`
  (thẻ gộp, 3 tab Đàm thoại / EQ / Cài đặt, đóng sẵn). Chi tiết: `docs/HUONG-DAN-CAI-DAT.md` mục 2.
- Phát tiếng ra loa (TTS/nhạc) cần thêm tích hợp **DLNA Digital Media Renderer** của HA cho loa — xem `docs/PHAT-RA-LOA.md`.

## 3. Cài APK lên loa (chỉ khi bạn đã quyết định)

APK: `apk/vn-r1-bodam.apk` (gói `vn.r1.bodam`, versionName 1.1, minSdk/targetSdk 22, ký bằng khoá debug),
dựng từ mã nguồn trong `apk/nguon/` (xem `apk/nguon/README-BUILD.md`). Đây là **bản phát hành**: không có
receiver kiểm thử. Kiểm sha256 trước khi cài:

```bash
cd apk && sha256sum -c vn-r1-bodam.apk.sha256
```

**Đã chạy trên loa thật (22/10/2026):** mic về HA, tự nối lại khi HA khởi động lại, phát tiếng từ HA xuống loa
qua cùng kết nối, đèn theo nhạc của firmware (độ sáng/sắc độ/bật tắt), lệnh đổi cấu hình giả bị bỏ qua khi đã
cấu hình. **Chưa kiểm:** tự bật mic sau khi loa khởi động lại (cần khởi động lại loa để chứng minh).

**Đọc cảnh báo trước:**

- **Mic tự bật khi loa khởi động** nếu app đã cấu hình (host + port + khoá), và luôn gửi về HA đã cấu hình khi đang chạy.
  HA từ chối kết nối khi bạn tắt mic (`switch.r1_tat_mic`), nhưng loa vẫn thử nối lại mỗi 2–30 giây (mỗi lần
  chỉ mở mic rất ngắn, tiếng bị bỏ ở phía HA).
- Firmware gốc của loa (Android 5.1.1) cho `adb` qua mạng cổng 5555 **không đòi xác thực** (theo số đo trên loa của chủ dự án): bật ADB nghĩa
  là bất kỳ máy nào trong LAN cũng có shell trên loa. Chỉ bật khi cần và tắt đi sau khi làm xong, đừng để loa lộ ra ngoài mạng.
- Shell trên loa là `uid=2000` (không root, không `su`).

Các bước:

```bash
# 1) Bật ADB trên loa (theo cách bạn đã dùng cho loa của mình), rồi nối:
adb connect <IP-loa>:5555           # ví dụ 192.0.2.10:5555

# 2) Đưa APK lên loa và cài. Lệnh `pm` trần bị chặn trên loa: BẮT BUỘC dùng đường dẫn đầy đủ /system/bin/pm
adb push apk/vn-r1-bodam.apk /data/local/tmp/
adb shell /system/bin/pm install -r /data/local/tmp/vn-r1-bodam.apk

# 3) Cấu hình LẦN ĐẦU (chỉ nhận khi app chưa cấu hình), rồi bật mic:
adb shell /system/bin/am start -n vn.r1.bodam/.ManHinhChinh --es host <IP-HA> --ei port 18765 --es khoa <khoá>
adb shell /system/bin/am start -n vn.r1.bodam/.ManHinhChinh --ez bat true
```

Khoá lấy từ tuỳ chọn `mic_listen_key` của tích hợp. Muốn đổi cấu hình về sau: `adb shell /system/bin/pm clear
vn.r1.bodam` rồi làm lại bước 3 (app đã cấu hình thì bỏ qua lệnh đổi, để app khác trên loa không chuyển được
đích đến của tiếng mic).

Tuỳ chọn, **chỉ khi chủ loa quyết định** — ẩn gói gốc của hãng cho khỏi tranh mic/nút:

```bash
adb shell /system/bin/pm hide com.phicomm.speaker.device
```

- Đây là **ẩn**, không xoá: gói gốc vẫn nằm trong hệ thống, làm ngược lại được.
- Lệnh này **chưa được kiểm trong dự án này**; nếu shell không đủ quyền thì lệnh sẽ báo lỗi và không đổi gì.

**Gỡ / hoàn tác:**

```bash
adb shell /system/bin/pm uninstall vn.r1.bodam
adb shell /system/bin/pm unhide com.phicomm.speaker.device     # nếu đã ẩn gói gốc
```

**Cấu hình APK** (host HA, cổng, khoá): APK có **một màn hình cài đặt** (`ManHinhChinh`) với các ô *Host HA*, *Port*, *Khoá*, khuếch đại dB,
khoảng nhấn đôi (ms), keycode nút giữa và công tắc *chế độ kiểm phím*. **Loa R1 không có màn hình**, và bản NV245 **chưa có cách điền
các ô này mà không cần màn hình** (xem mục 11). Đây là lỗ hổng lớn nhất khi muốn dùng APK; việc sửa đã được lập danh sách nhưng chưa làm.

## 4. Nút giữa

- Mã phím nút giữa trên loa là **195** (`0x00c3`), **đã đo thật** (thiết bị `/dev/input/event0`, `rk29-keypad`, có đủ sự kiện nhấn và nhả). APK NV245 đặt
  sẵn mặc định 195.
- **Nhấn đơn** = bật/tắt mic (quyết định sau khoảng chờ nhấn đôi, mặc định 500 ms). **Nhấn đôi** trong khoảng đó = bật/tắt Bluetooth. Nhấn giữ lâu
  được tính là một nhấn đơn. Mã phím khác 195 không làm gì. Logic này đã kiểm bằng test Java thuần (đồng hồ giả), **chưa kiểm trên loa thật**.
- **Giới hạn quan trọng:** APK hiện chỉ nhận phím qua `Activity.dispatchKeyEvent` của màn hình chính, nghĩa là **chỉ khi app đang ở tiền cảnh**.
  Chưa có cách nhận nút giữa khi app chạy nền.
- **Nếu nút của bạn ra mã khác:** (a) đo lại — `adb shell getevent -l /dev/input/event0` rồi nhấn nút, mã hiện dạng hex (ví dụ `00c3` = 195; lệnh chuẩn của Android, chưa chạy trong dự án này), hoặc bật *chế độ kiểm
  phím* trong app (ghi logcat tag `NV243Phim` và hiện mã trên màn hình); (b) điền mã thập phân vào ô *Keycode nút giữa*. Đặt `-1` = tắt xử lý nút.

## 5. Đèn

Loa có hai nhóm đèn, điều khiển bằng lệnh `/system/bin/lights_test set <mặt nạ> <6 số hex RRGGBB>` **chạy trên loa** (qua `adb shell`):

| Đèn | Mặt nạ | Màu | Đã kiểm |
|---|---|---|---|
| **Viền** | `7fffff8000` | **chỉ trắng**: bật `ffffff`, tắt `000000`, mờ `404040` | chủ máy xác nhận bằng mắt |
| **Đáy** | `7fff` | RGB | **xanh lá `00ff00` và xanh dương `0000ff` đã xác nhận**; **đỏ `ff0000` chưa chắc** |

Lệnh thử (ví dụ):

```bash
adb shell /system/bin/lights_test set 7fffff8000 ffffff   # viền sáng
adb shell /system/bin/lights_test set 7fffff8000 000000   # viền tắt
adb shell /system/bin/lights_test set 7fff 00ff00         # đáy xanh lá
adb shell /system/bin/lights_test set 7fff 0000ff         # đáy xanh dương
```

**Đèn chỉ sáng khi có dịch vụ trên loa.** Không có đường nào từ HA tới `lights_test`: tích hợp tính toán và lưu cài đặt đèn theo chức
năng (nghe, nghĩ, phản hồi, lỗi, tắt mic…) nhưng **không gửi gì tới loa** cho tới khi có một dịch vụ đèn trên loa; dịch vụ đó **chưa tồn tại** và APK
`vn.r1.bodam` cũng **không điều khiển đèn**. Thẻ cài đặt nói thẳng điều này. Chi tiết: `docs/DEN-LED.md`. Hiệu ứng của firmware (ID 200–412) không áp dụng
được từ shell; các màu pha (vàng, tím…) và mọi giá trị mặc định của bảng chức năng đều **chưa đo**.

## 6. Nối mic loa về HA

Đường mic: **APK trên loa nối VÀO HA** (loa là máy khách TCP, HA là máy chủ, loa không mở cổng nghe).

1. Trong HA: Cấu hình tích hợp → đặt **Máy chủ mic = IP của loa** (đây là IP duy nhất được phép nối vào), **Khoá luồng mic** = một chuỗi dài ngẫu
   nhiên do bạn tự đặt, **Cổng nghe mic** (mặc định `18765`, chưa đo). Đầu nhận chỉ mở khi đã đặt cả khoá lẫn IP loa.
2. Trong APK: *Host HA* = IP của HA, *Port* = cổng nghe mic ở trên, *Khoá* = đúng chuỗi trên.
3. Giao thức (4 byte độ dài big-endian + nội dung; khung `hello` có khoá → PCM16 mono 16 kHz → khung `end`): `docs/HOP-DONG-PHIA-LOA.md` mục 2b.
4. Trạng thái nhìn ở `sensor.r1_trang_thai_mic`: `tat` / `nghe` (cổng mở, chưa có tiếng) / `gui` (đang nhận tiếng).
5. `switch.r1_tat_mic` bật: HA **đóng kết nối** của loa và từ chối nối lại cho tới khi tắt công tắc (có test).

Kiểm thử không cần nút giữa (chỉ bản NV245 kiểm thử): `adb shell /system/bin/am broadcast -a vn.r1.bodam.KIEM_MIC --ez bat true` (bật) và `--ez bat false` (tắt).

## 7. Trạng thái: đã kiểm trên loa thật và chỉ kiểm bằng mock

**Đã kiểm trên loa thật (do chủ dự án thực hiện, theo tài liệu và báo cáo đo):**

- Cổng 8080 trả `get_info` và `get_eq_config`; cấu trúc dữ liệu EQ đã đọc thật (5 dải, giới hạn ±1500 mB).
- Ghi thật và đọc lại: `set_eq_bandlevel` (dải 0) và `set_bass_enable`.
- Mã phím nút giữa = 195 (đọc từ `/dev/input/event0`).
- Đèn viền chỉ trắng; đèn đáy xanh lá và xanh dương (xem mắt) — mục 5.
- Phần cứng/hệ điều hành (RK3229, Android 5.1.1, card âm thanh AK7755, shell uid 2000).

**CHỈ kiểm bằng mock/loa giả (chưa thử trên loa thật hoặc HA thật cùng loa):**

- Toàn bộ tích hợp HA: **316 ca test** với loa giả ở `127.0.0.1` (WebSocket giả, renderer UPnP giả, client TCP giả), xem mục 9.
- Các lệnh còn lại: bật/tắt EQ, cường độ bass, loudness, âm lượng, DLNA/AirPlay (viết theo tài liệu dịch ngược, **chưa ghi thử**; thực thể mang
  thuộc tính `confirmed: false`, thẻ ghi «chưa xác nhận»). Preset EQ chỉ hiển thị.
- Phát TTS/nhạc qua DLNA (`Set_DLNA_Open`, cổng của renderer, định dạng âm thanh nhận được).
- **Đầu nhận mic của HA** (`mic_server.py`) với **client TCP giả** theo giao thức APK; **APK chưa từng nối vào HA thật**.
- APK: build thành công (aapt/javac/d8/zipalign/apksigner mã thoát 0), **30 ca test Java thuần** (khung gói, khuếch đại dB, máy ghi với vận chuyển giả,
  logic nút với đồng hồ giả) — báo cáo của người build; **mã nguồn không có trong kho nên người nhận không chạy lại được**. Khi đóng gói đã
  đối chiếu bytecode của APK: khung giao thức, mã 195, `repeatCount==0`, manifest khớp báo cáo.
- **Chưa kiểm trên loa thật**: cài APK; mic qua `AudioRecord` có ra tiếng không và ai đang giữ mic (ứng dụng giọng nói gốc của loa có thể giữ); độ trễ; nút giữa
  có tới được app; Bluetooth bật/tắt; `pm hide`; mọi đèn do HA điều khiển; thẻ trong trình duyệt thật ngoài Chrome không đầu.
- **Chưa có**: dịch vụ phát PCM thô ra loa (bộ đàm nói vào loa), từ đánh thức chạy trên loa, dịch vụ đèn trên loa, đàm thoại hai chiều song công từ HA
  (việc này đang được làm, chưa hoàn thành).

## 8. Quyền riêng tư

- **Mic chỉ gửi khi được bật.** APK không ghi âm ra bộ nhớ hay log, không tự khởi động cùng máy (không có receiver khởi động), không có wake-word, chỉ ghi
  khi bạn bật bằng nút trên màn hình, nút giữa, hoặc lệnh kiểm thử. Tắt là dừng ghi, gửi khung `end` và đóng kết nối.
- **Báo hiệu khi đang gửi:** APK chạy dịch vụ tiền cảnh với thông báo «Đang gửi mic về Home Assistant»; trong HA, `sensor.r1_trang_thai_mic` hiện `gui`.
  **Nhưng:** loa không có màn hình nên thông báo gần như không ai thấy, và **chưa có đèn báo** (không có dịch vụ đèn trên loa — mục 5). Đừng coi hai thứ này
  là chỉ báo đủ cho người đứng cạnh loa.
- Tắt mic bằng `switch.r1_tat_mic` trong HA đóng kết nối của loa (mục 6).
- **Đường truyền không mã hoá**: khoá và tiếng đi qua TCP trơn trong LAN. Chỉ dùng trong mạng tin cậy; đầu nhận lọc theo IP loa và khoá nhưng IP có thể bị giả mạo trong LAN.
- **Khoá nằm dạng chữ thường trong SharedPreferences của app** (`allowBackup=false`, dữ liệu riêng của app).
- **Bản kiểm thử (`apk/nguon`, biến thể kiemthu) có receiver exported** (`KIEM_MIC`, `KIEM_DEN_NHAC`): bất kỳ app nào trên loa gửi được lệnh bật mic tới
  host bất kỳ. **Bản phát hành `apk/vn-r1-bodam.apk` không có chúng**, và cửa cấu hình bằng intent của `ManHinhChinh` chỉ nhận khi app CHƯA cấu hình.
- Đừng đặt loa ở nơi người ngoài ra lệnh được cho nhà (mic + từ đánh thức); đừng dán URL bộ đàm (chứa khoá) ra ngoài.

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
