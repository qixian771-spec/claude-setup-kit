"""Static checks on files the user installs by double-click. Nothing is installed here."""
import json
import plistlib
import re
import subprocess
import sys
import unittest
from pathlib import Path

import os

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")  # the fixtures describe the macOS reference machine
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402


class ChromeProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = plistlib.loads((ROOT / "installers" / "Chrome策略.mobileconfig").read_bytes())

    def test_identifier_matches_manifest_param(self):
        self.assertEqual(self.profile["PayloadIdentifier"], MANIFEST["params"]["chrome_profile_identifier"])
        self.assertEqual(self.profile["PayloadScope"], "System")
        self.assertEqual(self.profile["PayloadType"], "Configuration")
        self.assertFalse(self.profile["PayloadRemovalDisallowed"])

    def test_single_chrome_payload_carries_exactly_the_manifest_policy(self):
        payloads = self.profile["PayloadContent"]
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["PayloadType"], "com.google.Chrome")
        policy = {k: v for k, v in payload.items() if not k.startswith("Payload")}
        self.assertEqual(policy, MANIFEST["params"]["chrome_policy"])

    def test_uuids_are_stable(self):
        self.assertNotEqual(self.profile["PayloadUUID"], self.profile["PayloadContent"][0]["PayloadUUID"])
        for value in (self.profile["PayloadUUID"], self.profile["PayloadContent"][0]["PayloadUUID"]):
            self.assertRegex(value, r"^[0-9A-F]{8}-[0-9A-F]{4}-5[0-9A-F]{3}-[0-9A-F]{4}-[0-9A-F]{12}$")


class LauncherTests(unittest.TestCase):
    LIB = ROOT / "installers" / "lib"

    def test_every_shell_script_parses(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import check as check_tool
        sh, bash = check_tool.shell_path("sh"), check_tool.shell_path("bash")
        if not sh or not bash:
            self.skipTest("Windows 没有 Git Bash（PATH 里的 bash 是 WSL 启动器），跳过 sh 语法检查")
        for path in sorted(self.LIB.glob("*.sh")):
            subprocess.run([sh, "-n", str(path)], check=True)
        for path in sorted((ROOT / "installers").glob("*.command")):
            subprocess.run([bash, "-n", str(path)], check=True)
            if sys.platform != "win32":
                self.assertTrue(path.stat().st_mode & 0o100, path.name)

    def test_every_installer_named_in_the_manifest_exists(self):
        for comp in MANIFEST["components"]:
            for rel in re.findall(r"installers/[^\s（）,;。；：，]+", comp["next"]):
                self.assertTrue((ROOT / rel).is_file(), "%s → %s" % (comp["id"], rel))

    def test_launchers_use_known_components_and_existing_lib_scripts(self):
        launchers = [p for p in (ROOT / "installers").glob("安装*.command")]
        self.assertEqual(len(launchers), 7)
        seen = set()
        for path in launchers:
            text = path.read_text(encoding="utf-8")
            comp = re.search(r"--component (\S+)", text).group(1)
            self.assertIn(comp, render.COMPONENTS, path.name)
            seen.add(comp)
            script = re.search(r'installers/lib/(install-[\w-]+\.sh)', text).group(1)
            self.assertTrue((self.LIB / script).is_file(), script)
            self.assertTrue((self.LIB / script.replace("install-", "uninstall-")).is_file(), script)
            self.assertIn("tee -a", text)  # the log the AI reads afterwards
            self.assertEqual("sudo sh" in text, comp != "claude-wall", path.name)
        self.assertEqual(seen, {c for c in render.COMPONENTS if c != "clash" and not c.startswith("win-")})

    def test_windows_launchers_are_crlf_and_name_existing_scripts(self):
        win = ROOT / "installers" / "win"
        shipped = {p.name for p in (ROOT / "system-win").rglob("*.ps1")}
        for path in sorted(win.glob("*.cmd")):
            raw = path.read_bytes()
            self.assertIn(b"\r\n", raw, path.name)
            self.assertNotRegex(raw.decode("utf-8"), r"(?<!\r)\n", path.name)
            text = raw.decode("utf-8")
            self.assertIn("chcp 65001", text)
            # -File + self-elevating script: no nested -Command quoting (that broke on real Windows).
            self.assertIn("-ExecutionPolicy Bypass -File ", text)
            self.assertNotIn("-Command", text)
            self.assertNotIn("-Verb RunAs", text)
            self.assertIn('-Log "%LOG%"', text)
            if not path.name.startswith(("一键", "卸载")):
                self.assertIn("render.py --component win-", text)
            for script in re.findall(r"([\w-]+\.ps1)", text):
                self.assertIn(script, shipped, script)
        common = (ROOT / "system-win" / "firewall" / "common.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("-Verb RunAs", common)
        self.assertIn("function Invoke-Logged", common)
        for ps1 in (ROOT / "system-win").rglob("*.ps1"):
            body = ps1.read_text(encoding="utf-8-sig")
            if ps1.name.startswith(("install-", "uninstall-", "set-")):
                self.assertIn("Invoke-Logged $Log {", body, ps1.name)
                self.assertEqual("Enter-Elevated" in body, ps1.name != "install-tools.ps1", ps1.name)
        for ps1 in (ROOT / "system-win").rglob("*.ps1"):
            raw = ps1.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "%s 需要 UTF-8 BOM（Windows PowerShell 5.1）" % ps1.name)
            # PowerShell treats “ ” as string delimiters: Chinese quotes inside strings must be 「」.
            self.assertNotRegex(raw.decode("utf-8-sig"), "[“”]", ps1.name)
        manifest_names = set(re.findall(r"installers\\\\win\\\\([^\s（）,;。；：，\"]+)", json.dumps(MANIFEST, ensure_ascii=False)))
        self.assertIn("安装防火墙规则.cmd", manifest_names)
        for name in manifest_names:
            self.assertTrue((win / name).is_file(), "manifest 提到的 installers\\win\\%s 不存在" % name)
        for reg in win.glob("*.reg"):
            raw = reg.read_bytes()
            self.assertTrue(raw.startswith(b"\xff\xfe"), "%s 必须是 UTF-16LE（regedit 要求）" % reg.name)
            text = raw[2:].decode("utf-16-le")
            self.assertTrue(text.startswith("Windows Registry Editor Version 5.00"), reg.name)
            self.assertIn("WebRtcIPHandling", text)

    def test_install_scripts_refuse_before_writing(self):
        # refuse_existing must come before the first install/cp/launchctl in every root installer.
        for path in sorted(self.LIB.glob("install-*.sh")):
            text = path.read_text(encoding="utf-8")
            refuse = text.index("refuse_existing")
            first_write = min(i for i in (text.find(tok) for tok in ("install -", "launchctl bootstrap", "cp ", "networksetup -set")) if i >= 0)
            self.assertLess(refuse, first_write, path.name)
            self.assertIn("set -eu", text)
            self.assertNotIn("|| true", text, path.name)


if __name__ == "__main__":
    unittest.main()
