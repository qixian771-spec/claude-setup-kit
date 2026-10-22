#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root
anchor=com.apple/020.local.leak-guard
bootout_if_loaded local.leak-guard
pfctl -a "$anchor" -F all 2>/dev/null || true
pf_conf_remove "$anchor"
rm -f /Library/LaunchDaemons/local.leak-guard.plist /usr/local/libexec/leak-guard-loader /etc/pf.anchors/local.leak-guard
echo "[OK] 锚点 020 与装载器已移除。"
