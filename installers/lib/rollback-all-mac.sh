#!/bin/sh
# Elevated rollback orchestrator invoked by installers/一键撤回全部.command.
# Uninstalls installed kit components in safe reverse dependency order.
set -eu
. "$(dirname "$0")/common.sh"
need_root

b_up=${1:-}; b_v6=${2:-}
[ -d "$b_up" ] && [ -d "$b_v6" ] || {
    echo "用法: $0 <updater_build> <ipv6_build>" >&2
    exit 64
}
lib_dir=$(cd "$(dirname "$0")" && pwd)
label=$(sed -n 's/^IPV6_LABEL=//p' "$b_v6/PARAMS.txt" | head -1)

if [ -f /Library/LaunchDaemons/local.claude-address-update.plist ] || [ -e "/Library/Application Support/ClaudeDirectWallUpdater" ] || [ -f /etc/sudoers.d/claude-mac-env-mirror ]; then
    echo "== 卸载 updater =="
    sh "${lib_dir}/uninstall-updater.sh" "$b_up"
fi
if [ -f /Library/LaunchDaemons/local.net-guard-watch.plist ] || [ -e /usr/local/libexec/net-guard-watch ]; then
    echo "== 卸载 watch =="
    sh "${lib_dir}/uninstall-watch.sh"
fi
if [ -f /Library/LaunchDaemons/local.leak-guard.plist ] || [ -f /etc/pf.anchors/local.leak-guard ]; then
    echo "== 卸载 leak-guard（020） =="
    sh "${lib_dir}/uninstall-leak-guard.sh"
fi
if [ -f /Library/LaunchDaemons/local.claude-net-wall.plist ] || [ -f /etc/pf.anchors/local.claude-net-wall ]; then
    echo "== 卸载 net-wall（011） =="
    sh "${lib_dir}/uninstall-net-wall.sh"
fi
if [ -f /Library/LaunchDaemons/local.claude-direct-wall.plist ] || [ -f /etc/pf.anchors/local.claude-direct-wall ]; then
    echo "== 卸载 direct-wall（010） =="
    sh "${lib_dir}/uninstall-direct-wall.sh"
fi
if [ -f "/Library/LaunchDaemons/${label}.plist" ] && [ -x /usr/local/libexec/ipv6-guard.sh ]; then
    prog=""
    if prog=$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "/Library/LaunchDaemons/${label}.plist" 2>/dev/null); then
        :
    fi
    if [ "$prog" = "/usr/local/libexec/ipv6-guard.sh" ]; then
        echo "== 卸载 ipv6-guard（${label}） =="
        sh "${lib_dir}/uninstall-ipv6-guard.sh" "$b_v6"
    else
        echo "[保留] ${label} 不是本套件安装的脚本（${prog}），按安全规则不删"
    fi
fi
echo "[OK] root 级防护组件已全部撤回。"
