package vn.r1.bodam;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Lenh phu HA gui xuong loa (khung JSON, da xac thuc bang khoa o hello): bat/tat Bluetooth, cau hinh phim, hoi thong tin he thong.
 * Dinh dang CO DINH (HA tao bang json.dumps tach gon) nen doc bang mau chat nhu LenhDieuKhien; khung la/hong bi bo qua, khong bao gio
 * nem loi hay lam dut ket noi.
 */
public final class LenhPhu {
    private LenhPhu() { }

    public static final int DAI_TOI_DA = 160;
    /** So ma phim toi da HA duoc nhan va khoang ma hop le (ma phim Android that deu nho hon 1000). */
    public static final int TOI_DA_PHIM = 16, MA_TOI_DA = 999;

    public interface Dich {
        /** null = da gui lenh; con lai = ly do. */
        String datBluetooth(boolean bat);
        void datPhim(int[] ma, boolean doTatCa);
        void baoHeThong();
    }

    private static final Pattern BT = Pattern.compile("^\\{\"type\":\"bluetooth\",\"bat\":(true|false)\\}$");
    private static final Pattern PHIM = Pattern.compile("^\\{\"type\":\"phim_cau_hinh\",\"ma\":\\[([0-9,]{0,90})\\],\"do\":(true|false)\\}$");
    private static final String HOI_HE_THONG = "{\"type\":\"he_thong_hoi\"}";

    public static boolean laLenhPhu(String khung) {
        if (khung == null || khung.length() > DAI_TOI_DA) return false;
        return HOI_HE_THONG.equals(khung) || BT.matcher(khung).matches() || PHIM.matcher(khung).matches();
    }

    /** null = da xu ly; con lai = ly do bo qua. */
    public static String xuLy(String khung, Dich dich) {
        try {
            if (!laLenhPhu(khung)) return "khong phai lenh phu";
            if (HOI_HE_THONG.equals(khung)) { dich.baoHeThong(); return null; }
            Matcher m = BT.matcher(khung);
            if (m.matches()) return dich.datBluetooth("true".equals(m.group(1)));
            m = PHIM.matcher(khung);
            if (!m.matches()) return "khong khop";
            int[] ma = docDanhSach(m.group(1));
            if (ma == null) return "danh sach ma phim khong hop le";
            dich.datPhim(ma, "true".equals(m.group(2)));
            return null;
        } catch (Throwable t) {
            return t.toString();
        }
    }

    /** "195,116" -> {195,116}; rong -> {}; sai (so ngoai 1..999, qua 16 so, dau phay thua) -> null. */
    static int[] docDanhSach(String s) {
        if (s.isEmpty()) return new int[0];
        String[] p = s.split(",", -1);
        if (p.length > TOI_DA_PHIM) return null;
        int[] ra = new int[p.length];
        for (int i = 0; i < p.length; i++) {
            if (p[i].isEmpty() || p[i].length() > 3) return null;
            int v = Integer.parseInt(p[i]);
            if (v < 1 || v > MA_TOI_DA) return null;
            ra[i] = v;
        }
        return ra;
    }
}
