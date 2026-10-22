/* r1-eq-card — thẻ Lovelace chỉnh EQ / bass / loudness cho loa Phicomm R1 (tích hợp r1_speaker).
 *
 * Thẻ KHÔNG gọi loa trực tiếp: chỉ đọc trạng thái các thực thể của tích hợp và ghi qua dịch vụ
 * HA (number.set_value, switch.turn_on/off, select.select_option). Tích hợp tự nạp tệp này
 * (đường /r1_speaker/r1-eq-card.js), không cần thêm tài nguyên Lovelace bằng tay.
 *
 * Cấu hình tối thiểu:        type: custom:r1-eq-card
 * Nhiều loa / chỉ định loa:  device_id: <mã thiết bị>
 * Chỉ định thực thể tay:     entities: { eq_enable: switch.x, bass: ..., loudness: ...,
 *                              bass_strength: ..., loudness_gain: ..., eq_preset: ...,
 *                              volume: ..., bands: [number.b0, ... number.b4] }
 *
 * Lệnh nào đã xác nhận bằng ghi thật trên loa: thuộc tính `confirmed` của thực thể (do tích hợp
 * đặt). Thẻ gắn nhãn «chưa xác nhận» ở mọi điều khiển có confirmed=false.
 */
(function () {
  "use strict";
  var BUILD = "2026-10-22.8";

  var PLATFORM = "r1_speaker";
  var N_BANDS = 5;
  var TEXT = {
    vi: {
      title: "Loa R1 — Âm thanh", eq: "Bộ cân bằng (EQ)", bass: "Bass", loudness: "Loudness",
      bass_strength: "Cường độ bass", loudness_gain: "Độ lợi loudness", preset: "Preset",
      volume: "Âm lượng", params: "Thông số", range: "Dải mỗi băng", no_preset: "Đang chỉnh tay",
      unconfirmed: "chưa xác nhận", unconfirmed_tip: "Lệnh này chưa được thử ghi lên loa thật.",
      preset_tip: "Chọn preset chưa bật: loa chưa có lệnh đặt preset đã xác nhận.",
      offline: "Loa không phản hồi", none: "Không tìm thấy thực thể r1_speaker nào.",
      unit: "mB",
    },
    en: {
      title: "R1 speaker — Sound", eq: "Equalizer (EQ)", bass: "Bass", loudness: "Loudness",
      bass_strength: "Bass strength", loudness_gain: "Loudness gain", preset: "Preset",
      volume: "Volume", params: "Parameters", range: "Range per band", no_preset: "Manual",
      unconfirmed: "unconfirmed", unconfirmed_tip: "This command has not been tried on a real speaker.",
      preset_tip: "Preset selection is disabled: no confirmed preset command on the speaker yet.",
      offline: "Speaker not responding", none: "No r1_speaker entity found.",
      unit: "mB",
    },
  };

  function lang(hass) {
    var l = ((hass && (hass.language || (hass.locale && hass.locale.language))) || "vi");
    return l.toLowerCase().indexOf("vi") === 0 ? "vi" : "en";
  }

  /* Thứ tự băng khi thực thể unavailable (mất thuộc tính `band`): suy ra từ tần số trong
   * entity_id, vd ..._eq_60_hz, ..._eq_3_6_khz. Không đọc được thì để cuối. */
  function freqFromId(id) {
    var m = /eq_(\d+)(?:_(\d+))?_(k?hz)/i.exec(id || "");
    if (!m) return Infinity;
    var v = parseFloat(m[1] + (m[2] ? "." + m[2] : ""));
    return m[3].toLowerCase() === "khz" ? v * 1000 : v;
  }

  function stateOf(hass, id) {
    return id && hass && hass.states ? hass.states[id] : undefined;
  }

  function isUp(st) {
    return !!st && st.state !== "unavailable" && st.state !== "unknown";
  }

  /* Tìm thực thể của tích hợp. `config.entities` đè lên tìm tự động. */
  function discover(hass, config) {
    var reg = (hass && hass.entities) || {};
    var want = config.device_id || null;
    var mine = Object.keys(reg).filter(function (id) {
      var e = reg[id];
      return e && e.platform === PLATFORM && (!want || e.device_id === want);
    });
    if (!want && mine.length) {
      // Nhiều loa mà không chỉ định: lấy thiết bị đầu tiên theo mã để kết quả ổn định.
      var devs = mine.map(function (id) { return reg[id].device_id; }).sort();
      mine = mine.filter(function (id) { return reg[id].device_id === devs[0]; });
    }
    var by = function (domain, key) {
      return mine.filter(function (id) {
        return id.split(".")[0] === domain && reg[id].translation_key === key;
      }).sort();
    };
    var bands = by("number", "eq_band");
    return {
      eq_enable: by("switch", "eq_enable")[0], bass: by("switch", "bass")[0],
      loudness: by("switch", "loudness")[0], bass_strength: by("number", "bass_strength")[0],
      loudness_gain: by("number", "loudness_gain")[0], volume: by("number", "volume")[0],
      eq_preset: by("select", "eq_preset")[0], bands: bands,
    };
  }

  function control(hass, id) {
    var st = stateOf(hass, id);
    var a = (st && st.attributes) || {};
    return {
      entity: id || null,
      present: !!id,
      available: isUp(st),
      state: st ? st.state : null,
      // thiếu thuộc tính thì coi là CHƯA xác nhận (an toàn hơn coi là đã xác nhận)
      confirmed: a.confirmed === true,
      min: a.min !== undefined ? Number(a.min) : undefined,
      max: a.max !== undefined ? Number(a.max) : undefined,
      step: a.step !== undefined ? Number(a.step) : undefined,
      attributes: a,
    };
  }

  function numberControl(hass, id) {
    var c = control(hass, id);
    c.value = c.available ? Number(c.state) : null;
    return c;
  }

  function switchControl(hass, id) {
    var c = control(hass, id);
    c.on = c.available ? c.state === "on" : null;
    return c;
  }

  /* Dữ liệu thuần cho thẻ (kiểm được bằng Node): không đụng DOM. */
  function buildModel(hass, config) {
    config = config || {};
    var ent = discover(hass, config);
    var o = config.entities || {};
    Object.keys(o).forEach(function (k) { if (o[k]) ent[k] = o[k]; });
    var bandIds = (ent.bands || []).slice(0, N_BANDS);
    var bands = bandIds.map(function (id) {
      var c = numberControl(hass, id);
      c.band = c.attributes.band !== undefined ? Number(c.attributes.band) : null;
      c.label = c.attributes.label || null;
      return c;
    });
    if (bands.every(function (b) { return b.band !== null; })) {
      bands.sort(function (a, b) { return a.band - b.band; });
    } else {
      bands.sort(function (a, b) { return freqFromId(a.entity) - freqFromId(b.entity); });
    }
    var preset = control(hass, ent.eq_preset);
    var pa = preset.attributes;
    preset.options = pa.options || [];
    preset.current = preset.available && preset.state !== "unknown" ? preset.state : null;
    // Chọn preset chỉ bật khi tích hợp báo có lệnh đã xác nhận (selectable) — không đoán.
    preset.selectable = pa.selectable === true;
    var model = {
      found: !!(bands.length || ent.eq_enable || ent.bass || ent.loudness),
      bands: bands,
      eq: switchControl(hass, ent.eq_enable),
      bass: switchControl(hass, ent.bass),
      loudness: switchControl(hass, ent.loudness),
      bassStrength: numberControl(hass, ent.bass_strength),
      loudnessGain: numberControl(hass, ent.loudness_gain),
      volume: numberControl(hass, ent.volume),
      preset: preset,
    };
    var all = [model.eq, model.bass, model.loudness, model.bassStrength, model.loudnessGain,
               model.volume].concat(bands);
    model.offline = model.found && all.filter(function (c) { return c.present; })
      .every(function (c) { return !c.available; });
    // Khoảng giá trị chung của các băng: lấy của loa báo, không mã cứng.
    var live = bands.filter(function (b) { return b.min !== undefined && b.max !== undefined; });
    model.bandMin = live.length ? live[0].min : null;
    model.bandMax = live.length ? live[0].max : null;
    return model;
  }

  /* ── Giao diện ─────────────────────────────────────────────────────────── */

  var CSS = [
    ":host{display:block}",
    "ha-card{padding:12px 16px}",
    "h2{margin:0 0 8px;font-size:1.1em}",
    ".row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:6px 0}",
    ".bands{display:flex;justify-content:space-evenly;align-items:flex-end;margin:8px 0}",
    ".band{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1}",
    ".band input{writing-mode:vertical-lr;direction:rtl;width:24px;height:140px;margin:0}",
    ".val{font-size:.8em;min-height:1.2em}",
    ".lbl{font-size:.75em;opacity:.7}",
    ".badge{font-size:.65em;border:1px solid var(--warning-color,#f5a623);",
    "color:var(--warning-color,#f5a623);border-radius:8px;padding:0 5px;margin-left:6px}",
    ".slider{display:flex;align-items:center;gap:8px;flex:1;justify-content:flex-end}",
    ".slider input{flex:1;max-width:60%}",
    ".warn{color:var(--error-color,#db4437);font-size:.85em;margin-bottom:6px}",
    "section{margin-top:10px;border-top:1px solid var(--divider-color,#ddd);padding-top:6px}",
    "[disabled]{opacity:.5}",
  ].join("");

  function sign(v) { return v > 0 ? "+" + v : String(v); }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  class R1EqCard extends (typeof HTMLElement !== "undefined" ? HTMLElement : Object) {
    constructor() {
      super();
      this._config = {};
      this._sig = "";
      this._drag = false;
      if (this.attachShadow) this.attachShadow({ mode: "open" });
    }

    static getStubConfig() { return {}; }

    setConfig(config) {
      this._config = config || {};
      this._sig = "";
      if (this._hass) this._render();
    }

    getCardSize() { return 6; }

    set hass(hass) {
      this._hass = hass;
      this._render();
    }

    _call(domain, service, data) {
      this._hass.callService(domain, service, data);
    }

    _render() {
      if (!this._hass || !this.shadowRoot) return;
      var m = buildModel(this._hass, this._config);
      var t = TEXT[lang(this._hass)];
      var sig = JSON.stringify([m.bands.map(function (b) { return b.entity; }), m.eq.entity,
        m.bass.entity, m.loudness.entity, m.bassStrength.entity, m.loudnessGain.entity,
        m.volume.entity, m.preset.entity, m.preset.options, m.preset.selectable, m.offline,
        m.found, lang(this._hass), m.bands.map(function (b) { return b.confirmed; })]);
      if (sig !== this._sig) {
        this._sig = sig;
        this.shadowRoot.innerHTML = "<style>" + CSS + "</style>" + this._html(m, t);
        this._bind(m);
      }
      this._update(m, t);
    }

    _badge(c, t) {
      return c.present && !c.confirmed
        ? '<span class="badge" title="' + esc(t.unconfirmed_tip) + '">' + esc(t.unconfirmed) + "</span>"
        : "";
    }

    _html(m, t) {
      if (!m.found) return '<ha-card><div class="warn">' + esc(t.none) + "</div></ha-card>";
      var self = this;
      var bands = m.bands.map(function (b, i) {
        var min = b.min !== undefined ? b.min : "", max = b.max !== undefined ? b.max : "";
        return '<div class="band"><span class="val" data-v="b' + i + '"></span>' +
          '<input type="range" data-b="' + i + '" min="' + min + '" max="' + max +
          '" step="' + (b.step || 10) + '" orient="vertical">' +
          '<span class="lbl">' + esc(b.label || "") + "</span>" + self._badge(b, t) + "</div>";
      }).join("");
      var sw = function (key, c, label) {
        return c.present
          ? '<div class="row"><span>' + esc(label) + self._badge(c, t) +
            '</span><ha-switch data-s="' + key + '"></ha-switch></div>' : "";
      };
      var sl = function (key, c, label) {
        return c.present
          ? '<div class="row"><span>' + esc(label) + self._badge(c, t) + '</span>' +
            '<div class="slider"><input type="range" data-n="' + key + '" min="' + (c.min !== undefined ? c.min : 0) +
            '" max="' + (c.max !== undefined ? c.max : 100) + '" step="' + (c.step || 1) +
            '"><span class="val" data-v="' + key + '"></span></div></div>' : "";
      };
      var preset = "";
      if (m.preset.present) {
        preset = '<div class="row"><span>' + esc(t.preset) + self._badge(m.preset, t) +
          '</span><select data-p="1"' + (m.preset.selectable ? "" : ' disabled title="' + esc(t.preset_tip) + '"') + ">" +
          '<option value="">' + esc(t.no_preset) + "</option>" +
          m.preset.options.map(function (o) { return '<option value="' + esc(o) + '">' + esc(o) + "</option>"; }).join("") +
          "</select></div>";
      }
      return '<ha-card><h2>' + esc(t.title) + "</h2>" +
        '<div class="warn" data-off style="display:none">' + esc(t.offline) + "</div>" +
        sw("eq", m.eq, t.eq) + '<div class="bands">' + bands + "</div>" +
        '<section>' + sw("bass", m.bass, t.bass) + sl("bassStrength", m.bassStrength, t.bass_strength) +
        sw("loudness", m.loudness, t.loudness) + sl("loudnessGain", m.loudnessGain, t.loudness_gain) +
        "</section><section><div class=\"lbl\">" + esc(t.params) + "</div>" + sl("volume", m.volume, t.volume) +
        preset + '<div class="row"><span>' + esc(t.range) + '</span><span class="val" data-v="range"></span></div></section>' +
        "</ha-card>";
    }

    _bind(m) {
      var root = this.shadowRoot, self = this;
      var band = function (inp) { return m.bands[Number(inp.dataset.b)]; };
      root.querySelectorAll("input[data-b]").forEach(function (inp) {
        inp.addEventListener("input", function () {
          self._drag = true;
          var v = root.querySelector('[data-v="b' + inp.dataset.b + '"]');
          if (v) v.textContent = sign(Number(inp.value));
        });
        inp.addEventListener("change", function () {
          self._drag = false;
          self._call("number", "set_value", { entity_id: band(inp).entity, value: Number(inp.value) });
        });
      });
      root.querySelectorAll("input[data-n]").forEach(function (inp) {
        var c = m[inp.dataset.n];
        inp.addEventListener("input", function () {
          self._drag = true;
          var v = root.querySelector('[data-v="' + inp.dataset.n + '"]');
          if (v) v.textContent = inp.value;
        });
        inp.addEventListener("change", function () {
          self._drag = false;
          self._call("number", "set_value", { entity_id: c.entity, value: Number(inp.value) });
        });
      });
      root.querySelectorAll("[data-s]").forEach(function (el) {
        var c = m[el.dataset.s];
        el.addEventListener("change", function () {
          self._call("switch", el.checked ? "turn_on" : "turn_off", { entity_id: c.entity });
        });
      });
      var sel = root.querySelector("select[data-p]");
      if (sel) {
        sel.addEventListener("change", function () {
          if (sel.value) self._call("select", "select_option", { entity_id: m.preset.entity, option: sel.value });
        });
      }
    }

    _update(m, t) {
      var root = this.shadowRoot;
      if (!m.found) return;
      var off = root.querySelector("[data-off]");
      if (off) off.style.display = m.offline ? "" : "none";
      if (!this._drag) {
        root.querySelectorAll("input[data-b]").forEach(function (inp) {
          var b = m.bands[Number(inp.dataset.b)];
          inp.disabled = !b.available;
          if (b.available) inp.value = b.value;
          var v = root.querySelector('[data-v="b' + inp.dataset.b + '"]');
          if (v) v.textContent = b.available ? sign(b.value) : "—";
        });
        root.querySelectorAll("input[data-n]").forEach(function (inp) {
          var c = m[inp.dataset.n];
          inp.disabled = !c.available;
          if (c.available) inp.value = c.value;
          var v = root.querySelector('[data-v="' + inp.dataset.n + '"]');
          if (v) v.textContent = c.available ? String(c.value) : "—";
        });
      }
      root.querySelectorAll("[data-s]").forEach(function (el) {
        var c = m[el.dataset.s];
        el.disabled = !c.available;
        el.checked = c.on === true;
      });
      var sel = root.querySelector("select[data-p]");
      if (sel) sel.value = m.preset.current && m.preset.options.indexOf(m.preset.current) >= 0 ? m.preset.current : "";
      var r = root.querySelector('[data-v="range"]');
      if (r) r.textContent = m.bandMin !== null ? sign(m.bandMin) + " … " + sign(m.bandMax) + " " + t.unit : "—";
    }
  }

  // r1-card dựng thẻ từ lớp này (nạp bằng URL mới mỗi lần mở trang), không phụ thuộc bản cũ còn
  // trong bộ nhớ đệm của trình duyệt dưới URL cố định.
  if (typeof window !== "undefined") {
    window.R1_THE = window.R1_THE || {};
    window.R1_THE.eq = { lop: R1EqCard, build: BUILD };
  }

  if (typeof customElements !== "undefined" && !customElements.get("r1-eq-card")) {
    customElements.define("r1-eq-card", R1EqCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "r1-eq-card", name: "Phicomm R1 — EQ",
      description: "Chỉnh EQ 5 băng, bass, loudness của loa Phicomm R1 (tích hợp r1_speaker).",
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { buildModel: buildModel, discover: discover, freqFromId: freqFromId, TEXT: TEXT };
  }
})();
