# Đèn LED của loa R1 — phần phía HA

Trạng thái: **phía HA đã viết và test bằng sink trong bộ nhớ; phía loa CHƯA CÓ gì.** Từ HA tới
đèn loa không có đường nào: lệnh duy nhất chạy được là `/system/bin/lights_test set <mặt nạ> <rgb 6 số>`,
mà nó chỉ chạy được TRÊN LOA (shell hoặc một dịch vụ trên loa — dịch vụ đó chưa được duyệt, chưa
có). Vì vậy HA lưu cài đặt và tính ra đèn nào cần sáng nhưng **không gửi gì tới loa** cho tới khi có
một bản `LightsSink` thật. Giao diện: `den_port.py`; bộ điều khiển: `den.py`; hiệu ứng:
`hieu_ung.py`; tóm tắt cho thẻ: `cai_dat.py` (`sensor.r1_cai_dat`); thẻ: `www/r1-settings-card.js`.

## 1. Phần cứng đã kiểm (chủ máy xác nhận bằng mắt)

| Đèn | Mặt nạ | Màu | Ghi chú |
|---|---|---|---|
| Viền | `7fffff8000` | CHỈ TRẮNG | bật `ffffff`, tắt `000000`, chỉnh sáng bằng giá trị trắng (`404040` mờ rõ). Hiệu ứng thở ID 202 của firmware KHÔNG chạy. |
| Đáy | `7fff` | RGB | xanh lá `00ff00` và xanh dương `0000ff` đã xác nhận; đỏ `ff0000` chưa chắc (chưa phân biệt được với mặt nạ) |

`/system/etc/lights_effects.conf` có danh mục hiệu ứng của firmware (ID 200–255 thở/sáng liên tục,
300–315 và 400–412 chuyển dần) nhưng `lights_test set` không áp dụng được ID hiệu ứng từ shell → hiệu
ứng ở HA là **dữ liệu** (danh sách bước màu + thời gian), không phải ID của firmware.

### Đèn theo nhạc của firmware — ĐIỀU KHIỂN ĐƯỢC (đã thử trên loa 22/10/2026)

`get_info` cổng 8080 có `music_light_enable`, `music_light_luma`, `music_light_chroma`. Ghi chúng qua
cổng 8080 không được; đường thật (đọc từ app AI box và app player của loa) là dịch vụ hệ thống
**`msgcenter`** (`android.os.IMessageCenterService.sendMsg(nhóm, mã, giá trị)`), mà MỘT APP THƯỜNG gọi
được bằng phản chiếu (không cần quyền shell):

| nhóm | mã | giá trị | tác dụng |
|---|---|---|---|
| 4 | 64 | 0 / 1 | tắt / bật đèn nhạc (`music_light_enable`) |
| 4 | 65 | 0–100 | độ sáng (`music_light_luma`) |
| 4 | 66 | 1–100 | sắc độ (`music_light_chroma`) |
| 4 | 67 | – | chế độ co giãn (chưa dùng) |

Đã gửi từng mã rồi đọc lại bằng `get_info`: đổi đúng, đã trả về giá trị cũ. HA không tới `msgcenter`
trực tiếp: HA gửi khung `{"type":"den_nhac","ma":65,"gia_tri":50}` xuống APK loa trên kết nối mic đã
xác thực; APK kiểm chặt định dạng và khoảng giá trị rồi gọi `msgcenter` (`LenhDieuKhien.java`,
`TrungTamTin.java`). Thực thể: `number.r1_do_sang_den_nhac`, `number.r1_sac_do_den_nhac`,
`switch.r1_den_nhac` — chỉ dùng được khi APK đang nối về HA. Đây là đèn của FIRMWARE, khác với «hiệu ứng
khi phát nhạc của HA» (chức năng `phat_nhac` ở dưới, chưa ra đèn).

**Đèn viền (trắng) và đèn đáy (RGB) theo mức sáng tuỳ ý** cần quyền shell nên đi vòng qua một **máy chủ đèn**:
HA gửi `{"type":"den_vien","muc":0-255}` / `{"type":"den_day","rgb":"rrggbb"}` / `{"type":"den_hoi"}` xuống APK
(kiểm chặt, `LenhDieuKhien.java`), APK xếp vào hàng đợi riêng «mới nhất thắng» (`DenHangDoi.java`, không chặn
đường phát tiếng) rồi gọi máy chủ đèn quyền shell qua TCP 127.0.0.1:18771 (`DenCau.java` →
`apk/nguon/den/.../MayChuDen.java`, chỉ chạy `lights_test set <mặt nạ> <rgb>`). APK báo
`{"type":"den_trang_thai","san_sang":true|false}` lên HA (lúc nối và mỗi lần HA hỏi, 30 giây một lần);
thực thể `binary_sensor.r1_dich_vu_den` hiện máy chủ đèn có chạy không, `number.r1_do_sang_den` là độ sáng
chung 0–100 % nhân vào mọi chức năng. **Máy chủ đèn không tự sống sau khi loa khởi động lại**: phải có một
tiến trình `scripts/den_loa.sh <IP-loa> giam-sat` chạy ở máy khác trong nhà. **Chưa có xác nhận bằng mắt của chủ
nhà cho đường HA → APK → máy chủ đèn đầu-cuối** (phần HA và APK có test; đèn thật chỉ đã thử riêng
`lights_test` và vòng loopback). Không dùng hiệu ứng ID 500–505 của AI box (CHƯA thử).

Trước đó, vì sao cần máy chủ đèn: `lights_test` từ app (uid app không mở được
`/sys/class/leds/multi_leds0/led_color`, thoát 255). AI box điều khiển đèn viền/đáy bằng cách gửi
nhóm `0x1000` + ID hiệu ứng có sẵn trong `/system/etc/lights_effects.conf` (500/501/502 đáy đỏ/xanh lá/
xanh dương, 503 viền trắng, 504/505 tắt đáy/viền…) — chỉ chọn hiệu ứng có sẵn, không chỉnh mức sáng
tuỳ ý; CHƯA thử.

## 2. Hợp đồng `LightsSink` (`den_port.py`)

```
available -> bool
set_rim(level: int 0..255)         # viền: chỉ MỨC trắng, không có tham số màu → luật «chỉ trắng» do chữ ký hàm bảo đảm
set_base(rgb: (r, g, b))           # đáy
play_effect(steps, *, repeat)      # trả ngay; sink tự chạy nền (bản trên loa có thể lặp tại chỗ)
stop_effect()                      # dừng hiệu ứng đang chạy
```

* `Step(base: RGB | None, rim: int | None, seconds)`; `None` = giữ nguyên. `run_steps()` là bộ chạy
  sẵn cho sink không có bộ chạy riêng (đặt viền, đặt đáy, giữ `seconds`, tối thiểu `MIN_STEP_S`).
* `rim_write(level)` / `base_write(rgb)` cho ra đúng cặp (mặt nạ, hex) mà `lights_test set` nhận;
  bản thật chỉ cần gửi `Write.command`. Test dùng `tests/memory_lights.py`.
* HA luôn `stop_effect()` TRƯỚC khi ghi đèn theo cách khác và đánh số thế hệ: bản áp dụng cũ bị bỏ
  khi bản mới đến — không bao giờ có hai nơi cùng ghi đèn.
* Mặc định `NullLights`: `available = False`, trạng thái `CHO_PHIA_LOA`. Cắm sink thật:
  `entry.runtime_data.lights.set_sink(sink)`.

## 3. Cài đặt theo chức năng (`den.py`)

Tám chức năng, mỗi chức năng có: bật/tắt, dùng đèn viền (trắng), màu đèn đáy, hiệu ứng, độ sáng 0–100.
Chức năng đang hiệu lực chọn theo thứ tự ưu tiên (đứng trước thắng):

1. `tat_mic` — mic đang tắt (`switch.r1_tat_mic`);
2. `loi` — phiên đóng vì lỗi (`loi`, `loi_pipeline`, `mic_khong_noi_duoc`, `het_gio`) hoặc pipeline báo
   `ERROR` (đấu ở `assist_satellite.on_pipeline_event`); giữ `LIGHT_ERROR_HOLD_S` giây;
3. `phan_hoi` / `nghi` / `nghe` — theo trạng thái `assist_satellite.r1` (HA: TTS_START → responding,
   INTENT_START → processing, STT_START → listening);
4. `dam_thoai` — có phiên mở mà vệ tinh đang rảnh (giữa hai lượt);
5. `phat_nhac` — `media_player.r1_loa` đang phát (chỉ khi chức năng này BẬT);
6. `cho` — chờ từ đánh thức.

Chức năng TẮT = «lúc đó không có đèn» (tắt cả viền lẫn đáy); riêng `phat_nhac` tắt thì coi như không có
nhạc (rơi xuống `cho`). Đèn viền chỉ có trắng nên chức năng dùng viền chỉ chọn «dùng viền hay không»
và độ sáng; màu chỉ áp cho đèn đáy.

### Mặc định — ĐỀ XUẤT, CHƯA ĐO (không số nào được nhìn thử trên loa)

| Chức năng | Bật | Viền | Màu đáy | Hiệu ứng | Sáng |
|---|---|---|---|---|---|
| chờ / đánh thức | tắt | không | xanh dương | không | 20 |
| nghe | bật | có | xanh dương | không | 60 |
| nghĩ | bật | không | xanh dương | thở | 60 |
| phản hồi | bật | có | xanh lá | không | 60 |
| đàm thoại | bật | có | xanh lá | thở | 50 |
| phát nhạc | **tắt** | không | xanh lá | cầu vồng | 40 |
| lỗi | bật | có | **đỏ** | nhấp nháy | 80 |
| tắt mic | bật | có | **đỏ** | không | 25 (viền = `404040`, mức «mờ rõ» đã thấy) |

Lý do: chỉ dùng xanh lá/xanh dương (đã xác nhận) trừ ĐỎ; «lỗi» và «tắt mic» dùng đỏ nhưng **luôn kèm
đèn viền trắng** để vẫn thấy được nếu đèn đáy không hiện đỏ. «Chờ» tắt vì đèn thường trực gây phiền ban
đêm; «phát nhạc» tắt vì firmware có đèn nhạc riêng (lệnh chưa rõ) — bật cả hai có thể chồng nhau.
Cài đặt chỉ lưu phần KHÁC mặc định (`helpers.storage.Store`, khoá `r1_speaker.lights.<entry_id>`), nên
khi đo xong và đổi mặc định thì mục chưa chỉnh tay tự theo.

### Dịch vụ HA

* `r1_speaker.set_light_function` — `entity_id`, `function`, tuỳ chọn `enabled`, `rim`, `color` (`#rrggbb`),
  `effect`, `brightness` (0–100).
* `r1_speaker.set_music_light` — `entity_id`, tuỳ chọn `enabled`, `effect`, `brightness` (= hồ sơ của
  chức năng `phat_nhac`).
* `r1_speaker.preview_light` — `entity_id`, `function`, `seconds` (1–30): hiện đèn của chức năng đó rồi
  trả về trạng thái thật (cần sink thật mới thấy).

## 4. Danh mục hiệu ứng (`hieu_ung.py`)

Nguồn ý tưởng: danh mục hiệu ứng WLED, https://kno.wled.ge/features/effects/ (đọc 22/10/2026; chỉ đọc
tên + mô tả, KHÔNG lấy mã). Mỗi hiệu ứng chỉ cần «đổi màu đáy theo thời gian + viền trắng bật/tắt/mờ».

| id | Tên | Mục WLED (ID) | Viền làm gì |
|---|---|---|---|
| `tho` | Thở | Breathe (2) | sáng tối theo đáy |
| `cau_vong` | Cầu vồng | Colorloop (8) | mờ cố định (viền không đổi màu) |
| `nhap_nhay` | Nhấp nháy | Blink (1) | nháy cùng đáy |
| `nhip_tim` | Nhịp tim | Heartbeat (100) | đập cùng đáy |
| `phao_hoa` | Pháo hoa nhỏ | Fireworks (42) | bừng cùng đáy |
| `chop` | Chớp | Strobe Mega (25) | chớp cùng đáy |

Đã BỎ: Chase/Scan/Wipe/sóng/đuổi — cần ghi từng LED, mà chưa biết các bit của mặt nạ có địa chỉ riêng
từng LED hay không (mới thấy `7fff` = cả đáy, `7fffff8000` = cả viền). Quy ước đèn của loa thương mại
(Alexa, Google…) không được kiểm từ nguồn nào ở đây nên không viết vào.

Pháo hoa dùng `random.Random` truyền seed vào (test xác định được). Tốc độ đổi đèn tối đa thật
(mỗi `lights_test` là một tiến trình) CHƯA ĐO nên mọi số thời gian là đề xuất.

## 5. Thẻ cài đặt (`r1-settings-card`)

Mặc định chỉ hiện tiêu đề + nút «Cài đặt». Bấm nút mới mở bảng, ba nhóm:

* **Âm thanh** — âm lượng, EQ 5 dải, tăng mic, tắt mic (thực thể sẵn có); khử tạp / AGC / bộ hạn đỉnh
  chỉ ĐỌC (là tuỳ chọn của mục cài đặt, sửa ở trang Tuỳ chọn: lưu tuỳ chọn nạp lại cả mục, ngắt mic);
* **Ánh sáng** — mỗi chức năng một khối (bật, viền, màu, hiệu ứng, sáng, nút «Thử»), mục hiệu ứng khi phát
  nhạc, đèn nhạc của firmware (chỉ đọc), danh mục hiệu ứng kèm nguồn, và dòng nói thẳng «chưa có dịch
  vụ đèn trên loa» khi `dich_vu_den != san_sang`;
* **Kết nối** — IP loa, cổng, `ha_url`, APK trên loa đang nối hay chưa, cổng nghe mic (HA tự cấp). Khoá nghe mic
  **không bao giờ vào thuộc tính hay thẻ**: nút «Hiện lệnh cài APK» hỏi quản trị viên qua WebSocket
  `r1_speaker/apk_lenh` (chỉ quản trị viên, kết quả chỉ nằm trong bộ nhớ thẻ).

Thẻ KHÔNG gọi loa: chỉ đọc thực thể HA và gọi `number.set_value`, `switch.turn_on/off`,
`r1_speaker.set_light_function`, `r1_speaker.set_music_light`, `r1_speaker.preview_light`. Nạp tự động
như hai thẻ cũ; thêm vào bảng điều khiển: `type: custom:r1-settings-card` (nhiều loa: `device_id`).

## 6. Cần dịch vụ trên loa mới chạy (CHƯA CÓ)

* Mọi thứ liên quan đèn: không có đường từ HA tới `lights_test`. Cần một dịch vụ trên loa (chưa được duyệt)
  thoả `LightsSink`; trong lúc chờ, đèn KHÔNG sáng và thẻ nói rõ.
* Hiệu ứng khi phát nhạc của HA cũng vậy. (Đèn nhạc của FIRMWARE thì đã điều khiển được, xem mục 1.)

## 7. Chưa đo

* Đỏ `ff0000` trên đèn đáy; mọi màu pha (vàng, tím, lục lam…) dùng trong cầu vồng/pháo hoa.
* Chỉnh sáng đèn đáy bằng cách nhân RGB có tuyến tính không; mức sáng tối thiểu nhìn thấy của viền/đáy.
* Bước thời gian ngắn nhất `lights_test` theo kịp; hiệu ứng nào làm được ở tốc độ đó.
* Đèn nhạc của firmware chồng lên hiệu ứng nhạc của HA ra sao.
* Toàn bộ bảng mặc định ở mục 3.
