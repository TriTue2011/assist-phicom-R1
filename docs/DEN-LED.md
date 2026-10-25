# Đèn LED của loa R1

Tài liệu này mô tả toàn bộ phần đèn: phần cứng, cách HA điều khiển (qua ADB), danh mục hiệu ứng và **thông số riêng của
từng hiệu ứng**, cài đặt theo chức năng, mục **Thử**, dịch vụ HA, thẻ, và cách gỡ rối. Danh mục bên dưới được sinh từ
mã (`custom_components/r1_speaker/den_hieu_ung.py`); thẻ cài đặt vẽ form từ chính danh mục đó nên thêm hiệu ứng
hay thông số là thêm dữ liệu, không sửa giao diện.

## 0. Tóm tắt kiến trúc

```
 thẻ r1-card ──dịch vụ HA──▶ den.py (R1Lights)        chọn chức năng đang hiệu lực (tắt mic > lỗi > ... > chờ)
  (Thử / cài đặt)             │  mỗi chức năng: bật/tắt + vùng đáy + vùng viền (hiệu ứng + thông số)
                              ▼
                       den_adb.py (AdbLights) ── adb_client.py ──┬─▶ adb-server (127.0.0.1:5037), nếu có
                              │  lệnh cố định, đã lọc            └─▶ nối thẳng adbd của loa (cổng 5555)
                              ▼
                  loa: sh /data/local/tmp/r1den.sh <vùng> <hiệu ứng> khoa=giatri ...
                              │  ghi thẳng /sys/class/leds/multi_leds0/led_color (quyền shell của adb)
                              ▼
                       15 đèn đáy RGB + 24 đèn viền trắng
```

* **Hiệu ứng chạy NGAY TRÊN LOA** (script `r1den.sh`), HA chỉ gửi tên hiệu ứng và các số đã kiểm. Nhờ vậy tốc độ
  không phụ thuộc mạng và không có luồng lệnh từng bước từ HA.
* **Không cần APK** cho đèn (APK chỉ còn lo mic, âm lượng, đèn theo nhạc của firmware). Không cần máy chủ quyền shell.
* **Không bắt buộc có adb-server**: custom tự nói giao thức ADB, nối thẳng tới loa nếu không có server (mục 2).

## 1. Phần cứng (đã kiểm, chủ máy xác nhận bằng mắt)

| Đèn | Số đèn | Mặt nạ `led_color` | Màu |
|---|---|---|---|
| Đáy | 15 (bit 0–14) | `7fff`; từng đèn `1`, `2`, `4`... `4000` | RGB tự do |
| Viền | 24 (bit 15–38) | `7fffff8000`; từng đèn `8000`... `4000000000` | **chỉ trắng** (`LLLLLL`, L = mức sáng) |

Ghi: `echo "<mặt nạ hex> <rrggbb>" > /sys/class/leds/multi_leds0/led_color` (shell của adb ghi được; app thường bị SELinux
chặn). Mọi hiệu ứng ở mục 4 đã được xem bằng mắt từng cái một trên loa thật (23/10/2026), kèm kiểm tốc độ 50–250 % và
độ sáng 30 %.

## 2. Đường tới loa: ADB (tự nhận diện)

HA chạy lệnh trên loa bằng ADB. Có ba chế độ, chọn ở **Cấu hình tích hợp → Tuỳ chọn** (hai ô *Địa chỉ adb-server* và
*Cách nối ADB tới loa*):

| Chế độ (`adb_mode`) | Làm gì |
|---|---|
| `auto` (mặc định) | Thử adb-server (`adb_server`, mặc định `127.0.0.1:5037`); **không có server thì nối thẳng tới loa**. |
| `server` | Chỉ qua adb-server; không có thì báo lỗi. |
| `direct` | Chỉ nối thẳng tới adbd của loa (cổng `5555`), bỏ qua adb-server. |

Custom tự mang **máy khách ADB riêng** (`adb_client.py`, thuần Python, không thêm thư viện): cả hai đường đều chạy
lệnh, đẩy tệp (giao thức sync) và mở nhiều luồng cùng lúc. Loa R1 có `ro.adb.secure=0` nên **không đòi khoá RSA**; nếu
adbd đòi xác thực thì báo lỗi rõ ràng.

**Điều kiện cần biết:**

* **adbd của loa chỉ phục vụ MỘT kết nối TCP tại một thời điểm.** Nếu một client ADB khác đang giữ loa (một adb-server
  đã `adb connect` tới loa, tích hợp «Android Debug Bridge» của HA, máy tính của bạn), kết nối thẳng của custom không được
  trả lời và thẻ báo *«adbd của loa không trả lời (đang bận phục vụ một client ADB khác?)»*. Cách xử lý: dùng chế độ
  `server` hoặc `auto` với một adb-server duy nhất làm trung gian, hoặc ngắt client kia (`adb disconnect <IP-loa>:5555`).
* Ở chế độ nối thẳng, đáy và viền chạy **cùng một kết nối** (ghép luồng); kết nối được **nhả ngay khi không còn
  hiệu ứng lặp nào** để client ADB khác dùng được.
* Cổng ADB mạng của loa (`5555`) phải bật (đã bật sẵn trên loa này và còn sau khi khởi động lại).
* Nếu bạn dùng adb-server dạng container, nên chỉ mở nó trên máy chủ HA (`127.0.0.1:5037`), không mở ra LAN.

**Cảm biến `binary_sensor.r1_dich_vu_den`** («Dịch vụ đèn»): bật khi ADB tới loa dùng được; thuộc tính `duong_adb`
(`server` hoặc `direct`), `che_do_adb`, `loi`. Thẻ cài đặt (tab Ánh sáng) hiện đường đang dùng và lỗi gần nhất. Lỗi
ADB không làm hỏng gì: HA ghi một dòng cảnh báo mỗi lần lỗi *đổi*, rồi **tự thử lại sau 15 giây**; loa khởi động lại hoặc
nối lại thì HA áp lại đèn.

**An toàn:** lệnh gửi lên loa luôn có dạng `sh /data/local/tmp/r1den.sh <vùng> <hiệu ứng> khoa=giatri ...`, trong đó vùng
và hiệu ứng lấy từ danh mục, số đã kẹp trong khoảng, màu là sáu số hex, lựa chọn nằm trong danh sách. Phần cuối còn qua
một bộ lọc `[a-z_]+=[0-9a-z_]+`; **không có đường nào đưa chuỗi tuỳ ý vào shell của loa** (có test chặn).

## 3. Script `r1den.sh` trên loa

Nằm trong tích hợp (`custom_components/r1_speaker/r1den.sh`), HA **tự đẩy lên** `/data/local/tmp/r1den.sh` khi loa chưa
có hoặc khác phiên bản (dòng `(r1den-vN)` ở đầu tệp).

* Cú pháp: `r1den.sh <day|vien> <hiệu ứng> [khoá=giá_trị ...]`. Chạy **tiền cảnh** trong phiên ADB đang mở.
* Hiệu ứng **tĩnh** (`co_dinh`, `sang`) chỉ đặt giá trị rồi thoát: đèn giữ nguyên, HA không giữ phiên.
* Hiệu ứng **lặp** chạy tới khi phiên ADB đóng: script bắt `HUP`/`TERM`/`INT` rồi **tắt đúng vùng của nó** và thoát.
  Tiến trình nền không sống sau khi phiên ADB đóng (đã đo), nên HA giữ một phiên mở cho mỗi vùng đang chạy hiệu ứng lặp.
* Mỗi vùng có tệp pid riêng `/data/local/tmp/r1den.<vùng>.pid`: hiệu ứng mới của cùng vùng **dừng hẳn tiến trình cũ**
  (`kill -9`) trước khi ghi, nên không bao giờ có hai tiến trình cùng ghi một vùng; đáy và viền độc lập nhau.
* `r1den.sh <vùng> tat` tắt vùng đó. Script tự kẹp mọi số; giá trị sai rơi về mặc định.
* Loa không có `printf`, `head`, `tr`, `timeout`: script chỉ dùng tính năng của `mksh` (cắt chuỗi, `$((...))`, `RANDOM`).
  Hex lấy bằng bảng chữ số; HSV→RGB bằng số nguyên.

## 4. Danh mục hiệu ứng và thông số

Mỗi hiệu ứng có **bộ thông số riêng, số lượng khác nhau** (viền sáng liên tục chỉ có độ sáng; sao chổi có sáu). Thông số
có điều kiện (`chi_khi`) chỉ hiện khi điều kiện đúng. **Tốc độ** là phần trăm so với nhịp gốc (100 = như mô tả; 200 = nhanh
gấp đôi); **độ sáng** nhân thêm với độ sáng chung (`number.r1_do_sang_den`).

### 4.1 Đèn đáy (15 đèn RGB)

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

Cả vòng: mỗi đèn một màu, xoay vòng. Dải ngắn: vài dải cầu vồng chạy quanh đáy, đèn còn lại tối.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |
| `bao_hoa` | Độ bão hoà màu | 30–100 %, mặc định 100 |
| `kieu_dai` | Kiểu dải | `ca_vong` (Cả vòng 15 màu), `dai_ngan` (Dải ngắn chạy quanh); mặc định `ca_vong` |
| `so_dai` | Số dải: số vòng cầu vồng lặp lại (cả vòng) hoặc số dải ngắn chạy cùng lúc | 1–5, mặc định 1 |
| `do_rong` | Độ rộng mỗi dải (chỉ khi `kieu_dai` = `dai_ngan`) | 3–8 đèn, mặc định 5 |

#### `sao_choi` — Sao chổi

Đầu sáng nhất, đuôi tối dần chạy quanh đáy.

| Thông số | Ý nghĩa | Giá trị |
|---|---|---|
| `do_sang` | Độ sáng | 0–100 %, mặc định 100 |
| `toc_do` | Tốc độ | 25–400 %, mặc định 100 |
| `chieu` | Chiều | `xuoi` (Xuôi), `nguoc` (Ngược); mặc định `xuoi` |
| `dai_duoi` | Độ dài đuôi | 2–8 đèn, mặc định 5 |
| `so_choi` | Số sao chổi chạy cùng lúc, cách đều nhau quanh đáy | 1–4, mặc định 1 |
| `kieu_mau` | Kiểu màu | `nhieu_mau` (Nhiều màu (đỏ đến tím)), `don_sac` (Đơn sắc); mặc định `nhieu_mau` |
| `mau` | Màu *(chỉ khi `kieu_mau` = `don_sac`)* | màu `#rrggbb`, mặc định `#00ffff` |

### 4.2 Đèn viền (24 đèn, chỉ trắng — không có thông số màu)

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

## 5. Cài đặt theo chức năng

Tám chức năng; mỗi chức năng có **bật/tắt** và **hai vùng** (`day`, `vien`), mỗi vùng một hiệu ứng (hoặc `tat`) kèm bộ
thông số của hiệu ứng đó. Chức năng đang hiệu lực chọn theo thứ tự (đứng trước thắng):

`tat_mic` > `loi` > `phan_hoi` > `nghi` > `nghe` > `dam_thoai` > `phat_nhac` > `cho`

Chức năng đang **tắt** (`enabled` = không) nghĩa là «lúc đó không có đèn»: tắt cả hai vùng (riêng `phat_nhac` tắt thì coi
như không có nhạc). Mặc định (đề xuất, chủ máy chỉnh được trên thẻ; chỉ phần khác mặc định mới được lưu):

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

Cài đặt lưu ở `.storage/r1_speaker.lights.<mã mục>`. **Bản lưu cũ** (mô hình phẳng: màu, hiệu ứng, độ sáng, kiểu viền)
được **tự chuyển** sang mô hình hai vùng lần đầu nạp (hiệu ứng cũ giữ mã, kiểu viền chạy đuổi cũ thành viền `chay_duoi`,
viền trắng thành `sang`).

## 6. Mục Thử (tách riêng khỏi cài đặt)

Tab **Ánh sáng** của thẻ có mục **Thử đèn** nằm riêng, phía trên cài đặt từng chức năng; **trong từng cài đặt không có nút
Thử**. Cách dùng: chọn *Vùng* (đáy hoặc viền), chọn *Hiệu ứng*, chỉnh các thông số của hiệu ứng đó, chọn thời gian rồi bấm
**Thử**. Đèn chạy hiệu ứng đó vài giây (1–30 giây) rồi **tự trả về trạng thái thật**; **Dừng thử** trả về ngay.

* Thử **không lưu gì**: nó chỉ phủ tạm lên vùng được chọn (vùng kia giữ nguyên), nên bạn thử tốc độ, màu, chiều... thoải mái.
* Trạng thái của mục Thử (vùng, hiệu ứng, thông số đang chỉnh) chỉ nằm trong thẻ; chỉ nút **Thử** mới gọi dịch vụ.
* Đang thử thì thẻ hiện nhãn *Đang thử* (thuộc tính `thu` của `sensor.r1_cai_dat`).

## 7. Dịch vụ HA

Gọi qua *Công cụ nhà phát triển → Hành động* hoặc tự động hoá. `entity_id` là thực thể `r1_speaker` bất kỳ của loa
(ví dụ `sensor.r1_cai_dat`).

| Dịch vụ | Làm gì |
|---|---|
| `r1_speaker.set_light_function` | Đổi `enabled` và/hoặc một vùng (`day`, `vien`) của một chức năng (`function`). Mỗi vùng là `{effect, params}`. Đổi `effect` thì thông số về mặc định của hiệu ứng mới; chỉ gửi `params` thì giữ hiệu ứng và trộn vào thông số hiện có (giá trị sai kiểu không thay giá trị tốt). |
| `r1_speaker.preview_light` | **Thử**: chạy tạm `effect` với `params` ở `zone` (`day`/`vien`) trong `seconds` giây (1–30). Không lưu. |
| `r1_speaker.stop_preview_light` | Dừng thử, trả đèn về trạng thái thật. |

Ví dụ:

```yaml
action: r1_speaker.set_light_function
data:
  entity_id: sensor.r1_cai_dat
  function: nghe
  day:
    effect: sao_choi
    params: {kieu_mau: don_sac, mau: "#00ffff", dai_duoi: 6, toc_do: 150}
  vien:
    effect: chay_duoi
    params: {chieu: nguoc, dai_duoi: 4}
---
action: r1_speaker.preview_light
data:
  entity_id: sensor.r1_cai_dat
  zone: day
  effect: cau_vong_xoay
  params: {so_dai: 2, toc_do: 120}
  seconds: 10
```

Giá trị ngoài danh mục (hiệu ứng lạ, hiệu ứng của vùng khác) bị từ chối với lỗi rõ ràng.

## 8. Thuộc tính cho thẻ (`sensor.r1_cai_dat` → `anh_sang`)

`chuc_nang` (cài đặt từng chức năng kèm cờ `mac_dinh`), `danh_muc` (danh mục mục 4, thẻ vẽ form từ đây), `dang_ap_dung`,
`thu_tu_uu_tien`, `thu` (mục Thử đang chạy), `dich_vu_den`, `duong_adb`, `che_do_adb`, `loi_dich_vu`, `do_sang_chung`,
`den_nhac_firmware`. **Không có khoá hay địa chỉ bí mật nào** trong các thuộc tính này (có test).

## 9. Đèn theo nhạc của firmware (đường riêng, qua APK)

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
khi phát nhạc» của tích hợp (chức năng `phat_nhac` ở mục 5, chạy qua ADB).

Đèn viền và đèn đáy (hiệu ứng, màu, độ sáng) **không** đi đường này: xem mục 2 và 3 (ADB). Khung `den_vien`, `den_day`,
`den_hieu_ung`, `den_hoi` giữa HA và APK **đã bỏ** ở phía HA; APK cũ vẫn hiểu chúng nhưng HA không gửi nữa.

## 10. Gỡ rối

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Thẻ báo *Chưa có đường ADB* | tích hợp chưa tạo được đường ADB (mục `CHO_PHIA_LOA`) | khởi động lại tích hợp; kiểm địa chỉ loa |
| *adbd của loa không trả lời (đang bận...)* | client ADB khác đang giữ loa | `adb disconnect <IP-loa>:5555`, hoặc dùng chế độ `server` với một adb-server duy nhất |
| *adb-server: Connection refused* | không có server ở địa chỉ đã đặt | chế độ `auto` tự nối thẳng; hoặc sửa địa chỉ / đặt `direct` |
| *loa đòi xác thực ADB* | adbd bật khoá RSA | tắt `ro.adb.secure` hoặc dùng adb-server đã được loa tin cậy |
| Đèn đứng yên sau khi bấm | loa mất mạng | HA tự thử lại sau 15 giây; xem `binary_sensor.r1_dich_vu_den` |
| Đèn không tắt sau khi tắt tích hợp | phiên ADB bị đứt trước khi script nhận `HUP` | gọi `stop_preview_light` hoặc chạy `adb shell sh /data/local/tmp/r1den.sh day tat` |

Chạy tay để thử trên loa (không qua HA): `adb shell sh /data/local/tmp/r1den.sh day cau_vong_xoay toc_do=120` (Ctrl+C để dừng).

## 11. Đã kiểm / chưa kiểm

* **Đã xem bằng mắt trên loa thật (23/10/2026) với BẢN NGUYÊN MẪU của script** (trước khi thêm thông số riêng): cả 13 hiệu
  ứng (10 đáy, 3 viền) ở tốc độ và độ sáng mặc định; viền chạy đuổi ở tốc độ 250 % và 50 %; độ sáng 30 % (viền sáng,
  cầu vồng); tự tắt khi phiên ADB đóng.
* **Đã kiểm bằng máy trên loa thật:** máy khách ADB ở cả hai đường (qua adb-server và nối thẳng): chạy lệnh, đẩy tệp (md5 khớp),
  hai luồng (đáy + viền) cùng lúc trên một kết nối.
* **CHƯA xem bằng mắt với `r1den.sh` bản cuối** (có thông số riêng, màu cầu vồng tính bằng HSV, tệp pid từng vùng) và từng
  *thông số riêng* ở giá trị lạ (chiều ngược, số dải 2–3, đuôi dài, bảng màu ấm/lạnh, tỷ lệ bật...). Test chỉ kiểm mô hình, lệnh
  gửi đi và thẻ, **không** kiểm ánh sáng thật.
