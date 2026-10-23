#!/usr/bin/env python3
"""Tell the AI exactly what to do next, from the mirror_check result and manifest.json "steps".

Read-only. Runs mirror_check itself (or reads --input <mirror_check --json file>), then walks the
steps in order and prints the first step that is not yet passed: which components fail, which
prerequisite steps are missing, what the user must double-click, what to say to the user, and
which command to run afterwards. When every step passes it prints the ippure acceptance task.

Exit codes: 0 everything passed (go to ippure); 3 a step is pending (printed); 2 mirror_check
could not be run or the manifest is inconsistent.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS, FAIL, UNKNOWN, INFO, MANUAL = "PASS", "FAIL", "UNKNOWN", "INFO", "MANUAL"


def platform_key():
    # Only macOS and Windows have component tables; anything else (Linux CI runners) uses the macOS set.
    return "win32" if sys.platform.startswith("win") else "darwin"


def load_manifest(path, platform="darwin"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = {c["id"] for c in data["components"] if platform in c.get("platforms", ["darwin"])}
    data["steps"] = data.get("steps_win" if platform == "win32" else "steps", [])
    if not data["steps"]:
        raise ValueError("manifest 还没有 %s 的步骤（Windows 步骤随 W6 提供；对账请直接用 mirror_check.py）" % platform)
    covered = set()
    for step in data["steps"]:
        for key in ("components", "manual", "info", "precheck"):
            for cid in step.get(key, []):
                if cid not in ids:
                    raise ValueError("steps.%s 引用了不存在的组件 %s" % (step["id"], cid))
                if key != "precheck":
                    covered.add(cid)
        for req in step.get("requires", []):
            if req not in {s["id"] for s in data["steps"]}:
                raise ValueError("steps.%s 的前置 %s 不存在" % (step["id"], req))
    missing = ids - covered - {"os"}
    if missing:
        raise ValueError("这些组件没有归到任何步骤: %s" % sorted(missing))
    return data


def run_mirror_check(manifest_path, extra_args):
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "mirror_check.py"), "--json",
                           "--manifest", str(manifest_path)] + list(extra_args),
                          capture_output=True, encoding="utf-8", errors="replace")
    if not proc.stdout.strip():
        raise RuntimeError("mirror_check 没有输出（rc=%s）: %s" % (proc.returncode, proc.stderr.strip()[:200]))
    return json.loads(proc.stdout)


def step_state(step, status):
    """passed / pending; a step with no measurable components (S12) passes when its requires pass."""
    failing = [(cid, status.get(cid, UNKNOWN)) for cid in step.get("components", []) if status.get(cid, UNKNOWN) not in (PASS, INFO, MANUAL)]
    return ("pending" if failing else "passed"), failing


def decide(manifest, result):
    status = {i["id"]: i["status"] for i in result["items"]}
    evidence = {i["id"]: i for i in result["items"]}
    states = {}
    for step in manifest["steps"]:
        state, failing = step_state(step, status)
        if not step.get("components") and any(states.get(r) != "passed" for r in step.get("requires", [])):
            state = "pending"
        states[step["id"]] = state
        if state == "pending":
            blockers = [r for r in step.get("requires", []) if states.get(r) != "passed"]
            if blockers:
                # Do the earliest unmet prerequisite first; it is always an earlier step.
                first = next(s for s in manifest["steps"] if s["id"] == blockers[0])
                return build(first, status, evidence, states, via=step["id"])
            return build(step, status, evidence, states)
    return {"step": None, "state": "all_passed", "exit": 0,
            "ai_action": "python3 scripts/mirror_check.py（贴全量输出）",
            "user_action": "用 Chrome 打开 https://ippure.com/claude.html，等跑完，截上半页和分数区两张图",
            "say": "清单全部通过。最后请用 Chrome 打开 ippure.com/claude.html，等它跑完截两张图，我按四项记录交付。",
            "doc": "references/ippure-acceptance.md"}


def build(step, status, evidence, states, via=None):
    failing = [{"id": cid, "status": status.get(cid, UNKNOWN), "evidence": evidence.get(cid, {}).get("evidence", ""),
                "next": evidence.get(cid, {}).get("next", "")}
               for cid in step.get("components", []) if status.get(cid, UNKNOWN) not in (PASS, INFO, MANUAL)]
    sudo_needed = any("sudo" in f["evidence"] for f in failing if f["status"] == UNKNOWN)
    precheck = [{"id": cid, "status": status.get(cid, UNKNOWN)} for cid in step.get("precheck", [])]
    ids = ",".join(step.get("components", []))
    out = {"step": step["id"], "title": step["title"], "state": "pending", "exit": 3, "via": via,
           "failing": failing, "prerequisites": {r: states.get(r, "pending") for r in step.get("requires", [])},
           "precheck": precheck, "installer": step.get("installer"), "log": step.get("log"),
           "ai_action": step.get("ai_action"), "user_action": step.get("user_action"), "say": step.get("say"),
           "verify": "python3 scripts/mirror_check.py --only %s" % ids if ids else "python3 scripts/mirror_check.py",
           "then": "python3 scripts/next_step.py"}
    if sudo_needed:
        out["note"] = "有 ❓ 是因为需要 sudo：先 `sudo python3 scripts/mirror_check.py --only %s` 再判断，不要当作 ❌ 去重装" % ids
    if any(p["status"] != PASS for p in precheck):
        out["note"] = (out.get("note", "") + "；" if out.get("note") else "") + "前置检查未过（%s），先回去处理，否则安装器会拒装" % ", ".join(p["id"] for p in precheck if p["status"] != PASS)
    return out


MARK = {PASS: "✅", FAIL: "❌", UNKNOWN: "❓", INFO: "ℹ️", MANUAL: "👉"}


def params_hint(manifest_path):
    local = Path(manifest_path).parent / "mirror.params.json"
    if local.exists():
        return None
    return ("提醒: 仓库根目录没有 mirror.params.json，对账用的是参考机默认参数（出口节点 %s）。"
            "先按 START.md 第 0 步写入本机的 exit_node 等参数，再看下面的结果。" % json.loads(Path(manifest_path).read_text(encoding="utf-8"))["params"]["exit_node"])


def render(out):
    if out["state"] == "all_passed":
        return "\n".join(["# 全部步骤通过 → 做 ippure 验收", "AI 先运行: " + out["ai_action"], "让用户做: " + out["user_action"],
                          "对用户说: “%s”" % out["say"], "记录格式: " + out["doc"]])
    lines = ["# 现在做：%s %s" % (out["step"], out["title"])]
    if out.get("via"):
        lines.append("（%s 的前置；先完成这一步）" % out["via"])
    lines.append("未通过:")
    for f in out["failing"]:
        lines.append("  %s %-16s %s" % (MARK.get(f["status"], "?"), f["id"], f["evidence"]))
    if out["prerequisites"]:
        lines.append("前置步骤: " + "  ".join("%s=%s" % (k, "✅" if v == "passed" else "❌") for k, v in out["prerequisites"].items()))
    if out["precheck"]:
        lines.append("前置检查: " + "  ".join("%s %s" % (MARK.get(p["status"], "?"), p["id"]) for p in out["precheck"]))
    if out.get("note"):
        lines.append("注意: " + out["note"])
    if out.get("ai_action"):
        lines.append("AI 先做: " + out["ai_action"])
    if out.get("installer"):
        needs_root = out["installer"].endswith(".command") and out["log"] != "claude-wall"
        lines.append("让用户双击: " + out["installer"]
                     + ("（会弹终端要开机密码，输入时不显示字符）" if needs_root else "")
                     + ("（日志 installers/logs/%s-*.log，看最后 EXIT=）" % out["log"] if out.get("log") else ""))
    if out.get("user_action"):
        lines.append("用户动作: " + out["user_action"])
    if out.get("say"):
        lines.append("对用户说: “%s”" % out["say"])
    lines.append("做完后运行: " + out["verify"])
    lines.append("然后再运行: " + out["then"])
    return "\n".join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles default to GBK; the tables use ✅/❌ and Chinese.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    ap.add_argument("--input", help="用已有的 mirror_check --json 输出文件，不重新检测")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-network", action="store_true", help="传给 mirror_check")
    ap.add_argument("--param", action="append", default=[], help="传给 mirror_check")
    ap.add_argument("--platform", choices=("darwin", "win32"), help="（测试/CI 用）")
    args = ap.parse_args(argv)
    try:
        platform = args.platform or platform_key()
        manifest = load_manifest(args.manifest, platform)
        if args.input:
            result = json.loads(Path(args.input).read_text(encoding="utf-8"))
        else:
            extra = (["--no-network"] if args.no_network else []) + [x for p in args.param for x in ("--param", p)]
            if args.platform:
                extra += ["--platform", args.platform]
            result = run_mirror_check(args.manifest, extra)
        out = decide(manifest, result)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        # KeyError/TypeError: manifest or input JSON missing the expected shape
        print("[ERROR] %s" % exc, file=sys.stderr)
        return 2
    hint = params_hint(args.manifest)
    if hint:
        out["params_hint"] = hint
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render(out) if not hint else hint + "\n\n" + render(out))
    return out["exit"]


if __name__ == "__main__":
    sys.exit(main())
