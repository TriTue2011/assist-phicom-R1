"""Chặn vọng TRỄ (vong_tre.py): đo thật 14/11/2026 — vọng về mic sau ~470 ms, dao động tới ~745 ms; chặn theo cửa sổ trễ, tiếng nhà to hơn mức vọng thì cho qua."""
import struct

from custom_components.r1_speaker.vong_tre import KHUNG_MAU, ChanVongTre, rms


def khung(r: int) -> bytes:
    """Khúc 20 ms (320 mẫu, sóng vuông) có RMS = r."""
    return struct.pack("<320h", *([r, -r] * 160))


class Dong_ho:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def tao(**kw):
    d = Dong_ho()
    return d, ChanVongTre(clock=d, **kw)


def phat(d, vt, giay, r):
    for _ in range(int(giay * 50)):
        vt.note_far(khung(r))
        d.t += 0.02


def test_rms_khung_chuan():
    assert rms(khung(1500)) == 1500.0 and rms(b"") == 0.0 and len(khung(1)) == KHUNG_MAU * 2


def test_vong_tre_500ms_bi_chan_con_truoc_va_sau_cua_so_thi_khong():
    d, vt = tao()
    phat(d, vt, 1.0, 1500)                       # bên kia nói 1 s
    d.t = 1.5
    assert vt.chan(khung(1000)) is True, "vọng trễ 500 ms phải bị chặn"
    d.t = 1.0 + 1.2                              # loa im > 750 ms: hết vọng
    assert vt.chan(khung(1000)) is False
    d2, v2 = tao()
    phat(d2, v2, 0.2, 1500)                      # loa vừa bắt đầu: chưa tới cửa sổ 300 ms nên chưa có vọng
    assert v2.chan(khung(500)) is False


def test_tieng_nha_to_hon_muc_vong_di_qua_khi_noi_chen():
    d, vt = tao(ty_le=2.0)
    phat(d, vt, 1.0, 1500)
    d.t = 1.5
    assert vt.chan(khung(2900)) is True and vt.chan(khung(3100)) is False
    assert vt.da_chan == 1 and vt.da_qua == 1


def test_loa_im_hoac_nen_thap_khong_bao_gio_chan_va_cua_so_sai_la_tat():
    d, vt = tao()
    phat(d, vt, 1.0, 60)
    d.t = 1.5
    assert vt.chan(khung(80)) is False
    d, vt = tao(thap_s=0.75, cao_s=0.3)
    assert vt.bat is False
    phat(d, vt, 1.0, 1500)
    d.t = 1.5
    assert vt.chan(khung(10)) is False


def test_khuc_loa_don_cuc_noi_tiep_khong_dat_theo_gio_toi():
    d, vt = tao()
    vt.note_far(khung(1500) * 50)                # 1 s tiếng đến CÙNG LÚC (jitter mạng / hàng đợi)
    d.t = 0.5
    assert vt.chan(khung(500)) is True           # tiếng phát từ t=0 → 1 s: ở t=0.5 cửa sổ [−0.25, 0.2] có tiếng
    vt.note_far(khung(1500) * 50)                # khúc kế đến khi khúc trước chưa phát xong: nối tiếp sau khúc trước, không chồng lên
    assert abs(vt._het - 2.0) < 1e-6
    d.t = 3.0                                    # cả hai khúc đã phát xong (t = 2,0) và quá cửa sổ trễ: không còn vọng
    assert vt.chan(khung(500)) is False
