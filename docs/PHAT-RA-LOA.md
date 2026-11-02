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

## Tin báo không làm nhạc nhảy bài + hạ nhạc nền khi loa nói (NV287)

### Vì sao nhạc nhảy bài sau TTS (đo trên mã, không đoán)

Tin báo đi qua `media_player.play_media` với `announce`: `MusicKeeper` tạm dừng nhạc, tin **thay URI của renderer DLNA**, xong tin thì
khôi phục bằng cách đặt lại URI nhạc cũ + tua về vị trí đã chụp. Nhảy bài xảy ra ở hai chỗ nối nhau:

1. Khi tin kết thúc, renderer về idle. Mã cũ xóa `idle_reason` mỗi lần hỏi lại thấy renderer đang phát, nên lúc tin hết nó lại thành
   `finished` («hết bài»). Bộ điều khiển danh sách phát của chủ máy (`tritue_youtube_player`, ngoài repo này — trong repo chỉ có nút bấm
   `media_next_track` ở `phim.py`) đọc `idle_reason`: `finished` → sang bài kế. Đã chạy lại bằng chính mã của nó (`advance.py` + `ly_do_idle.py`
   0.28.6) với chuỗi trạng thái nhạc → tạm dừng → tin phát → idle: `finished` cho **sang bài kế**.
2. Lúc khôi phục, nếu bộ điều khiển đã kịp bật bài kế thì renderer đang `playing` bài khác, và `MusicKeeper._restore` thấy «đã có gì đó phát»
   thì không đụng tới nữa — nhạc ở lại bài kế, đúng triệu chứng.

**Vì sao không khai `interrupted`:** cùng bộ điều khiển coi `interrupted` là «bị bài khác đè» và **gỡ loa khỏi phiên** (chạy lại: gỡ loa, không
sang bài kế), tức nhạc phát lại được nhưng hết bài thì dừng hẳn. Nên trong lúc loa đang giữ nhạc, idle được khai là **`dang_giu`**: với bộ
điều khiển chưa biết giá trị này nó rơi về đường đoán bằng thời lượng bài với vị trí đã đóng băng lúc tạm dừng (không nhảy bài, không gỡ loa — chỉ
sai với bài không biết thời lượng); bản vá `NV287-VA-PLAYER.diff` cho bộ điều khiển hiểu hẳn `dang_giu` = «bỏ qua, chờ loa khôi phục».

### Cách sửa (mặc định: chỉ phần C; A + B mặc định TẮT)

| Phương án | Làm gì | Trạng thái |
|---|---|---|
| C — sửa «hết bài» giả (luôn bật) | Trong lúc có lượt giữ nhạc đang mở, renderer về idle được khai `idle_reason=dang_giu` (Stop của người dùng vẫn là `stopped`), kể cả đường DLNA lẫn đường AirPlay (trước đây AirPlay hết phiên là `finished` dù đó chỉ là tin). Hết giữ nhạc, nhạc phát lại thì `idle_reason` biến mất như cũ. | Đã làm, có test với renderer giả; hành vi của bộ điều khiển đã kiểm bằng mã thật của nó. |
| A — tin đi AirPlay song song (`tts_song_song_airplay`, mặc định tắt) | Tin mở một phiên RAOP **riêng**, không dừng DLNA, không đổi `_duong`/`_uri`/`idle_reason`/trạng thái của thực thể. Nhạc DLNA vẫn là «bài đang phát» suốt lúc tin nói nên không cần khôi phục, không có cửa cho «hết bài» giả. Chỉ dùng khi nhạc đang ở DLNA; nhạc ở AirPlay hoặc không có nhạc thì về đường thường. Tin song song mở không được thì về đường thường (nhả lượt giữ duck rồi giữ lại kiểu tạm dừng). | Đã làm, có test với RAOP giả + DLNA giả. **Chưa đo trên loa thật.** |
| B — hạ nhạc nền (`ha_nhac_xuong`, mặc định tắt, `ha_nhac_nac` mặc định 5 nấc) | Chỉ có tác dụng khi A bật: trong lúc tin song song phát, nhạc DLNA nhỏ đi N nấc (thang 0–15 của loa, qua đúng đường `volume_set` → APK `setStreamVolume`), rồi trả **đúng mức cũ** khi bên cuối cùng nhả — kể cả khi tin lỗi hoặc bị huỷ (nhả chạy trong `finally`). Không đọc được mức cũ (APK mic chưa nối) thì về tạm dừng như cũ, không hạ mù. Giữa lúc hạ nhạc mà phiên đàm thoại mở mic thì nhạc được tạm dừng nốt (nhỏ vẫn lọt vào mic). | Đã làm, có test cả đường âm lượng thật (`volume_set` → `mic_server`). **Chưa đo trên loa thật.** |

**Chưa đo, phải đo trước khi bật A/B trên loa thật** (đây là hai điều mã không tự trả lời được): (1) Android trên loa có trộn được DLNA + RAOP
cùng lúc hay không — nếu firmware chỉ cho một nguồn ra tiếng thì tin song song sẽ im hoặc cướp tiếng nhạc, phải tắt cờ; (2) RAOP có dùng luồng
âm lượng riêng với `STREAM_MUSIC` hay không — nếu RAOP cũng đi `STREAM_MUSIC` thì hạ nhạc cũng hạ luôn tin, ducking vô nghĩa, phải tắt
`ha_nhac_xuong` (giữ A nếu trộn được).

### Kịch bản đo cho chủ máy (tối đa 5 bước)

1. Phát nhạc qua DLNA lên `media_player.r1_loa`, ghi lại bài + vị trí.
2. Ở Tuỳ chọn tích hợp, bật `tts_song_song_airplay` và `ha_nhac_xuong` (để `ha_nhac_nac` = 5). Cần APK mic đã nối (thực thể `number` âm lượng có giá trị): chưa nối thì nhạc bị **tạm dừng** thay vì nhỏ đi (log: «ducking: không đọc được mức âm lượng cũ»).
3. Gọi tin báo (Thử dịch vụ: `tts.speak` tới `media_player.r1_loa`, hoặc `assist_satellite.announce`): nghe xem nhạc có nhỏ đi không, tin có đủ to không.
4. Hết tin, kiểm tra `media_content_id` vẫn là bài nhạc cũ, vị trí chạy tiếp (không quay về đầu, không sang bài kế) và âm lượng về đúng mức ở bước 1.
5. Kết luận: tin im hoặc nhạc dừng hẳn → tắt `tts_song_song_airplay`; tin cũng nhỏ đi theo nhạc → tắt `ha_nhac_xuong` (giữ A); cả hai đều đúng → giữ nguyên.

### Ví dụ: báo thức buổi sáng 30 phút (tự động hoá, không thêm mã tích hợp)

`bao_thuc.py` hiện có **không** làm được đúng kịch bản này: báo thức kiểu `tts` của nó lặp lại **một lời nhắn cố định** mỗi `lap_s` giây cho tới
khi bị tắt/hết `toi_da_s`, còn `hen_gio_tat_nhac` thì nhỏ dần rồi **dừng** nhạc — không có «nhạc 30 phút, mỗi 10 phút đọc thời gian còn lại rồi
nhạc phát tiếp». Kịch bản này làm bằng tự động hoá HA (nhạc phát tiếp được là nhờ NV287; ở chế độ mặc định thì mỗi tin tạm dừng + khôi phục,
ở chế độ song song thì nhạc không dừng):

```yaml
alias: Báo thức buổi sáng 30 phút
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: media_player.play_media
    target:
      entity_id: media_player.r1_loa
    data:
      media_content_id: "https://nhac.example/playlist-sang.mp3"
      media_content_type: music
  - delay: "00:10:00"
  - action: tts.speak
    target:
      entity_id: tts.MAY_TTS_CUA_BAN  # đổi thành thực thể TTS thật của người dùng
    data:
      media_player_entity_id: media_player.r1_loa
      message: "Còn 20 phút nữa là hết giờ báo thức, nhạc vẫn đang phát."
  - delay: "00:10:00"
  - action: tts.speak
    target:
      entity_id: tts.MAY_TTS_CUA_BAN
    data:
      media_player_entity_id: media_player.r1_loa
      message: "Còn 10 phút nữa là hết giờ báo thức."
  - delay: "00:10:00"
  - action: media_player.media_stop
    target:
      entity_id: media_player.r1_loa
```

**Chưa thử trên loa**: mọi kịch bản trên chỉ chạy với renderer DLNA giả + RAOP giả; nghiệm thu trên loa thật là việc của chủ máy.

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
