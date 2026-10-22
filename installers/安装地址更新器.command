#!/bin/bash
# 双击安装：Claude 地址更新器（每 15 分钟）+ 最小 sudoers 规则。先用 scripts/render.py 按本机参数渲染，再运行 installers/lib/install-updater.sh；全部输出同时写进 installers/logs/。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/updater-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：Claude 地址更新器（每 15 分钟）+ 最小 sudoers 规则"
  if build=$(python3 scripts/render.py --component updater | head -1) && [ -d "$build" ]; then
    echo "渲染目录: $build"; cat "$build/PARAMS.txt"
    sudo sh "installers/lib/install-updater.sh" "$build"
    echo "EXIT=$?"
  else
    echo "渲染失败，没有安装任何东西"; echo "EXIT=2"
  fi
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "安装结束，按回车关闭这个窗口" _
