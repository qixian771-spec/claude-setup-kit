#!/bin/bash
# 双击卸载：输入组件名后运行对应的 installers/lib/uninstall-*.sh。卸载顺序建议：updater → watch → leak-guard → net-wall → direct-wall。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
echo "可卸载的组件：direct-wall  net-wall  leak-guard  watch  ipv6-guard  updater  claude-wall"
read -r -p "输入要卸载的组件名（回车取消）： " comp
case "$comp" in
  direct-wall|net-wall|leak-guard|watch|ipv6-guard|updater|claude-wall) ;;
  "") echo "已取消"; exit 0 ;;
  *) echo "不认识的组件: $comp"; exit 64 ;;
esac
log="installers/logs/uninstall-$comp-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 卸载 $comp"
  case "$comp" in
    ipv6-guard|updater)
      build=$(python3 scripts/render.py --component "$comp" | head -1) && sudo sh "installers/lib/uninstall-$comp.sh" "$build" ;;
    claude-wall) sh installers/lib/uninstall-claude-wall.sh ;;
    *) sudo sh "installers/lib/uninstall-$comp.sh" ;;
  esac
  echo "EXIT=$?"
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "卸载结束，按回车关闭这个窗口" _
