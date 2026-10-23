# Hướng dẫn chi tiết từng cài đặt — loa Phicomm R1

Tài liệu này giải thích **từng** cài đặt: nó làm gì, chỉnh ở đâu, khoảng giá trị, mặc định, và khi nào nên đổi.
Nhãn «CHƯA ĐO» nghĩa là số mặc định là số hợp lý lấy từ chỗ khác, **chưa đo trên mic/loa R1 thật**: nếu thấy lạ thì
chỉnh theo tai nghe, đừng coi nó là số đúng.

Nơi chỉnh, theo thứ tự nên dùng:

| Nơi | Dùng khi |
|---|---|
| Thẻ `r1-card` (tab Đàm thoại / EQ / Cài đặt) | Hằng ngày: bấm, kéo, thử ngay |
| Trang thiết bị Phicomm R1 (các thực thể) | Đưa vào tự động hoá, kịch bản |
| Tuỳ chọn tích hợp (Cài đặt → Thiết bị & dịch vụ → Phicomm R1 Speaker → Cấu hình) | IP loa, địa chỉ HA, ghép lại APK |
| Dịch vụ HA (`r1_speaker.*`) | Tự động hoá |

---

## 1. Thêm loa và tuỳ chọn tích hợp

**Thêm loa:** Thêm tích hợp → *Phicomm R1 Speaker* → nhập hai ô.

| Ô | Ý nghĩa | Mặc định |
|---|---|---|
| Địa chỉ IP của loa | IP của loa trong mạng nhà (nên đặt IP tĩnh/giữ chỗ DHCP) | trống, phải nhập |
| Cổng điều khiển / EQ | Cổng loa nhận lệnh điều khiển và EQ | 8080 |

HA tự sinh khoá và cấp cổng nghe mic riêng cho loa này; không phải nhập. **Thêm loa thứ hai:** thêm tích hợp lần
nữa với IP khác, mỗi loa có khoá, cổng, phiên, đèn và thực thể riêng (tên có hậu tố `_2`, `_3`…).

**Tuỳ chọn** (Cấu hình của tích hợp; HA nạp lại tích hợp khi lưu):

| Ô | Ý nghĩa |
|---|---|
| Địa chỉ IP / cổng | Đổi thì HA kiểm lại bằng một lần hỏi loa; sai thì không lưu |
| Địa chỉ HA mà loa gọi tới (`ha_url`) | Dạng `http://<IP của HA>:8123`. Để trống = tự đoán. Có nhập thì HA kiểm ngay: không được là `127.0.0.1`/`localhost`, và HA phải tự gọi lại được địa chỉ đó |
| Đổi khoá URL bộ đàm | Sinh khoá mới cho các dòng go2rtc; dòng cũ ngừng chạy |
| Ghép lại APK | Sinh khoá nghe mic mới và mở lại cửa ghép; APK trên loa tự xin khoá mới sau vài giây (dùng khi cài lại APK hoặc thay loa) |
| Chỉnh thông số nâng cao | Sang bước hai: 19 số âm thanh ở mục 4 (cũng chỉnh được ở thẻ) |

---

## 2. Các thực thể của loa

| Thực thể (tên hiển thị) | Loại | Làm gì | Khoảng / ghi chú |
|---|---|---|---|
| Âm lượng | number | Âm lượng NHẠC của loa, đặt qua APK bằng `AudioManager.setStreamVolume` (chủ máy nghe xác nhận 22/10/2026: 0 mất tiếng, 8 to hơn). Chỉ chỉnh được khi APK đã nối và là bản mới biết báo âm lượng; không thì không khả dụng. Cũng chỉnh được bằng `volume_set` trên `media_player.r1_loa` (thẻ YouTube dùng cái này) và thanh «Âm lượng loa» trong tab Đàm thoại. Không đổi âm lượng của vuốt dải cảm ứng trên đỉnh loa (luồng thông báo/hệ thống, đèn xanh dương theo mức) | 0–15 |
| EQ 60 Hz, 230 Hz, 910 Hz, 3,6 kHz, 14 kHz | number | Năm dải EQ | −1500…+1500 mB (1 dB = 100 mB) |
| Chế độ EQ | select | Chọn 1 trong 10 preset Android: Normal, Classical, Dance, Flat, Folk, Heavy Metal, Hip Hop, Jazz, Pop, Rock. Chọn = ghi năm dải theo bảng của firmware; kéo tay một dải thì ô này hiện «không rõ» | |
| EQ | switch | Bật/tắt toàn bộ EQ | |
| Tăng cường bass / Cường độ bass | switch / number | Bật bass và độ mạnh | 0–1000 |
| Loudness / Độ lợi loudness | switch / number | Bù tiếng ở âm lượng nhỏ | 0–1000 |
| DLNA, AirPlay | switch | Cho loa nhận nhạc qua DLNA / AirPlay | |
| Tăng mic | number | Khuếch đại tuyến tính tiếng mic (dB) **ở HA**, áp trước khi tiếng vào Assist; chặn cứng ở biên độ tối đa, không lọc ồn. Nhớ giá trị qua các lần khởi động HA. **CHƯA ĐO** | 0–30 dB, mặc định 12 |
| Tắt mic | switch | Bật = mic ngừng (HA đóng luồng, không dò từ đánh thức, không nghe được). Dùng khi muốn riêng tư | |
| Assist (bật/tắt) | switch | Tắt = vệ tinh Assist không nghe/không đáp (luồng mic vẫn chảy) | |
| Đàm thoại | switch | Phiên song công do HA mở/giữ mở (thẻ dùng mic điện thoại, xem mục 6) | |
| Mic loa song song | switch | **Bật** = song công (hai bên nói cùng lúc, mặc định); **tắt** = nửa công (HA bỏ tiếng mic khi loa đang phát). Không liên quan «giữ để nói» hay «bật mic luôn» | |
| Đèn theo nhạc | switch | Bật/tắt đèn theo nhạc của firmware | |
| Độ sáng đèn nhạc / Sắc độ đèn nhạc | number | Chỉnh đèn theo nhạc (firmware) | 0–100 / 1–100 |
| Độ sáng đèn | number | Độ sáng **chung** của đèn viền và đèn đáy, nhân vào mọi chức năng đèn | 0–100 % |
| Trợ lý | select | Chọn pipeline Assist cho loa (nơi chọn từ đánh thức, STT, TTS) | |
| Loa | media_player | Phát nhạc, tạm dừng, âm lượng; nhận `play_media`, TTS, thông báo | |
| Bộ đàm | binary_sensor | Bật khi loa đã nối về HA (kênh phát sẵn sàng) | |
| Từ đánh thức | binary_sensor | Bật thoáng chốc khi có trigger từ đánh thức | |
| Dịch vụ đèn | binary_sensor | APK trên loa có sẵn sàng điều khiển đèn bằng hiệu ứng firmware không (mục 5) | tắt = APK chưa nối hoặc là bản cũ |
| Trạng thái mic | sensor | `tat` / `nghe` / `gui`; ở chế độ HA, «nghe» = luồng chảy liên tục về HA và HA đang dò từ đánh thức | |
| Tóm tắt cài đặt | sensor | Dữ liệu cho thẻ (đừng dùng trong tự động hoá) | |
| Trạng thái thiết bị | sensor | Số đo thiết bị từ loa | |

---

## 3. Thẻ Lovelace

**Cài tích hợp là tự thêm thẻ**: khi HA khởi động xong, tích hợp tự đăng ký tài nguyên `/r1_speaker/r1-card.js?v=<phiên bản>`
(đổi `?v=` mỗi lần cập nhật để trình duyệt bỏ bản cũ) và gỡ ba tài nguyên thẻ con cũ nếu bạn từng thêm tay. **Chỉ có MỘT thẻ**
`r1-card` (3 tab, tự nạp thẻ đàm thoại/EQ/cài đặt), nên bộ chọn thẻ chỉ hiện «R1 (gộp, tab)». Chỉ cần thêm thẻ
`type: custom:r1-card` (nhiều loa: thêm `device_id`). Bảng điều khiển ở chế độ YAML thì danh sách tài nguyên chỉ-đọc: khi đó tự
thêm `/r1_speaker/r1-card.js` (Mô-đun JavaScript). Tên loa và hàng tab luôn hiện; nội dung từng tab đóng sẵn, bấm tab để mở.
Nếu thẻ báo «Custom element not found»: tải lại cưỡng bức, xoá đệm giao diện, hoặc thêm `?v=<số>` sau địa chỉ tài nguyên.

**Tab Đàm thoại**

| Nút | Làm gì |
|---|---|
| **Giữ để nói** | Giữ = mic điện thoại đi ra loa, thả = nghe lại tiếng loa. Lần giữ đầu trình duyệt hỏi quyền mic và mở kênh. Cần mở HA bằng **https** |
| **Bật mic luôn** | Mic điện thoại mở liên tục; bấm lần nữa để tắt |
| **👂 Nghe tiếng trong nhà** | Chỉ quản trị viên. Phát tiếng mic loa ra điện thoại, **không lọc tiếng người**, không mở phiên, không phát ra loa, không cần mic điện thoại. Có thanh mức tiếng và dòng «ĐANG NGHE». Dừng khi ẩn tab hoặc tắt mic loa |
| Đóng kênh điện thoại | Đóng hẳn kênh mic điện thoại |
| Tắt mic | Giống công tắc «Tắt mic» |
| Tạm dừng / Phát | Điều khiển nhạc của `media_player.r1_loa` |

Mỗi loa chỉ một điện thoại một lúc (người thứ hai bị từ chối).

**Tab EQ:** năm dải, Chế độ EQ, Âm lượng.

**Tab Cài đặt**
- **Âm thanh:** tăng mic và khối **Cài đặt nâng cao** (mục 4). Mục khác mặc định có dấu `*`. Đổi một mục thì HA nạp
  lại tích hợp để áp dụng (mic nối lại sau vài giây).
- **Ánh sáng:** tám chức năng đèn, đèn nhạc, nút «Thử» (mục 5).
- **Kết nối:** IP, cổng, `ha_url`, trạng thái APK, cổng nghe mic (HA tự cấp), nút «Hiện lệnh cài APK» (quản trị viên).

---

## 4. Cài đặt nâng cao (19 mục)

Mọi mục **CHƯA ĐO** trên R1. Giá trị bằng mặc định thì không được lưu: khi sau này đo xong và đổi mặc định, các mục
bạn chưa chỉnh tay tự theo. Chỉnh ở thẻ (Cài đặt → Âm thanh → Cài đặt nâng cao), ở Tuỳ chọn → «Chỉnh thông số nâng cao»,
hoặc bằng dịch vụ `r1_speaker.set_advanced_option` (`key`, `value`).

### 4.1 Cổng thoại của bộ đàm nửa công (go2rtc → loa)

Chỉ dùng khi tiếng đi vào loa qua đường bộ đàm/go2rtc. Cổng thoại quyết định lúc nào HA coi là «đang có người nói» để
mở loa, và lúc nào đóng.

| Khoá | Nhãn trong thẻ | Khoảng | Mặc định | Chỉnh thế nào |
|---|---|---|---|---|
| `talk_threshold_db` | Ngưỡng có tiếng người (dBFS) | −90…−5 | −45 | To hơn (gần −5): khó mở loa, bỏ được tiếng ồn nền nhưng nuốt tiếng nhỏ. Nhỏ hơn: dễ mở, dễ nhận nhầm tiếng ồn |
| `talk_silence_s` | Im bao lâu thì đóng loa (giây) | 0,2…10 | 1,5 | Lớn: loa mở lâu hơn sau câu nói (không bị cụt giữa câu ngập ngừng). Nhỏ: đóng nhanh |
| `talk_preroll_s` | Giữ đầu câu (giây) | 0…2 | 0,3 | Giữ lại một đoạn tiếng ngay trước lúc mở để không mất chữ đầu. Lớn quá thì kéo theo cả tiếng ồn trước câu |
| `talk_tail_s` | Chờ loa tắt trước khi mở mic (giây) | 0…5 | 0,5 | Chống mic nghe lại tiếng loa còn vang. Nghe vọng thì tăng; muốn trả lời nhanh thì giảm |

### 4.2 Khử tạp âm (phía HA, mặc định TẮT)

Lọc tiếng mic trên HA bằng cách giảm các dải chỉ có tạp. Không tách được nhạc hay tiếng người khác.

| Khoá | Nhãn | Khoảng | Mặc định | Chỉnh thế nào |
|---|---|---|---|---|
| `noise_suppress` | Bật khử tạp | bật/tắt | tắt | Bật khi nền có tiếng quạt/máy lạnh đều đều |
| `noise_strength_db` | Giảm tối đa mỗi dải (dB) | 0…40 | 12 | Lớn: sạch hơn nhưng tiếng người dễ bị méo, «rỗng» |
| `noise_voice_db` | Ngưỡng nhận tiếng người (dB trên nền) | 0,5…12 | 4 | Lớn: chỉ coi là tiếng người khi nổi hẳn so với nền (bớt tạp, dễ nuốt tiếng nhỏ) |

### 4.3 Tự chỉnh mức — AGC (phía HA, mặc định TẮT)

Kéo tiếng mic về một mức đều: nhỏ thì tăng, to thì giữ.

| Khoá | Nhãn | Khoảng | Mặc định | Chỉnh thế nào |
|---|---|---|---|---|
| `agc_enable` | Bật AGC | bật/tắt | tắt | Bật khi người nói xa/gần không đều |
| `agc_target_db` | Mức đích RMS (dBFS) | −50…−3 | −20 | Mức tiếng muốn đạt. Cao hơn: to hơn, dễ vỡ tiếng |
| `agc_max_gain_db` | Tăng tối đa (dB) | 0…40 | 12 | Trần khuếch đại. Cao: nghe được tiếng rất nhỏ nhưng cũng khuếch đại cả tạp |
| `agc_silence_db` | Dưới mức này coi là im lặng (dBFS) | −90…−20 | −55 | Dưới mức này AGC không tăng (để không thổi phồng tiếng nền khi im) |

### 4.4 Hạn đỉnh (phía HA, mặc định TẮT)

Chặn tiếng quá to làm vỡ tiếng.

| Khoá | Nhãn | Khoảng | Mặc định | Chỉnh thế nào |
|---|---|---|---|---|
| `limiter_enable` | Bật hạn đỉnh | bật/tắt | tắt | Bật khi có tiếng hét/gõ mạnh làm vỡ |
| `limiter_ceiling` | Trần biên độ | 0,1…1,0 | 0,89 (≈ −1 dBFS) | Thấp hơn: tiếng bị ép nhỏ hơn nhưng không vỡ |

### 4.5 Đàm thoại song công

Áp dụng cho phiên đàm thoại do HA mở (mic điện thoại, công tắc «Đàm thoại»).

| Khoá | Nhãn | Khoảng | Mặc định | Chỉnh thế nào |
|---|---|---|---|---|
| `duplex_vad_threshold` | Ngưỡng tiếng người VAD (xác suất 0–1) | 0,05…0,95 | 0,5 | Cao: chặt hơn (bớt nhạc/tiếng ồn lọt qua, dễ bỏ sót giọng nhỏ). Thấp: lọt nhiều hơn |
| `duplex_preroll_s` | Giữ tiếng trước câu nói (giây) | 0…2 | 0,3 | Giữ đầu câu để không mất chữ đầu |
| `duplex_hangover_s` | Giữ tiếng sau câu nói (giây) | 0…5 | 0,5 | Kéo dài sau câu để không cụt đuôi |
| `duplex_max_s` | Thời gian tối đa của phiên (giây) | 60…86400 | 1800 | Phiên tự đóng khi quá thời gian này (an toàn khi quên tắt) |
| `duplex_duck` | Cắt vọng: bỏ tiếng mic nhỏ khi HA đang phát | bật/tắt | tắt | Bật khi nghe tiếng vọng của chính loa; đổi lại có thể mất tiếng nói nhỏ |
| `duplex_duck_db` | Ngưỡng mức tiếng cắt vọng (dBFS) | −90…−5 | −45 | Khung mic nhỏ hơn ngưỡng này (lúc HA đang phát) sẽ bị bỏ. Cao: cắt mạnh hơn |

Khử vọng (trừ tiếng HA đã phát khỏi mic) bật sẵn trong phiên song công với độ trễ cố định 300 ms, **CHƯA ĐO**.
Nhạc phát qua AirPlay/DLNA không đi qua đường tiếng của HA nên không được trừ.

---

## 5. Đèn

Chi tiết kiến trúc, ADB, script, an toàn và gỡ rối: [DEN-LED.md](DEN-LED.md). Phần này là **bảng cài đặt**.

**Cách chạy:** hiệu ứng chạy trên loa (`r1den.sh`) qua ADB; custom nối adb-server nếu có, không thì nối thẳng loa
(tuỳ chọn `adb_server`, `adb_mode` = `auto` / `server` / `direct` ở Cấu hình tích hợp). `binary_sensor.r1_dich_vu_den` cho biết
ADB dùng được không và đi đường nào.

**Mỗi chức năng** có **bật/tắt** và **hai vùng** (đáy, viền), mỗi vùng một hiệu ứng (hoặc tắt) kèm bộ thông số riêng của
hiệu ứng đó (số thông số khác nhau từng hiệu ứng). Khi nhiều chức năng cùng đúng, chức năng đứng trước thắng:

`Tắt mic` > `Lỗi` > `Phản hồi` > `Nghĩ` > `Nghe` > `Đàm thoại` > `Phát nhạc` > `Chờ`

**Mặc định** (đề xuất, chủ máy chỉnh được; chỉ phần khác mặc định mới được lưu):

| Chức năng | Khi nào | Bật | Đèn đáy | Đèn viền |
|---|---|---|---|---|
| `cho` | Nghỉ, chờ từ đánh thức | không | `co_dinh` (mau=#0000ff, do_sang=20) | tắt |
| `nghe` | Loa đang nghe | có | `co_dinh` (mau=#0000ff, do_sang=60) | `sang` (do_sang=60) |
| `nghi` | Assist đang xử lý | có | `tho` (mau=#0000ff, do_sang=60, toc_do=100, do_sau=0) | tắt |
| `phan_hoi` | Loa đang trả lời | có | `co_dinh` (mau=#00ff00, do_sang=60) | `sang` (do_sang=60) |
| `dam_thoai` | Có phiên đàm thoại (giữa hai lượt) | có | `tho` (mau=#00ff00, do_sang=50, toc_do=100, do_sau=0) | `sang` (do_sang=50) |
| `phat_nhac` | Đang phát nhạc | không | `cau_vong` (do_sang=40, toc_do=100, bao_hoa=100, chieu=xuoi) | tắt |
| `loi` | Phiên bị lỗi (giữ vài giây) | có | `nhap_nhay` (mau=#ff0000, do_sang=80, toc_do=100, ty_le_bat=50) | `sang` (do_sang=80) |
| `tat_mic` | Mic đang tắt | có | `co_dinh` (mau=#ff0000, do_sang=25) | `sang` (do_sang=25) |

**Thông số từng hiệu ứng.** Tốc độ là phần trăm so với nhịp gốc (100 = như mô tả); độ sáng nhân thêm với độ sáng chung
(`number.r1_do_sang_den`). Đèn viền chỉ trắng nên **không có thông số màu**.

##### Đèn đáy (15 đèn RGB)

#### `co_dinh` — Sáng cố định (tĩnh: đặt rồi thôi, không giữ phiên ADB)

Một màu sáng liên tục.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `mau` | Màu | màu `#rrggbb`, mặc định `#00ff00` |
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |

#### `tho` — Thở

Sáng dần rồi tối dần, chu kỳ 2 giây ở tốc độ 100%.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `mau` | Màu | màu `#rrggbb`, mặc định `#0000ff` |
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `do_sau` | Độ sâu (mức tối thấp nhất) | 0–80 %, mặc định 0 |

#### `nhap_nhay` — Nhấp nháy

Bật rồi tắt, chu kỳ 1 giây ở tốc độ 100%.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `mau` | Màu | màu `#rrggbb`, mặc định `#00ff00` |
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `ty_le_bat` | Tỷ lệ thời gian bật | 10–90 %, mặc định 50 |

#### `nhip_tim` — Nhịp tim

Hai nhịp mạnh, yếu rồi nghỉ.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `mau` | Màu | màu `#rrggbb`, mặc định `#ff0000` |
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `nghi_ms` | Nghỉ giữa các nhịp | 200–2000 ms, mặc định 660 |

#### `chop` — Chớp

Vài chớp rất ngắn rồi nghỉ.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `mau` | Màu | màu `#rrggbb`, mặc định `#ffffff` |
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `so_chop` | Số chớp mỗi lượt | 1–6, mặc định 3 |
| `nghi_ms` | Nghỉ giữa các lượt | 300–3000 ms, mặc định 800 |

#### `phao_hoa` — Pháo hoa nhỏ

Chùm màu ngẫu nhiên bừng lên rồi tắt dần.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `bang_mau` | Bảng màu | `nhieu_mau` (Nhiều màu), `am` (Tông ấm), `lanh` (Tông lạnh); mặc định `nhieu_mau` |
| `nghi_ms` | Nghỉ giữa các chùm | 100–2000 ms, mặc định 450 |

#### `cau_vong` — Cầu vồng 12 sắc

Cả vòng đáy đổi 12 sắc độ, mỗi sắc 0,4 giây ở tốc độ 100%.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `bao_hoa` | Độ bão hoà màu | 30–100 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |

#### `cau_vong_fw` — Cầu vồng 6 màu

Đổi lần lượt đỏ, cam, xanh lá, xanh dương, tím, lục lam.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |

#### `cau_vong_xoay` — Cầu vồng xoay

Mỗi đèn một màu, cả dải xoay vòng.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |
| `bao_hoa` | Độ bão hoà màu | 30–100 %, mặc định 100 |
| `so_dai` | Số dải cầu vồng quanh đáy | 1–3, mặc định 1 |

#### `sao_choi` — Sao chổi

Đầu sáng nhất, đuôi tối dần chạy quanh đáy.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |
| `dai_duoi` | Độ dài đuôi | 2–8 đèn, mặc định 5 |
| `kieu_mau` | Kiểu màu | `nhieu_mau` (Nhiều màu (đỏ đến tím)), `don_sac` (Đơn sắc); mặc định `nhieu_mau` |
| `mau` | Màu *(chỉ khi `kieu_mau` = `don_sac`)* | màu `#rrggbb`, mặc định `#00ffff` |

##### Đèn viền (24 đèn, chỉ trắng)

#### `sang` — Sáng liên tục (tĩnh: đặt rồi thôi, không giữ phiên ADB)

Viền trắng sáng liên tục.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |

#### `chay_duoi` — Chạy đuổi

Điểm sáng có đuôi mờ chạy quanh 24 đèn viền.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |
| `dai_duoi` | Độ dài đuôi | 1–10 đèn, mặc định 4 |

#### `tho` — Thở

Cả viền sáng dần rồi tối dần.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `do_sau` | Độ sâu (mức tối thấp nhất) | 0–80 %, mặc định 0 |

**Thử đèn** là mục riêng trên thẻ (tab Ánh sáng): chọn vùng, hiệu ứng, thông số rồi bấm Thử; chạy tạm vài giây rồi tự trả
đèn về trạng thái thật, không lưu gì (dịch vụ `preview_light`, `stop_preview_light`). Trong từng cài đặt chức năng không có
nút Thử.

---

## 6. Mic điện thoại, nghe tiếng, từ đánh thức

- **Từ đánh thức do HA dò**, không phải loa. Tiếng mic loa chảy **liên tục** về HA (đo thực tế khoảng 32 KB/s = 16 kHz,
  16 bit) và pipeline Assist dò từ khoá trong luồng đó. Chọn từ khoá ở Cài đặt HA → Trợ lý giọng nói → pipeline, và chọn
  pipeline cho loa ở ô «Trợ lý». Tắt mic hoặc tắt «Assist» thì HA ngừng dò. Từ đánh thức chạy ngay trên loa **chưa có**.
- **Nhạc và đàm thoại có lẫn vào mic.** Mic và loa chung một hộp. Nhạc không đi qua đường tiếng của HA nên không được
  khử; wakeup lúc đang nghe nhạc to **chưa kiểm chứng**. Muốn đàm thoại không vọng thì tắt «Mic loa song song» (nửa công).
- **Mic điện thoại cần https** (trình duyệt chặn mic ở `http://IP`). Nút «Nghe tiếng trong nhà» thì không cần mic điện
  thoại nên chạy được cả qua http.
- **Khoá nghe mic tự động.** APK bị từ chối thì tự xin khoá qua `POST /api/r1_speaker/ghep` (HA chỉ trao đúng một lần, cho
  đúng IP loa); cửa đóng khi APK xác thực và **tự mở lại khi loa gửi khoá sai**. Trong lúc cửa mở, app nào trên loa cũng xin
  được khoá (đánh đổi có chủ ý). Cài APK lần đầu:
  `adb shell /system/bin/am start -n vn.r1.bodam/.ManHinhChinh --es host <IP-HA> --ei port 18765 --ez bat true`
  (cổng HTTP của HA mặc định 8123). Loa đã cấu hình rồi thì lệnh đổi cấu hình bị bỏ qua: chạy trước
  `adb shell /system/bin/pm clear vn.r1.bodam`.

---

## 7. Dịch vụ HA (`r1_speaker.*`)

| Dịch vụ | Làm gì |
|---|---|
| `set_advanced_option` | Đổi một cài đặt nâng cao: `entity_id` (thực thể của loa), `key` (khoá ở mục 4), `value` (số hoặc true/false). Giá trị ngoài khoảng bị từ chối; nạp lại tích hợp để áp dụng |
| `set_light_function` | Đổi cấu hình đèn của một chức năng: `function`, `enabled`, và mỗi vùng `day` / `vien` là `{effect, params}` |
| `preview_light` | **Thử** một hiệu ứng ở một vùng: `zone`, `effect`, `params`, `seconds` (không lưu) |
| `stop_preview_light` | Dừng thử, trả đèn về trạng thái thật |
| `start_duplex` / `stop_duplex` | Mở/đóng phiên đàm thoại song công của loa |
| `get_intercom_source` | Trả hai dòng nguồn cho `go2rtc.yaml`: nói vào loa (`talk`) và nghe mic (`listen`) |
| `get_wake_endpoint` | Trả địa chỉ để loa/thiết bị khác POST trigger từ đánh thức về HA |

Lệnh WebSocket `r1_speaker/apk_lenh` (chỉ quản trị viên) trả lệnh cài APK có kèm khoá; khoá không nằm trong trạng thái
thực thể.
