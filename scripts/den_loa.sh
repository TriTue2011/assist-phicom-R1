#!/usr/bin/env bash
# Máy chủ ĐÈN trên loa Phicomm R1: chạy với quyền shell (uid 2000) vì SELinux chặn ứng dụng thường mở
# /sys/class/leds/.../led_color. APK vn.r1.bodam gửi lệnh đèn của HA cho nó qua TCP 127.0.0.1:18771 (socket nội
# bộ bị SELinux chặn). Cổng chỉ nghe trên loopback nhưng MỌI ứng dụng trên loa nối được, nên máy chủ chỉ chạy
# đúng hai lệnh `lights_test set <mặt nạ> <rgb>` với mặt nạ cố định và rgb 6 số hex đã kiểm; hậu quả tối đa khi
# bị lạm dụng là đổi màu/độ sáng đèn.
#
# Trên loa KHÔNG giữ được tiến trình quyền shell sau khi phiên adb kết thúc (đã thử nohup, subshell, sh -c):
# phải có MỘT tiến trình `adb shell` đang chạy ở máy khác. `giam-sat` làm việc đó và tự bật lại khi loa
# khởi động lại hoặc mất kết nối. Chạy nó nền ở một máy trong nhà (systemd/nohup/tmux). Chưa có mẫu systemd đi
# kèm; cài lên máy nào là quyết định của người dùng.
#
#   den_loa.sh <IP-loa> chay        chạy máy chủ đèn (giữ phiên adb; Ctrl+C để dừng)
#   den_loa.sh <IP-loa> giam-sat    như `chay` nhưng tự chạy lại khi rớt (vòng lặp, 5 giây)
#   den_loa.sh <IP-loa> trang-thai  máy chủ đèn đang chạy không
#   den_loa.sh <IP-loa> dung        dừng máy chủ đèn
set -euo pipefail

LOA="${1:?dùng: den_loa.sh <IP-loa> chay|giam-sat|trang-thai|dung}"
LENH="${2:?dùng: den_loa.sh <IP-loa> chay|giam-sat|trang-thai|dung}"
ADB="${ADB:-adb}"
GOC="$(cd "$(dirname "$0")/.." && pwd)"
JAR="${R1_DEN_JAR:-$GOC/apk/r1-den.jar}"
DICH="/data/local/tmp/r1-den.jar"
GOI="vn.r1.bodam"

kn() { "$ADB" connect "$LOA:5555" >/dev/null 2>&1 || true; }
adb_loa() { "$ADB" -s "$LOA:5555" "$@"; }

pid_may_chu() {   # in PID các app_process đang chạy MayChuDen (qua /proc/<pid>/cmdline)
  adb_loa shell 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline 2>/dev/null | grep -q "vn.r1.den.MayChuDen" && echo ${p#/proc/}; done' | tr -d '\r'
}

chay() {
  kn
  [ -f "$JAR" ] || { echo "không thấy $JAR" >&2; return 1; }
  adb_loa push "$JAR" "$DICH" >/dev/null
  local uid
  uid="$(adb_loa shell "/system/bin/dumpsys package $GOI" | tr -d '\r' | grep -m1 -o 'userId=[0-9]*' | cut -d= -f2)"
  [[ "$uid" =~ ^[0-9]+$ ]] || { echo "không đọc được uid của $GOI (đã cài APK chưa?)" >&2; return 1; }
  echo "máy chủ đèn: uid app = $uid (giữ phiên adb, Ctrl+C để dừng)"
  adb_loa shell "CLASSPATH=$DICH exec app_process /system/bin vn.r1.den.MayChuDen $uid"
}

case "$LENH" in
  chay) chay ;;
  giam-sat) while true; do chay || true; echo "máy chủ đèn rớt, thử lại sau 5 giây"; sleep 5; done ;;
  trang-thai) kn; p="$(pid_may_chu)"; [ -n "$p" ] && echo "đang chạy (pid $p)" || { echo "chưa chạy"; exit 1; } ;;
  dung) kn; for p in $(pid_may_chu); do adb_loa shell "kill $p"; done; echo "đã dừng" ;;
  *) echo "lệnh lạ: $LENH" >&2; exit 2 ;;
esac
