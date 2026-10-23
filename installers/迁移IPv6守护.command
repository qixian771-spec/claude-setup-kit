#!/bin/bash
# 双击迁移：把旧的 IPv6 守护（脚本在用户目录、以 root 执行）换成本套件 root 持有的守护，label 不变。渲染后运行 installers/lib/migrate-ipv6-guard.sh。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/ipv6-guard-migrate-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：迁移旧 IPv6 守护到 root 持有的脚本"
  if build=$(python3 scripts/render.py --component ipv6-guard | head -1) && [ -d "$build" ]; then
    echo "渲染目录: $build"; cat "$build/PARAMS.txt"
    sudo sh "installers/lib/migrate-ipv6-guard.sh" "$build"
    echo "EXIT=$?"
  else
    echo "渲染失败，没有安装任何东西"; echo "EXIT=2"
  fi
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "安装结束，按回车关闭这个窗口" _
