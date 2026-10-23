"""The documents must cover every component and every installer, and the packaging check must pass."""
import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path

import os

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")  # the fixtures describe the macOS reference machine
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check  # noqa: E402

MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
RUNBOOK = (ROOT / "references" / "runbook.md").read_text(encoding="utf-8")
CONVERSATION = (ROOT / "references" / "conversation.md").read_text(encoding="utf-8")
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")


class CoverageTests(unittest.TestCase):
    def test_runbook_names_every_macos_component_id(self):
        for comp in MANIFEST["components"]:
            if "darwin" in comp.get("platforms", ["darwin"]):
                self.assertIn("`%s`" % comp["id"], RUNBOOK, comp["id"])

    def test_runbook_steps_have_the_fixed_shape(self):
        steps = re.findall(r"^## (S\d+) ", RUNBOOK, re.M)
        self.assertEqual(steps, ["S%d" % i for i in range(1, 13)])
        for name in ("S2", "S3", "S4", "S5", "S6", "S7", "S8"):
            body = RUNBOOK.split("## %s " % name, 1)[1].split("\n## ", 1)[0]
            self.assertIn("进入", body, name)
            self.assertIn("对账", body, name)
            self.assertIn(".command", body, name)

    def test_every_launcher_is_in_runbook_and_conversation(self):
        for launcher in (ROOT / "installers").glob("安装*.command"):
            self.assertIn(launcher.name, RUNBOOK, launcher.name)
            self.assertIn(launcher.name, CONVERSATION, launcher.name)
        self.assertIn("Chrome策略.mobileconfig", CONVERSATION)
        self.assertIn("卸载.command", RUNBOOK)

    def test_scenarios_cover_weak_model_failures(self):
        table = RUNBOOK.split("## 4. 情景推演", 1)[1].split("## 附录", 1)[0]
        rows = [l for l in table.splitlines() if l.startswith("| ") and not l.startswith("| 输入情景") and not l.startswith("| ---")]
        self.assertGreaterEqual(len(rows), 21)
        self.assertTrue(any("跳过了 S11" in r for r in rows))
        self.assertTrue(any("内置浏览器" in r for r in rows))
        self.assertTrue(any("没贴 `EXIT=`" in r for r in rows))

    def test_hard_rules_are_stated_everywhere(self):
        for text, name in ((SKILL, "SKILL"), (RUNBOOK, "runbook"), (CONVERSATION, "conversation")):
            self.assertIn("出口", text, name)
            self.assertIn("Anthropic", text, name)
            self.assertIn("双击", text, name)

    def test_ippure_doc_lists_four_items_and_optional_language(self):
        text = (ROOT / "references" / "ippure-acceptance.md").read_text(encoding="utf-8")
        for item in ("出口 IP", "WebRTC", "DNS", "中文环境"):
            self.assertIn(item, text)
        self.assertIn("可选", text)
        self.assertIn("sys.language", text)


class WindowsDocTests(unittest.TestCase):
    RUNBOOK_WIN = (ROOT / "references" / "runbook-windows.md").read_text(encoding="utf-8")

    def test_windows_runbook_names_every_windows_component(self):
        for comp in MANIFEST["components"]:
            if "win32" in comp.get("platforms", []):
                self.assertIn("`%s`" % comp["id"], self.RUNBOOK_WIN, comp["id"])

    def test_windows_runbook_has_nine_steps_and_service_mode_rule(self):
        self.assertEqual(re.findall(r"^## (S\d+) ", self.RUNBOOK_WIN, re.M), ["S%d" % i for i in range(1, 10)])
        self.assertIn("服务模式", self.RUNBOOK_WIN)
        for name in ("安装防火墙规则.cmd", "安装自检守护.cmd", "安装IPv6守护.cmd", "Chrome策略.reg", "Edge策略.reg", "安装体检工具.cmd", "设置时区.cmd"):
            self.assertIn(name, self.RUNBOOK_WIN, name)
        self.assertIn("runbook-windows.md", SKILL)
        self.assertIn("py -3", (ROOT / "START.md").read_text(encoding="utf-8"))


class PackagingTests(unittest.TestCase):
    def test_check_passes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(check.main(), 0)
        self.assertIn("PASS", out.getvalue())

    def test_readme_paragraph_names_the_entry_and_the_rules(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        para = readme.split("发给 AI 的一段话", 1)[1].split("\n## ", 1)[0]
        for needle in ("claude-setup-kit", "START.md", "mirror_check.py", "next_step.py", "conversation.md", "ippure-acceptance.md", "不许切换"):
            self.assertIn(needle, para, needle)

    def test_webrtc_page_has_no_hardcoded_exit_ip(self):
        text = (ROOT / "assets" / "webrtc-test.html").read_text(encoding="utf-8")
        self.assertNotIn("192.220", text)
        self.assertIn("leaked_addresses", text)


if __name__ == "__main__":
    unittest.main()
