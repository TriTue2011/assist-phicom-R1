package vn.r1.bodam;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

/**
 * Man hinh cai dat duy nhat + xu ly nut giua.
 * Ma phim nut giua DA DO (NV245, 22/10/2026): 195 (0x00c3), /dev/input/event0
 * (rk29-keypad), co du DOWN va UP; mac dinh 195, nguoi dung van doi duoc.
 * Che do kiem van ghi log moi ma phim.
 */
public class ManHinhChinh extends Activity {
    private static final String TAG = "NV243Phim";

    private EditText oHost, oPort, oKhoa, oGain, oKhoang, oKeycode;
    private TextView tTrangThai, tKiemPhim;
    private Switch congTacKiem;
    private Button nutGhi;
    private LogicNut logicNut;
    private Handler handler;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handler = new Handler();
        CauHinh cfg = CauHinh.doc(this);

        LinearLayout goc = new LinearLayout(this);
        goc.setOrientation(LinearLayout.VERTICAL);
        int dem = 24;
        goc.setPadding(dem, dem, dem, dem);

        goc.addView(nhan("Host HA"));
        oHost = oNhap(cfg.host); goc.addView(oHost);
        goc.addView(nhan("Port"));
        oPort = oNhap(cfg.port > 0 ? String.valueOf(cfg.port) : ""); goc.addView(oPort);
        goc.addView(nhan("Khoá"));
        oKhoa = oNhap(cfg.khoa); goc.addView(oKhoa);
        goc.addView(nhan("Khuếch đại (dB) — mặc định 0 = CHƯA ĐO"));
        oGain = oNhap(String.valueOf(cfg.gainDb)); goc.addView(oGain);
        goc.addView(nhan("Khoảng nhấn đôi (ms)"));
        oKhoang = oNhap(String.valueOf(cfg.khoangNhanDoiMs)); goc.addView(oKhoang);
        goc.addView(nhan("Keycode nút giữa — 195 = đã đo, nút giữa"));
        oKeycode = oNhap(String.valueOf(cfg.keycodeNutGiua)); goc.addView(oKeycode);

        nutGhi = new Button(this);
        nutGhi.setText("Bật/Tắt ghi");
        nutGhi.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { doiTrangThaiGhi(); }
        });
        goc.addView(nutGhi);

        tTrangThai = new TextView(this);
        goc.addView(tTrangThai);

        congTacKiem = new Switch(this);
        congTacKiem.setText("Chế độ kiểm phím (ghi log mọi mã phím)");
        congTacKiem.setChecked(cfg.cheDoKiemPhim);
        goc.addView(congTacKiem);

        tKiemPhim = new TextView(this);
        tKiemPhim.setText("");
        goc.addView(tKiemPhim);

        ScrollView cuon = new ScrollView(this);
        cuon.addView(goc);
        setContentView(cuon);
        capNhatTrangThai();

        nhanCauHinhTuLenh(savedInstanceState);
        khoiTaoLogicNut(cfg);
    }

    /**
     * NV247 — nhan cau hinh qua lenh (loa khong co man hinh), khong can mo app:
     *   am start -n vn.r1.bodam/.ManHinhChinh --es host <IP> --ei port <1..65535>
     *       --es khoa <khoa> [--ez tiep_can true]
     * Chi ghi vao SharedPreferences "cau_hinh"; KHONG in khoa ra log.
     */
    private void nhanCauHinhTuLenh(Bundle savedInstanceState) {
        Intent it = getIntent();
        if (it == null) return;
        CauHinh hienTai = CauHinh.doc(this);
        if (it.hasExtra("host")) {
            if (!CauHinhTuLenh.choPhepDoiCauHinh(hienTai.host, hienTai.khoa)) {
                // Cua vao exported: da cau hinh roi thi KHONG cho app khac doi dich den cua tieng mic.
                tTrangThai.setText("Đã cấu hình: bỏ qua lệnh đổi cấu hình (muốn đổi: pm clear vn.r1.bodam).");
            } else {
                nhanCauHinhLanDau(it, hienTai);
            }
        }
        // --ez bat true: bat mic THEO CAU HINH DA LUU (khong doi dich den), nhu luc loa khoi dong.
        if (it.getBooleanExtra("bat", false)) {
            CauHinh c = CauHinh.doc(this);
            if (CauHinhTuLenh.nenTuBat(c.host, c.port, c.khoa) && !DichVuGhi.dangChay) {
                Intent dv = new Intent(this, DichVuGhi.class);
                dv.setAction(DichVuGhi.HANH_DONG_BAT);
                startService(dv);
            }
        }
    }

    private void nhanCauHinhLanDau(Intent it, CauHinh hienTai) {
        String host = it.getStringExtra("host");
        String portChuoi;
        if (it.hasExtra("port")) {
            int pi = it.getIntExtra("port", Integer.MIN_VALUE);
            portChuoi = (pi == Integer.MIN_VALUE)
                    ? it.getStringExtra("port") : String.valueOf(pi);
        } else {
            portChuoi = String.valueOf(hienTai.port);
        }
        String khoa = it.hasExtra("khoa") ? it.getStringExtra("khoa") : hienTai.khoa;
        Boolean tiepCan = it.hasExtra("tiep_can")
                ? Boolean.valueOf(it.getBooleanExtra("tiep_can", false)) : null;
        CauHinhTuLenh.KetQua q =
                CauHinhTuLenh.phanTich(host, portChuoi, khoa, tiepCan);
        if (!q.ok) {
            tTrangThai.setText("Cấu hình qua lệnh không hợp lệ: " + q.loi);
            return;
        }
        CauHinh c = CauHinh.doc(this);
        c.host = q.host;
        c.port = q.port;
        c.khoa = q.khoa;
        if (it.hasExtra("tiep_can")) c.batTiepCanPhim = q.tiepCan;
        c.luu(this);
        // Co y khong hien/ghi khoa ra bat ky dau.
        tTrangThai.setText("Đã nhận cấu hình qua lệnh: host=" + q.host
                + ", port=" + q.port);
        oHost.setText(q.host);
        oPort.setText(String.valueOf(q.port));
    }

    private TextView nhan(String chu) {
        TextView t = new TextView(this);
        t.setText(chu);
        return t;
    }

    private EditText oNhap(String giaTri) {
        EditText e = new EditText(this);
        e.setText(giaTri);
        e.setSingleLine(true);
        return e;
    }

    private void khoiTaoLogicNut(CauHinh cfg) {
        LogicNut.HenGio henGio = new LogicNut.HenGio() {
            private Runnable dangHen;
            @Override public void hen(long treMs, Runnable viec) {
                dangHen = viec;
                handler.postDelayed(viec, treMs);
            }
            @Override public void huy() {
                if (dangHen != null) handler.removeCallbacks(dangHen);
                dangHen = null;
            }
        };
        logicNut = new LogicNut(cfg.khoangNhanDoiMs, henGio, new LogicNut.HanhDong() {
            @Override public void doiMic() { doiTrangThaiGhi(); }
            @Override public void doiBluetooth() { doiBluetoothThat(); }
        });
    }

    CauHinh docCauHinhTuManHinh() {
        CauHinh c = new CauHinh();
        c.host = oHost.getText().toString().trim();
        c.port = parseInt(oPort.getText().toString().trim(), 0);
        c.khoa = oKhoa.getText().toString();
        c.gainDb = parseDouble(oGain.getText().toString().trim(), CauHinh.GAIN_MAC_DINH_DB);
        c.khoangNhanDoiMs = parseLong(oKhoang.getText().toString().trim(),
                CauHinh.KHOANG_NHAN_DOI_MAC_DINH_MS);
        c.keycodeNutGiua = parseInt(oKeycode.getText().toString().trim(),
                CauHinh.KEYCODE_NUT_GIUA_MAC_DINH);
        c.cheDoKiemPhim = congTacKiem.isChecked();
        return c;
    }

    private void doiTrangThaiGhi() {
        CauHinh cfg = docCauHinhTuManHinh();
        cfg.luu(this);
        khoiTaoLogicNut(cfg);
        Intent i = new Intent(this, DichVuGhi.class);
        if (DichVuGhi.dangChay) {
            i.setAction(DichVuGhi.HANH_DONG_TAT);
            startService(i);
        } else {
            i.setAction(DichVuGhi.HANH_DONG_BAT);
            startService(i);
        }
        handler.postDelayed(new Runnable() {
            @Override public void run() { capNhatTrangThai(); }
        }, 300);
        capNhatTrangThai();
    }

    private void doiBluetoothThat() {
        tTrangThai.setText(BluetoothDieuKhien.doi());
    }

    private void capNhatTrangThai() {
        if (DichVuGhi.dangChay) {
            tTrangThai.setText("Trạng thái: Đang gửi mic về Home Assistant");
        } else {
            tTrangThai.setText("Trạng thái: Mic đang tắt — chưa kết nối");
        }
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        CauHinh cfg = CauHinh.doc(this);
        if (cfg.cheDoKiemPhim || congTacKiem.isChecked()) {
            String dong = "KeyEvent keyCode=" + event.getKeyCode()
                    + " action=" + event.getAction();
            Log.i(TAG, dong);
            tKiemPhim.setText(dong);
        }
        // Nhan dai: Android gui nhieu ACTION_DOWN lap (repeatCount tang) — chi tinh
        // su kien dau (repeatCount == 0) nen nhan dai van chi la MOT nhan don.
        if (event.getAction() == KeyEvent.ACTION_DOWN
                && event.getRepeatCount() == 0
                && LogicNut.laPhimNutGiua(event.getKeyCode(), cfg.keycodeNutGiua)) {
            if (logicNut != null) logicNut.nhan();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    @Override protected void onResume() {
        super.onResume();
        capNhatTrangThai();
    }

    private static int parseInt(String s, int macDinh) {
        try { return Integer.parseInt(s); } catch (NumberFormatException e) { return macDinh; }
    }
    private static long parseLong(String s, long macDinh) {
        try { return Long.parseLong(s); } catch (NumberFormatException e) { return macDinh; }
    }
    private static double parseDouble(String s, double macDinh) {
        try { return Double.parseDouble(s); } catch (NumberFormatException e) { return macDinh; }
    }
}
