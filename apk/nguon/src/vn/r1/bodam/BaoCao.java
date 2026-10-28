package vn.r1.bodam;

import java.io.IOException;

/**
 * Bao cao cua APK ve HA qua ket noi mic: phien ban + kha nang (khi noi), thong tin he thong va Bluetooth (dinh ky).
 * Logic thuan de test; luong goi dinh ky nam o DieuKhienGhi.
 */
public final class BaoCao {
    private BaoCao() { }

    /** Phai khop android:versionName trong AndroidManifest (co test canh). */
    public static final String PHIEN_BAN = "1.3";
    public static final String[] KHA_NANG = {"den", "am_luong", "bluetooth", "he_thong", "phim"};
    public static final long CHU_KY_MS = 60000;

    public interface Gui { void gui(byte[] khung) throws IOException; }

    /** Ngay khi noi: phien ban/kha nang, Bluetooth, he thong. Loi gui bo qua (ket noi dut thi phien dang ket thuc). */
    public static void khiNoi(Gui g, HeThongLoa.Nguon n) {
        try { g.gui(Khung.apk(PHIEN_BAN, KHA_NANG)); } catch (IOException boQua) { return; }
        baoBluetooth(g, n.bluetooth());
        baoHeThong(g, n);
    }

    public static void baoHeThong(Gui g, HeThongLoa.Nguon n) {
        try { g.gui(Khung.heThong(HeThongLoa.tao(n))); } catch (IOException boQua) { } catch (RuntimeException boQua) { }
    }

    public static void baoBluetooth(Gui g, Boolean bat) {
        if (bat == null) return;
        try { g.gui(Khung.bluetooth(bat.booleanValue())); } catch (IOException boQua) { }
    }
}
