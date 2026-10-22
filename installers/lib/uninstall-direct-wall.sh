#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root
anchor=com.apple/010.local.claude-direct-wall
bootout_if_loaded local.claude-direct-wall
pfctl -a "$anchor" -F all
pf_conf_remove "$anchor"
rm -f /Library/LaunchDaemons/local.claude-direct-wall.plist /usr/local/libexec/claude-direct-wall /etc/pf.anchors/local.claude-direct-wall
echo "[OK] 锚点 010 与装载器已移除（/var/db/ClaudeDirectWall 的启用引用保留，不影响）。"
