#!/bin/bash
# 双击一键撤回全部（macOS）：按安全逆序卸掉本套件安装的更新器、自检守护、三道 PF 墙、IPv6 守护与体检命令。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/rollback-all-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：macOS 一键撤回全部"
  rc=0
  b_up=$(/usr/bin/python3 scripts/render.py --component updater | head -1) || rc=2
  b_v6=$(/usr/bin/python3 scripts/render.py --component ipv6-guard | head -1) || rc=2
  if [ "$rc" = 0 ]; then
    echo "请输入 1 次开机密码以撤回系统级防护（输入时不显示字符，输完按回车）："
    sudo sh "installers/lib/rollback-all-mac.sh" "$b_up" "$b_v6" || rc=$?
  fi
  if [ "$rc" = 0 ] && [ -e "$HOME/.local/bin/claude-wall" ]; then
    sh "installers/lib/uninstall-claude-wall.sh" || rc=$?
  fi
  echo "EXIT=${rc}"
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "撤回结束，按回车关闭这个窗口" _
