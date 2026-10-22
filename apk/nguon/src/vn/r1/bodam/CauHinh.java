package vn.r1.bodam;

import android.content.Context;
import android.content.SharedPreferences;

/** Cau hinh luu bang SharedPreferences. Khong ma cung IP/khoa. */
public final class CauHinh {
    public static final int KEYCODE_CHUA_DO = -1;
    // DA DO THAT 22/10/2026 (NV245): nhan nut giua tren loa phat ma 195 (0x00c3),
    // thiet bi /dev/input/event0 (rk29-keypad), co du DOWN va UP.
    public static final int KEYCODE_NUT_GIUA_MAC_DINH = 195;
    public static final double GAIN_MAC_DINH_DB = 0.0; // CHUA DO tren loa that
    public static final long KHOANG_NHAN_DOI_MAC_DINH_MS = 500;

    public String host;
    public int port;
    public String khoa;
    public double gainDb;
    public long khoangNhanDoiMs;
    public int keycodeNutGiua;
    public boolean cheDoKiemPhim;
    /** NV247: bat dich vu tiep can phim (nhan nut giua khi app khong tien canh).
     *  Mac dinh TAT — chi bat khi chu may dong y ro rang. */
    public boolean batTiepCanPhim;

    private static final String TEN = "cau_hinh";

    public static CauHinh doc(Context ctx) {
        SharedPreferences p = ctx.getSharedPreferences(TEN, Context.MODE_PRIVATE);
        CauHinh c = new CauHinh();
        c.host = p.getString("host", "");
        c.port = p.getInt("port", 0);
        c.khoa = p.getString("khoa", "");
        c.gainDb = Double.longBitsToDouble(p.getLong("gain_db",
                Double.doubleToLongBits(GAIN_MAC_DINH_DB)));
        c.khoangNhanDoiMs = p.getLong("khoang_nhan_doi_ms", KHOANG_NHAN_DOI_MAC_DINH_MS);
        c.keycodeNutGiua = p.getInt("keycode_nut_giua", KEYCODE_NUT_GIUA_MAC_DINH);
        c.cheDoKiemPhim = p.getBoolean("che_do_kiem_phim", false);
        c.batTiepCanPhim = p.getBoolean("bat_tiep_can_phim", false);
        return c;
    }

    public void luu(Context ctx) {
        SharedPreferences.Editor e = ctx.getSharedPreferences(TEN, Context.MODE_PRIVATE).edit();
        e.putString("host", host == null ? "" : host);
        e.putInt("port", port);
        e.putString("khoa", khoa == null ? "" : khoa);
        e.putLong("gain_db", Double.doubleToLongBits(gainDb));
        e.putLong("khoang_nhan_doi_ms", khoangNhanDoiMs);
        e.putInt("keycode_nut_giua", keycodeNutGiua);
        e.putBoolean("che_do_kiem_phim", cheDoKiemPhim);
        e.putBoolean("bat_tiep_can_phim", batTiepCanPhim);
        e.apply();
    }
}
