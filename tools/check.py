#!/usr/bin/env python3
"""Validate packaging: metadata, resource links, manifest/doc coverage and syntax. Runs nothing operational."""
import json
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git_shell(name):
    """Windows: the bash/sh that ships with Git for Windows, even when Git is not on PATH. System32\\bash.exe is the
    WSL launcher (FileNotFoundError / "系统找不到指定的文件" when WSL is absent) and is never used."""
    import os
    roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles(x86)"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    git = shutil.which("git")
    if git:
        roots.insert(0, str(Path(git).resolve().parents[1]))  # <Git>\cmd\git.exe or <Git>\bin\git.exe
    for root in roots:
        if not root:
            continue
        for sub in ("bin", "usr\\bin", "Git\\bin", "Git\\usr\\bin"):
            candidate = Path(root) / sub / (name + ".exe")
            if candidate.exists():
                return str(candidate)
    found = shutil.which(name)
    if found and "system32" not in found.lower():
        return found
    return None


def shell_path(name):
    """Path of bash or sh for `-n` syntax checks; None (never the WSL launcher) when Windows has no Git Bash."""
    if sys.platform == "win32":
        return _git_shell(name)
    found = shutil.which(name)
    if not found:
        raise ValueError("找不到 %s（语法检查需要）" % name)
    return found


def bash_path():
    return shell_path("bash")


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
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles default to a code page that cannot print the Chinese messages.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
    ids = [c["id"] for c in manifest["components"] if "darwin" in c.get("platforms", ["darwin"])]
    for c in manifest["components"]:
        require(set(c.get("platforms", ["darwin"])) <= {"darwin", "win32"} and c.get("platforms"), "%s: platforms 不对" % c["id"])
    runbook = (ROOT / "references" / "runbook.md").read_text(encoding="utf-8")
    missing = [i for i in ids if "`%s`" % i not in runbook]
    require(not missing, "执行手册没有提到这些组件 id: %s" % missing)
    for comp in manifest["components"]:
        for rel in re.findall(r"installers/[^\s（）,;。；：，]+", comp["next"]):
            require((ROOT / rel).is_file(), "%s 的下一步指向不存在的 %s" % (comp["id"], rel))
        # Windows installers (installers\win\...) arrive with W3–W5; until then only the names are reserved.
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
    win_runbook = (ROOT / "references" / "runbook-windows.md").read_text(encoding="utf-8")
    win_ids = [c["id"] for c in manifest["components"] if "win32" in c.get("platforms", [])]
    missing = [i for i in win_ids if "`%s`" % i not in win_runbook]
    require(not missing, "Windows 手册没有提到这些组件 id: %s" % missing)
    win_steps = next_step.load_manifest(ROOT / "manifest.json", "win32")["steps"]
    for step in win_steps:
        require("## %s " % step["id"] in win_runbook, "Windows 手册缺步骤 %s" % step["id"])
        if step.get("installer"):
            require((ROOT / step["installer"].replace("\\", "/")).is_file(), "steps_win.%s 的安装器不存在 %s" % (step["id"], step["installer"]))
    for name in set(re.findall(r"installers\\\\win\\\\([^\s（）,;。；：，\"]+)", json.dumps(manifest, ensure_ascii=False))):
        require((ROOT / "installers" / "win" / name).is_file(), "manifest 提到的 installers\\win\\%s 不存在" % name)
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
    # bash 3.2 (/bin/sh on macOS) in a UTF-8 locale reads "$name" followed by a multibyte character as part
    # of the name ("BK）: unbound variable"); every such use must be braced.
    bad_var = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]")
    shell_files = list((ROOT / "installers" / "lib").glob("*.sh")) + list((ROOT / "installers").glob("*.command")) \
        + [p for p in (ROOT / "system").rglob("*") if p.is_file() and "vendor" not in p.parts and p.suffix in ("", ".sh")]
    for path in shell_files:
        text = path.read_text(encoding="utf-8")
        require(not bad_var.search(text), "%s: $变量 后面紧跟非 ASCII 字符要写成 ${变量}" % path.relative_to(ROOT))
    sh, bash = shell_path("sh"), shell_path("bash")
    skipped = []
    if not sh or not bash:
        # Loud, not silent: the .sh/.command files are macOS installers; on a Windows box without Git Bash we cannot
        # parse them, so say so in the PASS line instead of crashing on the WSL launcher.
        skipped.append("sh 语法检查（Windows 没有 Git Bash，PATH 里的 bash 是 WSL 启动器）")
    for path in sorted((ROOT / "installers" / "lib").glob("*.sh")):
        if sh:
            subprocess.run([sh, "-n", str(path)], check=True)
        text = path.read_text(encoding="utf-8")
        require("set -eu" in text or path.name == "common.sh", "%s 缺 set -eu" % path.name)
        require("|| true" not in text, "%s 不准用 || true 吞错误" % path.name)
        counts["sh"] += 1
    for path in sorted((ROOT / "installers").glob("*.command")):
        if bash:
            subprocess.run([bash, "-n", str(path)], check=True)
        require(sys.platform == "win32" or path.stat().st_mode & 0o100, "%s 不可执行" % path.name)
        counts["command"] += 1
    counts["ps1"] = 0
    for path in sorted((ROOT / "system-win").rglob("*.ps1")):
        raw = path.read_bytes()
        require(raw.startswith(b"\xef\xbb\xbf"), "%s 需要 UTF-8 BOM" % path.name)
        require(not re.search("[“”]", raw.decode("utf-8-sig")), "%s 不能含 “ ”（PowerShell 当字符串分隔符）" % path.name)
        counts["ps1"] += 1
    for path in sorted((ROOT / "installers" / "win").glob("*.cmd")):
        require(b"\r\n" in path.read_bytes(), "%s 需要 CRLF" % path.name)
    # No machine-specific values in the shipped templates.
    for path in list((ROOT / "system").rglob("*")) + list((ROOT / "templates").rglob("*")):
        if path.is_file() and "vendor" not in path.parts:
            text = path.read_text(encoding="utf-8")
            for bad in ("/Users/", "utun1024", "user 501"):
                require(bad not in text, "%s 含机器相关值 %s" % (path.relative_to(ROOT), bad))
    print("PASS: metadata, links, manifest coverage, syntax", counts)
    for item in skipped:
        print("SKIPPED（明说，不是通过）: %s" % item)
    print("Operational scripts were not executed; mirror_check and installers are validated separately.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, subprocess.CalledProcessError, py_compile.PyCompileError) as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        sys.exit(1)
