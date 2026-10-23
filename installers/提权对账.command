#!/bin/bash
# 双击：用 sudo 跑一次只读对账（mirror_check --json），结果存 installers/logs/mirror-sudo-latest.json，给 next_step --input 用。
# 只读：查看 PF 规则和描述文件需要 root，这个文件什么都不装、不改。
cd "$(dirname "$0")/.." || exit 2
mkdir -p installers/logs
log="installers/logs/mirror-sudo-$(date +%Y%m%d-%H%M%S).log"
out="installers/logs/mirror-sudo-latest.json"
{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') 开始：提权只读对账（什么都不装）"
  if sudo /usr/bin/python3 scripts/mirror_check.py --json > "$out"; then rc=0; else rc=$?; fi
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
    echo "mirror_check 没有输出（多半是 sudo 密码没通过）"
  fi
  echo "EXIT=$rc"
} 2>&1 | tee -a "$log"
echo; echo "日志: $log"
read -r -p "对账结束，按回车关闭这个窗口" _
