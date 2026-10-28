package vn.r1.bodam;

/**
 * Phim do HA nhan xu ly: HA gui "phim_cau_hinh" (danh sach ma phim) khi APK noi vao. Phim thuoc HA thi APK KHONG xu ly tai cho
 * (khong doi mic/Bluetooth theo logic cu) ma bao su kien xuong/len ve HA; HA tu nhan dien nhan don/doi/ba/giu va chay hanh dong
 * nguoi dung da chon. Mat ket noi thi danh sach bi xoa va logic tai cho (LogicNut) chay lai nhu truoc.
 *
 * Che do do (doTatCa): bao MOI phim ve HA de nguoi dung tim ma phim cua nut/day cam ung; che do nay KHONG nuot phim.
 */
public final class PhimHa {
    private PhimHa() { }

    public interface Gui { boolean gui(byte[] khung); }

    public static final Gui QUA_KENH = new Gui() {
        @Override public boolean gui(byte[] khung) { return KenhHa.gui(khung); }
    };

    private static volatile int[] ma = new int[0];
    private static volatile boolean doTatCa = false;

    public static void datCauHinh(int[] danhSach, boolean do_) {
        ma = danhSach == null ? new int[0] : danhSach.clone();
        doTatCa = do_;
    }

    public static void xoa() { datCauHinh(null, false); }

    /** true = phim nay thuoc HA (APK khong xu ly tai cho). */
    public static boolean hoiXuLy(int keycode) {
        for (int m : ma) if (m == keycode) return true;
        return false;
    }

    public static boolean dangDo() { return doTatCa; }

    /**
     * Xu ly mot su kien phim cua he thong. lap = getRepeatCount() (chi bao lan dau: HA tu do thoi gian de nhan ra nhan giu).
     * Tra ve true neu phim bi nuot (thuoc HA); che do do chi bao, khong nuot.
     */
    public static boolean suKien(int keycode, boolean xuong, int lap, Gui g) {
        boolean cuaHa = hoiXuLy(keycode);
        if (!cuaHa && !doTatCa) return false;
        if (lap == 0) g.gui(Khung.phim(keycode, xuong));
        return cuaHa;
    }
}
