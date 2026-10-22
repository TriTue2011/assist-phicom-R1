package vn.r1.bodam;

import java.io.IOException;

/**
 * May trang thai ghi: tat -> khong ghi; bat -> mo van chuyen + gui hello;
 * guiPcm chi khi dang ghi; tat -> gui end + dong ngay.
 * Van chuyen tiem vao de kiem bang gia lap.
 */
public final class MayGhi {
    public interface VanChuyen {
        void mo() throws IOException;
        void gui(byte[] khung) throws IOException;
        void dong();
        boolean dangMo();
    }

    private final VanChuyen vanChuyen;
    private final String khoa;
    private boolean dangGhi = false;

    public MayGhi(VanChuyen vanChuyen, String khoa) {
        this.vanChuyen = vanChuyen;
        this.khoa = khoa == null ? "" : khoa;
    }

    public synchronized boolean dangGhi() { return dangGhi; }

    public synchronized void bat() throws IOException {
        if (dangGhi) return;
        vanChuyen.mo();
        vanChuyen.gui(Khung.hello(khoa));
        dangGhi = true;
    }

    public synchronized void guiPcm(byte[] pcmDaKhuechDai) throws IOException {
        if (!dangGhi) return;
        vanChuyen.gui(Khung.dongGoi(pcmDaKhuechDai));
    }

    public synchronized void tat() {
        if (!dangGhi) return;
        dangGhi = false;
        try {
            vanChuyen.gui(Khung.end());
        } catch (IOException boQua) {
            // Dong ngay ca khi gui end loi
        }
        vanChuyen.dong();
    }
}
