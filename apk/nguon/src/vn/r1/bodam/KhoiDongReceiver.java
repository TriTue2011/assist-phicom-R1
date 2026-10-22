package vn.r1.bodam;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Loa khoi dong lai: tu bat mic neu da cau hinh (host + port + khoa). Mic gui ve HA da cau hinh san,
 * HA tu choi khi nguoi dung tat mic (switch.r1_tat_mic). Receiver KHONG exported: chi he thong gui duoc.
 */
public class KhoiDongReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context ctx, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;
        CauHinh c = CauHinh.doc(ctx);
        if (!CauHinhTuLenh.nenTuBat(c.host, c.port, c.khoa)) return;
        Intent dv = new Intent(ctx, DichVuGhi.class);
        dv.setAction(DichVuGhi.HANH_DONG_BAT);
        ctx.startService(dv);
    }
}
