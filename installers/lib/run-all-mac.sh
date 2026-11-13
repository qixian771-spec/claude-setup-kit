#!/bin/sh
# Elevated orchestrator invoked by installers/一键安装全部.command (single sudo prompt, resumable).
# Skips components that are already installed and verified; stops immediately on any real error.
set -eu
. "$(dirname "$0")/common.sh"
need_root

b_dw=${1:-}; b_nw=${2:-}; b_lg=${3:-}; b_up=${4:-}; b_wa=${5:-}; b_v6=${6:-}; skips=",${7:-},"
[ -d "$b_dw" ] && [ -d "$b_nw" ] && [ -d "$b_lg" ] && [ -d "$b_up" ] && [ -d "$b_wa" ] && [ -d "$b_v6" ] || {
    echo "用法: $0 <dw> <nw> <lg> <up> <wa> <v6> [skip_steps]" >&2
    exit 64
}
lib_dir=$(cd "$(dirname "$0")" && pwd)
need_build "$b_v6"
label=$(sed -n 's/^IPV6_LABEL=//p' "$b_v6/PARAMS.txt" | head -1)
service=$(sed -n 's/^WIFI_SERVICE=//p' "$b_v6/PARAMS.txt" | head -1)
mirror_home=$(sed -n 's/^HOME=//p' "$b_v6/PARAMS.txt" | head -1)

is_skipped() {
    case "$skips" in *,"$1",*) return 0 ;; *) return 1 ;; esac
}

echo ""
echo "== [1/6] S2 Claude 直连墙（PF 锚点 010） =="
if is_skipped S2; then
    echo "[按 skip_steps 跳过] S2"
elif [ -f /etc/pf.anchors/local.claude-direct-wall ] && [ -x /usr/local/libexec/claude-direct-wall ] \
    && [ -f /Library/LaunchDaemons/local.claude-direct-wall.plist ] \
    && has_label com.apple/010.local.claude-direct-wall claude-wall-ipv4; then
    echo "[已装，跳过] Claude 直连墙（010）已在运行"
else
    sh "${lib_dir}/install-direct-wall.sh" "$b_dw"
fi

echo ""
echo "== [2/6] S3 Anthropic 整段墙（PF 锚点 011） =="
if is_skipped S3 || is_skipped S2; then
    echo "[按 skip_steps 跳过] S3"
elif [ -f /etc/pf.anchors/local.claude-net-wall ] && [ -x /usr/local/libexec/claude-net-wall ] \
    && [ -f /Library/LaunchDaemons/local.claude-net-wall.plist ] \
    && has_label com.apple/011.local.claude-net-wall claude-net-wall-ipv4; then
    echo "[已装，跳过] Anthropic 整段墙（011）已在运行"
else
    sh "${lib_dir}/install-net-wall.sh" "$b_nw"
fi

echo ""
echo "== [3/6] S4 防泄露墙（PF 锚点 020） =="
if is_skipped S4 || is_skipped S1 || is_skipped S2 || is_skipped S3; then
    echo "[按 skip_steps 跳过] S4"
elif [ -f /etc/pf.anchors/local.leak-guard ] && [ -x /usr/local/libexec/leak-guard-loader ] \
    && [ -f /Library/LaunchDaemons/local.leak-guard.plist ] \
    && has_label com.apple/020.local.leak-guard leak-guard-user-public; then
    echo "[已装，跳过] 防泄露墙（020）已在运行"
else
    sh "${lib_dir}/install-leak-guard.sh" "$b_lg"
fi

echo ""
echo "== [4/6] S5 地址更新器与最小免密对账助手 =="
if is_skipped S5 || is_skipped S2; then
    echo "[按 skip_steps 跳过] S5"
elif [ -f "/Library/Application Support/ClaudeDirectWallUpdater/sha256.json" ] \
    && [ -x /usr/local/libexec/claude-pf-helper ] \
    && [ -f /etc/sudoers.d/claude-mac-env-mirror ] \
    && [ -f /Library/LaunchDaemons/local.claude-address-update.plist ] \
    && daemon_loaded local.claude-address-update; then
    echo "[已装，跳过] 地址更新器已在运行"
else
    sh "${lib_dir}/install-updater.sh" "$b_up"
fi

echo ""
echo "== [5/6] S6 自检守护 =="
if is_skipped S6 || is_skipped S2 || is_skipped S3 || is_skipped S4; then
    echo "[按 skip_steps 跳过] S6"
elif [ -x /usr/local/libexec/net-guard-watch ] \
    && [ -f /usr/local/libexec/net-guard-watch-lib.sh ] \
    && [ -f /Library/LaunchDaemons/local.net-guard-watch.plist ] \
    && daemon_loaded local.net-guard-watch; then
    echo "[已装，跳过] 自检守护已在运行"
else
    sh "${lib_dir}/install-watch.sh" "$b_wa"
fi

echo ""
echo "== [6/6] S7 IPv6 关闭与守护 =="
if is_skipped S7; then
    echo "[按 skip_steps 跳过] S7"
elif [ -f "/Library/LaunchDaemons/${label}.plist" ]; then
    prog=""
    if prog=$(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments:0' "/Library/LaunchDaemons/${label}.plist" 2>/dev/null); then
        :
    fi
    case "$prog" in
        "${mirror_home}"/*)
            echo "[自动迁移] 检测到旧版用户目录 IPv6 守护（${prog}），迁移为 root 守护..."
            sh "${lib_dir}/migrate-ipv6-guard.sh" "$b_v6"
            ;;
        *)
            if [ -n "$prog" ] && [ -x "$prog" ] && [ ! -L "$prog" ] && [ "$(stat -f '%u' "$prog")" = 0 ]; then
                networksetup -setv6off "$service"
                echo "[已装，跳过] IPv6 root 守护（${label} → ${prog}）已在运行"
            else
                echo "[ERROR] 已有 ${label}.plist，但执行目标 ${prog} 异常且不在用户目录下，请先检查后再运行" >&2
                exit 73
            fi
            ;;
    esac
else
    sh "${lib_dir}/install-ipv6-guard.sh" "$b_v6"
fi

echo ""
echo "[OK] root 级组件处理完毕。"
