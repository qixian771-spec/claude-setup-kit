#!/bin/bash
# ipv6-guard.sh
# 驻守 Wi-Fi 的 IPv6「关闭」状态，防止被系统更新 / 网络重建 / VPN 软件意外恢复。
# 由 LaunchDaemon {{IPV6_LABEL}} 以 root 身份调用。
#
# 临时放行 :  touch {{HOME}}/.ipv6-guard-off
# 解除放行 :  rm -f {{HOME}}/.ipv6-guard-off
# 彻底停用 :  sudo launchctl bootout system/{{IPV6_LABEL}}
#
# 真正启用 IPv6（必须先放行，否则守护会立刻关回）：
#   touch {{HOME}}/.ipv6-guard-off
#   sudo networksetup -setv6automatic Wi-Fi
#   【注意】networksetup 没有 -setv6on；正确命令是 -setv6automatic
set -u

FLAG="{{HOME}}/.ipv6-guard-off"
LOG="/var/log/ipv6-guard.log"  # root writes here, never under the user's HOME (symlink → arbitrary root write)
SERVICE="{{WIFI_SERVICE}}"
IFACE="{{WIFI_IFACE}}"

# 放行开关存在时，守护不干预
[ -f "$FLAG" ] && exit 0

stamp() { /bin/date '+%Y-%m-%d %H:%M:%S'; }

GLOBAL6="$(/sbin/ifconfig "$IFACE" 2>/dev/null \
  | /usr/bin/awk '/inet6/ && $2 !~ /^fe80/ {print $2}' \
  | /usr/bin/tr '\n' ' ')"

CFG="$(/usr/sbin/networksetup -getinfo "$SERVICE" 2>/dev/null \
  | /usr/bin/awk -F': ' '/^IPv6:/{print $2}')"

if [ -n "$GLOBAL6" ] || [ "$CFG" != "Off" ]; then
  printf '[%s] 检出偏差 -> 全局IPv6=[%s] 配置=[%s]\n' "$(stamp)" "$GLOBAL6" "$CFG" >> "$LOG"
  /usr/sbin/networksetup -setv6off "$SERVICE" >> "$LOG" 2>&1
  RC=$?
  printf '[%s] 已执行 setv6off，退出码=%s\n' "$(stamp)" "$RC" >> "$LOG"
fi

exit 0
