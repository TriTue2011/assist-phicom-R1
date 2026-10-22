package vn.r1.bodam;

/**
 * Logic nut giua: nhan don (sau khi het khoang cho) -> doi mic;
 * nhan doi trong khoang -> doi Bluetooth, mic khong doi them.
 * Dong ho va hen gio tiem vao de kiem bang gia lap.
 */
public final class LogicNut {
    public interface DongHo { long bayGioMs(); }
    public interface HenGio {
        void hen(long treMs, Runnable viec);
        void huy();
    }
    public interface HanhDong {
        void doiMic();
        void doiBluetooth();
    }

    private final long khoangNhanDoiMs;
    private final HenGio henGio;
    private final HanhDong hanhDong;
    private boolean dangChoNhanDon = false;

    public LogicNut(long khoangNhanDoiMs, HenGio henGio, HanhDong hanhDong) {
        this.khoangNhanDoiMs = khoangNhanDoiMs;
        this.henGio = henGio;
        this.hanhDong = hanhDong;
    }

    /**
     * Loc ma phim: chi ma trung keycode nut giua da cau hinh moi kich hoat.
     * Mac dinh da do (NV245): 195. Keycode cau hinh am (chua do) -> khong kich hoat gi.
     */
    public static boolean laPhimNutGiua(int keycodeSuKien, int keycodeCauHinh) {
        return keycodeCauHinh >= 0 && keycodeSuKien == keycodeCauHinh;
    }

    /** Goi moi lan nhan nut giua (su kien nhan xuong). */
    public synchronized void nhan() {
        if (dangChoNhanDon) {
            // Nhan lan 2 trong khoang -> nhan doi
            henGio.huy();
            dangChoNhanDon = false;
            hanhDong.doiBluetooth();
        } else {
            dangChoNhanDon = true;
            henGio.hen(khoangNhanDoiMs, new Runnable() {
                @Override public void run() {
                    synchronized (LogicNut.this) {
                        if (dangChoNhanDon) {
                            dangChoNhanDon = false;
                            hanhDong.doiMic();
                        }
                    }
                }
            });
        }
    }

    public synchronized boolean dangCho() { return dangChoNhanDon; }
}
