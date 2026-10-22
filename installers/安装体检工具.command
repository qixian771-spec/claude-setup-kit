#!/bin/bash
# 双击安装：claude-wall 体检命令（无需 root）。先用 scripts/render.py 按本机参数渲染，再运行 installers/lib/install-claude-wall.sh；全部输出同时写进 installers/logs/。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/claude-wall-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：claude-wall 体检命令（无需 root）"
  if build=$(python3 scripts/render.py --component claude-wall | head -1) && [ -d "$build" ]; then
    echo "渲染目录: $build"; cat "$build/PARAMS.txt"
    sh "installers/lib/install-claude-wall.sh" "$build"
    echo "EXIT=$?"
  else
    echo "渲染失败，没有安装任何东西"; echo "EXIT=2"
  fi
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "安装结束，按回车关闭这个窗口" _
