package vn.r1.bodam;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Lenh dieu khien HA gui xuong loa qua ket noi mic (khung JSON, da xac thuc bang khoa o hello).
 * Hien chi co den nhac cua firmware: {"type":"den_nhac","ma":65,"gia_tri":50}. Dinh dang CO DINH
 * (HA tao bang json.dumps tach gon, dung thu tu khoa) nen doc bang mau chat thay vi parser JSON:
 * org.json trong android.jar chi la ban rong khi chay test thuan, va khung la/hong khong duoc
 * lam dut ket noi mic. Khong bao gio nem loi.
 */
public final class LenhDieuKhien {
    private LenhDieuKhien() { }

    /** Khung dieu khien toi da; dai hon coi la khong phai lenh. */
    public static final int DAI_TOI_DA = 128;

    public interface Dich {
        /** null = gui duoc; con lai = loi. */
        String guiDenNhac(int ma, int giaTri);
    }

    /** Dich that: tin toi dich vu msgcenter cua firmware. */
    public static final Dich THAT = new Dich() {
        @Override public String guiDenNhac(int ma, int giaTri) {
            return TrungTamTin.guiDenNhac(ma, giaTri);
        }
    };

    private static final Pattern DEN_NHAC = Pattern.compile(
            "^\\{\"type\":\"den_nhac\",\"ma\":(\\d{1,3}),\"gia_tri\":(\\d{1,3})\\}$");

    /** null = da xu ly (gui xong); con lai = ly do bo qua. Gia tri ngoai khoang bi chan o day. */
    public static String xuLy(String khung, Dich dich) {
        try {
            if (khung == null || khung.length() > DAI_TOI_DA) return "khung qua dai hoac rong";
            Matcher m = DEN_NHAC.matcher(khung);
            if (!m.matches()) return "khong phai lenh den_nhac";
            int ma = Integer.parseInt(m.group(1)), giaTri = Integer.parseInt(m.group(2));
            String loi = TrungTamTin.hopLeDenNhac(ma, giaTri);
            if (loi != null) return loi;
            return dich.guiDenNhac(ma, giaTri);
        } catch (Throwable t) {
            return t.toString();
        }
    }
}
