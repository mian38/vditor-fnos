#!/usr/bin/env bash
# =============================================================================
# Vditor Android 客户端构建脚本
#
# 用法：
#   ./build_apk.sh              # 构建 debug + release（release 需签名环境变量）
#   ./build_apk.sh debug        # 仅 debug
#   ./build_apk.sh release      # 仅 release
#
# 签名通过环境变量注入，密钥文件不入库：
#   VDITOR_KEYSTORE   keystore 绝对路径
#   VDITOR_STORE_PASS keystore 密码
#   VDITOR_KEY_ALIAS  key alias
#   VDITOR_KEY_PASS   key 密码
# 不提供时 release 产出 **unsigned** 包（可安装测试，但无法覆盖升级已签名的版本）
# =============================================================================
set -euo pipefail

TOOLCHAIN="${VDITOR_TOOLCHAIN:-/c/android-toolchain}"
PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$PROJ_DIR/../releases"

export JAVA_HOME="$TOOLCHAIN/jdk17"
export ANDROID_HOME="$TOOLCHAIN/sdk"
export ANDROID_SDK_ROOT="$TOOLCHAIN/sdk"
export PATH="$JAVA_HOME/bin:$PATH"

GRADLE="$TOOLCHAIN/gradle-8.7/bin/gradle"
TARGET="${1:-all}"

# local.properties 每次生成，避免硬编码路径进版本库
cat > "$PROJ_DIR/local.properties" <<EOF
sdk.dir=$(cygpath -w "$ANDROID_HOME" 2>/dev/null || echo "$ANDROID_HOME")
EOF

echo "== 环境 =="
echo "JDK      : $("$JAVA_HOME/bin/java" -version 2>&1 | head -1)"
echo "SDK      : $ANDROID_HOME"
echo "Gradle   : $("$GRADLE" -v 2>/dev/null | grep -i '^Gradle' | head -1)"
if [ -n "${VDITOR_KEYSTORE:-}" ] && [ -f "${VDITOR_KEYSTORE:-}" ]; then
  echo "签名     : 已配置（$VDITOR_KEYSTORE）"
else
  echo "签名     : 未配置 → release 将产出 unsigned 包"
fi
echo

mkdir -p "$OUT_DIR"

run() {
  echo "== Gradle: $1 =="
  ( cd "$PROJ_DIR" && "$GRADLE" "$1" )
}

case "$TARGET" in
  debug)   run assembleDebug ;;
  release) run assembleRelease ;;
  all)     run assembleDebug; run assembleRelease ;;
  *)       echo "未知参数：$TARGET（可选 debug / release / all）"; exit 1 ;;
esac

echo
echo "== 产物 =="
find "$PROJ_DIR/app/build/outputs/apk" -name '*.apk' -printf '%-72p %10s bytes\n' 2>/dev/null || true

# 拷贝一份到 releases/ 便于分发
while IFS= read -r apk; do
  [ -n "$apk" ] || continue
  base="$(basename "$apk")"
  dest="$OUT_DIR/${base%.apk}-$(date +%Y%m%d_%H%M).apk"
  cp -f "$apk" "$dest"
  echo "已拷贝 → $dest"
done < <(find "$PROJ_DIR/app/build/outputs/apk" -name '*.apk' 2>/dev/null)
