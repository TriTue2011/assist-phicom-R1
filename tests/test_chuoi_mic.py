"""Chuỗi mic: amplify → khử tạp → AGC → hạn đỉnh → listener; bật/tắt từ options.

Loa giả: máy chủ TCP 127.0.0.1 (PcmServer của test_mic). KHÔNG chạm loa thật."""

import asyncio

import numpy as np
import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.r1_speaker import const
from custom_components.r1_speaker import mic as mic_mod
from custom_components.r1_speaker.agc import FULL, AgcSettings, LimiterSettings
from custom_components.r1_speaker.chuoi_mic import MicChain
from custom_components.r1_speaker.const import MIC_CHUNK
from custom_components.r1_speaker.noise_suppress import NoiseSettings
from custom_components.r1_speaker.settings import agc_settings, limiter_settings, noise_settings

from .test_bo_dam import _them
from .test_mic import PcmServer, _cho, _nhanh, pcm_server  # noqa: F401
from .test_tuy_chon import _luu
from .tin_hieu_tong_hop import RATE, chay, from_pcm, nhieu_trang, rms, sine, to_pcm

AGC = AgcSettings(enabled=True, target_db=-20.0, max_gain_db=24.0, silence_db=-55.0)
LIM = LimiterSettings(enabled=True, ceiling=0.89)
NOI = NoiseSettings(enabled=True)
TRAN = int(0.89 * 32767)


def dbfs(x) -> float:
    return float(20 * np.log10(rms(x) / FULL + 1e-12))


def kich_ban_muc(muc_db: float, giay: float = 7.0):
    """Nền trắng -70 dBFS suốt, sine 440 Hz mức ``muc_db`` (RMS) từ 1,5 s."""
    n = int(giay * RATE)
    nen = nhieu_trang(n) * FULL * 10 ** (-70 / 20)
    tieng = np.zeros(n)
    tieng[int(1.5 * RATE):] = sine(440, giay - 1.5, FULL * 10 ** (muc_db / 20) * np.sqrt(2))
    return nen + tieng


# ── MicChain thuần ────────────────────────────────────────────────────────────────────

def test_ca_ba_tat_la_mac_dinh_va_khung_khong_doi():
    c = MicChain(NoiseSettings(), AgcSettings(), LimiterSettings())
    assert not c.active and c.noise is None and c.agc is None and c.limiter is None
    for khung in (b"", b"\x01", b"abc", to_pcm(sine(500, 0.1, 9000))):
        assert c.process(khung) is khung
    assert MicChain().process(b"xyz") == b"xyz"


def test_chuoi_day_du_bang_do_muc_ra_dinh_va_do_dai():
    print("\nchuỗi đủ (khử tạp+AGC+hạn đỉnh), sine từ 1,5 s trên nền -70 dBFS:")
    print("vào dBFS | ra (giây cuối) | đỉnh / FS")
    for muc in (-40, -20, -6):
        vao = to_pcm(kich_ban_muc(muc))
        ra = chay(MicChain(NOI, AGC, LIM), vao)
        y = from_pcm(ra)
        dinh = np.abs(y).max()
        print(f"{muc:+4d}      | {dbfs(y[-RATE:]):+7.2f}        | {dinh / FULL:.4f}")
        assert len(ra) == len(vao)
        assert abs(dbfs(y[-RATE:]) - AGC.target_db) < 2.0
        assert dinh <= TRAN


def test_hat_loa_dot_ngot_sau_tieng_nho_hang_bo_han_dinh():
    """AGC đang tăng ~+20 dB cho tiếng nhỏ rồi gặp tiếng to đột ngột: nếu không có bộ hạn đỉnh,
    mẫu chạm trần cứng ±32767 (méo cứng); có thì mọi mẫu ≤ trần."""
    x = np.concatenate([sine(440, 3.0, FULL * 10 ** (-40 / 20) * np.sqrt(2)),
                        sine(440, 1.0, FULL * 0.9)])
    khong = from_pcm(chay(MicChain(None, AGC, None), to_pcm(x)))
    co = from_pcm(chay(MicChain(None, AGC, LIM), to_pcm(x)))
    print(f"\nđột ngột to: không hạn đỉnh → đỉnh {np.abs(khong).max() / FULL:.3f} FS; "
          f"có hạn đỉnh → {np.abs(co).max() / FULL:.3f} FS")
    assert np.abs(khong).max() >= 32767
    assert np.abs(co).max() <= TRAN


def test_thu_tu_khu_tap_truoc_agc():
    """Đảo thứ tự sẽ làm AGC khuếch đại nền tạp trước khi khử; đúng thứ tự thì nền thuần
    ở mức trên ngưỡng im lặng bị khử rồi mới vào AGC → mức nền ra thấp hơn."""
    n = 5 * RATE
    nen = nhieu_trang(n) * FULL * 10 ** (-45 / 20)        # nền -45 dBFS, TRÊN ngưỡng im lặng
    ra = from_pcm(chay(MicChain(NOI, AGC, None), to_pcm(nen)))
    chi_agc = from_pcm(chay(MicChain(None, AGC, None), to_pcm(nen)))
    print(f"\nnền -45 dBFS: khử tạp+AGC → {dbfs(ra[-RATE:]):+.1f}; chỉ AGC → "
          f"{dbfs(chi_agc[-RATE:]):+.1f} dBFS")
    assert dbfs(ra[-RATE:]) < dbfs(chi_agc[-RATE:]) - 5
    assert MicChain(NOI, AGC, LIM).noise is not None


# ── Nối vào R1Mic ─────────────────────────────────────────────────────────────────────

async def _chay_mic(pcm_server, cau_hinh, khuc):
    m = mic_mod.R1Mic("127.0.0.1", pcm_server.port)
    cau_hinh(m)
    nhan: list[bytes] = []
    m.add_chunk_listener(nhan.append)
    task = asyncio.create_task(m.run())
    try:
        await _cho(lambda: pcm_server.writers)
        for k in khuc:
            await pcm_server.send(k)
            await asyncio.sleep(0)
        await _cho(lambda: len(nhan) >= len(khuc))
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return m, nhan


async def test_mic_mac_dinh_khuc_den_listener_la_amplify_dung_nhu_truoc(pcm_server):
    khuc = [to_pcm(np.random.default_rng(i).standard_normal(MIC_CHUNK // 2) * 800)
            for i in range(6)]
    m, nhan = await _chay_mic(pcm_server, lambda m: m.set_gain(12.0), khuc)
    assert nhan == [mic_mod.amplify(k, 12.0) for k in khuc]       # tắt: khúc y nguyên amplify


async def test_mic_bat_chuoi_dsp_khuc_ra_dung_do_dai_va_duoi_tran(pcm_server):
    x = kich_ban_muc(-6, giay=3.0)
    khuc = [to_pcm(x[i:i + MIC_CHUNK // 2]) for i in range(0, len(x) - MIC_CHUNK // 2 + 1,
                                                          MIC_CHUNK // 2)]

    def bat(m):
        m.set_gain(12.0)
        m.set_dsp(NOI, AGC, LIM)

    m, nhan = await _chay_mic(pcm_server, bat, khuc)
    assert all(len(k) == MIC_CHUNK for k in nhan) and len(nhan) == len(khuc)
    assert max(np.abs(from_pcm(k)).max() for k in nhan) <= TRAN
    # khác hẳn đầu ra amplify-chỉ: chuỗi thật sự chạy
    assert nhan != [mic_mod.amplify(k, 12.0) for k in khuc]


async def test_mic_dsp_hong_thi_phat_khuc_goc_khong_dut_luong(pcm_server, monkeypatch, caplog):
    def no(self, pcm):
        raise RuntimeError("giả lập hỏng")

    monkeypatch.setattr(MicChain, "process", no)
    khuc = [to_pcm(sine(300, 0.064, 4000)) for _ in range(3)]
    m, nhan = await _chay_mic(pcm_server, lambda m: m.set_dsp(NOI, None, None), khuc)
    assert nhan == [mic_mod.amplify(k, 0.0) for k in khuc]        # khúc gốc, luồng vẫn sống
    assert "DSP chain failed" in caplog.text


async def test_mic_giu_hold_khong_chay_dsp_va_khong_phat(pcm_server):
    m = mic_mod.R1Mic("127.0.0.1", pcm_server.port)
    m.set_dsp(NOI, AGC, LIM)
    nhan = []
    m.add_chunk_listener(nhan.append)
    nha = m.hold()
    task = asyncio.create_task(m.run())
    try:
        await _cho(lambda: pcm_server.writers)
        await pcm_server.send(to_pcm(sine(300, 0.064, 4000)))
        await _cho(lambda: m.connected)
        await asyncio.sleep(0.1)
        assert nhan == []
    finally:
        nha()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ── Options ───────────────────────────────────────────────────────────────────────────

_GOC = dict(talk_threshold_db=-45.0, talk_silence_s=1.5, talk_preroll_s=0.3, talk_tail_s=0.5,
            noise_suppress=False, noise_strength_db=const.DEFAULT_NOISE_STRENGTH_DB,
            noise_voice_db=const.DEFAULT_NOISE_VOICE_DB, agc_enable=False,
            agc_target_db=const.DEFAULT_AGC_TARGET_DB, agc_max_gain_db=const.DEFAULT_AGC_MAX_GAIN_DB,
            agc_silence_db=const.DEFAULT_AGC_SILENCE_DB, limiter_enable=False,
            limiter_ceiling=const.DEFAULT_LIMITER_CEILING,
            duplex_vad_threshold=const.DEFAULT_DUPLEX_VAD_THRESHOLD,
            duplex_preroll_s=const.DEFAULT_DUPLEX_PREROLL,
            duplex_hangover_s=const.DEFAULT_DUPLEX_HANGOVER, duplex_max_s=const.DEFAULT_DUPLEX_MAX_S,
            duplex_duck=const.DEFAULT_DUPLEX_DUCK, duplex_duck_db=const.DEFAULT_DUPLEX_DUCK_DB)


async def test_mac_dinh_options_tat_het(hass, r1):
    e = await _them(hass, r1)
    assert not noise_settings(e).enabled and not agc_settings(e).enabled
    assert not limiter_settings(e).enabled
    assert not e.runtime_data.mic.noise.enabled
    assert not MicChain(e.runtime_data.mic.noise, e.runtime_data.mic.agc,
                        e.runtime_data.mic.limiter).active


async def test_bat_tu_options_ap_vao_mic_va_chi_luu_gia_tri_khac_goc(hass, r1):
    e = await _them(hass, r1)
    res = await hass.config_entries.options.async_init(e.entry_id)
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port, "nang_cao": True})
    res = await hass.config_entries.options.async_configure(res["flow_id"], {
        **_GOC, "noise_suppress": True, "noise_strength_db": 15.0, "agc_enable": True,
        "agc_target_db": -18.0, "limiter_enable": True, "limiter_ceiling": 0.8})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert e.options == {"noise_suppress": True, "noise_strength_db": 15.0, "agc_enable": True,
                         "agc_target_db": -18.0, "limiter_enable": True,
                         "limiter_ceiling": 0.8}                  # mặc định không bị lưu
    await hass.async_block_till_done()                            # nạp lại mục
    m = e.runtime_data.mic
    assert m.noise == NoiseSettings(True, 15.0, const.DEFAULT_NOISE_VOICE_DB)
    assert m.agc == AgcSettings(True, -18.0, const.DEFAULT_AGC_MAX_GAIN_DB,
                                const.DEFAULT_AGC_SILENCE_DB)
    assert m.limiter == LimiterSettings(True, 0.8)


@pytest.mark.parametrize("truong,gia_tri", [
    ("noise_strength_db", -1.0), ("noise_strength_db", 80.0), ("noise_voice_db", 0.0),
    ("agc_target_db", 0.0), ("agc_max_gain_db", 99.0), ("agc_silence_db", 0.0),
    ("limiter_ceiling", 0.0), ("limiter_ceiling", 1.5)])
async def test_gia_tri_dsp_ngoai_dai_bi_tu_choi(hass, r1, truong, gia_tri):
    from homeassistant.data_entry_flow import InvalidData
    e = await _them(hass, r1)
    res = await hass.config_entries.options.async_init(e.entry_id)
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"host": "127.0.0.1", "port": r1.port, "nang_cao": True})
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(res["flow_id"], {**_GOC, truong: gia_tri})
    assert e.options == {}
