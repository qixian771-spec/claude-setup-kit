#!/bin/sh
# Turn IPv6 off on the physical service and keep it off with a root daemon (script lives in the user's ~/.local/bin).
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
label=$(sed -n 's/^IPV6_LABEL=//p' "$BUILD/PARAMS.txt" | head -1); service=$(sed -n 's/^WIFI_SERVICE=//p' "$BUILD/PARAMS.txt" | head -1)
script=$(src system/userbin/ipv6-guard.sh); plist=$(src system/LaunchDaemons/ipv6-guard.plist)
refuse_existing "$MIRROR_HOME/.local/bin/ipv6-guard.sh" "/Library/LaunchDaemons/$label.plist"
networksetup -getinfo "$service" >/dev/null || { echo "网络服务 $service 不存在" >&2; exit 65; }
install -d -o "$MIRROR_USER" -m 755 "$MIRROR_HOME/.local" "$MIRROR_HOME/.local/bin"
install -o "$MIRROR_USER" -m 755 "$script" "$MIRROR_HOME/.local/bin/ipv6-guard.sh"
networksetup -setv6off "$service"
install -o root -g wheel -m 644 "$plist" "/Library/LaunchDaemons/$label.plist"
launchctl bootstrap system "/Library/LaunchDaemons/$label.plist"
networksetup -getinfo "$service" | grep -q '^IPv6: Off' || { echo "IPv6 没有关掉" >&2; exit 74; }
echo "[OK] $service 的 IPv6 已关，守护 $label 每 30 秒复查。"
