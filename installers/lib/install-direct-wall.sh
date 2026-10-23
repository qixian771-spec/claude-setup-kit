#!/bin/sh
# Anchor 010: Claude's exact IPs may only leave through the TUN. Also hooks /etc/pf.conf for boot.
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
anchor=com.apple/010.local.claude-direct-wall
rules=$(src system/pf.anchors/local.claude-direct-wall); loader=$(src system/libexec/claude-direct-wall); plist=$(src system/LaunchDaemons/local.claude-direct-wall.plist)
refuse_existing /etc/pf.anchors/local.claude-direct-wall /usr/local/libexec/claude-direct-wall /Library/LaunchDaemons/local.claude-direct-wall.plist
pfctl -n -a "$anchor" -f "$rules"
mkdir -p /usr/local/libexec
install -o root -g wheel -m 644 "$rules" /etc/pf.anchors/local.claude-direct-wall
install -o root -g wheel -m 755 "$loader" /usr/local/libexec/claude-direct-wall
install -o root -g wheel -m 644 "$plist" /Library/LaunchDaemons/local.claude-direct-wall.plist
mkdir -p /var/db/ClaudeDirectWall; chmod 700 /var/db/ClaudeDirectWall
pf_conf_add "$anchor" /etc/pf.anchors/local.claude-direct-wall
/usr/local/libexec/claude-direct-wall || { rc=$?; echo "装载器 /usr/local/libexec/claude-direct-wall 退出码 ${rc}（含义见 system/libexec 里它的 exit 行）；文件已装、未回滚，先对账" >&2; exit 74; }
launchctl bootstrap system /Library/LaunchDaemons/local.claude-direct-wall.plist
has_label "$anchor" claude-wall-ipv4 && has_label "$anchor" claude-wall-ipv6 || { echo "装载后规则不在，失败" >&2; exit 74; }
echo "[OK] Claude 直连墙（锚点 010）已装载并设为开机装载。目标表："; pfctl -a "$anchor" -t claude_wall_targets -T show | sed 's/^/     /'
