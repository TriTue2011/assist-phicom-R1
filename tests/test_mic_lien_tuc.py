"""Luồng mic HTTP của R1 phải LIÊN TỤC theo thời gian thực dù phiên song công bỏ khúc (đo 16/11/2026: app Zalo nhận 33 khung/s thay vì 50 → điện thoại báo «tín hiệu kém»)."""
from custom_components.r1_speaker.intercom import TrucThoiGian

BPS = 32000          # 16 kHz PCM16 mono
CHUNK = 2048         # 64 ms, khúc của R1


def _chay(sec, co_khuc, dt=0.02):
    """Mô phỏng vòng MicView: mỗi bước 20 ms; khúc thật tới mỗi 64 ms nếu co_khuc(i) cho phép, ngược lại thử chèn im lặng. Trả (byte_ghi, byte_im_lang, ds_lan_chen)."""
    t = 0.0
    truc = TrucThoiGian(BPS, t)
    tong = im = 0
    chen = []
    i = 0
    tiep = 0.0
    while t < sec:
        if t >= tiep:
            if co_khuc(i):
                truc.da_ghi(CHUNK)
                tong += CHUNK
            i += 1
            tiep += CHUNK / BPS
            if co_khuc(i - 1):
                t += dt
                continue
        n = truc.can_chen(t)
        if n:
            truc.da_ghi(n)
            tong += n
            im += n
            chen.append((round(t, 2), n))
        t += dt
    return tong, im, chen


def test_a_complete_stream_never_gets_silence_inserted():
    tong, im, chen = _chay(10.0, lambda i: True)
    assert im == 0 and not chen, chen[:3]


def test_a_third_of_the_chunks_dropped_still_gives_a_full_real_time_stream():
    tong, im, _ = _chay(20.0, lambda i: i % 3 != 2)            # R1 duplex bỏ 1/3 khúc
    assert im > 0
    assert 0.98 * 20 * BPS <= tong <= 1.02 * 20 * BPS + CHUNK, "luồng phải đủ nhịp thực (đo %.0f%%)" % (100 * tong / (20 * BPS))


def test_long_silence_without_any_chunk_is_filled_continuously_not_once_per_second():
    tong, im, chen = _chay(3.0, lambda i: i == 0)               # một khúc rồi im 3 giây (VAD/nửa công bỏ hết)
    assert tong >= (3.0 - 0.1) * BPS - CHUNK, tong
    assert len(chen) > 10, "chèn ĐỀU (mỗi vài chục ms), không phải một cục mỗi giây: %s" % chen[:3]
    assert max(n for _, n in chen) <= 6400


def test_late_chunk_within_the_wait_window_is_not_treated_as_lost():
    t = 0.0
    truc = TrucThoiGian(BPS, t)
    truc.da_ghi(CHUNK)                                            # khúc đầu
    assert truc.can_chen(0.128) == 0                              # khúc thứ 2 trễ 64 ms: còn trong cửa sổ chờ 100 ms
    assert truc.can_chen(0.30) > 0                                # trễ quá lâu thì bù


def test_audio_written_ahead_of_the_clock_is_used_up_before_any_silence_is_inserted():
    truc = TrucThoiGian(BPS, 0.0)
    for _ in range(30):                                           # 1,9 s tiếng dồn cùng lúc (61440 byte)
        truc.da_ghi(CHUNK)
    assert sum(truc.can_chen(k * 0.02) for k in range(0, 90)) == 0, "còn tiếng dư cho ~1,9 s: chưa được chèn im lặng"
    assert truc.can_chen(3.0) > 0, "hết tiếng dư mà vẫn không có khúc mới thì phải bù im lặng"
