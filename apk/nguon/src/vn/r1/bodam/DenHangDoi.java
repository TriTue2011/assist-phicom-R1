package vn.r1.bodam;

/**
 * Hang doi lenh den chay tren luong rieng: goi may chu den co the cham toi vai giay, khong duoc chan
 * luong doc tieng HA gui xuong loa. "Moi nhat thang": hieu ung den gui lien tuc, den cham thi chi
 * can muc moi nhat cua tung loai (vien / day), khong dong lenh cu.
 */
public final class DenHangDoi implements Runnable {
    /** Bao lai HA ket qua cau hoi "may chu den san sang chua". */
    public interface Ben {
        void baoSanSang(boolean sanSang);
    }

    private final LenhDieuKhien.DichDen dich;
    private final Ben ben;
    private String vien, day;
    private boolean hoi, dung;

    public DenHangDoi(LenhDieuKhien.DichDen dich, Ben ben) {
        this.dich = dich;
        this.ben = ben;
    }

    /** Nhan mot khung den (khung khong hop le bi bo). Tra ve true neu da nhan. */
    public synchronized boolean dat(String khung) {
        int loai = LenhDieuKhien.loaiDen(khung);
        if (loai == 1) vien = khung;
        else if (loai == 2) day = khung;
        else if (loai == 3) hoi = true;
        else return false;
        notifyAll();
        return true;
    }

    public synchronized void dungLai() {
        dung = true;
        notifyAll();
    }

    /** Lam het viec dang cho (khong doi). Tra ve true neu co viec. */
    public boolean chayMotLuot() {
        String v, d;
        boolean h;
        synchronized (this) {
            v = vien; vien = null;
            d = day; day = null;
            h = hoi; hoi = false;
        }
        if (v != null) LenhDieuKhien.xuLyDen(v, dich);
        if (d != null) LenhDieuKhien.xuLyDen(d, dich);
        if (h) {
            boolean san;
            try { san = dich.sanSang(); } catch (Throwable t) { san = false; }
            ben.baoSanSang(san);
        }
        return v != null || d != null || h;
    }

    @Override public void run() {
        while (true) {
            synchronized (this) {
                while (!dung && vien == null && day == null && !hoi) {
                    try { wait(); } catch (InterruptedException e) { return; }
                }
                if (dung) return;
            }
            try { chayMotLuot(); } catch (Throwable t) { /* mot lenh hong khong duoc giet luong */ }
        }
    }
}
