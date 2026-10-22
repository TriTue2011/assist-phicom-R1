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

    /** Gui lenh den nhac (da kiem khoang gia tri). */
    public static String guiDenNhac(int ma, int giaTri) {
        String loi = hopLeDenNhac(ma, giaTri);
        return loi != null ? loi : gui(NHOM_DEN_NHAC, ma, giaTri);
    }
}
