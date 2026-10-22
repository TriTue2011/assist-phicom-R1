package vn.r1.bodam;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * CHI DE KIEM THU (NV245) — CAN GO TRUOC BAN PHAT HANH.
 * Nhan lenh bat/tat ghi mic qua adb khi khong co man hinh:
 *   /system/bin/am broadcast -a vn.r1.bodam.KIEM_MIC --ez bat true
 *   /system/bin/am broadcast -a vn.r1.bodam.KIEM_MIC --ez bat false
 * Di DUNG duong DichVuGhi nhu nut giua/man hinh (khong tao duong song song):
 * bat=true -> gui HANH_DONG_BAT neu chua ghi; bat=false -> HANH_DONG_TAT neu dang ghi.
 */
public class KiemMicReceiver extends BroadcastReceiver {
    public static final String HANH_DONG_KIEM_MIC = "vn.r1.bodam.KIEM_MIC";
    private static final String TAG = "NV245KiemMic";

    @Override public void onReceive(Context ctx, Intent intent) {
        if (intent == null) return;
        String hd = intent.getAction();
        if ("vn.r1.bodam.KIEM_DEN_NHAC".equals(hd)) {
            // am broadcast -a vn.r1.bodam.KIEM_DEN_NHAC --ei ma 65 --ei giatri 50
            // CHI nhom 4 (den nhac), ma 64-67, gia tri trong khoang (TrungTamTin.guiDenNhac kiem).
            int ma = intent.getIntExtra("ma", -1), gt = intent.getIntExtra("giatri", 0);
            String loi = TrungTamTin.guiDenNhac(ma, gt);
            Log.i(TAG, "KIEM_DEN_NHAC ma=" + ma + " giatri=" + gt + " -> "
                    + (loi == null ? "da gui" : loi));
            return;
        }
        if (!HANH_DONG_KIEM_MIC.equals(hd)) return;
        boolean bat = intent.getBooleanExtra("bat", false);
        // CHI KIEM THU: nhan host/cong/khoa qua tham so broadcast (khong can man hinh)
        CauHinh c = CauHinh.doc(ctx);
        if (intent.hasExtra("host")) c.host = intent.getStringExtra("host");
        if (intent.hasExtra("port")) c.port = intent.getIntExtra("port", c.port);
        if (intent.hasExtra("khoa")) c.khoa = intent.getStringExtra("khoa");
        c.luu(ctx);
        Intent dv = new Intent(ctx, DichVuGhi.class);
        if (bat) {
            if (!DichVuGhi.dangChay) {
                dv.setAction(DichVuGhi.HANH_DONG_BAT);
                ctx.startService(dv);
                Log.i(TAG, "KIEM_MIC: bat ghi mic");
            } else {
                Log.i(TAG, "KIEM_MIC: dang ghi san, bo qua lenh bat");
            }
        } else {
            if (DichVuGhi.dangChay) {
                dv.setAction(DichVuGhi.HANH_DONG_TAT);
                ctx.startService(dv);
                Log.i(TAG, "KIEM_MIC: tat ghi mic");
            } else {
                Log.i(TAG, "KIEM_MIC: mic dang tat san, bo qua lenh tat");
            }
        }
    }
}
