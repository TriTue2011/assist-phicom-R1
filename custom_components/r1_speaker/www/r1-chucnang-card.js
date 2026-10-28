/* r1-chucnang-card — tab CHỨC NĂNG của loa Phicomm R1 (tích hợp r1_speaker): bật/tắt kết nối phát nhạc và đặt báo thức.
 *
 * Thẻ KHÔNG gọi loa: chỉ đọc thực thể HA (switch DLNA/AirPlay/Bluetooth, button «Đóng ADB mạng», sensor «Lần báo thức kế tiếp»)
 * và gọi dịch vụ HA (switch.turn_on/off, button.press, r1_speaker.bao_thuc_dat/xoa/bat_tat/tat/hoan).
 * Cấu hình:  type: custom:r1-chucnang-card   (nhiều loa: device_id: <mã thiết bị>; thẻ gộp r1-card tự truyền)
 */
(function () {
  "use strict";
  var BUILD = "2026-10-28.1";
  var PLATFORM = "r1_speaker";
  var DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  var LINKS = ["dlna", "airplay", "bluetooth"];

  var TEXT = {
    vi: {
      none: "Không tìm thấy thực thể r1_speaker nào.",
      links: "Kết nối", dlna: "DLNA", airplay: "AirPlay", bluetooth: "Bluetooth", adb_dong: "Đóng ADB mạng…",
      adb_confirm: "Đóng ADB mạng của loa?\n\nƯU: không máy nào trong mạng nối được cổng 5555 (chặn botnet kiểu Kimwolf, kể cả quyền root).\nNHƯỢC: đèn tự do, cài ứng dụng, khởi động lại từ HA, thông tin hệ thống và công tắc Bluetooth ngừng chạy. Mic, âm lượng, phát nhạc, Dừng/Tắt tiếng vẫn dùng bình thường.\nMỞ LẠI: rút điện loa rồi cắm lại.",
      bt_unknown: "Bluetooth chưa đọc được trạng thái (cần ADB)",
      alarms: "Báo thức", hoan: "Hoãn (phút)", ringing: "Đang kêu", stop: "Tắt", snooze: "Hoãn", once: "Một lần", none_alarm: "Chưa có báo thức",
      on_off: "Bật/tắt", del: "Xoá", add: "Thêm", time: "Giờ", label: "Nhãn", say: "Lời nhắn", url: "Địa chỉ âm thanh",
      tts: "Đọc lời nhắn", media: "Phát âm thanh", reminder: "Nhắc nhở",
      days: { mon: "T2", tue: "T3", wed: "T4", thu: "T5", fri: "T6", sat: "T7", sun: "CN" },
    },
    en: {
      none: "No r1_speaker entity found.",
      links: "Connections", dlna: "DLNA", airplay: "AirPlay", bluetooth: "Bluetooth", adb_dong: "Close network ADB…",
      adb_confirm: "Close the speaker's network ADB?\n\nPRO: no machine on the network can reach port 5555 (blocks Kimwolf-style botnets, root included).\nCON: free-form lights, app install, reboot from HA, system info and the Bluetooth switch stop working. Mic, volume, playback, Stop/Mute keep working.\nRE-OPEN: unplug the speaker and plug it back in.",
      bt_unknown: "Bluetooth state unreadable (needs ADB)",
      alarms: "Alarms", hoan: "Snooze (min)", ringing: "Ringing", stop: "Stop", snooze: "Snooze", once: "Once", none_alarm: "No alarms yet",
      on_off: "On/off", del: "Delete", add: "Add", time: "Time", label: "Label", say: "Message", url: "Audio URL",
      tts: "Speak message", media: "Play audio", reminder: "Reminder",
      days: { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" },
    },
  };

  function lang(hass) {
    var l = ((hass && (hass.language || (hass.locale && hass.locale.language))) || "vi");
    return l.toLowerCase().indexOf("vi") === 0 ? "vi" : "en";
  }
  function stateOf(hass, id) { return id && hass && hass.states ? hass.states[id] : undefined; }
  function isUp(st) { return !!st && st.state !== "unavailable" && st.state !== "unknown"; }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* Loa của thẻ: ``device_id`` chỉ định; không có thì loa đầu theo mã thiết bị (cùng cách các thẻ con khác chọn). */
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
      dlna: by("switch", "dlna"), airplay: by("switch", "airplay"), bluetooth: by("switch", "bluetooth"),
      adb_dong: by("button", "dong_adb"), alarms: by("sensor", "bao_thuc_ke_tiep"), hoan: by("number", "hoan_phut"),
    };
  }

  /* Giờ kêu để hiện: ``gio`` (báo thức) hoặc giờ của lần kêu kế tiếp (nhắc nhở một lần chỉ có ``ke_tiep``). */
  function gioHienThi(a) {
    if (a.gio) return String(a.gio);
    var d = a.ke_tiep ? new Date(a.ke_tiep) : null;
    return d && !isNaN(d) ? ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2) : "—";
  }

  /* Dữ liệu thuần cho thẻ (kiểm được bằng Node): không đụng DOM. */
  function buildModel(hass, config) {
    var ent = discover(hass, config || {});
    var links = {};
    LINKS.forEach(function (k) {
      var cs = stateOf(hass, ent[k]);
      // «unknown» (ví dụ Bluetooth chưa đọc được qua ADB) vẫn cho bấm lệnh; chỉ «unavailable» mới khoá.
      var co = !!cs && cs.state !== "unavailable";
      links[k] = { entity: ent[k] || null, present: !!ent[k], available: co,
                   on: co ? (cs.state === "on" ? true : (cs.state === "off" ? false : null)) : null,
                   note: (cs && cs.attributes && cs.attributes.renderer) || "" };
    });
    var as = stateOf(hass, ent.alarms), at = (as && as.attributes) || {};
    var list = (Array.isArray(at.bao_thuc) ? at.bao_thuc : []).map(function (a) {
      return { id: String(a.id), gio: gioHienThi(a), ngay: Array.isArray(a.ngay) ? a.ngay : [], nhan: a.nhan || "",
               loai: a.loai || "tts", bat: a.bat !== false, luc: !a.gio };
    });
    var hs = stateOf(hass, ent.hoan);
    return {
      found: !!(ent.alarms || LINKS.some(function (k) { return ent[k]; }) || ent.adb_dong),
      links: links, adbDong: { entity: ent.adb_dong || null, present: !!ent.adb_dong },
      alarms: { entity: ent.alarms || null, present: !!ent.alarms, available: isUp(as), list: list, ringing: at.dang_keu || null,
                hoan: { entity: ent.hoan || null, present: !!ent.hoan, available: isUp(hs), value: isUp(hs) ? Number(hs.state) : null } },
    };
  }

  /* Hành động của người dùng → lệnh gọi dịch vụ HA (hoặc null). Không bao giờ gọi loa. */
  function makeCall(m, a) {
    var sid = m.alarms.entity;
    if (a.type === "link") {
      var c = m.links[a.key];
      return c && c.available ? ["switch", a.on ? "turn_on" : "turn_off", { entity_id: c.entity }] : null;
    }
    if (a.type === "adb_dong") return m.adbDong.present ? ["button", "press", { entity_id: m.adbDong.entity }] : null;
    if (a.type === "hoan_dat") {
      var n = Math.round(Number(a.value));
      return m.alarms.hoan.available && n >= 1 && n <= 120 ? ["number", "set_value", { entity_id: m.alarms.hoan.entity, value: n }] : null;
    }
    if (!sid) return null;
    if (a.type === "ring_stop") return ["r1_speaker", "bao_thuc_tat", { entity_id: sid }];
    if (a.type === "ring_snooze") return ["r1_speaker", "bao_thuc_hoan", { entity_id: sid }];
    if (a.type === "al_bat") return ["r1_speaker", "bao_thuc_bat_tat", { entity_id: sid, id: String(a.id), bat: a.on === true }];
    if (a.type === "al_xoa") return ["r1_speaker", "bao_thuc_xoa", { entity_id: sid, id: String(a.id) }];
    if (a.type === "al_them") {
      var f = a.form || {};
      if (!/^([01]?\d|2[0-3]):[0-5]\d$/.test(f.gio || "")) return null;
      var d = { entity_id: sid, gio: f.gio, ngay: (f.ngay || []).filter(function (x) { return DAYS.indexOf(x) >= 0; }),
                loai: f.loai === "media" ? "media" : "tts", bat: true };
      if (f.nhan) d.nhan = String(f.nhan).slice(0, 80);
      if (f.noi_dung) d.noi_dung = String(f.noi_dung).slice(0, 500);
      return ["r1_speaker", "bao_thuc_dat", d];
    }
    return null;
  }

  function initialForm() { return { gio: "07:00", ngay: [], nhan: "", loai: "tts", noi_dung: "" }; }

  function htmlLinks(m, t) {
    var any = LINKS.some(function (k) { return m.links[k].present; }) || m.adbDong.present;
    if (!any) return "";
    var h = "<section><b>" + esc(t.links) + "</b>";
    LINKS.forEach(function (k) {
      var c = m.links[k];
      if (!c.present) return;
      h += '<div class="row"><label>' + esc(t[k]) + '</label><input type="checkbox" data-link="' + k + '"' +
        (c.on === true ? " checked" : "") + (c.available ? "" : " disabled") + "></div>";
    });
    if (m.adbDong.present) h += '<div class="row"><button class="sec" data-adb-dong>' + esc(t.adb_dong) + "</button></div>";
    var nt = [];
    if (m.links.dlna.note) nt.push("DLNA: " + m.links.dlna.note);
    if (m.links.bluetooth.present && m.links.bluetooth.available && m.links.bluetooth.on === null) nt.push(t.bt_unknown);
    return h + (nt.length ? '<div class="note">' + esc(nt.join(" · ")) + "</div>" : "") + "</section>";
  }

  function icBtn(cls, attr, icon, label) {
    return '<button class="' + cls + '" ' + attr + ' title="' + esc(label) + '" aria-label="' + esc(label) + '"><ha-icon icon="' + icon + '"></ha-icon></button>';
  }

  function htmlAlarms(m, t, form) {
    if (!m.alarms.present) return "";
    var h = "<section><b>" + esc(t.alarms) + "</b>";
    var H = m.alarms.hoan;
    if (m.alarms.ringing) {
      h += '<div class="row ring"><span>' + esc(t.ringing) + "</span><span>" + icBtn("ctl main", "data-ring-stop", "mdi:alarm-off", t.stop) +
        icBtn("ctl", "data-ring-snooze", "mdi:alarm-snooze", t.snooze + (H.value ? " " + H.value : "")) + "</span></div>";
    }
    if (H.present) {
      h += '<div class="row"><label>' + esc(t.hoan) + '</label><input type="number" min="1" max="120" step="1" data-hoan value="' +
        esc(H.value === null ? "" : H.value) + '"' + (H.available ? "" : " disabled") + "></div>";
    }
    if (!m.alarms.list.length) h += '<div class="note">' + esc(t.none_alarm) + "</div>";
    m.alarms.list.forEach(function (a) {
      var ngay = a.ngay.length ? a.ngay.map(function (d) { return t.days[d] || d; }).join(" ") : t.once;
      h += '<div class="row al" data-al="' + esc(a.id) + '"><span class="gio">' + esc(a.gio) + '</span>' +
        '<span class="mt">' + esc(ngay + (a.nhan ? " · " + a.nhan : "")) + "</span>" +
        '<input type="checkbox" data-al-bat="' + esc(a.id) + '" title="' + esc(t.on_off) + '"' + (a.bat ? " checked" : "") + ">" +
        icBtn("ctl", 'data-al-xoa="' + esc(a.id) + '"', "mdi:delete", t.del) + "</div>";
    });
    h += '<div class="form"><div class="row"><input type="time" data-f="gio" value="' + esc(form.gio) + '" aria-label="' + esc(t.time) + '"></div><div class="days">';
    DAYS.forEach(function (d) {
      h += '<button class="day' + (form.ngay.indexOf(d) >= 0 ? " on" : "") + '" data-day="' + d + '" aria-pressed="' + (form.ngay.indexOf(d) >= 0 ? "true" : "false") + '">' + esc(t.days[d]) + "</button>";
    });
    h += '</div><div class="row"><input type="text" data-f="nhan" maxlength="80" placeholder="' + esc(t.label) + '" value="' + esc(form.nhan) + '">' +
      '<select data-f="loai"><option value="tts"' + (form.loai === "tts" ? " selected" : "") + ">" + esc(t.tts) + '</option><option value="media"' +
      (form.loai === "media" ? " selected" : "") + ">" + esc(t.media) + "</option></select></div>" +
      '<div class="row"><input type="text" data-f="noi_dung" maxlength="500" placeholder="' + esc(form.loai === "media" ? t.url : t.say) + '" value="' + esc(form.noi_dung) + '">' +
      icBtn("ctl main", "data-al-them", "mdi:plus", t.add) + "</div></div></section>";
    return h;
  }

  function renderHtml(m, t, form) {
    if (!m.found) return '<ha-card><div class="warn">' + esc(t.none) + "</div></ha-card>";
    return "<ha-card>" + htmlLinks(m, t) + htmlAlarms(m, t, form) + "</ha-card>";
  }

  var CSS = [
    ":host{display:block}", "ha-card{padding:12px 16px}",
    ".row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:6px 0}",
    "section{margin-top:10px;border-top:1px solid var(--divider-color,#ddd);padding-top:6px}", "section:first-child{margin-top:0;border-top:0;padding-top:0}",
    "button{font:inherit;padding:6px 14px;border-radius:8px;border:1px solid var(--divider-color,#bbb);background:transparent;color:inherit;cursor:pointer}",
    "button[disabled]{opacity:.45;cursor:not-allowed}", ".warn{color:var(--error-color,#db4437)}", ".note{font-size:.8em;opacity:.75}",
    ".ctl{display:grid;place-items:center;width:36px;height:36px;padding:0;border:0;border-radius:50%;color:var(--primary-text-color);background:transparent;--mdc-icon-size:22px}",
    ".ctl.main{width:42px;height:42px;margin:0 2px;color:var(--text-primary-color,#fff);background:var(--primary-color,#03a9f4);--mdc-icon-size:26px}",
    ".gio{font-weight:600;font-size:1.1em;min-width:3.4em}", ".mt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.9em;opacity:.85}",
    ".al{border-bottom:1px solid var(--divider-color,#eee)}", ".ring{color:var(--error-color,#db4437);font-weight:600}",
    ".form{margin-top:10px}", ".days{display:flex;gap:4px;flex-wrap:wrap;margin:6px 0}",
    ".day{padding:4px 9px;border-radius:14px;font-size:.85em}", ".day.on{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}",
    "input[type=text],input[type=time],input[type=number],select{font:inherit;padding:6px;border-radius:8px;border:1px solid var(--divider-color,#bbb);background:transparent;color:inherit}",
    "input[type=text]{flex:1;min-width:0}", "input[type=number]{width:5em}",
  ].join("");

  class R1ChucNangCard extends (typeof HTMLElement !== "undefined" ? HTMLElement : Object) {
    constructor() {
      super();
      this._config = {};
      this._form = initialForm();
      this._html = null;
      this._deferred = false;
      if (this.attachShadow) {
        this.attachShadow({ mode: "open" });
        var self = this;
        // Rời ô nhập thì dựng bản bị hoãn (HA cập nhật trạng thái liên tục, dựng lại sẽ xoá chữ đang gõ).
        this.shadowRoot.addEventListener("focusout", function () {
          if (self._deferred) setTimeout(function () { if (self._deferred) self._render(); }, 0);
        });
      }
    }

    static getStubConfig() { return {}; }
    setConfig(config) { this._config = config || {}; this._html = null; if (this._hass) this._render(); }
    getCardSize() { return 8; }
    set hass(hass) { this._hass = hass; this._render(); }

    _render() {
      if (!this._hass || !this.shadowRoot) return;
      var ae = this.shadowRoot.activeElement;
      if (this._html !== null && ae && /^(INPUT|SELECT)$/.test(ae.tagName)) { this._deferred = true; return; }
      this._deferred = false;
      var html = "<style>" + CSS + "</style>" + renderHtml(buildModel(this._hass, this._config), TEXT[lang(this._hass)], this._form);
      if (html === this._html) return;
      this._html = html;
      this.shadowRoot.innerHTML = html;
      this._bind();
    }

    _call(c) { if (c) this._hass.callService(c[0], c[1], c[2]); }

    _bind() {
      var root = this.shadowRoot, self = this, t = TEXT[lang(this._hass)];
      var now = function () { return buildModel(self._hass, self._config); };
      var dispatch = function (a) { self._call(makeCall(now(), a)); };
      var all = function (s, fn) { Array.prototype.forEach.call(root.querySelectorAll(s), fn); };
      all("[data-link]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "link", key: el.dataset.link, on: el.checked }); });
      });
      all("[data-adb-dong]", function (el) {
        el.addEventListener("click", function () { if (window.confirm(t.adb_confirm)) dispatch({ type: "adb_dong" }); });
      });
      all("[data-hoan]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "hoan_dat", value: el.value }); });
      });
      all("[data-ring-stop]", function (el) { el.addEventListener("click", function () { dispatch({ type: "ring_stop" }); }); });
      all("[data-ring-snooze]", function (el) { el.addEventListener("click", function () { dispatch({ type: "ring_snooze" }); }); });
      all("[data-al-bat]", function (el) {
        el.addEventListener("change", function () { dispatch({ type: "al_bat", id: el.dataset.alBat, on: el.checked }); });
      });
      all("[data-al-xoa]", function (el) {
        el.addEventListener("click", function () { dispatch({ type: "al_xoa", id: el.dataset.alXoa }); });
      });
      all("[data-f]", function (el) {                               // bản nháp biểu mẫu sống qua các lần dựng lại
        el.addEventListener("input", function () { self._form[el.dataset.f] = el.value; });
        el.addEventListener("change", function () {
          self._form[el.dataset.f] = el.value;
          if (el.dataset.f === "loai") { self._html = null; self._render(); }   // đổi ô gợi ý (lời nhắn / địa chỉ âm thanh)
        });
      });
      all("[data-day]", function (el) {
        el.addEventListener("click", function () {
          var i = self._form.ngay.indexOf(el.dataset.day);
          if (i >= 0) self._form.ngay.splice(i, 1); else self._form.ngay.push(el.dataset.day);
          self._html = null; self._render();
        });
      });
      all("[data-al-them]", function (el) {
        el.addEventListener("click", function () {
          var c = makeCall(now(), { type: "al_them", form: self._form });
          if (!c) return;
          self._call(c);
          self._form.nhan = ""; self._form.noi_dung = "";
          self._html = null; self._render();
        });
      });
    }
  }

  // r1-card dựng thẻ từ lớp này (nạp bằng URL mới mỗi lần mở trang), không phụ thuộc bản cũ còn trong bộ nhớ đệm.
  if (typeof window !== "undefined") {
    window.R1_THE = window.R1_THE || {};
    window.R1_THE.chucnang = { lop: R1ChucNangCard, build: BUILD };
  }
  if (typeof customElements !== "undefined" && !customElements.get("r1-chucnang-card")) {
    customElements.define("r1-chucnang-card", R1ChucNangCard);
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildModel: buildModel, makeCall: makeCall, renderHtml: renderHtml, TEXT: TEXT };
  }
})();
