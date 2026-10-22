#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
bootout_if_loaded local.claude-address-update
rm -f /Library/LaunchDaemons/local.claude-address-update.plist /etc/sudoers.d/claude-mac-env-mirror
rm -rf "/Library/Application Support/ClaudeDirectWallUpdater"
echo "[OK] 地址更新器与 sudoers 规则已移除；用户状态目录 $MIRROR_HOME/Library/Application Support/ClaudeDirectWallUpdater 保留（日志）。"
