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
  var BUILD = "2026-10-22.6";

  var PLATFORM = "r1_speaker";
  var STATUS = { tat: "off", nghe: "listening", gui: "sending" };
  var TEXT = {
    vi: {
      title: "Loa R1 — Đàm thoại", hold: "Giữ để nói", holding: "🔴 Đang nói — thả ra để nghe", always: "Bật mic luôn", mic: "Mic",
      off: "Tắt", listening: "Đang nghe", sending: "Đang gửi", unknown: "Không rõ",
      off_tip: "Không có tiếng nào rời loa.",
      listening_tip: "Loa chờ từ đánh thức; chưa gửi tiếng nào về Home Assistant.",
      sending_tip: "Tiếng mic đang được gửi về Home Assistant.",
      unknown_tip: "Không đọc được trạng thái mic — coi như mic có thể đang mở.",
      busy: "Đang có phiên", mute: "Tắt mic", music: "Nhạc", pause: "Tạm dừng", play: "Phát",
      nothing: "Không có nhạc đang phát", playing: "Đang phát", paused: "Đã tạm dừng",
      pending: "Phía loa chưa có (từ đánh thức trên loa còn chờ)",
      refused: "Phiên bị từ chối gần đây", none: "Không tìm thấy thực thể r1_speaker nào.",
      no_mic: "Mic chưa sẵn sàng — chưa mở được phiên",
      dt_close: "Đóng kênh điện thoại", dt_wait: "Đang nối…", dt_on: "Mic điện thoại đã mở — giữ nút để nói, thả ra để nghe loa",
      dt_on_luon: "Mic điện thoại mở liên tục — bấm «Bật mic luôn» để tắt",
      dt_https: "Trình duyệt chỉ cho dùng mic khi mở Home Assistant bằng https (địa chỉ ngoài hoặc https trong nhà).",
      dt_err: "Không mở được mic điện thoại", dt_busy: "Loa đang có kênh khác (điện thoại khác hoặc phiên đang mở).",
      dt_fail: "Không mở được phiên đàm thoại với loa.", dt_ended: "Phiên đàm thoại đã đóng.", dt_lost: "Đã ngắt kết nối.",
    },
    en: {
      title: "R1 speaker — Talk", hold: "Hold to talk", holding: "🔴 Talking — release to listen", always: "Mic always on", mic: "Mic",
      off: "Off", listening: "Listening", sending: "Sending", unknown: "Unknown",
      off_tip: "No audio leaves the speaker.",
      listening_tip: "The speaker waits for the wake word; nothing is sent to Home Assistant yet.",
      sending_tip: "Microphone audio is being sent to Home Assistant.",
      unknown_tip: "Mic status unreadable — assume the mic may be open.",
      busy: "Session in progress", mute: "Mute mic", music: "Music", pause: "Pause", play: "Play",
      nothing: "Nothing is playing", playing: "Playing", paused: "Paused",
      pending: "Speaker side not built yet (wake word on the speaker is pending)",
      refused: "A session was recently refused", none: "No r1_speaker entity found.",
      no_mic: "Microphone not ready — cannot start a session",
      dt_close: "Close phone channel", dt_wait: "Connecting…", dt_on: "Phone microphone ready — hold to talk, release to hear the speaker",
      dt_on_luon: "Phone microphone open continuously — press «Mic always on» to stop",
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
      intercom: by("switch", "intercom_open"),
      mic_status: by("sensor", "mic_status"), wake: by("binary_sensor", "wake"),
      speaker: by("media_player", "speaker"), mute: by("switch", "mute"),
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
                     giuMo: !!ist && !!ist.attributes && ist.attributes.giu_mo === true };
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
      title: sa.media_title || null,
      canPause: isUp(sp) && (ms === "playing" || ms === "buffering"),
      canPlay: isUp(sp) && ms === "paused",
    };
    var always = { entity: intercom.entity, present: intercom.present, on: intercom.on && intercom.giuMo };
    var mst = stateOf(hass, ent.mute);
    var mute = { entity: ent.mute || null, present: !!ent.mute, available: isUp(mst),
                 on: isUp(mst) ? mst.state === "on" : null };
    var wst = stateOf(hass, ent.wake);
    var wa = (wst && wst.attributes) || {};
    var wake = { entity: ent.wake || null, present: !!ent.wake, on: !!wst && wst.state === "on",
                 pending: wa.phia_loa === "CHO_PHIA_LOA", mode: wa.che_do || mic.mode };
    return {
      found: !!(ent.intercom || ent.mic_status || ent.speaker), mic: mic, talk: talk, intercom: intercom,
      music: music, always: always, mute: mute, wake: wake, deviceId: ent.device_id,
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
        '<div class="row"><button data-hold>' + esc(t.hold) + '</button><button class="sec" data-always>' + esc(t.always) + "</button></div>" +
        '<div class="tip" data-dt-status></div><div class="warn" data-dt-err style="display:none"></div>' +
        '<div class="row" data-dt-panel style="display:none"><button class="sec" data-dt-close>' + esc(t.dt_close) + "</button></div>" +
        '<div class="row"><label>' + esc(t.mute) + '</label><ha-switch data-mute></ha-switch></div>' +
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
      on("[data-dt-close]", function () { self._dtDong(); });
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
      this._dtAn = function () { if (document.visibilityState === "hidden") self._dtDong(); };
      this._dtRoi = function () { self._dtDong(); };
      document.addEventListener("visibilitychange", this._dtAn);
      window.addEventListener("pagehide", this._dtRoi);
    }

    disconnectedCallback() {
      document.removeEventListener("visibilitychange", this._dtAn);
      window.removeEventListener("pagehide", this._dtRoi);
      this._dtDong();
    }

    /* ── Mic điện thoại (như bộ đàm camera của c2a): MỘT WebSocket hai chiều tới HA. Mic chỉ gửi khi đang giữ nút
       (hoặc «Bật mic luôn»); tiếng loa phát ra điện thoại suốt lúc kênh mở. Kênh đóng hẳn khi ẩn tab / rời trang. */
    _dtHienThi(loi) {
      var root = this.shadowRoot, t = this._t || TEXT.vi;
      if (!root) return;
      var panel = root.querySelector("[data-dt-panel]"), st = root.querySelector("[data-dt-status]");
      var er = root.querySelector("[data-dt-err]");
      if (!panel) return;
      if (loi !== undefined) this._dtLoi = loi || "";
      panel.style.display = this._dt ? "" : "none";
      st.textContent = this._dt ? (this._dtSan ? (this._dtLuon ? t.dt_on_luon : t.dt_on) : t.dt_wait) : "";
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
      var AC = window.AudioContext || window.webkitAudioContext;
      var dt = { stream: null, ac: null, ws: null, lich: 0 };
      this._dt = dt; this._dtSan = false; this._dtNoi = false;
      try {
        dt.ac = new AC({ sampleRate: 16000 });
        if (dt.ac.state === "suspended" && dt.ac.resume) dt.ac.resume();
      } catch (e) { this._dtDong(t.dt_err + ": " + (e && e.message ? e.message : e)); return; }
      this._dtHienThi();
      navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
        .then(function (stream) {
          if (self._dt !== dt) { stream.getTracks().forEach(function (k) { k.stop(); }); return null; }
          dt.stream = stream;
          return self._hass.callWS({ type: "auth/sign_path", path: "/api/r1_speaker/dam_thoai/" + eid + "/ws", expires: 30 });
        })
        .then(function (r) {
          if (!r || self._dt !== dt) return;
          var ws = new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + r.path);
          ws.binaryType = "arraybuffer";
          dt.ws = ws;
          ws.onopen = function () { self._dtSan = true; self._dtNoiMic(dt); self._dtDatNoi(); self._dtHienThi(); };
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
      if (dt.lich - now > 1.0) return;                         // tụt hậu quá 1 giây: bỏ khúc này để đuổi kịp
      if (dt.lich < now + 0.05) dt.lich = now + 0.15;
      var buf = ac.createBuffer(1, f.length, 16000);
      buf.copyToChannel(f, 0);
      var src = ac.createBufferSource();
      src.buffer = buf; src.connect(ac.destination); src.start(dt.lich);
      dt.lich += buf.duration;
    }

    _dtCoThe() {
      var t = this._t || TEXT.vi;
      if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        this._dtHienThi(t.dt_https); return false;
      }
      return true;
    }

    /* Mic điện thoại đi khi: đang giữ nút HOẶC «Bật mic luôn», và kênh đã mở. */
    _dtDatNoi() {
      var noi = !!(this._dtSan && (this._giu || this._dtLuon));
      var ws = this._dt && this._dt.ws;
      var truoc = this._dtNoi;
      this._dtNoi = noi;
      if (noi && this._dt.ac && this._dt.ac.state === "suspended" && this._dt.ac.resume) this._dt.ac.resume();
      if (truoc && !noi && ws && ws.readyState === 1) ws.send("het");
    }

    _dtGiuBat() {
      if (!this._dtCoThe()) return;
      this._giu = true;
      if (!this._dt) this._dtMo(); else this._dtDatNoi();
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
      if (!this._dt) this._dtMo(); else this._dtDatNoi();
      this._dtHienThi();
    }

    _dtDong(loi) {
      var dt = this._dt;
      this._dt = null; this._dtSan = false; this._dtNoi = false; this._dtLuon = false; this._giu = false;
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
      var t = this._t, noi = !!this._dtNoi, nho = !!this._giu && !noi;     // nho = đang giữ nhưng kênh chưa mở xong
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
      q("[data-mic-tip]").textContent = t[m.mic.status + "_tip"] || "";
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
      q("[data-pending]").style.display = m.wake.pending && m.wake.mode === "speaker" ? "" : "none";
      var rf = q("[data-refused]");
      rf.style.display = m.mic.refused ? "" : "none";
      rf.textContent = m.mic.refused ? t.refused + ": " + (m.mic.lastRefusal || "") : "";
      var mt = m.music.canPause ? t.playing : (m.music.canPlay ? t.paused : t.nothing);
      q("[data-music-text]").textContent = m.music.title ? mt + " — " + m.music.title : mt;
      q("[data-pause]").disabled = !m.music.canPause;
      q("[data-play]").disabled = !m.music.canPlay;
      this._dtHienThi();
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
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "r1-talk-card", name: "Phicomm R1 — Đàm thoại",
      description: "Nút đàm thoại, trạng thái mic, tạm dừng/phát nhạc và EQ của loa Phicomm R1 (r1_speaker).",
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildModel: buildModel, discover: discover, TEXT: TEXT, STATUS: STATUS };
  }
})();
