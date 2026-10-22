#!/bin/bash
# Build NV247 khong Gradle, mot lenh: aapt -> javac -> d8 -> zipalign -> apksigner
#
#   ./build.sh [release|kiemthu]
#
# Duong dan doc tu BIEN MOI TRUONG (khong ma cung):
#   R1_TOOLCHAIN   goc toolchain (mac dinh: $HOME/workspace/android-toolchain)
#   R1_JDK         JDK (mac dinh: $R1_TOOLCHAIN/jdk17)
#   R1_SDK         Android SDK (mac dinh: $R1_TOOLCHAIN/android-sdk)
#   R1_BUILD_TOOLS phien ban build-tools (mac dinh: 30.0.3)
#   R1_KEYSTORE    keystore ky APK (mac dinh: ./debug.keystore; neu chua co se tao moi)
#
# Vi du:
#   R1_TOOLCHAIN=/opt/android-tc ./build.sh release
#   ./build.sh kiemthu
set -e
cd "$(dirname "$0")"

VARIANT="${1:-release}"
if [ "$VARIANT" != "release" ] && [ "$VARIANT" != "kiemthu" ]; then
    echo "Dung: $0 [release|kiemthu]" >&2
    exit 1
fi

TC="${R1_TOOLCHAIN:-$HOME/workspace/android-toolchain}"
JAVA_HOME="${R1_JDK:-$TC/jdk17}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"
SDK="${R1_SDK:-$TC/android-sdk}"
BTVER="${R1_BUILD_TOOLS:-30.0.3}"
BT="$SDK/build-tools/$BTVER"
AJAR="$SDK/platforms/android-22/android.jar"

[ -d "$JAVA_HOME" ] || { echo "LOI: khong thay JDK: $JAVA_HOME (dat R1_JDK)" >&2; exit 1; }
[ -f "$AJAR" ] || { echo "LOI: khong thay android.jar: $AJAR (dat R1_SDK)" >&2; exit 1; }
[ -x "$BT/aapt" ] || { echo "LOI: khong thay aapt: $BT/aapt (dat R1_SDK/R1_BUILD_TOOLS)" >&2; exit 1; }

if [ "$VARIANT" = "release" ]; then
    MANIFEST="AndroidManifest-release.xml"   # khong co receiver kiem thu
    NGOAI_TRU="KiemMicReceiver.java"         # khong bien dich receiver vao ban phat hanh
    OUT="nv247-vn-r1-bodam.apk"
else
    MANIFEST="AndroidManifest-kiemthu.xml"   # co receiver kiem thu
    NGOAI_TRU=""
    OUT="nv247-vn-r1-bodam-kiemthu.apk"
fi

rm -rf gen build/classes build/dex
mkdir -p gen build/classes build/dex
# aapt doi ten file manifest phai dung la AndroidManifest.xml
cp "$MANIFEST" AndroidManifest.xml
"$BT/aapt" package -f -m -J gen -M AndroidManifest.xml -S res -I "$AJAR" -F build/apk-tho.apk

SRCS="$(find src gen -name '*.java')"
if [ -n "$NGOAI_TRU" ]; then
    SRCS="$(echo "$SRCS" | grep -v "$NGOAI_TRU" || true)"
fi
# shellcheck disable=SC2086
javac -source 8 -target 8 -encoding UTF-8 -cp "$AJAR" -d build/classes $SRCS
"$BT/d8" --release --lib "$AJAR" --output build/dex $(find build/classes -name '*.class')
cp build/apk-tho.apk build/apk-chua-dex.apk
(cd build && zip -j apk-chua-dex.apk dex/classes.dex > /dev/null)
"$BT/zipalign" -f 4 build/apk-chua-dex.apk build/apk-aligned.apk

KS="${R1_KEYSTORE:-debug.keystore}"
if [ ! -f "$KS" ]; then
    echo "Tao keystore moi: $KS (debug)"
    keytool -genkeypair -keystore "$KS" -storepass android \
        -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US"
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
    --out "$OUT" build/apk-aligned.apk
echo "Xong bien the: $VARIANT -> $OUT"
sha256sum "$OUT"
