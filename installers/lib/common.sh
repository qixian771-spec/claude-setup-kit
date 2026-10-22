# Shared helpers for the install/uninstall scripts. POSIX sh; sourced after `set -eu`.
# Every script takes ONE argument: the directory scripts/render.py produced for its component.
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
LC_ALL=C
export LC_ALL

need_root() { [ "$(id -u)" = 0 ] || { echo "请用 sudo 运行（双击 installers 里的 .command 会自动提权）" >&2; exit 70; }; }
need_build() {
    BUILD=${1:-}
    [ -n "$BUILD" ] && [ -d "$BUILD" ] && [ -f "$BUILD/PARAMS.txt" ] || { echo "用法: $0 <render.py 输出目录>" >&2; exit 64; }
    BUILD=$(cd "$BUILD" && pwd)
    param() { sed -n "s/^$1=//p" "$BUILD/PARAMS.txt" | head -1; }
    MIRROR_USER=$(param USER); MIRROR_HOME=$(param HOME); MIRROR_UID=$(param UID)
    [ -n "$MIRROR_USER" ] && [ -n "$MIRROR_HOME" ] && [ -n "$MIRROR_UID" ] || { echo "PARAMS.txt 不完整" >&2; exit 65; }
}
src() { # src <relative path under BUILD>: the file must exist and not be a link
    [ -f "$BUILD/$1" ] && [ ! -L "$BUILD/$1" ] || { echo "缺少渲染文件: $1" >&2; exit 71; }
    printf '%s\n' "$BUILD/$1"
}
refuse_existing() { # refuse_existing <path>...: never overwrite; uninstall first
    for dst in "$@"; do
        [ ! -e "$dst" ] && [ ! -L "$dst" ] || { echo "已存在，拒绝覆盖: $dst（要重装先运行对应的卸载）" >&2; exit 72; }
    done
}
pf_enabled() { pfctl -s info 2>/dev/null | grep -F 'Status: Enabled' >/dev/null; }
has_label() { pfctl -a "$1" -sr 2>/dev/null | grep -F "label \"$2\"" >/dev/null; }

# Add one `load anchor` line to /etc/pf.conf (after a backup, syntax-checked). Idempotent.
pf_conf_add() { # pf_conf_add <anchor> <rules file>
    line="load anchor \"$1\" from \"$2\""
    if grep -Fqx "$line" /etc/pf.conf; then echo "pf.conf 已有: $line"; return 0; fi
    bk="/etc/pf.conf.bak-mirror-$(date +%Y%m%d-%H%M%S)"
    cp -p /etc/pf.conf "$bk"
    printf '\n# claude-mac-env-mirror\n%s\n' "$line" >> /etc/pf.conf
    if ! pfctl -n -f /etc/pf.conf >/dev/null 2>&1; then
        cp -p "$bk" /etc/pf.conf; echo "pf.conf 语法检查失败，已恢复备份 $bk" >&2; exit 73
    fi
    echo "pf.conf 追加: $line（备份 $bk）"
}
pf_conf_remove() { # pf_conf_remove <anchor>
    grep -F "load anchor \"$1\"" /etc/pf.conf >/dev/null || return 0
    bk="/etc/pf.conf.bak-mirror-$(date +%Y%m%d-%H%M%S)"
    cp -p /etc/pf.conf "$bk"
    tmp=$(mktemp /etc/pf.conf.tmp.XXXXXX)
    grep -vF "load anchor \"$1\"" /etc/pf.conf > "$tmp"
    pfctl -n -f "$tmp" >/dev/null 2>&1 || { rm -f "$tmp"; echo "去掉装载行后 pf.conf 语法检查失败，未改动" >&2; exit 73; }
    cat "$tmp" > /etc/pf.conf; rm -f "$tmp"
    echo "pf.conf 已去掉 $1 的装载行（备份 $bk）"
}
daemon_loaded() { launchctl print "system/$1" >/dev/null 2>&1; }
bootout_if_loaded() { if daemon_loaded "$1"; then launchctl bootout "system/$1"; fi; }
