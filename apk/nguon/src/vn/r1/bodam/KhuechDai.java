package vn.r1.bodam;

/** Khuech dai phan mem PCM16 LE theo dB. Logic thuan. */
public final class KhuechDai {
    private KhuechDai() {}

    public static double heSo(double db) {
        return Math.pow(10.0, db / 20.0);
    }

    /** Ap dung tai cho; tra ve cung mang. Kep gia tri trong [-32768, 32767]. */
    public static byte[] apDung(byte[] pcmLe, double db) {
        if (db == 0.0) return pcmLe;
        double hs = heSo(db);
        int n = pcmLe.length / 2;
        for (int i = 0; i < n; i++) {
            int lo = pcmLe[2 * i] & 0xFF;
            int hi = pcmLe[2 * i + 1];
            short mau = (short) ((hi << 8) | lo);
            long v = Math.round(mau * hs);
            if (v > 32767) v = 32767;
            if (v < -32768) v = -32768;
            pcmLe[2 * i] = (byte) (v & 0xFF);
            pcmLe[2 * i + 1] = (byte) ((v >> 8) & 0xFF);
        }
        return pcmLe;
    }
}
