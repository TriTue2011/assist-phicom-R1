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
        return dongGoi(utf8("{\"type\":\"den_trang_thai\",\"san_sang\":" + (sanSang ? "true" : "false") + "}"));
    }

    static byte[] utf8(String s) {
        try {
            return s.getBytes("UTF-8");
        } catch (UnsupportedEncodingException e) {
            throw new RuntimeException(e);
        }
    }
}
