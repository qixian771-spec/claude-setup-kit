#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
bootout_if_loaded local.claude-address-update
rm -f /Library/LaunchDaemons/local.claude-address-update.plist /etc/sudoers.d/claude-mac-env-mirror
rm -rf "/Library/Application Support/ClaudeDirectWallUpdater"
state="$MIRROR_HOME/Library/Application Support/ClaudeDirectWallUpdater"
# Keep the logs but move them aside: the installer refuses to overwrite this directory, so leaving it in place
# would make "uninstall, then reinstall" impossible (EXIT=72).
if [ -e "$state" ]; then kept="$state.uninstalled-$(date +%Y%m%d-%H%M%S)"; mv "$state" "$kept"; else kept="（没有状态目录）"; fi
echo "[OK] 地址更新器与 sudoers 规则已移除；用户状态目录（日志）挪到了 ${kept}。"
