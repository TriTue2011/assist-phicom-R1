package vn.r1.bodam;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.accessibility.AccessibilityEvent;

/**
 * NV247 — nhan phim nut giua khi app KHONG o tien canh (loa R1 khong co man hinh).
 *
 * CHI HOAT DONG KHI: chu may bat co "bat_tiep_can_phim" trong cau hinh
 * (mac dinh TAT; bat bang lenh: am start ... --ez tiep_can true)
 * VA nguoi dung (hoac adb) bat dich vu trong Cai dat > Tro nang.
 *
 * Ly do chon AccessibilityService (xem bao cao NV247 phan nghien cuu):
 * - La API chuan tu API 16 de nhan KeyEvent toan cuc (onKeyEvent),
 *   khong can root, chay duoc tren Android 5.1 (API 22).
 * - Khong can giu activity tien canh, khong chiem nut HOME.
 * Rui ro: dich vu tro nang co the thay moi phim bam — chi bat khi chu may
 * dong y ro rang; ma chi phan ung dung ma phim nut giua da cau hinh.
 * CHUA KIEM TREN LOA THAT.
 */
public class TiepCanPhim extends AccessibilityService {

    private LogicNut logicNut;

    @Override protected boolean onKeyEvent(KeyEvent event) {
        CauHinh cfg = CauHinh.doc(this);
        if (!cfg.batTiepCanPhim) return false;
        if (event.getAction() == KeyEvent.ACTION_DOWN
                && event.getRepeatCount() == 0
                && LogicNut.laPhimNutGiua(event.getKeyCode(), cfg.keycodeNutGiua)) {
            if (logicNut == null) logicNut = taoLogicNut(cfg.khoangNhanDoiMs);
            logicNut.nhan();
            return true;
        }
        return false;
    }

    private LogicNut taoLogicNut(long khoangNhanDoiMs) {
        final Handler h = new Handler(Looper.getMainLooper());
        LogicNut.HenGio henGio = new LogicNut.HenGio() {
            private Runnable dangHen;
            @Override public void hen(long treMs, Runnable viec) {
                huy();
                dangHen = viec;
                h.postDelayed(viec, treMs);
            }
            @Override public void huy() {
                if (dangHen != null) h.removeCallbacks(dangHen);
                dangHen = null;
            }
        };
        final TiepCanPhim dv = this;
        return new LogicNut(khoangNhanDoiMs, henGio, new LogicNut.HanhDong() {
            @Override public void doiMic() {
                Intent i = new Intent(dv, DichVuGhi.class);
                if (DichVuGhi.dangChay) {
                    i.setAction(DichVuGhi.HANH_DONG_TAT);
                } else {
                    i.setAction(DichVuGhi.HANH_DONG_BAT);
                }
                dv.startService(i);
            }
            @Override public void doiBluetooth() {
                BluetoothDieuKhien.doi();
            }
        });
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }

    @Override public void onInterrupt() { }
}
