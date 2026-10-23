#!/bin/sh
# Anchor 020: block physical DNS/STUN and force this user's public traffic into the TUN. Hooks /etc/pf.conf.
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
anchor=com.apple/020.local.leak-guard
rules=$(src system/pf.anchors/local.leak-guard); loader=$(src system/libexec/leak-guard-loader); plist=$(src system/LaunchDaemons/local.leak-guard.plist)
refuse_existing /etc/pf.anchors/local.leak-guard /usr/local/libexec/leak-guard-loader /Library/LaunchDaemons/local.leak-guard.plist
grep -q "user $MIRROR_UID " "$rules" || { echo "规则里的 UID 不是 ${MIRROR_UID}，渲染参数不对" >&2; exit 65; }
tun=$(sed -n 's/^TUN=//p' "$BUILD/PARAMS.txt" | head -1)
ifconfig "$tun" 2>/dev/null | grep -q 'inet ' || { echo "TUN 接口 $tun 不在：先把 Clash 的 TUN 开起来，否则装上这堵墙这台机器会立刻断网" >&2; exit 75; }
pfctl -n -a "$anchor" -f "$rules"
install -o root -g wheel -m 644 "$rules" /etc/pf.anchors/local.leak-guard
install -o root -g wheel -m 755 "$loader" /usr/local/libexec/leak-guard-loader
install -o root -g wheel -m 644 "$plist" /Library/LaunchDaemons/local.leak-guard.plist
mkdir -p /var/db/LocalLeakGuard; chmod 700 /var/db/LocalLeakGuard
pf_conf_add "$anchor" /etc/pf.anchors/local.leak-guard
/usr/local/libexec/leak-guard-loader
launchctl bootstrap system /Library/LaunchDaemons/local.leak-guard.plist
has_label "$anchor" leak-guard-dns && has_label "$anchor" leak-guard-user-public || { echo "装载后规则不在，失败" >&2; exit 74; }
echo "[OK] 防泄露墙（锚点 020）已装载：物理 53/853/STUN 封锁，UID $MIRROR_UID 的公网只准走 ${tun}。"
