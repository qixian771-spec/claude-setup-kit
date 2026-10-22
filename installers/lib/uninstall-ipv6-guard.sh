#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
label=$(sed -n 's/^IPV6_LABEL=//p' "$BUILD/PARAMS.txt" | head -1)
bootout_if_loaded "$label"
rm -f "/Library/LaunchDaemons/$label.plist" "$MIRROR_HOME/.local/bin/ipv6-guard.sh"
echo "[OK] IPv6 守护已移除；IPv6 仍是关闭状态，要打开请在系统设置里手动改。"
