#!/bin/bash
# Airflow · Mac 键盘共享客户端（终端一键安装 / 免文件权限）
# 用法：在 Mac 终端执行  curl -fsSL http://<PC-IP>:8123/install.sh | bash
# 不使用 set -u：任何变量缺失都不应中断连接

PC_IP="__AIRFLOW_PC_IP__"
DESKFLOW_VERSION="1.27.0"
APP="/Applications/Deskflow.app"
CONF_DIR="$HOME/Library/Deskflow"
CONF="$CONF_DIR/Deskflow.conf"
TMP_DMG="/tmp/Airflow-Deskflow-$$.dmg"
DONE=0

say() { printf "\033[1;36m[Airflow]\033[0m %s\n" "$1"; }
die() { printf "\033[1;31m[Airflow]\033[0m %s\n" "$1" >&2; exit 1; }

# IP 由 Windows 端注入；这里绝不读取 stdin（curl | bash 时 stdin 是脚本本身）
if [ -z "$PC_IP" ] || [ "$PC_IP" = "__AIRFLOW_PC_IP__" ]; then
  die "这个链接没有携带电脑 IP，请在 Windows 端重新打开下载页复制新命令。"
fi

ARCH="$(uname -m 2>/dev/null || echo unknown)"
if [ "$ARCH" = "arm64" ]; then
  DMG_NAME="deskflow-${DESKFLOW_VERSION}-macos-arm64.dmg"
else
  DMG_NAME="deskflow-${DESKFLOW_VERSION}-macos-x86_64.dmg"
fi
DMG_URL="https://github.com/deskflow/deskflow/releases/download/v${DESKFLOW_VERSION}/${DMG_NAME}"

# 优先用 Homebrew（完全不需要挂载安装包）
if [ ! -d "$APP" ] && command -v brew >/dev/null 2>&1; then
  say "检测到 Homebrew，尝试用 brew 安装 Deskflow…"
  brew install --cask deskflow >/dev/null 2>&1 || true
fi

if [ ! -d "$APP" ]; then
  say "未安装 Deskflow，开始下载（$ARCH）…"
  for v in /Volumes/Deskflow*; do
    [ -d "$v" ] && hdiutil detach "$v" -quiet 2>/dev/null
  done
  rm -f "$TMP_DMG"
  curl -L --fail --retry 3 --retry-delay 2 --progress-bar "$DMG_URL" -o "$TMP_DMG" \
    || die "下载失败，请检查网络。也可手动安装：$DMG_URL"
  SIZE="$(wc -c < "$TMP_DMG" 2>/dev/null | tr -d ' ')"
  [ "${SIZE:-0}" -gt 10000000 ] || die "下载不完整（${SIZE:-0} 字节），请重试。"
  say "正在挂载安装包…"
  VOL=""
  if hdiutil attach "$TMP_DMG" -nobrowse -noverify -quiet >/dev/null 2>&1; then
    VOL="$(ls -d /Volumes/Deskflow* 2>/dev/null | head -1)"
  fi
  if [ -z "$VOL" ]; then
    MNT="/tmp/AirflowDeskflowMnt"
    mkdir -p "$MNT"
    if hdiutil attach "$TMP_DMG" -nobrowse -noverify -quiet -mountpoint "$MNT" >/dev/null 2>&1; then
      VOL="$MNT"
    fi
  fi
  [ -n "$VOL" ] && [ -d "$VOL" ] || die "无法挂载安装包（系统可能限制磁盘镜像）。可手动下载安装：$DMG_URL"
  SRC_APP="$(ls -d "$VOL"/*.app 2>/dev/null | head -1)"
  [ -n "$SRC_APP" ] || die "安装包里没有找到应用。"
  cp -R "$SRC_APP" /Applications/ 2>/dev/null || sudo cp -R "$SRC_APP" /Applications/ || die "复制到 /Applications 失败。"
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
  hdiutil detach "$VOL" -quiet 2>/dev/null
  rm -f "$TMP_DMG"
fi

CORE="$APP/Contents/MacOS/deskflow-core"
[ -x "$CORE" ] || CORE="$APP/Contents/MacOS/deskflow"
[ -x "$CORE" ] || die "未找到 Deskflow 主程序。"

mkdir -p "$CONF_DIR"
cat > "$CONF" <<EOF
[core]
coreMode=1
computerName=Mac

[client]
remoteHost=$PC_IP

[log]
level=Info
EOF

say "已配置：本机作为客户端 → Windows ($PC_IP:24800)"
say "按 Ctrl+C 退出（会同时关闭后台连接）"

"$CORE" client -s "$CONF" &
CHILD=$!

cleanup() {
  [ "$DONE" = 1 ] && return
  DONE=1
  kill "$CHILD" 2>/dev/null
  wait "$CHILD" 2>/dev/null
  if command -v afplay >/dev/null 2>&1; then
    afplay /System/Library/Sounds/Glass.aiff >/dev/null 2>&1 &
  fi
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'display notification "键盘共享已停止" with title "Airflow"' >/dev/null 2>&1
  fi
  say "已退出。"
}
trap cleanup EXIT INT TERM HUP

wait "$CHILD"