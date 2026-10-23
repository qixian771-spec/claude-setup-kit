#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
label=$(sed -n 's/^IPV6_LABEL=//p' "$BUILD/PARAMS.txt" | head -1)
# Only remove what this kit installed under this label: a machine whose guard runs under another label (the
# reference Mac uses com.niuniu.ipv6-guard) must not lose ~/.local/bin/ipv6-guard.sh.
[ -f "/Library/LaunchDaemons/$label.plist" ] || { echo "[ERROR] 没有 /Library/LaunchDaemons/$label.plist：这台机器的 IPv6 守护不是用 label $label 装的，不动它。先 ls /Library/LaunchDaemons | grep -i ipv6 找到真正的 label，写进 mirror.params.json 的 ipv6_guard_label 再渲染、再卸载。" >&2; exit 73; }
bootout_if_loaded "$label"
rm -f "/Library/LaunchDaemons/$label.plist" "$MIRROR_HOME/.local/bin/ipv6-guard.sh"
echo "[OK] IPv6 守护已移除；IPv6 仍是关闭状态，要打开请在系统设置里手动改。"
