"""next_step.py: picks the first pending step in manifest order, honours prerequisites, and knows when to stop."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import os

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")  # the fixtures describe the macOS reference machine
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import next_step as ns  # noqa: E402

MANIFEST = ns.load_manifest(ROOT / "manifest.json")
ALL_IDS = [c["id"] for c in MANIFEST["components"] if "darwin" in c.get("platforms", ["darwin"])]


def result(overrides=None, default="PASS"):
    overrides = overrides or {}
    items = []
    for cid in ALL_IDS:
        status = overrides.get(cid, default)
        if cid == "sys.language":
            status = "INFO"
        if cid == "browser.webrtc":
            status = "MANUAL"
        items.append({"id": cid, "status": status, "evidence": "e-" + cid, "next": "n-" + cid})
    return {"items": items}


class DecideTests(unittest.TestCase):
    def test_all_passed_goes_to_ippure(self):
        out = ns.decide(MANIFEST, result())
        self.assertEqual(out["state"], "all_passed")
        self.assertEqual(out["exit"], 0)
        self.assertIn("ippure", out["user_action"])

    def test_only_leak_guard_failing_picks_s4_with_installer_and_precheck(self):
        out = ns.decide(MANIFEST, result({"pf.020": "FAIL", "loader.020": "FAIL", "daemon.020": "FAIL"}))
        self.assertEqual(out["step"], "S4")
        self.assertEqual(out["installer"], "installers/安装防泄露墙.command")
        self.assertEqual([f["id"] for f in out["failing"]], ["pf.020", "loader.020", "daemon.020"])
        self.assertEqual(out["precheck"], [{"id": "net.tun_iface", "status": "PASS"}])
        self.assertEqual(out["prerequisites"], {"S1": "passed", "S2": "passed", "S3": "passed"})
        self.assertIn("pf.020,loader.020,daemon.020", out["verify"])
        self.assertEqual(out["exit"], 3)

    def test_everything_missing_starts_at_s1(self):
        out = ns.decide(MANIFEST, result(default="FAIL"))
        self.assertEqual(out["step"], "S1")
        self.assertIn("render.py --component clash", out["ai_action"])

    def test_unmet_prerequisite_redirects_to_the_earlier_step(self):
        # S6 fails but S4 (one of its requires) also fails: do S4 first, and say why.
        out = ns.decide(MANIFEST, result({"loader.watch": "FAIL", "pf.020": "FAIL"}))
        self.assertEqual(out["step"], "S4")
        self.assertIsNone(out["via"])  # S4 itself comes earlier in order and is pending on its own

    def test_s12_waits_for_every_step_even_without_components(self):
        out = ns.decide(MANIFEST, result({"sys.timezone": "FAIL"}))
        self.assertEqual(out["step"], "S10")

    def test_unknown_needing_sudo_is_flagged_not_reinstalled(self):
        res = result({"pf.010": "UNKNOWN"})
        next(i for i in res["items"] if i["id"] == "pf.010")["evidence"] = "需要 sudo: pfctl -a x -sr（用 sudo 重跑）"
        out = ns.decide(MANIFEST, res)
        self.assertEqual(out["step"], "S2")
        self.assertIn("sudo", out["note"])

    def test_precheck_failure_is_called_out(self):
        out = ns.decide(MANIFEST, result({"pf.020": "FAIL", "net.tun_iface": "FAIL"}))
        self.assertEqual(out["step"], "S1")  # TUN belongs to S1, which must pass before S4
        out = ns.decide(MANIFEST, result({"pf.020": "FAIL"}))
        self.assertNotIn("note", out)

    def test_info_and_manual_never_block(self):
        out = ns.decide(MANIFEST, result({"chrome.policy": "PASS"}))
        self.assertEqual(out["state"], "all_passed")


class ManifestStepTests(unittest.TestCase):
    def test_steps_cover_every_component_once_and_in_runbook_order(self):
        seen = []
        for step in MANIFEST["steps"]:
            seen += step.get("components", []) + step.get("manual", []) + step.get("info", [])
        self.assertEqual(len(seen), len(set(seen)), "组件重复归属")
        self.assertEqual(set(seen) | {"os"}, set(ALL_IDS))
        self.assertEqual([s["id"] for s in MANIFEST["steps"]], ["S%d" % i for i in range(1, 13)])
        for step in MANIFEST["steps"]:
            for req in step.get("requires", []):
                self.assertLess(int(req[1:]), int(step["id"][1:]), "%s 的前置 %s 必须在它前面" % (step["id"], req))
            self.assertTrue(step.get("say"), step["id"])
            if step.get("installer"):
                self.assertTrue((ROOT / step["installer"]).is_file(), step["installer"])

    def test_inconsistent_manifest_is_rejected(self):
        data = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        data["steps"][0]["components"].append("nope")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                ns.load_manifest(path)


class WindowsStepTests(unittest.TestCase):
    MANIFEST_WIN = ns.load_manifest(ROOT / "manifest.json", "win32")
    WIN_IDS = [c["id"] for c in MANIFEST_WIN["components"] if "win32" in c.get("platforms", [])]

    def result(self, overrides=None, default="PASS"):
        items = []
        for cid in self.WIN_IDS:
            status = (overrides or {}).get(cid, default)
            if cid in ("sys.language", "dns.system"):
                status = "INFO"
            if cid == "browser.webrtc":
                status = "MANUAL"
            items.append({"id": cid, "status": status, "evidence": "e", "next": "n"})
        return {"items": items}

    def test_windows_steps_cover_every_windows_component(self):
        seen = []
        for step in self.MANIFEST_WIN["steps"]:
            seen += step.get("components", []) + step.get("manual", []) + step.get("info", [])
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen) | {"os"}, set(self.WIN_IDS))
        for step in self.MANIFEST_WIN["steps"]:
            if step.get("installer"):
                self.assertTrue((ROOT / step["installer"].replace("\\", "/")).is_file(), step["installer"])

    def test_windows_firewall_step_needs_tun_and_clash(self):
        out = ns.decide(self.MANIFEST_WIN, self.result({"wf.011": "FAIL", "wf.020": "FAIL", "wf.enabled": "FAIL"}))
        self.assertEqual(out["step"], "S2")
        self.assertEqual(out["installer"], "installers\\win\\安装防火墙规则.cmd")
        self.assertEqual(out["precheck"], [{"id": "net.tun_iface", "status": "PASS"}])
        out = ns.decide(self.MANIFEST_WIN, self.result({"wf.011": "FAIL", "net.tun_iface": "FAIL"}))
        self.assertEqual(out["step"], "S1")

    def test_windows_all_passed_and_cli_platform_flag(self):
        self.assertEqual(ns.decide(self.MANIFEST_WIN, self.result())["state"], "all_passed")
        with tempfile.TemporaryDirectory() as tmp:
            res = Path(tmp) / "r.json"
            res.write_text(json.dumps(self.result({"reg.edge": "FAIL"})), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ns.main(["--platform", "win32", "--input", str(res)])
            self.assertEqual(code, 3)
            self.assertIn("现在做：S5", out.getvalue())
            self.assertIn("Chrome策略.reg", out.getvalue())


class CliTests(unittest.TestCase):
    def test_platform_key_falls_back_to_macos_tables(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_SETUP_KIT_PLATFORM", None)
            with unittest.mock.patch.object(sys, "platform", "linux"):
                self.assertEqual(ns.platform_key(), "darwin")
            with unittest.mock.patch.object(sys, "platform", "win32"):
                self.assertEqual(ns.platform_key(), "win32")
            os.environ["CLAUDE_SETUP_KIT_PLATFORM"] = "win32"
            with unittest.mock.patch.object(sys, "platform", "darwin"):
                self.assertEqual(ns.platform_key(), "win32")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ns.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_input_file_and_text_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps(result({"chrome.policy": "FAIL"})), encoding="utf-8")
            code, out, _ = self.run_cli("--input", str(path))
            self.assertEqual(code, 3)
            self.assertIn("现在做：S9", out)
            self.assertIn("Chrome策略.mobileconfig", out)
            self.assertIn("做完后运行: python3 scripts/mirror_check.py --only chrome.policy", out)
            code, out, _ = self.run_cli("--input", str(path), "--json")
            self.assertEqual(json.loads(out)["step"], "S9")
            path.write_text(json.dumps(result()), encoding="utf-8")
            code, out, _ = self.run_cli("--input", str(path))
            self.assertEqual(code, 0)
            self.assertIn("ippure", out)

    def test_missing_local_params_is_hinted_and_root_installers_mention_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_bytes((ROOT / "manifest.json").read_bytes())
            res = Path(tmp) / "r.json"
            res.write_text(json.dumps(result({"pf.011": "FAIL"})), encoding="utf-8")
            code, out, _ = self.run_cli("--manifest", str(manifest), "--input", str(res))
            self.assertIn("没有 mirror.params.json", out)
            self.assertIn("开机密码", out)
            (Path(tmp) / "mirror.params.json").write_text("{}", encoding="utf-8")
            code, out, _ = self.run_cli("--manifest", str(manifest), "--input", str(res))
            self.assertNotIn("没有 mirror.params.json", out)
            res.write_text(json.dumps(result({"tool.claude_wall": "FAIL"})), encoding="utf-8")
            code, out, _ = self.run_cli("--manifest", str(manifest), "--input", str(res))
            self.assertNotIn("开机密码", out)

    def test_bad_manifest_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text("{}", encoding="utf-8")
            code, _, err = self.run_cli("--manifest", str(path), "--input", str(path))
            self.assertEqual(code, 2)
            self.assertIn("[ERROR]", err)


if __name__ == "__main__":
    unittest.main()
