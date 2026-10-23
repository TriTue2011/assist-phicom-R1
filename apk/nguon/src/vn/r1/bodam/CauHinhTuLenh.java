package vn.r1.bodam;

/**
 * Phan tich tham so cau hinh nhan qua lenh am start (loa khong co man hinh).
 * Logic thuan — khong log khoa o bat ky dau.
 *
 * Vi du:
 *   am start -n vn.r1.bodam/.ManHinhChinh --es host 192.0.2.10 --ei port 18765 --es khoa MAT_KHAU
 */
public final class CauHinhTuLenh {
    private CauHinhTuLenh() {}

    public static final class KetQua {
        public final boolean ok;
        public final String loi;      // != null khi !ok
        public final String host;
        public final int port;
        public final String khoa;
        public final boolean tiepCan; // bat dich vu tiep can phim (mac dinh TAT)

        private KetQua(String loi) {
            this.ok = false; this.loi = loi;
            this.host = null; this.port = 0; this.khoa = null; this.tiepCan = false;
        }

        private KetQua(String host, int port, String khoa, boolean tiepCan) {
            this.ok = true; this.loi = null;
            this.host = host; this.port = port; this.khoa = khoa; this.tiepCan = tiepCan;
        }
    }

    /**
     * Cua vao cau hinh bang intent (ManHinhChinh) la cua EXPORTED: bat ky app nao tren loa cung goi duoc,
     * nen CHI nhan khi app CHUA cau hinh (lan dau). Da cau hinh roi thi bo qua; muon doi: `pm clear
     * vn.r1.bodam` roi cau hinh lai (hoac cai ban kiem thu).
     */
    public static boolean choPhepDoiCauHinh(String hostHienTai, String khoaHienTai) {
        return hostHienTai == null || hostHienTai.trim().isEmpty()
                || khoaHienTai == null || khoaHienTai.isEmpty();
    }

    /**
     * Tin hieu he thong cho phep APK TU CHAY LAI dich vu mic (khi da cau hinh):
     * khoi dong loa, khoi dong nhanh (mot so firmware chi gui tin hieu nay), va sau khi APK bi cai de
     * (cai de lam tien trinh bi dung; khong co tin hieu nay dich vu chet cho toi lan khoi dong lai sau).
     * So khop CHINH XAC (phan biet hoa thuong) de tin hieu la khong kich hoat tu bat.
     */
    public static boolean hanhDongTuBat(String hanhDong) {
        return "android.intent.action.BOOT_COMPLETED".equals(hanhDong)
                || "android.intent.action.QUICKBOOT_POWERON".equals(hanhDong)
                || "android.intent.action.MY_PACKAGE_REPLACED".equals(hanhDong);
    }

    /** Du cau hinh de tu bat mic: host va port hop le. Khoa co the CHUA co: APK se tu xin khoa tu HA (Ghep). */
    public static boolean nenTuBat(String host, int port, String khoa) {
        return host != null && !host.trim().isEmpty() && port >= 1 && port <= 65535;
    }

    /**
     * @param host      bat buoc, khong duoc rong
     * @param portChuoi bat buoc, so nguyen 1..65535
     * @param khoa      tuy chon, duoc phep rong ("" = khong khoa)
     * @param tiepCan   tuy chon, null = giu nguyen cau hinh hien tai
     */
    public static KetQua phanTich(String host, String portChuoi, String khoa, Boolean tiepCan) {
        String h = host == null ? "" : host.trim();
        if (h.isEmpty()) return new KetQua("host rong");
        int port;
        try {
            port = Integer.parseInt(portChuoi == null ? "" : portChuoi.trim());
        } catch (NumberFormatException e) {
            return new KetQua("port khong phai so nguyen");
        }
        if (port < 1 || port > 65535) return new KetQua("port ngoai khoang 1..65535");
        String k = khoa == null ? "" : khoa;
        return new KetQua(h, port, k, tiepCan == Boolean.TRUE);
    }
}
