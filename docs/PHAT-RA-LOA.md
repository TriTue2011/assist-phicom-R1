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
   và trên thẻ R1. Hỏi lại renderer có chu kỳ chỉ **khi đang phát** (2,9 giây; 1 giây khi đang báo tin) và theo chu kỳ 10 giây
   của tích hợp khi DLNA bật (để thấy cả nhạc do thiết bị khác bật). Idle/tạm dừng thì không hỏi nền.

`tts.speak` và `media_player.play_media` đều đi đường này; `media-source://` được giải ra URL, URL tương đối được đổi thành địa chỉ
HA mà loa tới được. Âm lượng chỉnh bằng `number.phicomm_r1_volume` (đường APK có sẵn).

## Vị trí chính xác và tua mịn (0.6.2)

UPnP chỉ báo vị trí bằng số NGUYÊN giây (cắt xuống), nên đọc thẳng thì lệch trung bình nửa giây và dao động ±1 giây. `youtube` dùng vị trí để đồng bộ
nhiều loa, nên số thô làm R1 «đo sai rồi chỉnh theo số sai» và trôi dần. Thực thể nay **ước vị trí chính xác hơn** (giao các ràng buộc theo thời gian,
sai số cỡ 0,1–0,3 giây sau vài lần hỏi), ghi lại khi lệch quá 0,3 giây hoặc 15 giây một lần, và chu kỳ hỏi là 2,9 giây (không phải số nguyên giây, để
pha đổi dần). Tua gửi đích có phần thập phân (`0:00:42.370`); loa từ chối thì tự làm tròn GẦN NHẤT tới giây (thư viện mặc định cắt xuống) và nhớ.

## Dừng và tắt tiếng loa (0.6.4)

Thẻ R1 (tab Đàm thoại) có nút **Dừng** (`media_player.media_stop`, tự gửi lại nếu renderer bỏ qua) và công tắc **Tắt tiếng loa** (`media_player.volume_mute`).
Tắt tiếng loa là đưa âm lượng nhạc về 0 qua đường APK đã kiểm (như `number.r1_am_luong`), nhớ mức cũ để bật lại đúng mức; khác công tắc «Tắt mic» (đóng
luồng mic). Cần APK nối về HA; chưa nối thì báo lỗi rõ.

## Lý do idle (`idle_reason`)

Khi `idle`, thực thể có thuộc tính `idle_reason`: `finished` (bài tự hết), `stopped` (lệnh dừng của người dùng/tự động hoá),
`interrupted` (bài mới thay bài đang phát), `error` (renderer báo lỗi truyền tải, hoặc loa không trả lời giữa lúc đang phát).
Tích hợp phát nhạc YouTube đọc thuộc tính này để phân biệt Stop với hết bài thay vì đoán bằng thời lượng bài.

## AirPlay song song với DLNA, bù trừ nhau (0.11.0)

Loa R1 có cả renderer DLNA lẫn bộ nhận AirPlay 1 (RAOP). Từ 0.11.0 tích hợp **tự gửi AirPlay** (`airplay.py`, không dùng `apple_tv`/`pyatv`, không thêm thư viện Python)
và cho chọn đường phát ở **Tuỳ chọn → Đường phát nhạc và tin ra loa** (`duong_phat`):

| Giá trị | Cách phát |
|---|---|
| `dlna` (mặc định) | Chỉ DLNA, đúng như trước 0.11.0. AirPlay không được đụng tới. |
| `dlna_truoc` | DLNA; hỏng thì AirPlay. |
| `airplay_truoc` | AirPlay; hỏng thì DLNA. |
| `airplay` | Chỉ AirPlay. |

**Bù trừ** nghĩa là: đường đầu hỏng thì tự thử đường kia, và đường bị bỏ luôn được **dừng trước** (loa không bao giờ phát hai nơi). «Hỏng» chỉ tính theo
tín hiệu chắc chắn, không theo cảm giác chậm:

- DLNA hỏng = lệnh `SetAVTransportURI`/`Play` bị từ chối hoặc không nối được, hoặc renderer báo `ERROR_OCCURRED`. Renderer nạp luồng chậm (còn idle, không báo lỗi) **không** bị coi là hỏng.
- AirPlay hỏng = loa từ chối một bước RTSP, ffmpeg không mở/giải mã được nguồn, hoặc chưa có gói tiếng đầu sau 10 giây.

Cả hai đều hỏng thì báo một lỗi nêu tên cả hai đường. Thuộc tính `duong_phat` (`dlna`/`airplay`) trên `media_player.r1_loa` cho biết đường đang ra tiếng. Khi AirPlay
đang phát, kết quả hỏi DLNA bị bỏ qua tại một cổng duy nhất để không ghi đè trạng thái.

**AirPlay ở đây là PCM không nén, không mã hoá** (SDP `L16/44100/2`, loa báo hỗ trợ qua mDNS `cn=0,1`, `et=0,1`). Tiếng được giải mã bằng **ffmpeg của máy chạy HA**
(bản HA OS/Container chuẩn đều có) nên nhận mọi định dạng ffmpeg đọc được, kể cả m4a/opus của YouTube; chỉ nhận địa chỉ `http(s)` (ffmpeg bị khoá giao thức, không đọc được `file:`).
Loa đệm khoảng 2 giây (`Audio-Latency`) nên tiếng ra chậm hơn DLNA chừng đó.

**Khác DLNA:**

- Không biết thời lượng bài (`media_duration` trống) và **không tua tại chỗ**: tua = phát lại từ vị trí đó (ffmpeg `-ss`), nên có một quãng ngắt.
- Tạm dừng = `FLUSH`; phát tiếp phát lại phần đã gửi mà chưa kịp nghe nên tiếp đúng chỗ đã dừng.
- Báo tin (TTS) khi đang nghe nhạc: nhạc tạm dừng, tin phát, rồi nhạc được đặt lại và tua về vị trí cũ (`giu_nhac`) — tức nhạc **bắt đầu lại** từ vị trí cũ, có một quãng ngắt, như đường DLNA.
- Cổng RAOP lúc đo (28/10/2026) là `5012`; nếu đổi sau khi loa khởi động lại thì sửa `airplay_port` trong Tuỳ chọn. Công tắc AirPlay của loa được bật tự động khi cần.

**Không làm** (nói thẳng để khỏi hiểu nhầm): đây là AirPlay từng loa một, **không có đồng bộ nhiều loa** kiểu Music Assistant/`cliairplay`; hai loa AirPlay chạy cùng lúc sẽ
lệch nhau vài trăm mili giây hoặc hơn. Nghe đồng bộ nhiều loa vẫn là việc chưa làm.

**Đã kiểm:** mã gửi chạy với loa RAOP giả viết độc lập theo đặc tả (bắt tay, đóng gói RTP big-endian, đồng bộ, timing, gửi lại gói, tạm dừng, âm lượng, huỷ) và với renderer DLNA giả
(các kịch bản bù trừ hai chiều, chậm không bị coi là hỏng, đổi đường giữa chừng, báo tin, tua). **Chưa kiểm trên loa thật**: chưa nghe được tiếng, chưa đo độ trễ, chưa thử xem
loa có chấp nhận đúng gói đồng bộ/timing này không, chưa thử ffmpeg thật (máy dựng không có ffmpeg).

## Lỗi

`media_player.r1_loa` báo lỗi rõ (không im lặng) nếu loa không trả lời SSDP (DLNA tắt hoặc loa mất mạng), nếu renderer chưa lên sau
15 giây kể từ khi bật DLNA, hoặc nếu một lệnh bị renderer từ chối.

## Đã đo trên loa thật (28/10/2026)

Loa trả lời SSDP unicast, công bố `MediaRenderer:1` (Platinum UPnP 1.0.4, cổng 1590 lúc đo); đọc `GetTransportInfo` được, hỗ trợ
`Seek`. **Chưa nghe thử phát âm thanh thật** từ mã mới: kiểm bằng `media_player.play_media` rồi xem `idle_reason` khi bài hết.
Chưa đo: định dạng âm thanh nào loa nhận (MP3/WAV/AAC từ TTS và YouTube), có tua được thật, hành vi khi hai nguồn cùng phát.
