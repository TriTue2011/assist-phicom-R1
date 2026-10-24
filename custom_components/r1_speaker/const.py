"""Hằng số của tích hợp Phicomm R1 Speaker."""

from datetime import timedelta

DOMAIN = "r1_speaker"

CONF_HOST = "host"
CONF_PORT = "port"
#: Để trống có chủ ý: người dùng tự điền địa chỉ IP của loa trong form thêm tích hợp.
DEFAULT_HOST = ""
#: Cổng WebSocket điều khiển + EQ. ĐÃ ĐO (21/10/2026): ``get_eq_config`` trả lời ở cổng 8080,
#: khoá ``type``. (Cổng 8082 là cổng nhạc của AI box đã gỡ, không còn dùng.) Đổi được ở
#: config flow lẫn tuỳ chọn.
DEFAULT_PORT = 8080

#: Chu kỳ coordinator hỏi lại loa; mất kết nối thì tự thử lại đúng chu kỳ này.
SCAN_INTERVAL = timedelta(seconds=10)
#: Chờ phản hồi / mở kết nối tối đa ngần này giây.
RESPONSE_TIMEOUT = 5.0

VOL_MIN, VOL_MAX = 0, 15
EQ_BANDS = 5
#: Giới hạn dự phòng của một dải EQ (mB) khi loa không báo minBandLevel/maxBandLevel. Số này
#: là giá trị ĐO trên loa thật (get_eq_config: -1500..1500); giới hạn đang dùng luôn ưu tiên
#: số loa báo (R1State.eq_min / eq_max).
EQ_MIN, EQ_MAX = -1500, 1500
STRENGTH_MIN, STRENGTH_MAX = 0, 1000
GAIN_MIN, GAIN_MAX = 0, 1000
#: Tên dải theo tài liệu dịch ngược (60Hz, 230Hz, 910Hz, 3.6kHz, 14kHz).
EQ_BAND_NAMES = ("60 Hz", "230 Hz", "910 Hz", "3.6 kHz", "14 kHz")
#: Preset EQ của firmware loa: mức mỗi dải (dB) cho 60/230/910/3600/14000 Hz, đọc thẳng từ bảng trong
#: ``/system/lib/soundfx/libbundlewrapper.so`` của loa (22/10/2026; cả 9 preset khác Flat đều tìm thấy
#: nguyên dãy này). Loa không có lệnh «đặt preset» nên chọn preset = ghi 5 dải; loa báo mức bằng mB
#: (= dB × 100).
EQ_PRESET_DB = {
    "Normal": (3, 0, 0, 0, 3), "Classical": (5, 3, -2, 4, 4), "Dance": (6, 0, 2, 4, 1),
    "Flat": (0, 0, 0, 0, 0), "Folk": (3, 0, 0, 2, -1), "Heavy Metal": (4, 1, 9, 3, 0),
    "Hip Hop": (5, 3, 0, 1, 3), "Jazz": (4, 2, -2, 2, 5), "Pop": (-1, 2, 5, 1, -2),
    "Rock": (5, 3, -1, 3, 5),
}
EQ_PRESET_MB = {name: tuple(db * 100 for db in levels) for name, levels in EQ_PRESET_DB.items()}
#: Đèn theo nhạc CỦA FIRMWARE: APK loa gửi tin tới dịch vụ ``msgcenter`` (nhóm 4, player nhận qua
#: ``PlayerVisualizerHelper.notifyMsg``). Mã 64 bật/tắt (0/1), 65 độ sáng luma (0–100), 66 sắc độ
#: chroma (1–100). Đã thử trên loa 22/10/2026: gửi rồi đọc lại bằng ``get_info``.
MUSIC_LIGHT_ENABLE, MUSIC_LIGHT_LUMA, MUSIC_LIGHT_CHROMA = 64, 65, 66
MUSIC_LIGHT_RANGE = {MUSIC_LIGHT_ENABLE: (0, 1), MUSIC_LIGHT_LUMA: (0, 100), MUSIC_LIGHT_CHROMA: (1, 100)}

#: Sau Set_DLNA_Open, chờ thực thể dlna_dmr của loa sẵn sàng tối đa ngần này giây.
DLNA_READY_TIMEOUT = 15.0

# ── Mic của loa → Assist (dịch vụ mic trên loa CHƯA có; xem mic.py) ───────────────
CONF_MIC_HOST = "mic_host"
CONF_MIC_PORT = "mic_port"
#: Cổng gợi ý trong form; HOST bỏ trống nghĩa là tắt phần nghe. Số này chưa chốt với dịch vụ
#: mic (chưa viết), đổi được trong tuỳ chọn.
DEFAULT_MIC_PORT = 8765

# ── Đầu NHẬN mic: APK trên loa kết nối TỚI HA (mic_server.py) ─────────────
CONF_MIC_LISTEN_PORT = "mic_listen_port"
CONF_MIC_LISTEN_KEY = "mic_listen_key"
#: True = khoá do HA tự sinh và CHƯA trao cho APK (cửa ghép mở, xem ghep_khoa.py).
CONF_MIC_CHUA_GHEP = "mic_chua_ghep"
#: Cổng HA lắng nghe luồng mic từ APK loa. CHƯA ĐO: APK NV243 chưa nối thử vào HA thật nên
#: chưa có số đo nào chốt cổng này; 18765 là số chọn tạm, đổi được trong tuỳ chọn. Đầu nhận
#: chỉ mở khi ĐÃ đặt khoá (``mic_listen_key``) và IP loa (``mic_host``) — xem mic_server.py.
DEFAULT_MIC_LISTEN_PORT = 18765

# ── Đàm thoại SONG CÔNG kích hoạt từ HA (NV246, song_cong.py) ─────────────────────
CONF_DUPLEX_VAD_THRESHOLD = "duplex_vad_threshold"
CONF_DUPLEX_PREROLL = "duplex_preroll_s"
CONF_DUPLEX_HANGOVER = "duplex_hangover_s"
CONF_DUPLEX_MAX_S = "duplex_max_s"
CONF_DUPLEX_DUCK = "duplex_duck"
CONF_DUPLEX_DUCK_DB = "duplex_duck_db"
#: Ngưỡng xác suất tiếng người của microVAD (``pymicro_vad`` — cùng VAD Assist của HA dùng):
#: khung 10 ms có xác suất >= ngưỡng thì coi là có tiếng người. 0 = KHÔNG LỌC: mọi tiếng từ mic loa đi thẳng
#: lên điện thoại (mặc định từ 24/10/2026: chủ máy đo thật thấy lọc cứng làm mất ~1 giây sau mỗi 3–4 giây, kể cả
#: ngưỡng 0,05, trong khi nút «Nghe» không qua lọc thì liền mạch). Muốn lọc: đặt 0,2–0,5 (CHƯA ĐO trên mic loa R1);
#: lọc tạp âm không mất tiếng thì dùng «Khử tạp» thay vì VAD.
DEFAULT_DUPLEX_VAD_THRESHOLD = 0.0
#: Đệm TRƯỚC tiếng người (giây): giữ sẵn chừng này tiếng ngay trước câu để không cắt đầu câu.
#: CHƯA ĐO trên loa R1; 0.3 mượn số preroll của bộ đàm nửa công.
DEFAULT_DUPLEX_PREROLL = 0.3
#: Đệm SAU tiếng người (giây): câu vừa dứt vẫn chuyển thêm chừng này để không cắt cuối câu.
#: CHƯA ĐO trên loa R1.
DEFAULT_DUPLEX_HANGOVER = 0.5
#: Phiên song công tối đa (giây) = 30 phút theo đề xuất của chủ máy; CHƯA ĐO. Phiên KHÔNG có
#: ngưỡng im lặng tự đóng: chỉ HA kết thúc, mất kết nối, hoặc quá hạn này phiên mới đóng.
DEFAULT_DUPLEX_MAX_S = 1800.0
#: Cắt vọng TUỲ CHỌN: khi HA đang phát xuống loa, khung mic nhỏ hơn ``duplex_duck_db`` (dBFS)
#: bị bỏ (giảm hú/vọng). MẶC ĐỊNH TẮT — chủ máy chấp nhận vọng nhẹ để biết ai đang ở đó.
#: Cả hai số CHƯA ĐO trên loa R1.
DEFAULT_DUPLEX_DUCK = False
DEFAULT_DUPLEX_DUCK_DB = -45.0

#: Sự kiện phiên song công mở/đóng (kèm lý do đóng).
EVENT_DUPLEX = f"{DOMAIN}_duplex"

#: Luồng mic hợp đồng: PCM16 mono 16 kHz little-endian — đúng định dạng Assist đòi.
MIC_RATE = 16000
MIC_CHUNK = 2048
#: Khuếch đại tối đa (dB) trước khi vào Assist.
MIC_GAIN_MAX = 30
#: Mặc định +12 dB. CHƯA ĐO trên mic của loa R1 (số mượn từ camera: mic nhỏ cần +12…+18 dB);
#: đo xong thì đổi số này. Giá trị đã chỉnh tay được nhớ qua lần khởi động và thắng mặc định.
DEFAULT_MIC_GAIN_DB = 12.0
#: Hàng đợi mic về pipeline: ngần này khúc (MIC_CHUNK byte = 64 ms/khúc) → trễ tối đa ≈ 0,5 s.
#: Đầy thì bỏ khúc CŨ NHẤT (luôn giữ tiếng mới nhất), không để đệm tích tụ thành trễ cả câu.
MIC_QUEUE_CHUNKS = 8

# ── Khử tạp âm phía HA (noise_suppress.py), chạy sau amplify, trước các listener ─────────
CONF_NOISE_ENABLE = "noise_suppress"
CONF_NOISE_STRENGTH_DB = "noise_strength_db"
CONF_NOISE_VOICE_DB = "noise_voice_db"
#: MẶC ĐỊNH TẮT. Lý do: mới đo trên tín hiệu tổng hợp, CHƯA đo trên mic thật của loa R1, trong
#: nhà thật, lúc loa đang phát nhạc. Bộ lọc nhầm có thể làm hỏng từ đánh thức / nhận dạng
#: giọng nói hơn là giúp; bật khi đã nghe thử và so tỉ lệ nhận đúng có/không có lọc.
DEFAULT_NOISE_ENABLE = False
#: Giảm tối đa mỗi ô tần số (dB). CHƯA ĐO trên mic loa. Quét 6/12/18/24 dB trên tín hiệu tổng
#: hợp (bản thuật toán cuối): SNR ra gần như phẳng từ 12 dB trở lên (±0,6 dB), nhiễu thuần
#: trắng giảm 5,9/11,8/17,5/21,9 dB, hồng 4,8/8,7/11,1/11,9 dB. 12 dB chọn vì thận trọng
#: (giảm ít nhiễu nhạc và ít cắt tiếng hơn 18–24 dB), KHÔNG phải điểm tối ưu đã chứng minh.
DEFAULT_NOISE_STRENGTH_DB = 12.0
#: Khung có tiếng người khi công suất vượt nền đang theo dõi ngần này dB. CHƯA ĐO trên mic loa.
DEFAULT_NOISE_VOICE_DB = 4.0

# ── AGC + bộ hạn đỉnh (agc.py), chạy sau khử tạp, trước các listener ─────────────────────
CONF_AGC_ENABLE = "agc_enable"
CONF_AGC_TARGET_DB = "agc_target_db"
CONF_AGC_MAX_GAIN_DB = "agc_max_gain_db"
CONF_AGC_SILENCE_DB = "agc_silence_db"
CONF_LIMITER_ENABLE = "limiter_enable"
CONF_LIMITER_CEILING = "limiter_ceiling"
#: MẶC ĐỊNH TẮT cả AGC lẫn bộ hạn đỉnh: chưa đo mức tiếng nói thật trên mic loa R1 nên chưa
#: biết đích RMS, mức tăng tối đa hay ngưỡng im lặng nào hợp; đã có amplify cố định +12 dB.
DEFAULT_AGC_ENABLE = False
#: Đích RMS của AGC (dBFS, RMS chứ không phải đỉnh). -20 dBFS là mức tiếng nói quen dùng cho
#: nhận dạng giọng; CHƯA ĐO trên mic loa R1.
DEFAULT_AGC_TARGET_DB = -20.0
#: Mức tăng tối đa của AGC (dB). CHƯA ĐO; chồng lên amplify +12 dB nên giữ nhỏ.
DEFAULT_AGC_MAX_GAIN_DB = 12.0
#: Dưới mức này (dBFS RMS) coi là khoảng nền/im lặng: AGC không tăng, mức tăng thả dần về 0 dB.
#: CHƯA ĐO (cần biết mức nền thật của phòng và mic).
DEFAULT_AGC_SILENCE_DB = -55.0
DEFAULT_LIMITER_ENABLE = False
#: Trần đỉnh của bộ hạn đỉnh, theo tỉ lệ biên độ tối đa (0,89 ≈ -1 dBFS).
DEFAULT_LIMITER_CEILING = 0.89

# ── Bộ đàm nửa công (HA → loa) và cổng phát về loa ──────────────────────────────────
CONF_PLAY_HOST = "play_host"
CONF_PLAY_PORT = "play_port"
#: 0 = chưa có kênh phát về loa → bộ đàm tắt. KHÔNG có cổng mặc định: phía loa CHƯA có dịch
#: vụ nhận PCM, nên chưa có số đo nào để chọn (xem docs/HOP-DONG-PHIA-LOA.md).
DEFAULT_PLAY_PORT = 0

CONF_TALK_THRESHOLD_DB = "talk_threshold_db"
CONF_TALK_SILENCE = "talk_silence_s"
CONF_TALK_PREROLL = "talk_preroll_s"
CONF_TALK_TAIL = "talk_tail_s"
#: Mặc định mượn từ bộ đàm camera Imou (đã đo THẬT trên camera + mic điện thoại). Trên loa R1
#: CHƯA ĐO: chưa biết mức ồn nền của đường go2rtc → loa, nên cả bốn số chỉ là điểm khởi đầu.
DEFAULT_TALK_THRESHOLD_DB = -45.0   # RMS từng khúc, dBFS; to hơn là có tiếng người
DEFAULT_TALK_SILENCE = 1.5          # im ngần này giây thì đóng kênh để nghe lại
DEFAULT_TALK_PREROLL = 0.3          # giữ ngần này giây ngay trước tiếng (khỏi mất đầu câu)
DEFAULT_TALK_TAIL = 0.5             # sau khi đóng, còn bỏ mic ngần này giây (loa còn vang)

#: Luồng phát về loa: PCM16 mono 16 kHz LE (cùng định dạng mic).
PLAY_RATE = MIC_RATE
#: Đầu vào bộ đàm từ go2rtc: A-law 8 kHz — định dạng go2rtc→HA đã chạy thật ở bộ đàm camera.
INTERCOM_RATE = 8000

# ── Phiên đàm thoại, từ đánh thức, trạng thái mic ───────────────────────────────────
CONF_WAKE_MODE = "wake_mode"
#: ``ha``: từ đánh thức do pipeline của HA dò → luồng mic về HA liên tục (hành vi ban đầu).
WAKE_HA = "ha"
#: ``speaker``: từ đánh thức chạy TRÊN LOA, HA không nhận byte mic nào cho tới khi loa báo
#: trigger (``POST /api/r1_speaker/wake/<entry>``) hoặc người bấm nút. **PHÍA LOA CHƯA CÓ** (CHỜ).
WAKE_SPEAKER = "speaker"
DEFAULT_WAKE_MODE = WAKE_HA
#: Địa chỉ HA mà loa / go2rtc gọi tới (đã kiểm ở options flow). Trống = tự đoán như trước.
CONF_HA_URL = "ha_url"
#: ADB tới loa để chạy hiệu ứng đèn (xem adb_client.py): địa chỉ adb-server, chế độ auto/server/direct.
CONF_ADB_SERVER = "adb_server"
CONF_ADB_MODE = "adb_mode"
DEFAULT_ADB_SERVER = "127.0.0.1:5037"
DEFAULT_ADB_MODE = "auto"
ADB_PORT = 5555

#: Một phiên (nút đàm thoại / từ đánh thức / bộ đàm) chạy tối đa ngần này giây kể từ lượt cuối.
SESSION_MAX_S = 60.0
#: Mở phiên mà luồng mic chưa nối được sau ngần này giây → đóng phiên, không treo.
SESSION_MIC_WAIT_S = 5.0
#: Loa đã báo «còn sống» (trigger hoặc nhịp tim) trong ngần này giây mới coi là đang nghe từ gọi.
WAKE_ALIVE_S = 120.0
#: ``binary_sensor.r1_tu_danh_thuc`` bật ngần này giây sau mỗi trigger.
WAKE_PULSE_S = 5.0

#: Giữ nhạc khi báo tin: chờ renderer rời trạng thái «đang phát» sau lệnh tạm dừng, chờ TTS
#: bắt đầu / kết thúc, chờ nhạc phát lại sau khi khôi phục.
PAUSE_CONFIRM_S = 2.0
ANNOUNCE_START_WAIT = 6.0
ANNOUNCE_MAX = 120.0
RESTORE_WAIT = 8.0

#: Trạng thái mic (sensor.r1_trang_thai_mic). tắt: không nghe, không byte nào rời loa;
#: nghe: loa đang chờ từ đánh thức (chưa gửi gì về HA); gửi: byte mic đang về HA.
MIC_TAT, MIC_NGHE, MIC_GUI = "tat", "nghe", "gui"
MIC_STATUSES = (MIC_TAT, MIC_NGHE, MIC_GUI)

EVENT_WAKE = f"{DOMAIN}_wake"
EVENT_SESSION_REFUSED = f"{DOMAIN}_session_refused"

#: Khoá trong ``entry.data`` cho đường POST/GET bộ đàm (go2rtc không gửi được header
#: Authorization từ lệnh exec nên khoá nằm trong URL; sinh một lần, giữ qua lần khởi động).
CONF_INTERCOM_KEY = "intercom_key"

#: Lệnh ghi lên loa ĐÃ XÁC NHẬN bằng ghi thật + đọc lại (21/10/2026). Mọi lệnh khác của
#: tích hợp (set_eq_enable, set_bass_strength, set_loudness_*, set_volume, preset) CHƯA xác nhận;
#: thẻ Lovelace gắn nhãn «chưa xác nhận» dựa vào danh sách này.
CONFIRMED_COMMANDS = frozenset({"set_eq_bandlevel", "set_bass_enable", "set_volume"})

#: Đường tĩnh của thẻ Lovelace (tệp nằm trong custom_components/r1_speaker/www).
CARD_URL = "/r1_speaker/r1-eq-card.js"
#: Thẻ đàm thoại (nút đàm thoại, trạng thái mic, tạm dừng/phát nhạc; nhúng thẻ EQ ở trên).
TALK_CARD_URL = "/r1_speaker/r1-talk-card.js"

#: Thẻ cài đặt (nhóm Âm thanh / Ánh sáng / Kết nối), ẨN cho tới khi bấm nút mở.
SETTINGS_CARD_URL = "/r1_speaker/r1-settings-card.js"

# ── Đèn LED theo chức năng (den.py / den_port.py / hieu_ung.py; xem docs/DEN-LED.md) ────────
#: Chức năng «lỗi» sáng ngần này giây sau mỗi lần lỗi rồi trả về chức năng đúng lúc đó.
#: ĐỀ XUẤT, CHƯA ĐO.
LIGHT_ERROR_HOLD_S = 3.0
#: Lệnh «thử đèn» của thẻ giữ chức năng được thử ngần này giây rồi trả về trạng thái thật.
LIGHT_PREVIEW_S = 5.0
LIGHT_PREVIEW_MAX_S = 30.0

# ── Từ đánh thức (cài đặt; HA chưa có mic loa nên chưa nghe được; mặc định TẮT) ──────────
CONF_WAKE_ENABLE = "wake_enable"
CONF_WAKE_WORD = "wake_word"
CONF_WAKE_SENSITIVITY = "wake_sensitivity"
DEFAULT_WAKE_ENABLE = False
DEFAULT_WAKE_WORD = ""           # CHƯA CHỌN từ khoá
DEFAULT_WAKE_SENSITIVITY = 0.5   # CHƯA ĐO trên mic loa R1

#: Thẻ gộp: một tài nguyên duy nhất, nạp cả ba thẻ con (EQ, đàm thoại, cài đặt).
CARD_GOP_URL = "/r1_speaker/r1-card.js"
