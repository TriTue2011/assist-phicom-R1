/* r1-settings-card — thẻ Lovelace CÀI ĐẶT cho loa Phicomm R1 (tích hợp r1_speaker).
 *
 * Mặc định chỉ hiện tiêu đề + nút «Cài đặt»; bấm nút mới mở bảng cài đặt, chia ba nhóm:
 *   Âm thanh  — âm lượng, EQ 5 dải, tăng mic, tắt mic; khử tạp / AGC / bộ hạn đỉnh (CHỈ ĐỌC: là
 *               tuỳ chọn của mục cài đặt, không phải thực thể; sửa ở trang Tuỳ chọn của tích hợp);
 *   Ánh sáng  — đèn theo chức năng (bật/tắt, đèn viền trắng, màu đèn đáy, hiệu ứng, độ sáng),
 *               hiệu ứng khi phát nhạc, danh mục hiệu ứng;
 *   Kết nối   — host, cổng, ha_url, khoá bộ đàm (chỉ «đã có / chưa có», KHÔNG hiện giá trị khoá).
 *
 * Thẻ KHÔNG gọi loa: chỉ đọc thực thể HA (sensor.r1_cai_dat và các thực thể EQ / âm lượng / mic) và
 * gọi dịch vụ HA (number.set_value, switch.turn_on/off, r1_speaker.set_light_function,
 * r1_speaker.set_music_light, r1_speaker.preview_light). Đèn chỉ sáng khi có dịch vụ đèn trên loa
 * (CHƯA có); thẻ nói rõ điều đó thay vì giả vờ.
 *
 * Cấu hình tối thiểu:   type: custom:r1-settings-card
 * Nhiều loa:            device_id: <mã thiết bị>
 * Chỉ định tay:         entities: { settings: sensor.x, volume: number.y, mic_gain: number.z,
 *                         mute: switch.u }
 */
(function () {
  "use strict";
  var BUILD = "2026-10-22.20";

  var PLATFORM = "r1_speaker";
  var FUNCTIONS = ["cho", "nghe", "nghi", "phan_hoi", "dam_thoai", "phat_nhac", "loi", "tat_mic"];
  var TABS = ["audio", "light", "conn"];
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
        duplex_vad_threshold: "Ngưỡng tiếng người VAD (xác suất 0–1)", duplex_preroll_s: "Giữ tiếng trước câu nói (giây)",
        duplex_hangover_s: "Giữ tiếng sau câu nói (giây)", duplex_max_s: "Thời gian tối đa của phiên (giây)",
        duplex_duck: "Cắt vọng: bỏ tiếng mic nhỏ khi HA đang phát", duplex_duck_db: "Ngưỡng mức tiếng cắt vọng (dBFS)" },
      read_only: "Chỉ đọc — sửa ở trang Tuỳ chọn của tích hợp", noise: "Khử tạp âm",
      agc: "Tự chỉnh mức (AGC)", limiter: "Bộ hạn đỉnh", on: "Bật", off: "Tắt", goto: "Mở tuỳ chọn",
      sink_pending: "Chưa có dịch vụ đèn trên loa: cài đặt được lưu nhưng đèn CHƯA sáng.",
      sink_svc: "Loa chưa sẵn sàng điều khiển đèn bằng hiệu ứng firmware: hãy cài APK mới nhất lên loa.",
      fw_sang: "Đèn firmware không chỉnh độ sáng từng chức năng: 0 = tắt, lớn hơn 0 = bật. Màu làm tròn về bảng màu của firmware; thở và nháy chạy gốc, các hiệu ứng còn lại chạy bằng cách đổi liên tục màu.",
      sink_lost: "Dịch vụ đèn trên loa không trả lời.", sink_ready: "Dịch vụ đèn: sẵn sàng",
      sink_err: "Lỗi gần nhất",
      fn: { cho: "Chờ / từ đánh thức", nghe: "Đang nghe", nghi: "Đang nghĩ", phan_hoi: "Đang trả lời",
            dam_thoai: "Đàm thoại", phat_nhac: "Phát nhạc (hiệu ứng của HA)", loi: "Lỗi", tat_mic: "Tắt mic" },
      enabled: "Bật", rim: "Đèn viền (chỉ trắng)", color: "Màu đèn đáy", effect: "Hiệu ứng",
      brightness: "Độ sáng", speed: "Tốc độ hiệu ứng", preview: "Thử", active: "đang áp dụng", proposal: "mặc định đề xuất, chưa đo",
      no_effect: "Không (sáng cố định)", red_warn: "Đỏ chưa xác nhận trên đèn đáy",
      music: "Hiệu ứng khi phát nhạc",
      fw: "Đèn theo nhạc của firmware (chỉnh ở các thực thể «Đèn theo nhạc», «Độ sáng/Sắc độ đèn nhạc»)",
      fw_on: "bật", fw_luma: "luma", fw_chroma: "chroma", unknown: "không rõ",
      catalog: "Danh mục hiệu ứng", source: "nguồn",
      host: "Địa chỉ loa", port: "Cổng điều khiển / EQ", mic: "Mic (host:cổng)",
      play: "Phát về loa (host:cổng)", wake: "Từ đánh thức chạy ở", ha_url: "Địa chỉ HA loa gọi tới",
      key: "Khoá bộ đàm", key_set: "Đã có (không hiện giá trị)", key_unset: "Chưa có", empty: "(trống)",
      conn_note: "Sửa địa chỉ loa và địa chỉ HA ở trang Tuỳ chọn: ở đó có kiểm kết nối trước khi lưu.",
      apk: "APK trên loa", apk_on: "Đang nối vào HA", apk_off: "Chưa nối — cài APK xong phải chạy lệnh cấu hình MỘT lần (bấm «Hiện lệnh cài APK» bên dưới); sau đó APK tự chạy mỗi khi loa khởi động",
      listen: "Cổng nghe mic (HA tự cấp)", key_auto: "Khoá nghe mic: HA tự sinh, không cần nhập",
      apk_note: "Chạy lệnh trên một máy có adb. Loa đã cấu hình rồi thì lệnh đổi cấu hình bị BỎ QUA: chạy trước adb shell /system/bin/pm clear vn.r1.bodam (xoá cấu hình cũ).",
      apk_show: "Hiện lệnh cài APK (quản trị viên)", apk_hide: "Ẩn lệnh", apk_err: "Không lấy được lệnh",
      unconfirmed: "chưa xác nhận",
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
        duplex_vad_threshold: "VAD voice threshold (probability 0–1)", duplex_preroll_s: "Audio kept before speech (s)",
        duplex_hangover_s: "Audio kept after speech (s)", duplex_max_s: "Max session length (s)",
        duplex_duck: "Echo cut: drop quiet mic audio while HA is playing", duplex_duck_db: "Echo-cut level threshold (dBFS)" },
      read_only: "Read-only — change it on the integration's Options page",
      noise: "Noise suppression", agc: "Auto gain (AGC)", limiter: "Peak limiter", on: "On", off: "Off",
      goto: "Open options",
      sink_pending: "No light service on the speaker yet: settings are saved but the light does NOT shine.",
      sink_svc: "The speaker is not ready for firmware light effects: install the latest APK on the speaker.",
      fw_sang: "Firmware lights have no per-function brightness: 0 = off, above 0 = on. Colours snap to the firmware palette; breathe and blink run natively, other effects run by cycling colours.",
      sink_lost: "The light service on the speaker is not answering.", sink_ready: "Light service: ready",
      sink_err: "Last error",
      fn: { cho: "Idle / wake word", nghe: "Listening", nghi: "Thinking", phan_hoi: "Responding",
            dam_thoai: "Conversation", phat_nhac: "Music playing (HA effect)", loi: "Error", tat_mic: "Mic muted" },
      enabled: "On", rim: "Rim light (white only)", color: "Base colour", effect: "Effect",
      brightness: "Brightness", speed: "Effect speed", preview: "Try", active: "in effect", proposal: "suggested default, not measured",
      no_effect: "None (steady)", red_warn: "Red is unconfirmed on the base light",
      music: "Light effect while music plays",
      fw: "Speaker firmware's own music light (set with the «Music light» entities)",
      fw_on: "on", fw_luma: "luma", fw_chroma: "chroma", unknown: "unknown",
      catalog: "Effect catalogue", source: "source",
      host: "Speaker address", port: "Control / EQ port", mic: "Mic (host:port)",
      play: "Playback to speaker (host:port)", wake: "Wake word runs on", ha_url: "HA address the speaker calls",
      key: "Intercom key", key_set: "Set (value is never shown)", key_unset: "Not set", empty: "(empty)",
      conn_note: "Change the speaker and HA addresses on the Options page, which checks the connection before saving.",
      apk: "APK on the speaker", apk_on: "Connected to HA", apk_off: "Not connected — after installing the APK you must run the setup command ONCE (press «Show APK setup command» below); after that the APK starts by itself whenever the speaker boots",
      listen: "Mic listen port (issued by HA)", key_auto: "Mic listen key: generated by HA, nothing to type",
      apk_note: "Run it from a machine with adb. A speaker that is already configured IGNORES the command: first run adb shell /system/bin/pm clear vn.r1.bodam (clears the old configuration).",
      apk_show: "Show APK setup command (administrators)", apk_hide: "Hide command", apk_err: "Could not get the command",
      unconfirmed: "unconfirmed",
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
    var fns = FUNCTIONS.filter(function (k) { return chuc[k]; }).map(function (k) {
      var p = chuc[k];
      return { key: k, enabled: p.enabled === true, rim: p.rim === true, color: String(p.color || "#000000"),
               effect: p.effect || "none", brightness: num(p.brightness, 0), tocDo: num(p.toc_do, 100), rimKieu: num(p.rim_kieu, 0), isDefault: p.mac_dinh === true,
               active: al.dang_ap_dung === k };
    });
    var fw = al.den_nhac_firmware || {};
    var music = fns.filter(function (f) { return f.key === "phat_nhac"; })[0] || null;
    return {
      found: !!(ent.settings || ent.volume || bands.length),
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
        sink: { state: al.dich_vu_den || null, ready: al.dich_vu_den === "san_sang",
                lost: al.dich_vu_den === "mat_ket_noi", svc: al.dich_vu_den === "CHO_DICH_VU_DEN", error: al.loi_dich_vu || null },
        functions: fns, music: music, current: al.dang_ap_dung || null,
        tocDoHoTro: Array.isArray(al.hieu_ung_co_toc_do) ? al.hieu_ung_co_toc_do : null,
        tocDo: { min: num((al.toc_do || {}).min, 25), max: num((al.toc_do || {}).max, 400) },
        fw: al.den_firmware === true, hoTro: Array.isArray(al.hieu_ung_ho_tro) ? al.hieu_ung_ho_tro : null,
        bangMau: Array.isArray(al.bang_mau_firmware) ? al.bang_mau_firmware : [],
        effects: (al.hieu_ung || []).map(function (h) {
          return { id: h.id, name: h.ten, nameEn: h.ten_en, source: h.nguon, rimNote: h.vien };
        }),
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

  /* Trạng thái giao diện: ĐÓNG mặc định. */
  function initialUi() { return { open: false, tab: "audio" }; }
  function reduceUi(ui, action) {
    if (action.type === "toggle") return { open: !ui.open, tab: ui.tab };
    if (action.type === "tab" && TABS.indexOf(action.tab) >= 0) return { open: ui.open, tab: action.tab };
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
    if (!sid) return null;
    var coerce = function (field, v) {
      if (field === "enabled" || field === "rim" || field === "bat") return v === true || v === "true" || v === "on";
      if (field === "brightness" || field === "toc_do" || field === "sang" || field === "che_do" || field === "rim_kieu") return Math.round(Number(v));
      return String(v);
    };
    if (a.type === "fn" && FUNCTIONS.indexOf(a.key) >= 0) {
      var d = { entity_id: sid, function: a.key };
      d[a.field] = coerce(a.field, a.value);
      return ["r1_speaker", "set_light_function", d];
    }
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
    if (a.type === "music") {
      var m = { entity_id: sid };
      m[a.field] = coerce(a.field, a.value);
      return ["r1_speaker", "set_music_light", m];
    }
    if (a.type === "preview" && FUNCTIONS.indexOf(a.key) >= 0) {
      return ["r1_speaker", "preview_light", { entity_id: sid, function: a.key }];
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

  function effectSelect(attrs, selected, effects, t, lg) {
    var h = "<select " + attrs + '><option value="none"' + (selected === "none" ? " selected" : "") + ">" +
      esc(t.no_effect) + "</option>";
    effects.forEach(function (e) {
      h += '<option value="' + esc(e.id) + '"' + (selected === e.id ? " selected" : "") + ">" +
        esc(lg === "vi" ? e.name : e.nameEn) + "</option>";
    });
    return h + "</select>";
  }

  /* Đèn firmware: chỉ các hiệu ứng làm được; màu chọn trong bảng của firmware (màu gần nhất với màu đang lưu). */
  function hieuUngDung(L) {
    if (!L.hoTro) return L.effects;
    return L.effects.filter(function (e) { return L.hoTro.indexOf(e.id) >= 0; });
  }
  function rgbOf(hex) { return [1, 3, 5].map(function (i) { return parseInt(String(hex).substr(i, 2), 16) || 0; }); }
  function mauGan(hex, bang) {
    var c = rgbOf(hex), best = null, bd = 1e12;
    bang.forEach(function (b) {
      var r = rgbOf(b.rgb), d = 0;
      for (var i = 0; i < 3; i++) d += (c[i] - r[i]) * (c[i] - r[i]);
      if (d < bd) { bd = d; best = b; }
    });
    return best;
  }
  function mauSelect(attrs, hex, L, lg) {
    var gan = mauGan(hexOk(hex), L.bangMau), o = "";
    L.bangMau.forEach(function (b) {
      o += '<option value="' + esc(b.rgb) + '"' + (gan && gan.rgb === b.rgb ? " selected" : "") + ">" +
        esc(lg === "vi" ? b.ten : b.ten_en) + (b.tho ? "" : "") + "</option>";
    });
    return "<select " + attrs + ">" + o + "</select>";
  }

  function htmlLight(m, t, lg) {
    var L = m.light, h = '<div data-panel="light">';
    var s = L.sink;
    h += '<div class="sink ' + (s.ready ? "ok" : "warn") + '" data-sink>' +
      esc(s.ready ? t.sink_ready : (s.lost ? t.sink_lost : (s.svc ? t.sink_svc : t.sink_pending))) +
      (s.error ? " — " + esc(t.sink_err) + ": " + esc(s.error) : "") + "</div>";
    L.functions.forEach(function (f) {
      if (f.key === "phat_nhac") return;      // hiện riêng ở mục «hiệu ứng khi phát nhạc»
      h += htmlFunction(f, L, t, lg);
    });
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
    var mu = L.music;
    if (mu) {
      h += '<section data-music><details class="grp"><summary><b>' + esc(t.music) + "</b></summary>" +
        '<div class="row"><label>' + esc(t.enabled) + '</label><input type="checkbox" data-music-field="enabled"' +
        (mu.enabled ? " checked" : "") + "></div>" +
        '<div class="row"><label>' + esc(t.effect) + "</label>" +
        effectSelect('data-music-field="effect"', mu.effect, hieuUngDung(L), t, lg) + "</div>" +
        '<div class="row"><label>' + esc(t.brightness) + "</label>" +
        slider('data-music-field="brightness"', mu.brightness, 0, 100, 5, false) +
        '<span class="val">' + esc(mu.brightness) + "</span></div>" +
        (mu.isDefault ? '<div class="note">' + esc(t.proposal) + "</div>" : "") +
        '<div class="note" data-fw>' + esc(t.fw) + ": " + esc(t.fw_on) + "=" +
        esc(L.firmware.on === null ? t.unknown : (L.firmware.on ? t.on : t.off)) + ", " + esc(t.fw_luma) + "=" +
        esc(L.firmware.luma === null ? t.unknown : L.firmware.luma) + ", " + esc(t.fw_chroma) + "=" +
        esc(L.firmware.chroma === null ? t.unknown : L.firmware.chroma) + "</div></details></section>";
    }
    return h + "</div>";                     // danh mục hiệu ứng + nguồn đã bỏ khỏi thẻ (theo yêu cầu)
  }

  function htmlFunction(f, L, t, lg) {
    var key = esc(f.key), d = 'data-fn="' + key + '" data-field=';
    return '<section class="fn' + (f.active ? " active" : "") + '" data-fn-block="' + key + '">' +
      '<details class="grp"><summary><b>' + esc(t.fn[f.key] || f.key) + "</b>" + (f.active ? ' <span class="tag">' + esc(t.active) + "</span>" : "") + "</summary>" +
      '<div class="row"><label>' + esc(t.enabled) + "</label><input type=\"checkbox\" " + d + '"enabled"' +
      (f.enabled ? " checked" : "") + "></div>" +
      '<div class="row"><label>' + esc(t.rim) + "</label><input type=\"checkbox\" " + d + '"rim"' +
      (f.rim ? " checked" : "") + "></div>" +
      '<div class="row"><label>Hiệu ứng viền</label><select ' + d + '"rim_kieu">' +
      ['<option value="0"' + (f.rimKieu === 0 ? " selected" : "") + ">Không</option>"].concat(
        Array.from({ length: 24 }, function (_, i) {
          return '<option value="' + (i + 1) + '"' + (f.rimKieu === i + 1 ? " selected" : "") + ">Chạy đuổi " + (i + 1) + "</option>";
        })).join("") + "</select></div>" +
      '<div class="row"><label>' + esc(t.color) + "</label>" + (L.fw && L.bangMau.length
        ? mauSelect(d + '"color"', f.color, L, lg)
        : '<input type="color" ' + d + '"color" value="' + esc(hexOk(f.color)) + '">') + "</div>" +
      (!L.fw && isRed(f.color) ? '<div class="warn small">' + esc(t.red_warn) + "</div>" : "") +
      '<div class="row"><label>' + esc(t.effect) + "</label>" + effectSelect(d + '"effect"', f.effect, hieuUngDung(L), t, lg) +
      "</div>" +
      (L.fw ? '<div class="note">' + esc(t.fw_sang) + "</div>" : "") +
      '<div class="row"><label>' + esc(t.brightness) + "</label>" + slider(d + '"brightness"', f.brightness, 0, 100, 5, false) +
      '<span class="val">' + esc(f.brightness) + "</span></div>" +
      // Tốc độ: chỉ hiện khi hiệu ứng đang chọn do HA tự đổi màu theo nhịp (thở/nháy gốc của firmware có chu kỳ cố định).
      (f.effect !== "none" && (!L.tocDoHoTro || L.tocDoHoTro.indexOf(f.effect) >= 0)
        ? '<div class="row"><label>' + esc(t.speed) + "</label>" + slider(d + '"toc_do"', f.tocDo, L.tocDo.min, L.tocDo.max, 5, false) +
          '<span class="val">' + esc(f.tocDo) + "%</span></div>"
        : "") +
      (f.isDefault ? '<div class="note">' + esc(t.proposal) + "</div>" : "") +
      '<button class="sec" data-preview="' + key + '">' + esc(t.preview) + "</button></details></section>";
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
    h += ui.tab === "light" ? htmlLight(m, t, lg) : (ui.tab === "conn" ? htmlConn(m, t) : htmlAudio(m, t));
    return h + "</ha-card>";
  }

  var CSS = [
    ":host{display:block}", "ha-card{padding:12px 16px}", "h2{margin:0;font-size:1.1em}",
    ".head{display:flex;align-items:center;justify-content:space-between;gap:8px}",
    ".row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:6px 0}",
    ".row input[type=range]{flex:1}", ".val{min-width:3em;text-align:right}",
    "section{margin-top:10px;border-top:1px solid var(--divider-color,#ddd);padding-top:6px}",
    "section.active{border-left:3px solid var(--primary-color,#03a9f4);padding-left:8px}",
    ".tabs{display:flex;gap:6px;margin:10px 0}", ".tab.sel{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}",
    "button{font:inherit;padding:6px 14px;border-radius:8px;border:1px solid var(--divider-color,#bbb);",
    "background:transparent;color:inherit;cursor:pointer}", "button.sec{margin-top:4px}",
    ".warn{color:var(--error-color,#db4437)}", ".small{font-size:.8em}", ".note{font-size:.8em;opacity:.75}", ".grp{font-weight:600;margin-top:8px}", "input[type=number]{width:90px}", "pre.lenh{white-space:pre-wrap;word-break:break-all;font-size:.75em;user-select:all;margin:6px 0}",
    ".ok{color:var(--success-color,#43a047)}", ".sink{margin:8px 0;font-size:.9em}",
    ".tag{font-size:.75em;padding:1px 6px;border-radius:8px;background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}",
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
          var dv = el.hasAttribute("data-mic-gain") ? " dB" : (el.dataset.eq ? " mB" : "");
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
      all("[data-fn][data-field]", function (el) {
        el.addEventListener("change", function () {
          dispatch({ type: "fn", key: el.dataset.fn, field: el.dataset.field,
                     value: el.type === "checkbox" ? el.checked : el.value });
        });
      });
      all("[data-main-field]", function (el) {
        el.addEventListener("change", function () {
          dispatch({ type: "main", field: el.dataset.mainField, value: el.type === "checkbox" ? el.checked : el.value });
        });
      });
      all("[data-music-field]", function (el) {
        el.addEventListener("change", function () {
          dispatch({ type: "music", field: el.dataset.musicField, value: el.type === "checkbox" ? el.checked : el.value });
        });
      });
      all("[data-opt]", function (el) {
        el.addEventListener("change", function () {
          var bat = el.dataset.bool === "1";
          dispatch({ type: "opt", key: el.dataset.opt, bool: bat, value: bat ? el.checked : el.value });
        });
      });
      all("[data-preview]", function (el) {
        el.addEventListener("click", function () { dispatch({ type: "preview", key: el.dataset.preview }); });
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
                       makeCall: makeCall, TEXT: TEXT, FUNCTIONS: FUNCTIONS, TABS: TABS };
  }
})();
