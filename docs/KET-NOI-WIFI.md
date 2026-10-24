# Kết nối WiFi cho loa R1 mới (hoặc vừa reset)

Dùng cho **loa mới tinh** hoặc loa **vừa reset về cài đặt gốc** (chưa biết WiFi nhà). Loa không có màn hình, nên nó tự phát một WiFi riêng để bạn
đưa tên và mật khẩu WiFi nhà vào. Kho này có sẵn trang làm việc đó: **`Trang kết nối WiFi cho loa R1.html`** (ở gốc kho). Trang chạy
**hoàn toàn offline**, không gửi gì ra Internet: chỉ gửi cấu hình thẳng tới loa. Cùng cơ chế với mục 1 của chương trình *Bo Cai R1* và *Ai Box Plus*.

## Các bước

1. **Cắm điện loa**, rồi **giữ nút trên loa 5–10 giây**: đèn **nhấp nháy** và loa phát ra âm thanh (loa chờ cấu hình). Lúc đó loa phát WiFi tên **`Phicomm_R1_XXXX`** (XXXX là mã riêng của loa). Đây là bước của chương trình *Bo Cai R1* (mục 1, đã chạy tốt 24/10/2026); chỉ cắm điện thì loa đã có WiFi nhà **không** phát mạng này.
2. **Tải tệp HTML về** điện thoại hoặc máy tính (từ kho GitHub: mở tệp → *Download raw file*), **trước khi** đổi WiFi, vì khi nối vào WiFi của loa
   bạn sẽ không có Internet.
3. **Nối điện thoại/máy tính vào WiFi `Phicomm_R1_XXXX`.** Nên **tắt dữ liệu di động và VPN** để máy không đi đường khác (điện thoại hay tự chuyển sang
   4G vì WiFi này không có Internet: nếu vậy chọn «vẫn giữ kết nối» khi máy hỏi).
4. **Mở tệp HTML trực tiếp trong trình duyệt** (mở từ bộ nhớ máy, không mở qua một trang web trên mạng).
5. Bấm **«Kiểm tra kết nối tới loa»**: phải báo *«Tới được loa ở 192.168.43.1:8989»*.
6. Điền **Tên WiFi (SSID)**, **Mật khẩu** và **Loại mã hoá** của WiFi nhà:
   * `WPA/WPA2` (hầu hết các nhà), `WEP` (cũ), hoặc `Không mật khẩu`.
7. Bấm **«Gửi cấu hình»**. Chờ **10–20 giây**: loa tự bắt WiFi nhà và **tắt** mạng `Phicomm_R1_XXXX`. Khi mạng đó biến mất là loa đã nhận.
8. **Nối điện thoại/máy tính lại vào WiFi nhà.** Tìm IP của loa trong bảng DHCP của router (thiết bị tên Phicomm/R1), rồi **đặt IP tĩnh hoặc giữ chỗ DHCP** cho
   loa để địa chỉ không đổi.
9. Sang HA: thêm tích hợp **Phicomm R1 Speaker** với IP đó (xem [README](../README.md) mục *Loa mới: từ đầu đến dùng được*).

## Cách trang làm việc (để bạn tự kiểm)

* Địa chỉ loa ở chế độ chờ cấu hình: `http://192.168.43.1:8989/`; lệnh cấu hình: `POST http://192.168.43.1:8989/api/configwifi`.
* Thân gửi đi là JSON: `{"ssid": "<tên WiFi>", "secure": "WPA" | "WEP" | "INSECURE", "password": "<mật khẩu>", "mac": ""}`.
* Trang thử **cách 1** (JSON chuẩn, đọc được phản hồi của loa). Nếu trình duyệt chặn (CORS), trang tự chuyển **cách 2** (`no-cors`, gửi văn bản thuần chứa cùng JSON):
  cách này **không đọc được phản hồi**, nên hãy chờ mạng `Phicomm_R1_XXXX` biến mất để biết loa đã nhận.

## Gỡ rối

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy WiFi `Phicomm_R1_XXXX` | loa không ở chế độ chờ cấu hình (đã có WiFi, hoặc chưa reset) | reset loa về cài đặt gốc theo hướng dẫn của hãng, rồi cắm điện lại |
| «Chưa tới được loa» | chưa nối đúng WiFi của loa; VPN hoặc dữ liệu di động đang bật; trình duyệt tự đổi mạng | nối lại WiFi `Phicomm_R1_XXXX`, tắt VPN và dữ liệu di động, thử lại bấm *Kiểm tra* |
| Gửi xong mà `Phicomm_R1_XXXX` vẫn còn sau 30 giây | sai tên/mật khẩu WiFi nhà, hoặc sai loại mã hoá, hoặc WiFi nhà là băng tần loa không bắt được | kiểm tên (đúng hoa/thường), mật khẩu, loại mã hoá; thử WiFi 2,4 GHz (theo thông số công khai, R1 chỉ có 2,4 GHz; **chưa kiểm trên loa này**) |
| Loa vào WiFi nhà nhưng HA không thấy | IP loa đổi, hoặc loa và HA khác mạng con | xem IP trong router, đặt IP tĩnh, kiểm HA cùng mạng với loa |

**Bảo mật:** mật khẩu WiFi nhà đi qua HTTP thường tới loa trong mạng riêng `Phicomm_R1_XXXX` (chỉ máy bạn và loa). Hãy làm bước này ở nhà, không ở nơi đông người.
Trang không lưu mật khẩu.

**Nếu trang không được:** dùng chương trình *Bo Cai R1* trên máy tính, mục [1] «Cấu hình WiFi cho loa» (nối máy tính vào `Phicomm_R1_XXXX`, nhập SSID, loại mã hoá, mật khẩu; chương trình báo «Đã gửi cấu hình thành công»). Trình duyệt có thể chặn (CORS, mạng riêng) hoặc loa có thể đòi đúng kiểu JSON mà cách gửi dự phòng của trang không đáp ứng; công cụ trên máy tính không bị các giới hạn đó.

**Chưa kiểm bởi tác giả của tài liệu này:** trang và địa chỉ `192.168.43.1:8989` do chủ kho cung cấp; tài liệu mô tả đúng nội dung trang, chưa chạy lại trên một loa vừa reset.
