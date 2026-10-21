# Thiết kế: để Home Assistant nghe mic của loa R1 (chiều loa → HA)

Trạng thái: **bản thiết kế ban đầu (lịch sử)**. Phương án sau đó được làm là APK `vn.r1.bodam`
(thư mục `apk/`, xem `README.md` và `HOP-DONG-PHIA-LOA.md` mục 2b); các mục «CHƯA BIẾT» dưới đây
vẫn còn phần chưa đo. Bản thiết kế này được viết khi chưa cài gì lên loa, chưa
kết nối loa. Mọi chỗ ghi *CHƯA BIẾT* cần đo trước khi chọn cách làm,
và việc đo cần chủ máy duyệt (mục 5).

Chiều ngược lại (HA phát tiếng ra loa) đã làm xong ở `media_player.r1_loa`, xem
`docs/PHAT-RA-LOA.md`.

## 1. Đã biết và chưa biết

Số liệu đo (chỉ đọc, qua ADB, đợt trước) và phân tích tĩnh các APK:

| Mục | Đã biết |
|---|---|
| SoC / hệ điều hành | Rockchip RK3229, ARMv7 (armeabi-v7a), Android 5.1.1, bản dựng 2018, bản vá bảo mật 2016. |
| RAM | Khoảng 490 MB tổng (MemTotal 501444 kB). **Chưa biết còn trống bao nhiêu khi loa chạy bình thường.** |
| Âm thanh | 4 card ALSA. Card 2 là `RK_AK7755` (codec/DSP AKM có đầu vào mic). Có thiết bị thu `pcmC2D0c` (và `pcmC1D0c`). Có `tinycap`, `tinymix`, `tinyplay` trong `/system/bin`. |
| Quyền shell | `adb shell` chạy với uid 2000 (shell). `adb root` không nâng quyền. Không có `su`. |
| Ứng dụng đã cài | `info.dourok.voicebot` (ứng dụng giọng nói), `vn.aibox.bttool`. Phân tích tĩnh cho thấy voicebot **đã thu mic liên tục** bằng `AudioRecord` 16 kHz, 16-bit, mono, có phát hiện từ gọi, và có một nhánh nói chuyện với Assist của HA. |
| `pm` qua adb | Từng báo `error: closed`, nên **đường cài APK chưa rõ**. |

**CHƯA BIẾT** (quyết định phương án):

1. Đường mic thật: tín hiệu mic đi qua `pcmC2D0c` hay `pcmC1D0c`, bao nhiêu kênh, tốc độ lấy mẫu,
   DSP AK7755 có đang xử lý (khử vang, định hướng) trước khi ra PCM hay không.
2. Tiến trình nào đang giữ thiết bị thu. Trên Android 5.1, `AudioFlinger` thường giữ thiết bị
   thu độc quyền khi một ứng dụng đang thu; mở thêm một đường thu có thể bị báo bận hoặc
   cướp mic của voicebot.
3. Uid 2000 có đọc được `/dev/snd/pcmC2D0c` hay không (nhóm `audio`/quyền thư mục).
4. RAM và CPU còn trống thực tế khi loa đang phát nhạc.
5. Có chỗ ghi nào cho uid 2000 để đặt một chương trình (ví dụ `/data/local/tmp`) và có chạy được
   tệp thực thi từ đó không. SELinux đang ở `permissive` (theo thuộc tính khởi động) nên
   khó chặn, nhưng chưa kiểm.
6. Cách cài một APK: `pm` hỏng qua adb, chưa biết `adb install` có chạy không.
7. Voicebot đang cấu hình đi nhánh nào. Phân tích tĩnh thấy một nhánh khác gửi âm thanh mic
   không mã hoá ra máy chủ ngoài mạng. **Trước khi bật bất cứ thứ gì dùng mic, phải biết
   voicebot đang gửi mic đi đâu.** Đây là việc riêng tư, đừng bỏ qua.

## 2. Phương án 0 (không cài gì thêm): cấu hình voicebot sẵn có

Voicebot đã có mic, từ gọi và nhánh Assist của HA. Nếu cấu hình được sang nhánh HA (và tắt
nhánh gửi ra ngoài) thì không cần cài gì. Nhưng nó là ứng dụng của bên thứ ba, không phải
thực thể trong HA của chúng ta: không có `assist_satellite`, không có công tắc tắt mic, và
độ ổn định chưa biết.

- Đọc gì từ loa: không đọc, voicebot tự nói với HA.
- Quyền: không thêm. Cài: không. Rủi ro: thấp với loa; rủi ro riêng tư ở mục 1.7.
- Gỡ lại: đổi cấu hình về cũ. Chưa kiểm voicebot cấu hình được những gì.

Phương án này nên *được đánh giá trước* vì rẻ nhất, nhưng không thay thế hai phương án dưới
nếu muốn thực thể `assist_satellite` như camera Imou.

## 3. Phương án 1: dịch vụ tự viết trên R1, đẩy PCM về go2rtc hoặc HA

Ý tưởng: một chương trình nhỏ đọc PCM từ mic codec AK7755, gửi liên tục về máy chủ HA. Phía HA
nhận bằng go2rtc (nguồn âm thanh) rồi dùng như `dahua_talk` dùng luồng camera: tích hợp
`r1_speaker` thêm `assist_satellite.r1` (mẫu `custom_components/dahua_talk/assist_satellite.py`)
đọc luồng, chạy pipeline Assist, trả lời bằng `media_player.r1_loa`.

Hai cách dựng chương trình trên loa:

- **1a. Chương trình native ARMv7 bọc `tinycap`/`tinyalsa`** (nhỏ nhất, vài trăm KB, gần
  như không tốn RAM). Đọc `/dev/snd/pcmC2D0c` (CHƯA BIẾT quyền). Phát PCM 16 kHz 16-bit
  mono qua TCP hoặc RTP. Cần đặt tệp lên loa và chạy từ `adb shell` (uid 2000), và phải
  tự chạy lại sau khi loa khởi động lại (không có `init.d` cho uid shell: chưa có cách tự
  khởi động nếu không root).
- **1b. APK dùng `AudioRecord`** (như voicebot). Chỉ cần quyền `RECORD_AUDIO` khai trong APK,
  **không cần root** để thu. Dùng `AudioRecord` đi qua `AudioFlinger` nên không tranh
  `/dev/snd` trực tiếp, nhưng vẫn có thể tranh nguồn mic với voicebot. Có thể tự khởi động qua
  `BOOT_COMPLETED`. Cần đường cài APK (mục 1.6 chưa rõ).

Đọc gì từ loa: chỉ PCM mic. Băng thông: 16 kHz × 2 byte = 32 KB/s (khoảng 256 kb/s), nhẹ.

Quyền cần: 1a cần uid 2000 đọc được thiết bị thu (chưa biết) và chạy được tệp thực thi;
1b cần `RECORD_AUDIO`. **Nếu đo ra uid 2000 không đọc được `/dev/snd` thì 1a cần root: ghi
rõ là cần root và dừng ở đó, không đề xuất khai thác.** 1b không cần root nhưng cần cài được
APK.

Rủi ro với loa:
- Tranh mic với voicebot/dịch vụ giọng nói của loa: có thể làm hỏng từ gọi sẵn có, hoặc
  chương trình mới bị báo bận.
- Tốn CPU/RAM trên máy chỉ có 490 MB: nếu loa bắt đầu giật khi phát nhạc thì phải gỡ.
- Treo tiến trình thu có thể giữ mic và chặn voicebot (cần cách dừng).
- Phát PCM không mã hoá trong LAN: ai trong mạng nối được cổng đó đều nghe được mic. Phải
  giới hạn bên nhận (chỉ HA nối vào, hoặc loa chỉ đẩy tới địa chỉ HA) và không mở cổng nghe
  trên loa nếu tránh được. Đẩy ra (loa → HA) tốt hơn mở cổng trên loa.
- Mic đang mở liên tục: phải có công tắc tắt mic bên HA (mẫu `switch.<camera>_tat_mic`).

Gỡ lại: dừng tiến trình rồi xoá tệp đã đặt (1a), hoặc `adb uninstall` (1b). Không đổi cấu hình
hệ thống nên gỡ là hết dấu vết. Điều kiện: phải biết chính xác đã đặt gì, ghi lại ngay
lúc cài.

## 4. Phương án 2: vệ tinh Wyoming (hoặc tương đương)

Giao thức Wyoming của HA: loa mở cổng TCP, HA kết nối vào, hai bên trao đổi dòng JSON và
khung PCM. HA tự có `assist_satellite` khi thêm tích hợp Wyoming, kèm từ gọi
(openWakeWord) ở phía HA. Ưu điểm: không phải viết `assist_satellite` riêng.

- Bản `wyoming-satellite` chính thức viết bằng **Python, cần Linux + `arecord`/`aplay`**.
  Android 5.1 ARMv7 không có Python, và Termux hiện không hỗ trợ Android đời này, nên
  **không chạy được nguyên bản**. Chưa kiểm có APK Wyoming nào chạy trên Android 5.1; đừng
  coi là có sẵn.
- Khả thi thực tế: tự viết một APK (Java) nói giao thức Wyoming, thu bằng `AudioRecord` như
  1b. Khi đó phần cần cài, quyền, rủi ro và cách gỡ **giống 1b**, cộng thêm: loa phải mở cổng
  TCP nghe (rủi ro nghe lén trong LAN như trên, giảm bằng cách chỉ nhận từ địa chỉ của HA).
- Đọc gì từ loa: PCM mic, và nhận PCM/TTS để phát (có thể dùng lại `media_player.r1_loa`
  thay vì phát qua Wyoming).

## 5. Đề xuất

1. Làm trước **lệnh đo chỉ đọc** (dưới đây) để trả lời mục 1.1 đến 1.7.
2. Đánh giá **Phương án 0** (cấu hình voicebot): chi phí gần bằng không, nhưng phải biết
   voicebot đang gửi mic đi đâu (1.7).
3. Nếu cần thực thể HA đàng hoàng: chọn **Phương án 1b** (APK `AudioRecord` đẩy ra go2rtc/HA)
   nếu `adb install` chạy được. Lý do: không cần root, dùng đường mic mà Android đã cấp quyền
   (ít tranh chấp hơn mở thẳng `/dev/snd`), và phần HA (`assist_satellite` + công tắc mic)
   tái dùng mẫu của camera. Phương án 2 chỉ đáng khi chủ máy muốn dùng tích hợp Wyoming có
   sẵn của HA và chấp nhận viết APK nói Wyoming.
4. Nếu đo cho thấy 1a cần root, hoặc APK không cài được: **dừng và hỏi chủ máy**, không tìm
   cách vượt.

Không dùng: lệnh `shell` của WebSocket cổng 8080 (nó chạy lệnh tuỳ ý, không xác thực) và cổng
ADB mở không xác thực làm đường *lấy quyền*. Dùng ADB để *đo chỉ đọc* theo mục dưới là việc
chủ máy duyệt, không phải đường cài đặt.

## 6. Lệnh đo chỉ đọc đề xuất (chờ chủ máy duyệt, chưa chạy)

Tất cả chạy bằng `adb shell` với uid 2000, không ghi gì lên loa:

```
id
getprop ro.product.cpu.abi
getenforce
cat /proc/meminfo
dumpsys meminfo
cat /proc/asound/cards
cat /proc/asound/pcm
ls -l /dev/snd
ls -l /system/bin/tinycap
dumpsys media.audio_flinger
dumpsys media.audio_policy
dumpsys package info.dourok.voicebot | grep -i -E "permission|RECORD_AUDIO"
ps | grep -i -E "voicebot|mediaserver|unisound"
```

Cần đọc kết quả thế nào: `id` có nhóm `audio` không; `ls -l /dev/snd` mode và nhóm của
`pcmC2D0c`; `dumpsys media.audio_flinger` cho biết ai đang giữ thiết bị thu; `meminfo` cho RAM
trống.

**Không thuộc "chỉ đọc", cần duyệt riêng:** `tinycap` (mở thiết bị thu thật, có thể tranh mic
với voicebot trong lúc chạy; nên thử ngắn, khi voicebot đang nghỉ); `adb install`; ghi vào
`/data/local/tmp`.

## 7. Việc phía HA khi đã có luồng mic (không phụ thuộc phương án)

Theo mẫu camera Imou: `assist_satellite.r1`, `number.r1_tang_mic`, `switch.r1_tat_mic`,
`select.r1_tro_ly`, và phát trả lời ra `media_player.r1_loa`. Có sự phản hồi âm thanh (loa
phát, mic nghe lại): camera tự tắt mic khi phát; R1 có DSP AK7755 nên *có thể* có khử vang,
nhưng chưa biết; nếu không, `assist_satellite` phải tự tắt tiếng mic trong lúc phát.
