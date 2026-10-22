package vn.r1.bodam;

import android.bluetooth.BluetoothAdapter;

/** Bat/tat Bluetooth bang nut doi (dung chung cho ManHinhChinh va TiepCanPhim). */
public final class BluetoothDieuKhien {
    private BluetoothDieuKhien() {}

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
