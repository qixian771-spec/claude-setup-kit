"""Tests for W20 foolproof anti-lazy upgrades: claude.privacy, auto_init.py, finish_gate.py, and macOS one-click scripts."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import auto_init as ai  # noqa: E402
import finish_gate as fg  # noqa: E402
import mirror_check as mc  # noqa: E402
import next_step as ns  # noqa: E402
from test_mirror_check import FakeHost, HOME, MANIFEST, Stat  # noqa: E402


class ClaudePrivacyCheckTests(unittest.TestCase):
    def test_baseline_passes_all_14_switches(self):
        host = FakeHost()
        st, ev = mc.check_claude_privacy(host, {}, {})
        self.assertEqual(st, mc.PASS)
        self.assertIn("14 项", ev)

    def test_missing_file_or_keys_or_wrong_value_fails(self):
        host = FakeHost()
        del host.stats[HOME + "/.claude/settings.json"]
        st, ev = mc.check_claude_privacy(host, {}, {})
        self.assertEqual(st, mc.FAIL)
        self.assertIn("不存在", ev)

        host = FakeHost()
        host.files[HOME + "/.claude/settings.json"] = json.dumps({"env": {"DISABLE_TELEMETRY": "0"}})
        st, ev = mc.check_claude_privacy(host, {}, {})
        self.assertEqual(st, mc.FAIL)
        self.assertIn("缺 13 项", ev)
        self.assertIn("DISABLE_TELEMETRY='0'", ev)

        host = FakeHost()
        host.links.add(HOME + "/.claude/settings.json")
        st, ev = mc.check_claude_privacy(host, {}, {})
        self.assertEqual(st, mc.FAIL)
        self.assertIn("符号链接", ev)


class AutoInitTests(unittest.TestCase):
    def test_supplement_creates_and_preserves_existing_settings_with_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            # First run on clean home creates ~/.claude/settings.json without backup
            res1 = ai.supplement_claude_privacy(home=home)
            self.assertTrue(res1["changed"])
            self.assertIsNone(res1["backup"])
            self.assertEqual(len(res1["added_keys"]), 14)

            # Second run is idempotent
            res2 = ai.supplement_claude_privacy(home=home)
            self.assertFalse(res2["changed"])
            self.assertEqual(res2["missing_keys"], [])

            # Partial existing file gets backed up and supplemented without overwriting user's keys
            settings = home / ".claude" / "settings.json"
            settings.write_text(json.dumps({
                "model": "opus",
                "env": {"CUSTOM_VAR": "keep_me", "DISABLE_TELEMETRY": "1"},
            }), encoding="utf-8")
            res3 = ai.supplement_claude_privacy(home=home)
            self.assertTrue(res3["changed"])
            self.assertTrue(Path(res3["backup"]).is_file())
            merged = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(merged["model"], "opus")
            self.assertEqual(merged["env"]["CUSTOM_VAR"], "keep_me")
            self.assertTrue(merged["skipWebFetchPreflight"])
            self.assertEqual(merged["env"]["OTEL_TRACES_EXPORTER"], "none")

    def test_supplement_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".claude").mkdir()
            real = home / "outside.json"
            real.write_text("{}", encoding="utf-8")
            (home / ".claude" / "settings.json").symlink_to(real)
            with self.assertRaises(RuntimeError):
                ai.supplement_claude_privacy(home=home)

    def test_detect_clash_exit_from_exit_group_and_fallback_selector(self):
        host = FakeHost()
        params = mc.load_manifest(MANIFEST, "darwin")["params"]
        info = ai.detect_clash_exit(host, params)
        self.assertTrue(info["clash_reachable"])
        self.assertTrue(info["exit_group_present"])
        self.assertEqual(info["detected_node"], "丽萨美国")

        # Pre-S1 user whose Clash uses a custom group name instead of 出口选择
        host2 = FakeHost()
        del host2.apis["/proxies/%E5%87%BA%E5%8F%A3%E9%80%89%E6%8B%A9"]
        host2.apis["/rules"] = {"rules": [{"type": "Match", "payload": "", "proxy": "Proxy"}]}
        host2.apis["/proxies"] = {
            "proxies": {
                "Proxy": {"type": "Selector", "now": "东京节点01"},
                "东京节点01": {"type": "Trojan"},
            }
        }
        info2 = ai.detect_clash_exit(host2, params)
        self.assertTrue(info2["clash_reachable"])
        self.assertFalse(info2["exit_group_present"])
        self.assertEqual(info2["detected_node"], "东京节点01")
        self.assertIn("尚未导入", info2["hint"])

    def test_auto_init_writes_params_file_and_protects_against_node_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            m_path = Path(tmp) / "manifest.json"
            shutil.copy(MANIFEST, m_path)
            home = Path(tmp) / "home"
            home.mkdir()
            # Pre-seed a node that IS in group_members vs one that is NOT in group_members
            fake_host = FakeHost()
            with unittest.mock.patch.object(mc, "Host", return_value=fake_host), \
                 unittest.mock.patch.object(ai, "detect_network_service_mac", return_value="Wi-Fi"), \
                 unittest.mock.patch.object(ai, "detect_ipv6_guard_label_mac", return_value=None):
                res = ai.run_auto_init(manifest_path=m_path, home=home)
                self.assertTrue((Path(tmp) / "mirror.params.json").is_file())
                self.assertEqual(res["params_data"]["exit_node"], "丽萨美国")
                self.assertEqual(res["params_data"]["network_services"], ["Wi-Fi"])

                # Simulate accidental node switch inside 出口选择 to 韩国43 (both are in group_members):
                # auto_init must NOT overwrite exit_node="丽萨美国", so clash.exit still catches the switch!
                fake_host.apis["/proxies/%E5%87%BA%E5%8F%A3%E9%80%89%E6%8B%A9"]["now"] = "韩国43"
                res2 = ai.run_auto_init(manifest_path=m_path, home=home)
                self.assertEqual(res2["params_data"]["exit_node"], "丽萨美国")


class FinishGateTests(unittest.TestCase):
    def _make_result(self, platform="darwin", overrides=None, skip_steps=None):
        m = ns.load_manifest(MANIFEST, platform)
        ids = [c["id"] for c in m["components"] if platform in c.get("platforms", ["darwin"])]
        overrides = overrides or {}
        items = []
        for cid in ids:
            status = overrides.get(cid, mc.PASS)
            if cid in ("sys.language", "desktop.updater") and cid not in overrides:
                status = mc.INFO
            if cid == "browser.webrtc" and cid not in overrides:
                status = mc.MANUAL
            items.append({"id": cid, "status": status, "evidence": "ok-" + cid, "next": "fix-" + cid})
        return {
            "generated_utc": "2026-11-13T10:00:00Z",
            "platform": platform,
            "params": {"exit_node": "测试美国", "skip_steps": skip_steps or []},
            "items": items,
        }

    def test_gate_blocks_when_params_missing_or_steps_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            m_path = Path(tmp) / "manifest.json"
            shutil.copy(MANIFEST, m_path)
            r_path = Path(tmp) / "res.json"
            r_path.write_text(json.dumps(self._make_result()), encoding="utf-8")

            # Missing mirror.params.json -> BLOCKED
            code, data = fg.evaluate_gate(str(m_path), input_path=str(r_path), platform="darwin")
            self.assertEqual(code, 1)
            self.assertEqual(data["gate"], "BLOCKED")
            self.assertEqual(data["reason"], "missing_params_file")

            # mirror.params.json exists, but claude.privacy + chrome.policy fail -> BLOCKED listing BOTH S9 and S10
            (Path(tmp) / "mirror.params.json").write_text('{"exit_node": "测试美国"}', encoding="utf-8")
            r_path.write_text(
                json.dumps(self._make_result(overrides={"chrome.policy": mc.FAIL, "claude.privacy": mc.FAIL})),
                encoding="utf-8",
            )
            code, data = fg.evaluate_gate(str(m_path), input_path=str(r_path), platform="darwin")
            self.assertEqual(code, 1)
            self.assertEqual(data["gate"], "BLOCKED")
            pending_ids = [s["id"] for s in data["pending_steps"]]
            self.assertIn("S9", pending_ids)
            self.assertIn("S10", pending_ids)
            txt = fg.render_gate(code, data)
            self.assertIn("FINISH_GATE=BLOCKED", txt)

    def test_gate_passes_with_token_and_honours_skip_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            m_path = Path(tmp) / "manifest.json"
            shutil.copy(MANIFEST, m_path)
            (Path(tmp) / "mirror.params.json").write_text('{"exit_node": "测试美国"}', encoding="utf-8")
            r_path = Path(tmp) / "res.json"
            r_path.write_text(
                json.dumps(self._make_result(overrides={"chrome.policy": mc.FAIL}, skip_steps=["S9"])),
                encoding="utf-8",
            )
            code, data = fg.evaluate_gate(str(m_path), input_path=str(r_path), platform="darwin")
            self.assertEqual(code, 0)
            self.assertEqual(data["gate"], "PASSED")
            self.assertEqual(len(data["gate_code"]), 12)
            self.assertIn("S9", data["skipped"])
            txt = fg.render_gate(code, data)
            self.assertIn("FINISH_GATE=PASSED", txt)
            self.assertIn(data["gate_code"], txt)


class MacOneClickScriptsSyntaxTests(unittest.TestCase):
    def test_shell_syntax_valid(self):
        for rel in (
            "installers/一键安装全部.command",
            "installers/一键撤回全部.command",
            "installers/lib/run-all-mac.sh",
            "installers/lib/rollback-all-mac.sh",
        ):
            p = ROOT / rel
            self.assertTrue(p.is_file(), rel)
            proc = subprocess.run(["sh", "-n", str(p)], capture_output=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, "%s syntax error: %s" % (rel, proc.stderr))


if __name__ == "__main__":
    unittest.main()
