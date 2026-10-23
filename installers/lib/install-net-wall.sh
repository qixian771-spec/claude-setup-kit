#!/bin/sh
# Anchor 011: Anthropic's whole networks may only leave through the TUN (loaded by its own daemon).
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
anchor=com.apple/011.local.claude-net-wall
rules=$(src system/pf.anchors/local.claude-net-wall); loader=$(src system/libexec/claude-net-wall); plist=$(src system/LaunchDaemons/local.claude-net-wall.plist)
refuse_existing /etc/pf.anchors/local.claude-net-wall /usr/local/libexec/claude-net-wall /Library/LaunchDaemons/local.claude-net-wall.plist
pf_enabled || { echo "PF 未启用：先装 Claude 直连墙（010）" >&2; exit 73; }
pfctl -n -a "$anchor" -f "$rules"
install -o root -g wheel -m 644 "$rules" /etc/pf.anchors/local.claude-net-wall
install -o root -g wheel -m 755 "$loader" /usr/local/libexec/claude-net-wall
install -o root -g wheel -m 644 "$plist" /Library/LaunchDaemons/local.claude-net-wall.plist
/usr/local/libexec/claude-net-wall || { rc=$?; echo "装载器 /usr/local/libexec/claude-net-wall 退出码 ${rc}（含义见 system/libexec 里它的 exit 行）；文件已装、未回滚，先对账" >&2; exit 74; }
launchctl bootstrap system /Library/LaunchDaemons/local.claude-net-wall.plist
has_label "$anchor" claude-net-wall-ipv4 && has_label "$anchor" claude-net-wall-ipv6 || { echo "装载后规则不在，失败" >&2; exit 74; }
echo "[OK] Anthropic 整段墙（锚点 011）已装载。名单："; pfctl -a "$anchor" -t claude_wall_nets -T show | sed 's/^/     /'
