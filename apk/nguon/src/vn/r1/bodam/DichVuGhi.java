package vn.r1.bodam;

import android.app.Notification;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import java.io.IOException;
import java.net.Socket;

/**
 * Dich vu tien canh: chi chay khi dang ghi. Ghi mic -> gui PCM qua TCP.
 * Khong ghi ra bo nho/log.
 *
 * NV247: logic phien ghi tach vao DieuKhienGhi (thuan, test duoc):
 * - connect co timeout (5 s), dong socket ngay khi TAT,
 * - generation: BAT moi huy phien cu, khong bao gio 2 luong song song,
 * - thong bao "Dang ket noi…" truoc, chi bao "Dang gui…" sau khi gui hello xong.
 */
public class DichVuGhi extends Service {
    public static final String HANH_DONG_BAT = "vn.r1.bodam.BAT";
    public static final String HANH_DONG_TAT = "vn.r1.bodam.TAT";
    private static final int ID_THONG_BAO = 247;
    static volatile boolean dangChay = false;

    private final DieuKhienGhi dieuKhien = new DieuKhienGhi(DieuKhienGhi.NoiLai.macDinh());
    private Handler chu;

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        chu = new Handler(Looper.getMainLooper());
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String hd = intent == null ? null : intent.getAction();
        if (HANH_DONG_TAT.equals(hd)) {
            dungLai();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (dangChay) return START_STICKY;
        dangChay = true;
        hienThongBao("Đang kết nối…");
        final CauHinh cfg = CauHinh.doc(this);
        final DichVuGhi dichVu = this;
        dieuKhien.datGhep(new Ghep(this));
        dieuKhien.bat(cfg.host, cfg.port, cfg.khoa, cfg.gainDb, nhaTaoThat(),
                new DieuKhienGhi.BenNhanTrangThai() {
                    @Override public void doiTrangThai(final String trangThai) {
                        chu.post(new Runnable() {
                            @Override public void run() {
                                if ("dang_gui".equals(trangThai)) {
                                    dichVu.hienThongBao("Đang gửi mic về Home Assistant");
                                } else if ("cho_noi_lai".equals(trangThai)) {
                                    dichVu.hienThongBao("Mất kết nối, đang nối lại…");
                                } else if ("loi".equals(trangThai)) {
                                    dichVu.dungLai();
                                    dichVu.stopSelf();
                                } else if ("da_dung".equals(trangThai)) {
                                    dangChay = false;
                                }
                            }
                        });
                    }
                });
        return START_STICKY;
    }

    private void hienThongBao(String chuoi) {
        Intent mo = new Intent(this, ManHinhChinh.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, mo, 0);
        Notification n = new Notification.Builder(this)
                .setContentTitle("R1 Bộ đàm")
                .setContentText(chuoi)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentIntent(pi)
                .build();
        startForeground(ID_THONG_BAO, n);
    }

    private DieuKhienGhi.NhaTao nhaTaoThat() {
        return new DieuKhienGhi.NhaTao() {
            @Override public Socket ketNoi(String host, int port) throws IOException {
                return DieuKhienGhi.ketNoiCoTimeout(host, port);
            }
            @Override public DieuKhienGhi.MayDocAm taoMayDoc(int kichThuocDem)
                    throws IOException {
                int min = AudioRecord.getMinBufferSize(16000,
                        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
                if (min <= 0) min = 3200;
                final AudioRecord rec = thuTaoAudioRecord(min);
                if (rec == null || rec.getState() != AudioRecord.STATE_INITIALIZED) {
                    throw new IOException("khong tao duoc AudioRecord");
                }
                return new DieuKhienGhi.MayDocAm() {
                    @Override public void batDau() { rec.startRecording(); }
                    @Override public int doc(byte[] buf, int batDau, int dai) {
                        return rec.read(buf, batDau, dai);
                    }
                    @Override public void dung() {
                        try { rec.stop(); } catch (IllegalStateException boQua) { }
                        rec.release();
                    }
                };
            }
        };
    }

    private AudioRecord thuTaoAudioRecord(int min) {
        AudioRecord r = null;
        try {
            r = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min);
            if (r.getState() == AudioRecord.STATE_INITIALIZED) return r;
            r.release();
        } catch (IllegalArgumentException boQua) { }
        try {
            r = new AudioRecord(MediaRecorder.AudioSource.MIC, 16000,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, min);
        } catch (IllegalArgumentException boQua) {
            return null;
        }
        return r;
    }

    private void dungLai() {
        dieuKhien.tat();
        dangChay = false;
        stopForeground(true);
    }

    @Override public void onDestroy() {
        dungLai();
        super.onDestroy();
    }
}
