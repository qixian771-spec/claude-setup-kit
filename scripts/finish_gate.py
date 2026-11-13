#!/usr/bin/env python3
"""Anti-lazy completion gate (`finish_gate.py`) for claude-setup-kit (macOS & Windows).

AI agents MUST run this script and paste its `FINISH_GATE=PASSED` certificate before declaring the setup finished.
If any non-skipped step is still FAIL (❌) or UNKNOWN (❓) — or if `mirror.params.json` was never initialized — this
script prints a loud `FINISH_GATE=BLOCKED` banner with the exact remaining actions and exits with code 1.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mirror_check as mc  # noqa: E402
import next_step as ns  # noqa: E402


def evaluate_gate(manifest_path, input_path=None, platform=None, require_params_file=True):
    platform = platform or ns.platform_key()
    ns._PLATFORM_OVERRIDE = platform
    manifest = ns.load_manifest(manifest_path, platform)
    local_params = Path(manifest_path).parent / "mirror.params.json"
    cmd_py = "py -3" if platform == "win32" else "python3"

    if require_params_file and not local_params.exists():
        return 1, {
            "gate": "BLOCKED",
            "reason": "missing_params_file",
            "message": "仓库根目录还没有 mirror.params.json（尚未绑定本机出口节点与网卡）",
            "next_command": "%s scripts/auto_init.py" % cmd_py,
        }

    if input_path:
        result = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    else:
        extra = ["--platform", platform] if platform else []
        result = ns.run_mirror_check(manifest_path, extra)
        sudo_cache = Path(manifest_path).parent / "installers" / "logs" / "mirror-sudo-latest.json"
        if platform == "darwin" and sudo_cache.is_file():
            try:
                cache_mtime = sudo_cache.stat().st_mtime
                stale_for_profiles = any(
                    Path(p).exists() and Path(p).stat().st_mtime > cache_mtime
                    for p in (
                        "/Library/Managed Preferences/com.google.Chrome.plist",
                        "/Library/Managed Preferences/com.anthropic.claudefordesktop.plist",
                        "/etc/pf.anchors/local.claude-direct-wall",
                    )
                )
                if not stale_for_profiles:
                    cached = json.loads(sudo_cache.read_text(encoding="utf-8-sig"))
                    by_cached = {i["id"]: i for i in (cached.get("items") or [])}
                    merged_items = []
                    for item in (result.get("items") or []):
                        if item.get("status") == mc.UNKNOWN and "sudo" in (item.get("evidence") or ""):
                            c_item = by_cached.get(item["id"])
                            if c_item and c_item.get("status") != mc.UNKNOWN:
                                merged_items.append(c_item)
                                continue
                        merged_items.append(item)
                    result["items"] = merged_items
            except (OSError, ValueError, KeyError, TypeError):
                pass
    decision = ns.decide(manifest, result)

    items = result.get("items") or []
    counts = {k: sum(1 for i in items if i.get("status") == k) for k in (mc.PASS, mc.FAIL, mc.UNKNOWN, mc.INFO, mc.MANUAL)}

    if decision["state"] != "all_passed":
        # Collect ALL remaining pending steps so a lazy AI sees everything left, not just one item
        status_map = {i["id"]: i["status"] for i in items}
        raw_skips = (result.get("params") or {}).get("skip_steps") or []
        skips = set(s.strip() for s in (raw_skips.split(",") if isinstance(raw_skips, str) else raw_skips) if s.strip())
        pending_steps = []
        for st in manifest["steps"]:
            if st["id"] in skips:
                continue
            st_state, failing = ns.step_state(st, status_map)
            if st_state == "pending":
                pending_steps.append({"id": st["id"], "title": st["title"], "failing": [cid for cid, _ in failing]})
        return 1, {
            "gate": "BLOCKED",
            "platform": platform,
            "counts": counts,
            "current_step": decision,
            "pending_steps": pending_steps,
        }

    by_id = {i["id"]: i for i in items}
    params = result.get("params") or {}
    exit_node = params.get("exit_node", "?")
    gen_utc = result.get("generated_utc", "")
    digest_raw = "%s|%s|%s|%s" % (
        platform,
        exit_node,
        gen_utc,
        ",".join("%s:%s" % (i["id"], i["status"]) for i in items),
    )
    gate_code = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()[:12].upper()
    return 0, {
        "gate": "PASSED",
        "gate_code": gate_code,
        "platform": platform,
        "exit_node": exit_node,
        "generated_utc": gen_utc,
        "counts": counts,
        "total": len(items),
        "skipped": decision.get("skipped") or {},
        "privacy_evidence": by_id.get("claude.privacy", {}).get("evidence", ""),
        "exit_ip_evidence": by_id.get("net.exit_ip", {}).get("evidence", "（已跳过）"),
        "dns_evidence": by_id.get("dns.upstream", {}).get("evidence", "（已跳过）"),
        "say": decision.get("say", ""),
    }


def render_gate(code, data):
    if code != 0:
        lines = [
            "============================================================",
            "🚫 交卷被拒（FINISH_GATE=BLOCKED）—— 严禁向用户宣布已完成！",
            "============================================================",
        ]
        if data.get("reason") == "missing_params_file":
            lines.append("原因: " + data["message"])
            lines.append("AI 现在立刻运行: " + data["next_command"])
            return "\n".join(lines)
        psteps = data.get("pending_steps") or []
        lines.append("还剩 %d 个步骤未通过：%s" % (
            len(psteps),
            "、".join("%s(%s)" % (s["id"], s["title"]) for s in psteps),
        ))
        lines.append("")
        lines.append(ns.render(data["current_step"]))
        lines.append("")
        lines.append("⚠️ AI 铁律：把上面列出的待做项全部完成后，再次运行 finish_gate.py 直到拿到 FINISH_GATE=PASSED！")
        return "\n".join(lines)

    c = data["counts"]
    skipped = data["skipped"]
    skip_txt = "无（全量完成）" if not skipped else "；".join("%s（%s）" % kv for kv in skipped.items())
    return "\n".join([
        "============================================================",
        "🎉 通关核验通过（FINISH_GATE=PASSED  核验码=%s）" % data["gate_code"],
        "============================================================",
        "平台: %s  |  固定主出口: %s  |  时间(UTC): %s" % (data["platform"], data["exit_node"], data["generated_utc"]),
        "对账合计: ✅ %d  ❌ %d  ❓ %d  ℹ️ %d  👉 %d（共 %d 项）" % (
            c[mc.PASS], c[mc.FAIL], c[mc.UNKNOWN], c[mc.INFO], c[mc.MANUAL], data["total"]
        ),
        "隐私开关: %s" % data["privacy_evidence"],
        "出口实测: %s" % data["exit_ip_evidence"],
        "DNS 实测: %s" % data["dns_evidence"],
        "未授权跳过: %s" % skip_txt,
        "",
        "【请把以上核验单贴给用户，并请用户完成最后一步浏览器截图】",
        "对用户说: “%s”" % data["say"],
    ])


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    ap.add_argument("--input", help="使用提权对账生成的 mirror-sudo-latest.json")
    ap.add_argument("--platform", choices=("darwin", "win32"), help="（测试/CI 用）")
    ap.add_argument("--allow-default-params", action="store_true", help="（仅参考机自检/测试用）允许无 mirror.params.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        code, data = evaluate_gate(
            args.manifest,
            input_path=args.input,
            platform=args.platform,
            require_params_file=not args.allow_default_params,
        )
    except Exception as exc:
        print("[ERROR] finish_gate 运行失败: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_gate(code, data))
    return code


if __name__ == "__main__":
    sys.exit(main())
