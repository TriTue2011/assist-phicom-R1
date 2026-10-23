package vn.r1.bodam;

import android.os.IBinder;

/**
 * Gui tin toi dich vu he thong "msgcenter" cua firmware R1: IMessageCenterService.sendMsg(nhom,
 * ma, giaTri) — cach app AI box dieu khien den LED (nhom 0x1000). App player dang ky nhan nhom 4
 * cho den theo nhac (PlayerVisualizerHelper.notifyMsg): ma 64 bat/tat, 65 do sang (luma 0-100),
 * 66 sac do (chroma 1-100), 67 che do co gian. Goi bang phan chieu vi lop nay an (khong co trong
 * android.jar).
 */
public final class TrungTamTin {
    private TrungTamTin() { }

    public static final int NHOM_DEN_NHAC = 4;
    public static final int MA_BAT = 64, MA_LUMA = 65, MA_CHROMA = 66, MA_CHE_DO = 67;

    /** null = hop le; con lai la ly do tu choi (khong gui gia tri ngoai khoang cho firmware). */
    public static String hopLeDenNhac(int ma, int giaTri) {
        switch (ma) {
            case MA_BAT: return giaTri == 0 || giaTri == 1 ? null : "bat/tat phai la 0 hoac 1";
            case MA_LUMA: return giaTri >= 0 && giaTri <= 100 ? null : "luma phai tu 0 den 100";
            case MA_CHROMA: return giaTri >= 1 && giaTri <= 100 ? null : "chroma phai tu 1 den 100";
            case MA_CHE_DO: return giaTri >= 0 && giaTri <= 16 ? null : "che do ngoai khoang";
            default: return "ma den nhac la: " + ma;
        }
    }

    /** Gui mot tin. Tra ve null neu gui duoc, hoac thong bao loi. */
    public static String gui(int nhom, int ma, int giaTri) {
        try {
            Class<?> sm = Class.forName("android.os.ServiceManager");
            IBinder b = (IBinder) sm.getMethod("getService", String.class).invoke(null, "msgcenter");
            if (b == null) return "khong co dich vu msgcenter";
            Class<?> stub = Class.forName("android.os.IMessageCenterService$Stub");
            Object svc = stub.getMethod("asInterface", IBinder.class).invoke(null, b);
            if (svc == null) return "asInterface tra null";
            svc.getClass().getMethod("sendMsg", int.class, int.class, int.class)
                    .invoke(svc, nhom, ma, giaTri);
            return null;
        } catch (Throwable t) {
            return t.toString();
        }
    }

    /** Nhom cua hieu ung den co san trong /system/etc/lights_effects.conf (cach app AI box dieu khien den). */
    public static final int NHOM_HIEU_UNG = 0x1000;
    /** ID hieu ung cho phep (200-206 tho, 251-255 sang co dinh, 500-505 mau thu nha may + tat, 510-515 tho 4 giay). */
    private static final int[] HIEU_UNG_HOP_LE = {
        200, 201, 202, 203, 204, 206, 251, 252, 253, 254, 255, 500, 501, 502, 503, 504, 505, 510, 511, 512, 513, 514, 515,
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24};

    public static boolean laHieuUngHopLe(int id) {
        for (int x : HIEU_UNG_HOP_LE) if (x == id) return true;
        return false;
    }

    /** Gui mot hieu ung den cua firmware: sendMsg(0x1000, id, 0). Chi nhan ID trong danh sach cho phep. */
    public static String guiHieuUng(int id) {
        return laHieuUngHopLe(id) ? gui(NHOM_HIEU_UNG, id, 0) : "hieu ung den khong cho phep: " + id;
    }

    /** Co lay duoc dich vu msgcenter khong (dieu kien de dieu khien den bang hieu ung firmware). */
    public static boolean sanSang() {
        try {
            Class<?> sm = Class.forName("android.os.ServiceManager");
            IBinder b = (IBinder) sm.getMethod("getService", String.class).invoke(null, "msgcenter");
            return b != null;
        } catch (Throwable t) {
            return false;
        }
    }

    /** Gui lenh den nhac (da kiem khoang gia tri). */
    public static String guiDenNhac(int ma, int giaTri) {
        String loi = hopLeDenNhac(ma, giaTri);
        return loi != null ? loi : gui(NHOM_DEN_NHAC, ma, giaTri);
    }
}
