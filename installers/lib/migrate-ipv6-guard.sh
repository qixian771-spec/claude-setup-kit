#!/bin/sh
# Replace an IPv6 guard installed by hand or by an older kit (its script under the user's home, executed as root)
# with this kit's root-owned one, keeping the label from PARAMS.txt. Order: every pre-check first, then a backup of
# the old files, only then unload/remove/install — a failure before the install step leaves the old guard untouched.
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
label=$(sed -n 's/^IPV6_LABEL=//p' "$BUILD/PARAMS.txt" | head -1); service=$(sed -n 's/^WIFI_SERVICE=//p' "$BUILD/PARAMS.txt" | head -1)
case "$label" in ""|*[!A-Za-z0-9._-]*) echo "[ERROR] label '${label}' 不合法" >&2; exit 65;; esac
plist="/Library/LaunchDaemons/$label.plist"
[ -f "$plist" ] || { echo "[ERROR] 没有 ${plist}：没有旧守护可迁移，直接双击 安装IPv6守护.command" >&2; exit 73; }
if ! old=$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "$plist" 2>/dev/null); then echo "[ERROR] 读不出 ${plist} 的 ProgramArguments，不动它" >&2; exit 73; fi
[ "$old" != /usr/local/libexec/ipv6-guard.sh ] || { echo "已经是本套件的 root 守护，不用迁移" >&2; exit 72; }
case "$old" in "$MIRROR_HOME"/*) ;; *) echo "[ERROR] 旧守护脚本 ${old} 不在用户目录下，不自动删；请手动处理后再装" >&2; exit 73;; esac
[ -f "$old" ] && [ ! -L "$old" ] || { echo "[ERROR] ${old} 不是普通文件（不存在或是符号链接），不动" >&2; exit 73; }
[ "$(basename "$old")" = ipv6-guard.sh ] || grep -q 'setv6off' "$old" || { echo "[ERROR] ${old} 看起来不是 IPv6 守护脚本（文件名不是 ipv6-guard.sh、内容也没有 setv6off），不动" >&2; exit 73; }
# Pre-checks of the install that follows, so we never remove the old guard and then fail to install the new one.
refuse_existing /usr/local/libexec/ipv6-guard.sh
networksetup -getinfo "$service" >/dev/null || { echo "网络服务 ${service} 不存在" >&2; exit 65; }
src system/userbin/ipv6-guard.sh >/dev/null; src system/LaunchDaemons/ipv6-guard.plist >/dev/null
backup="/var/db/ipv6-guard-migrate-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$backup"; cp -p "$plist" "$old" "$backup/"
bootout_if_loaded "$label"
rm -f "$plist" "$old"
echo "[OK] 旧守护 ${label}（${old}）已卸下，备份在 ${backup}；开始装本套件的 root 守护"
exec sh "$(dirname "$0")/install-ipv6-guard.sh" "$BUILD"
