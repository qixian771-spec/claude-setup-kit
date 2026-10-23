#!/bin/bash
# 双击：用 sudo 跑一次只读对账（mirror_check --json），结果存 installers/logs/mirror-sudo-latest.json，给 next_step --input 用。
# 只读：查看 PF 规则和描述文件需要 root，这个文件什么都不装、不改。root 执行的是仓库里的 mirror_check.py——和所有 .command 一样，
# 信任的是这份仓库本身；root 不会去执行用户目录下的其他脚本（claude-wall 由用户身份那一次跑）。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/mirror-sudo-$(date +%Y%m%d-%H%M%S).log"
out="installers/logs/mirror-sudo-latest.json"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：提权只读对账（什么都不装）"
  # Root gets a clean environment and no network: it must not pick up a user-writable curl/dig from PATH, and a
  # probe from root would bypass the per-user PF rule if the TUN ever dropped. Network items stay ❓ here on purpose;
  # the user-mode run covers them.
  # Two passes, then merge: (1) as the user, with network — everything that does not need root (exit IP, DNS,
  # claude-wall status); (2) as root with a clean environment and no network — the PF/profiles items the user cannot
  # read. mirror_check resolves the desktop user from SUDO_UID (env -i would drop it). An item is taken from the root
  # pass unless root could not tell (❓) and the user pass could.
  user_json="installers/logs/mirror-sudo-user.json"; root_json="installers/logs/mirror-sudo-root.json"
  if /usr/bin/python3 scripts/mirror_check.py --json > "$user_json"; then user_rc=0; else user_rc=$?; fi  # 1/2 = has ❌/❓, still usable
  if sudo env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$HOME" USER="$USER" SUDO_UID="$(id -u)" SUDO_USER="$USER" LC_ALL=C /usr/bin/python3 -E -s scripts/mirror_check.py --json --no-network > "$root_json"; then root_rc=0; else root_rc=$?; fi
  if [ -s "$root_json" ] && [ -s "$user_json" ] && /usr/bin/python3 - "$user_json" "$root_json" "$out" <<'PY'
import json, sys
user, root = (json.load(open(f, encoding="utf-8")) for f in sys.argv[1:3])
by_user = {i["id"]: i for i in user["items"]}
items = []
for r in root["items"]:
    u = by_user.get(r["id"])
    items.append(u if (r["status"] == "UNKNOWN" and u and u["status"] != "UNKNOWN") else r)
statuses = {i["status"] for i in items}
exit_code = 1 if "FAIL" in statuses else 2 if "UNKNOWN" in statuses else 0
merged = dict(user, items=items, exit=exit_code, note=(user.get("note") or ""), merged_from=["user", "root(--no-network)"])
json.dump(merged, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  then rc=0; mirror_rc=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["exit"])' "$out"); else rc=1; mirror_rc="?"; : > "$out"; echo "用户身份那次退出 ${user_rc:-?}（输出 $(wc -c < "$user_json" | tr -d ' ') 字节），root 那次退出 ${root_rc:-?}（输出 $(wc -c < "$root_json" | tr -d ' ') 字节）"; fi
  if [ -s "$out" ]; then
    /usr/bin/python3 - "$out" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
m = {"PASS": "✅", "FAIL": "❌", "UNKNOWN": "❓", "INFO": "ℹ️", "MANUAL": "👉"}
for i in d["items"]:
    print("%s %-16s %s" % (m.get(i["status"], "?"), i["id"], i["evidence"]))
c = {k: sum(1 for i in d["items"] if i["status"] == k) for k in m}
print("合计: ✅ %d  ❌ %d  ❓ %d  ℹ️ %d  👉 %d  共 %d 项  → exit %d" % (c["PASS"], c["FAIL"], c["UNKNOWN"], c["INFO"], c["MANUAL"], len(d["items"]), d["exit"]))
PY
    echo "结果已写到 ${out}；接下来 AI 运行: python3 scripts/next_step.py --input $out"
  else
    echo "两次对账里至少一次没有输出或合并失败（root 那次为空多半是 sudo 密码没通过；用户那次为空看上面的退出码），没有合并结果；上一次的结果已被清掉"
  fi
  echo "MIRROR_EXIT=${mirror_rc}（合并后对账的退出码：0 全 ✅ / 1 有 ❌ / 2 有 ❓；root 那一次本身退出 ${root_rc:-?}）"
  echo "EXIT=${rc}"
} 2>&1 | tee -a "$log"
echo; echo "日志: $log"
read -r -p "对账结束，按回车关闭这个窗口" _
