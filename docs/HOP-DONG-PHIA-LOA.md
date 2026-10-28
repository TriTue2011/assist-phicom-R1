# Hợp đồng giao thức giữa HA và loa R1

Trạng thái: **phía HA đã viết và test bằng loa giả (127.0.0.1). Phía loa: có APK mic
`vn.r1.bodam` (mục 2b, build rồi nhưng chưa kiểm cùng HA thật); phần phát PCM và từ đánh thức
CHƯA CÓ.** Tài liệu này là chỗ duy nhất ghi đúng điều HA mong đợi để người làm phía loa (hoặc
phép đo trên loa) bám theo. Mọi mục đánh dấu **CHỜ ĐO** hoặc **TODO phía loa** chưa có đường đã
chứng minh; đừng coi là có sẵn.

Ký hiệu: ĐÃ XÁC NHẬN = đã ghi/đọc thật trên loa và đọc lại; CHƯA XÁC NHẬN = có trong tài liệu
dịch ngược hoặc ở thẻ R1-card nhưng chưa thử trên loa này; CHƯA CÓ = chưa tồn tại.

## 1. Điều khiển và EQ (WebSocket, cổng mặc định 8080) — ĐÃ NỐI

- Khung gửi: JSON, khoá `type`; tham số được gửi **cả phẳng lẫn trong `data`** vì chưa biết loa
  nhận kiểu nào (`client.build_message`). Khi đo xong thì giữ một kiểu.
- Đọc: `get_info` và `get_eq_config` (mỗi 10 giây). `data` của phản hồi là **chuỗi JSON**.
  Cấu trúc đã đo (21/10/2026):
  `eq.{Eq_Enable, Current_Preset (-1 = không chọn), Preset_list[{Preset,Name}], Bands.{list[i].BandLevel, minBandLevel -1500, maxBandLevel 1500}}`,
  `bass.{Bass_Enable, Current_Strength}`, `loudness.{Loudness_Enable, Current_Gain}`.
- Ghi:

| Lệnh | Tham số | Trạng thái | Dùng ở |
|---|---|---|---|
| `set_eq_bandlevel` | `band` 0–4, `level` mB | **ĐÃ XÁC NHẬN** (band 0) | `number` EQ, thẻ |
| `set_bass_enable` | `enable` | **ĐÃ XÁC NHẬN** | `switch` bass, thẻ |
| `set_eq_enable` | `enable` | CHƯA XÁC NHẬN (có trong R1-card) | `switch` EQ, thẻ |
| `set_bass_strength` | `strength` | CHƯA XÁC NHẬN (có trong R1-card) | `number`, thẻ |
| `set_loudness_enable` | `enable` | CHƯA XÁC NHẬN | `switch`, thẻ |
| `set_loudness_gain` | `gain` | CHƯA XÁC NHẬN | `number`, thẻ |
| đặt preset theo số | — | **CHƯA CÓ lệnh nào xác định** | thẻ/`select` chỉ hiển thị |
| `send_message` what=4 (âm lượng) | `arg1`=5, `arg2`=0–15 | CHƯA XÁC NHẬN | `number` âm lượng |
| `Set_DLNA_Open` / `Set_AirPlay_Open` | `open` | CHƯA XÁC NHẬN (DLNA: xem PHAT-RA-LOA.md) | `switch` |

Thực thể và thẻ gắn thuộc tính `confirmed` theo bảng này (`const.CONFIRMED_COMMANDS`); thẻ hiện
nhãn «chưa xác nhận» ở mọi điều khiển có `confirmed=false`. Khi một lệnh được xác nhận bằng ghi
thật, thêm tên lệnh vào `CONFIRMED_COMMANDS` là đủ — nhãn tự biến mất. Preset: R1-card và web
của loa áp preset bằng cách ghi 5 dải; HA chưa làm vậy (`selectable=false`) vì giá trị từng
preset chưa đo.

Cổng 8080 còn nhận lệnh `shell` chạy tuỳ ý không xác thực (ngoài phạm vi, HA **không** dùng).

## 2. Mic loa → HA (TCP) — phía HA ĐÃ CÓ, phía loa CHƯA CÓ

Phía HA (`mic.py`) là **máy khách TCP**: nối `mic_host:mic_port`, đọc liên tục.

- Luồng: PCM16 mono **16 kHz** little-endian, thô (không tiêu đề, không khung), loa là máy chủ.
- HA đọc khúc 2048 byte; **im quá 5 giây** (không đủ một khúc) thì coi là đứt và nối lại sau
  2 giây; nối được mà chưa nhận trọn khúc nào thì **vẫn unavailable**.
- `mic_host` trống = tắt phần nghe (mặc định). Cổng mic **CHƯA ĐO / chưa có dịch vụ**: form gợi ý
  8765 chỉ là số điền sẵn, không phải số đã chứng minh.
- **TODO phía loa:** một dịch vụ mở cổng TCP, mở mic (AK7755, thiết bị `pcmC2D0c`?) và đẩy PCM
  vào cổng. Chưa biết: đường mic thật, ai đang giữ mic (voicebot?), quyền uid 2000, RAM trống
  (xem `THIET-KE-MIC.md`). **CHỜ KẾT QUẢ ĐO.**
- Bảo mật: ai nối được cổng này nghe được mic. Phía loa nên chỉ nhận kết nối từ IP của HA.

## 2b. Mic loa → HA qua APK `vn.r1.bodam` (loa nối VÀO HA) — đã build, CHƯA kiểm đầu-cuối

Đường này đảo chiều so với mục 2: APK trên loa là **máy khách TCP**, HA (`mic_server.py`,
`R1MicServer`) là máy chủ. Loa không mở cổng nghe trong LAN.

- HA nghe `0.0.0.0:<mic_listen_port>` (mặc định 18765, CHƯA ĐO). Chỉ mở khi đã đặt `mic_listen_key`
  và `mic_host` (IP loa). Kết nối từ IP khác `mic_host` bị đóng ngay.
- Mọi khung = **4 byte độ dài big-endian + payload**.
  1. Khung đầu: JSON `{"type":"hello","version":1,"key":"<khoá>"}`. Khoá so bằng `hmac.compare_digest`;
     sai khoá/phiên bản thì đóng; chờ hello tối đa 10 giây.
  2. Khung giữa: PCM16 little-endian mono 16 kHz thô (cùng định dạng mục 2). Trần một khung 1 MiB.
  3. Khung cuối: JSON `{"type":"end"}`, APK rồi đóng kết nối.
- Một luồng tại một thời điểm; luồng thứ hai bị đóng. Mất kết nối giữa chừng chỉ đóng phiên đó.
- `switch.r1_tat_mic` bật: HA **giữ kết nối** của loa (nó còn mang âm lượng và đèn nhạc) nhưng đọc rồi **bỏ ngay** mọi khung tiếng mic: không khuếch
  đại, không DSP, không listener nào nhận (từ 0.6.5; trước đó đóng kết nối nên tắt mic là mất luôn chỉnh âm lượng). Lưu ý riêng tư: byte tiếng vẫn tới tiến
  trình HA trên mạng nội bộ rồi bị bỏ; muốn không có byte nào thì tắt mic trên loa/APK. Khung PCM rỗng bị bỏ; byte lẻ cuối khung được dồn sang khung sau
  (mẫu PCM16 không lệch).
- Lưu ý đã biết: `mic_host` đóng hai vai (IP loa được phép của đầu nhận và địa chỉ đường cũ ở mục 2), nên khi đặt
  nó HA còn tự thử nối ra `mic_host:mic_port` (mặc định 8765) mỗi 2 giây và thất bại im lặng vì loa không có dịch vụ
  ở cổng đó. Vô hại nhưng gây nhiễu log mức debug; chưa tách thành hai tuỳ chọn.
- Khung PCM đi qua đúng chuỗi khuếch đại + DSP + listener của `R1Mic` (không có đường mic thứ hai).
- APK chỉ ghi/gửi khi người dùng bật (nút trên màn hình, nút giữa, hoặc lệnh kiểm thử `KIEM_MIC`);
  đang gửi thì có thông báo «Đang gửi mic về Home Assistant».
- Còn lại cần đo: mic qua `AudioRecord` có ra tiếng trên loa thật không; ai đang giữ mic (voicebot
  gốc); độ trễ; cổng 18765 so với cổng cấu hình trong APK.

## 3. HA → loa (kênh phát PCM) — phía HA ĐÃ CÓ, phía loa CHƯA CÓ

Phía HA (`playback.py`) là **máy khách TCP**: mỗi lượt nói mở một kết nối tới
`play_host:play_port`, ghi PCM rồi **đóng kết nối khi hết tiếng**.

- Luồng: PCM16 mono **16 kHz** little-endian thô, cùng định dạng mic. Đầu vào bộ đàm từ go2rtc
  là A-law 8 kHz (đường đã chạy thật ở bộ đàm camera); HA giải A-law rồi nâng lên 16 kHz
  (nội suy tuyến tính) trước khi gửi.
- Hợp đồng phía loa (đề xuất): nhận kết nối, phát byte ra loa ngay khi nhận, dừng khi kết nối
  đóng; một kết nối tại một thời điểm (kết nối mới đến lúc đang phát: từ chối hoặc thay thế, chọn
  khi làm). Loa **không cần** gửi gì ngược lại.
- `play_port` mặc định **0 = chưa có kênh** → bộ đàm tắt, `binary_sensor.r1_bo_dam` unavailable,
  HTTP POST bộ đàm trả 503. HA không đoán cổng.
- **TODO phía loa:** chưa có đường đã chứng minh để phát PCM thô ra loa R1 (tinyplay? AudioTrack
  trong một APK? ghi mixer chưa thử). **CHỜ KẾT QUẢ ĐO.**
- Phát qua DLNA (`media_player.r1_loa`, dùng cho TTS của Assist) là đường khác, đã làm, xem
  `PHAT-RA-LOA.md`.

## 4. Nửa công — thuộc về HA, không cần phía loa

Khi bộ đàm đang phát về loa, HA **bỏ** mọi khúc mic (`R1Mic.hold()`): không vào Assist, không ra
`MicView`. Luồng mic TCP vẫn được đọc (loa khỏi nghẽn). Sau khi đóng cổng thoại, chờ thêm
`talk_tail_s` rồi mới nhả. Lý do: loa không tự tắt mic khi phát (khác camera Imou; chưa biết
AK7755 có khử vang không — **CHỜ ĐO**), nên nếu không bỏ, loa sẽ nghe lại tiếng mình.

## 4b. Giao diện trừu tượng (`audio_port.py`) — chỗ cắm cho đường phần cứng chưa có

Mã đàm thoại phía HA (`dam_thoai.R1Talk`, vệ tinh Assist, bộ đàm) KHÔNG biết loa lấy tiếng mic
bằng cách nào. Nó chỉ dùng hai giao diện (`typing.Protocol`):

| Giao diện | Hướng | Hợp đồng |
|---|---|---|
| `PcmSource` | loa → HA | nhận khung PCM qua `add_chunk_listener`; trạng thái `configured` / `available` / `muted` / `connected` / `holding`; `want()` xin luồng chạy (hết người xin thì loa không có gì để gửi); `hold()` bỏ tiếng (nửa công); `add_state_listener`, `add_link_listener` |
| `PcmSink` | HA → loa | `async_play(dòng khung PCM) -> số giây`; `configured` |

Khung: **PCM16 mono 16 kHz little-endian**, số chẵn byte, không quá `MAX_FRAME_BYTES`
(`check_frame` từ chối khung rỗng / lẻ / quá lớn). Hai bản cài hiện có (`mic.R1Mic`,
`playback.R1Playback`) là máy khách TCP theo mục 2 và 3; đường thật sau này chỉ cần thoả cùng giao
diện. Test dùng bản trong bộ nhớ (`tests/memory_port.py`), không TCP, không đoán phần cứng.

**Không xử lý trên loa đè lên luồng.** Loa gửi mic THÔ: không lọc ồn, không AGC, không cổng im
lặng đặt mẫu về 0 (xem `BAI-HOC-TU-CAMERA.md` a). Mọi xử lý (khuếch đại `number.r1_tang_mic`,
STT, từ đánh thức kiểu `ha`) nằm ở HA.

## 4c. Từ đánh thức TRÊN LOA → HA (HTTP POST) — phía HA ĐÃ CÓ, phía loa CHƯA CÓ (CHỜ)

Chế độ `wake_mode = speaker`: từ đánh thức chạy trên loa; HA **không nối luồng mic** và không
nhận byte mic nào cho tới khi loa báo trigger (hoặc người bật `switch.r1_dam_thoai`).

- Địa chỉ: dịch vụ `r1_speaker.get_wake_endpoint` trả `POST <ha_url>/api/r1_speaker/wake/<entry>?k=<khoá>`.
- Thân JSON tuỳ chọn: `{"event": "wake", "word": "<từ>"}` (mặc định `wake`) hoặc nhịp tim
  `{"event": "alive"}` (nên gửi vài chục giây một lần: có nhịp tim gần đây thì
  `sensor.r1_trang_thai_mic` mới hiện «nghe» — chưa có phía loa thì HA hiện «tắt», không nói dối).
- Trả lời: `200` (`{"phien":"mo"}` hoặc `{"nhan":"alive"}`); `409` đang có phiên khác
  (`{"loi": "..."}`); `503` mic chưa cấu hình / đang tắt; `400` sai định dạng; `401` khoá sai
  (kèm `Retry-After: 60`, xem `BAI-HOC-TU-CAMERA.md` h).
- Sau `200` loa mới được gửi luồng mic (mục 2) và chỉ trong lúc phiên mở: HA nối vào `mic_host:mic_port`
  khi có phiên và đóng khi hết phiên.
- `binary_sensor.r1_tu_danh_thuc` bật vài giây sau mỗi trigger (thuộc tính `phia_loa` =
  `CHO_PHIA_LOA` cho tới lần gọi đầu) và sự kiện `r1_speaker_wake` bắn lên bus.
- **Chưa đo / chưa làm:** mô hình từ đánh thức chạy trên loa (RAM ~490 MB, CPU), có bắt được từ gọi
  ở xa không, tranh mic với voicebot. Mọi thứ trên loa cần chủ máy duyệt riêng (`THIET-KE-MIC.md`).

## 5. Việc cần đo trên loa (chưa làm, cần chủ máy duyệt)

1. Đường mic và chủ sở hữu thiết bị thu (mục 2).
2. Đường phát PCM thô, và độ trễ/đệm của nó (mục 3).
3. Ngưỡng/thời gian cổng thoại thật: mức ồn nền của đường go2rtc → loa, và tiếng loa vang lại
   mic bao lâu (`talk_threshold_db`, `talk_silence_s`, `talk_preroll_s`, `talk_tail_s`; mặc định
   mượn từ camera: −45 dBFS, 1,5 s, 0,3 s, 0,5 s).
4. Ghi thử `set_eq_enable`, `set_bass_strength`, `set_loudness_enable`, `set_loudness_gain`
   (đọc lại bằng `get_eq_config`, trả về giá trị gốc) rồi thêm vào `CONFIRMED_COMMANDS`.
5. Giá trị 5 dải của từng preset (để áp preset bằng cách ghi 5 dải như R1-card).
6. Từ đánh thức trên loa: mô hình nào, chạy ở đâu, độ trễ trigger → luồng mic, tầm bắt (mục 4c).
7. Mức mic thật để chọn lại `number.r1_tang_mic` (mặc định +12 dB chưa đo) và `talk_threshold_db`.
8. Định dạng `listen` ở go2rtc (mục 3 của hướng dẫn cài đặt chưa thử với go2rtc thật).

## 6. Đèn LED — phía HA ĐÃ CÓ (qua `LightsSink`), phía loa CHƯA CÓ

Lệnh `lights_test set <mặt nạ> <rgb>` chỉ chạy được trên loa; HA không có đường tới nó. Hợp đồng
`LightsSink`, mặt nạ, chức năng, hiệu ứng và việc chưa đo: xem `DEN-LED.md`. **TODO phía loa:** một dịch
vụ đèn (chưa được duyệt) thoả giao diện đó.
