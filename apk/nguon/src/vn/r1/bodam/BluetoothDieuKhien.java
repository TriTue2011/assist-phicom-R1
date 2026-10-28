package vn.r1.bodam;

import android.bluetooth.BluetoothAdapter;

/** Bat/tat Bluetooth bang nut doi (dung chung cho ManHinhChinh va TiepCanPhim). */
public final class BluetoothDieuKhien {
    private BluetoothDieuKhien() {}

    /** Bluetooth dang bat? null neu loa khong co Bluetooth. */
    public static Boolean dangBat() {
        BluetoothAdapter bt = BluetoothAdapter.getDefaultAdapter();
        return bt == null ? null : Boolean.valueOf(bt.isEnabled());
    }

    /** Dat Bluetooth bat/tat (lenh tu HA). null = da gui lenh (hoac da dung trang thai yeu cau); con lai = ly do. */
    public static String dat(boolean bat) {
        try {
            BluetoothAdapter bt = BluetoothAdapter.getDefaultAdapter();
            if (bt == null) return "thiet bi khong co Bluetooth";
            if (bt.isEnabled() == bat) return null;
            boolean ok = bat ? bt.enable() : bt.disable();
            return ok ? null : "he thong tu choi lenh Bluetooth";
        } catch (Throwable t) {
            return t.toString();
        }
    }

    /** Tra ve chu hien thi trang thai; khong doi UI truc tiep. */
    public static String doi() {
        BluetoothAdapter bt = BluetoothAdapter.getDefaultAdapter();
        if (bt == null) return "Thiết bị không có Bluetooth";
        if (bt.isEnabled()) {
            bt.disable();
            return "Bluetooth: đã TẮT (nhấn đôi)";
        }
        bt.enable();
        return "Bluetooth: đã BẬT (nhấn đôi)";
    }
}
