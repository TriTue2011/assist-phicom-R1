# Hướng dẫn cài đặt tích hợp Phicomm R1 Speaker

Gồm bốn phần: (1) cài tích hợp vào Home Assistant, (2) thẻ chỉnh EQ, (3) Assist và bộ đàm,
(4) phần trên loa. Tổng quan, cài APK mic `vn.r1.bodam` và trạng thái đã kiểm nằm ở `README.md`
(gốc kho). **Mic có APK `vn.r1.bodam` (thư mục `apk/`) nhưng đường mic từ loa thật về HA CHƯA được
kiểm đầu-cuối; phát PCM về loa và từ đánh thức trên loa CHƯA CÓ**, xem mục 4 và
`HOP-DONG-PHIA-LOA.md`. Chưa có phần đó thì EQ, âm lượng, DLNA và thẻ vẫn dùng được.

## 1. Cài vào Home Assistant

Cần: Home Assistant 2026.2 trở lên (hacs.json; test chạy trên 2026.2.3), loa R1 cùng mạng LAN với HA.

1. Chép thư mục `custom_components/r1_speaker` của kho này vào `<cấu hình HA>/custom_components/`
   (ví dụ `/config/custom_components/r1_speaker`). Giữ nguyên cả thư mục con `www/` (chứa thẻ)
   và `translations/`.
2. **Khởi động lại Home Assistant** (Cài đặt → Hệ thống → ⋮ → Khởi động lại).
3. Cài đặt → Thiết bị & dịch vụ → **Thêm tích hợp** → tìm **Phicomm R1 Speaker** →
   nhập **địa chỉ IP của loa** và **cổng điều khiển/EQ** (mặc định **8080**, đã đo: `get_eq_config`
   trả lời ở cổng này). Bấm Gửi: tích hợp kiểm bằng một lần `get_info`; không đọc được thì báo
   «Không đọc được loa». Nên đặt IP tĩnh/giữ chỗ DHCP cho loa.
4. Xong là có thiết bị **Phicomm R1** với các thực thể:

| Thực thể | Việc |
|---|---|
| `number.phicomm_r1_eq_60_hz` … `_14_khz` | 5 dải EQ, −1500…1500 mB (giới hạn do loa báo) |
| `switch.phicomm_r1_eq` / `_bass_boost` / `_loudness` | bật/tắt EQ, bass, loudness |
| `number.phicomm_r1_bass_strength`, `_loudness_gain` | cường độ bass, độ lợi loudness |
| `select.phicomm_r1_eq_preset` | preset của loa (**chỉ hiển thị**, chọn sẽ báo lỗi) |
| `number.phicomm_r1_volume`, `switch.phicomm_r1_dlna`, `_airplay` | âm lượng, DLNA, AirPlay |
| `media_player.r1_loa` | phát tiếng của HA ra loa qua DLNA (TTS) — xem `PHAT-RA-LOA.md` |
| `assist_satellite.r1`, `number.r1_tang_mic`, `switch.r1_tat_mic`, `select.r1_tro_ly` | vệ tinh Assist, tăng mic, tắt mic, chọn pipeline |
| `binary_sensor.r1_bo_dam` | kênh phát về loa của bộ đàm (chẩn đoán) |

> **Lệnh chưa xác nhận.** Chỉ `set_eq_bandlevel` (5 dải) và `set_bass_enable` đã được ghi thử
> thật trên loa. Âm lượng đã nghe xác nhận (đặt qua APK, cần APK bản mới). Bật/tắt EQ, cường độ bass, loudness, DLNA/AirPlay đã viết theo tài
> liệu dịch ngược nhưng **chưa thử ghi**; thực thể có thuộc tính `confirmed: false` và thẻ gắn
> nhãn «chưa xác nhận». Loa không nhận lệnh thì HA báo lỗi chứ không đổi trạng thái giả.

Nhạc (cổng 8082): AI box đã gỡ nên **dịch vụ nhạc không còn được đăng ký** (mã vẫn nằm ở
`music.py`, cờ `MUSIC_SERVICES` trong `media_player.py`).

### Tuỳ chọn (đổi sau khi đã thêm)

Cài đặt → Thiết bị & dịch vụ → Phicomm R1 Speaker → **Cấu hình**. HA nạp lại tích hợp khi lưu.

| Mục | Ý nghĩa | Mặc định |
|---|---|---|
| Địa chỉ IP loa, cổng điều khiển/EQ | đổi thì kiểm lại bằng `get_info`, sai thì không lưu | lúc thêm; cổng 8080 |
| Địa chỉ HA mà loa gọi tới (`ha_url`) | xem mục 3.5; kiểm ngay khi lưu | trống = tự đoán |
| Đổi khoá URL bộ đàm | sinh khoá mới; dòng go2rtc cũ ngừng chạy | tắt |
| Chỉnh thông số nâng cao | tích để sang bước hai: ngưỡng tiếng người / im bao lâu / giữ đầu câu / chờ loa tắt của bộ đàm; khử tạp, AGC, hạn đỉnh phía HA; sáu tham số đàm thoại song công | tắt (mọi số là mặc định CHƯA ĐO trên R1) |

**Khoá và cổng nghe mic KHÔNG phải nhập, cũng không phải copy sang loa.** Khi thêm loa, HA tự sinh khoá nghe mic
(24 byte ngẫu nhiên) và cấp cổng nghe riêng (từ 18765 trở lên, không trùng loa khác). **Ghép tự động:** APK trên loa bị
từ chối (khoá cũ/trống) thì tự gọi `POST /api/r1_speaker/ghep`; HA trao khoá đúng MỘT lần, và chỉ cho địa chỉ nguồn
trùng IP loa của mục đang chờ ghép; APK lưu khoá+cổng rồi nối lại. Cửa ghép đóng ngay khi APK xác thực thành công
(app khác trên loa không xin được) và TỰ MỞ LẠI khi loa gửi khoá sai (APK đã mất khoá) — đánh đổi có chủ ý: trong lúc
cửa mở, app nào trên loa cũng xin được khoá; chỉ áp dụng cho khoá do HA sinh. Xoá rồi thêm lại tích hợp, hoặc tích «Ghép lại APK» trong Tuỳ chọn → khoá mới và cửa
ghép mở lại; APK tự lấy khoá mới sau vài giây. Cài APK lần đầu chỉ cần địa chỉ HA:
`am start -n vn.r1.bodam/.ManHinhChinh --es host <IP-HA> --ei port 18765 --ez bat true` (cổng HTTP của HA mặc định
8123). Lệnh kèm khoá vẫn có ở thẻ → Cài đặt → Kết nối (quản trị viên) cho ai muốn cấp tay. Khoá/cổng đã đặt tay từ
phiên bản cũ vẫn giữ và KHÔNG có cửa ghép.

**Cài đặt chi tiết** (ngưỡng tiếng người, khử tạp, AGC, hạn đỉnh, đàm thoại song công, 19 mục) chỉnh thẳng ở thẻ →
Cài đặt → Âm thanh → «Cài đặt nâng cao» (dịch vụ `r1_speaker.set_advanced_option`; mục khác mặc định có dấu `*`).
Đổi một mục nạp lại tích hợp để áp dụng (mic nối lại sau vài giây). Vẫn còn ở Tuỳ chọn → «Chỉnh thông số nâng cao».

**Nhiều loa:** thêm tích hợp lần nữa với IP loa khác. Mỗi loa có khoá, cổng nghe, phiên song công, đèn và thực
thể riêng (tên thêm hậu tố `_2`, `_3`…). Thẻ gộp tự hiện hàng chọn loa (theo tên thiết bị, đổi tên ở trang thiết bị của HA) khi có từ hai loa; có thể ghim một loa bằng `device_id`. Dịch vụ nhận `entity_id` của loa cần
điều khiển.

Giá trị bằng mặc định **không được lưu**: khi sau này đo xong và đổi mặc định, các mục bạn chưa
chỉnh tay tự theo.

## 2. Thẻ Lovelace chỉnh EQ và thẻ đàm thoại

Tích hợp **tự đăng ký tài nguyên Lovelace** `/r1_speaker/r1-card.js?v=<phiên bản>` khi HA khởi động xong (cách của tích hợp YouTube;
đổi phiên bản trong `manifest.json` là `?v=` đổi theo, trình duyệt bỏ bản cũ) và gỡ ba tài nguyên thẻ con cũ nếu còn. Chỉ có **một thẻ**
`type: custom:r1-card` (thẻ gộp, tự nạp thẻ đàm thoại/EQ/chức năng/cài đặt). KHÔNG dùng `add_extra_js_url`: nạp sớm làm giao diện HA không thấy thẻ
(«Custom element not found»). Chế độ YAML thì danh sách tài nguyên chỉ-đọc: tự thêm `/r1_speaker/r1-card.js` (Mô-đun JavaScript).

Thêm thẻ (chế độ YAML):

```yaml
type: custom:r1-eq-card
```

Thẻ tự tìm các thực thể của tích hợp (qua nền tảng `r1_speaker`, không dựa vào tên). Có nhiều
loa thì thêm `device_id: <mã thiết bị>`. Chỉ định tay khi cần:

```yaml
type: custom:r1-eq-card
entities:
  eq_enable: switch.phicomm_r1_eq
  bass: switch.phicomm_r1_bass_boost
  loudness: switch.phicomm_r1_loudness
  bass_strength: number.phicomm_r1_bass_strength
  loudness_gain: number.phicomm_r1_loudness_gain
  volume: number.phicomm_r1_volume
  eq_preset: select.phicomm_r1_eq_preset
  bands: [number.phicomm_r1_eq_60_hz, number.phicomm_r1_eq_230_hz, number.phicomm_r1_eq_910_hz,
          number.phicomm_r1_eq_3_6_khz, number.phicomm_r1_eq_14_khz]
```

Thẻ có: 5 thanh dải (giới hạn lấy từ loa báo), công tắc EQ, bass, loudness, thanh cường độ bass
và độ lợi loudness, âm lượng, preset (chỉ hiển thị, đang khoá), khoảng giá trị của dải. Thẻ
**không gọi loa trực tiếp**: đọc trạng thái thực thể, ghi bằng dịch vụ `number.set_value`,
`switch.turn_on/off`. Loa không phản hồi thì thẻ hiện «Loa không phản hồi» và khoá các điều
khiển. Nếu thẻ không hiện (HA không có `frontend`), thêm tay: Cài đặt → Bảng điều khiển →
⋮ → Tài nguyên → `/r1_speaker/r1-eq-card.js`, loại **Mô-đun JavaScript**.

**Thẻ cài đặt (ẩn):** `type: custom:r1-settings-card` (tự nạp từ `/r1_speaker/r1-settings-card.js`).
Mặc định chỉ có tiêu đề và nút «Cài đặt»; bấm nút mới mở ba nhóm Âm thanh / Ánh sáng / Kết nối. Đèn
theo chức năng chỉ SÁNG khi có dịch vụ đèn trên loa (chưa có) — xem `DEN-LED.md`.

## 3. Assist và bộ đàm

**Thẻ đàm thoại `custom:r1-talk-card`** (tự nạp cùng thẻ EQ): nút Đàm thoại / Kết thúc, **trạng thái mic
luôn hiện bằng chữ** (Tắt / Đang nghe / Đang gửi; trạng thái không đọc được hiện «Không rõ», không giả làm
«Tắt»), công tắc tắt mic, tạm dừng / phát nhạc, thẻ EQ nhúng bên dưới (`show_eq: false` để bỏ). Thẻ chỉ đọc
trạng thái và gọi dịch vụ HA.

### 3.1 Vệ tinh Assist (`assist_satellite.r1`)

Mô hình giống camera (`dahua_talk`): mic loa → HA → pipeline Assist → trả lời phát ra
`media_player.r1_loa`. **Cần luồng mic từ loa (mục 4)**: có APK `vn.r1.bodam` + đầu nhận mic của
HA nhưng chưa kiểm đầu-cuối trên loa thật. Khi chưa có luồng, `assist_satellite.r1` ở trạng thái
**unavailable** (không sập; đường nối ra loa tự thử lại mỗi 2 giây).

Khi đã có luồng mic:

1. Đặt Máy chủ mic + cổng mic trong Tuỳ chọn.
2. Từ gọi do **pipeline** quyết: Cài đặt → Trợ lý giọng nói → chọn pipeline → mục Từ gọi (ví dụ
   openWakeWord) rồi chọn pipeline đó ở `select.r1_tro_ly`.
3. `number.r1_tang_mic` (0–30 dB) bù độ nhỏ của mic; `switch.r1_tat_mic` bật = **đóng hẳn luồng
   mic** (không nhận byte nào).
4. Trả lời nối tiếp (hội thoại hỏi lại) nghe thẳng không cần từ gọi; thông báo:
   `assist_satellite.announce` / `start_conversation`.

### 3.2 Bộ đàm nửa công

Như bộ đàm camera: nói từ điện thoại/trình duyệt, tiếng ra loa R1; **chỉ mở loa khi có tiếng
người**, đóng sau một quãng im, giữ đầu câu; suốt lúc loa mở HA **bỏ tiếng mic** để loa khỏi tự
nghe mình. Luân phiên, không song công.

```
Trình duyệt (thẻ WebRTC Camera, mic) → go2rtc → exec ffmpeg → POST A-law 8 kHz
   → HA /api/r1_speaker/intercom/<mã loa>?k=<khoá>   (cổng thoại → nâng 16 kHz)
   → TCP PCM16 16 kHz → [dịch vụ nhận PCM trên loa: CHƯA CÓ] → loa
Loa → TCP PCM16 16 kHz → HA (mic.py) → /api/r1_speaker/mic/<mã loa>?k=<khoá> → go2rtc → người nghe
```

Cần: go2rtc ≥ 1.9.10, thẻ WebRTC Camera, HA mở bằng https (để trình duyệt cho dùng mic), và
**hai dịch vụ phía loa (mục 4)**. Bước:

1. Đặt **cổng nhận tiếng phát** (khác 0) và Máy chủ mic trong Tuỳ chọn.
2. Công cụ nhà phát triển → Hành động → `r1_speaker.get_intercom_source` với
   `entity_id: media_player.r1_loa` (thêm `ha_url: http://<IP HA>:8123` nếu go2rtc không cùng
   mạng/máy với HA; bảng chọn `ha_url` giống `ha-camera-talk`). Trả hai dòng:
   - `talk`: dán vào danh sách nguồn của luồng go2rtc (trong dấu nháy kép). Dòng này **giống hệt
     dòng đã chạy thật ở bộ đàm camera**; đừng sửa ba cờ `-probesize 32 -analyzeduration 0
     -fflags nobuffer`.
   - `listen`: nguồn nghe mic loa. **CHƯA thử với go2rtc thật** — nếu go2rtc không nhận cú pháp,
     dùng URL `…/api/r1_speaker/mic/…` làm nguồn `ffmpeg:` theo cách bạn quen.
3. Kiểm từ máy chạy go2rtc: `curl -s -o /dev/null -w '%{http_code}\n' -X POST "<URL>"` — `401` =
   sai khoá/mã loa, `503` = chưa cấu hình cổng phát hoặc mic không sẵn sàng, `409` = đang có
   phiên khác, `200` = nhận.
4. `binary_sensor.r1_bo_dam`: **unavailable** = chưa đặt cổng phát; **unknown** = chưa thử;
   **on** = lần phát gần nhất thành công; **off** = lần gần nhất hỏng (loa không nhận). Hỏng thì
   bộ đàm không làm sập gì, mic được nhả và thử lại ở lần nói kế.

> **Bảo mật.** Khoá nằm trong URL (go2rtc không gửi được header `Authorization`) và cho phép
> **nói vào loa** và **nghe mic loa**. Đừng dán URL ra ngoài; đừng đưa URL đi qua internet; đổi
> khoá bằng Tuỳ chọn → Đổi khoá URL bộ đàm. Muốn tạm thôi nghe: bật `switch.r1_tat_mic` (đóng
> luồng, URL nghe trả 503). Đừng đặt loa ở nơi người ngoài nói được từ gọi để ra lệnh nhà.

Giới hạn đã biết: HA chưa xử lý trường hợp vệ tinh đang giữa một lượt Assist mà bộ đàm mở (mic
bị giữ nên lượt ấy hết giờ); TTS qua DLNA và bộ đàm PCM có thể phát chồng lên nhau.

### 3.3 Đàm thoại: nút, phiên, nhạc (HA làm máy chủ Assist)

**Nghe tiếng trong nhà (một chiều, chỉ quản trị viên).** Nút «👂 Nghe tiếng trong nhà» trên tab Đàm thoại phát tiếng từ
mic loa ra điện thoại, KHÔNG lọc tiếng người nên nghe được cả tiếng động xung quanh (nhạc, tiếng nói, tiếng bước
chân), không mở phiên đàm thoại, không phát gì ra loa và không cần mic điện thoại (nên chạy cả qua `http://IP`).
Loa không có đèn báo khi bị nghe, nên: chỉ quản trị viên thấy nút, thẻ ghi rõ «ĐANG NGHE», có thanh mức tiếng, HA ghi
nhật ký lúc bắt đầu/kết thúc, và kênh đóng khi ẩn tab/rời trang hoặc khi tắt mic loa (`switch.r1_tat_mic`). Muốn thử:
phát nhạc ra loa rồi bấm nút từ điện thoại ở phòng khác (đứng cạnh loa sẽ nghe cả tiếng trực tiếp lẫn tiếng qua kênh,
trễ nhau chừng nửa giây).

**Nói bằng micro điện thoại (trong thẻ, như bộ đàm camera của c2a).** Trên tab Đàm thoại: **Giữ để nói** = mic
điện thoại đi ra loa, thả ra là nghe lại tiếng loa; **Bật mic luôn** = mic điện thoại mở liên tục (bấm lần nữa để
tắt). Lần giữ đầu trình duyệt hỏi quyền mic và mở kênh (một WebSocket hai chiều về chính HA, xác thực bằng đường
dẫn đã ký của HA); kênh mở sẵn thì lần sau nói liền, nút «Đóng kênh điện thoại» hoặc ẩn tab/rời trang là đóng hẳn
(mic không chạy ngầm). **Trình duyệt chỉ cho dùng mic khi mở HA bằng https**: qua địa chỉ ngoài (tên miền
Cloudflare) được; qua `http://<IP>:8123` trong nhà thì thẻ báo rõ và không mở gì. Mỗi loa chỉ một điện thoại một
lúc (người thứ hai bị từ chối). Kiểm bằng test HA + Chrome mic giả; CHƯA thử trên điện thoại thật với loa thật.

HA là máy chủ Assist: pipeline chọn ở `select.r1_tro_ly` lo STT / hiểu lệnh / TTS; loa chỉ là
tai và miệng (`assist_satellite.r1` + `media_player.r1_loa`).

- **Phiên Assist** (từ đánh thức trên loa hoặc HA): tạm dừng nhạc đang phát trên loa (DLNA/YouTube qua
  `media_player.r1_loa`) và mở MỘT phiên Assist nghe thẳng (bỏ bước từ gọi). Phiên xong thì nhạc
  phát lại (nhạc đang phát đúng URI cũ → `media_play`; URI đã bị TTS thay → đặt lại đúng URI cũ và
  tua về vị trí cũ). Công tắc tắt mic đóng phiên ngay. (Nút «Đàm thoại» / «Kết thúc» đã bỏ.)
- **`switch.r1_dam_thoai`** (đàm thoại song công, mic mở liên tục): bật = mở phiên và giữ mở («Bật mic
  luôn»), tắt = đóng. Thuộc tính `giu_mo` cho biết phiên do công tắc giữ mở hay chỉ đang giữ nút. Thẻ
  «Giữ để nói» mở/đóng phiên bằng dịch vụ `r1_speaker.start_duplex` / `stop_duplex`. Cần APK loa đang
  nối về HA (đường phát xuống loa đi qua chính kết nối đó).
- **`switch.r1_mic_loa_song_song`** («Mic loa song song»): bật = mic và loa SONG SONG (nghe và nói cùng
  lúc, có khử vọng); tắt = NỬA CÔNG (luân phiên, bỏ mic khi loa đang phát). Chỉ chọn kiểu đàm thoại,
  không liên quan tới cách thao tác mic («Giữ để nói» / «Bật mic luôn»). Nhớ qua lần khởi động HA.
- **Một phiên một lúc**: bấm khi phiên khác (nút / từ đánh thức / bộ đàm) chưa đóng → bị TỪ CHỐI
  ngay kèm lời nêu nguồn và tuổi phiên đang mở (thuộc tính `tu_choi_gan_nhat`, sự kiện
  `r1_speaker_session_refused`). Phiên có đồng hồ canh: mic không nối được sau 5 giây hoặc quá 60 giây
  thì tự đóng, nhạc phát lại.
- **`tts.speak` / thông báo (`announce`) trên `media_player.r1_loa`**: nhạc tạm dừng trước, tin phát,
  nhạc phát lại sau tin. Lệnh trả về ngay, không chờ hết tin. Nhạc thường (không `announce`) không bị đụng.
- **Nhạc YouTube**: tích hợp YouTube của HA (`tritue_youtube_player`) gọi `media_player.play_media`
  với luồng do HA ký lên `media_player.r1_loa` → renderer DLNA của loa. Không dùng cổng 8082 (AI box đã gỡ).
  CHƯA ĐO: luồng proxy hết hạn khi đặt lại URI sau tin; loa có nhận tua (`media_seek`) không.
- **`media_player.r1_loa`** tự điều khiển renderer DLNA của loa (không cần thêm `dlna_dmr`): phát, tạm dừng, dừng, tua, và khai
  trạng thái, tên bài, thời lượng, `idle_reason`. Xem `docs/PHAT-RA-LOA.md`.
- **`sensor.r1_trang_thai_mic`**: `tat` (không nghe), `nghe` (loa chờ từ đánh thức, chưa gửi gì về HA),
  `gui` (byte mic đang về HA). Chế độ `ha`: luồng nối là `gui`. Chế độ `speaker`: `gui` chỉ trong phiên.
- **`number.r1_tang_mic`** 0–30 dB, mặc định **+12 dB (CHƯA ĐO trên mic loa)**; khuếch đại tuyến tính,
  chặn cứng (mặc định không lọc ồn; khử tạp/AGC phía HA là tuỳ chọn, mặc định tắt). Đã chỉnh tay thì giá trị được nhớ và thắng mặc định.

### 3.4 Từ đánh thức: `ha` hay trên loa (`wake_mode`)

| `wake_mode` | Từ đánh thức dò ở | Mic về HA | Trạng thái |
|---|---|---|---|
| `ha` (mặc định) | pipeline của HA (openWakeWord…) | liên tục khi luồng nối | dùng được ngay nếu có luồng mic |
| `speaker` | TRÊN LOA | chỉ sau trigger / nút | **phía loa CHƯA CÓ (CHỜ)** |

Chọn `speaker` khi chưa có phía loa: HA không nối mic, `sensor.r1_trang_thai_mic` hiện `tat`, chỉ nút
đàm thoại mở được phiên. Hợp đồng trigger: `HOP-DONG-PHIA-LOA.md` mục 4c.

### 3.5 `ha_url`: địa chỉ HA mà loa / go2rtc gọi tới

Đặt ở tuỳ chọn, **kiểm ngay khi lưu** và sai thì không lưu gì: dạng `http(s)://máy[:cổng]`;
`127.0.0.1` / `localhost` / `0.0.0.0` bị từ chối (trên loa hay go2rtc chúng trỏ về chính nó, không
phải HA); HA phải tự gọi được `<ha_url>/api/r1_speaker/ping` (khoá riêng) và nhận đúng trả lời.
Phép thử này chỉ chứng minh địa chỉ đúng là HA này; việc loa với tới được vẫn cần thử trên mạng thật.
Dịch vụ `get_intercom_source` / `get_wake_endpoint` lấy địa chỉ này khi không truyền `ha_url`.

**Khoá URL bị đổi / sai**: lời gọi bằng khoá sai nhận `401` + `Retry-After: 60`, và HA hiện MỘT thông
báo «khoá bị đổi hoặc sai» (gọi lặp không sinh thêm thông báo). Đổi khoá ở tuỳ chọn (`rotate_intercom_key`),
dán lại dòng mới (`get_intercom_source`, `get_wake_endpoint`); thông báo tự mất.

### 3.6 Truy cập từ xa (4G)

Mic trên trình duyệt (cho thẻ/Assist trên điện thoại) chỉ chạy trên **HTTPS**: cần HA truy cập qua
HTTPS (Nabu Casa hoặc đường tunnel HTTPS đã có). VPN trên máy HA có thể đổi đường đi của gói tin tới loa
và `ha_url`. Tích hợp này không tự cấu hình mạng nào.

## 4. Phần trên loa

Ba phần cần chạy **trên loa**. Mic có APK `vn.r1.bodam` (thư mục `apk/`, cài bằng ADB, xem
`README.md`); hai phần còn lại **chưa tồn tại** và chưa có phép đo nào chứng minh cách làm.

| Cần | Ghi chú | Trạng thái |
|---|---|---|
| Đẩy **PCM16 mono 16 kHz** từ mic về HA | APK `vn.r1.bodam` (bản build 245) nối VÀO HA (`<IP HA>:<cổng nghe mic>`), khung `hello` kèm khoá — hợp đồng ở `HOP-DONG-PHIA-LOA.md` mục 2b | **APK đã build; CHƯA cài/kiểm trên loa thật cùng HA thật** (mic có ra tiếng không, ai đang giữ mic, độ trễ) |
| Dịch vụ TCP nhận **PCM16 mono 16 kHz** và phát ra loa | HA nối vào `play_host:play_port` | **CHƯA CÓ — CHỜ ĐO** (đường phát PCM thô) |
| Từ đánh thức chạy trên loa, `POST` trigger về HA | `wake_mode = speaker`, `HOP-DONG-PHIA-LOA.md` mục 4c | **CHƯA CÓ — CHỜ** (cần chủ máy duyệt riêng) |

Hợp đồng chi tiết, danh sách việc cần đo và các phương án đã phân tích: `HOP-DONG-PHIA-LOA.md`,
`THIET-KE-MIC.md`. Không có các dịch vụ này thì đừng đặt cổng phát: tích hợp vẫn chạy, phần
nghe/bộ đàm chỉ ở trạng thái unavailable.

## 5. Kiểm tra / phát triển

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-test.txt   # HA 2026.2.3 qua pytest-homeassistant-custom-component
.venv/bin/python -m pytest                       # loa giả ở 127.0.0.1, KHÔNG chạm loa thật
.venv/bin/python -m bandit -r custom_components -lll -q
```

Test thẻ trong Chrome không đầu: `tests/test_the_chrome.py` (tự bỏ qua nếu không có Chrome).

## 6. Sự cố thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| Thêm tích hợp báo «Không đọc được loa» | IP/cổng sai hoặc cổng 8080 bị chặn; thử cổng khác trong Tuỳ chọn. |
| Thực thể EQ unavailable | Loa không trả `get_eq_config`; xem log `custom_components.r1_speaker`. Thẻ hiện «Loa không phản hồi». |
| Kéo thanh EQ mà số không đổi | Lệnh bị loa bỏ qua (chỉ `set_eq_bandlevel` đã xác nhận); lần hỏi kế (10 giây) HA lấy lại số thật. |
| Thẻ báo «Custom element not found» | Tích hợp tự thêm tài nguyên `/r1_speaker/r1-card.js`; nếu chưa có (bảng điều khiển YAML) hãy thêm tay, rồi tải lại cưỡng bức trang. |
| `assist_satellite.r1` unavailable | Chưa có/đứt luồng mic (mục 4), hoặc `switch.r1_tat_mic` đang bật là chủ động (idle, không phải lỗi). |
| POST bộ đàm trả 503 | Chưa đặt cổng nhận tiếng phát. |
