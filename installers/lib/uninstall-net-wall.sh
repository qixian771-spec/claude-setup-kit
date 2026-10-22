#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root
bootout_if_loaded local.claude-net-wall
pfctl -a com.apple/011.local.claude-net-wall -F all 2>/dev/null || true
rm -f /Library/LaunchDaemons/local.claude-net-wall.plist /usr/local/libexec/claude-net-wall /etc/pf.anchors/local.claude-net-wall
echo "[OK] 锚点 011 与装载器已移除。"
