#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root
bootout_if_loaded local.net-guard-watch
rm -f /Library/LaunchDaemons/local.net-guard-watch.plist /usr/local/libexec/net-guard-watch /usr/local/libexec/net-guard-watch-lib.sh
echo "[OK] 自检守护已移除（/var/db/NetGuardWatch 的历史保留）。"
