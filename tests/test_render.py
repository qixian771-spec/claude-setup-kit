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

import os

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")  # the fixtures describe the macOS reference machine
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

    def test_local_params_with_utf8_bom_are_accepted(self):
        (self.root / "mirror.params.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"ipv6_guard_label": "bom.label"}).encode("utf-8"))
        self.assertEqual(self.values()["IPV6_LABEL"], "bom.label")

    def test_root_console_user_refused(self):
        class Root:
            pw_name, pw_dir, pw_uid = "root", "/var/root", 0
        with patch.object(render, "console_user", side_effect=render.RenderError("root")):
            with self.assertRaises(render.RenderError):
                self.values()


class WindowsParamTests(RenderFixture):
    def test_windows_user_and_adapter(self):
        with patch.object(render, "platform_key", return_value="win32"), \
                patch.dict(os.environ, {"USERNAME": "qixia", "USERPROFILE": "C:\\Users\\qixia"}), \
                patch.object(render, "powershell", side_effect=lambda s: "S-1-5-21-1-2-3-1001" if "WindowsIdentity" in s else "以太网\nWLAN\n"):
            self.stack.close()  # drop the macOS patches so the Windows branches run
            self.stack = contextlib.ExitStack()
            self.addCleanup(self.stack.close)
            v = render.load_params(self.manifest, ["network_services=以太网"])
            self.assertEqual((v["USER"], v["HOME"], v["UID"], v["USER_SID"], v["WIFI_IFACE"]), ("qixia", "C:\\Users\\qixia", "S-1-5-21-1-2-3-1001", "S-1-5-21-1-2-3-1001", "以太网"))
            self.assertEqual(v["TUN"], "Meta")  # params_win merged
            with self.assertRaises(render.RenderError):
                render.load_params(self.manifest, ["network_services=Nope"])

    def test_windows_rejects_system_sid(self):
        self.stack.close()  # the fixture patches console_user itself; test the real one
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        with patch.object(render, "platform_key", return_value="win32"), \
                patch.dict(os.environ, {"USERNAME": "SYSTEM", "USERPROFILE": "C:\\Windows"}), \
                patch.object(render, "powershell", return_value="S-1-5-18"):
            with self.assertRaises(render.RenderError):
                render.console_user()


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
        rule = sudoers.rstrip().splitlines()[-1]
        # A sudoers "*" also matches "/": no wildcard may reach outside the pinned paths, and no awk program as root.
        self.assertNotIn("/etc/pf.anchors/*", rule)
        self.assertNotIn("awk", rule)
        self.assertNotIn("mkdir -m 700 *", rule)
        self.assertIn("/usr/bin/profiles -P", rule)
        plist = (out / "ipv6-guard/system/LaunchDaemons/ipv6-guard.plist").read_text(encoding="utf-8")
        self.assertIn("<string>local.ipv6-guard</string>", plist)
        guard = (out / "ipv6-guard/system/userbin/ipv6-guard.sh").read_text(encoding="utf-8")
        self.assertIn('IFACE="en9"', guard)
        self.assertIn('SERVICE="Wi-Fi"', guard)

    def test_windows_firewall_component_renders_scripts_and_params(self):
        out = self.root / "wf"
        written = render.render_component("win-firewall", self.values(), out)
        self.assertEqual(sorted(Path(w).name for w in written), ["common.ps1", "install-firewall.ps1", "uninstall-firewall.ps1"])
        params = (out / "PARAMS.txt").read_text(encoding="utf-8")
        self.assertIn("USER_SID=", params)
        text = (out / "system-win/firewall/install-firewall.ps1").read_text(encoding="utf-8")
        for needle in ("Refuse-Existing", "clash_verge_service", "Set-NetFirewallProfile", "-LocalUser", "-InterfaceAlias", "Assert-Rule"):
            self.assertIn(needle, text)
        self.assertLess(text.index("Refuse-Existing"), text.index("New-NetFirewallRule"))
        self.assertLess(text.index("clash_verge_service"), text.index("New-NetFirewallRule"))

    def test_windows_tasks_component_renders_placeholders(self):
        out = self.root / "wt"
        written = render.render_component("win-tasks", self.values(), out)
        names = sorted(Path(w).name for w in written)
        self.assertEqual(names, ["common.ps1", "install-tasks.ps1", "ipv6-guard.ps1", "uninstall-tasks.ps1", "watch.ps1"])
        watch = (out / "system-win/tasks/watch.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$Tun = 'utun1024'", watch)
        self.assertIn("$ExpectedExit = '丽萨美国'", watch)
        self.assertIn("$ExitGroup = '出口选择'", watch)
        self.assertNotIn("{{", watch)
        guard = (out / "system-win/tasks/ipv6-guard.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$Adapter = 'en9'", guard)  # the fixture's interface for the Wi-Fi service
        install = (out / "system-win/tasks/install-tasks.ps1").read_text(encoding="utf-8-sig")
        self.assertLess(install.index("拒绝覆盖"), install.index("Register-ScheduledTask"))
        self.assertIn("NT AUTHORITY\\SYSTEM", install)
        self.assertTrue((out / "system-win/firewall/common.ps1").is_file())  # dot-sourced by install-tasks.ps1

    def test_windows_tools_component_renders(self):
        out = self.root / "wtools"
        written = render.render_component("win-tools", self.values(), out)
        self.assertEqual(sorted(Path(w).name for w in written), ["claude-wall.ps1", "common.ps1", "install-tools.ps1", "set-timezone.ps1"])
        wall = (out / "system-win/tools/claude-wall.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$Tun = 'utun1024'", wall)
        self.assertNotIn("{{", wall)
        self.assertIn("TIMEZONE_WIN=n/a", (out / "PARAMS.txt").read_text(encoding="utf-8-sig"))

    def test_modes_preserved_and_vendor_copied(self):
        out = self.root / "upd"
        render.render_component("updater", self.values(), out)
        self.assertTrue((out / "system/updater/vendor/ruamel/yaml/__init__.py").is_file())
        self.assertFalse((out / "system/updater/sha256.json").exists())  # generated at install time
        render.render_component("direct-wall", self.values(), self.root / "dw")
        mode = (self.root / "dw/system/libexec/claude-direct-wall").stat().st_mode
        if sys.platform != "win32":  # NTFS has no execute bit
            self.assertTrue(mode & stat.S_IXUSR)

    def test_output_dir_must_not_exist(self):
        out = self.root / "exists"
        out.mkdir()
        with self.assertRaises(render.RenderError):
            render.render_component("watch", self.values(), out)

    def test_two_nodes_render_without_the_optional_socks5_node(self):
        # NODE3 (socks5) is optional: without NODE3_* the proxy block and both group members disappear and nothing
        # is left unrendered; with it, the socks5 proxy is present. START.md promises exactly this.
        keys = {k for k in render.PLACEHOLDER.findall((ROOT / "templates/clash-profile.template.yaml").read_text(encoding="utf-8")) if k.startswith("NODE")}
        two = {k: "v-" + k.lower() for k in keys if not k.startswith("NODE3_")}
        text = render.render_text((ROOT / "templates/clash-profile.template.yaml").read_text(encoding="utf-8"), dict(self.values(), **two), "t")
        self.assertNotIn("{{", text)
        self.assertNotIn("v-node3", text)
        self.assertNotIn("type: socks5", text)
        self.assertNotIn("ENDIF", text.split("\nmixed-port", 1)[1])  # markers never survive into the YAML body
        self.assertEqual(text.count("- 'v-node2_name'"), 2)
        three = {k: "v-" + k.lower() for k in keys}
        text3 = render.render_text((ROOT / "templates/clash-profile.template.yaml").read_text(encoding="utf-8"), dict(self.values(), **three), "t")
        self.assertIn("type: socks5", text3)
        self.assertEqual(text3.count("- 'v-node3_name'"), 2)
        self.assertNotIn("{{IF", text3)

    def test_failed_render_leaves_no_output_directory(self):
        out = self.root / "half"
        with self.assertRaises(render.RenderError):
            render.render_component("clash", self.values(), out)  # no node values
        self.assertFalse(out.exists())

    def test_conditional_markers_must_balance(self):
        with self.assertRaises(render.RenderError):
            render.render_text("# {{IF X}}\na\n", {}, "t")
        with self.assertRaises(render.RenderError):
            render.render_text("a\n# {{ENDIF}}\n", {}, "t")
        self.assertEqual(render.render_text("a\nb  # {{IF X}}\nc\n", {}, "t"), "a\nc\n")
        self.assertEqual(render.render_text("a\nb  # {{IF X}}\nc\n", {"X": "1"}, "t"), "a\nb\nc\n")

    def test_clash_needs_node_values_and_rejects_bad_node_file(self):
        with self.assertRaises(render.RenderError):
            render.render_component("clash", self.values(), self.root / "c1")
        nodes = self.root / "nodes.json"
        nodes.write_text(json.dumps({"NODE1_NAME": "a", "server": "x"}), encoding="utf-8")
        with self.assertRaises(render.RenderError):
            render.load_nodes(nodes)
        with self.assertRaises(render.RenderError):
            render.load_nodes(self.root / "missing.json")
        nodes.write_text("{broken", encoding="utf-8")
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
        self.assertIn("Google出口", text)
        self.assertIn("DOMAIN-SUFFIX,google.com,Google出口", text)
        self.assertNotIn("\n- IP-ASN,", text)  # needs ASN.mmdb download before any proxy works → deadlock on a fresh machine
        self.assertIn("support-x25519mlkem768: true", text)
        self.assertLess(text.index("DOMAIN,storage.googleapis.com,出口选择"), text.index("DOMAIN-SUFFIX,googleapis.com,Google出口"))
        self.assertLess(text.index("DOMAIN-SUFFIX,google.com,Google出口"), text.index("GEOSITE,geolocation-!cn"))
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
