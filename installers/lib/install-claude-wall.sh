#!/bin/sh
# claude-wall: the user's health-check command. No root; uses sudo -n inside (covered by the updater's sudoers rule).
set -eu
. "$(dirname "$0")/common.sh"; need_build "${1:-}"
[ "$(id -u)" != 0 ] || { echo "这个不要用 sudo 跑" >&2; exit 70; }
tool=$(src system/userbin/claude-wall)
refuse_existing "$HOME/.local/bin/claude-wall"
mkdir -p "$HOME/.local/bin"; install -m 755 "$tool" "$HOME/.local/bin/claude-wall"
"$HOME/.local/bin/claude-wall" status || { echo "claude-wall status 退出码 $?（装好了，但体检没过：按上面的提示处理）"; exit 74; }
echo "[OK] claude-wall 已装到 ~/.local/bin。"
