package vn.r1.bodam;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;

/**
 * Cau noi toi may chu den chay voi quyen shell tren loa (xem den/vn/r1/den/MayChuDen.java) qua TCP
 * 127.0.0.1:18771 (socket noi bo bi SELinux chan). Dong lenh chi la "V <0-255>", "D <rrggbb>" hoac "P".
 */
public final class DenCau {
    private DenCau() { }

    static final int CONG = 18771;

    /** Gui mot dong, tra ve null neu may chu tra "ok", con lai la ly do loi. */
    public static String gui(String dong) {
        Socket s = new Socket();
        try {
            s.connect(new InetSocketAddress("127.0.0.1", CONG), 1500);
            s.setSoTimeout(3000);
            OutputStream o = s.getOutputStream();
            o.write((dong + "\n").getBytes("UTF-8"));
            o.flush();
            String tl = new BufferedReader(new InputStreamReader(s.getInputStream(), "UTF-8")).readLine();
            return "ok".equals(tl) ? null : (tl == null ? "may chu den khong tra loi" : tl);
        } catch (Throwable t) {
            return "may chu den chua chay: " + t;
        } finally {
            try { s.close(); } catch (Throwable ignore) { }
        }
    }

    public static String vien(int muc) { return gui("V " + muc); }

    public static String day(String rgb) { return gui("D " + rgb); }

    /** May chu den co dang chay va chap nhan app nay khong. */
    public static boolean sanSang() { return gui("P") == null; }
}
