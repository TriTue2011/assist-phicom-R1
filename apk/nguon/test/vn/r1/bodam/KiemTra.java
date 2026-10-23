package vn.r1.bodam;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

/** Test Java thuan (khong JUnit): chay bang main, dem passed/failed, exit 1 neu co failed. */
public class KiemTra {
    static int passed = 0, failed = 0;

    static void ok(boolean dk, String ten) {
        if (dk) { passed++; System.out.println("PASS " + ten); }
        else { failed++; System.out.println("FAIL " + ten); }
    }

    // --- Gia lap van chuyen ---
    static class VCgia implements MayGhi.VanChuyen {
        List<byte[]> daGui = new ArrayList<byte[]>();
        boolean mo = false, daDong = false;
        public void mo() { mo = true; }
        public void gui(byte[] k) { daGui.add(Arrays.copyOf(k, k.length)); }
        public void dong() { daDong = true; mo = false; }
        public boolean dangMo() { return mo; }
    }

    // --- Gia lap hen gio + dong ho ---
    static class HenGia implements LogicNut.HenGio {
        Runnable viec; boolean daHuy;
        public void hen(long treMs, Runnable v) { viec = v; daHuy = false; }
        public void huy() { daHuy = true; viec = null; }
        void chay() { Runnable v = viec; viec = null; if (v != null) v.run(); }
    }

    // --- NV247: gia lap dieu khien ghi ---
    static class MayDocGia implements DieuKhienGhi.MayDocAm {
        private final byte[][] cacLan;
        private int chiSo = 0;
        MayDocGia(byte[]... cacLan) { this.cacLan = cacLan; }
        public void batDau() { }
        public int doc(byte[] buf, int batDau, int dai) {
            if (chiSo >= cacLan.length) return -1;
            byte[] d = cacLan[chiSo++];
            int n = Math.min(d.length, dai);
            System.arraycopy(d, 0, buf, batDau, n);
            return n;
        }
        public void dung() { }
    }

    static class SocketGia extends java.net.Socket {
        final java.io.ByteArrayOutputStream dem = new java.io.ByteArrayOutputStream();
        boolean daDong = false;
        SocketGia() { super(); } // khong ket noi that — tranh mang sandbox
        @Override public java.io.OutputStream getOutputStream() { return dem; }
        @Override public void close() { daDong = true; }
        @Override public boolean isClosed() { return daDong; }
        /** Tach cac payload khung tu byte da ghi. */
        List<byte[]> cacPayload() {
            List<byte[]> kq = new ArrayList<byte[]>();
            byte[] b = dem.toByteArray();
            int i = 0;
            while (i + 4 <= b.length) {
                int len = ((b[i] & 0xFF) << 24) | ((b[i + 1] & 0xFF) << 16)
                        | ((b[i + 2] & 0xFF) << 8) | (b[i + 3] & 0xFF);
                if (len < 0 || i + 4 + len > b.length) break;
                byte[] pl = new byte[len];
                System.arraycopy(b, i + 4, pl, 0, len);
                kq.add(pl);
                i += 4 + len;
            }
            return kq;
        }
    }

    static class NhaTaoGia implements DieuKhienGhi.NhaTao {
        enum CheDo { NHANH, TREO, LOI }
        CheDo cheDo = CheDo.NHANH;
        DieuKhienGhi.MayDocAm mayDoc = new MayDocGia();
        volatile SocketGia socketCuoi;
        final java.util.concurrent.CountDownLatch daVaoKetNoi =
                new java.util.concurrent.CountDownLatch(1);
        public java.net.Socket ketNoi(String host, int port) throws IOException {
            daVaoKetNoi.countDown();
            if (cheDo == CheDo.LOI) throw new IOException("ket noi bi tu choi (gia)");
            if (cheDo == CheDo.TREO) {
                try { Thread.sleep(120000); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("bi ngat khi dang ket noi");
                }
            }
            socketCuoi = new SocketGia();
            return socketCuoi;
        }
        public DieuKhienGhi.MayDocAm taoMayDoc(int kichThuocDem) { return mayDoc; }
    }

    static class TrangThaiGia implements DieuKhienGhi.BenNhanTrangThai {
        final List<String> cacTrangThai = new ArrayList<String>();
        public synchronized void doiTrangThai(String tt) { cacTrangThai.add(tt); }
        public synchronized boolean chua(String tt) { return cacTrangThai.contains(tt); }
        public synchronized int dem(String tt) {
            int n = 0;
            for (String x : cacTrangThai) if (x.equals(tt)) n++;
            return n;
        }
        public synchronized String dau() {
            return cacTrangThai.isEmpty() ? null : cacTrangThai.get(0);
        }
    }

    // --- Noi lai: socket dut o lan ghi thu 3, mic doc mai, nha tao theo kich ban ---
    static class SocketDut extends SocketGia {
        int soLanGhi = 0;
        @Override public java.io.OutputStream getOutputStream() {
            return new java.io.OutputStream() {
                @Override public void write(int b) throws IOException { ghi(); }
                @Override public void write(byte[] b, int o, int n) throws IOException { ghi(); }
                private synchronized void ghi() throws IOException {
                    if (++soLanGhi >= 3) throw new IOException("dut (gia)");
                }
            };
        }
    }

    static class MayDocVo implements DieuKhienGhi.MayDocAm {
        public void batDau() { }
        public int doc(byte[] b, int bd, int dai) {
            try { Thread.sleep(5); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); return -1; }
            b[bd] = 1; b[bd + 1] = 2;
            return 2;
        }
        public void dung() { }
    }

    static class NhaTaoKichBan implements DieuKhienGhi.NhaTao {
        enum Kieu { LOI, DUT, SONG }
        final Kieu[] kichBan;
        final java.util.concurrent.atomic.AtomicInteger goi =
                new java.util.concurrent.atomic.AtomicInteger();
        NhaTaoKichBan(Kieu... kichBan) { this.kichBan = kichBan; }
        public java.net.Socket ketNoi(String host, int port) throws IOException {
            Kieu k = kichBan[Math.min(goi.getAndIncrement(), kichBan.length - 1)]; // cuoi lap mai
            if (k == Kieu.LOI) throw new IOException("tu choi (gia)");
            return k == Kieu.DUT ? new SocketDut() : new SocketGia();
        }
        public DieuKhienGhi.MayDocAm taoMayDoc(int kichThuocDem) { return new MayDocVo(); }
    }

    static void doiKhongQua(long ms, DieuKien dk) throws InterruptedException {
        long han = System.currentTimeMillis() + ms;
        while (!dk.dat() && System.currentTimeMillis() < han) Thread.sleep(50);
    }
    interface DieuKien { boolean dat(); }

    public static void main(String[] args) throws Exception {
        // (a) Khung
        byte[] k = Khung.dongGoi(new byte[]{1, 2, 3});
        ok(k.length == 7 && k[0] == 0 && k[1] == 0 && k[2] == 0 && k[3] == 3
                && k[4] == 1 && k[5] == 2 && k[6] == 3, "khung: do dai BE + payload");
        byte[] lon = Khung.dongGoi(new byte[258]);
        ok((lon[2] & 0xFF) == 1 && (lon[3] & 0xFF) == 2, "khung: do dai 258 BE dung");
        byte[] hello = Khung.hello("khoa-mau");
        String helloStr = new String(hello, 4, hello.length - 4, Charset.forName("UTF-8"));
        ok(helloStr.equals("{\"type\":\"hello\",\"version\":1,\"key\":\"khoa-mau\"}"),
                "khung: hello JSON dung (co key)");
        int lenHello = ((hello[0] & 0xFF) << 24) | ((hello[1] & 0xFF) << 16)
                | ((hello[2] & 0xFF) << 8) | (hello[3] & 0xFF);
        ok(lenHello == hello.length - 4, "khung: do dai hello khop payload");
        byte[] end = Khung.end();
        String endStr = new String(end, 4, end.length - 4, Charset.forName("UTF-8"));
        ok(endStr.equals("{\"type\":\"end\"}"), "khung: end JSON dung");

        // (b) Khuech dai
        byte[] mau0 = new byte[]{0x00, 0x40, 0x00, (byte) 0xC0}; // 16384, -16384
        byte[] banSao = Arrays.copyOf(mau0, mau0.length);
        KhuechDai.apDung(mau0, 0.0);
        ok(Arrays.equals(mau0, banSao), "gain: 0 dB khong doi mau");
        byte[] mau6 = new byte[]{0x00, 0x40};
        KhuechDai.apDung(mau6, 6.0);
        int v6 = (short) ((mau6[1] << 8) | (mau6[0] & 0xFF));
        ok(v6 > 32000 && v6 <= 32767, "gain: +6 dB nhan ~2x (16384->" + v6 + ")");
        byte[] mauTran = new byte[]{0x00, 0x70}; // 28672, +6dB = 57344 -> kep 32767
        KhuechDai.apDung(mauTran, 6.0);
        int vT = (short) ((mauTran[1] << 8) | (mauTran[0] & 0xFF));
        ok(vT == 32767, "gain: kep tren 32767 khong tran");
        byte[] mauAm = new byte[]{0x00, (byte) 0x90}; // -28672 -> kep -32768
        KhuechDai.apDung(mauAm, 6.0);
        int vA = (short) ((mauAm[1] << 8) | (mauAm[0] & 0xFF));
        ok(vA == -32768, "gain: kep duoi -32768 khong tran");

        // (c) May trang thai ghi
        VCgia vc = new VCgia();
        MayGhi mg = new MayGhi(vc, "khoa-mau");
        mg.guiPcm(new byte[]{1, 2});
        ok(vc.daGui.isEmpty() && !mg.dangGhi(), "may: tat -> guiPcm khong gui gi");
        mg.bat();
        ok(mg.dangGhi() && vc.daGui.size() == 1, "may: bat -> gui hello truoc");
        String h2 = new String(vc.daGui.get(0), 4, vc.daGui.get(0).length - 4,
                Charset.forName("UTF-8"));
        ok(h2.contains("\"key\":\"khoa-mau\""), "may: hello chua key cau hinh");
        mg.guiPcm(new byte[]{9, 9});
        ok(vc.daGui.size() == 2 && vc.daGui.get(1).length == 6, "may: dang ghi -> gui khung PCM");
        mg.tat();
        ok(!mg.dangGhi() && vc.daDong && vc.daGui.size() == 3, "may: tat -> gui end + dong");
        String e2 = new String(vc.daGui.get(2), 4, vc.daGui.get(2).length - 4,
                Charset.forName("UTF-8"));
        ok(e2.equals("{\"type\":\"end\"}"), "may: khung cuoi la end");
        mg.tat();
        ok(vc.daGui.size() == 3, "may: tat lan 2 khong gui them");

        // (d) Logic nut
        final int[] demMic = {0}, demBt = {0};
        HenGia hen = new HenGia();
        LogicNut nut = new LogicNut(500, hen, new LogicNut.HanhDong() {
            public void doiMic() { demMic[0]++; }
            public void doiBluetooth() { demBt[0]++; }
        });
        nut.nhan();
        ok(demMic[0] == 0 && demBt[0] == 0, "nut: nhan don chua het cho -> chua doi gi");
        hen.chay(); // het khoang cho
        ok(demMic[0] == 1 && demBt[0] == 0, "nut: nhan don -> chi doi mic 1 lan, BT nguyen");
        nut.nhan();
        nut.nhan(); // nhan doi trong khoang
        ok(demBt[0] == 1 && demMic[0] == 1, "nut: nhan doi -> BT doi 1 lan, mic khong doi them");
        hen.chay();
        ok(demMic[0] == 1 && demBt[0] == 1, "nut: sau nhan doi khong phat sinh nhan don");
        nut.nhan();
        hen.chay(); // qua khoang -> nhan don thu nhat
        nut.nhan();
        hen.chay(); // qua khoang -> nhan don thu hai
        ok(demMic[0] == 3 && demBt[0] == 1, "nut: hai nhan cach xa = hai nhan don rieng");

        // (e) NV245: keycode nut giua 195 (da do tren loa)
        ok(CauHinh.KEYCODE_NUT_GIUA_MAC_DINH == 195,
                "nv245: mac dinh keycode nut giua = 195 (da do)");
        ok(LogicNut.laPhimNutGiua(195, 195), "nv245: ma 195 khop cau hinh 195");
        ok(!LogicNut.laPhimNutGiua(24, 195), "nv245: ma khac (24) khong kich hoat");
        ok(!LogicNut.laPhimNutGiua(4, 195), "nv245: ma khac (4) khong kich hoat");
        ok(!LogicNut.laPhimNutGiua(195, CauHinh.KEYCODE_CHUA_DO),
                "nv245: cau hinh chua do (-1) -> khong ma nao kich hoat");

        // Mo phong dispatch: chi ma khop moi goi nhan()
        final int[] demMic2 = {0}, demBt2 = {0};
        HenGia hen2 = new HenGia();
        final LogicNut nut2 = new LogicNut(500, hen2, new LogicNut.HanhDong() {
            public void doiMic() { demMic2[0]++; }
            public void doiBluetooth() { demBt2[0]++; }
        });
        // nhan don bang ma 195 -> doi mic 1 lan
        if (LogicNut.laPhimNutGiua(195, 195)) nut2.nhan();
        hen2.chay();
        ok(demMic2[0] == 1 && demBt2[0] == 0, "nv245: nhan don 195 -> mic doi 1 lan, BT nguyen");
        // nhan doi bang ma 195 -> doi Bluetooth 1 lan
        if (LogicNut.laPhimNutGiua(195, 195)) nut2.nhan();
        if (LogicNut.laPhimNutGiua(195, 195)) nut2.nhan();
        ok(demBt2[0] == 1 && demMic2[0] == 1, "nv245: nhan doi 195 -> BT doi 1 lan, mic khong doi them");
        // nhan bang ma khac 195 -> khong gi xay ra
        if (LogicNut.laPhimNutGiua(87, 195)) nut2.nhan();
        hen2.chay();
        ok(demMic2[0] == 1 && demBt2[0] == 1, "nv245: nhan ma 87 -> khong kich hoat gi");
        // nhan qua dai: app chi tinh 1 su kien DOWN dau (loc repeatCount o dispatch)
        // -> dung nghia 1 nhan don: doi mic dung 1 lan khi het khoang cho
        if (LogicNut.laPhimNutGiua(195, 195)) nut2.nhan();
        hen2.chay();
        ok(demMic2[0] == 2 && demBt2[0] == 1, "nv245: nhan dai (1 DOWN duoc tinh) -> nhan don, mic doi 1 lan");

        System.out.println("TONG (cu NV243/NV245): passed=" + passed + " failed=" + failed);

        // ==== NV247: chay sau cac test cu ====
        try {
            chayTestNv247();
        } catch (Exception e) {
            failed++;
            System.out.println("FAIL nv247: ngoai le " + e);
        }
        System.out.println("TONG NV247 (gom ca cu): passed=" + passed + " failed=" + failed);
        if (failed > 0) System.exit(1);
    }

    static void chayTestNv247() throws Exception {
        final Charset UTF8 = Charset.forName("UTF-8");

        // (f1) TAT khi dang ket noi treo -> khong con luong nao chay
        {
            DieuKhienGhi dk = new DieuKhienGhi();
            NhaTaoGia nt = new NhaTaoGia();
            nt.cheDo = NhaTaoGia.CheDo.TREO;
            TrangThaiGia tt = new TrangThaiGia();
            dk.bat("10.255.255.1", 9, "k", 0.0, nt, tt);
            nt.daVaoKetNoi.await(5, TimeUnit.SECONDS);
            Thread.sleep(300);
            dk.tat();
            doiKhongQua(5000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            ok(dk.soLuongLuocSong() == 0,
                    "nv247-1: TAT khi dang ket noi treo -> khong con luong ghi");
        }

        // (f2) BAT khi luong cu dang treo (khong TAT truoc) -> chi 1 luong
        {
            DieuKhienGhi dk = new DieuKhienGhi();
            NhaTaoGia ntTreo = new NhaTaoGia();
            ntTreo.cheDo = NhaTaoGia.CheDo.TREO;
            TrangThaiGia tt = new TrangThaiGia();
            dk.bat("10.255.255.1", 9, "k", 0.0, ntTreo, tt);
            ntTreo.daVaoKetNoi.await(5, TimeUnit.SECONDS);
            NhaTaoGia ntNhanh = new NhaTaoGia();
            ntNhanh.mayDoc = new MayDocGia(new byte[]{1, 2, 3, 4});
            dk.bat("127.0.0.1", 18765, "k", 0.0, ntNhanh, tt); // BAT de len phien cu
            Thread.sleep(400);
            int dem = dk.soLuongLuocSong();
            ok(dem <= 1, "nv247-1: BAT de len ket noi treo -> toi da 1 luong (thuc te "
                    + dem + ")");
            dk.tat();
            doiKhongQua(5000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            ok(dk.soLuongLuocSong() == 0, "nv247-1: sau TAT khong con luong");
        }

        // (f3) Ket noi hong -> trang thai dang_ket_noi roi loi, luong tu ket thuc
        {
            DieuKhienGhi dk = new DieuKhienGhi();
            NhaTaoGia nt = new NhaTaoGia();
            nt.cheDo = NhaTaoGia.CheDo.LOI;
            TrangThaiGia tt = new TrangThaiGia();
            dk.bat("127.0.0.1", 1, "k", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return tt.cacTrangThai.size() >= 2; }
            });
            ok(tt.cacTrangThai.size() >= 2
                    && "dang_ket_noi".equals(tt.cacTrangThai.get(0))
                    && tt.cacTrangThai.contains("loi"),
                    "nv247-1: ket noi hong -> dang_ket_noi roi loi");
            ok(dk.soLuongLuocSong() == 0,
                    "nv247-1: ket noi hong -> luong tu ket thuc, khong treo");
        }

        // (f4) Duong hanh phuc: dang_ket_noi truoc, dang_gui chi sau hello
        {
            NhaTaoGia nt = new NhaTaoGia();
            nt.mayDoc = new MayDocGia(new byte[]{5, 6, 7, 8});
            final TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi();
            dk.bat("127.0.0.1", 18765, "khoa-mau", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return tt.chua("dang_gui"); }
            });
            ok("dang_ket_noi".equals(tt.dau()) && tt.chua("dang_gui"),
                    "nv247-2: dang_ket_noi truoc, dang_gui chi sau khi gui hello xong");
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            List<byte[]> khung = nt.socketCuoi.cacPayload();
            ok(!khung.isEmpty(), "nv247-2: co khung duoc gui qua van chuyen");
            String f0 = new String(khung.get(0), UTF8);
            ok(f0.contains("\"type\":\"hello\"") && f0.contains("\"key\":\"khoa-mau\""),
                    "nv247-2: khung dau tien la hello co key");
            dk.tat();
        }

        // (f5) Khung PCM luon chan byte du doc le
        {
            NhaTaoGia nt = new NhaTaoGia();
            nt.mayDoc = new MayDocGia(
                    new byte[]{1, 2, 3}, new byte[]{4, 5, 6}, new byte[]{7, 8, 9});
            TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi();
            dk.bat("127.0.0.1", 18765, "k", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            dk.tat();
            List<byte[]> pcm = new ArrayList<byte[]>();
            for (byte[] pl : nt.socketCuoi.cacPayload()) {
                if (pl.length > 0 && pl[0] != '{') pcm.add(pl);
            }
            boolean tatCaChan = true;
            int tong = 0;
            for (byte[] p : pcm) {
                if (p.length % 2 != 0) tatCaChan = false;
                tong += p.length;
            }
            ok(tatCaChan && pcm.size() == 3,
                    "nv247-6: moi khung PCM deu chan byte (" + pcm.size() + " khung)");
            // 9 byte doc (3 lan le) -> byte le cuoi cung bi CAT khi luong ket thuc
            // (dung "cat" trong spec); khong bao gio gui khung le.
            ok(tong == 8, "nv247-6: byte le cuoi bi cat khi ket thuc, tong chan duoc 8 (thuc te "
                    + tong + ")");
        }

        // (f6) Phan tich tham so lenh am start
        {
            CauHinhTuLenh.KetQua q1 =
                    CauHinhTuLenh.phanTich("192.0.2.10", "18765", "bi-mat", null);
            ok(q1.ok && "192.0.2.10".equals(q1.host) && q1.port == 18765
                    && "bi-mat".equals(q1.khoa) && !q1.tiepCan,
                    "nv247-4: lenh hop le -> ok");
            ok(!CauHinhTuLenh.phanTich("", "18765", "k", null).ok,
                    "nv247-4: host rong -> loi");
            ok(!CauHinhTuLenh.phanTich("   ", "18765", "k", null).ok,
                    "nv247-4: host toan khoang trang -> loi");
            ok(!CauHinhTuLenh.phanTich("h", "0", "k", null).ok,
                    "nv247-4: port 0 -> loi");
            ok(!CauHinhTuLenh.phanTich("h", "70000", "k", null).ok,
                    "nv247-4: port 70000 -> loi");
            ok(!CauHinhTuLenh.phanTich("h", "abc", "k", null).ok,
                    "nv247-4: port chu -> loi");
            CauHinhTuLenh.KetQua q2 =
                    CauHinhTuLenh.phanTich("h", "18765", "", Boolean.TRUE);
            ok(q2.ok && "".equals(q2.khoa) && q2.tiepCan,
                    "nv247-4: khoa rong duoc phep, tiep_can=true");
        }

        // (f7) Noi lai: ket noi dut -> doi roi noi lai, KHONG phat "loi"/"da_dung" giua chung
        {
            final NhaTaoKichBan nt = new NhaTaoKichBan(NhaTaoKichBan.Kieu.DUT, NhaTaoKichBan.Kieu.SONG);
            final TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi(new DieuKhienGhi.NoiLai(20, 80, 0, 3));
            dk.bat("127.0.0.1", 18765, "k", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return tt.dem("dang_gui") >= 2; }
            });
            ok(nt.goi.get() >= 2 && tt.dem("dang_gui") >= 2 && tt.chua("cho_noi_lai"),
                    "noi-lai: dut giua chung -> cho_noi_lai roi noi lai (" + nt.goi.get() + " lan ket noi)");
            ok(!tt.chua("loi") && !tt.chua("da_dung") && dk.soLuongLuocSong() == 1,
                    "noi-lai: khong phat loi/da_dung khi chua tat, van dung mot luong");
            dk.tat();
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            ok(dk.soLuongLuocSong() == 0 && tt.dem("da_dung") == 1,
                    "noi-lai: tat() -> luong thoat, da_dung dung mot lan");
        }

        // (f8) Chua tung noi duoc: that bai lien tiep toi han thi bo cuoc bang "loi", dung han
        {
            final NhaTaoKichBan nt = new NhaTaoKichBan(NhaTaoKichBan.Kieu.LOI);
            final TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi(new DieuKhienGhi.NoiLai(10, 40, 0, 3));
            dk.bat("127.0.0.1", 1, "k", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return tt.chua("loi"); }
            });
            ok(tt.chua("loi") && nt.goi.get() == 3 && tt.dem("cho_noi_lai") == 2,
                    "noi-lai: chua tung noi duoc -> 3 lan roi loi (" + nt.goi.get() + " lan, "
                            + tt.dem("cho_noi_lai") + " lan cho)");
            doiKhongQua(2000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            ok(dk.soLuongLuocSong() == 0, "noi-lai: bo cuoc -> luong ket thuc");
        }

        // (f9) Da tung noi duoc: that bai tiep khong bao gio bo cuoc
        {
            final NhaTaoKichBan nt = new NhaTaoKichBan(NhaTaoKichBan.Kieu.DUT, NhaTaoKichBan.Kieu.LOI);
            final TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi(new DieuKhienGhi.NoiLai(10, 30, 0, 3));
            dk.bat("127.0.0.1", 1, "k", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return nt.goi.get() >= 8; }
            });
            ok(nt.goi.get() >= 8 && !tt.chua("loi") && dk.soLuongLuocSong() == 1,
                    "noi-lai: da tung noi -> van thu tiep qua han chua-tung-noi (" + nt.goi.get() + " lan)");
            dk.tat();
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            ok(dk.soLuongLuocSong() == 0, "noi-lai: tat() sau nhieu lan that bai -> luong thoat");
        }

        // (f10) tat() luc dang cho noi lai: thoat ngay, khong ket noi them
        {
            final NhaTaoKichBan nt = new NhaTaoKichBan(NhaTaoKichBan.Kieu.DUT, NhaTaoKichBan.Kieu.LOI);
            final TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi(new DieuKhienGhi.NoiLai(60000, 60000, 0, 3));
            dk.bat("127.0.0.1", 1, "k", 0.0, nt, tt);
            doiKhongQua(3000, new DieuKien() {
                public boolean dat() { return tt.chua("cho_noi_lai"); }
            });
            int truoc = nt.goi.get();
            dk.tat();
            doiKhongQua(2000, new DieuKien() {
                public boolean dat() { return dk.soLuongLuocSong() == 0; }
            });
            Thread.sleep(200);
            ok(dk.soLuongLuocSong() == 0 && nt.goi.get() == truoc && tt.dem("da_dung") == 1,
                    "noi-lai: tat() luc dang cho -> thoat ngay, khong ket noi them");
        }

        // (f11) Khung dieu khien den nhac tu HA: chi nhan dung dinh dang, ngoai khoang bi chan
        {
            final List<String> daGui = new ArrayList<String>();
            LenhDieuKhien.Dich gia = new LenhDieuKhien.Dich() {
                public String guiDenNhac(int ma, int giaTri) { daGui.add(ma + ":" + giaTri); return null; }
            };
            ok(LenhDieuKhien.xuLy("{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":50}", gia) == null
                    && daGui.contains("65:50"), "den-nhac: khung hop le -> gui luma 50");
            ok(LenhDieuKhien.xuLy("{\"type\":\"den_nhac\",\"ma\":66,\"gia_tri\":4}", gia) == null
                    && daGui.contains("66:4"), "den-nhac: sac do 4");
            ok(LenhDieuKhien.xuLy("{\"type\":\"den_nhac\",\"ma\":64,\"gia_tri\":1}", gia) == null
                    && daGui.contains("64:1"), "den-nhac: bat 1");
            int truoc = daGui.size();
            String[] hong = {
                "{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":101}",        // luma ngoai khoang
                "{\"type\":\"den_nhac\",\"ma\":66,\"gia_tri\":0}",          // chroma 0 khong hop le
                "{\"type\":\"den_nhac\",\"ma\":64,\"gia_tri\":2}",          // bat/tat chi 0/1
                "{\"type\":\"den_nhac\",\"ma\":99,\"gia_tri\":1}",          // ma la
                "{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":-5}",         // am
                "{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":5000}",       // qua so chu so
                "{\"gia_tri\":50,\"ma\":65,\"type\":\"den_nhac\"}",         // sai thu tu khoa
                "{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":50,\"x\":1}", // them truong
                "{\"type\":\"hello\",\"version\":1}",                       // khung khac
                "{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":50} ",        // thua khoang trang
                "", "{", "khong phai json", null
            };
            boolean tatCaBiChan = true;
            for (String h : hong) if (LenhDieuKhien.xuLy(h, gia) == null) tatCaBiChan = false;
            ok(tatCaBiChan && daGui.size() == truoc, "den-nhac: khung hong/ngoai khoang/la khong bao gio gui");
            StringBuilder dai = new StringBuilder("{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":50");
            for (int i = 0; i < 200; i++) dai.append(' ');
            ok(LenhDieuKhien.xuLy(dai.append('}').toString(), gia) != null && daGui.size() == truoc,
                    "den-nhac: khung qua dai bi bo");
            LenhDieuKhien.Dich no = new LenhDieuKhien.Dich() {
                public String guiDenNhac(int ma, int giaTri) { throw new IllegalStateException("no"); }
            };
            ok(LenhDieuKhien.xuLy("{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":50}", no) != null,
                    "den-nhac: dich nem loi -> tra ly do, khong nem ra ngoai");
            ok(TrungTamTin.hopLeDenNhac(65, 0) == null && TrungTamTin.hopLeDenNhac(65, 100) == null
                    && TrungTamTin.hopLeDenNhac(66, 1) == null && TrungTamTin.hopLeDenNhac(66, 100) == null,
                    "den-nhac: bien khoang luma 0-100, chroma 1-100 hop le");
        }

        // (f11b) Den vien / den day / hoi san sang: khung chat, gia tri ngoai khoang bi chan, hang doi "moi nhat thang"
        {
            final List<String> daGui = new ArrayList<String>();
            LenhDieuKhien.DichDen gia = new LenhDieuKhien.DichDen() {
                public String guiVien(int muc) { daGui.add("V" + muc); return null; }
                public String guiDay(String rgb) { daGui.add("D" + rgb); return null; }
                public boolean sanSang() { return true; }
                public String guiHieuUng(int id) { daGui.add("E" + id); return null; }
            };
            ok(LenhDieuKhien.loaiDen("{\"type\":\"den_vien\",\"muc\":128}") == 1
                    && LenhDieuKhien.loaiDen("{\"type\":\"den_day\",\"rgb\":\"00ff7f\"}") == 2
                    && LenhDieuKhien.loaiDen("{\"type\":\"den_hoi\"}") == 3, "den: nhan dang ba loai khung");
            ok(LenhDieuKhien.xuLyDen("{\"type\":\"den_vien\",\"muc\":255}", gia) == null
                    && LenhDieuKhien.xuLyDen("{\"type\":\"den_vien\",\"muc\":0}", gia) == null
                    && LenhDieuKhien.xuLyDen("{\"type\":\"den_day\",\"rgb\":\"0080ff\"}", gia) == null
                    && daGui.toString().equals("[V255, V0, D0080ff]"), "den: khung hop le -> goi dich dung gia tri");
            int truoc = daGui.size();
            String[] hong = {
                "{\"type\":\"den_vien\",\"muc\":256}", "{\"type\":\"den_vien\",\"muc\":-1}",
                "{\"type\":\"den_vien\",\"muc\":1000}", "{\"type\":\"den_vien\",\"muc\":\"5\"}",
                "{\"type\":\"den_day\",\"rgb\":\"00FF7F\"}", "{\"type\":\"den_day\",\"rgb\":\"00ff7\"}",
                "{\"type\":\"den_day\",\"rgb\":\"00ff7f0\"}", "{\"type\":\"den_day\",\"rgb\":\"gg0000\"}",
                "{\"type\":\"den_day\",\"rgb\":\"00ff7f\",\"x\":1}", "{\"muc\":5,\"type\":\"den_vien\"}",
                "{\"type\":\"den_vien\",\"muc\":5} ", "{\"type\":\"den_hoi\",\"x\":1}", "", "{", null
            };
            boolean chan = true;
            for (String h : hong) {
                // 256 dung dinh dang (3 chu so) nen duoc nhan dang nhung xuLyDen phai chan o kiem khoang
                boolean laDinhDangDung = h != null && h.equals("{\"type\":\"den_vien\",\"muc\":256}");
                if ((!laDinhDangDung && LenhDieuKhien.loaiDen(h) != 0) || LenhDieuKhien.xuLyDen(h, gia) == null) chan = false;
            }
            ok(chan && daGui.size() == truoc, "den: khung hong/ngoai khoang/lech dinh dang khong bao gio gui");
            LenhDieuKhien.DichDen no = new LenhDieuKhien.DichDen() {
                public String guiVien(int muc) { throw new IllegalStateException("no"); }
                public String guiDay(String rgb) { throw new IllegalStateException("no"); }
                public boolean sanSang() { throw new IllegalStateException("no"); }
                public String guiHieuUng(int id) { daGui.add("E" + id); return null; }
            };
            ok(LenhDieuKhien.xuLyDen("{\"type\":\"den_vien\",\"muc\":5}", no) != null, "den: dich nem loi -> tra ly do");

            // Am luong nhac: dinh dang khung chat, khoang 0..toiDa, dich nem loi khong giet luong
            final List<Integer> amDat = new ArrayList<Integer>();
            LenhDieuKhien.DichAm am = new LenhDieuKhien.DichAm() {
                public String dat(int muc) { amDat.add(muc); return null; }
                public int muc() { return 7; }
                public int toiDa() { return 15; }
            };
            ok(LenhDieuKhien.laAmLuong("{\"type\":\"am_luong\",\"muc\":8}") && LenhDieuKhien.laAmLuong("{\"type\":\"am_hoi\"}"),
                    "am luong: nhan dang khung am_luong va am_hoi");
            boolean amChan = true;
            for (String h : new String[] {null, "", "rac", "{\"type\":\"am_luong\",\"muc\":-1}", "{\"type\":\"am_luong\",\"muc\":100}",
                    "{\"type\":\"am_luong\",\"muc\":\"8\"}", "{\"type\":\"am_luong\", \"muc\":8}", "{\"muc\":8,\"type\":\"am_luong\"}",
                    "{\"type\":\"den_vien\",\"muc\":8}"}) {
                if (LenhDieuKhien.laAmLuong(h)) amChan = false;
            }
            ok(amChan, "am luong: khung hong/lech dinh dang khong duoc nhan dang");
            ok(LenhDieuKhien.xuLyAm("{\"type\":\"am_luong\",\"muc\":8}", am) == null && amDat.toString().equals("[8]"),
                    "am luong: muc 8 duoc dat dung mot lan");
            amDat.clear();
            ok(LenhDieuKhien.xuLyAm("{\"type\":\"am_luong\",\"muc\":16}", am) != null && amDat.isEmpty(),
                    "am luong: muc 16 > toi da 15 bi chan, khong goi dich");
            ok(LenhDieuKhien.xuLyAm("{\"type\":\"am_hoi\"}", am) == null && amDat.isEmpty(),
                    "am luong: am_hoi chi bao lai, khong dat");
            LenhDieuKhien.DichAm amNo = new LenhDieuKhien.DichAm() {
                public String dat(int muc) { throw new IllegalStateException("no"); }
                public int muc() { throw new IllegalStateException("no"); }
                public int toiDa() { throw new IllegalStateException("no"); }
            };
            ok(LenhDieuKhien.xuLyAm("{\"type\":\"am_luong\",\"muc\":8}", amNo) != null, "am luong: dich nem loi -> tra ly do, khong nem ra ngoai");
            ok(new String(Khung.amLuong(7, 15), java.nio.charset.Charset.forName("UTF-8")).endsWith("{\"type\":\"am_luong_trang_thai\",\"muc\":7,\"toi_da\":15}"),
                    "am luong: khung trang thai dung hop dong voi HA");

            // Hang doi: gui lien tuc thi chi muc moi nhat cua tung loai; hoi san sang -> bao lai; dich nem loi khong giet luong
            final List<Boolean> baoLai = new ArrayList<Boolean>();
            daGui.clear();
            DenHangDoi h = new DenHangDoi(gia, new DenHangDoi.Ben() {
                public void baoSanSang(boolean b) { baoLai.add(b); }
            });
            h.dat("{\"type\":\"den_vien\",\"muc\":10}");
            h.dat("{\"type\":\"den_vien\",\"muc\":20}");
            h.dat("{\"type\":\"den_day\",\"rgb\":\"010203\"}");
            h.dat("{\"type\":\"den_day\",\"rgb\":\"040506\"}");
            ok(!h.dat("{\"type\":\"den_nhac\",\"ma\":65,\"gia_tri\":5}") && !h.dat(null) && !h.dat("rac"),
                    "den: hang doi tu choi khung khong phai den");
            h.dat("{\"type\":\"den_hoi\"}");
            ok(h.chayMotLuot() && daGui.toString().equals("[V20, D040506]") && baoLai.toString().equals("[true]"),
                    "den: hang doi giu muc moi nhat (V20, D040506) va tra loi hoi san sang");
            ok(!h.chayMotLuot(), "den: het viec thi chayMotLuot tra false");
            DenHangDoi hn = new DenHangDoi(no, new DenHangDoi.Ben() { public void baoSanSang(boolean b) { baoLai.add(b); } });
            hn.dat("{\"type\":\"den_hoi\"}");
            hn.chayMotLuot();
            ok(baoLai.toString().equals("[true, false]"), "den: dich loi -> bao HA khong san sang, khong nem ra");
            // Luong that: dung duoc
            final DenHangDoi hl = new DenHangDoi(gia, new DenHangDoi.Ben() { public void baoSanSang(boolean b) { } });
            Thread tl = new Thread(hl);
            tl.start();
            hl.dat("{\"type\":\"den_vien\",\"muc\":77}");
            long han = System.currentTimeMillis() + 2000;
            while (!daGui.contains("V77") && System.currentTimeMillis() < han) Thread.sleep(10);
            hl.dungLai();
            tl.join(2000);
            ok(daGui.contains("V77") && !tl.isAlive(), "den: luong hang doi xu ly roi dung duoc");

            byte[] tt = Khung.trangThaiDen(true), tf = Khung.trangThaiDen(false);
            ok(new String(tt, 4, tt.length - 4, "UTF-8").equals("{\"type\":\"den_trang_thai\",\"san_sang\":true,\"che_do\":\"firmware\"}")
                    && new String(tf, 4, tf.length - 4, "UTF-8").equals("{\"type\":\"den_trang_thai\",\"san_sang\":false,\"che_do\":\"firmware\"}")
                    && tt[3] == (byte) (tt.length - 4), "den: khung trang thai dung dinh dang HA doi");
        }

        // (f11e) Hieu ung den co san cua firmware (cach AI box): chi ID trong danh sach cho phep, khung chat, khong can may chu
        {
            final List<String> daGui2 = new ArrayList<String>();
            LenhDieuKhien.DichDen gia2 = new LenhDieuKhien.DichDen() {
                public String guiVien(int muc) { return "khong dung"; }
                public String guiDay(String rgb) { return "khong dung"; }
                public boolean sanSang() { return true; }
                public String guiHieuUng(int id) { daGui2.add("E" + id); return null; }
            };
            ok(LenhDieuKhien.loaiDen("{\"type\":\"den_hieu_ung\",\"id\":501}") == 4, "hieu ung: nhan dang khung");
            int[] tot = {200, 201, 202, 203, 204, 206, 251, 252, 253, 254, 255, 500, 501, 502, 503, 504, 505, 510, 511, 512, 513, 514, 515,
                    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24};
            boolean heTot = true;
            for (int id : tot) {
                if (LenhDieuKhien.xuLyDen("{\"type\":\"den_hieu_ung\",\"id\":" + id + "}", gia2) != null) heTot = false;
            }
            ok(heTot && daGui2.size() == tot.length && daGui2.get(0).equals("E200"), "hieu ung: moi ID cho phep deu duoc gui");
            int truoc2 = daGui2.size();
            String[] xau = {"{\"type\":\"den_hieu_ung\",\"id\":0}", "{\"type\":\"den_hieu_ung\",\"id\":205}",
                "{\"type\":\"den_hieu_ung\",\"id\":999}", "{\"type\":\"den_hieu_ung\",\"id\":4096}",
                "{\"type\":\"den_hieu_ung\",\"id\":-1}", "{\"type\":\"den_hieu_ung\",\"id\":\"501\"}",
                "{\"id\":501,\"type\":\"den_hieu_ung\"}", "{\"type\":\"den_hieu_ung\",\"id\":501,\"x\":1}",
                "{\"type\":\"den_hieu_ung\",\"id\":501} "};
            boolean chan2 = true;
            for (String x : xau) if (LenhDieuKhien.xuLyDen(x, gia2) == null) chan2 = false;
            ok(chan2 && daGui2.size() == truoc2, "hieu ung: ID la/ngoai danh sach/khung lech dinh dang khong bao gio gui");
            final List<Boolean> bao = new ArrayList<Boolean>();
            DenHangDoi hh = new DenHangDoi(gia2, new DenHangDoi.Ben() { public void baoSanSang(boolean b) { bao.add(b); } });
            daGui2.clear();
            hh.dat("{\"type\":\"den_hieu_ung\",\"id\":500}");
            hh.dat("{\"type\":\"den_hieu_ung\",\"id\":501}");     // moi nhat thang o o day
            hh.dat("{\"type\":\"den_hieu_ung\",\"id\":505}");
            hh.dat("{\"type\":\"den_hieu_ung\",\"id\":503}");     // moi nhat thang o o vien
            hh.chayMotLuot();
            ok(daGui2.toString().equals("[E501, E503]"), "hieu ung: hang doi giu moi nhat cua day (501) va vien (503), day truoc vien: " + daGui2);
            ok(!TrungTamTin.laHieuUngHopLe(0) && TrungTamTin.laHieuUngHopLe(503) && !TrungTamTin.laHieuUngHopLe(205),
                    "hieu ung: danh sach cho phep");
        }

        // (f11c) May chu den quyen shell: chi nhan dung ba lenh, khong bao gio chay chuoi do nguoi gui dua vao
        {
            vn.r1.den.MayChuDen.Lenh l = vn.r1.den.MayChuDen.phanTich("V 128");
            ok(l != null && l.matNa.equals("7fffff8000") && l.rgb.equals("808080"), "may chu den: V 128 -> vien, trang 808080");
            l = vn.r1.den.MayChuDen.phanTich("V 0");
            ok(l.rgb.equals("000000"), "may chu den: V 0 -> tat vien");
            l = vn.r1.den.MayChuDen.phanTich("D 00ff7f");
            ok(l.matNa.equals("7fff") && l.rgb.equals("00ff7f"), "may chu den: D -> day RGB");
            ok(vn.r1.den.MayChuDen.phanTich("P") == null, "may chu den: P -> chi hoi san sang");
            String[] xau = {"V 256", "V -1", "V 5; reboot", "D 00FF7F", "D 00ff7", "D 00ff7f0", "rm -rf /", "V  5", "v 5", "", "V 1234",
                "D 00ff7f; id", "P P"};
            boolean het = true;
            for (String x : xau) {
                try { vn.r1.den.MayChuDen.phanTich(x); het = false; } catch (IllegalArgumentException ok) { }
            }
            try { vn.r1.den.MayChuDen.phanTich(null); het = false; } catch (IllegalArgumentException ok) { }
            ok(het, "may chu den: lenh la/ngoai khoang/chen chuoi bi tu choi");
        }

        // (f11d) Ghep khoa tu dong: bi tu choi lien tiep -> xin khoa tu HA (co gioi han tan suat), nhan duoc thi noi lai ngay
        {
            final java.util.List<String> goiNoi = java.util.Collections.synchronizedList(new ArrayList<String>());
            DieuKhienGhi.NhaTao chiNhanCongMoi = new DieuKhienGhi.NhaTao() {
                public java.net.Socket ketNoi(String host, int port) throws IOException {
                    goiNoi.add(host + ":" + port);
                    if (port != 18770) throw new IOException("tu choi (gia)");
                    return new SocketGia();
                }
                public DieuKhienGhi.MayDocAm taoMayDoc(int n) { return new MayDocVo(); }
            };
            final java.util.List<String> daLuu = java.util.Collections.synchronizedList(new ArrayList<String>());
            final java.util.concurrent.atomic.AtomicInteger soLanXin = new java.util.concurrent.atomic.AtomicInteger();
            final java.util.List<String> hostXin = java.util.Collections.synchronizedList(new ArrayList<String>());
            DieuKhienGhi.GhepKhoa ghepGia = new DieuKhienGhi.GhepKhoa() {
                public String[] thu(String host) { soLanXin.incrementAndGet(); hostXin.add(host); return new String[]{"18770", "khoa-moi"}; }
                public void luu(int port, String khoa) { daLuu.add(port + "/" + khoa); }
            };
            TrangThaiGia tt = new TrangThaiGia();
            final DieuKhienGhi dk = new DieuKhienGhi(new DieuKhienGhi.NoiLai(10, 40, 0, 50));
            dk.datGhep(ghepGia);
            dk.bat("ha.example", 18765, "khoa-cu", 0.0, chiNhanCongMoi, tt);
            doiKhongQua(4000, new DieuKien() { public boolean dat() { return goiNoi.contains("ha.example:18770"); } });
            ok(goiNoi.contains("ha.example:18770") && soLanXin.get() == 1 && hostXin.get(0).equals("ha.example")
                    && daLuu.size() == 1 && daLuu.get(0).equals("18770/khoa-moi"),
                    "ghep: bi tu choi -> xin khoa dung host, luu cong+khoa moi, noi lai bang cong moi " + goiNoi);
            dk.tat();
            doiKhongQua(2000, new DieuKien() { public boolean dat() { return dk.soLuongLuocSong() == 0; } });

            // HA khong trao (da ghep / sai IP): xin RAT THUA (cach nhau >= 20 s), khong dap lien tuc vao HA
            final java.util.concurrent.atomic.AtomicInteger xin2 = new java.util.concurrent.atomic.AtomicInteger();
            DieuKhienGhi.GhepKhoa tuChoi = new DieuKhienGhi.GhepKhoa() {
                public String[] thu(String host) { xin2.incrementAndGet(); return null; }
                public void luu(int port, String khoa) { throw new IllegalStateException("khong duoc luu"); }
            };
            final DieuKhienGhi dk2 = new DieuKhienGhi(new DieuKhienGhi.NoiLai(10, 40, 0, 500));
            dk2.datGhep(tuChoi);
            dk2.bat("ha.example", 18765, "khoa-cu", 0.0, new NhaTaoKichBan(NhaTaoKichBan.Kieu.LOI), new TrangThaiGia());
            Thread.sleep(1500);
            dk2.tat();
            ok(xin2.get() == 1, "ghep: HA khong trao -> chi xin 1 lan trong 1,5 s (gioi han tan suat), da xin " + xin2.get());
            doiKhongQua(2000, new DieuKien() { public boolean dat() { return dk2.soLuongLuocSong() == 0; } });

            // Khong dat ghep (hanh vi cu): khong goi gi them
            ok(Ghep.phanTichTraLoi("{\"port\":18765,\"key\":\"abcDEF_123-xyz9\"}") != null
                    && Ghep.phanTichTraLoi("{\"port\":18765,\"key\":\"abcDEF_123-xyz9\"}")[1].equals("abcDEF_123-xyz9")
                    && Ghep.phanTichTraLoi("{\"port\":70000,\"key\":\"abcDEF_123-xyz9\"}") == null
                    && Ghep.phanTichTraLoi("{\"port\":0,\"key\":\"abcDEF_123-xyz9\"}") == null
                    && Ghep.phanTichTraLoi("{\"port\":1,\"key\":\"ngan\"}") == null
                    && Ghep.phanTichTraLoi("{\"loi\":\"x\"}") == null && Ghep.phanTichTraLoi(null) == null,
                    "ghep: doc tra loi HA chat (cong 1..65535, khoa 8..128 ky tu hop le)");
            ok(Ghep.hostHopLe("192.0.2.200") && Ghep.hostHopLe("ha.example")
                    && !Ghep.hostHopLe("a/b") && !Ghep.hostHopLe("a:80") && !Ghep.hostHopLe("a b") && !Ghep.hostHopLe("")
                    && !Ghep.hostHopLe(null) && !Ghep.hostHopLe("h@evil"),
                    "ghep: host chi gom ky tu ten/IP, khong chen duoc duong dan/cong/tai khoan vao URL");
        }

        // (f12) Ban phat hanh: cua cau hinh bang intent chi mo LAN DAU; tu bat mic chi khi du cau hinh
        {
            ok(CauHinhTuLenh.choPhepDoiCauHinh("", "") && CauHinhTuLenh.choPhepDoiCauHinh(null, null),
                    "cau-hinh: chua cau hinh -> cho phep nhan lenh");
            ok(CauHinhTuLenh.choPhepDoiCauHinh("192.0.2.10", "") && CauHinhTuLenh.choPhepDoiCauHinh("", "k"),
                    "cau-hinh: thieu host hoac khoa -> van coi la chua xong, cho phep");
            ok(!CauHinhTuLenh.choPhepDoiCauHinh("192.0.2.10", "khoa") && !CauHinhTuLenh.choPhepDoiCauHinh(" h ", "k"),
                    "cau-hinh: DA cau hinh -> tu choi lenh doi (app khac khong chuyen duoc dich den mic)");
            ok(CauHinhTuLenh.nenTuBat("192.0.2.10", 18765, "khoa"), "tu-bat: du host/port/khoa -> tu bat");
            ok(!CauHinhTuLenh.nenTuBat("", 18765, "khoa") && !CauHinhTuLenh.nenTuBat("h", 0, "khoa")
                    && !CauHinhTuLenh.nenTuBat("h", 70000, "khoa") && CauHinhTuLenh.nenTuBat("h", 18765, "")
                    && !CauHinhTuLenh.nenTuBat(null, 1, "k") && CauHinhTuLenh.nenTuBat("h", 1, null),
                    "tu-bat: thieu host/port hop le/khoa -> KHONG tu bat mic");
            ok(CauHinhTuLenh.hanhDongTuBat("android.intent.action.BOOT_COMPLETED")
                    && CauHinhTuLenh.hanhDongTuBat("android.intent.action.QUICKBOOT_POWERON")
                    && CauHinhTuLenh.hanhDongTuBat("android.intent.action.MY_PACKAGE_REPLACED"),
                    "tu-bat: 3 tin hieu (khoi dong, khoi dong nhanh, cai de APK) deu cho phep tu bat");
            ok(!CauHinhTuLenh.hanhDongTuBat(null) && !CauHinhTuLenh.hanhDongTuBat("")
                    && !CauHinhTuLenh.hanhDongTuBat("vn.r1.bodam.TAT") && !CauHinhTuLenh.hanhDongTuBat("vn.r1.bodam.BAT")
                    && !CauHinhTuLenh.hanhDongTuBat("android.intent.action.USER_PRESENT")
                    && !CauHinhTuLenh.hanhDongTuBat("android.intent.action.BOOT_COMPLETED.gia")
                    && !CauHinhTuLenh.hanhDongTuBat("android.intent.action.boot_completed"),
                    "tu-bat: tin hieu la, rong, null, lenh tat/bat noi bo, sai chu hoa/thuong -> KHONG tu bat");
        }
    }
}
