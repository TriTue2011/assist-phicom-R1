# R1 Bộ đàm (vn.r1.bodam) — Hướng dẫn build một lệnh (NV247)

APK mic cho loa Phicomm R1: chỉ ghi mic → gửi PCM16 16 kHz mono về Home Assistant
qua TCP (khung: 4 byte độ dài big-endian + payload; hello JSON có khoá; khung end).

## Yêu cầu

- JDK 17 (javac/java)
- Android SDK: platform `android-22` + build-tools `30.0.3`
  (bản dựng gốc dùng Temurin 17.0.20.1 + platform android-22 + build-tools 30.0.3)

## Build một lệnh

```sh
# mac dinh dung toolchain cu (neu co)
./build.sh release     # bien the phat hanh -> nv247-vn-r1-bodam.apk
./build.sh kiemthu     # bien the kiem thu  -> nv247-vn-r1-bodam-kiemthu.apk
```

Đường dẫn đọc từ BIẾN MÔI TRƯỜNG (không mã cứng):

| Biến           | Ý nghĩa                        | Mặc định                          |
|----------------|--------------------------------|-----------------------------------|
| `R1_TOOLCHAIN` | Gốc toolchain                  | `$HOME/workspace/android-toolchain` |
| `R1_JDK`       | Thư mục JDK                    | `$R1_TOOLCHAIN/jdk17`              |
| `R1_SDK`       | Thư mục Android SDK            | `$R1_TOOLCHAIN/android-sdk`       |
| `R1_BUILD_TOOLS` | Phiên bản build-tools        | `30.0.3`                          |
| `R1_KEYSTORE`  | Keystore ký APK                | `./debug.keystore` (tự tạo nếu thiếu) |

Ví dụ:

```sh
R1_TOOLCHAIN=/opt/android-tc R1_BUILD_TOOLS=30.0.3 ./build.sh release
```

## Hai biến thể

- **release** (`nv247-vn-r1-bodam.apk`): bản phát hành — KHÔNG có receiver kiểm thử (dex không chứa
  `KiemMicReceiver`). Cửa cấu hình bằng intent của `ManHinhChinh` chỉ nhận khi app **chưa cấu hình**;
  đã cấu hình thì bỏ qua (muốn đổi: `pm clear vn.r1.bodam` rồi cấu hình lại).
- **kiemthu** (`nv247-vn-r1-bodam-kiemthu.apk`): bản kiểm thử — thêm receiver exported
  `vn.r1.bodam.KIEM_MIC` (bật/tắt mic, đổi host/khoá) và `vn.r1.bodam.KIEM_DEN_NHAC`. Bất kỳ app nào trên
  loa cũng gọi được: CHỈ dùng kiểm thử, không để trên loa chạy thật.

Cả hai ký bằng keystore debug đi kèm lần build trước (cùng chứng thư với bản
NV243/NV245 → cài đè được). File `debug.keystore` KHÔNG nằm trong gói nguồn này.

## Cấu trúc nguồn

```
src/vn/r1/bodam/   DichVuGhi.java  (dịch vụ tiền cảnh, ủy quyền cho DieuKhienGhi)
                   DieuKhienGhi.java (logic phiên ghi: timeout/generation/khung chẵn)
                   ManHinhChinh.java (màn hình cài đặt + nhận cấu hình qua am start)
                   TiepCanPhim.java  (AccessibilityService nhận nút giữa, mặc định TẮT)
                   KiemMicReceiver.java (CHỈ bản kiểm thử)
                   CauHinh.java / CauHinhTuLenh.java / Khung.java / KhuechDai.java
                   LogicNut.java / MayGhi.java / BluetoothDieuKhien.java
test/vn/r1/bodam/  KiemTra.java    (test Java thuần, chạy: xem "Kiểm thử" dưới)
res/               values/strings.xml, xml/tiep_can_phim.xml
AndroidManifest-release.xml / AndroidManifest-kiemthu.xml
build.sh
```

## Kiểm thử

```sh
# bien dich + chay test thuan (can android.jar trong SDK)
AJAR="$R1_SDK/platforms/android-22/android.jar"   # hoac duong dan tuong duong
javac -source 8 -target 8 -encoding UTF-8 -cp "$AJAR" \
    -d /tmp/lop $(find src test -name '*.java')
java -cp "/tmp/lop:$AJAR" vn.r1.bodam.KiemTra   # ky vong: passed=47 failed=0, exit 0
```

## Cấu hình loa không màn hình (qua adb)

```sh
adb shell am start -n vn.r1.bodam/.ManHinhChinh \
    --es host 192.0.2.10 --ei port 18765 --es khoa MAT_KHAU
# bat nhan nut giua khi app khong tien canh (can chu may duyet + bat trong Tro nang):
adb shell am start -n vn.r1.bodam/.ManHinhChinh --es host 192.0.2.10 \
    --ei port 18765 --es khoa MAT_KHAU --ez tiep_can true
```

Lưu ý: KHÔNG đưa IP/khoá thật vào mã nguồn hay gói này.


## Cấu hình lần đầu, tự bật khi khởi động, lệnh đèn nhạc

- **Cấu hình lần đầu** (loa không có màn hình), khi app chưa cấu hình:
  `am start -n vn.r1.bodam/.ManHinhChinh --es host <IP HA> --ei port 18765 --es khoa <khoá>`.
  Cài đè bằng `pm install -r` giữ nguyên cấu hình (cùng chứng thư ký).
- **Bật mic theo cấu hình đã lưu:** `am start -n vn.r1.bodam/.ManHinhChinh --ez bat true`
  (không đổi được đích đến).
- **Tự bật khi loa khởi động lại:** `KhoiDongReceiver` (không exported, nhận `BOOT_COMPLETED`) bật mic nếu
  đã đủ host, port và khoá. HA từ chối kết nối khi người dùng tắt mic (`switch.r1_tat_mic`).
- **Nối lại:** mất kết nối (HA khởi động lại, mạng chập chờn) thì chờ 2 giây tăng dần tới 30 giây rồi thử
  lại; chưa từng nối được mà thất bại 12 lần liên tiếp thì dừng (sai host/khoá).
- **Đèn theo nhạc của firmware:** HA gửi khung `{"type":"den_nhac","ma":65,"gia_tri":50}` xuống kết nối
  mic; `LenhDieuKhien` kiểm chặt định dạng và khoảng giá trị rồi `TrungTamTin` gọi dịch vụ hệ thống
  `msgcenter` (nhóm 4, mã 64 bật/tắt, 65 độ sáng 0–100, 66 sắc độ 1–100).
- **Kiểm thử thuần:** biên dịch `src` + `test` rồi chạy `vn.r1.bodam.KiemTra` (xem lệnh ở mục Kiểm thử).
