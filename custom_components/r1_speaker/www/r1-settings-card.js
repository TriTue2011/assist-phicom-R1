/* r1-settings-card — thẻ Lovelace CÀI ĐẶT cho loa Phicomm R1 (tích hợp r1_speaker).
 *
 * Mặc định chỉ hiện tiêu đề + nút «Cài đặt»; bấm nút mới mở bảng cài đặt, chia ba nhóm:
 *   Âm thanh  — âm lượng, EQ 5 dải, tăng mic, tắt mic; khử tạp / AGC / bộ hạn đỉnh (CHỈ ĐỌC: là
 *               tuỳ chọn của mục cài đặt, không phải thực thể; sửa ở trang Tuỳ chọn của tích hợp);
 *   Ánh sáng  — mục «Thử đèn» RIÊNG (chọn vùng, hiệu ứng, thông số rồi bấm Thử; không lưu), và cài đặt đèn theo
 *               chức năng: mỗi chức năng có bật/tắt + hai vùng (đáy, viền), mỗi vùng một hiệu ứng với bộ thông số
 *               RIÊNG của hiệu ứng đó (form dựng từ danh mục ``danh_muc`` do HA gửi);
 *   Kết nối   — host, cổng, ha_url, khoá bộ đàm (chỉ «đã có / chưa có», KHÔNG hiện giá trị khoá);
 *   Phát & khởi động lại (NV302) — đường phát nhạc/tin, tin báo đi đường ngược với nhạc, hạ nhạc nền; lịch khởi động lại
 *               (bật/tắt, giờ, từng thứ trong tuần), tự khởi động lại khi loa treo, nút «Khởi động lại ngay», lần cuối + lý do.
 *               MỖI cài đặt là MỘT thực thể chuẩn (switch / select / number / time) của tích hợp, lưu vào tuỳ chọn của mục
 *               (cùng nguồn với hộp tuỳ chọn HA): thẻ chỉ đọc/ghi qua thực thể, KHÔNG có nơi lưu thứ hai.
 *
 * Thẻ KHÔNG gọi loa: chỉ đọc thực thể HA (sensor.r1_cai_dat và các thực thể EQ / âm lượng / mic) và
 * gọi dịch vụ HA (number.set_value, switch.turn_on/off, r1_speaker.set_light_function,
 * r1_speaker.preview_light, r1_speaker.stop_preview_light). Hiệu ứng chạy trên loa qua ADB (HA nối adb-server hoặc
 * nối thẳng loa); thẻ báo đang đi đường nào và lỗi nếu có.
 *
 * Cấu hình tối thiểu:   type: custom:r1-settings-card
 * Nhiều loa:            device_id: <mã thiết bị>
 * Chỉ định tay:         entities: { settings: sensor.x, volume: number.y, mic_gain: number.z,
 *                         mute: switch.u }
 */
(function () {
  "use strict";
  var BUILD = "2026-11-03.31";

  var PLATFORM = "r1_speaker";
  var FUNCTIONS = ["cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi", "tat_mic"];
  var TABS = ["audio", "light", "conn", "sys"];
  var PHIM = ["don", "doi", "ba", "giu"];   // cử chỉ phím của loa: một lần, hai lần, ba lần, giữ
  var DAYS = ["t2", "t3", "t4", "t5", "t6", "t7", "cn"];
  var OPTIONS_PATH = "/config/integrations/integration/r1_speaker";
  var TEXT = {
    vi: {
      title: "Loa R1 — Cài đặt", open: "Cài đặt", close: "Đóng",
      audio: "Âm thanh", light: "Ánh sáng", conn: "Kết nối",
      none: "Không tìm thấy thực thể r1_speaker nào.",
      volume: "Âm lượng", eq: "EQ", mic_gain: "Tăng mic (dB)", mute: "Tắt mic",
      adv: "Cài đặt nâng cao", adv_note: "Mọi số là mặc định CHƯA đo trên loa R1. Đổi một mục sẽ nạp lại tích hợp để áp dụng (mic nối lại sau vài giây).",
      adv_group: { thoai: "Cổng thoại bộ đàm", khu_tap: "Khử tạp âm", agc: "Tự chỉnh mức (AGC)", han_dinh: "Bộ hạn đỉnh", song_cong: "Đàm thoại song công" },
      adv_label: {
        talk_threshold_db: "Ngưỡng có tiếng người (dBFS)", talk_silence_s: "Im bao lâu thì đóng loa (giây)",
        talk_preroll_s: "Giữ đầu câu (giây)", talk_tail_s: "Chờ loa tắt trước khi mở mic (giây)",
        noise_suppress: "Bật khử tạp", noise_strength_db: "Giảm tối đa mỗi dải (dB)", noise_voice_db: "Ngưỡng nhận tiếng người (dB trên nền)",
        agc_enable: "Bật AGC", agc_target_db: "Mức đích RMS (dBFS)", agc_max_gain_db: "Tăng tối đa (dB)", agc_silence_db: "Dưới mức này coi là im lặng (dBFS)",
        limiter_enable: "Bật hạn đỉnh", limiter_ceiling: "Trần biên độ (0,89 ≈ -1 dBFS)",
        duplex_vad_threshold: "Ngưỡng tiếng người VAD (0 = không lọc, 0,2–0,5 = lọc)", duplex_preroll_s: "Giữ tiếng trước câu nói (giây)",
        duplex_hangover_s: "Giữ tiếng sau câu nói (giây)", duplex_max_s: "Thời gian tối đa của phiên (giây)",
        duplex_duck: "Cắt vọng: bỏ tiếng mic nhỏ khi HA đang phát", duplex_duck_db: "Ngưỡng mức tiếng cắt vọng (dBFS)" },
      read_only: "Chỉ đọc — sửa ở trang Tuỳ chọn của tích hợp", noise: "Khử tạp âm",
      agc: "Tự chỉnh mức (AGC)", limiter: "Bộ hạn đỉnh", on: "Bật", off: "Tắt", goto: "Mở tuỳ chọn",
      sink_pending: "Chưa có đường ADB tới loa: cài đặt được lưu nhưng đèn CHƯA sáng.",
      sink_ready: "Đèn: ADB sẵn sàng", sink_err: "Lỗi gần nhất",
      adb_server: "qua adb-server", adb_direct: "nối thẳng loa", adb_idle: "chưa dùng", adb_lbl: "Đường ADB",
      thu_title: "Thử đèn", thu_note: "Chạy tạm vài giây rồi tự trả đèn về trạng thái thật. Không lưu gì; cài đặt từng chức năng nằm ở dưới.",
      zone: "Vùng", zone_day: "Đèn đáy (15 đèn RGB)", zone_vien: "Đèn viền (24 đèn, chỉ trắng)",
      thu_run: "Thử", thu_stop: "Dừng thử", thu_secs: "Thời gian thử (giây)", thu_on: "Đang thử",
      fn_title: "Cài đặt đèn theo chức năng", zone_off: "Tắt",
      fn: { cho: "Chờ / từ đánh thức", nghe: "Đang nghe", nghi: "Đang nghĩ", phan_hoi: "Đang trả lời",
            dam_thoai: "Đàm thoại", phat_nhac: "Phát nhạc", loi: "Lỗi", tat_mic: "Tắt mic" },
      enabled: "Bật", effect: "Hiệu ứng", active: "đang áp dụng", proposal: "mặc định đề xuất, chưa đo",
      fw: "Đèn theo nhạc của firmware (chỉnh ở các thực thể «Đèn theo nhạc», «Độ sáng/Sắc độ đèn nhạc»)",
      fw_on: "bật", fw_luma: "luma", fw_chroma: "chroma", unknown: "không rõ",
      host: "Địa chỉ loa", port: "Cổng điều khiển / EQ", mic: "Mic (host:cổng)",
      play: "Phát về loa (host:cổng)", wake: "Từ đánh thức chạy ở", ha_url: "Địa chỉ HA loa gọi tới",
      key: "Khoá bộ đàm", key_set: "Đã có (không hiện giá trị)", key_unset: "Chưa có", empty: "(trống)",
      conn_note: "Sửa địa chỉ loa và địa chỉ HA ở trang Tuỳ chọn: ở đó có kiểm kết nối trước khi lưu.",
      apk: "APK trên loa", apk_on: "Đang nối vào HA", apk_off: "Chưa nối — cài APK xong phải chạy lệnh cấu hình MỘT lần (bấm «Hiện lệnh cài APK» bên dưới); sau đó APK tự chạy mỗi khi loa khởi động",
      listen: "Cổng nghe mic (HA tự cấp)", key_auto: "Khoá nghe mic: HA tự sinh, không cần nhập",
      apk_note: "Chạy lệnh trên một máy có adb. Loa đã cấu hình rồi thì lệnh đổi cấu hình bị BỎ QUA: chạy trước adb shell /system/bin/pm clear vn.r1.bodam (xoá cấu hình cũ).",
      apk_show: "Hiện lệnh cài APK (quản trị viên)", apk_hide: "Ẩn lệnh", apk_err: "Không lấy được lệnh",
      unconfirmed: "chưa xác nhận",
      sys: "Phát & khởi động lại",
      play_title: "Phát nhạc & tin báo", path: "Đường phát",
      path_note: "Nhạc và tin báo ra loa bằng đường nào. AirPlay do tích hợp tự gửi, cần ffmpeg trên máy chạy HA.",
      paths: { dlna: "Chỉ DLNA (mặc định)", dlna_truoc: "DLNA trước, hỏng thì AirPlay", airplay_truoc: "AirPlay trước, hỏng thì DLNA", airplay: "Chỉ AirPlay" },
      port: "Cổng AirPlay", port_note: "Cổng AirPlay (RAOP) của loa, mặc định 5012; đổi nếu AirPlay không nối được sau khi loa khởi động lại.",
      parallel: "Tin báo đi đường ngược với nhạc",
      parallel_note: "Chưa đo trên loa thật: chỉ bật khi muốn thử. Nhạc AirPlay thì tin báo qua DLNA, nhạc DLNA thì tin báo qua AirPlay, nhạc không dừng; lỗi thì về đường thường.",
      duck_title: "Nâng cao: hạ nhạc nền", duck: "Hạ nhạc nền khi loa nói", duck_nac: "Số nấc hạ",
      duck_note: "Chưa đo trên loa thật. Chỉ có tác dụng khi tin báo song song bật; nhạc nhỏ đi rồi trả đúng mức cũ.",
      dsp_title: "Xử lý âm thanh mic & âm lượng media", engine: "Động cơ xử lý âm thanh mic",
      engines: { noi_bo: "Nội bộ (mặc định)", nang_cao: "Nâng cao (Speex + khử vọng miền tần số)" },
      engine_note: "Nâng cao: khử tạp Speex + khử vọng miền tần số tự dò độ trễ loa → mic; chưa đo trên loa thật. Số đo ERLE hiện ngay trên thẻ đàm thoại.",
      noise_on: "Khử ồn mic", aec_on: "Khử vọng trong đàm thoại song công",
      aec_note: "Tắt «Mic loa song song» ở thẻ đàm thoại (nửa công) là cách chắc chắn nhất để hết vọng.",
      media_vol: "Âm lượng nhạc (media)", media_note: "Chỉ hạ NHẠC bằng phần mềm (đường AirPlay); tin báo/TTS và âm lượng loa không đổi.",
      phim_title: "Phím trên loa", phim_note: "Loa chỉ có một phím: mỗi cử chỉ một hành động. Cuối danh sách là «Chạy: script / tự động hoá / cảnh / nút».",
      phim_cc: { don: "Nhấn một lần", doi: "Nhấn hai lần", ba: "Nhấn ba lần", giu: "Nhấn giữ" },
      rs_title: "Khởi động lại loa",
      resp: "Tình trạng loa", resp_state: { phan_hoi: "Loa đang phản hồi", treo: "Loa TREO: mạng còn thông nhưng ứng dụng trên loa im",
        mat_mang: "Loa MẤT MẠNG: không trả lời", dang_khoi_dong: "Loa đang khởi động lại", chua_biet: "Chưa biết (vừa khởi động HA)" },
      rs_sched: "Khởi động lại theo lịch", rs_time: "Giờ khởi động lại", rs_days: "Các ngày trong tuần",
      rs_sched_note: "Mặc định tắt. Tới giờ mà loa đang có phiên hoặc đang phát nhạc thì hoãn tối đa 45 phút.",
      day: { t2: "T2", t3: "T3", t4: "T4", t5: "T5", t6: "T6", t7: "T7", cn: "CN" },
      day_full: { t2: "Thứ hai", t3: "Thứ ba", t4: "Thứ tư", t5: "Thứ năm", t6: "Thứ sáu", t7: "Thứ bảy", cn: "Chủ nhật" },
      rs_hang: "Tự khởi động lại khi loa treo",
      rs_hang_note: "Mặc định tắt. Chỉ khi mạng còn thông mà loa im từ 15 phút, cần ADB; tối đa một lần mỗi 6 giờ. Loa mất mạng thì HA không làm được gì.",
      rs_now: "Khởi động lại ngay", rs_now_confirm: "Khởi động lại loa ngay bây giờ? Loa sẽ im khoảng nửa phút.",
      rs_last: "Lần khởi động lại cuối", rs_never: "chưa có", rs_reason: "lý do", rs_next: "Lần tới theo lịch", rs_defer: "Đang hoãn vì",
      rs_reasons: { lich: "lịch", treo: "loa treo", bam: "bấm tay" }, rs_failed: "không thành",
    },
    en: {
      title: "R1 speaker — Settings", open: "Settings", close: "Close",
      audio: "Audio", light: "Light", conn: "Connection",
      none: "No r1_speaker entity found.",
      volume: "Volume", eq: "EQ", mic_gain: "Mic gain (dB)", mute: "Mute mic",
      adv: "Advanced settings", adv_note: "Every value is a default NOT yet measured on the R1. Changing one reloads the integration to apply it (the mic reconnects in a few seconds).",
      adv_group: { thoai: "Intercom voice gate", khu_tap: "Noise suppression", agc: "Auto gain (AGC)", han_dinh: "Peak limiter", song_cong: "Duplex call" },
      adv_label: {
        talk_threshold_db: "Voice threshold (dBFS)", talk_silence_s: "Silence before closing the speaker (s)",
        talk_preroll_s: "Pre-roll kept before speech (s)", talk_tail_s: "Wait after playback before reopening the mic (s)",
        noise_suppress: "Noise suppression on", noise_strength_db: "Max reduction per band (dB)", noise_voice_db: "Voice threshold (dB above floor)",
        agc_enable: "AGC on", agc_target_db: "Target RMS level (dBFS)", agc_max_gain_db: "Max gain (dB)", agc_silence_db: "Below this counts as silence (dBFS)",
        limiter_enable: "Limiter on", limiter_ceiling: "Ceiling (0.89 ≈ -1 dBFS)",
        duplex_vad_threshold: "VAD voice threshold (0 = no filtering, 0.2–0.5 = filter)", duplex_preroll_s: "Audio kept before speech (s)",
        duplex_hangover_s: "Audio kept after speech (s)", duplex_max_s: "Max session length (s)",
        duplex_duck: "Echo cut: drop quiet mic audio while HA is playing", duplex_duck_db: "Echo-cut level threshold (dBFS)" },
      read_only: "Read-only — change it on the integration's Options page",
      noise: "Noise suppression", agc: "Auto gain (AGC)", limiter: "Peak limiter", on: "On", off: "Off",
      goto: "Open options",
      sink_pending: "No ADB path to the speaker yet: settings are saved but the light does NOT shine.",
      sink_ready: "Light: ADB ready", sink_err: "Last error",
      adb_server: "via adb-server", adb_direct: "straight to the speaker", adb_idle: "not used yet", adb_lbl: "ADB path",
      thu_title: "Try a light", thu_note: "Runs for a few seconds, then the lights return to their real state. Nothing is saved; per-function settings are below.",
      zone: "Zone", zone_day: "Base light (15 RGB LEDs)", zone_vien: "Rim light (24 LEDs, white only)",
      thu_run: "Try", thu_stop: "Stop trying", thu_secs: "Try time (seconds)", thu_on: "Trying",
      fn_title: "Light settings per function", zone_off: "Off",
      fn: { cho: "Idle / wake word", nghe: "Listening", nghi: "Thinking", phan_hoi: "Responding",
            dam_thoai: "Conversation", phat_nhac: "Music playing", loi: "Error", tat_mic: "Mic muted" },
      enabled: "On", effect: "Effect", active: "in effect", proposal: "suggested default, not measured",
      fw: "Speaker firmware's own music light (set with the «Music light» entities)",
      fw_on: "on", fw_luma: "luma", fw_chroma: "chroma", unknown: "unknown",
      host: "Speaker address", port: "Control / EQ port", mic: "Mic (host:port)",
      play: "Playback to speaker (host:port)", wake: "Wake word runs on", ha_url: "HA address the speaker calls",
      key: "Intercom key", key_set: "Set (value is never shown)", key_unset: "Not set", empty: "(empty)",
      conn_note: "Change the speaker and HA addresses on the Options page, which checks the connection before saving.",
      apk: "APK on the speaker", apk_on: "Connected to HA", apk_off: "Not connected — after installing the APK you must run the setup command ONCE (press «Show APK setup command» below); after that the APK starts by itself whenever the speaker boots",
      listen: "Mic listen port (issued by HA)", key_auto: "Mic listen key: generated by HA, nothing to type",
      apk_note: "Run it from a machine with adb. A speaker that is already configured IGNORES the command: first run adb shell /system/bin/pm clear vn.r1.bodam (clears the old configuration).",
      apk_show: "Show APK setup command (administrators)", apk_hide: "Hide command", apk_err: "Could not get the command",
      unconfirmed: "unconfirmed",
      sys: "Playback & restart",
      play_title: "Music & announcements", path: "Playback path",
      path_note: "Which path music and announcements take to the speaker. AirPlay is sent by this integration and needs ffmpeg on the HA host.",
      paths: { dlna: "DLNA only (default)", dlna_truoc: "DLNA first, AirPlay if it fails", airplay_truoc: "AirPlay first, DLNA if it fails", airplay: "AirPlay only" },
      port: "AirPlay port", port_note: "The speaker's AirPlay (RAOP) port, default 5012; change it if AirPlay cannot connect after the speaker restarted.",
      parallel: "Announcements on the opposite path to the music",
      parallel_note: "Not measured on a real speaker: enable only to experiment. Music on AirPlay → announcement over DLNA, music on DLNA → announcement over AirPlay; the music keeps playing; on error it falls back to the normal path.",
      duck_title: "Advanced: duck background music", duck: "Duck music while speaking", duck_nac: "Ducking steps",
      duck_note: "Not measured on a real speaker. Only applies when parallel announcements are on; music drops, then returns to the exact previous level.",
      dsp_title: "Mic audio processing & media volume", engine: "Mic audio engine",
      engines: { noi_bo: "Built-in (default)", nang_cao: "Advanced (Speex + frequency-domain echo cancel)" },
      engine_note: "Advanced: Speex noise suppression + frequency-domain echo cancel that finds the speaker→mic delay itself; not measured on a real speaker. The ERLE readout shows on the call card.",
      noise_on: "Mic noise suppression", aec_on: "Echo cancel in duplex call",
      aec_note: "Turning «Parallel mic» off on the call card (half duplex) is the surest way to remove echo.",
      media_vol: "Music volume (media)", media_note: "Lowers MUSIC only, in software (AirPlay path); announcements/TTS and speaker volume are unchanged.",
      phim_title: "Speaker button", phim_note: "The speaker has one button: one action per gesture. The list ends with «Run: script / automation / scene / button».",
      phim_cc: { don: "Single press", doi: "Double press", ba: "Triple press", giu: "Long press" },
      rs_title: "Restart the speaker",
      resp: "Speaker status", resp_state: { phan_hoi: "Speaker is responding", treo: "Speaker is HUNG: network up but its app is silent",
        mat_mang: "Speaker OFFLINE: no answer", dang_khoi_dong: "Speaker is restarting", chua_biet: "Unknown (HA just started)" },
      rs_sched: "Scheduled restart", rs_time: "Restart time", rs_days: "Days of the week",
      rs_sched_note: "Off by default. If a session or music is active at that time, it waits up to 45 minutes.",
      day: { t2: "Mon", t3: "Tue", t4: "Wed", t5: "Thu", t6: "Fri", t7: "Sat", cn: "Sun" },
      day_full: { t2: "Monday", t3: "Tuesday", t4: "Wednesday", t5: "Thursday", t6: "Friday", t7: "Saturday", cn: "Sunday" },
      rs_hang: "Restart by itself when hung",
      rs_hang_note: "Off by default. Only when the network is up but the speaker has been silent for 15 minutes; needs ADB; at most once per 6 hours. If the speaker is offline HA can do nothing.",
      rs_now: "Restart now", rs_now_confirm: "Restart the speaker now? It will be silent for about half a minute.",
      rs_last: "Last restart", rs_never: "none yet", rs_reason: "reason", rs_next: "Next scheduled", rs_defer: "Postponed because",
      rs_reasons: { lich: "schedule", treo: "hung speaker", bam: "button" }, rs_failed: "failed",
    },
  };

  function lang(hass) {
    var l = ((hass && (hass.language || (hass.locale && hass.locale.language))) || "vi");
    return l.toLowerCase().indexOf("vi") === 0 ? "vi" : "en";
  }
  function stateOf(hass, id) { return id && hass && hass.states ? hass.states[id] : undefined; }
  function isUp(st) { return !!st && st.state !== "unavailable" && st.state !== "unknown"; }
  function num(v, d) { var n = parseFloat(v); return isFinite(n) ? n : d; }

  function discover(hass, config) {
    var reg = (hass && hass.entities) || {};
    var want = config.device_id || null;
    var mine = Object.keys(reg).filter(function (id) {
      var e = reg[id];
      return e && e.platform === PLATFORM && (!want || e.device_id === want);
    });
    if (!want && mine.length) {
      var devs = mine.map(function (id) { return reg[id].device_id; }).sort();
      mine = mine.filter(function (id) { return reg[id].device_id === devs[0]; });
    }
    var all = function (domain, key) {
      return mine.filter(function (id) {
        return id.split(".")[0] === domain && reg[id].translation_key === key;
      }).sort();
    };
    return {
      settings: all("sensor", "settings")[0], volume: all("number", "volume")[0],
      mic_gain: all("number", "mic_gain")[0], mute: all("switch", "mute")[0],
      bands: all("number", "eq_band"),
      duong_phat: all("select", "duong_phat")[0], tin_nguoc: all("switch", "tin_nguoc_nhac")[0],
      duck: all("switch", "ha_nhac_xuong")[0], duck_nac: all("number", "ha_nhac_nac")[0], cong_airplay: all("number", "cong_airplay")[0],
      kdl_bat: all("switch", "kdl_bat")[0], kdl_gio: all("time", "kdl_gio")[0], kdl_khi_treo: all("switch", "kdl_khi_treo")[0],
      kdl_ngay: DAYS.map(function (d) { return all("switch", "kdl_ngay_" + d)[0]; }),
      dsp_dong_co: all("select", "dsp_dong_co")[0], khu_on: all("switch", "khu_on")[0], khu_vong: all("switch", "khu_vong")[0],
      am_luong_media: all("number", "am_luong_media")[0],
      phim: PHIM.map(function (cc) { return all("select", "phim_" + cc)[0]; }),
      reboot: all("button", "reboot")[0], kdl_cuoi: all("sensor", "khoi_dong_lai_cuoi")[0], phan_hoi: all("binary_sensor", "phan_hoi")[0],
    };
  }

  /* Dữ liệu thuần cho thẻ (kiểm được bằng Node): không đụng DOM. */
  function buildModel(hass, config) {
    config = config || {};
    var ent = discover(hass, config);
    var o = config.entities || {};
    Object.keys(o).forEach(function (k) { if (o[k]) ent[k] = o[k]; });
    var st = stateOf(hass, ent.settings);
    var a = (st && st.attributes) || {};
    var al = a.anh_sang || {}, am = a.am_thanh || {}, kn = a.ket_noi || {};
    var level = function (id, dmin, dmax, dstep) {
      var s = stateOf(hass, id), at = (s && s.attributes) || {};
      return { entity: id || null, present: !!id, available: isUp(s),
               value: isUp(s) ? num(s.state, null) : null,
               min: num(at.min, dmin), max: num(at.max, dmax), step: num(at.step, dstep) };
    };
    var bands = (ent.bands || []).map(function (id, i) {
      var b = level(id, -1500, 1500, 10), at = (stateOf(hass, id) || {}).attributes || {};
      b.band = at.band !== undefined ? Number(at.band) : i;
      b.label = at.label || ("EQ " + (b.band + 1));
      return b;
    }).sort(function (x, y) { return x.band - y.band; });
    var mst = stateOf(hass, ent.mute);
    var chuc = al.chuc_nang || {};
    var zoneOf = function (z) { z = z || {}; return { effect: z.effect || "tat", params: z.params || {} }; };
    var fns = FUNCTIONS.filter(function (k) { return chuc[k]; }).map(function (k) {
      var p = chuc[k];
      return { key: k, enabled: p.enabled === true, day: zoneOf(p.day), vien: zoneOf(p.vien), isDefault: p.mac_dinh === true,
               active: al.dang_ap_dung === k };
    });
    var fw = al.den_nhac_firmware || {};
    var sw = function (id) {
      var q = stateOf(hass, id);
      return { entity: id || null, present: !!id, available: isUp(q), on: isUp(q) ? q.state === "on" : null };
    };
    var sel = stateOf(hass, ent.duong_phat), tm = stateOf(hass, ent.kdl_gio), last = stateOf(hass, ent.kdl_cuoi), ph = stateOf(hass, ent.phan_hoi);
    var la = (last && last.attributes) || {}, pa = (ph && ph.attributes) || {};
    var sys = {
      play: {
        path: { entity: ent.duong_phat || null, present: !!ent.duong_phat, available: isUp(sel), value: isUp(sel) ? sel.state : null,
                options: (sel && sel.attributes && sel.attributes.options) || [] },
        parallel: sw(ent.tin_nguoc), duck: sw(ent.duck), duckNac: level(ent.duck_nac, 1, 14, 1), port: level(ent.cong_airplay, 1, 65535, 1),
      },
      restart: {
        enabled: sw(ent.kdl_bat), onHang: sw(ent.kdl_khi_treo),
        time: { entity: ent.kdl_gio || null, present: !!ent.kdl_gio, available: isUp(tm), value: isUp(tm) ? String(tm.state).slice(0, 5) : null },
        days: DAYS.map(function (d, i) { var x = sw(ent.kdl_ngay[i]); x.code = d; return x; }),
        button: { entity: ent.reboot || null, present: !!ent.reboot },
        last: { present: !!ent.kdl_cuoi, at: isUp(last) ? last.state : null, reason: la.ly_do || null, result: la.ket_qua || null,
                next: la.ke_tiep || null, deferring: la.dang_hoan || null },
        resp: { present: !!ent.phan_hoi, reason: pa.ly_do || null },
      },
    };
    var fmtOpt = function (st, o) {
      try { if (typeof hass.formatEntityState === "function") { var r = hass.formatEntityState(st, o); if (r) return String(r); } } catch (e) { /* giao diện cũ: dùng khoá thô */ }
      return o;
    };
    var eng = stateOf(hass, ent.dsp_dong_co);
    sys.dsp = {
      engine: { entity: ent.dsp_dong_co || null, present: !!ent.dsp_dong_co, available: isUp(eng), value: isUp(eng) ? eng.state : null,
                options: (eng && eng.attributes && eng.attributes.options) || [] },
      noise: sw(ent.khu_on), aec: sw(ent.khu_vong), media: level(ent.am_luong_media, 0, 100, 5),
    };
    sys.phim = PHIM.map(function (cc, i) {
      var st = stateOf(hass, ent.phim[i]), ops = (st && st.attributes && st.attributes.options) || [];
      return { code: cc, entity: ent.phim[i] || null, present: !!ent.phim[i], available: isUp(st), value: isUp(st) ? st.state : null,
               options: ops, labels: ops.map(function (o) { return fmtOpt(st, o); }) };
    });
    sys.entities = [sys.play.path, sys.play.parallel, sys.play.duck, sys.play.duckNac, sys.play.port, sys.restart.enabled, sys.restart.onHang,
                    sys.restart.time, sys.restart.button, sys.dsp.engine, sys.dsp.noise, sys.dsp.aec, sys.dsp.media]
      .concat(sys.restart.days, sys.phim).map(function (x) { return x.entity; }).filter(Boolean);
    return {
      found: !!(ent.settings || ent.volume || bands.length),
      sys: sys,
      gop: config.gop === true,
      offline: !!ent.settings && !isUp(st),
      settings: { entity: ent.settings || null, present: !!ent.settings },
      audio: {
        volume: level(ent.volume, 0, 15, 1), bands: bands, micGain: level(ent.mic_gain, 0, 30, 1),
        mute: { entity: ent.mute || null, present: !!ent.mute, available: isUp(mst),
                on: isUp(mst) ? mst.state === "on" : null },
        noise: am.khu_tap || null, agc: am.agc || null, limiter: am.han_dinh || null,
        adv: Array.isArray(am.nang_cao) ? am.nang_cao : [],
      },
      light: {
        sink: { state: al.dich_vu_den || null, ready: al.dich_vu_den === "san_sang", error: al.loi_dich_vu || null,
                path: al.duong_adb || null, mode: al.che_do_adb || null },
        functions: fns, current: al.dang_ap_dung || null,
        catalog: al.danh_muc || { day: [], vien: [] }, thu: al.thu || {},
        firmware: { on: fw.bat === undefined ? null : fw.bat, luma: fw.luma === undefined ? null : fw.luma,
                    chroma: fw.chroma === undefined ? null : fw.chroma },
      },
      conn: {
        host: kn.host || "", port: kn.cong || null, micHost: kn.mic_host || "", micPort: kn.mic_cong || null,
        playHost: kn.phat_host || "", playPort: kn.phat_cong || null, wake: kn.che_do_tu_danh_thuc || "",
        haUrl: kn.ha_url || "", keySet: kn.khoa_bo_dam === "da_co", optionsPath: kn.tuy_chon || OPTIONS_PATH,
        apk: kn.apk_dang_noi === true, listenPort: kn.cong_nghe_mic || null, listenKeySet: kn.khoa_nghe_mic === "da_co",
        admin: !!(hass && hass.user && hass.user.is_admin),
      },
    };
  }

  /* Trạng thái giao diện: ĐÓNG mặc định. ``thu`` là mục Thử RIÊNG (chỉ nằm trong thẻ, không lưu ở HA). */
  function initialUi() { return { open: false, tab: "audio", thu: { zone: "day", effect: null, params: {}, secs: 8 } }; }
  function reduceUi(ui, action) {
    var thu = ui.thu || initialUi().thu;
    if (action.type === "toggle") return { open: !ui.open, tab: ui.tab, thu: thu };
    if (action.type === "tab" && TABS.indexOf(action.tab) >= 0) return { open: ui.open, tab: action.tab, thu: thu };
    if (action.type === "thu_zone" && (action.zone === "day" || action.zone === "vien")) {
      return { open: ui.open, tab: ui.tab, thu: { zone: action.zone, effect: null, params: {}, secs: thu.secs } };
    }
    if (action.type === "thu_effect") return { open: ui.open, tab: ui.tab, thu: { zone: thu.zone, effect: action.effect, params: {}, secs: thu.secs } };
    if (action.type === "thu_param") {
      var p = {}; Object.keys(thu.params).forEach(function (k) { p[k] = thu.params[k]; }); p[action.key] = action.value;
      return { open: ui.open, tab: ui.tab, thu: { zone: thu.zone, effect: thu.effect, params: p, secs: thu.secs } };
    }
    if (action.type === "thu_secs") return { open: ui.open, tab: ui.tab, thu: { zone: thu.zone, effect: thu.effect, params: thu.params, secs: action.secs } };
    return ui;
  }

  /* Hành động của người dùng → lệnh gọi dịch vụ HA (hoặc null). Không bao giờ gọi loa. */
  function makeCall(model, a) {
    var sid = model.settings.entity;
    if (a.type === "vol" && model.audio.volume.entity) {
      return ["number", "set_value", { entity_id: model.audio.volume.entity, value: Number(a.value) }];
    }
    if (a.type === "eq" && a.entity) return ["number", "set_value", { entity_id: a.entity, value: Number(a.value) }];
    if (a.type === "micgain" && model.audio.micGain.entity) {
      return ["number", "set_value", { entity_id: model.audio.micGain.entity, value: Number(a.value) }];
    }
    if (a.type === "mute" && model.audio.mute.entity) {
      return ["switch", a.on ? "turn_on" : "turn_off", { entity_id: model.audio.mute.entity }];
    }
    var sysOk = function (id) { return !!id && model.sys && model.sys.entities.indexOf(id) >= 0; };        // chỉ thực thể của thẻ này
    if (a.type === "sw" && sysOk(a.entity)) return ["switch", a.on ? "turn_on" : "turn_off", { entity_id: a.entity }];
    if (a.type === "sel" && sysOk(a.entity) && typeof a.value === "string") return ["select", "select_option", { entity_id: a.entity, option: a.value }];
    if (a.type === "sysnum" && sysOk(a.entity) && isFinite(Number(a.value))) return ["number", "set_value", { entity_id: a.entity, value: Number(a.value) }];
    if (a.type === "time" && sysOk(a.entity) && /^\d{2}:\d{2}$/.test(String(a.value))) return ["time", "set_value", { entity_id: a.entity, time: a.value + ":00" }];
    if (a.type === "reboot" && sysOk(a.entity)) return ["button", "press", { entity_id: a.entity }];
    if (!sid) return null;
    var coerce = function (field, v) {
      if (field === "enabled" || field === "rim" || field === "bat") return v === true || v === "true" || v === "on";
      if (field === "sang" || field === "che_do") return Math.round(Number(v));
      return String(v);
    };
    var zoneKey = function (z) { return z === "vien" ? "vien" : "day"; };
    var val = function (kind, v) { return kind === "range" ? Math.round(Number(v)) : String(v); };
    if (a.type === "fn" && FUNCTIONS.indexOf(a.key) >= 0 && a.field === "enabled") {
      return ["r1_speaker", "set_light_function", { entity_id: sid, function: a.key, enabled: coerce("enabled", a.value) }];
    }
    if (a.type === "fn_effect" && FUNCTIONS.indexOf(a.key) >= 0) {       // đổi hiệu ứng: thông số về mặc định của hiệu ứng mới
      var e = { entity_id: sid, function: a.key }; e[zoneKey(a.zone)] = { effect: String(a.effect) };
      return ["r1_speaker", "set_light_function", e];
    }
    if (a.type === "fn_param" && FUNCTIONS.indexOf(a.key) >= 0) {          // đổi MỘT thông số: giữ hiệu ứng, trộn vào thông số hiện có
      var pr = {}; pr[a.param] = val(a.kind, a.value);
      var f = { entity_id: sid, function: a.key }; f[zoneKey(a.zone)] = { params: pr };
      return ["r1_speaker", "set_light_function", f];
    }
    if (a.type === "thu_run" && a.effect) {
      var tp = {}; Object.keys(a.params || {}).forEach(function (k) { tp[k] = a.params[k]; });
      return ["r1_speaker", "preview_light", { entity_id: sid, zone: zoneKey(a.zone), effect: String(a.effect), params: tp,
                                                 seconds: Math.max(1, Math.min(30, Math.round(Number(a.secs) || 8))) }];
    }
    if (a.type === "thu_stop") return ["r1_speaker", "stop_preview_light", { entity_id: sid }];
    if (a.type === "opt" && typeof a.key === "string") {
      var kieuBat = !!a.bool;
      var val = kieuBat ? (a.value === true || a.value === "true" || a.value === "on") : Number(a.value);
      if (!kieuBat && !isFinite(val)) return null;
      return ["r1_speaker", "set_advanced_option", { entity_id: sid, key: a.key, value: val }];
    }
    if (a.type === "main") {                       // đèn chính RGB: mode/độ sáng/tốc độ qua cổng 8080 của loa
      var mn = { entity_id: sid };
      mn[a.field] = coerce(a.field, a.value);
      return ["r1_speaker", "set_main_light", mn];
    }
    return null;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function hexOk(c) { return /^#[0-9a-f]{6}$/i.test(c) ? c.toLowerCase() : "#000000"; }
  function isRed(c) {
    c = hexOk(c);
    return parseInt(c.slice(1, 3), 16) > 180 && parseInt(c.slice(3, 5), 16) < 80 && parseInt(c.slice(5, 7), 16) < 80;
  }
  function v(x, t) { return x === null || x === undefined || x === "" ? esc(t.empty) : esc(x); }
  function onoff(x, t) { return x && x.bat ? t.on : t.off; }

  function slider(attrs, value, min, max, step, disabled) {
    return '<input type="range" ' + attrs + ' min="' + esc(min) + '" max="' + esc(max) + '" step="' + esc(step) +
      '" value="' + esc(value === null ? min : value) + '"' + (disabled ? " disabled" : "") + ">";
  }

  function htmlAudio(m, t) {
    var A = m.audio, h = '<div data-panel="audio">';
    if (!m.gop) h += '<div class="row"><label>' + esc(t.volume) + "</label>" +
      slider("data-vol", A.volume.value, A.volume.min, A.volume.max, A.volume.step, !A.volume.available) +
      '<span class="val">' + esc(A.volume.value === null ? "—" : A.volume.value) + "</span></div>";
    if (!m.gop) {
      h += "<section><b>" + esc(t.eq) + "</b>";
      A.bands.forEach(function (b) {
        h += '<div class="row"><label>' + esc(b.label) + "</label>" +
          slider('data-eq="' + esc(b.entity) + '"', b.value, b.min, b.max, b.step, !b.available) +
          '<span class="val">' + esc(b.value === null ? "—" : b.value) + "</span></div>";
      });
      h += "</section>";
    }
    h += '<div class="row"><label>' + esc(t.mic_gain) + "</label>" +
      slider("data-mic-gain", A.micGain.value, A.micGain.min, A.micGain.max, A.micGain.step, !A.micGain.available) +
      '<span class="val">' + esc(A.micGain.value === null ? "—" : A.micGain.value + " dB") + "</span></div>";
    if (!m.gop) h += '<div class="row"><label>' + esc(t.mute) + '</label><input type="checkbox" data-mute' +
      (A.mute.on ? " checked" : "") + (A.mute.available ? "" : " disabled") + "></div>";
    if (A.adv && A.adv.length) {
      h += '<section class="adv"><b>' + esc(t.adv) + '</b><div class="note">' + esc(t.adv_note) + "</div>";
      var gr = "";
      A.adv.forEach(function (o) {
        if (o.nhom !== gr) { gr = o.nhom; h += '<div class="grp">' + esc((t.adv_group || {})[gr] || gr) + "</div>"; }
        var lb = (t.adv_label || {})[o.k] || o.k, ch = o.v !== o.mac_dinh ? " *" : "";
        h += '<div class="row"><label>' + esc(lb + ch) + "</label>";
        if (o.kieu === "bat") {
          h += '<input type="checkbox" data-opt="' + esc(o.k) + '" data-bool="1"' + (o.v ? " checked" : "") + ">";
        } else {
          h += '<input type="number" data-opt="' + esc(o.k) + '" min="' + esc(o.min) + '" max="' + esc(o.max) +
            '" step="' + esc(o.buoc) + '" value="' + esc(o.v) + '">';
        }
        h += "</div>";
      });
      h += "</section>";
    }
    h += '<button class="sec" data-goto>' + esc(t.goto) + "</button></div>";
    return h;
  }

  /* ── Nhóm Ánh sáng: danh mục hiệu ứng do HA gửi (den_hieu_ung.py); form dựng theo thông số CỦA TỪNG hiệu ứng. ── */
  function nm(o, lg) { return lg === "vi" ? o.vi : o.en; }
  function findEffect(L, zone, id) {
    return ((L.catalog || {})[zone] || []).filter(function (e) { return e.id === id; })[0] || null;
  }
  function paramShown(p, values) { return !p.chi_khi || values[p.chi_khi.key] === p.chi_khi.value; }
  function paramValue(p, values) { return values[p.key] === undefined ? p.default : values[p.key]; }
  /* ``attrs``: chuỗi thuộc tính data-* gắn vào MỌI ô để bộ lắng nghe biết đây là thông số nào. */
  function htmlParams(eff, values, attrs, lg) {
    var h = "";
    (eff ? eff.params : []).forEach(function (p) {
      if (!paramShown(p, values)) return;
      var cur = paramValue(p, values), a = attrs + ' data-param="' + esc(p.key) + '" data-kind="' + esc(p.kind) + '"';
      h += '<div class="row"><label>' + esc(nm(p, lg)) + "</label>";
      if (p.kind === "range") {
        h += slider(a + ' data-unit="' + esc(p.unit || "") + '"', cur, p.min, p.max, p.step, false) +
          '<span class="val">' + esc(cur) + esc(p.unit || "") + "</span>";
      } else if (p.kind === "color") {
        h += '<input type="color" ' + a + ' value="' + esc(hexOk(cur)) + '">';
      } else {
        h += "<select " + a + ">" + (p.options || []).map(function (o) {
          return '<option value="' + esc(o.value) + '"' + (cur === o.value ? " selected" : "") + ">" + esc(nm(o, lg)) + "</option>";
        }).join("") + "</select>";
      }
      h += "</div>";
    });
    return h;
  }
  function effectOptions(L, zone, selected, t, lg, withOff) {
    var o = withOff ? '<option value="tat"' + (selected === "tat" ? " selected" : "") + ">" + esc(t.zone_off) + "</option>" : "";
    ((L.catalog || {})[zone] || []).forEach(function (e) {
      o += '<option value="' + esc(e.id) + '"' + (selected === e.id ? " selected" : "") + ">" + esc(nm(e, lg)) + "</option>";
    });
    return o;
  }

  /* Hiệu ứng + thông số ĐẦY ĐỦ của mục Thử (mặc định của hiệu ứng, phủ giá trị người dùng đã đổi). */
  function thuEffective(L, ui) {
    var thu = (ui && ui.thu) || initialUi().thu, list = (L.catalog || {})[thu.zone] || [];
    var id = thu.effect && findEffect(L, thu.zone, thu.effect) ? thu.effect : (list[0] ? list[0].id : null);
    var eff = id ? findEffect(L, thu.zone, id) : null, params = {};
    (eff ? eff.params : []).forEach(function (p) { params[p.key] = thu.params[p.key] !== undefined ? thu.params[p.key] : p.default; });
    (eff ? eff.params : []).forEach(function (p) { if (!paramShown(p, params)) delete params[p.key]; });
    return { zone: thu.zone, effect: id, params: params, secs: thu.secs, def: eff };
  }

  function htmlThu(L, ui, t, lg) {
    var e = thuEffective(L, ui), dang = Object.keys(L.thu || {}).length > 0;
    return '<section data-thu><details class="grp" open><summary><b>' + esc(t.thu_title) + "</b>" +
      (dang ? ' <span class="tag">' + esc(t.thu_on) + "</span>" : "") + "</summary>" +
      '<div class="note">' + esc(t.thu_note) + "</div>" +
      '<div class="row"><label>' + esc(t.zone) + '</label><select data-thu-zone><option value="day"' + (e.zone === "day" ? " selected" : "") + ">" +
      esc(t.zone_day) + '</option><option value="vien"' + (e.zone === "vien" ? " selected" : "") + ">" + esc(t.zone_vien) + "</option></select></div>" +
      '<div class="row"><label>' + esc(t.effect) + "</label><select data-thu-effect>" + effectOptions(L, e.zone, e.effect, t, lg, false) + "</select></div>" +
      htmlParams(e.def, e.params, "data-thu-param", lg) +
      '<div class="row"><label>' + esc(t.thu_secs) + "</label>" + slider("data-thu-secs", e.secs, 1, 30, 1, false) +
      '<span class="val">' + esc(e.secs) + "</span></div>" +
      '<div class="row"><button class="sec" data-thu-run>' + esc(t.thu_run) + '</button><button class="sec" data-thu-stop>' + esc(t.thu_stop) + "</button></div>" +
      "</details></section>";
  }

  function htmlZone(f, zone, L, t, lg) {
    var z = f[zone], eff = z.effect === "tat" ? null : findEffect(L, zone, z.effect);
    var base = 'data-fn="' + esc(f.key) + '" data-zone="' + zone + '"';
    return '<div class="zone" data-zone-block="' + zone + '"><div class="zname">' + esc(zone === "day" ? t.zone_day : t.zone_vien) + "</div>" +
      '<div class="row"><label>' + esc(t.effect) + "</label><select " + base + " data-fn-effect>" + effectOptions(L, zone, z.effect, t, lg, true) + "</select></div>" +
      htmlParams(eff, z.params, base + " data-fn-param", lg) + "</div>";
  }

  function htmlFunction(f, L, t, lg) {
    var key = esc(f.key);
    return '<section class="fn' + (f.active ? " active" : "") + '" data-fn-block="' + key + '">' +
      '<details class="grp"><summary><b>' + esc(t.fn[f.key] || f.key) + "</b>" + (f.active ? ' <span class="tag">' + esc(t.active) + "</span>" : "") + "</summary>" +
      '<div class="row"><label>' + esc(t.enabled) + '</label><input type="checkbox" data-fn="' + key + '" data-field="enabled"' + (f.enabled ? " checked" : "") + "></div>" +
      htmlZone(f, "day", L, t, lg) + htmlZone(f, "vien", L, t, lg) +
      (f.isDefault ? '<div class="note">' + esc(t.proposal) + "</div>" : "") + "</details></section>";
  }

  function htmlLight(m, t, lg, ui) {
    var L = m.light, h = '<div data-panel="light">', s = L.sink;
    var via = s.path === "server" ? t.adb_server : (s.path === "direct" ? t.adb_direct : t.adb_idle);
    h += '<div class="sink ' + (s.ready ? "ok" : "warn") + '" data-sink>' +
      esc(s.state === "CHO_PHIA_LOA" ? t.sink_pending : (s.ready ? t.sink_ready : t.sink_err)) + " — " + esc(t.adb_lbl) + ": " + esc(via) +
      (s.error ? " — " + esc(t.sink_err) + ": " + esc(s.error) : "") + "</div>";
    h += htmlThu(L, ui, t, lg);
    h += '<div class="gtitle"><b>' + esc(t.fn_title) + "</b></div>";
    L.functions.forEach(function (f) { h += htmlFunction(f, L, t, lg); });
    // Đèn CHÍNH (RGB): mode 0–16 của firmware (cổng 8080, dịch vụ set_main_light). Mode 1 = cầu vồng đã test.
    var CHE_DO_CHINH = [[0, "Mặc định"], [1, "Cầu vồng (xoay vòng)"], [3, "Đơn sắc"], [2, "Mode 2"], [4, "Mode 4"], [5, "Mode 5"],
      [6, "Mode 6"], [8, "Mode 8"], [9, "Mode 9"], [10, "Mode 10"], [11, "Mode 11"], [12, "Mode 12"], [13, "Mode 13"],
      [14, "Mode 14"], [15, "Mode 15"], [16, "Mode 16"]];
    h += '<section data-main><details class="grp"><summary><b>Đèn RGB chính (firmware)</b></summary>' +
      '<div class="row"><label>Chế độ</label><select data-main-field="che_do">' +
      CHE_DO_CHINH.map(function (c) { return '<option value="' + c[0] + '">' + esc(c[1]) + "</option>"; }).join("") +
      "</select></div>" +
      '<div class="row"><label>Bật</label><input type="checkbox" data-main-field="bat"></div>' +
      '<div class="row"><label>Độ sáng</label>' + slider('data-main-field="sang"', 100, 1, 200, 1, false) +
      '<span class="val">100</span></div>' +
      '<div class="row"><label>Tốc độ (firmware)</label>' + slider('data-main-field="toc_do"', 50, 1, 100, 1, false) +
      '<span class="val">50</span></div>' +
      '<div class="note">Đèn RGB chính theo mode của firmware (lệnh qua cổng 8080): chỉ mode 1 là cầu vồng đã kiểm; các mode khác chưa đặt tên, xem trên loa.</div></details></section>';
    var mu = L.firmware;
    h += '<div class="note" data-fw>' + esc(t.fw) + ": " + esc(t.fw_on) + "=" +
      esc(mu.on === null ? t.unknown : (mu.on ? t.on : t.off)) + ", " + esc(t.fw_luma) + "=" +
      esc(mu.luma === null ? t.unknown : mu.luma) + ", " + esc(t.fw_chroma) + "=" + esc(mu.chroma === null ? t.unknown : mu.chroma) + "</div>";
    return h + "</div>";
  }

  function htmlConn(m, t) {
    var C = m.conn;
    var hp = function (h, p) { return (h || p) ? esc((h || "—") + ":" + (p === null ? "—" : p)) : esc(t.empty); };
    return '<div data-panel="conn">' +
      '<div class="row"><span>' + esc(t.host) + "</span><b>" + v(C.host, t) + "</b></div>" +
      '<div class="row"><span>' + esc(t.port) + "</span><b>" + v(C.port, t) + "</b></div>" +
      '<div class="row"><span>' + esc(t.ha_url) + "</span><b>" + v(C.haUrl, t) + "</b></div>" +
      '<div class="row"><span>' + esc(t.apk) + '</span><b data-apk-state>' + esc(C.apk ? t.apk_on : t.apk_off) + "</b></div>" +
      '<div class="row"><span>' + esc(t.listen) + "</span><b>" + v(C.listenPort, t) + "</b></div>" +
      '<div class="note">' + esc(t.key_auto) + "</div>" +
      (C.admin && C.listenKeySet ? '<button class="sec" data-apk-show>' + esc(C.lenh ? t.apk_hide : t.apk_show) + "</button>" +
        (C.lenh ? '<pre class="lenh" data-apk-cmd>' + esc(C.lenh) + '</pre><div class="note">' + esc(t.apk_note) + "</div>" : "") +
        (C.lenhLoi ? '<div class="warn small">' + esc(t.apk_err + ": " + C.lenhLoi) + "</div>" : "") : "") +
      '<div class="note">' + esc(t.conn_note) + '</div><button class="sec" data-goto>' + esc(t.goto) + "</button></div>";
  }

  /* ── Nhóm «Phát & khởi động lại» (NV302): mỗi dòng là MỘT thực thể chuẩn; thẻ chỉ gọi dịch vụ chuẩn của thực thể đó. ── */
  function fmtAt(iso, lg) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toLocaleString(lg === "vi" ? "vi-VN" : "en-GB", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
  }
  function swRow(label, x, attr, note) {
    return '<div class="row"><label>' + esc(label) + '</label><input type="checkbox" ' + attr + '="' + esc(x.entity || "") + '"' +
      (x.on ? " checked" : "") + (x.available ? "" : " disabled") + "></div>" + (note ? '<div class="note">' + esc(note) + "</div>" : "");
  }
  function htmlSys(m, t, lg) {
    var S = m.sys, P = S.play, R = S.restart, h = '<div data-panel="sys">';
    h += '<details class="grp" open data-sec="play"><summary><b>' + esc(t.play_title) + "</b></summary>";
    var opts = (P.path.options.length ? P.path.options : Object.keys(t.paths));
    h += '<div class="row"><label>' + esc(t.path) + '</label><select data-sys-sel="' + esc(P.path.entity || "") + '"' + (P.path.available ? "" : " disabled") + ">" +
      opts.map(function (o) { return '<option value="' + esc(o) + '"' + (P.path.value === o ? " selected" : "") + ">" + esc(t.paths[o] || o) + "</option>"; }).join("") +
      '</select></div><div class="note">' + esc(t.path_note) + "</div>";
    h += '<div class="row"><label>' + esc(t.port) + '</label><input type="number" data-sys-num="' + esc(P.port.entity || "") + '" min="1" max="65535" step="1" value="' +
      esc(P.port.value === null ? "" : P.port.value) + '"' + (P.port.available ? "" : " disabled") + '></div><div class="note">' + esc(t.port_note) + "</div>";
    h += swRow(t.parallel, P.parallel, "data-sys-sw", t.parallel_note);
    h += '<details class="grp adv2" data-sec="duck"><summary>' + esc(t.duck_title) + "</summary>" + swRow(t.duck, P.duck, "data-sys-sw", t.duck_note) +
      '<div class="row"><label>' + esc(t.duck_nac) + "</label>" +
      slider('data-sys-nac="' + esc(P.duckNac.entity || "") + '"', P.duckNac.value, 1, 14, 1, !P.duckNac.available) +
      '<span class="val">' + esc(P.duckNac.value === null ? "—" : P.duckNac.value) + "</span></div></details></details>";
    var D = S.dsp;
    h += '<details class="grp" data-sec="dsp"><summary><b>' + esc(t.dsp_title) + "</b></summary>";
    h += '<div class="row"><label>' + esc(t.engine) + '</label><select data-sys-sel="' + esc(D.engine.entity || "") + '"' + (D.engine.available ? "" : " disabled") + ">" +
      (D.engine.options.length ? D.engine.options : Object.keys(t.engines)).map(function (o) {
        return '<option value="' + esc(o) + '"' + (D.engine.value === o ? " selected" : "") + ">" + esc(t.engines[o] || o) + "</option>"; }).join("") +
      '</select></div><div class="note">' + esc(t.engine_note) + "</div>";
    h += swRow(t.noise_on, D.noise, "data-sys-sw", "") + swRow(t.aec_on, D.aec, "data-sys-sw", t.aec_note);
    h += '<div class="row"><label>' + esc(t.media_vol) + "</label>" +
      slider('data-sys-num="' + esc(D.media.entity || "") + '"', D.media.value, 0, 100, 5, !D.media.available) +
      '<span class="val">' + esc(D.media.value === null ? "—" : D.media.value + " %") + '</span></div><div class="note">' + esc(t.media_note) + "</div></details>";
    h += '<details class="grp" data-sec="phim"><summary><b>' + esc(t.phim_title) + '</b></summary><div class="note">' + esc(t.phim_note) + "</div>";
    S.phim.forEach(function (p) {
      h += '<div class="row"><label>' + esc(t.phim_cc[p.code] || p.code) + '</label><select data-sys-sel="' + esc(p.entity || "") + '"' + (p.available ? "" : " disabled") + ">" +
        (p.value && p.options.indexOf(p.value) < 0 ? '<option value="' + esc(p.value) + '" selected>' + esc(p.value) + "</option>" : "") +
        p.options.map(function (o, i) { return '<option value="' + esc(o) + '"' + (p.value === o ? " selected" : "") + ">" + esc(p.labels[i]) + "</option>"; }).join("") +
        "</select></div>";
    });
    h += "</details>";
    h += '<details class="grp" open data-sec="restart"><summary><b>' + esc(t.rs_title) + "</b></summary>";
    if (R.resp.present) h += '<div class="status ' + (R.resp.reason === "phan_hoi" ? "ok" : (R.resp.reason === "treo" || R.resp.reason === "mat_mang" ? "warn" : "")) +
      '" data-resp="' + esc(R.resp.reason || "") + '">' + esc(t.resp + ": " + (t.resp_state[R.resp.reason] || "—")) + "</div>";
    h += swRow(t.rs_sched, R.enabled, "data-sys-sw", t.rs_sched_note);
    h += '<div class="row"><label>' + esc(t.rs_time) + '</label><input type="time" data-sys-time="' + esc(R.time.entity || "") + '" value="' + esc(R.time.value || "") + '"' +
      (R.time.available ? "" : " disabled") + "></div>";
    h += '<div class="lbl">' + esc(t.rs_days) + '</div><div class="days" role="group" aria-label="' + esc(t.rs_days) + '">';
    R.days.forEach(function (d) {
      h += '<button class="chip' + (d.on ? " sel" : "") + '" data-day="' + esc(d.entity || "") + '" aria-pressed="' + (d.on ? "true" : "false") +
        '" aria-label="' + esc(t.day_full[d.code]) + '"' + (d.available ? "" : " disabled") + ">" + esc(t.day[d.code]) + "</button>";
    });
    h += "</div>";
    h += swRow(t.rs_hang, R.onHang, "data-sys-sw", t.rs_hang_note);
    h += '<button class="sec" data-reboot="' + esc(R.button.entity || "") + '"' + (R.button.present ? "" : " disabled") + ">" + esc(t.rs_now) + "</button>";
    if (R.last.present) {
      var l = R.last, rs = l.reason ? (t.rs_reasons[l.reason] || l.reason) : null;
      h += '<div class="status" data-last>' + esc(t.rs_last + ": " + (l.at ? fmtAt(l.at, lg) : t.rs_never) +
        (rs ? " (" + t.rs_reason + ": " + rs + (l.result && l.result !== "ok" ? ", " + t.rs_failed : "") + ")" : "")) + "</div>";
      if (l.next) h += '<div class="note" data-next>' + esc(t.rs_next + ": " + fmtAt(l.next, lg)) + "</div>";
      if (l.deferring) h += '<div class="note" data-defer>' + esc(t.rs_defer + ": " + l.deferring) + "</div>";
    }
    return h + "</details></div>";
  }

  /* HTML thuần của thẻ. Đóng: chỉ tiêu đề + nút. Mở: ba tab + nhóm đang chọn. */
  function renderHtml(m, ui, t, lg) {
    lg = lg || "vi";
    if (!m.found) return '<ha-card><div class="warn">' + esc(t.none) + "</div></ha-card>";
    var h = m.gop ? "<ha-card>" : '<ha-card><div class="head"><h2>' + esc(t.title) + '</h2><button data-open aria-expanded="' +
      (ui.open ? "true" : "false") + '">' + esc(ui.open ? t.close : t.open) + "</button></div>";
    if (!m.gop && !ui.open) return h + "</ha-card>";
    h += '<div class="tabs" role="tablist">';
    TABS.forEach(function (k) {
      h += '<button class="tab' + (ui.tab === k ? " sel" : "") + '" role="tab" data-tab="' + k +
        '" aria-selected="' + (ui.tab === k ? "true" : "false") + '">' + esc(t[k]) + "</button>";
    });
    h += "</div>";
    h += ui.tab === "light" ? htmlLight(m, t, lg, ui) : (ui.tab === "conn" ? htmlConn(m, t) : (ui.tab === "sys" ? htmlSys(m, t, lg) : htmlAudio(m, t)));
    return h + "</ha-card>";
  }

  var CSS = [
    ":host{display:block}", "ha-card{padding:12px 16px;font-size:14px;box-sizing:border-box;max-width:100%;overflow-x:hidden}", "h2{margin:0;font-size:1.1em}",
    ".head{display:flex;align-items:center;justify-content:space-between;gap:8px}",
    ".row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:6px 0;min-height:44px;flex-wrap:wrap}",
    ".row label{flex:1 1 150px;min-width:0}", "input[type=checkbox]{width:28px;height:28px;flex:none}",
    "select,input[type=time],input[type=number]{font:inherit;min-height:44px;max-width:100%;box-sizing:border-box}", "input[type=range]{min-height:44px}",
    ".row input[type=range]{flex:1}", ".val{min-width:3em;text-align:right}",
    "section{margin-top:10px;border-top:1px solid var(--divider-color,#ddd);padding-top:6px}",
    "section.active{border-left:3px solid var(--primary-color,#03a9f4);padding-left:8px}",
    ".tabs{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}", ".tab.sel{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}",
    "button{font:inherit;min-height:44px;min-width:44px;padding:6px 14px;border-radius:8px;border:1px solid var(--divider-color,#bbb);",
    "background:transparent;color:inherit;cursor:pointer}", "button.sec{margin-top:4px}",
    ".warn{color:var(--error-color,#db4437)}", ".small{font-size:14px}", ".note{font-size:14px;opacity:.8}", ".grp{font-weight:600;margin-top:8px}", "input[type=number]{width:90px}", "pre.lenh{white-space:pre-wrap;word-break:break-all;font-size:.75em;user-select:all;margin:6px 0}",
    ".ok{color:var(--success-color,#43a047)}", ".sink{margin:8px 0;font-size:.9em}",
    ".zone{margin:6px 0 6px 6px;padding-left:8px;border-left:2px solid var(--divider-color,#ddd)}", ".zname{font-weight:600;font-size:.9em}", ".gtitle{margin-top:14px}",
    "details[data-sec]{font-weight:400}", "details[data-sec]>summary{font-weight:600}",
    ".days{display:flex;gap:4px;margin:4px 0 8px}", ".chip{flex:1 1 0;min-width:44px;padding:6px 0;text-align:center}",
    ".chip.sel{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}", ".lbl{margin-top:6px}",
    ".status{margin:8px 0}", "details.adv2{margin-top:8px}", "details.adv2>summary{min-height:44px;display:flex;align-items:center;cursor:pointer}",
    "summary{min-height:44px;display:flex;align-items:center;cursor:pointer}",
    ".tag{font-size:14px;padding:1px 6px;border-radius:8px;background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}",
  ].join("");

  class R1SettingsCard extends (typeof HTMLElement !== "undefined" ? HTMLElement : Object) {
    constructor() {
      super();
      this._config = {};
      this._ui = initialUi();
      this._html = null;
      this._deferred = false;
      if (this.attachShadow) {
        this.attachShadow({ mode: "open" });
        // MỘT lần (shadowRoot không đổi khi dựng lại innerHTML): rời ô nhập thì dựng bản bị hoãn.
        var self = this;
        this.shadowRoot.addEventListener("focusout", function () {
          if (self._deferred) setTimeout(function () { if (self._deferred) self._render(); }, 0);
        });
      }
    }

    static getStubConfig() { return {}; }
    setConfig(config) { this._config = config || {}; this._html = null; if (this._hass) this._render(); }
    getCardSize() { return this._ui.open ? 12 : 1; }
    set hass(hass) { this._hass = hass; this._render(); }

    _model() {
      var m = buildModel(this._hass, this._config);
      m.conn.lenh = this._lenh || null; m.conn.lenhLoi = this._lenhLoi || "";   // lệnh có khoá: chỉ giữ trong bộ nhớ thẻ
      return m;
    }

    _render(force) {
      if (!this._hass || !this.shadowRoot) return;
      // Đang kéo thanh / chọn mục: đừng dựng lại DOM dưới tay người dùng; dựng sau khi rời ô.
      var ae = this.shadowRoot.activeElement;
      if (!force && this._html !== null && ae && /^(INPUT|SELECT)$/.test(ae.tagName)) {
        this._deferred = true;
        return;
      }
      this._deferred = false;
      var lg = lang(this._hass);
      var html = "<style>" + CSS + "</style>" + renderHtml(this._model(), this._ui, TEXT[lg], lg);
      if (html === this._html) return;
      this._html = html;
      // Giữ nhóm đang mở qua lần dựng lại (HA cập nhật trạng thái liên tục, dựng lại làm nhóm tự đóng).
      var moNhom = Array.prototype.map.call(this.shadowRoot.querySelectorAll("details.grp"), function (d) { return d.open; });
      this.shadowRoot.innerHTML = html;
      Array.prototype.forEach.call(this.shadowRoot.querySelectorAll("details.grp"), function (d, i) {
        if (moNhom[i]) d.open = true;
      });
      this._bind();
    }

    _call(c) { if (c) this._hass.callService(c[0], c[1], c[2]); }

    _bind() {
      var root = this.shadowRoot, self = this;
      var dispatch = function (a) { self._call(makeCall(self._model(), a)); };
      var q = function (s) { return root.querySelector(s); };
      var all = function (s, fn) { Array.prototype.forEach.call(root.querySelectorAll(s), fn); };
      var open = q("[data-open]");
      if (open) open.addEventListener("click", function () {
        self._ui = reduceUi(self._ui, { type: "toggle" }); self._render(true);
      });
      all("[data-tab]", function (el) {
        el.addEventListener("click", function () {
          self._ui = reduceUi(self._ui, { type: "tab", tab: el.dataset.tab }); self._render(true);
        });
      });
      all("[data-apk-show]", function (el) {
        el.addEventListener("click", function () {
          if (self._lenh) { self._lenh = null; self._lenhLoi = ""; self._render(true); return; }
          var sid = self._model().settings.entity;
          self._hass.callWS({ type: "r1_speaker/apk_lenh", entity_id: sid })
            .then(function (r) { self._lenh = r && r.lenh ? r.lenh : null; self._lenhLoi = ""; self._render(true); })
            .catch(function (e) { self._lenh = null; self._lenhLoi = (e && e.message) || "?"; self._render(true); });
        });
      });
      all("[data-goto]", function (el) {
        el.addEventListener("click", function () {
          var path = self._model().conn.optionsPath;
          history.pushState(null, "", path);
          window.dispatchEvent(new Event("location-changed"));
        });
      });
      // Số hiển thị THỜI GIAN THỰC khi đang kéo (trước đây chỉ cập nhật sau khi thả tay nên thanh kéo trông «đơ»).
      all('input[type="range"]', function (el) {
        el.addEventListener("input", function () {
          var v = el.parentNode && el.parentNode.querySelector(".val");
          if (!v) return;
          var dv = el.hasAttribute("data-mic-gain") ? " dB" : (el.dataset.eq ? " mB" : (el.dataset.unit || ""));
          v.textContent = el.value + dv;
        });
      });
      var vol = q("[data-vol]");
      if (vol) vol.addEventListener("change", function () { dispatch({ type: "vol", value: vol.value }); });
      all("[data-eq]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "eq", entity: el.dataset.eq, value: el.value }); });
      });
      var mg = q("[data-mic-gain]");
      if (mg) mg.addEventListener("change", function () { dispatch({ type: "micgain", value: mg.value }); });
      var mu = q("[data-mute]");
      if (mu) mu.addEventListener("change", function () { dispatch({ type: "mute", on: mu.checked }); });
      all("[data-fn][data-field]", function (el) {                      // chỉ ô «Bật» của chức năng
        el.addEventListener("change", function () {
          dispatch({ type: "fn", key: el.dataset.fn, field: el.dataset.field, value: el.checked });
        });
      });
      all("[data-fn-effect]", function (el) {
        el.addEventListener("change", function () {
          dispatch({ type: "fn_effect", key: el.dataset.fn, zone: el.dataset.zone, effect: el.value });
        });
      });
      all("[data-fn-param]", function (el) {
        el.addEventListener("change", function () {
          dispatch({ type: "fn_param", key: el.dataset.fn, zone: el.dataset.zone, param: el.dataset.param, kind: el.dataset.kind, value: el.value });
        });
      });
      // Mục Thử: trạng thái chỉ nằm trong thẻ; chỉ nút «Thử» mới gọi dịch vụ.
      var ui = function (a) { self._ui = reduceUi(self._ui, a); self._render(true); };
      var tz = q("[data-thu-zone]");
      if (tz) tz.addEventListener("change", function () { ui({ type: "thu_zone", zone: tz.value }); });
      var te = q("[data-thu-effect]");
      if (te) te.addEventListener("change", function () { ui({ type: "thu_effect", effect: te.value }); });
      all("[data-thu-param]", function (el) {
        el.addEventListener("change", function () { ui({ type: "thu_param", key: el.dataset.param, value: el.dataset.kind === "range" ? Number(el.value) : el.value }); });
      });
      var ts = q("[data-thu-secs]");
      if (ts) ts.addEventListener("change", function () { ui({ type: "thu_secs", secs: Number(ts.value) }); });
      var tr = q("[data-thu-run]");
      if (tr) tr.addEventListener("click", function () {
        var e = thuEffective(self._model().light, self._ui);
        dispatch({ type: "thu_run", zone: e.zone, effect: e.effect, params: e.params, secs: e.secs });
      });
      var tstop = q("[data-thu-stop]");
      if (tstop) tstop.addEventListener("click", function () { dispatch({ type: "thu_stop" }); });
      all("[data-main-field]", function (el) {
        el.addEventListener("change", function () {
          dispatch({ type: "main", field: el.dataset.mainField, value: el.type === "checkbox" ? el.checked : el.value });
        });
      });
      all("[data-sys-sw]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "sw", entity: el.dataset.sysSw, on: el.checked }); });
      });
      all("[data-sys-sel]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "sel", entity: el.dataset.sysSel, value: el.value }); });
      });
      all("[data-sys-nac]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "sysnum", entity: el.dataset.sysNac, value: el.value }); });
      });
      all("[data-sys-num]", function (el) {
        el.addEventListener("change", function () { if (el.value !== "") dispatch({ type: "sysnum", entity: el.dataset.sysNum, value: el.value }); });
      });
      all("[data-sys-time]", function (el) {
        el.addEventListener("change", function () { if (el.value) dispatch({ type: "time", entity: el.dataset.sysTime, value: el.value }); });
      });
      all("[data-day]", function (el) {
        el.addEventListener("click", function () { dispatch({ type: "sw", entity: el.dataset.day, on: el.getAttribute("aria-pressed") !== "true" }); });
      });
      all("[data-reboot]", function (el) {
        el.addEventListener("click", function () {
          var t = TEXT[lang(self._hass)];
          if (typeof window.confirm !== "function" || window.confirm(t.rs_now_confirm)) dispatch({ type: "reboot", entity: el.dataset.reboot });
        });
      });
      all("[data-opt]", function (el) {
        el.addEventListener("change", function () {
          var bat = el.dataset.bool === "1";
          dispatch({ type: "opt", key: el.dataset.opt, bool: bat, value: bat ? el.checked : el.value });
        });
      });
    }
  }

  // r1-card dựng thẻ từ lớp này (nạp bằng URL mới mỗi lần mở trang), không phụ thuộc bản cũ còn
  // trong bộ nhớ đệm của trình duyệt dưới URL cố định.
  if (typeof window !== "undefined") {
    window.R1_THE = window.R1_THE || {};
    window.R1_THE.settings = { lop: R1SettingsCard, build: BUILD };
  }

  if (typeof customElements !== "undefined" && !customElements.get("r1-settings-card")) {
    customElements.define("r1-settings-card", R1SettingsCard);
    // (Không khai báo vào bộ chọn thẻ: thẻ gộp r1-card là thẻ duy nhất; thẻ này chỉ được r1-card nạp.)
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildModel: buildModel, renderHtml: renderHtml, initialUi: initialUi, reduceUi: reduceUi,
                       makeCall: makeCall, thuEffective: thuEffective, TEXT: TEXT, FUNCTIONS: FUNCTIONS, TABS: TABS, DAYS: DAYS };
  }
})();
