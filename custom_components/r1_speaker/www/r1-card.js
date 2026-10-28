/* R1 — thẻ gộp có tab nhỏ: Đàm thoại / EQ / Chức năng / Cài đặt. Chỉ hiện một phần mỗi lúc, cách YouTube chia tab.
 * Cấu hình: type: custom:r1-card (không tham số).
 *
 * Ba thẻ con được nạp bằng ĐƯỜNG DẪN đổi MỖI LẦN MỞ TRANG (/r1_speaker/b/<thời gian>/...) rồi đăng ký
 * dưới tên riêng (r1-*-card-n): trình duyệt/ứng dụng HA/proxy giữ bản cũ của URL cố định hàng giờ (có
 * lớp đệm còn bỏ qua cả tham số ?...), nên dùng thẳng ``<r1-talk-card>`` thì sửa xong vẫn thấy bản cũ.
 * Nếu vẫn nhận bản cũ thì dùng tạm thẻ cũ và ghi rõ ở cuối thẻ. */
const BUILD = "2026-10-28.1";

const TABS = [
  { id: "talk", tag: "r1-talk-card-n", ten: "Đàm thoại", cfg: { show_eq: false } },
  { id: "eq", tag: "r1-eq-card-n", ten: "EQ", cfg: {} },
  { id: "chucnang", tag: "r1-chucnang-card-n", ten: "Chức năng", cfg: {} },
  { id: "settings", tag: "r1-settings-card-n", ten: "Cài đặt", cfg: { gop: true } },
];

let napXong = null;
/** Nạp ba thẻ con (một lần mỗi trang). ``window.R1_NAP`` chỉ để test thay cho import thật. */
function nap() {
  if (!napXong) {
    const nap1 = window.R1_NAP || ((url) => import(url));
    const t = Date.now();
    // Mỗi thẻ con nạp độc lập: một thẻ hỏng không làm mất cả thẻ gộp.
    napXong = Promise.all(TABS.map((x) =>
      Promise.resolve().then(() => nap1(`/r1_speaker/b/${t}/r1-${x.id}-card.js`)).catch(() => null)
    )).then(() => {
      TABS.forEach((x) => {
        const goc = window.R1_THE && window.R1_THE[x.id];
        if (goc) {                                   // bản mới nạp được
          // Tên DUY NHẤT mỗi lần nạp: bản cũ còn trong bộ nhớ của trang (ứng dụng HA giữ trang rất lâu) không che được bản mới.
          x.tag = x.tag + "-" + t;
          customElements.define(x.tag, class extends goc.lop {});
          x.tuoi = true;
        } else if (customElements.get("r1-" + x.id + "-card")) {
          x.tag = "r1-" + x.id + "-card";            // đường lui: thẻ cũ đã đăng ký sẵn
          x.tuoi = false;
        } else {
          throw new Error("thẻ con " + x.id + " không nạp được");
        }
      });
    });
  }
  return napXong;
}

class R1Card extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    if (this._root) return;
    this._root = this.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = [
      ":host{display:block}",
      ".tabs{display:flex;gap:6px;overflow-x:auto;padding:4px 2px 8px}",
      ".tab{flex:0 0 auto;border:0;border-radius:16px;padding:6px 12px;font-size:.85rem;cursor:pointer;background:var(--secondary-background-color,#2a2a2a);color:var(--primary-text-color,#fff)}",
      ".tab.sel{background:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}",
      ".ver{font-size:.7rem;opacity:.5;padding:2px 4px}",
      ".tieude{font-size:1.1rem;font-weight:600;padding:4px 4px 2px}",
    ].join("");
    this._root.appendChild(style);
    // Tên loa và hàng tab LUÔN hiện; chỉ NỘI DUNG (Đàm thoại / EQ / Cài đặt-âm thanh) đóng sẵn tới khi bấm tab.
    const head = document.createElement("div");
    head.className = "tieude";
    head.textContent = "Loa R1";
    this._root.appendChild(head);
    this._head = head;
    this._body = document.createElement("div");
    this._root.appendChild(this._body);
    this._parts = {};
    this._btn = {};
    this._sel = null;
    this._san = nap().then(() => this._dung(), (loi) => this._loi(loi));
  }
  _dung() {
    const bar = document.createElement("div");
    bar.className = "tabs";
    TABS.forEach((t) => {
      const b = document.createElement("button");
      b.className = "tab";
      b.textContent = t.ten;
      b.addEventListener("click", () => this._chon(t.id));
      bar.appendChild(b);
      this._btn[t.id] = b;
      const el = document.createElement(t.tag);
      el.setConfig(this._cfgCon(t));
      el.style.display = "none";
      this._body.appendChild(el);
      this._parts[t.id] = el;
    });
    this._body.insertBefore(bar, this._body.firstChild);
    this._loaBar = document.createElement("div");
    this._loaBar.className = "tabs loa";
    this._body.insertBefore(this._loaBar, this._body.firstChild);
    const ver = document.createElement("div");
    ver.className = "ver";
    const cu = TABS.filter((x) => !x.tuoi).map((x) => x.id);
    const bd = (id) => (((window.R1_THE || {})[id] || {}).build || "?");
    ver.textContent = "r1-card " + BUILD + " · đàm thoại " + bd("talk") + " · EQ " + bd("eq") + " · cài đặt " + bd("settings") + " · chức năng " + bd("chucnang") +
      (cu.length ? " · DÙNG BẢN CŨ của: " + cu.join(", ") + " (lớp đệm chặn bản mới)" : "");
    this._body.appendChild(ver);
    if (this._hass) this._gan(this._hass);
  }
  _loi(loi) {
    const d = document.createElement("div");
    d.className = "ver";
    d.textContent = "Không nạp được thẻ R1: " + loi;
    this._body.appendChild(d);
  }
  _chon(id) {
    // Bấm tab đang mở thì đóng lại; bấm tab khác thì mở tab đó (mặc định đều đóng)
    const mo = this._sel === id ? null : id;
    this._sel = mo;
    Object.keys(this._parts).forEach((k) => {
      this._parts[k].style.display = k === mo ? "" : "none";
      this._btn[k].classList.toggle("sel", k === mo);
    });
    this._hienLoa();
  }
  /** Cấu hình thẻ con. ``device_id`` trong cấu hình thẻ gộp ghim MỘT loa cho cả ba tab; không ghim mà có nhiều loa thì EQ và
   * Cài đặt theo loa đang chọn ở hàng chọn loa. Đàm thoại giữ cách chọn riêng của nó. */
  _cfgCon(t) {
    const dev = this._config.device_id || (t.id !== "talk" && this._dev) || null;
    return { type: "custom:" + t.tag, ...t.cfg, ...(dev ? { device_id: dev } : {}) };
  }
  /** Các loa R1 của HA: [{id, ten}], xếp theo mã thiết bị (cùng thứ tự các thẻ con dùng để chọn loa đầu). Tên là tên thiết bị
   * trong HA (đổi tên ở trang thiết bị thì thẻ theo); trùng tên thì thêm số thứ tự. */
  _loa(hass) {
    const reg = (hass && hass.entities) || {};
    const ids = [...new Set(Object.values(reg).filter((e) => e && e.platform === "r1_speaker" && e.device_id).map((e) => e.device_id))].sort();
    const ten = ids.map((id) => {
      const d = (hass.devices || {})[id] || {};
      return d.name_by_user || d.name || "Phicomm R1";
    });
    return ids.map((id, i) => ({ id, ten: ten.filter((x) => x === ten[i]).length > 1 ? ten[i] + " (" + (i + 1) + ")" : ten[i] }));
  }
  /* Hàng chọn MỘT loa (cho EQ, Chức năng, Cài đặt) ẩn khi mở tab Đàm thoại: tab đó có hàng chọn NHIỀU loa của riêng nó, hai hàng sẽ chồng nhau. */
  _hienLoa() { if (this._loaBar) this._loaBar.style.display = this._coLoa && this._sel !== "talk" ? "" : "none"; }
  _capNhatLoa(hass) {
    if (!this._loaBar) return;
    const ds = this._config.device_id ? [] : this._loa(hass);
    if (ds.length < 2) ds.length = 0;
    if (ds.length && !ds.some((d) => d.id === this._dev)) this._dev = ds[0].id;
    const sig = ds.map((d) => d.id + "|" + d.ten).join("\n") + "#" + this._dev;
    if (sig === this._loaSig) return;
    const doi = ds.length && this._devCon !== this._dev;       // loa đang chọn chưa được truyền cho thẻ con
    this._loaSig = sig;
    this._devCon = ds.length ? this._dev : undefined;
    this._loaBar.textContent = "";
    this._coLoa = ds.length > 0;
    this._hienLoa();
    ds.forEach((d) => {
      const b = document.createElement("button");
      b.className = "tab" + (d.id === this._dev ? " sel" : "");
      b.textContent = d.ten;
      b.addEventListener("click", () => { this._dev = d.id; this._capNhatLoa(this._hass); });
      this._loaBar.appendChild(b);
    });
    if (doi) TABS.filter((t) => t.id !== "talk").forEach((t) => this._parts[t.id].setConfig(this._cfgCon(t)));
  }
  _gan(hass) { Object.values(this._parts).forEach((p) => (p.hass = hass)); this._capNhatLoa(hass); }
  set hass(hass) { this._hass = hass; this._gan(hass); }
  getCardSize() { return 10; }
}
if (!customElements.get("r1-card")) customElements.define("r1-card", R1Card);
window.customCards = window.customCards || [];
window.customCards.push({ type: "r1-card", name: "R1 (gộp, tab)", description: "Đàm thoại, EQ, cài đặt loa R1 trong một thẻ có tab" });
