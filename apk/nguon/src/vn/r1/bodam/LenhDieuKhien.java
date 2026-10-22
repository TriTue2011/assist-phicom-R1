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

    /** Dich den vien/day: may chu den quyen shell tren loa (DenCau). */
    public interface DichDen {
        /** null = gui duoc; con lai = loi. muc 0-255 (chi trang). */
        String guiVien(int muc);
        /** rgb: sau so hex thuong. */
        String guiDay(String rgb);
        boolean sanSang();
        /** Hieu ung den co san cua firmware (ID da kiem danh sach cho phep o noi goi). null = gui duoc. */
        String guiHieuUng(int id);
    }

    public static final DichDen DEN_THAT = new DichDen() {
        @Override public String guiHieuUng(int id) { return TrungTamTin.guiHieuUng(id); }
        @Override public String guiVien(int muc) { return DenCau.vien(muc); }
        @Override public String guiDay(String rgb) { return DenCau.day(rgb); }
        @Override public boolean sanSang() { return TrungTamTin.sanSang(); }
    };

    /** Dich am luong nhac: dat / doc muc hien tai / muc toi da. Ban that la AmLuong (AudioManager), kiem thu dung gia. */
    public interface DichAm {
        /** null = dat duoc; con lai = ly do. */
        String dat(int muc);
        /** Muc hien tai, -1 neu khong doc duoc. */
        int muc();
        int toiDa();
    }

    private static final Pattern AM_LUONG = Pattern.compile("^\\{\"type\":\"am_luong\",\"muc\":(\\d{1,2})\\}$");
    private static final String AM_HOI = "{\"type\":\"am_hoi\"}";

    /** Khung am luong ({"type":"am_luong","muc":N} hoac {"type":"am_hoi"}) hop le ve dinh dang. */
    public static boolean laAmLuong(String khung) {
        if (khung == null || khung.length() > DAI_TOI_DA) return false;
        return AM_HOI.equals(khung) || AM_LUONG.matcher(khung).matches();
    }

    /** Xu ly khung am luong: dat muc (neu la am_luong). null = xong (hoac chi hoi); con lai = ly do bo qua. Khong nem loi. */
    public static String xuLyAm(String khung, DichAm dich) {
        try {
            if (!laAmLuong(khung)) return "khong phai khung am luong";
            Matcher m = AM_LUONG.matcher(khung);
            if (!m.matches()) return null;                       // am_hoi: chi bao lai
            int muc = Integer.parseInt(m.group(1));
            int toiDa = dich.toiDa();
            if (toiDa >= 0 && muc > toiDa) return "muc am luong ngoai 0.." + toiDa;
            return dich.dat(muc);
        } catch (Throwable t) {
            return t.toString();
        }
    }

    private static final Pattern DEN_VIEN = Pattern.compile("^\\{\"type\":\"den_vien\",\"muc\":(\\d{1,3})\\}$");
    private static final Pattern DEN_DAY = Pattern.compile("^\\{\"type\":\"den_day\",\"rgb\":\"([0-9a-f]{6})\"\\}$");
    private static final Pattern DEN_HIEU_UNG = Pattern.compile("^\\{\"type\":\"den_hieu_ung\",\"id\":(\\d{1,3})\\}$");
    private static final String DEN_HOI = "{\"type\":\"den_hoi\"}";

    /** Loai khung den: 1 = vien, 2 = day, 3 = hoi san sang, 4 = hieu ung firmware, 0 = khong phai khung den hop le. */
    public static int loaiDen(String khung) {
        if (khung == null || khung.length() > DAI_TOI_DA) return 0;
        if (DEN_HOI.equals(khung)) return 3;
        if (DEN_VIEN.matcher(khung).matches()) return 1;
        if (DEN_DAY.matcher(khung).matches()) return 2;
        if (DEN_HIEU_UNG.matcher(khung).matches()) return 4;
        return 0;
    }

    /** Xu ly khung den_vien / den_day. null = da gui; con lai = ly do bo qua. Khong nem loi ra ngoai.
     *  (den_hoi do ben goi tra loi, vi can ghi len ket noi.) */
    public static String xuLyDen(String khung, DichDen dich) {
        try {
            int loai = loaiDen(khung);
            if (loai == 1) {
                Matcher m = DEN_VIEN.matcher(khung);
                m.matches();
                int muc = Integer.parseInt(m.group(1));
                if (muc > 255) return "muc vien ngoai 0-255";
                return dich.guiVien(muc);
            }
            if (loai == 2) {
                Matcher m = DEN_DAY.matcher(khung);
                m.matches();
                return dich.guiDay(m.group(1));
            }
            if (loai == 4) {
                Matcher m = DEN_HIEU_UNG.matcher(khung);
                m.matches();
                int id = Integer.parseInt(m.group(1));
                if (!TrungTamTin.laHieuUngHopLe(id)) return "hieu ung den khong cho phep: " + id;
                return dich.guiHieuUng(id);
            }
            return "khong phai lenh den vien/day/hieu ung";
        } catch (Throwable t) {
            return t.toString();
        }
    }

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
