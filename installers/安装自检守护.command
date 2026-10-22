#!/bin/bash
# 双击安装：自检守护（每 60 秒重装缺失规则、告警）。先用 scripts/render.py 按本机参数渲染，再运行 installers/lib/install-watch.sh；全部输出同时写进 installers/logs/。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/watch-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：自检守护（每 60 秒重装缺失规则、告警）"
  if build=$(python3 scripts/render.py --component watch | head -1) && [ -d "$build" ]; then
    echo "渲染目录: $build"; cat "$build/PARAMS.txt"
    sudo sh "installers/lib/install-watch.sh" "$build"
    echo "EXIT=$?"
  else
    echo "渲染失败，没有安装任何东西"; echo "EXIT=2"
  fi
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "安装结束，按回车关闭这个窗口" _
