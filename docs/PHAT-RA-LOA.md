# Phát tiếng của HA ra loa R1 (`media_player.r1_loa`)

**Không cần thêm DLNA hay AirPlay riêng.** `r1_speaker` tự điều khiển renderer DLNA có sẵn trong firmware của loa (từ 0.6.0;
trước đó phải thêm tay tích hợp `dlna_dmr`).

## Cách hoạt động

1. Khi phát, nếu DLNA của loa đang tắt thì tích hợp bật nó (`Set_DLNA_Open`).
2. Tích hợp tìm địa chỉ mô tả của renderer bằng **nhiều đường, rẻ trước đắt** (0.6.1): địa chỉ đã nhớ lần nối gần nhất → địa chỉ mà `dlna_dmr`
   cũ (nếu từng thêm cho loa này) đã lưu → bộ nhớ SSDP của chính Home Assistant → **SSDP unicast tới loa** (cổng 1900; loa trả về địa
   chỉ mô tả thiết bị, cổng do loa cấp lúc chạy nên không nhớ cứng) → SSDP multicast. Chỉ nhận mô tả thuộc đúng loa này. Không tìm được
   thì báo rõ đã thử đường nào và gợi ý kiểm UDP 1900 giữa Home Assistant và loa (tường lửa, wifi cách ly máy khách, Docker kiểu
   cầu nối).
3. Phát bằng UPnP AV (`SetAVTransportURI` + `Play`), tạm dừng/phát tiếp/dừng/tua cũng qua đó. Thư viện `async_upnp_client` có sẵn
   trong Home Assistant lo phần SOAP.
4. Trạng thái (`playing` / `paused` / `idle`), tên bài, **thời lượng**, vị trí và **lý do idle** hiện ngay trên `media_player.r1_loa`
   và trên thẻ R1. Hỏi lại renderer có chu kỳ chỉ **khi đang phát** (3 giây; 1 giây khi đang báo tin) và theo chu kỳ 10 giây
   của tích hợp khi DLNA bật (để thấy cả nhạc do thiết bị khác bật). Idle/tạm dừng thì không hỏi nền.

`tts.speak` và `media_player.play_media` đều đi đường này; `media-source://` được giải ra URL, URL tương đối được đổi thành địa chỉ
HA mà loa tới được. Âm lượng chỉnh bằng `number.phicomm_r1_volume` (đường APK có sẵn).

## Lý do idle (`idle_reason`)

Khi `idle`, thực thể có thuộc tính `idle_reason`: `finished` (bài tự hết), `stopped` (lệnh dừng của người dùng/tự động hoá),
`interrupted` (bài mới thay bài đang phát), `error` (renderer báo lỗi truyền tải, hoặc loa không trả lời giữa lúc đang phát).
Tích hợp phát nhạc YouTube đọc thuộc tính này để phân biệt Stop với hết bài thay vì đoán bằng thời lượng bài.

## Lỗi

`media_player.r1_loa` báo lỗi rõ (không im lặng) nếu loa không trả lời SSDP (DLNA tắt hoặc loa mất mạng), nếu renderer chưa lên sau
15 giây kể từ khi bật DLNA, hoặc nếu một lệnh bị renderer từ chối.

## Đã đo trên loa thật (28/10/2026)

Loa trả lời SSDP unicast, công bố `MediaRenderer:1` (Platinum UPnP 1.0.4, cổng 1590 lúc đo); đọc `GetTransportInfo` được, hỗ trợ
`Seek`. **Chưa nghe thử phát âm thanh thật** từ mã mới: kiểm bằng `media_player.play_media` rồi xem `idle_reason` khi bài hết.
Chưa đo: định dạng âm thanh nào loa nhận (MP3/WAV/AAC từ TTS và YouTube), có tua được thật, hành vi khi hai nguồn cùng phát.
