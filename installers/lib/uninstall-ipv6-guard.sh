#!/bin/sh
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
label=$(sed -n 's/^IPV6_LABEL=//p' "$BUILD/PARAMS.txt" | head -1)
# Only remove what this kit installed: the plist must exist under this label AND point at our script. A guard
# installed by someone else (the reference Mac's com.niuniu.ipv6-guard runs ~/.local/bin/ipv6-guard.sh) is left alone.
[ -f "/Library/LaunchDaemons/$label.plist" ] || { echo "[ERROR] 没有 /Library/LaunchDaemons/$label.plist：这台机器的 IPv6 守护不是用 label $label 装的，不动它。先 ls /Library/LaunchDaemons | grep -i ipv6 找到真正的 label，写进 mirror.params.json 的 ipv6_guard_label 再渲染、再卸载。" >&2; exit 73; }
if ! prog=$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "/Library/LaunchDaemons/$label.plist" 2>/dev/null); then echo "[ERROR] 读不出 /Library/LaunchDaemons/$label.plist 的 ProgramArguments，不动它。" >&2; exit 73; fi
[ "$prog" = /usr/local/libexec/ipv6-guard.sh ] || { echo "[ERROR] /Library/LaunchDaemons/$label.plist 执行的是 '$prog'，不是本套件的 /usr/local/libexec/ipv6-guard.sh：这不是本套件装的守护，不动它。" >&2; exit 73; }
bootout_if_loaded "$label"
rm -f "/Library/LaunchDaemons/$label.plist" /usr/local/libexec/ipv6-guard.sh
echo "[OK] IPv6 守护已移除；IPv6 仍是关闭状态，要打开请在系统设置里手动改。"
