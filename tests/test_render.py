"""render.py: templates render completely, only into the chosen directory, with this machine's values."""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402


class FakeUser:
    pw_name, pw_dir, pw_uid = "tester", "/Users/tester", 502


class RenderFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mirror-render-")
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_bytes((ROOT / "manifest.json").read_bytes())
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(render, "console_user", return_value=FakeUser()))
        self.stack.enter_context(patch.object(render, "wifi_iface", return_value="en9"))

    def values(self, *overrides):
        return render.load_params(self.manifest, list(overrides))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = render.main(["--manifest", str(self.manifest), *argv])
        return code, out.getvalue(), err.getvalue()


class ParamTests(RenderFixture):
    def test_values_come_from_manifest_user_and_network(self):
        v = self.values()
        self.assertEqual((v["USER"], v["HOME"], v["UID"], v["WIFI_IFACE"]), ("tester", "/Users/tester", "502", "en9"))
        self.assertEqual(v["TUN"], "utun1024")
        self.assertEqual(v["IPV6_LABEL"], "local.ipv6-guard")
        self.assertEqual(v["EXIT_GROUP_URLENC"], "%E5%87%BA%E5%8F%A3%E9%80%89%E6%8B%A9")

    def test_local_overrides_and_cli_params(self):
        (self.root / "mirror.params.json").write_text(json.dumps({"ipv6_guard_label": "com.example.ipv6"}), encoding="utf-8")
        self.assertEqual(self.values()["IPV6_LABEL"], "com.example.ipv6")
        self.assertEqual(self.values("ipv6_guard_label=x.y")["IPV6_LABEL"], "x.y")
        with self.assertRaises(render.RenderError):
            self.values("bogus=1")
        (self.root / "mirror.params.json").write_text(json.dumps({"nope": 1}), encoding="utf-8")
        with self.assertRaises(render.RenderError):
            self.values()

    def test_root_console_user_refused(self):
        class Root:
            pw_name, pw_dir, pw_uid = "root", "/var/root", 0
        with patch.object(render, "console_user", side_effect=render.RenderError("root")):
            with self.assertRaises(render.RenderError):
                self.values()


class ComponentTests(RenderFixture):
    def test_every_system_component_renders_without_placeholders(self):
        for name in render.COMPONENTS:
            if name == "clash":
                continue
            out = self.root / name
            written = render.render_component(name, self.values(), out)
            self.assertTrue(written, name)
            for rel in written:
                path = out / rel
                if "vendor" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("{{", text, rel)
                self.assertNotIn("niuniu", text, rel)
            self.assertIn("USER=tester", (out / "PARAMS.txt").read_text(encoding="utf-8"))

    def test_rendered_values_land_in_the_right_places(self):
        out = self.root / "all"
        for name in ("leak-guard", "watch", "updater", "ipv6-guard"):
            render.render_component(name, self.values(), out / name)
        leak = (out / "leak-guard/system/pf.anchors/local.leak-guard").read_text(encoding="utf-8")
        self.assertIn("user 502 label", leak)
        self.assertIn("on utun1024 no state", leak)
        lib = (out / "watch/system/libexec/net-guard-watch-lib.sh").read_text(encoding="utf-8")
        self.assertIn("EXPECTED_EXIT='丽萨美国'", lib)
        watch = (out / "watch/system/libexec/net-guard-watch").read_text(encoding="utf-8")
        self.assertIn("/proxies/%E5%87%BA%E5%8F%A3%E9%80%89%E6%8B%A9", watch)
        self.assertIn("'/Users/tester/Library/Application Support/ClaudeDirectWallUpdater/stdout.log'", watch)
        runner = (out / "updater/system/updater/runner.py").read_text(encoding="utf-8")
        self.assertIn("ACCOUNT = 'tester'", runner)
        self.assertIn("pw_dir != '/Users/tester'", runner)
        sudoers = (out / "updater/system/sudoers/claude-mac-env-mirror").read_text(encoding="utf-8")
        self.assertTrue(sudoers.rstrip().splitlines()[-1].startswith("tester ALL=(root) NOPASSWD:"))
        self.assertNotIn("NOPASSWD: ALL", sudoers)
        plist = (out / "ipv6-guard/system/LaunchDaemons/ipv6-guard.plist").read_text(encoding="utf-8")
        self.assertIn("<string>local.ipv6-guard</string>", plist)
        guard = (out / "ipv6-guard/system/userbin/ipv6-guard.sh").read_text(encoding="utf-8")
        self.assertIn('IFACE="en9"', guard)
        self.assertIn('SERVICE="Wi-Fi"', guard)

    def test_modes_preserved_and_vendor_copied(self):
        out = self.root / "upd"
        render.render_component("updater", self.values(), out)
        self.assertTrue((out / "system/updater/vendor/ruamel/yaml/__init__.py").is_file())
        self.assertFalse((out / "system/updater/sha256.json").exists())  # generated at install time
        render.render_component("direct-wall", self.values(), self.root / "dw")
        mode = (self.root / "dw/system/libexec/claude-direct-wall").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    def test_output_dir_must_not_exist(self):
        out = self.root / "exists"
        out.mkdir()
        with self.assertRaises(render.RenderError):
            render.render_component("watch", self.values(), out)

    def test_clash_needs_node_values_and_rejects_bad_node_file(self):
        with self.assertRaises(render.RenderError):
            render.render_component("clash", self.values(), self.root / "c1")
        nodes = self.root / "nodes.json"
        nodes.write_text(json.dumps({"NODE1_NAME": "a", "server": "x"}), encoding="utf-8")
        with self.assertRaises(render.RenderError):
            render.load_nodes(nodes)
        keys = {k for k in render.PLACEHOLDER.findall((ROOT / "templates/clash-profile.template.yaml").read_text(encoding="utf-8")) if k.startswith("NODE")}
        nodes.write_text(json.dumps({k: "v-" + k.lower() for k in keys}), encoding="utf-8")
        values = dict(self.values(), **render.load_nodes(nodes))
        written = render.render_component("clash", values, self.root / "c2")
        text = (self.root / "c2/templates/clash-profile.template.yaml").read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertIn("v-node1_server", text)
        self.assertIn("出口选择", text)
        params = (self.root / "c2/PARAMS.txt").read_text(encoding="utf-8")
        self.assertNotIn("v-node", params)  # node secrets never land in the params summary

    def test_cli_prints_out_dir_and_fails_cleanly(self):
        code, out, err = self.run_cli("--component", "watch", "--out", str(self.root / "w"))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], str(self.root / "w"))
        code, out, err = self.run_cli("--component", "watch", "--out", str(self.root / "w"))
        self.assertEqual(code, 2)
        self.assertIn("不覆盖", err)
        code, out, err = self.run_cli("--component", "watch", "--print-params")
        self.assertEqual(code, 0)
        self.assertIn("USER=tester", out)


if __name__ == "__main__":
    unittest.main()
