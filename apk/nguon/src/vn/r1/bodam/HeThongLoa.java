package vn.r1.bodam;

import android.bluetooth.BluetoothAdapter;
import android.content.Context;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.StatFs;

import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.Locale;

/**
 * Thong tin he thong cua loa (CPU, RAM, bo nho, WiFi, Bluetooth, thoi gian chay) doc bang API thuong cua Android va /proc,
 * KHONG can ADB. Ket qua la van ban chia khoi "---ten" DUNG dinh dang ma duong ADB cua HA dang phan tich
 * (he_thong.phan_tich), nen HA dung chung mot ham phan tich. KHONG doc so se-ri, dia chi MAC hay BSSID.
 */
public final class HeThongLoa {
    private HeThongLoa() { }

    /** Nguon du lieu (that hoac gia). Moi ham tra null neu khong doc duoc. */
    public interface Nguon {
        String doc(String duongDan);
        String df();
        String wifi();
        Boolean bluetooth();
    }

    /** Ghep van ban: bo nho (4 dong dau cua /proc/meminfo), tai, mau CPU, nhan/tan so, /data, WiFi, Bluetooth, uptime. */
    public static String tao(Nguon n) {
        StringBuilder b = new StringBuilder();
        String mem = n.doc("/proc/meminfo");
        if (mem != null) b.append(dongDau(mem, 4)).append('\n');
        b.append("---load\n").append(chon(n.doc("/proc/loadavg"))).append('\n');
        b.append("---s2\n").append(dongCpu(n.doc("/proc/stat"))).append('\n');
        b.append("---cpu\n").append(chon(n.doc("/sys/devices/system/cpu/online"))).append('\n');
        String tanSo = n.doc("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq");
        if (tanSo != null) b.append(chon(tanSo)).append('\n');
        String df = n.df();
        if (df != null) b.append("---df\n").append(df).append('\n');
        String wifi = n.wifi();
        if (wifi != null) b.append("---wifi\n").append(wifi).append('\n');
        Boolean bt = n.bluetooth();
        if (bt != null) b.append("---bt\n").append(bt.booleanValue() ? "1" : "0").append('\n');
        b.append("---up\n").append(chon(n.doc("/proc/uptime")));
        return b.toString();
    }

    static String chon(String s) { return s == null ? "" : s.trim(); }

    /** n dong dau (bo dong rong cuoi). */
    static String dongDau(String s, int n) {
        String[] d = s.split("\n");
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < d.length && i < n; i++) { if (i > 0) b.append('\n'); b.append(d[i]); }
        return b.toString();
    }

    /** Dong tong "cpu  ..." (khong phai "cpu0 ...") cua /proc/stat; khong co thi rong. */
    static String dongCpu(String stat) {
        if (stat == null) return "";
        for (String d : stat.split("\n")) if (d.startsWith("cpu ")) return d.trim();
        return "";
    }

    /** "/data <tong> <dung> <trong>" don vi M, mot so le (dung voi bieu thuc cua phia HA). */
    static String dongDf(long tongByte, long trongByte) {
        double mb = 1024.0 * 1024.0;
        return String.format(Locale.US, "/data %.1fM %.1fM %.1fM", tongByte / mb, (tongByte - trongByte) / mb, trongByte / mb);
    }

    /** Dong giong "mWifiInfo" cua dumpsys: SSID, RSSI, toc do, tan so. Khong co BSSID/MAC. */
    static String dongWifi(String ssid, int rssi, int mbps, int mhz) {
        String s = ssid == null ? "" : ssid.replace("\"", "").replace(",", " ").trim();
        return "mWifiInfo SSID: " + s + ", RSSI: " + rssi + ", Link speed: " + mbps + "Mbps, Frequency: " + mhz + "MHz,";
    }

    private static volatile Context ctx;

    static void khoiTao(Context c) { ctx = c == null ? null : c.getApplicationContext(); }

    public static final Nguon THAT = new Nguon() {
        @Override public String doc(String duongDan) {
            FileInputStream in = null;
            try {
                in = new FileInputStream(duongDan);
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[1024];
                int r;
                while ((r = in.read(buf)) > 0 && out.size() < 8192) out.write(buf, 0, r);
                return out.toString("UTF-8");
            } catch (IOException | RuntimeException loi) {
                return null;
            } finally {
                if (in != null) { try { in.close(); } catch (IOException boQua) { } }
            }
        }

        @Override public String df() {
            try {
                StatFs s = new StatFs("/data");
                long bs = s.getBlockSize();
                return dongDf(s.getBlockCount() * bs, s.getAvailableBlocks() * bs);
            } catch (Throwable t) {
                return null;
            }
        }

        @Override public String wifi() {
            try {
                Context c = ctx;
                if (c == null) return null;
                WifiManager wm = (WifiManager) c.getSystemService(Context.WIFI_SERVICE);
                WifiInfo wi = wm == null ? null : wm.getConnectionInfo();
                if (wi == null) return null;
                return dongWifi(wi.getSSID(), wi.getRssi(), wi.getLinkSpeed(), wi.getFrequency());
            } catch (Throwable t) {
                return null;
            }
        }

        @Override public Boolean bluetooth() {
            try {
                return BluetoothDieuKhien.dangBat();
            } catch (Throwable t) {
                return null;
            }
        }
    };
}
