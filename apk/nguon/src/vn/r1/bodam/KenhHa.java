package vn.r1.bodam;

import java.io.IOException;

/**
 * Kenh gui khung dieu khien len HA qua ket noi mic dang mo (nguoi dung la phien ghi hien tai).
 * Cho phep lop khac (TiepCanPhim, nut bam) gui su kien ma khong biet phien nao dang song.
 * Khong co ket noi thi bo qua im lang (tra ve false), khong bao gio nem loi.
 */
public final class KenhHa {
    private KenhHa() { }

    private static volatile MayGhi may;

    static void dat(MayGhi m) { may = m; }

    /** Chi go neu van la phien nay (phien moi da thay the thi khong dong nham). */
    static void bo(MayGhi m) { if (may == m) may = null; }

    public static boolean gui(byte[] khungDaDongGoi) {
        MayGhi m = may;
        if (m == null) return false;
        try {
            m.guiKhung(khungDaDongGoi);
            return true;
        } catch (IOException loi) {
            return false;
        }
    }
}
