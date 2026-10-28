package vn.r1.bodam;

import java.io.UnsupportedEncodingException;

/** Ma hoa khung giao thuc: 4 byte do dai big-endian + payload. Logic thuan, khong phu thuoc Android. */
public final class Khung {
    private Khung() {}

    public static byte[] dongGoi(byte[] payload) {
        byte[] out = new byte[4 + payload.length];
        out[0] = (byte) ((payload.length >>> 24) & 0xFF);
        out[1] = (byte) ((payload.length >>> 16) & 0xFF);
        out[2] = (byte) ((payload.length >>> 8) & 0xFF);
        out[3] = (byte) (payload.length & 0xFF);
        System.arraycopy(payload, 0, out, 4, payload.length);
        return out;
    }

    public static byte[] hello(String khoa) {
        String k = khoa == null ? "" : khoa.replace("\\", "\\\\").replace("\"", "\\\"");
        return dongGoi(utf8("{\"type\":\"hello\",\"version\":1,\"key\":\"" + k + "\"}"));
    }

    public static byte[] end() {
        return dongGoi(utf8("{\"type\":\"end\"}"));
    }

    /** Bao HA may chu den (quyen shell) tren loa co chay khong. */
    public static byte[] trangThaiDen(boolean sanSang) {
        return dongGoi(utf8("{\"type\":\"den_trang_thai\",\"san_sang\":" + (sanSang ? "true" : "false") + ",\"che_do\":\"firmware\"}"));
    }

    /** Bao HA muc am luong nhac hien tai va muc toi da cua loa. */
    public static byte[] amLuong(int muc, int toiDa) {
        return dongGoi(utf8("{\"type\":\"am_luong_trang_thai\",\"muc\":" + muc + ",\"toi_da\":" + toiDa + "}"));
    }

    /** Thoat chuoi cho JSON: dau nhay kep, gach cheo nguoc, xuong dong, ky tu dieu khien (< 0x20). */
    static String thoat(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c);
            }
        }
        return b.toString();
    }

    /** Thong tin he thong cua loa dang van ban chia khoi "---ten" (HA phan tich bang cung ham voi duong ADB). */
    public static byte[] heThong(String txt) {
        return dongGoi(utf8("{\"type\":\"he_thong\",\"txt\":\"" + thoat(txt == null ? "" : txt) + "\"}"));
    }

    /** Bao HA Bluetooth cua loa dang bat/tat. */
    public static byte[] bluetooth(boolean bat) {
        return dongGoi(utf8("{\"type\":\"bluetooth_trang_thai\",\"bat\":" + (bat ? "true" : "false") + "}"));
    }

    /** Su kien phim: ma phim Android, xuong = true (nhan) / false (nha). HA tu nhan dien nhan don/doi/ba/giu. */
    public static byte[] phim(int ma, boolean xuong) {
        return dongGoi(utf8("{\"type\":\"phim\",\"ma\":" + ma + ",\"xuong\":" + (xuong ? "true" : "false") + "}"));
    }

    /** Phien ban APK va cac khau no ho tro: HA biet APK cu thieu gi thay vi gui lenh vao hu khong. */
    public static byte[] apk(String phienBan, String[] khaNang) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < khaNang.length; i++) { if (i > 0) b.append(','); b.append('"').append(thoat(khaNang[i])).append('"'); }
        return dongGoi(utf8("{\"type\":\"apk\",\"ver\":\"" + thoat(phienBan) + "\",\"kha_nang\":[" + b + "]}"));
    }

    static byte[] utf8(String s) {
        try {
            return s.getBytes("UTF-8");
        } catch (UnsupportedEncodingException e) {
            throw new RuntimeException(e);
        }
    }
}
