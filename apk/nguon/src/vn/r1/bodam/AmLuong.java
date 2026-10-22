package vn.r1.bodam;

import android.content.Context;
import android.media.AudioManager;

/**
 * Am luong NHAC cua loa bang ham chuan cua Android: AudioManager.setStreamVolume(STREAM_MUSIC, 0..toiDa, 0).
 * Chu may nghe xac nhan 22/10/2026: chi so 0 mat tieng, 8 to hon (AudioFlinger: chi so 4 = -32 dB, chi so 2 = -51 dB).
 * KHONG can quyen dac biet. Luong thong bao/he thong (vuot day cam ung) la luong khac, khong dung o day.
 */
final class AmLuong implements LenhDieuKhien.DichAm {
    private static final int LUONG_NHAC = AudioManager.STREAM_MUSIC;
    private static volatile Context ctx;

    static void khoiTao(Context c) { ctx = c == null ? null : c.getApplicationContext(); }

    private static AudioManager am() {
        Context c = ctx;
        return c == null ? null : (AudioManager) c.getSystemService(Context.AUDIO_SERVICE);
    }

    @Override public String dat(int muc) {
        try {
            AudioManager a = am();
            if (a == null) return "chua co Context";
            if (muc < 0 || muc > a.getStreamMaxVolume(LUONG_NHAC)) return "muc ngoai khoang 0.." + a.getStreamMaxVolume(LUONG_NHAC);
            a.setStreamVolume(LUONG_NHAC, muc, 0);
            return null;
        } catch (Throwable t) {
            return t.toString();
        }
    }

    @Override public int muc() {
        try { AudioManager a = am(); return a == null ? -1 : a.getStreamVolume(LUONG_NHAC); } catch (Throwable t) { return -1; }
    }

    @Override public int toiDa() {
        try { AudioManager a = am(); return a == null ? -1 : a.getStreamMaxVolume(LUONG_NHAC); } catch (Throwable t) { return -1; }
    }
}
