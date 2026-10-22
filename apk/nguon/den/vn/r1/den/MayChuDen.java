package vn.r1.den;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * May chu den tren loa R1, chay voi quyen SHELL (uid 2000) boi `app_process` (xem scripts/den_loa.sh).
 * Ly do: SELinux (Enforcing) chan ung dung thuong mo /sys/class/leds/.../led_color, con domain shell thi duoc.
 *
 * Lang nghe CHI tren 127.0.0.1 (khong ra mang LAN). Socket noi bo (abstract/UNIX) KHONG dung duoc: SELinux
 * chan ung dung thuong ket noi toi domain shell (do 22/10/2026: "Permission denied"). Nen moi app tren loa
 * deu goi duoc, vi vay may chu chi chay DUNG hai lenh `lights_test set <mat na> <rgb>` voi mat na trong
 * danh sach cho phep va rgb 6 so hex; khong bao gio chay chuoi do nguoi gui dua vao. Hau qua toi da khi bi
 * lam dung: doi mau/do sang den.
 *
 * Giao thuc (moi lenh mot dong, tra lai "ok" hoac "loi <ly do>"):
 *   V <0-255>     den vien (CHI TRANG): muc trang, 0 = tat
 *   D <rrggbb>    den day (RGB)
 *   P             hoi san sang
 */
public final class MayChuDen {
    private MayChuDen() { }

    public static final int CONG = 18771;
    public static final String MAT_NA_VIEN = "7fffff8000";
    public static final String MAT_NA_DAY = "7fff";
    private static final String LIGHTS_TEST = "/system/bin/lights_test";

    /** Mot lenh da kiem: mat na + rgb de chay lights_test, hoac null neu chi la hoi san sang. */
    public static final class Lenh {
        public final String matNa, rgb;
        Lenh(String matNa, String rgb) { this.matNa = matNa; this.rgb = rgb; }
    }

    /** Phan tich mot dong lenh. Tra ve null neu "P"; nem IllegalArgumentException (ly do) neu khong hop le. */
    public static Lenh phanTich(String dong) {
        if (dong == null) throw new IllegalArgumentException("dong rong");
        String d = dong.trim();
        if (d.equals("P")) return null;
        if (d.length() > 16) throw new IllegalArgumentException("dong qua dai");
        if (d.matches("V [0-9]{1,3}")) {
            int v = Integer.parseInt(d.substring(2));
            if (v > 255) throw new IllegalArgumentException("muc vien ngoai 0-255");
            String h = String.format("%02x", v);
            return new Lenh(MAT_NA_VIEN, h + h + h);       // vien CHI TRANG: ba kenh bang nhau
        }
        if (d.matches("D [0-9a-f]{6}")) return new Lenh(MAT_NA_DAY, d.substring(2));
        throw new IllegalArgumentException("lenh la");
    }

    static String chay(Lenh l) {
        try {
            Process p = new ProcessBuilder(LIGHTS_TEST, "set", l.matNa, l.rgb).redirectErrorStream(true).start();
            InputStream in = p.getInputStream();
            byte[] b = new byte[256];
            int n = in.read(b);
            int ma = p.waitFor();
            return ma == 0 ? "ok" : "loi lights_test thoat " + ma + (n > 0 ? " " + new String(b, 0, n).trim() : "");
        } catch (Exception e) {
            return "loi " + e;
        }
    }

    /** Xu ly mot dong, tra loi can gui lai. */
    static String xuLy(String dong) {
        try {
            Lenh l = phanTich(dong);
            return l == null ? "ok" : chay(l);
        } catch (IllegalArgumentException e) {
            return "loi " + e.getMessage();
        }
    }

    public static void main(String[] args) throws IOException {
        try {
            // Tach khoi phien adb (khong dung mot minh: xem scripts/den_loa.sh).
            android.system.Os.setsid();
        } catch (Exception e) {
            System.err.println("khong tach duoc phien (van chay): " + e);
        }
        ServerSocket may = new ServerSocket(CONG, 4, InetAddress.getByName("127.0.0.1"));
        System.out.println("may chu den san sang (127.0.0.1:" + CONG + ")");
        while (true) {
            Socket s = may.accept();
            try {
                s.setSoTimeout(5000);
                BufferedReader r = new BufferedReader(new InputStreamReader(s.getInputStream(), "UTF-8"));
                OutputStream o = s.getOutputStream();
                String dong;
                while ((dong = r.readLine()) != null) {
                    o.write((xuLy(dong) + "\n").getBytes("UTF-8"));
                    o.flush();
                }
            } catch (IOException e) {
                // ket noi hong: bo, cho ket noi tiep
            } finally {
                try { s.close(); } catch (IOException ignore) { }
            }
        }
    }
}
