#!/bin/sh
# Replace an IPv6 guard installed by hand or by an older kit (its script under the user's home, executed as root)
# with this kit's root-owned one, keeping the label from PARAMS.txt. Refuses anything it does not recognise.
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
label=$(sed -n 's/^IPV6_LABEL=//p' "$BUILD/PARAMS.txt" | head -1); plist="/Library/LaunchDaemons/$label.plist"
[ -f "$plist" ] || { echo "[ERROR] 没有 ${plist}：没有旧守护可迁移，直接双击 安装IPv6守护.command" >&2; exit 73; }
if ! old=$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "$plist" 2>/dev/null); then echo "[ERROR] 读不出 ${plist} 的 ProgramArguments，不动它" >&2; exit 73; fi
[ "$old" != /usr/local/libexec/ipv6-guard.sh ] || { echo "已经是本套件的 root 守护，不用迁移" >&2; exit 72; }
case "$old" in "$MIRROR_HOME"/*) ;; *) echo "[ERROR] 旧守护脚本 ${old} 不在用户目录下，不自动删；请手动处理后再装" >&2; exit 73;; esac
bootout_if_loaded "$label"
rm -f "$plist" "$old"
echo "[OK] 旧守护 ${label}（${old}）已卸下，开始装本套件的 root 守护"
exec sh "$(dirname "$0")/install-ipv6-guard.sh" "$BUILD"
