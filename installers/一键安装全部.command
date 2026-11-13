#!/bin/bash
# 双击一键安装全部（macOS 防偷懒省事版）：只输 1 次开机密码，按顺序自动完成：
#   auto_init（自动识别参数 + 补齐 Claude 14 项隐私静音开关）→ PF 三道墙（S2–S4）→ 地址更新器（S5）→ 自检守护（S6）→ IPv6 守护（S7）→ 体检工具（S8）
# 已安装过的步骤自动跳过，支持中断后续跑；全部输出写进 installers/logs/install-all-*.log。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/install-all-$(date +%Y%m%d-%H%M%S).log"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：macOS 一键安装全部（S2–S8 + 官方隐私静音开关）"
  rc=0
  if ! /usr/bin/python3 scripts/auto_init.py; then
    echo "[ERROR] auto_init 初始化失败"; rc=2
  fi

  skips=$(/usr/bin/python3 -c 'import json,pathlib; p=pathlib.Path("mirror.params.json"); d=json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}; s=d.get("skip_steps") or []; print(",".join(s) if isinstance(s,list) else str(s))' 2>/dev/null)
  tun=$(/usr/bin/python3 -c 'import json,pathlib; m=json.loads(pathlib.Path("manifest.json").read_text(encoding="utf-8"))["params"]; p=pathlib.Path("mirror.params.json"); m.update(json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}); print(m["tun_device"])' 2>/dev/null)

  if [ "$rc" = 0 ]; then
    case ",${skips}," in
      *,S4,*|*,S1,*) ;;
      *)
        if ! ifconfig "$tun" 2>/dev/null | grep -q 'inet '; then
          echo "[ERROR] TUN 接口 ${tun} 还没开启：请先在 Clash Verge 设置里打开 TUN 模式，再双击本文件（否则装上防泄露墙会立刻断网）"
          rc=75
        fi
        ;;
    esac
  fi

  if [ "$rc" = 0 ]; then
    b_dw=$(/usr/bin/python3 scripts/render.py --component direct-wall | head -1) || rc=2
    b_nw=$(/usr/bin/python3 scripts/render.py --component net-wall | head -1) || rc=2
    b_lg=$(/usr/bin/python3 scripts/render.py --component leak-guard | head -1) || rc=2
    b_up=$(/usr/bin/python3 scripts/render.py --component updater | head -1) || rc=2
    b_wa=$(/usr/bin/python3 scripts/render.py --component watch | head -1) || rc=2
    b_v6=$(/usr/bin/python3 scripts/render.py --component ipv6-guard | head -1) || rc=2
    b_cw=$(/usr/bin/python3 scripts/render.py --component claude-wall | head -1) || rc=2
  fi

  if [ "$rc" = 0 ]; then
    echo "参数核对（来自 ${b_dw}/PARAMS.txt）："
    cat "${b_dw}/PARAMS.txt"
    echo ""
    echo "接下来需要输入 1 次开机密码（输入时屏幕不显示字符，输完按回车）："
    if sudo sh "installers/lib/run-all-mac.sh" "$b_dw" "$b_nw" "$b_lg" "$b_up" "$b_wa" "$b_v6" "$skips"; then
      :
    else
      rc=$?
    fi
  fi

  if [ "$rc" = 0 ]; then
    case ",${skips}," in
      *,S8,*|*,S5,*|*,S6,*) echo "[按 skip_steps 跳过] S8 claude-wall" ;;
      *)
        echo ""
        echo "== [7/7] S8 体检工具 claude-wall =="
        if [ -x "$HOME/.local/bin/claude-wall" ]; then
          echo "[已装，跳过] ~/.local/bin/claude-wall 已存在"
        else
          sh "installers/lib/install-claude-wall.sh" "$b_cw" || rc=$?
        fi
        ;;
    esac
  fi

  if [ "$rc" = 0 ] && [ -d "/Applications/Google Chrome.app" ] && [ ! -f "/Library/Managed Preferences/com.google.Chrome.plist" ]; then
    echo ""
    echo "👉 [顺手提示 S9] 检测到 Chrome 尚未安装防泄露描述文件，已为你弹出描述文件窗口："
    echo "   请到【系统设置 → 通用 → 设备管理】里点安装『Claude 环境镜像：Chrome 防泄露策略』，装完后完全退出（⌘Q）重开 Chrome。"
    open "installers/Chrome策略.mobileconfig" >/dev/null 2>&1 || :
  fi

  if [ "$rc" = 0 ] && sudo -n true >/dev/null 2>&1; then
    u_json="installers/logs/mirror-sudo-user.json"
    r_json="installers/logs/mirror-sudo-root.json"
    m_out="installers/logs/mirror-sudo-latest.json"
    /usr/bin/python3 scripts/mirror_check.py --json > "$u_json" 2>/dev/null || :
    sudo -n env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$HOME" USER="$USER" SUDO_UID="$(id -u)" SUDO_USER="$USER" LC_ALL=C /usr/bin/python3 -E -s scripts/mirror_check.py --json --no-network > "$r_json" 2>/dev/null || :
    if [ -s "$u_json" ] && [ -s "$r_json" ]; then
      /usr/bin/python3 - "$u_json" "$r_json" "$m_out" <<'PY' >/dev/null 2>&1 || :
import json, sys
user, root = (json.load(open(f, encoding="utf-8")) for f in sys.argv[1:3])
by_user = {i["id"]: i for i in user["items"]}
items = [by_user[r["id"]] if (r["status"] == "UNKNOWN" and r["id"] in by_user and by_user[r["id"]]["status"] != "UNKNOWN") else r for r in root["items"]]
st = {i["status"] for i in items}
merged = dict(user, items=items, exit=(1 if "FAIL" in st else 2 if "UNKNOWN" in st else 0), merged_from=["user", "root(--no-network)"])
json.dump(merged, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
    fi
  fi

  echo ""
  echo "EXIT=${rc}"
} 2>&1 | grep --line-buffered -v ALTQ | tee -a "$log"
echo; echo "日志: $log"
read -r -p "一键安装结束，按回车关闭这个窗口" _
