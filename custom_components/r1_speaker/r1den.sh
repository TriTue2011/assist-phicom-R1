#!/system/bin/sh
# r1den.sh <vung: day|vien> <hieu_ung> [khoa=gia_tri ...]   (r1den-v1)
#
# Hiệu ứng đèn R1 chạy NGAY TRÊN LOA (ghi thẳng /sys/class/leds/multi_leds0/led_color, quyền shell của adb).
# Chạy TIỀN CẢNH trong phiên adb đang mở: phiên đóng (HUP/TERM/INT) thì tắt đèn rồi thoát. Hiệu ứng tĩnh
# (đáy:co_dinh, viền:sang) chỉ đặt giá trị rồi thoát, đèn giữ nguyên.
# Danh sách hiệu ứng và thông số là DỮ LIỆU ở den_hieu_ung.py (HA đã kiểm khoảng giá trị); script vẫn kẹp lại
# từng số để một lệnh sai không ghi bậy vào đèn.
# Mặt nạ: đáy = 15 đèn (bit 0-14, 7fff), viền = 24 đèn (bit 15-38, 7fffff8000), viền CHỈ TRẮNG.
F=/sys/class/leds/multi_leds0/led_color
VUNG=$1; HU=$2
[ $# -ge 2 ] && shift 2
H=0123456789abcdef
BASE=7fff; RIM=7fffff8000

# ── thông số (mặc định = giá trị đã được chủ máy xác nhận bằng mắt) ──
MAU=ffffff; DS=100; TD=100; DO_SAU=0; TY_LE=50; NGHI=660; SO_CHOP=3; BANG=nhieu_mau
BAO_HOA=100; CHIEU=xuoi; SO_DAI=1; DAI_DUOI=5; KIEU=nhieu_mau
for a in "$@"; do
  case $a in
    mau=*) MAU=${a#mau=};; do_sang=*) DS=${a#do_sang=};; toc_do=*) TD=${a#toc_do=};;
    do_sau=*) DO_SAU=${a#do_sau=};; ty_le_bat=*) TY_LE=${a#ty_le_bat=};; nghi_ms=*) NGHI=${a#nghi_ms=};;
    so_chop=*) SO_CHOP=${a#so_chop=};; bang_mau=*) BANG=${a#bang_mau=};; bao_hoa=*) BAO_HOA=${a#bao_hoa=};;
    chieu=*) CHIEU=${a#chieu=};; so_dai=*) SO_DAI=${a#so_dai=};; dai_duoi=*) DAI_DUOI=${a#dai_duoi=};;
    kieu_mau=*) KIEU=${a#kieu_mau=};;
  esac
done
# kẹp số nguyên: kep BIEN MIN MAX MACDINH
kep() {
  eval "v=\$$1"
  case $v in ''|*[!0-9]*) v=$4;; esac
  [ $v -lt $2 ] && v=$2; [ $v -gt $3 ] && v=$3
  eval "$1=$v"
}
kep DS 0 100 100; kep TD 25 400 100; kep DO_SAU 0 80 0; kep TY_LE 10 90 50; kep NGHI 100 3000 660
kep SO_CHOP 1 6 3; kep BAO_HOA 30 100 100; kep SO_DAI 1 3 1; kep DAI_DUOI 1 10 5
case $MAU in [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;; *) MAU=ffffff;; esac
case $CHIEU in xuoi|nguoc) ;; *) CHIEU=xuoi;; esac
case $BANG in nhieu_mau|am|lanh) ;; *) BANG=nhieu_mau;; esac
case $KIEU in nhieu_mau|don_sac) ;; *) KIEU=nhieu_mau;; esac

# Chỉ tắt VÙNG của mình (đáy và viền chạy độc lập). Mỗi vùng có một tệp pid: hiệu ứng mới của cùng vùng dừng hẳn
# (kill -9) tiến trình cũ trước khi ghi, nên không bao giờ có hai tiến trình cùng ghi một vùng.
case $VUNG in day) MASK=$BASE;; vien) MASK=$RIM;; *) echo "vung khong hop le: $VUNG" >&2; exit 2;; esac
PIDF=/data/local/tmp/r1den.$VUNG.pid
[ -f $PIDF ] && { OLD=$(cat $PIDF); [ -n "$OLD" ] && [ "$OLD" != "$$" ] && kill -9 $OLD 2>/dev/null; }
echo $$ > $PIDF
tat() { echo "$MASK 000000" > $F; }
bye() { tat; [ "$(cat $PIDF 2>/dev/null)" = "$$" ] && rm -f $PIDF; exit 0; }
trap bye HUP TERM INT

# ── tiện ích ──
hx() { echo -n ${H:$(($1/16)):1}${H:$(($1%16)):1}; }
# sc RRGGBB PCT -> SC (màu nhân PCT/100)
sc() { SC=$(hx $((16#${1:0:2}*$2/100)))$(hx $((16#${1:2:2}*$2/100)))$(hx $((16#${1:4:2}*$2/100))); }
# hsv HUE(0-359) SAT(0-100) VAL(0-100) -> SC
hsv() {
  h=$(( ($1 % 360 + 360) % 360 )); s=$(( $2*255/100 )); v=$(( $3*255/100 ))
  f=$(( (h%60)*255/60 )); p=$(( v*(255-s)/255 )); q=$(( v*(255-s*f/255)/255 )); t=$(( v*(255-s*(255-f)/255)/255 ))
  case $((h/60)) in 0) r=$v;g=$t;b=$p;; 1) r=$q;g=$v;b=$p;; 2) r=$p;g=$v;b=$t;; 3) r=$p;g=$q;b=$v;; 4) r=$t;g=$p;b=$v;; *) r=$v;g=$p;b=$q;; esac
  SC=$(hx $r)$(hx $g)$(hx $b)
}
# ms: thời gian bước theo tốc độ; nghi MS
ms() { echo $(( $1*100/TD )); }
nghi() { m=$(( $1*100/TD )); [ $m -lt 5 ] && m=5; s=$((m/1000)); r=$((1000+m%1000)); sleep $s.${r:1:3}; }
dat() { echo "$1 $2" > $F; }
# mặt nạ từng đèn: mb 0..14, mr 0..23 -> M
mb() { i=$1; set -- 1 2 4 8 10 20 40 80 100 200 400 800 1000 2000 4000; eval "M=\${$((i+1))}"; }
mr() { i=$1; set -- 8000 10000 20000 40000 80000 100000 200000 400000 800000 1000000 2000000 4000000 8000000 10000000 20000000 40000000 80000000 100000000 200000000 400000000 800000000 1000000000 2000000000 4000000000; eval "M=\${$((i+1))}"; }
# thở: sin^1.6 đã lấy mẫu 40 bước (0-100), trộn với đáy DO_SAU
THO="0 0 0 1 3 5 9 13 19 25 33 41 50 58 67 75 82 88 93 97 99 100 99 97 93 88 82 75 67 58 50 41 33 25 19 13 9 5 3 1"
tho() { # tho MASK RRGGBB
  while :; do
    for p in $THO; do
      l=$(( DO_SAU + (100-DO_SAU)*p/100 )); sc $2 $((l*DS/100)); dat $1 $SC; nghi 50
    done
  done
}
# chiều chạy: DIR=1 xuôi, -1 ngược
[ "$CHIEU" = nguoc ] && DIR=-1 || DIR=1

case "$VUNG:$HU" in
 day:co_dinh) sc $MAU $DS; dat $BASE $SC ;;
 day:tho) tho $BASE $MAU ;;
 day:nhap_nhay)
   sc $MAU $DS; C=$SC; ON=$((1000*TY_LE/100)); OFF=$((1000-ON))
   while :; do dat $BASE $C; nghi $ON; dat $BASE 000000; nghi $OFF; done ;;
 day:nhip_tim)
   sc $MAU $DS; C=$SC; sc $MAU $((DS*15/100)); L=$SC; sc $MAU $((DS*75/100)); M2=$SC
   while :; do dat $BASE $C; nghi 120; dat $BASE $L; nghi 100; dat $BASE $M2; nghi 120; dat $BASE 000000; nghi $NGHI; done ;;
 day:chop)
   sc $MAU $DS; C=$SC
   while :; do n=0; while [ $n -lt $SO_CHOP ]; do dat $BASE $C; nghi 60; dat $BASE 000000; nghi 200; n=$((n+1)); done; nghi $NGHI; done ;;
 day:phao_hoa)
   case $BANG in
     am) set -- ff0000 ff7300 ffe500 ff0080;;
     lanh) set -- 0000ff 00ffff 8000ff 00ff00;;
     *) set -- 00ff00 0000ff ffff00 ff00ff 00ffff;;
   esac
   N=$#
   while :; do
     eval "c=\${$((RANDOM%N+1))}"
     sc $c $DS; dat $BASE $SC; nghi 80
     sc $c $((DS*45/100)); dat $BASE $SC; nghi 100
     sc $c $((DS*15/100)); dat $BASE $SC; nghi 100
     dat $BASE 000000
     nghi $(( NGHI*55/100 + RANDOM%NGHI ))
   done ;;
 day:cau_vong) # 12 sắc độ, mỗi sắc 400 ms
   k=0
   while :; do hsv $((k*30*DIR)) $BAO_HOA $DS; dat $BASE $SC; nghi 400; k=$(( (k+1)%12 )); done ;;
 day:cau_vong_fw) # 6 màu firmware, mỗi màu 500 ms
   set -- ff0000 ff7300 00ff00 0000ff 8000ff 00ffff
   k=0
   while :; do
     [ $DIR = 1 ] && idx=$((k%6+1)) || idx=$((6-k%6))
     eval "c=\${$idx}"; sc $c $DS; dat $BASE $SC; nghi 500; k=$((k+1))
   done ;;
 day:cau_vong_xoay) # mỗi đèn một màu, dải xoay một đèn mỗi khung
   k=0
   while :; do
     i=0; while [ $i -lt 15 ]; do
       hsv $(( (i*360*SO_DAI/15) + DIR*k*24*SO_DAI )) $BAO_HOA $DS; mb $i; dat $M $SC; i=$((i+1))
     done
     k=$(( (k+1)%15 )); nghi 70
   done ;;
 day:sao_choi) # đầu sáng nhất, đuôi tối dần; nhiều màu (đỏ -> tím) hoặc đơn sắc
   k=0
   while :; do
     i=0; while [ $i -lt 15 ]; do
       d=$(( (DIR*(k-i) % 15 + 15) % 15 )); mb $i
       if [ $d -lt $DAI_DUOI ]; then
         lv=$(( DS * (DAI_DUOI-d)*(DAI_DUOI-d) / (DAI_DUOI*DAI_DUOI) ))
         if [ $KIEU = don_sac ]; then sc $MAU $lv; else hsv $((d*270/DAI_DUOI)) 100 $lv; fi
         dat $M $SC
       else dat $M 000000; fi
       i=$((i+1))
     done
     k=$((k+1)); nghi 70
   done ;;
 vien:sang) sc ffffff $DS; dat $RIM $SC ;;
 vien:tho) tho $RIM ffffff ;;
 vien:chay_duoi)
   k=0
   while :; do
     i=0; while [ $i -lt 24 ]; do
       d=$(( (DIR*(k-i) % 24 + 24) % 24 )); mr $i
       if [ $d -lt $DAI_DUOI ]; then
         lv=$(( DS * (DAI_DUOI-d)*(DAI_DUOI-d) / (DAI_DUOI*DAI_DUOI) )); sc ffffff $lv; dat $M $SC
       else dat $M 000000; fi
       i=$((i+1))
     done
     k=$((k+1)); nghi 50
   done ;;
 day:tat|vien:tat) tat ;;
 *) echo "hieu ung khong hop le: $VUNG:$HU" >&2; exit 2 ;;
esac
