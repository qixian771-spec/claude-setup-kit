#!/usr/bin/env python3
"""Validate packaging: metadata, resource links, manifest/doc coverage and syntax. Runs nothing operational."""
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def frontmatter(text):
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    require(match is not None, "SKILL.md 缺少 YAML frontmatter")
    meta = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def main():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    meta = frontmatter(skill)
    require(meta.get("name") == "claude-setup-kit", "skill name 不对")
    require(0 < len(meta.get("description", "")) <= 1024, "description 缺失或超过 1024 字符")
    require(meta.get("license") == "MIT", "license 应为 MIT")
    require(set(meta) <= {"name", "description", "license"}, "frontmatter 有未知键")

    # Every relative link in the Markdown must resolve to a file.
    docs = [ROOT / "SKILL.md", ROOT / "README.md"] + sorted((ROOT / "references").glob("*.md")) + sorted((ROOT / "docs").glob("*.md"))
    for doc in docs:
        for link in re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", doc.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            require((doc.parent / link).resolve().exists(), "%s: 链接不存在 %s" % (doc.name, link))

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in manifest["components"]]
    runbook = (ROOT / "references" / "runbook.md").read_text(encoding="utf-8")
    missing = [i for i in ids if "`%s`" % i not in runbook]
    require(not missing, "执行手册没有提到这些组件 id: %s" % missing)
    for comp in manifest["components"]:
        for rel in re.findall(r"installers/[^\s（）,;。；：，]+", comp["next"]):
            require((ROOT / rel).is_file(), "%s 的下一步指向不存在的 %s" % (comp["id"], rel))
    for launcher in (ROOT / "installers").glob("安装*.command"):
        require(launcher.name in runbook, "手册没有提到 %s" % launcher.name)
    sys.path.insert(0, str(ROOT / "scripts"))
    import next_step  # validates steps ↔ components consistency
    steps = next_step.load_manifest(ROOT / "manifest.json")["steps"]
    appendix = runbook.split("## 附录 B", 1)[1]
    for step in steps:
        require("| %s |" % step["id"] in appendix, "附录 B 缺步骤 %s" % step["id"])
        for cid in step.get("components", []) + step.get("manual", []) + step.get("info", []):
            require("`%s`" % cid in appendix, "附录 B 缺组件 %s" % cid)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    require("发给 AI 的一段话" in readme and "START.md" in readme, "README 必须有“发给 AI 的一段话”并指向 START.md")
    start = (ROOT / "START.md").read_text(encoding="utf-8")
    for needle in ("vps-node-rebuild-3xui", "claude-client-full-reset", "next_step.py", "ippure"):
        require(needle in start, "START.md 缺 %s" % needle)
    ui = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    require("$claude-setup-kit" in ui, "agents/openai.yaml 的 default_prompt 必须点名 skill")
    for name in ("LICENSE", ".gitignore", "START.md", ".github/workflows/validate.yml", "manifest.json", "assets/webrtc-test.html",
                 "installers/Chrome策略.mobileconfig", "templates/clash-profile.template.yaml", "templates/clash-profile.script.js"):
        require((ROOT / name).is_file(), "缺少文件 %s" % name)

    counts = {"python": 0, "sh": 0, "command": 0}
    for path in sorted(list((ROOT / "scripts").glob("*.py")) + list((ROOT / "tools").glob("*.py")) + list((ROOT / "tests").glob("*.py"))):
        py_compile.compile(str(path), doraise=True)
        text = path.read_text(encoding="utf-8")
        require(not re.search(r"\bopen\([^)]*\)", text) or "encoding=" in text, "%s: open() 需要 encoding=" % path.name)
        counts["python"] += 1
    for path in sorted((ROOT / "installers" / "lib").glob("*.sh")):
        subprocess.run(["sh", "-n", str(path)], check=True)
        text = path.read_text(encoding="utf-8")
        require("set -eu" in text or path.name == "common.sh", "%s 缺 set -eu" % path.name)
        require("|| true" not in text, "%s 不准用 || true 吞错误" % path.name)
        counts["sh"] += 1
    for path in sorted((ROOT / "installers").glob("*.command")):
        subprocess.run(["bash", "-n", str(path)], check=True)
        require(path.stat().st_mode & 0o100, "%s 不可执行" % path.name)
        counts["command"] += 1
    # No machine-specific values in the shipped templates.
    for path in list((ROOT / "system").rglob("*")) + list((ROOT / "templates").rglob("*")):
        if path.is_file() and "vendor" not in path.parts:
            text = path.read_text(encoding="utf-8")
            for bad in ("/Users/", "utun1024", "user 501"):
                require(bad not in text, "%s 含机器相关值 %s" % (path.relative_to(ROOT), bad))
    print("PASS: metadata, links, manifest coverage, syntax", counts)
    print("Operational scripts were not executed; mirror_check and installers are validated separately.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError, py_compile.PyCompileError) as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        sys.exit(1)
