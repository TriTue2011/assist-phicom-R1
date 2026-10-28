/* r1-talk-card — thẻ Lovelace ĐÀM THOẠI cho loa Phicomm R1 (tích hợp r1_speaker).
 *
 * Có: «Giữ để nói» (giữ nút = mic ĐIỆN THOẠI ra loa, thả = nghe lại loa), «Bật mic luôn» (mic điện thoại mở liên tục), TRẠNG THÁI
 * MIC (tắt / nghe / gửi — luôn hiện, có chữ chứ không chỉ màu), công tắc tắt mic, nút Tạm dừng /
 * Phát nhạc, và thẻ EQ (r1-eq-card) nhúng bên dưới. Thẻ KHÔNG gọi loa: chỉ đọc trạng thái thực thể
 * HA và gọi dịch vụ HA (switch.turn_on/off, media_player.*) và mở MỘT WebSocket về chính HA cho mic điện thoại.
 *
 * Cấu hình tối thiểu:   type: custom:r1-talk-card
 * Nhiều loa:            device_id: <mã thiết bị>
 * Không nhúng thẻ EQ:   show_eq: false
 * Chỉ định tay:         entities: { intercom: switch.x, mic_status: sensor.z,
 *                         wake: binary_sensor.w, speaker: media_player.v, mute: switch.u }
 */
(function () {
  "use strict";
  var BUILD = "2026-10-22.11";

  var PLATFORM = "r1_speaker";
  var STATUS = { tat: "off", nghe: "listening", gui: "sending" };
  var TEXT = {
    vi: {
      title: "Loa R1 — Đàm thoại", hold: "Giữ để nói", holding: "🔴 Đang nói — thả ra để nghe", always: "Bật mic luôn", mic: "Mic",
      off: "Tắt", listening: "Đang nghe", sending: "Đang gửi", unknown: "Không rõ",
      off_tip: "Không có tiếng nào rời loa.",
      listening_tip: "Loa chờ từ đánh thức; chưa gửi tiếng nào về Home Assistant.",
      listening_tip_ha: "Mic loa gửi tiếng LIÊN TỤC về Home Assistant; HA đang dò từ đánh thức trong luồng đó.",
      sending_tip: "Tiếng mic đang được gửi về Home Assistant.",
      unknown_tip: "Không đọc được trạng thái mic — coi như mic có thể đang mở.",
      busy: "Đang có phiên", mute: "Tắt mic", conn: "Kết nối loa (bật/tắt để dò lỗi phát nhạc)", dlna: "DLNA", airplay: "AirPlay", bluetooth: "Bluetooth",
      bt_unknown: "Bluetooth chưa đọc được trạng thái (cần ADB)", music: "Nhạc", music_last: "Bài vừa rồi", pause: "Tạm dừng", play: "Phát",
      nothing: "Không có nhạc đang phát", playing: "Đang phát", paused: "Đã tạm dừng",
      r_finished: "đã hết bài", r_stopped: "đã dừng", r_error: "lỗi phát (renderer DLNA của loa báo lỗi)", r_interrupted: "bị bài khác thay",
      pending: "Phía loa chưa có (từ đánh thức trên loa còn chờ)",
      refused: "Phiên bị từ chối gần đây", none: "Không tìm thấy thực thể r1_speaker nào.",
      no_mic: "Mic chưa sẵn sàng — chưa mở được phiên",
      ng_on: "👂 Nghe tiếng trong nhà", ng_off: "Dừng nghe", ng_wait: "Đang nối…", ng_live: "ĐANG NGHE mic loa — tiếng trong nhà đang được phát ra điện thoại",
      ng_mute: "Mic loa đang tắt: không có gì để nghe", ng_err: "Không nghe được", ng_denied: "Chỉ quản trị viên được nghe mic loa",
      ng_ended: "Đã dừng nghe",
      dt_bat: "📞 Bật đàm thoại", dt_tat: "Tắt đàm thoại", song_song: "Song song (hai bên cùng nói/nghe, có lọc âm)",
      ss_note_on: "Song song: mic loa và mic điện thoại cùng chạy; khử vọng và lọc âm áp dụng.",
      ss_note_off: "Nửa công: ai có tiếng thì giữ quyền nói; im lặng thì quyền nói tự về loa.",
      huong_loa: "Đang nghe loa (quyền nói ở loa)", huong_dien_thoai: "Điện thoại đang nói — mic loa tạm bỏ",
      huong_song_song: "Song song — hai bên cùng nghe", dt_assist: "Assist tạm nghỉ chờ từ khoá trong lúc đàm thoại.",
      gain_nghe: "Âm lượng nghe trên điện thoại", dt_wait: "Đang nối…",
      vol_loa: "Âm lượng loa", vol_off: "Chưa chỉnh được: loa chưa nối hoặc APK cũ chưa báo âm lượng.",
      dt_on: "Mic điện thoại sẵn sàng — giữ nút để nói", dt_on_luon: "Mic điện thoại mở liên tục",
      dt_https: "Trình duyệt chỉ cho dùng mic khi mở Home Assistant bằng https (địa chỉ ngoài hoặc https trong nhà).",
      dt_err: "Không mở được mic điện thoại", dt_busy: "Loa đang có kênh khác (điện thoại khác hoặc phiên đang mở).",
      dt_fail: "Không mở được phiên đàm thoại với loa.", dt_ended: "Phiên đàm thoại đã đóng.", dt_lost: "Đã ngắt kết nối.",
    },
    en: {
      title: "R1 speaker — Talk", hold: "Hold to talk", holding: "🔴 Talking — release to listen", always: "Mic always on", mic: "Mic",
      off: "Off", listening: "Listening", sending: "Sending", unknown: "Unknown",
      off_tip: "No audio leaves the speaker.",
      listening_tip: "The speaker waits for the wake word; nothing is sent to Home Assistant yet.",
      listening_tip_ha: "The speaker microphone streams CONTINUOUSLY to Home Assistant; HA listens for the wake word in that stream.",
      sending_tip: "Microphone audio is being sent to Home Assistant.",
      unknown_tip: "Mic status unreadable — assume the mic may be open.",
      busy: "Session in progress", mute: "Mute mic", conn: "Speaker connections (toggle to troubleshoot playback)", dlna: "DLNA", airplay: "AirPlay", bluetooth: "Bluetooth",
      bt_unknown: "Bluetooth state unreadable (needs ADB)", music: "Music", music_last: "Last track", pause: "Pause", play: "Play",
      nothing: "Nothing is playing", playing: "Playing", paused: "Paused",
      r_finished: "finished", r_stopped: "stopped", r_error: "playback error (the speaker's DLNA renderer reported an error)", r_interrupted: "replaced by another track",
      pending: "Speaker side not built yet (wake word on the speaker is pending)",
      refused: "A session was recently refused", none: "No r1_speaker entity found.",
      no_mic: "Microphone not ready — cannot start a session",
      ng_on: "👂 Listen to the house", ng_off: "Stop listening", ng_wait: "Connecting…", ng_live: "LISTENING to the speaker microphone — house sounds are playing on this phone",
      ng_mute: "Speaker microphone is off: nothing to hear", ng_err: "Could not listen", ng_denied: "Only administrators can listen to the speaker microphone",
      ng_ended: "Stopped listening",
      dt_bat: "📞 Start intercom", dt_tat: "Stop intercom", song_song: "Parallel (both sides talk/listen, filtered)",
      ss_note_on: "Parallel: speaker and phone microphones both run; echo cancelling and filters apply.",
      ss_note_off: "Half duplex: whoever has sound holds the floor; on silence the floor returns to the speaker.",
      huong_loa: "Listening to the speaker (floor on the speaker)", huong_dien_thoai: "Phone is talking — speaker mic paused",
      huong_song_song: "Parallel — both sides hear each other", dt_assist: "Assist is paused (no wake word) during the intercom.",
      gain_nghe: "Listening volume on this phone", dt_wait: "Connecting…",
      vol_loa: "Speaker volume", vol_off: "Not adjustable: speaker offline or the old APK does not report volume.",
      dt_on: "Phone microphone ready — hold to talk", dt_on_luon: "Phone microphone open continuously",
      dt_https: "The browser only allows the microphone when Home Assistant is opened over https.",
      dt_err: "Could not open the phone microphone", dt_busy: "The speaker already has another channel (another phone or an open session).",
      dt_fail: "Could not open an intercom session with the speaker.", dt_ended: "The intercom session closed.", dt_lost: "Disconnected.",
    },
  };

  function lang(hass) {
    var l = ((hass && (hass.language || (hass.locale && hass.locale.language))) || "vi");
    return l.toLowerCase().indexOf("vi") === 0 ? "vi" : "en";
  }

  function stateOf(hass, id) { return id && hass && hass.states ? hass.states[id] : undefined; }
  function isUp(st) { return !!st && st.state !== "unavailable" && st.state !== "unknown"; }
  /* Nút (button) có trạng thái «unknown» cho tới lần bấm đầu: chỉ «unavailable» mới là không dùng được. */
  function btnUp(st) { return !!st && st.state !== "unavailable"; }

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
    var by = function (domain, key) {
      return mine.filter(function (id) {
        return id.split(".")[0] === domain && reg[id].translation_key === key;
      }).sort()[0];
    };
    return {
      intercom: by("switch", "intercom_open"), song: by("switch", "song_song"),
      mic_status: by("sensor", "mic_status"), wake: by("binary_sensor", "wake"),
      speaker: by("media_player", "speaker"), mute: by("switch", "mute"), volume: by("number", "volume"),
      dlna: by("switch", "dlna"), airplay: by("switch", "airplay"), bluetooth: by("switch", "bluetooth"),
      device_id: mine.length ? reg[mine[0]].device_id : null,
    };
  }

  /* Dữ liệu thuần cho thẻ (kiểm được bằng Node): không đụng DOM. */
  function buildModel(hass, config) {
    config = config || {};
    var ent = discover(hass, config);
    var o = config.entities || {};
    Object.keys(o).forEach(function (k) { if (o[k]) ent[k] = o[k]; });
    var st = stateOf(hass, ent.mic_status);
    var a = (st && st.attributes) || {};
    // Trạng thái mic: giá trị lạ / không đọc được KHÔNG được hiện như «tắt» (an toàn: «không rõ»).
    var status = st && STATUS[st.state] ? STATUS[st.state] : "unknown";
    var mic = {
      entity: ent.mic_status || null, present: !!ent.mic_status, status: status,
      raw: st ? st.state : null, session: a.phien || null, mode: a.che_do_tu_danh_thuc || null,
      muted_audio: a.bo_tieng === true, speakerSide: a.phia_loa || null,
      refused: Number(a.so_lan_tu_choi || 0), lastRefusal: a.tu_choi_gan_nhat || null,
    };
    var ist = stateOf(hass, ent.intercom);
    var inSession = !!mic.session;
    var intercom = { entity: ent.intercom || null, present: !!ent.intercom, available: isUp(ist),
                     on: !!ist && ist.state === "on",
                     giuMo: !!ist && !!ist.attributes && ist.attributes.giu_mo === true,
                     huong: (ist && ist.attributes && ist.attributes.huong) || null };
    // Âm lượng nhạc của loa (number do APK báo/đặt): không khả dụng thì thanh trượt tắt và nói rõ lý do.
    var vst = stateOf(hass, ent.volume);
    var vnum = vst ? Number(vst.state) : NaN;
    var vol = { entity: ent.volume || null, present: !!ent.volume, available: isUp(vst) && !isNaN(vnum),
                value: isNaN(vnum) ? null : vnum,
                max: (vst && vst.attributes && Number(vst.attributes.max)) || 15 };
    var sst = stateOf(hass, ent.song);
    var song = { entity: ent.song || null, present: !!ent.song, available: isUp(sst), on: !!sst && sst.state === "on" };
    // «Giữ để nói» / «Bật mic luôn» bấm được khi công tắc đàm thoại sẵn sàng (mic đã nối, chưa tắt)
    // và KHÔNG có phiên Assist chiếm chỗ; phiên đàm thoại của chính nó không tính là «bận».
    var assistBusy = inSession && !intercom.on;
    var talk = {
      entity: intercom.entity, present: intercom.present, available: intercom.available,
      enabled: intercom.available && !assistBusy,
      reason: !intercom.available ? "no_mic" : (assistBusy ? "busy" : null),
    };
    var sp = stateOf(hass, ent.speaker);
    var sa = (sp && sp.attributes) || {};
    var ms = sp ? sp.state : null;
    var music = {
      entity: ent.speaker || null, present: !!ent.speaker, available: isUp(sp), state: ms,
      title: sa.media_title || null, dur: sa.media_duration || null, reason: sa.idle_reason || null,
      canPause: isUp(sp) && (ms === "playing" || ms === "buffering"),
      canPlay: isUp(sp) && ms === "paused",
    };
    var always = { entity: intercom.entity, present: intercom.present, on: intercom.on && intercom.giuMo };
    var mst = stateOf(hass, ent.mute);
    var mute = { entity: ent.mute || null, present: !!ent.mute, available: isUp(mst),
                 on: isUp(mst) ? mst.state === "on" : null };
    var conn = {};
    ["dlna", "airplay", "bluetooth"].forEach(function (k) {
      var cs = stateOf(hass, ent[k]);
      // «unknown» (ví dụ Bluetooth chưa đọc được qua ADB) vẫn cho bấm lệnh; chỉ «unavailable» mới khoá.
      var co = !!cs && cs.state !== "unavailable";
      conn[k] = { entity: ent[k] || null, present: !!ent[k], available: co, on: co ? (cs.state === "on" ? true : (cs.state === "off" ? false : null)) : null,
                  note: (cs && cs.attributes && cs.attributes.renderer) || "" };
    });
    var wst = stateOf(hass, ent.wake);
    var wa = (wst && wst.attributes) || {};
    var wake = { entity: ent.wake || null, present: !!ent.wake, on: !!wst && wst.state === "on",
                 pending: wa.phia_loa === "CHO_PHIA_LOA", mode: wa.che_do || mic.mode };
    return {
      found: !!(ent.intercom || ent.mic_status || ent.speaker), mic: mic, talk: talk, intercom: intercom, song: song, volume: vol,
      music: music, always: always, mute: mute, conn: conn, wake: wake, deviceId: ent.device_id,
      showEq: config.show_eq !== false,
    };
  }

  var CSS = [
    ":host{display:block}", "ha-card{padding:12px 16px}", "h2{margin:0 0 8px;font-size:1.1em}",
    ".row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:8px 0}",
    ".mic{display:flex;align-items:center;gap:8px;font-weight:600}",
    ".dot{width:12px;height:12px;border-radius:50%;background:var(--disabled-color,#9e9e9e)}",
    ".mic[data-status=sending] .dot{background:var(--error-color,#db4437)}",
    ".mic[data-status=listening] .dot{background:var(--warning-color,#f5a623)}",
    ".mic[data-status=unknown] .dot{background:var(--error-color,#db4437);outline:2px dashed currentColor}",
    ".tip{font-size:.8em;opacity:.75;margin:2px 0 6px}",
    "button{font:inherit;padding:8px 16px;border-radius:8px;border:1px solid var(--divider-color,#bbb);",
    "background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff);cursor:pointer}",
    "button.sec{background:transparent;color:inherit}",
    "button.noi{background:var(--error-color,#db4437);color:#fff}",
    "button[disabled]{opacity:.45;cursor:not-allowed}",
    // Nhấn GIỮ trên màn hình cảm ứng: không có touch-action:none thì trình duyệt điện thoại bắt đầu cuộn/menu
    // giữ lâu và HUỶ thao tác (pointercancel) ngay, nên «giữ để nói» không giữ được.
    "button[data-hold]{touch-action:none;-webkit-touch-callout:none;-webkit-user-select:none;user-select:none}",
    ".warn{color:var(--error-color,#db4437);font-size:.85em}",
    ".note{font-size:.8em;opacity:.75}",
    "section{margin-top:10px;border-top:1px solid var(--divider-color,#ddd);padding-top:6px}",
    ".eq{margin-top:10px}",
  ].join("");

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  class R1TalkCard extends (typeof HTMLElement !== "undefined" ? HTMLElement : Object) {
    constructor() {
      super();
      this._config = {};
      this._sig = null;
      if (this.attachShadow) this.attachShadow({ mode: "open" });
    }

    static getStubConfig() { return {}; }
    setConfig(config) { this._config = config || {}; this._sig = null; if (this._hass) this._render(); }
    getCardSize() { return 8; }
    set hass(hass) { this._hass = hass; this._render(); }

    _call(domain, service, data) { return this._hass.callService(domain, service, data); }

    _render() {
      if (!this._hass || !this.shadowRoot) return;
      var m = buildModel(this._hass, this._config);
      var t = TEXT[lang(this._hass)];
      // Dựng lại khi bộ thực thể (hoặc ngôn ngữ) đổi — kể cả lúc đầu chưa thấy thực thể nào rồi mới
      // có (HA khởi động / đăng ký thực thể đến muộn): không bao giờ cập nhật lên DOM chưa dựng.
      var sig = JSON.stringify([m.found, m.mic.entity, m.talk.entity, m.music.entity,
        m.mute.entity, m.wake.entity, m.showEq, lang(this._hass)]);
      if (sig !== this._sig) {
        this._sig = sig;
        this._eq = null;
        this._t = t;
        this.shadowRoot.innerHTML = "<style>" + CSS + "</style>" + this._html(m, t);
        this._bind();
        this._mountEq();
      }
      this._update(m, t);
    }

    _html(m, t) {
      if (!m.found) return '<ha-card><div class="warn">' + esc(t.none) + "</div></ha-card>";
      return '<ha-card><h2>' + esc(t.title) + "</h2>" +
        '<div class="mic" data-mic data-status="unknown"><span class="dot"></span>' +
        '<span>' + esc(t.mic) + ': <b data-mic-text></b></span></div>' +
        '<div class="tip" data-mic-tip></div>' +
        '<div class="warn" data-refused style="display:none"></div>' +
        '<section data-dt-sec><div class="row"><button data-dt-bat>' + esc(t.dt_bat) + "</button></div>" +
        '<div class="tip" data-dt-status></div><div class="warn" data-dt-err style="display:none"></div>' +
        '<div class="row"><label>' + esc(t.song_song) + '</label><ha-switch data-song-song></ha-switch></div>' +
        '<div class="note" data-ss-note></div>' +
        '<div class="row"><button data-hold>' + esc(t.hold) + '</button><button class="sec" data-always>' + esc(t.always) + "</button></div>" +
        '<div class="row" data-vol-row><label>' + esc(t.vol_loa) + '</label><input type="range" data-vol min="0" max="15" step="1">' +
        '<span class="val" data-vol-val></span></div><div class="note" data-vol-off style="display:none">' + esc(t.vol_off) + "</div>" +
        '<div class="row"><label>' + esc(t.gain_nghe) + '</label><input type="range" data-nghe-gain min="100" max="800" step="50">' +
        '<span class="val" data-gain-val></span></div></section>' +
        '<div class="row" data-ng-row style="display:none"><button class="sec" data-nghe>' + esc(t.ng_on) + "</button>" +
        '<span data-ng-muc class="muc"></span></div><div class="tip" data-ng-status></div>' +
        '<div class="row"><label>' + esc(t.mute) + '</label><ha-switch data-mute></ha-switch></div>' +
        '<section data-conn-sec style="display:none"><b>' + esc(t.conn) + "</b>" +
        ["dlna", "airplay", "bluetooth"].map(function (k) {
          return '<div class="row" data-conn-row="' + k + '"><label>' + esc(t[k]) + '</label><ha-switch data-conn="' + k + '"></ha-switch></div>';
        }).join("") + '<div class="tip" data-conn-note></div></section>' +
        '<div class="note" data-pending style="display:none">' + esc(t.pending) + "</div>" +
        '<section><div class="row"><span>' + esc(t.music) + ': <span data-music-text></span></span>' +
        '<span><button class="sec" data-pause>' + esc(t.pause) + '</button> ' +
        '<button class="sec" data-play>' + esc(t.play) + "</button></span></div></section>" +
        '<div class="eq" data-eq></div></ha-card>';
    }

    _bind() {
      var root = this.shadowRoot, self = this;
      var on = function (sel, fn) { var el = root.querySelector(sel); if (el) el.addEventListener("click", fn); };
      // Mọi nút đọc mô hình MỚI NHẤT lúc bấm (thực thể có thể đổi sau lần dựng).
      var now = function () { return buildModel(self._hass, self._config); };
      // Giữ để nói (đúng như bộ đàm camera của c2a): giữ nút = mic ĐIỆN THOẠI đi ra loa, thả = nghe lại loa.
      // Lần giữ đầu mở kênh (xin mic, nối WebSocket) ngay trong cử chỉ bấm; kênh mở sẵn thì lần sau nói được liền.
      var hold = root.querySelector("[data-hold]");
      if (hold) {
        hold.addEventListener("pointerdown", function (ev) {
          ev.preventDefault();
          var m = now();
          if (!m.talk.enabled) return;                  // loa chưa nối / phiên Assist đang chiếm
          // Giữ nguồn con trỏ cho nút: kéo ngón ra ngoài vẫn đang giữ (như nút «giữ để nói» của camera).
          try { hold.setPointerCapture(ev.pointerId); } catch (e) { /* sự kiện không có pointerId */ }
          self._dtGiuBat();
        });
        ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (n) {
          hold.addEventListener(n, function () { self._dtGiuTha(); });
        });
        hold.addEventListener("contextmenu", function (ev) { ev.preventDefault(); });
      }
      on("[data-always]", function () {
        var m = now();
        if (!m.talk.enabled && !self._dtLuon) return;
        self._dtLuonDoi();
      });
      on("[data-pause]", function () {
        var m = now();
        if (m.music.canPause) self._call("media_player", "media_pause", { entity_id: m.music.entity });
      });
      on("[data-play]", function () {
        var m = now();
        if (m.music.canPlay) self._call("media_player", "media_play", { entity_id: m.music.entity });
      });
      on("[data-dt-bat]", function () { if (self._dt) self._dtDong(); else self._dtMo(); });
      var ss = root.querySelector("[data-song-song]");
      if (ss) ss.addEventListener("change", function () {
        var m = now();
        if (m.song.available) self._call("switch", ss.checked ? "turn_on" : "turn_off", { entity_id: m.song.entity });
      });
      var vs = root.querySelector("[data-vol]");
      if (vs) vs.addEventListener("change", function () {
        var m2 = now();
        if (m2.volume.available) self._call("number", "set_value", { entity_id: m2.volume.entity, value: Number(vs.value) });
      });
      var gs = root.querySelector("[data-nghe-gain]");
      if (gs) gs.addEventListener("input", function () { self._datGain(Number(gs.value)); });
      on("[data-nghe]", function () { if (self._ng) self._ngDong(); else self._ngMo(); });
      root.querySelectorAll("[data-conn]").forEach(function (cs) {
        cs.addEventListener("change", function () {
          var c = now().conn[cs.dataset.conn];
          if (c && c.available) self._call("switch", cs.checked ? "turn_on" : "turn_off", { entity_id: c.entity });
        });
      });
      var sw = root.querySelector("[data-mute]");
      if (sw) sw.addEventListener("change", function () {
        var m = now();
        if (m.mute.available) self._call("switch", sw.checked ? "turn_on" : "turn_off", { entity_id: m.mute.entity });
      });
    }

    _mountEq() {
      var host = this.shadowRoot.querySelector("[data-eq]");
      if (!host || this._config.show_eq === false || typeof customElements === "undefined" ||
          !customElements.get("r1-eq-card")) return;
      this._eq = document.createElement("r1-eq-card");
      var cfg = {};
      if (this._config.device_id) cfg.device_id = this._config.device_id;
      this._eq.setConfig(cfg);
      host.appendChild(this._eq);
    }

    connectedCallback() {
      var self = this;
      this._dtAn = function () { if (document.visibilityState === "hidden") { self._dtDong(); self._ngDong(); } };
      this._dtRoi = function () { self._dtDong(); self._ngDong(); };
      document.addEventListener("visibilitychange", this._dtAn);
      window.addEventListener("pagehide", this._dtRoi);
    }

    disconnectedCallback() {
      document.removeEventListener("visibilitychange", this._dtAn);
      window.removeEventListener("pagehide", this._dtRoi);
      this._dtDong();
      this._ngDong();
    }

    /* ── Mic điện thoại (như bộ đàm camera của c2a): MỘT WebSocket hai chiều tới HA. Mic chỉ gửi khi đang giữ nút
       (hoặc «Bật mic luôn»); tiếng loa phát ra điện thoại suốt lúc kênh mở. Kênh đóng hẳn khi ẩn tab / rời trang. */
    /* ── Âm thanh phát ra điện thoại: gain người dùng + bộ nén (khỏi vỡ tiếng khi to) ─────────────────── */
    _gainNghe() {
      if (this._gain === undefined) {
        var g = 300;
        try { g = Number(localStorage.getItem("r1_nghe_gain")) || 300; } catch (e) { /* chế độ riêng tư */ }
        this._gain = Math.min(800, Math.max(100, g)) / 100;
      }
      return this._gain;
    }

    _datGain(pct) {
      this._gain = Math.min(800, Math.max(100, pct)) / 100;
      try { localStorage.setItem("r1_nghe_gain", String(Math.round(this._gain * 100))); } catch (e) { /* không nhớ cũng được */ }
      var self = this;
      [this._dt, this._ng].forEach(function (o) { if (o && o.gain) o.gain.gain.value = self._gain; });
      var v = this.shadowRoot && this.shadowRoot.querySelector("[data-gain-val]");
      if (v) v.textContent = Math.round(this._gain * 100) + "%";
    }

    _chuoiAm(o) {
      var ac = o.ac;
      o.gain = ac.createGain();
      o.gain.gain.value = this._gainNghe();
      // Lọc phía điện thoại (nhẹ, không tốn CPU của HA): cắt ồn trầm (quạt, rung bàn) rồi nén để tiếng to không vỡ.
      var cao = ac.createBiquadFilter();
      cao.type = "highpass"; cao.frequency.value = 120;
      var nen = ac.createDynamicsCompressor();
      o.gain.connect(cao); cao.connect(nen); nen.connect(ac.destination);
    }

    _taoAc() {
      var AC = window.AudioContext || window.webkitAudioContext;
      var ac;
      try { ac = new AC({ sampleRate: 16000, latencyHint: "interactive" }); } catch (e) { ac = new AC({ sampleRate: 16000 }); }
      if (ac.state === "suspended" && ac.resume) ac.resume();
      return ac;
    }

    /* ── Nghe tiếng trong nhà (một chiều loa → điện thoại, CHỈ quản trị viên, không cần mic điện thoại) ── */
    _ngHienThi(loi) {
      var root = this.shadowRoot, t = this._t || TEXT.vi;
      if (!root) return;
      var row = root.querySelector("[data-ng-row]"), btn = root.querySelector("[data-nghe]");
      var st = root.querySelector("[data-ng-status]"), muc = root.querySelector("[data-ng-muc]");
      if (!row) return;
      if (loi !== undefined) this._ngLoi = loi || "";
      var admin = !!(this._hass && this._hass.user && this._hass.user.is_admin);
      row.style.display = admin ? "" : "none";
      btn.textContent = this._ng ? t.ng_off : t.ng_on;
      btn.classList.toggle("noi", !!this._ng && !!this._ngSan);
      st.textContent = this._ng ? (this._ngSan ? t.ng_live : t.ng_wait) : (this._ngLoi || "");
      if (!this._ng) muc.textContent = "";
    }

    _ngMo() {
      var self = this, t = this._t || TEXT.vi, m = buildModel(this._hass, this._config);
      var eid = m.mic.entity || m.talk.entity;
      this._ngLoi = "";
      if (!eid) return;
      var ng = { ac: null, ws: null, lich: 0, gain: null };
      this._ng = ng; this._ngSan = false;
      try { ng.ac = this._taoAc(); this._chuoiAm(ng); }
      catch (e) { this._ngDong(t.ng_err + ": " + (e && e.message ? e.message : e)); return; }
      this._ngHienThi();
      this._hass.callWS({ type: "auth/sign_path", path: "/api/r1_speaker/nghe/" + eid + "/ws", expires: 30 })
        .then(function (r) {
          if (self._ng !== ng) return;
          var ws = new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + r.path);
          ws.binaryType = "arraybuffer";
          ng.ws = ws;
          ws.onopen = function () { self._ngSan = true; self._ngHienThi(); };
          ws.onmessage = function (e) {
            if (typeof e.data === "string") {
              try { var j = JSON.parse(e.data); if (j.loi) self._ngLoi = j.loi; } catch (x) { /* bỏ qua */ }
              return;
            }
            var i16 = new Int16Array(e.data), dinh = 0;
            for (var i = 0; i < i16.length; i++) dinh = Math.max(dinh, Math.abs(i16[i]));
            var muc = self.shadowRoot && self.shadowRoot.querySelector("[data-ng-muc]");
            if (muc) muc.textContent = "▮".repeat(Math.min(10, Math.round(dinh / 3277)));   // thanh mức tiếng
            self._dtNhan(ng, e);
          };
          ws.onclose = function (e) {
            if (self._ng !== ng) return;
            var tt = self._t || TEXT.vi;
            self._ngDong(e.code === 4404 || e.code === 4405 ? tt.ng_mute : (e.code === 4403 || e.code === 1008 ? tt.ng_denied : tt.ng_ended));
          };
        })
        .catch(function (err) {
          if (self._ng === ng) self._ngDong((self._t || TEXT.vi).ng_err + ": " + (err && err.message ? err.message : err));
        });
    }

    _ngDong(loi) {
      var ng = this._ng;
      this._ng = null; this._ngSan = false;
      if (ng) {
        try { if (ng.ws) { ng.ws.onclose = null; ng.ws.close(); } } catch (e) { /* đã đóng */ }
        try { if (ng.ac) ng.ac.close(); } catch (e) { /* đã đóng */ }
      }
      this._ngHienThi(loi || "");
    }

    /* ── Đàm thoại qua điện thoại (như bộ đàm camera của c2a): MỘT WebSocket hai chiều tới HA ────────────
       «Bật đàm thoại» mở kênh NGHE loa (không cần quyền mic, chạy cả qua http); mic điện thoại chỉ xin lần đầu
       giữ nút / «Bật mic luôn» (cần https). Giữ nút = báo «noi» (giữ quyền nói); «Bật mic luôn» = HA tự nhận ra tiếng nói (VOX). */
    _dtHienThi(loi) {
      var root = this.shadowRoot, t = this._t || TEXT.vi;
      if (!root) return;
      var bat = root.querySelector("[data-dt-bat]"), st = root.querySelector("[data-dt-status]");
      var er = root.querySelector("[data-dt-err]");
      if (!bat) return;
      if (loi !== undefined) this._dtLoi = loi || "";
      bat.textContent = this._dt ? t.dt_tat : t.dt_bat;
      bat.classList.toggle("noi", !!this._dt && !!this._dtSan);
      var huong = this._huong || null;
      var chu = "";
      if (this._dt) {
        if (!this._dtSan) chu = t.dt_wait;
        else {
          chu = (huong === "dien_thoai" ? t.huong_dien_thoai : huong === "song_song" ? t.huong_song_song : t.huong_loa);
          if (this._dtLuon) chu += " · " + t.dt_on_luon; else if (this._dtNoi) chu += " · " + t.holding;
          chu += " — " + t.dt_assist;
        }
      }
      st.textContent = chu;
      er.style.display = this._dtLoi ? "" : "none";
      er.textContent = this._dtLoi || "";
      this._capNhatNutGiu();
    }

    /* Gọi TRONG cử chỉ bấm: AudioContext tạo và resume ngay đây (iOS/Android chỉ cho phát khi bắt đầu từ cử chỉ). */
    _dtMo() {
      var self = this, t = this._t || TEXT.vi, m = buildModel(this._hass, this._config);
      var eid = m.mic.entity || m.talk.entity;
      this._dtLoi = "";
      if (!eid) return;
      var dt = { stream: null, ac: null, ws: null, lich: 0, gain: null, xinMic: false };
      this._dt = dt; this._dtSan = false; this._dtNoi = false; this._dtPtt = false;
      try { dt.ac = this._taoAc(); this._chuoiAm(dt); }
      catch (e) { this._dtDong(t.dt_err + ": " + (e && e.message ? e.message : e)); return; }
      this._dtHienThi();
      this._hass.callWS({ type: "auth/sign_path", path: "/api/r1_speaker/dam_thoai/" + eid + "/ws", expires: 30 })
        .then(function (r) {
          if (!r || self._dt !== dt) return;
          var ws = new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + r.path);
          ws.binaryType = "arraybuffer";
          dt.ws = ws;
          ws.onopen = function () {
            self._dtSan = true;
            if (self._giu || self._dtLuon) self._dtXinMic();
            self._dtDatNoi(); self._dtHienThi();
          };
          ws.onmessage = function (e) { self._dtNhan(dt, e); };
          ws.onclose = function (e) {
            if (self._dt !== dt) return;
            var tt = self._t || TEXT.vi;
            var ly = e.code === 4409 ? tt.dt_busy : e.code === 4400 ? tt.dt_fail : e.code === 4001 ? tt.dt_ended : tt.dt_lost;
            self._dtDong(ly);
          };
        })
        .catch(function (err) {
          if (self._dt === dt) self._dtDong((self._t || TEXT.vi).dt_err + ": " + (err && err.message ? err.message : err));
        });
    }

    /* Xin mic điện thoại LẦN ĐẦU cần (trong cử chỉ giữ nút / bật mic luôn). Cần https. */
    _dtXinMic() {
      var self = this, dt = this._dt;
      if (!dt || dt.stream || dt.xinMic) return;
      if (!this._dtCoThe()) { this._giu = false; this._dtLuon = false; this._dtHienThi(); return; }
      dt.xinMic = true;
      navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
        .then(function (stream) {
          dt.xinMic = false;
          if (self._dt !== dt) { stream.getTracks().forEach(function (k) { k.stop(); }); return; }
          dt.stream = stream;
          self._dtNoiMic(dt); self._dtDatNoi(); self._dtHienThi();
        })
        .catch(function (err) {
          dt.xinMic = false; self._giu = false; self._dtLuon = false;
          self._dtHienThi(((self._t || TEXT.vi).dt_err) + ": " + (err && err.message ? err.message : err));
        });
    }

    _dtNoiMic(dt) {
      var self = this, ac = dt.ac;
      var nguon = ac.createMediaStreamSource(dt.stream);
      var xl = ac.createScriptProcessor(2048, 1, 1);          // cũ nhưng chạy mọi trình duyệt, không cần tệp worklet
      xl.onaudioprocess = function (e) {
        var ws = dt.ws;
        if (!self._dtNoi || !ws || ws.readyState !== 1) return;
        var f = e.inputBuffer.getChannelData(0), i16 = new Int16Array(f.length);
        for (var i = 0; i < f.length; i++) i16[i] = Math.max(-1, Math.min(1, f[i])) * 32767;
        ws.send(i16.buffer);
      };
      var cam = ac.createGain();
      cam.gain.value = 0;                                      // processor phải nối ra đích mới chạy; không phát lại tiếng mình
      nguon.connect(xl); xl.connect(cam); cam.connect(ac.destination);
    }

    _dtNhan(dt, e) {
      if (typeof e.data === "string") {
        try { var j = JSON.parse(e.data); if (j.loi) this._dtHienThi(j.loi); } catch (x) { /* bỏ qua */ }
        return;
      }
      var ac = dt.ac, i16 = new Int16Array(e.data);
      if (!ac || !i16.length) return;
      var f = new Float32Array(i16.length);
      for (var i = 0; i < i16.length; i++) f[i] = i16[i] / 32768;
      var now = ac.currentTime;
      if (dt.lich - now > 0.5) return;                         // tụt hậu quá nửa giây: bỏ khúc này để đuổi kịp (đỡ «chậm»)
      if (dt.lich < now + 0.03) dt.lich = now + 0.08;
      var buf = ac.createBuffer(1, f.length, 16000);
      buf.copyToChannel(f, 0);
      var src = ac.createBufferSource();
      src.buffer = buf; src.connect(dt.gain || ac.destination); src.start(dt.lich);
      dt.lich += buf.duration;
    }

    _dtCoThe() {
      var t = this._t || TEXT.vi;
      if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        this._dtHienThi(t.dt_https); return false;
      }
      return true;
    }

    /* Mic điện thoại đi khi: đang giữ nút HOẶC «Bật mic luôn», kênh mở và đã có mic. Giữ nút báo «noi»/«het» cho HA. */
    _dtDatNoi() {
      var dt = this._dt;
      if (!dt) return;
      var noi = !!(this._dtSan && dt.stream && (this._giu || this._dtLuon));
      var ptt = !!(this._giu && noi);
      var ws = dt.ws, truoc = this._dtNoi;
      this._dtNoi = noi;
      if (noi && dt.ac && dt.ac.state === "suspended" && dt.ac.resume) dt.ac.resume();
      if (ws && ws.readyState === 1) {
        if (ptt && !this._dtPtt) ws.send("noi");
        else if (!ptt && (this._dtPtt || (truoc && !noi))) ws.send("het");
      }
      this._dtPtt = ptt;
    }

    _dtGiuBat() {
      if (!this._dtCoThe()) return;
      this._giu = true;
      if (!this._dt) this._dtMo();
      this._dtXinMic();
      this._dtDatNoi();
      this._dtHienThi();
    }

    _dtGiuTha() {
      if (!this._giu) return;
      this._giu = false;
      this._dtDatNoi();
      this._dtHienThi();
    }

    _dtLuonDoi() {
      if (this._dtLuon) { this._dtLuon = false; this._dtDatNoi(); this._dtHienThi(); return; }
      if (!this._dtCoThe()) return;
      this._dtLuon = true;
      if (!this._dt) this._dtMo();
      this._dtXinMic();
      this._dtDatNoi();
      this._dtHienThi();
    }

    _dtDong(loi) {
      var dt = this._dt;
      this._dt = null; this._dtSan = false; this._dtNoi = false; this._dtPtt = false; this._dtLuon = false; this._giu = false;
      if (dt) {
        try { if (dt.ws) { dt.ws.onclose = null; dt.ws.close(); } } catch (e) { /* đã đóng */ }
        try { if (dt.stream) dt.stream.getTracks().forEach(function (k) { k.stop(); }); } catch (e) { /* đã dừng */ }
        try { if (dt.ac) dt.ac.close(); } catch (e) { /* đã đóng */ }
      }
      this._dtHienThi(loi || "");
    }

    _capNhatNutGiu() {
      var root = this.shadowRoot;
      var hold = root && root.querySelector("[data-hold]"), al = root && root.querySelector("[data-always]");
      if (!hold || !this._t) return;
      var t = this._t, noi = !!this._dtNoi, nho = !!this._giu && !noi;     // nho = đang giữ nhưng mic/kênh chưa sẵn sàng
      hold.classList.toggle("noi", noi && !this._dtLuon);
      hold.textContent = noi && !this._dtLuon ? t.holding : (nho ? t.dt_wait : t.hold);
      if (al) {
        al.classList.toggle("noi", !!this._dtLuon && noi);
        al.textContent = t.always + (this._dtLuon ? " ✓" : "");
      }
    }

    _update(m, t) {
      var root = this.shadowRoot;
      if (!m.found) return;
      var q = function (s) { return root.querySelector(s); };
      q("[data-mic]").dataset.status = m.mic.status;
      q("[data-mic-text]").textContent = t[m.mic.status];
      // Chế độ «ha»: luồng mic chảy liên tục về HA để HA dò từ đánh thức, nên «Đang nghe» KHÔNG có nghĩa là chưa gửi gì.
      q("[data-mic-tip]").textContent = (m.mic.status === "listening" && m.mic.mode !== "speaker"
        ? t.listening_tip_ha : t[m.mic.status + "_tip"]) || "";
      var hold = q("[data-hold]"), al = q("[data-always]");
      // Nút «giữ để nói» KHÔNG được vô hiệu hoá khi ngón tay còn đang giữ: phiên vừa mở làm trạng thái HA đổi
      // thoáng chốc, nút bị khoá giữa chừng là trình duyệt huỷ thao tác giữ và đàm thoại tắt ngay (như nút camera
      // của c2a: không bao giờ khoá lúc đang giữ).
      hold.disabled = !m.talk.enabled && !this._giu;
      al.disabled = !m.talk.enabled && !this._dtLuon;
      this._t = t;
      hold.title = al.title = m.talk.reason ? t[m.talk.reason] : "";
      var sw = q("[data-mute]");
      if (sw) { sw.disabled = !m.mute.available; sw.checked = m.mute.on === true; }
      var csec = q("[data-conn-sec]");
      if (csec) {
        var coAi = ["dlna", "airplay", "bluetooth"].some(function (k) { return m.conn[k].present; });
        csec.style.display = coAi ? "" : "none";
        ["dlna", "airplay", "bluetooth"].forEach(function (k) {
          var row = q('[data-conn-row="' + k + '"]'), c = m.conn[k], cs = q('[data-conn="' + k + '"]');
          if (row) row.style.display = c.present ? "" : "none";
          if (cs) { cs.disabled = !c.available; cs.checked = c.on === true; }
        });
        var nt = [];
        if (m.conn.dlna.note) nt.push("DLNA: " + m.conn.dlna.note);
        if (m.conn.bluetooth.present && m.conn.bluetooth.available && m.conn.bluetooth.on === null) nt.push(t.bt_unknown);
        q("[data-conn-note]").textContent = nt.join(" · ");
      }
      q("[data-pending]").style.display = m.wake.pending && m.wake.mode === "speaker" ? "" : "none";
      var rf = q("[data-refused]");
      rf.style.display = m.mic.refused ? "" : "none";
      rf.textContent = m.mic.refused ? t.refused + ": " + (m.mic.lastRefusal || "") : "";
      var mt = m.music.canPause ? t.playing : (m.music.canPlay ? t.paused : t.nothing);
      var xt = mt;
      if (m.music.title) xt += " — " + m.music.title;
      if ((m.music.canPause || m.music.canPlay) && m.music.dur) {
        xt += " (" + Math.floor(m.music.dur / 60) + ":" + ("0" + (m.music.dur % 60)).slice(-2) + ")";
      } else if (!m.music.canPause && !m.music.canPlay && m.music.reason && t["r_" + m.music.reason]) {
        xt = t.music_last + " " + t["r_" + m.music.reason];     // vì sao loa đang im: hết bài / người dùng dừng / lỗi
      }
      q("[data-music-text]").textContent = xt;
      q("[data-pause]").disabled = !m.music.canPause;
      q("[data-play]").disabled = !m.music.canPlay;
      var ss = q("[data-song-song]");
      if (ss) { ss.disabled = !m.song.available; ss.checked = m.song.on; }
      var nt = q("[data-ss-note]");
      if (nt) nt.textContent = m.song.on ? t.ss_note_on : t.ss_note_off;
      this._huong = m.intercom.huong;
      var vs = q("[data-vol]"), vv = q("[data-vol-val]"), vrow = q("[data-vol-row]"), voff = q("[data-vol-off]");
      if (vrow) vrow.style.display = m.volume.present ? "" : "none";
      if (vs) {
        vs.max = String(m.volume.max); vs.disabled = !m.volume.available;
        if (m.volume.available && root.activeElement !== vs) vs.value = String(m.volume.value);
      }
      if (vv) vv.textContent = m.volume.available ? String(m.volume.value) : "—";
      if (voff) voff.style.display = m.volume.present && !m.volume.available ? "" : "none";
      var gs = q("[data-nghe-gain]");
      if (gs && root.activeElement !== gs) gs.value = String(Math.round(this._gainNghe() * 100));
      var gv = q("[data-gain-val]");
      if (gv) gv.textContent = Math.round(this._gainNghe() * 100) + "%";
      this._dtHienThi();
      this._ngHienThi();
      if (this._eq) this._eq.hass = this._hass;
    }
  }

  // r1-card dựng thẻ từ lớp này (nạp bằng URL mới mỗi lần mở trang), không phụ thuộc bản cũ còn
  // trong bộ nhớ đệm của trình duyệt dưới URL cố định.
  if (typeof window !== "undefined") {
    window.R1_THE = window.R1_THE || {};
    window.R1_THE.talk = { lop: R1TalkCard, build: BUILD };
  }

  if (typeof customElements !== "undefined" && !customElements.get("r1-talk-card")) {
    customElements.define("r1-talk-card", R1TalkCard);
    // (Không khai báo vào bộ chọn thẻ: thẻ gộp r1-card là thẻ duy nhất; thẻ này chỉ được r1-card nạp.)
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildModel: buildModel, discover: discover, TEXT: TEXT, STATUS: STATUS };
  }
})();
