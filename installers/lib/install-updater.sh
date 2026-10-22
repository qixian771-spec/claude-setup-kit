#!/bin/sh
# Address updater: as the desktop user every 15 min, refreshes anchor 010's exact-IP table from the Clash DNS cache.
# Needs a narrow sudoers rule (installed here after visudo -cf) and the 010 wall already in place.
set -eu
. "$(dirname "$0")/common.sh"; need_root; need_build "${1:-}"
pkg="/Library/Application Support/ClaudeDirectWallUpdater"; state="$MIRROR_HOME/Library/Application Support/ClaudeDirectWallUpdater"
plist=$(src system/LaunchDaemons/local.claude-address-update.plist); sudoers=$(src system/sudoers/claude-mac-env-mirror)
refuse_existing "$pkg" "$state" /Library/LaunchDaemons/local.claude-address-update.plist /etc/sudoers.d/claude-mac-env-mirror
[ -x /usr/local/libexec/claude-direct-wall ] || { echo "先装 Claude 直连墙（010）" >&2; exit 73; }
[ -d "$BUILD/system/updater/vendor/ruamel/yaml" ] || { echo "缺少 vendor/ruamel" >&2; exit 71; }
visudo -cf "$sudoers" >/dev/null || { echo "sudoers 规则语法错误，停止" >&2; exit 65; }
mkdir -p "$pkg"; chown root:wheel "$pkg"; chmod 755 "$pkg"
(cd "$BUILD/system/updater" && find . -type d -exec install -d -o root -g wheel -m 755 "$pkg/{}" \; \
   && find . -type f ! -name 'sha256.json' -exec install -o root -g wheel -m 644 "{}" "$pkg/{}" \;)
# runner.py verifies every file against sha256.json before importing anything.
(cd "$pkg" && find . -type f ! -name sha256.json | sed 's|^\./||' | sort | while read -r f; do printf '  "%s": "%s"' "$f" "$(shasum -a 256 "$f" | cut -d' ' -f1)"; echo ','; done) \
   | sed '$ s/,$//' | { echo '{'; cat; echo '}'; } > "$pkg/sha256.json"
chown root:wheel "$pkg/sha256.json"; chmod 644 "$pkg/sha256.json"
install -d -o "$MIRROR_USER" -m 700 "$state"
install -o root -g wheel -m 440 "$sudoers" /etc/sudoers.d/claude-mac-env-mirror
install -o root -g wheel -m 644 "$plist" /Library/LaunchDaemons/local.claude-address-update.plist
launchctl bootstrap system /Library/LaunchDaemons/local.claude-address-update.plist
sleep 15
[ -f "$state/stdout.log" ] && grep -q '"status"' "$state/stdout.log" || { echo "更新器首轮没有写日志，失败（看 $state/stderr.log）" >&2; exit 74; }
echo "[OK] 地址更新器已装（每 15 分钟）。首轮结果："; tail -1 "$state/stdout.log" | cut -c1-160
