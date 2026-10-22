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
                    && !CauHinhTuLenh.nenTuBat("h", 70000, "khoa") && !CauHinhTuLenh.nenTuBat("h", 18765, "")
                    && !CauHinhTuLenh.nenTuBat(null, 1, "k") && !CauHinhTuLenh.nenTuBat("h", 1, null),
                    "tu-bat: thieu host/port hop le/khoa -> KHONG tu bat mic");
        }
    }
}
