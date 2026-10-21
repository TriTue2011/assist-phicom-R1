# Bài học từ camera Imou áp vào loa R1

Nguồn: mục «Sự cố thường gặp» của bộ đàm camera (`ha-camera-talk/README.md`) và mã `dahua_talk`.
**Không sao chép thiết kế camera.** Camera dùng chung phần cứng với go2rtc và kênh nói riêng (37777);
R1 khác: HA nói với loa qua giao diện âm thanh trừu tượng (`audio_port.py`), từ đánh thức
nằm trên loa, trạng thái mic do HA tự tính (`dam_thoai.py`). Bảng dưới ghi từng bài học đã áp thế nào
cho R1, test nào chứng minh, và phần nào **chờ đo** (không hứa hẹn).

| | Bài học (camera) | Áp vào R1 | Kiểm bằng | Còn chờ |
|---|---|---|---|---|
| a | Lọc ồn trên thiết bị cắt tiếng về 0 (35–94% thời gian) | Không xử lý nào ĐÈ LÊN luồng ở phía loa: loa phải gửi mic THÔ (hợp đồng, `HOP-DONG-PHIA-LOA.md` 4b); mọi xử lý nằm ở HA. Mặc định HA chỉ khuếch đại tuyến tính, chặn cứng, không cổng im lặng. (Khử tạp / AGC / hạn đỉnh phía HA — `noise_suppress.py`, `agc.py`, do bên khác thêm cùng đợt — là tuỳ chọn, mặc định TẮT; test (a) chỉ chứng minh trường hợp mặc định.) | `test_mic_khong_bi_dat_ve_0_khi_khong_co_tieng_nguoi` (cấu hình mặc định: tiếng ≈ −80 dBFS tới pipeline nguyên vẹn; `Gate` không tồn tại ở đường mic) | Phía loa có tự bật lọc ồn/AGC của AK7755 hay không: **CHỜ ĐO** |
| b | Mic nhỏ cần khuếch đại | `number.r1_tang_mic` 0–30 dB, mặc định **+12 dB, CHƯA ĐO** (mượn từ camera) | `test_tang_mic_mac_dinh_12db_chua_do_va_khuech_dai_khong_loc`; `test_tang_mic_tang_bien_do` | Số đo mức mic thật → chọn lại mặc định |
| c | Hai phiên cùng mở (`stdin already set`) | Một phiên một lúc, dùng chung cho nút / từ đánh thức / từ gọi của HA / bộ đàm. Phiên thứ hai bị từ chối NGAY kèm nguồn + tuổi phiên + sự kiện; phiên có đồng hồ canh (mic không nối 5 s, quá 60 s) | `test_phien_thu_hai_bi_tu_choi_co_thong_bao_khong_treo`, `test_hai_loi_xin_cung_luc_chi_mot_thang`, `test_phien_thu_hai_qua_nut_bi_tu_choi_co_thong_bao`, `test_bo_dam_bi_tu_choi_khi_dang_co_phien_assist`, `test_phien_het_gio_thi_tu_dong`, `test_mic_khong_noi_duoc_trong_phien_khong_treo` (đều bọc `wait_for`) | — |
| d | Trễ cả câu do đệm | Hàng đợi mic về pipeline chỉ `MIC_QUEUE_CHUNKS` = 8 khúc (≈ 0,5 s), đầy thì bỏ khúc CŨ; trước đây là 64 khúc (≈ 4 s) | `test_do_tre_va_dem_nho` (trễ mic→pipeline < 0,3 s trên mock; hàng đợi có trần, giữ khúc mới nhất) | Trễ thật của đường mic trên loa + mạng: **CHƯA ĐO** |
| e | Nói nhỏ thì không phát | Ngưỡng là THAM SỐ cấu hình (`talk_threshold_db`, mặc định −45 dBFS mượn từ camera) | `test_gate_tham_so_quyet_dinh_nguong`, `test_form_co_du_truong` | Ngưỡng hợp lý cho R1: **CHƯA ĐO** |
| f | Đang nói thì không nghe bên kia | Nửa công: `R1Mic.hold()` khi bộ đàm phát; `_dang_noi` bỏ mic khi loa nói TTS | `test_giu_mic_khi_loa_phat_nua_cong`, `test_tra_loi_di_qua_media_player_r1_loa`, test bộ đàm cũ | AK7755 có khử vang không (nửa công chỉ là «nửa công»): **CHỜ ĐO** |
| g | Sai `ha_url` (127.0.0.1 trong container) | Tuỳ chọn `ha_url` KIỂM ngay khi lưu: sai dạng / loopback (loa ở máy khác) / HA không tự gọi được `/ping` → lỗi cụ thể, KHÔNG lưu. (Trước đây `ha_url` chỉ là tham số dịch vụ, kiểm bằng regex — không có kiểm kết nối.) | `test_ha_url_sai_khong_luu` (9 ca), `test_ha_url_khong_toi_duoc_bao_loi_khong_luu`, `test_ha_url_dung_luu_va_dich_vu_dung_no` | HA tự gọi chính nó không chứng minh loa với tới được; cần thử trên mạng thật |
| h | Khoá đổi → 401 lặp | Khoá đổi được (`rotate_intercom_key`); khoá sai → 401 + `Retry-After` + MỘT thông báo (không lặp), tự gỡ khi đổi khoá / có lời gọi đúng | `test_khoa_sai_401_mot_thong_bao_doi_khoa_thi_het` | Phía loa có tôn trọng `Retry-After` không (loa chưa có) |
| i | Từ đánh thức không bắt ở xa | Chỉ ghi nhận, KHÔNG hứa hẹn tầm bắt | — | Tầm bắt, mô hình, tỷ lệ báo nhầm trên loa: **CHƯA ĐO** |
| j | Truy cập từ xa (4G): mic trình duyệt chỉ chạy trên HTTPS | Ghi rõ trong hướng dẫn 3.6: cần HA truy cập qua HTTPS (Nabu Casa hoặc tunnel HTTPS); VPN có thể đổi đường đi. Không tự cấu hình mạng | tài liệu | Chưa thử qua 4G thật |
| k | Thẻ không có nút mic thì không biết mic đang mở | `r1-talk-card`: trạng thái mic LUÔN hiện bằng chữ (Tắt / Đang nghe / Đang gửi; không đọc được → «Không rõ», không giả làm «Tắt»); `sensor.r1_trang_thai_mic` | `test_mo_hinh_the_trang_thai_mic_luon_hien`, `test_mo_hinh_the_nut_dam_thoai_bam_duoc_va_nhac` (Node), `test_giao_dien_the_dam_thoai_...` (Chrome không đầu, DOM thật) | Thẻ trong giao diện HA thật (lớp phủ `ha-card`, theme): chưa kiểm |

## Điểm khác camera (chủ ý)

- **Từ đánh thức chạy TRÊN LOA** (`wake_mode = speaker`): HA không nhận byte mic cho tới trigger. Camera
  gửi mic liên tục để HA dò. Phía loa **chưa có** nên trạng thái mic ở chế độ này là `tat` cho tới khi loa
  báo còn sống — không giả vờ «đang nghe».
- **Trạng thái mic tính ở HA**: `gui` chỉ khi byte mic thật đang về HA.
- **Giữ nhạc**: DLNA không có «hạ nhạc khi báo tin»; TTS thay URI đang phát nên khôi phục đặt lại URI cũ
  (`giu_nhac.py`). Camera không có nhạc nên không có bài này.
- **Đường âm thanh trừu tượng**: không đoán phần cứng; xem `HOP-DONG-PHIA-LOA.md` 4b.
