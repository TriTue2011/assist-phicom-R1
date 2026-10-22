package vn.r1.bodam;

import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;

/** Phát PCM16 16 kHz mono nhận từ HA qua kết nối đang mở. Mở/đóng theo phiên mic. */
final class PhatAm {
    static final int TOC_DO = 16000;
    private AudioTrack track;

    synchronized void mo() {
        if (track != null) return;
        int dem = AudioTrack.getMinBufferSize(TOC_DO, AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT);
        track = new AudioTrack(AudioManager.STREAM_MUSIC, TOC_DO, AudioFormat.CHANNEL_OUT_MONO,
                AudioFormat.ENCODING_PCM_16BIT, Math.max(dem, 3200) * 2, AudioTrack.MODE_STREAM);
        track.play();
    }

    synchronized void ghi(byte[] pcm, int len) {
        if (track == null) mo();
        track.write(pcm, 0, len);
    }

    synchronized void dong() {
        if (track == null) return;
        try { track.stop(); } catch (IllegalStateException ignored) { }
        track.release();
        track = null;
    }
}
