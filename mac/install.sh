#!/bin/bash
# Airflow · Mac 键盘共享客户端（终端一键安装 / 免文件权限）
# 用法：在 Mac 终端执行  curl -fsSL http://<PC-IP>:8123/install.sh | bash
set -u

PC_IP="__AIRFLOW_PC_IP__"
DESKFLOW_VERSION="1.27.0"
APP="/Applications/Deskflow.app"
CONF_DIR="$HOME/Library/Deskflow"
CONF="$CONF_DIR/Deskflow.conf"
TMP_DMG="/tmp/Airflow-Deskflow-$$.dmg"
DONE=0

say() { printf "\033[1;36m[Airflow]\033[0m %s\n" "$1"; }
die() { printf "\033[1;31m[Airflow]\033[0m %s\n" "$1" >&2; exit 1; }

if [ -z "$PC_IP" ] || [ "$PC_IP" = "__AIRFLOW_PC_IP__" ]; then
  printf "请输入 Windows 电脑的局域网 IP："
  if [ -t 0 ]; then
    read -r PC_IP
  else
    # curl | bash 模式下 stdin 是脚本本身，必须从终端读
    read -r PC_IP < /dev/tty || die "无法读取输入；请改用局域网页面提供的完整命令。"
  fi
fi
[ -n "$PC_IP" ] || die "没有填写 IP，退出。"

ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
  DMG_NAME="deskflow-${DESKFLOW_VERSION}-macos-arm64.dmg"
else
  DMG_NAME="deskflow-${DESKFLOW_VERSION}-macos-x86_64.dmg"
fi
DMG_URL="https://github.com/deskflow/deskflow/releases/download/v${DESKFLOW_VERSION}/${DMG_NAME}"

if [ ! -d "$APP" ]; then
  say "未安装 Deskflow，开始下载（$ARCH）…"
  curl -L --fail --progress-bar "$DMG_URL" -o "$TMP_DMG" || die "下载失败，请检查网络后重试。"
  say "正在安装到 /Applications（可能要求输入密码）…"
  hdiutil attach "$TMP_DMG" -nobrowse -quiet || die "无法挂载安装包。"
  VOL="$(ls -d /Volumes/Deskflow* 2>/dev/null | head -1)"
  [ -n "$VOL" ] || die "未找到安装卷。"
  if [ -d "$VOL/Deskflow.app" ]; then
    cp -R "$VOL/Deskflow.app" /Applications/ 2>/dev/null || sudo cp -R "$VOL/Deskflow.app" /Applications/ || die "复制失败。"
  fi
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