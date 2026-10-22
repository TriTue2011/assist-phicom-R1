package vn.r1.bodam;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;

/**
 * Dieu khien phien ghi mic — logic thuan (khong phu thuoc Android) de test duoc.
 *
 * - Ket noi socket CO timeout (CONNECT_TIMEOUT_MS).
 * - Generation: moi lan bat() tang the he; luong cua the he cu tu thoat,
 *   dam bao khong bao gio co hai phien ghi song song.
 * - tat(): dat co dung, tang the he, DONG SOCKET NGAY de huy ket noi dang treo,
 *   va ngat luong cu neu no dang cho.
 */
public final class DieuKhienGhi {

    /** Timeout ket noi TCP, ms. */
    public static final int CONNECT_TIMEOUT_MS = 5000;

    /** Trang thai gui ve lop Android: "dang_ket_noi" / "dang_gui" / "cho_noi_lai" / "loi" / "da_dung".
     *  "cho_noi_lai" chi co khi bat noi lai (NoiLai): ket noi dut, doi roi thu lai. */
    public interface BenNhanTrangThai {
        void doiTrangThai(String trangThai);
    }

    /** Nguon am thanh truu tuong (thay cho AudioRecord de test). */
    public interface MayDocAm {
        void batDau() throws IOException;
        /** Tra ve so byte doc duoc; 0 = chua co du lieu; < 0 = het. */
        int doc(byte[] buf, int batDau, int dai) throws IOException;
        void dung();
    }

    public interface NhaTao {
        Socket ketNoi(String host, int port) throws IOException;
        MayDocAm taoMayDoc(int kichThuocDem) throws IOException;
    }

    /** Chinh sach noi lai khi ket noi dut (HA khoi dong lai, mang chap chon...). Cho tang dan tu
     *  choDauMs den choToiDaMs. Mot phien gui duoc it nhat phienToiThieuMs coi la da noi duoc: tu do
     *  thu mai khong bo cuoc. Chua tung noi duoc ma that bai toiDaThuKhiChuaNoi lan lien tiep thi
     *  bao "loi" (sai host/khoa/mic) va dung han. Giua cac lan thu mic duoc DONG. */
    public static final class NoiLai {
        final long choDauMs, choToiDaMs, phienToiThieuMs;
        final int toiDaThuKhiChuaNoi;

        public NoiLai(long choDauMs, long choToiDaMs, long phienToiThieuMs, int toiDaThuKhiChuaNoi) {
            this.choDauMs = choDauMs;
            this.choToiDaMs = choToiDaMs;
            this.phienToiThieuMs = phienToiThieuMs;
            this.toiDaThuKhiChuaNoi = toiDaThuKhiChuaNoi;
        }

        /** 2 s, 4 s ... toi da 30 s; phien >= 5 s la da noi duoc; 12 lan that bai dau thi bo cuoc. */
        public static NoiLai macDinh() { return new NoiLai(2000, 30000, 5000, 12); }
    }

    /** Xin khoa tu HA khi bi tu choi (ghep khoa tu dong). null = khong ghep (hanh vi cu). */
    public interface GhepKhoa {
        /** {cong, khoa} neu HA trao khoa; null neu khong. */
        String[] thu(String host);
        void luu(int port, String khoa);
    }

    private volatile GhepKhoa ghep;

    public void datGhep(GhepKhoa g) { this.ghep = g; }

    private static final long GHEP_CACH_MS = 20000;

    private final NoiLai noiLai; // null = khong noi lai (hanh vi cu)

    public DieuKhienGhi() { this(null); }

    public DieuKhienGhi(NoiLai noiLai) { this.noiLai = noiLai; }

    private final Object khoa = new Object();
    private Thread luong;
    private Socket socket;
    private int theHe = 0;
    private volatile boolean dung = false;

    /** Ket noi TCP co timeout — dung cho ca code that lan test. */
    public static Socket ketNoiCoTimeout(String host, int port) throws IOException {
        Socket s = new Socket();
        s.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
        return s;
    }

    /** Bat phien ghi moi. Neu phien cu con song (ke ca dang treo o connect),
     *  no se tu thoat nho the he tang. */
    public void bat(final String host, final int port, final String khoaMayGhi,
                    final double gainDb,
                    final NhaTao nhaTao, final BenNhanTrangThai benNhan) {
        final int theHeCuaToi;
        synchronized (khoa) {
            theHe++;
            theHeCuaToi = theHe;
            dung = false;
            dongSocketKhoa(); // huy ket noi treo cua phien cu (neu co)
            if (luong != null) luong.interrupt(); // goi luong cu neu dang cho
            luong = new Thread(new Runnable() {
                @Override public void run() {
                    if (noiLai == null) {
                        vongGhi(theHeCuaToi, host, port, khoaMayGhi, gainDb, nhaTao, benNhan);
                    } else {
                        vongNoiLai(theHeCuaToi, host, port, khoaMayGhi, gainDb, nhaTao, benNhan);
                    }
                }
            }, "nv247-ghi");
            luong.start();
        }
    }

    /** Tat: khong con luong nao chay sau khi ham nay tra ve (ngoai do tre
     *  toi da cua connect timeout doi voi ket noi that). */
    public void tat() {
        synchronized (khoa) {
            dung = true;
            theHe++;
            dongSocketKhoa();
            if (luong != null) luong.interrupt();
        }
    }

    /** Dem luong worker con song (phuc vu test). */
    public int soLuongLuocSong() {
        int dem = 0;
        for (Thread t : Thread.getAllStackTraces().keySet()) {
            if ("nv247-ghi".equals(t.getName()) && t.isAlive()) dem++;
        }
        return dem;
    }

    private void dongSocketKhoa() {
        Socket s = socket;
        socket = null;
        if (s != null) {
            try { s.close(); } catch (IOException boQua) { }
        }
    }

    private boolean daNgung(int theHeCuaToi) {
        synchronized (khoa) { return dung || theHeCuaToi != theHe; }
    }

    /** Vong nguoi giu: chay vongGhi, dut thi doi roi noi lai theo chinh sach. "loi"/"da_dung" cua
     *  tung vongGhi bi chan lai (lop Android coi "loi" la dung dich vu) — chi phat "loi" khi bo
     *  cuoc, "da_dung" khi tat() that su. */
    private void vongNoiLai(int theHeCuaToi, String host, int port, String khoaMayGhi,
                            double gainDb, NhaTao nhaTao, final BenNhanTrangThai benNhan) {
        BenNhanTrangThai loc = new BenNhanTrangThai() {
            @Override public void doiTrangThai(String trangThai) {
                if ("loi".equals(trangThai) || "da_dung".equals(trangThai)) return;
                benNhan.doiTrangThai(trangThai);
            }
        };
        long cho = noiLai.choDauMs;
        int thatBai = 0;
        boolean daTungNoi = false;
        long lanGhepCuoi = 0;
        while (true) {
            long dai = vongGhi(theHeCuaToi, host, port, khoaMayGhi, gainDb, nhaTao, loc);
            if (daNgung(theHeCuaToi)) break;
            if (dai >= 0 && dai >= noiLai.phienToiThieuMs) {
                daTungNoi = true;
                thatBai = 0;
                cho = noiLai.choDauMs;
            } else {
                thatBai++;
                // Bi tu choi lien tiep (khoa cu/trong): xin khoa moi tu HA roi noi lai ngay, khong phai copy tay.
                GhepKhoa g = ghep;
                long bay = System.currentTimeMillis();
                if (g != null && thatBai >= 2 && bay - lanGhepCuoi >= GHEP_CACH_MS) {
                    lanGhepCuoi = bay;
                    String[] kq = null;
                    try { kq = g.thu(host); } catch (Throwable boQua) { }
                    if (kq != null && kq.length == 2) {
                        port = Integer.parseInt(kq[0]);
                        khoaMayGhi = kq[1];
                        try { g.luu(port, khoaMayGhi); } catch (Throwable boQua) { }
                        thatBai = 0;
                        cho = noiLai.choDauMs;
                        continue;
                    }
                }
            }
            if (!daTungNoi && thatBai >= noiLai.toiDaThuKhiChuaNoi) {
                benNhan.doiTrangThai("loi");
                return;
            }
            benNhan.doiTrangThai("cho_noi_lai");
            try {
                Thread.sleep(cho);
            } catch (InterruptedException ngat) {
                break; // tat() hoac bat() moi goi day
            }
            cho = Math.min(cho * 2, noiLai.choToiDaMs);
            if (daNgung(theHeCuaToi)) break;
        }
        boolean datTat;
        synchronized (khoa) { datTat = dung; }
        if (datTat) benNhan.doiTrangThai("da_dung");
    }

    /** Mot phien ghi. Tra ve so ms da o trang thai "dang_gui"; -1 neu chua toi do. */
    private long vongGhi(int theHeCuaToi, String host, int port, String khoaMayGhi,
                         double gainDb, NhaTao nhaTao, BenNhanTrangThai benNhan) {
        benNhan.doiTrangThai("dang_ket_noi");
        Socket s;
        try {
            s = nhaTao.ketNoi(host, port);
        } catch (IOException loi) {
            benNhan.doiTrangThai("loi");
            return -1;
        }
        synchronized (khoa) {
            if (theHeCuaToi != theHe || dung) {
                try { s.close(); } catch (IOException boQua) { }
                return -1;
            }
            socket = s;
        }
        final OutputStream out;
        try {
            out = s.getOutputStream();
        } catch (IOException loi) {
            benNhan.doiTrangThai("loi");
            synchronized (khoa) { dongSocketKhoa(); }
            return -1;
        }
        MayGhi.VanChuyen vc = new MayGhi.VanChuyen() {
            @Override public void mo() { }
            @Override public void gui(byte[] khung) throws IOException {
                out.write(khung);
                out.flush();
            }
            @Override public void dong() {
                synchronized (khoa) { dongSocketKhoa(); }
            }
            @Override public boolean dangMo() {
                synchronized (khoa) { return socket != null && !socket.isClosed(); }
            }
        };
        MayGhi mayGhi = new MayGhi(vc, khoaMayGhi);
        try {
            mayGhi.bat(); // gui hello; xong moi duoc coi la "dang gui"
        } catch (IOException loi) {
            benNhan.doiTrangThai("loi");
            synchronized (khoa) { dongSocketKhoa(); }
            return -1;
        }
        benNhan.doiTrangThai("dang_gui");
        final long luc = System.currentTimeMillis();

        // Lenh den vien/day chay tren luong rieng (goi may chu den co the cham): khong chan duong phat tieng.
        final MayGhi mayGhiCuoi = mayGhi;
        final DenHangDoi hangDen = new DenHangDoi(LenhDieuKhien.DEN_THAT, new DenHangDoi.Ben() {
            @Override public void baoSanSang(boolean sanSang) {
                try { mayGhiCuoi.guiKhung(Khung.trangThaiDen(sanSang)); } catch (IOException boQua) { }
            }
        });
        Thread luongDen = new Thread(hangDen, "r1-den");
        luongDen.setDaemon(true);
        luongDen.start();
        hangDen.dat("{\"type\":\"den_hoi\"}");                   // bao HA trang thai may chu den ngay khi noi

        // Luồng nhận PCM từ HA (phát xuống loa) trên cùng kết nối; khung JSON điều khiển bị bỏ qua.
        final PhatAm phat = new PhatAm();
        new Thread(new Runnable() {
            @Override public void run() {
                boolean dangDoc = false;
                try {
                    java.io.InputStream in = s.getInputStream();
                    phat.mo();
                    dangDoc = true;
                    while (true) {
                        int a = in.read(), b = in.read(), c = in.read(), d = in.read();
                        if ((a | b | c | d) < 0) break;
                        int len = (a << 24) | (b << 16) | (c << 8) | d;
                        if (len <= 0 || len > 65536) break;
                        byte[] pcm = new byte[len];
                        int da = 0;
                        while (da < len) {
                            int r = in.read(pcm, da, len - da);
                            if (r < 0) return;
                            da += r;
                        }
                        if (pcm[0] == '{') {                       // khung JSON điều khiển (đèn nhạc, đèn viền/đáy)
                            if (len <= LenhDieuKhien.DAI_TOI_DA) {
                                String khungJson = new String(pcm, 0, len, java.nio.charset.Charset.forName("UTF-8"));
                                if (!hangDen.dat(khungJson)) {
                                    LenhDieuKhien.xuLy(khungJson, LenhDieuKhien.THAT);
                                }
                            }
                            continue;
                        }
                        phat.ghi(pcm, len);
                    }
                } catch (java.io.IOException | RuntimeException ignored) {
                    // kết nối đóng/hỏng: luồng phát dừng, phiên mic xử lý tiếp
                } finally {
                    hangDen.dungLai();
                    phat.dong();
                    if (dangDoc) {
                        // HA dong / ket noi hong: dong socket de phia gui mic bao dut ngay
                        synchronized (khoa) { if (socket == s) dongSocketKhoa(); }
                    }
                }
            }
        }, "r1-phat-am").start();

        MayDocAm docAm;
        try {
            docAm = nhaTao.taoMayDoc(3200);
        } catch (IOException loi) {
            mayGhi.tat();
            benNhan.doiTrangThai("loi");
            synchronized (khoa) { dongSocketKhoa(); }
            return System.currentTimeMillis() - luc;
        }
        byte[] buf = new byte[3201];
        int du = 0; // byte le don sang lan doc sau (0 hoac 1)
        try {
            docAm.batDau();
            while (true) {
                synchronized (khoa) {
                    if (dung || theHeCuaToi != theHe) break;
                }
                int doc = docAm.doc(buf, du, buf.length - du);
                if (doc < 0) break;
                if (doc == 0) continue;
                int tong = du + doc;
                int chan = tong & ~1; // chi gui so byte chan
                if (chan > 0) {
                    byte[] pcm = new byte[chan];
                    System.arraycopy(buf, 0, pcm, 0, chan);
                    KhuechDai.apDung(pcm, gainDb);
                    mayGhi.guiPcm(pcm);
                }
                du = tong - chan; // 0 hoac 1
                if (du == 1) buf[0] = buf[chan];
            }
        } catch (IOException boQua) {
            // Mat ket noi giua chung: dong sach phia duoi
        } finally {
            try { docAm.dung(); } catch (Exception boQua) { }
            mayGhi.tat();
            synchronized (khoa) { dongSocketKhoa(); }
            benNhan.doiTrangThai("da_dung");
        }
        return System.currentTimeMillis() - luc;
    }
}
