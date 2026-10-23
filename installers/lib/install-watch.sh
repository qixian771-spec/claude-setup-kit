#!/bin/sh
# Self-check daemon: every 60 s re-loads missing 010/011/020 rules with the existing loaders and warns about TUN/Clash/updater.
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
watch=$(src system/libexec/net-guard-watch); lib=$(src system/libexec/net-guard-watch-lib.sh); plist=$(src system/LaunchDaemons/local.net-guard-watch.plist)
refuse_existing /usr/local/libexec/net-guard-watch /usr/local/libexec/net-guard-watch-lib.sh /Library/LaunchDaemons/local.net-guard-watch.plist
for l in claude-direct-wall claude-net-wall leak-guard-loader; do [ -x /usr/local/libexec/$l ] || { echo "先装好三堵墙（缺 /usr/local/libexec/${l}）" >&2; exit 73; }; done
install -o root -g wheel -m 644 "$lib" /usr/local/libexec/net-guard-watch-lib.sh
install -o root -g wheel -m 755 "$watch" /usr/local/libexec/net-guard-watch
install -o root -g wheel -m 644 "$plist" /Library/LaunchDaemons/local.net-guard-watch.plist
launchctl bootstrap system /Library/LaunchDaemons/local.net-guard-watch.plist
sleep 3
[ -f /var/db/NetGuardWatch/last ] || { echo "守护启动后没有写结果，失败（看 /var/log/net-guard-watch.stderr.log）" >&2; exit 74; }
echo "[OK] 自检守护已装。最近一次："; cat /var/db/NetGuardWatch/last
