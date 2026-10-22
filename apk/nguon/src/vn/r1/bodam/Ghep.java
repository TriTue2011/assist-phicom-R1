package vn.r1.bodam;

import android.content.Context;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Ghep khoa tu dong: khi HA tu choi (khoa cu/trong) APK xin khoa tu HA, nguoi dung khong phai copy khoa.
 * POST http://<host HA>:8123/api/r1_speaker/ghep -> {"port":18765,"key":"..."}; HA chi trao khoa MOT lan cho
 * dung IP loa (xem custom_components/r1_speaker/ghep_khoa.py). Chi goi toi host da cau hinh, khong bao gio
 * toi dia chi khac. Khoa khong duoc ghi log.
 */
public final class Ghep implements DieuKhienGhi.GhepKhoa {
    static final int CONG_HTTP_HA = 8123;

    private static final Pattern PORT = Pattern.compile("\"port\"\\s*:\\s*(\\d{1,5})");
    private static final Pattern KEY = Pattern.compile("\"key\"\\s*:\\s*\"([A-Za-z0-9_\\-]{8,128})\"");

    private final Context ctx;

    public Ghep(Context ctx) { this.ctx = ctx.getApplicationContext(); }

    /** Doc tra loi cua HA: {cong, khoa} hoac null neu khong dung dinh dang/ngoai khoang. Logic thuan. */
    public static String[] phanTichTraLoi(String body) {
        if (body == null || body.length() > 512) return null;
        Matcher p = PORT.matcher(body), k = KEY.matcher(body);
        if (!p.find() || !k.find()) return null;
        int cong = Integer.parseInt(p.group(1));
        if (cong < 1 || cong > 65535) return null;
        return new String[] { String.valueOf(cong), k.group(1) };
    }

    /** Host chi gom ky tu hop le cua ten/IP: khong de lenh cau hinh chen duong dan hay cong khac vao URL. */
    static boolean hostHopLe(String host) {
        return host != null && host.matches("[A-Za-z0-9.\\-]{1,253}");
    }

    @Override public String[] thu(String host) {
        if (!hostHopLe(host)) return null;
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL("http://" + host + ":" + CONG_HTTP_HA + "/api/r1_speaker/ghep").openConnection();
            c.setRequestMethod("POST");
            c.setConnectTimeout(3000);
            c.setReadTimeout(3000);
            c.setDoOutput(true);
            c.getOutputStream().close();
            if (c.getResponseCode() != 200) return null;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] b = new byte[256];
            int n;
            while ((n = in.read(b)) > 0 && out.size() <= 512) out.write(b, 0, n);
            return phanTichTraLoi(new String(out.toByteArray(), "UTF-8"));
        } catch (Throwable t) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    @Override public void luu(int port, String khoa) {
        CauHinh cfg = CauHinh.doc(ctx);
        cfg.port = port;
        cfg.khoa = khoa;
        cfg.luu(ctx);
    }
}
