/* r1-talk-card — thẻ Lovelace ĐÀM THOẠI cho loa Phicomm R1 (tích hợp r1_speaker).
 *
 * Có: nút Đàm thoại (tạm dừng nhạc, mở phiên Assist), nút Kết thúc, TRẠNG THÁI MIC (tắt / nghe /
 * gửi — luôn hiện, có chữ chứ không chỉ màu), công tắc tắt mic, nút Tạm dừng / Phát nhạc, và
 * thẻ EQ (r1-eq-card) nhúng bên dưới. Thẻ KHÔNG gọi loa: chỉ đọc trạng thái thực thể HA và gọi
 * dịch vụ HA (button.press, media_player.media_pause/media_play, switch.turn_on/off).
 *
 * Cấu hình tối thiểu:   type: custom:r1-talk-card
 * Nhiều loa:            device_id: <mã thiết bị>
 * Không nhúng thẻ EQ:   show_eq: false
 * Chỉ định tay:         entities: { talk: button.x, end_talk: button.y, mic_status: sensor.z,
 *                         wake: binary_sensor.w, speaker: media_player.v, mute: switch.u }
 */
(function () {
  "use strict";

  var PLATFORM = "r1_speaker";
  var STATUS = { tat: "off", nghe: "listening", gui: "sending" };
  var TEXT = {
    vi: {
      title: "Loa R1 — Đàm thoại", talk: "Đàm thoại", end: "Kết thúc", mic: "Mic",
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
    },
    en: {
      title: "R1 speaker — Talk", talk: "Talk", end: "End", mic: "Mic",
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
      talk: by("button", "talk"), end_talk: by("button", "end_talk"),
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
    var talkSt = stateOf(hass, ent.talk);
    var inSession = !!mic.session;
    var talk = {
      entity: ent.talk || null, present: !!ent.talk, available: btnUp(talkSt),
      // Không bấm được khi: nút không sẵn sàng (mic chưa nối / đã tắt) hoặc đang có phiên.
      enabled: btnUp(talkSt) && !inSession,
      reason: !btnUp(talkSt) ? "no_mic" : (inSession ? "busy" : null),
    };
    var endSt = stateOf(hass, ent.end_talk);
    var end = { entity: ent.end_talk || null, present: !!ent.end_talk, visible: inSession && btnUp(endSt) };
    var sp = stateOf(hass, ent.speaker);
    var sa = (sp && sp.attributes) || {};
    var ms = sp ? sp.state : null;
    var music = {
      entity: ent.speaker || null, present: !!ent.speaker, available: isUp(sp), state: ms,
      title: sa.media_title || null,
      canPause: isUp(sp) && (ms === "playing" || ms === "buffering"),
      canPlay: isUp(sp) && ms === "paused",
    };
    var mst = stateOf(hass, ent.mute);
    var mute = { entity: ent.mute || null, present: !!ent.mute, available: isUp(mst),
                 on: isUp(mst) ? mst.state === "on" : null };
    var wst = stateOf(hass, ent.wake);
    var wa = (wst && wst.attributes) || {};
    var wake = { entity: ent.wake || null, present: !!ent.wake, on: !!wst && wst.state === "on",
                 pending: wa.phia_loa === "CHO_PHIA_LOA", mode: wa.che_do || mic.mode };
    return {
      found: !!(ent.talk || ent.mic_status || ent.speaker), mic: mic, talk: talk, end: end,
      music: music, mute: mute, wake: wake, deviceId: ent.device_id,
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
    "button[disabled]{opacity:.45;cursor:not-allowed}",
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

    _call(domain, service, data) { this._hass.callService(domain, service, data); }

    _render() {
      if (!this._hass || !this.shadowRoot) return;
      var m = buildModel(this._hass, this._config);
      var t = TEXT[lang(this._hass)];
      // Dựng lại khi bộ thực thể (hoặc ngôn ngữ) đổi — kể cả lúc đầu chưa thấy thực thể nào rồi mới
      // có (HA khởi động / đăng ký thực thể đến muộn): không bao giờ cập nhật lên DOM chưa dựng.
      var sig = JSON.stringify([m.found, m.mic.entity, m.talk.entity, m.end.entity, m.music.entity,
        m.mute.entity, m.wake.entity, m.showEq, lang(this._hass)]);
      if (sig !== this._sig) {
        this._sig = sig;
        this._eq = null;
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
        '<div class="row"><button data-talk></button><button class="sec" data-end style="display:none">' +
        esc(t.end) + "</button></div>" +
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
      on("[data-talk]", function () {
        var m = now();
        if (m.talk.enabled) self._call("button", "press", { entity_id: m.talk.entity });
      });
      on("[data-end]", function () {
        var m = now();
        if (m.end.visible) self._call("button", "press", { entity_id: m.end.entity });
      });
      on("[data-pause]", function () {
        var m = now();
        if (m.music.canPause) self._call("media_player", "media_pause", { entity_id: m.music.entity });
      });
      on("[data-play]", function () {
        var m = now();
        if (m.music.canPlay) self._call("media_player", "media_play", { entity_id: m.music.entity });
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

    _update(m, t) {
      var root = this.shadowRoot;
      if (!m.found) return;
      var q = function (s) { return root.querySelector(s); };
      q("[data-mic]").dataset.status = m.mic.status;
      q("[data-mic-text]").textContent = t[m.mic.status];
      q("[data-mic-tip]").textContent = t[m.mic.status + "_tip"] || "";
      var talk = q("[data-talk]");
      talk.textContent = m.talk.reason === "busy" ? t.busy : t.talk;
      talk.disabled = !m.talk.enabled;
      talk.title = m.talk.reason ? t[m.talk.reason] : "";
      q("[data-end]").style.display = m.end.visible ? "" : "none";
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
      if (this._eq) this._eq.hass = this._hass;
    }
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
