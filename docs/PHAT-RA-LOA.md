# Phát tiếng của HA ra loa R1 (`media_player.r1_loa`)

Không có giao thức DLNA tự viết. Firmware của loa đã có DLNA renderer; HA phát qua tích hợp
`dlna_dmr` có sẵn. `r1_speaker` chỉ thêm phần dlna_dmr không làm được: **bật DLNA trên loa
(`Set_DLNA_Open`) trước khi phát**, rồi chuyển lệnh sang thực thể dlna_dmr của chính loa đó.

## Cài đặt

1. Thêm tích hợp `r1_speaker` (IP và cổng WebSocket của loa).
2. Bật DLNA một lần (công tắc DLNA của `r1_speaker`) để loa có renderer.
3. Thêm **DLNA Digital Media Renderer** cho loa. Nên thêm bằng **URL mô tả thiết bị nhập tay**
   (luồng thủ công), vì luồng đó bật "poll availability" nên thực thể dlna_dmr tự nối lại khi
   DLNA của loa vừa lên. Luồng khám phá SSDP không bật tuỳ chọn này; khi đó thực thể chỉ nối
   lại nếu nghe được thông báo SSDP alive từ loa.
4. Phát: `tts.speak` hoặc `media_player.play_media` với `media_player.r1_loa`. Âm lượng chỉnh
   bằng `number.phicomm_r1_volume`.

`media_player.r1_loa` báo lỗi rõ (không im lặng) nếu chưa có mục dlna_dmr cùng địa chỉ máy
với loa, hoặc nếu thực thể dlna_dmr chưa sẵn sàng sau 15 giây kể từ khi bật DLNA.

## Chưa kiểm trên loa thật

Cổng và đường dẫn mô tả thiết bị của renderer (báo cáo dịch ngược ghi 1146 nhưng là suy đoán,
cổng cấp phát lúc chạy); loa có gửi SSDP alive, có chấp nhận đăng ký sự kiện UPnP, định dạng
âm thanh nào nhận được (MP3/WAV từ TTS); `Set_DLNA_Open` có thật sự khởi động renderer.
Test chỉ dùng loa giả (WebSocket + renderer UPnP giả ở 127.0.0.1).
