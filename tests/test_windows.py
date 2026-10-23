"""Windows variants of mirror_check: PowerShell outputs are scripted per tag; nothing real runs."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mirror_check as mc  # noqa: E402
import winchecks  # noqa: E402
from test_mirror_check import FakeHost, MANIFEST, Stat, GROUP_PATH  # noqa: E402

HOME = "C:\\Users\\tester"


class WinHost(FakeHost):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.platform = "win32"
        self.environ = {"APPDATA": HOME + "\\AppData\\Roaming", "LOCALAPPDATA": HOME + "\\AppData\\Local", "USERPROFILE": HOME}
        self.cmds = {
            ("curl", "-sS", "-m", "15", "https://www.cloudflare.com/cdn-cgi/trace"): (0, "ip=203.0.113.166\ncolo=LAX\nloc=US\n", ""),
            ("nslookup", "-class=chaos", "-type=txt", "whoami.cloudflare", "1.1.1.1"): (0, 'Server:  one.one.one.one\n\nwhoami.cloudflare\ttext =\n\n\t"203.0.113.166"\n', ""),
            ("nslookup", "-type=txt", "o-o.myaddr.l.google.com", "ns1.google.com"): (0, 'o-o.myaddr.l.google.com\ttext =\n\n\t"2400:cb00:445:1024::ac46:cd0a"\n', ""),
            ("tzutil", "/g"): (0, "Pacific Standard Time\n", ""),
        }
        self.ps_outputs = {
            "os": "Microsoft Windows 10 Pro 10.0.19045\n",
            "tun": "198.18.0.1\n",
            "dns-udp": "198.18.0.50\n", "dns-tcp": "198.18.0.50\n", "dns-system": "198.18.0.50\n",
            "adapters": "Ethernet\nWLAN\n",
            "sysdns": "198.18.0.2\n",
            "ipv6-binding": "False\n", "ipv6-addr": "",
            "reg-Chrome": json.dumps({"WebRtcIPHandling": "disable_non_proxied_udp", "DnsOverHttpsMode": "off"}),
            "reg-Edge": json.dumps({"WebRtcIPHandling": "disable_non_proxied_udp", "DnsOverHttpsMode": "off"}),
            "fw-profile": json.dumps([{"Name": "Domain", "Enabled": True}, {"Name": "Private", "Enabled": True}, {"Name": "Public", "Enabled": True}]),
            "fw-rule": json.dumps({"DisplayName": "x", "Enabled": "True", "Action": "Block", "Direction": "Outbound"}),
            "task": json.dumps({"State": "Ready", "LastTaskResult": 0, "LastRunTime": "2026-10-22 16:00"}),
            "lang": "zh-Hans-CN\nen-US\n",
        }
        self.stats = {
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe": Stat(0, 0o100644),
            "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe": Stat(0, 0o100644),
            HOME + "\\AppData\\Local\\claude-setup-kit\\claude-wall.ps1": Stat(0, 0o100644),
        }
        runtime = HOME + "\\AppData\\Roaming\\io.github.clash-verge-rev.clash-verge-rev\\clash-verge.yaml"
        self.files = {runtime: list(self.files.values())[1], "C:\\ProgramData\\claude-setup-kit\\watch\\last": "2026-10-22T22:36:23Z\tOK\t全部正常\n",
                      HOME + "\\AppData\\Roaming\\io.github.clash-verge-rev.clash-verge-rev\\config.yaml": "mixed-port: 7890\nexternal-controller-pipe: x\n"}
        self.apis["/configs"]["tun"]["device"] = "Meta"

    # Paths built on macOS use "/", the fixture keys use "\\": compare them normalised.
    def _norm(self, path):
        return str(path).replace("/", "\\")

    def read_text(self, path):
        key = next((k for k in self.files if self._norm(k) == self._norm(path)), None)
        if key is None:
            raise mc.HostError("读不到 %s" % path)
        return self.files[key]

    def lstat(self, path):
        return next((v for k, v in self.stats.items() if self._norm(k) == self._norm(path)), None)

    def env(self, name):
        if name not in self.environ:
            raise mc.HostError("环境变量 %%%s%% 没有设置" % name)
        return self.environ[name]

    def home(self):
        return Path(HOME)


def run_json(host, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mc.main(["--manifest", MANIFEST, "--json", "--platform", "win32", *argv], host=host)
    data = json.loads(out.getvalue())
    return code, {i["id"]: i for i in data["items"]}, data


class WindowsBaselineTests(unittest.TestCase):
    def test_manifest_selects_windows_components_and_params(self):
        m = mc.load_manifest(MANIFEST, "win32")
        ids = {c["id"] for c in m["components"]}
        self.assertIn("wf.011", ids)
        self.assertIn("clash.core", ids)
        self.assertNotIn("pf.010", ids)
        self.assertNotIn("daemon.watch", ids)
        self.assertEqual(m["params"]["tun_device"], "Meta")
        self.assertEqual(m["params"]["clash_api"], "pipe://verge-mihomo")
        self.assertEqual(m["platform"], "win32")
        self.assertEqual(len(m["components"]), 27)

    def test_reference_windows_passes_everything(self):
        code, items, data = run_json(WinHost())
        failing = {k: v["evidence"] for k, v in items.items() if v["status"] not in (mc.PASS, mc.INFO, mc.MANUAL)}
        self.assertEqual(failing, {})
        self.assertEqual(data["platform"], "win32")
        self.assertEqual(items["dns.system"]["status"], mc.INFO)  # Clash Verge 2.4.4 leaves the system DNS alone; recorded only
        self.assertEqual(code, 0)

    def test_every_windows_query_is_read_only(self):
        host = WinHost()
        run_json(host)
        for argv in host.calls:
            self.assertIn(argv[0], ("powershell", "curl", "nslookup", "tzutil"), argv)
        for tag in host.ps_outputs:
            self.assertNotRegex(tag, r"set|new|remove|install", tag)


class WindowsFailureTests(unittest.TestCase):
    def test_tun_adapter_missing(self):
        host = WinHost()
        del host.ps_outputs["tun"]
        _, items, _ = run_json(host, "--only", "net.tun_iface")
        self.assertEqual(items["net.tun_iface"]["status"], mc.FAIL)
        self.assertIn("Meta", items["net.tun_iface"]["evidence"])

    def test_local53_not_fake_ip(self):
        host = WinHost()
        host.ps_outputs["dns-udp"] = "104.16.123.96\n"
        _, items, _ = run_json(host, "--only", "dns.local53")
        self.assertIn("不是 fake-ip", items["dns.local53"]["evidence"])

    def test_wrong_adapter_alias_is_explained_not_a_cim_error(self):
        # Chinese Windows names the adapter 以太网; the manifest default is Ethernet. The two adapter checks must say
        # which names exist instead of surfacing Get-DnsClientServerAddress / Get-NetAdapterBinding CIM errors.
        host = WinHost()
        host.ps_outputs["adapters"] = "以太网\nWLAN\n"
        del host.ps_outputs["sysdns"]
        del host.ps_outputs["ipv6-binding"]
        _, items, _ = run_json(host, "--only", "dns.system,net.ipv6_off")
        for cid in ("dns.system", "net.ipv6_off"):
            self.assertEqual(items[cid]["status"], mc.UNKNOWN, cid)
            self.assertIn("'Ethernet'", items[cid]["evidence"])
            self.assertIn("以太网", items[cid]["evidence"])
            self.assertIn("mirror.params.json", items[cid]["evidence"])
            self.assertNotIn("PowerShell 失败", items[cid]["evidence"])

    def test_ipv6_binding_still_enabled(self):
        host = WinHost()
        host.ps_outputs["ipv6-binding"] = "True\n"
        _, items, _ = run_json(host, "--only", "net.ipv6_off")
        self.assertIn("仍启用", items["net.ipv6_off"]["evidence"])

    def test_chrome_installed_per_user_is_still_checked(self):
        # Per-user Chrome lives under %LOCALAPPDATA%; it must not be reported as "not installed" and skipped.
        host = WinHost()
        del host.stats["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"]
        host.stats[mc.expand(host, "%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe")] = Stat(0, 0o100644)
        _, items, _ = run_json(host, "--only", "chrome.policy")
        self.assertEqual(items["chrome.policy"]["status"], mc.PASS)

    def test_policies_missing_or_wrong(self):
        host = WinHost()
        del host.ps_outputs["reg-Chrome"]
        host.ps_outputs["reg-Edge"] = json.dumps({"WebRtcIPHandling": "default", "DnsOverHttpsMode": "off"})
        _, items, _ = run_json(host, "--only", "chrome.policy,reg.edge")
        self.assertIn("不存在", items["chrome.policy"]["evidence"])
        self.assertIn("值不对", items["reg.edge"]["evidence"])
        del host.stats["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"]
        _, items, _ = run_json(host, "--only", "chrome.policy")
        self.assertEqual(items["chrome.policy"]["status"], mc.INFO)

    def test_firewall_profile_off_and_rule_missing(self):
        host = WinHost()
        host.ps_outputs["fw-profile"] = json.dumps([{"Name": "Domain", "Enabled": False}, {"Name": "Private", "Enabled": True}, {"Name": "Public", "Enabled": False}])
        del host.ps_outputs["fw-rule"]
        _, items, _ = run_json(host, "--only", "wf.enabled,wf.011,wf.020")
        self.assertIn("Domain", items["wf.enabled"]["evidence"])
        self.assertIn("缺规则 claude-setup-kit: net-wall v4", items["wf.011"]["evidence"])
        self.assertEqual(items["wf.020"]["status"], mc.FAIL)

    def test_rule_with_numeric_enums_is_not_trusted(self):
        # The check asks PowerShell for string enums; a numeric payload means the query shape changed.
        host = WinHost()
        host.ps_outputs["fw-rule"] = json.dumps({"DisplayName": "x", "Enabled": 1, "Action": 4, "Direction": 2})
        _, items, _ = run_json(host, "--only", "wf.011")
        self.assertEqual(items["wf.011"]["status"], mc.FAIL)

    def test_rule_disabled(self):
        host = WinHost()
        host.ps_outputs["fw-rule"] = json.dumps({"DisplayName": "x", "Enabled": "False", "Action": "Block", "Direction": "Outbound"})
        _, items, _ = run_json(host, "--only", "wf.011")
        self.assertIn("状态不对", items["wf.011"]["evidence"])

    def test_scheduled_task_states(self):
        host = WinHost()
        host.ps_outputs["task"] = json.dumps({"State": "Disabled", "LastTaskResult": 0, "LastRunTime": "x"})
        _, items, _ = run_json(host, "--only", "task.watch")
        self.assertIn("Disabled", items["task.watch"]["evidence"])
        host.ps_outputs["task"] = json.dumps({"State": "Ready", "LastTaskResult": 1, "LastRunTime": "x"})
        _, items, _ = run_json(host, "--only", "task.watch")
        self.assertIn("最近结果 1", items["task.watch"]["evidence"])
        del host.ps_outputs["task"]
        _, items, _ = run_json(host, "--only", "task.ipv6")
        self.assertIn("不存在", items["task.ipv6"]["evidence"])

    def test_watch_file_and_timezone_and_upstream(self):
        host = WinHost()
        host.files["C:\\ProgramData\\claude-setup-kit\\watch\\last"] = "2026-10-22T22:36:23Z\tWARN\tTUN 不在\n"
        _, items, _ = run_json(host, "--only", "watch.fresh")
        self.assertIn("WARN", items["watch.fresh"]["evidence"])
        host.cmds[("tzutil", "/g")] = (0, "China Standard Time\n", "")
        _, items, _ = run_json(host, "--only", "sys.timezone")
        self.assertEqual(items["sys.timezone"]["status"], mc.FAIL)
        host.cmds[("nslookup", "-class=chaos", "-type=txt", "whoami.cloudflare", "1.1.1.1")] = (0, 'whoami.cloudflare\ttext =\n\n\t"198.51.100.9"\n', "")
        _, items, _ = run_json(host, "--only", "dns.upstream")
        self.assertIn("≠ HTTPS 出口", items["dns.upstream"]["evidence"])

    def test_claude_wall_ps_missing(self):
        host = WinHost()
        del host.stats[HOME + "\\AppData\\Local\\claude-setup-kit\\claude-wall.ps1"]
        _, items, _ = run_json(host, "--only", "tool.claude_wall_ps")
        self.assertIn("不存在", items["tool.claude_wall_ps"]["evidence"])


class PlumbingTests(unittest.TestCase):
    def test_main_script_binds_winchecks_to_its_own_error_class(self):
        # Run the real script as __main__ on this (non-Windows) host: powershell is missing, so the
        # Windows checks must turn the HostError into ❌/❓ cleanly instead of leaking a foreign class.
        import subprocess
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "mirror_check.py"), "--manifest", MANIFEST,
                               "--platform", "win32", "--no-network", "--json", "--only", "net.tun_iface,wf.011"],
                              capture_output=True, encoding="utf-8")
        self.assertIn(proc.returncode, (1, 2), proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        items = {i["id"]: i for i in json.loads(proc.stdout)["items"]}
        self.assertEqual(items["net.tun_iface"]["status"], mc.FAIL)
        self.assertEqual(items["wf.011"]["status"], mc.FAIL)

    def test_dechunk(self):
        self.assertEqual(mc.dechunk(b"4\r\nWiki\r\n6;ext=1\r\npedia \r\n0\r\n\r\n"), b"Wikipedia ")
        with self.assertRaises(mc.HostError):
            mc.dechunk(b"10\r\nshort")

    def test_clixml_error_is_humanised(self):
        err = '#< CLIXML\n<Objs><S S="Error">Get-NetIPAddress : 找不到接口 Meta_x000D__x000A_</S><S S="Error">所在位置</S></Objs>'
        self.assertEqual(mc.clixml_error(err), "Get-NetIPAddress : 找不到接口 Meta")
        self.assertEqual(mc.clixml_error(""), "")

    def test_windows_next_text_is_used(self):
        host = WinHost()
        del host.ps_outputs["tun"]
        _, items, _ = run_json(host, "--only", "net.tun_iface")
        self.assertIn("Meta", items["net.tun_iface"]["next"])
        self.assertNotIn("utun", items["net.tun_iface"]["next"])

    def test_expand_windows_variables(self):
        host = WinHost()
        self.assertEqual(mc.expand(host, "%APPDATA%/x/y.yaml").replace("/", "\\"), HOME + "\\AppData\\Roaming\\x\\y.yaml")
        with self.assertRaises(mc.HostError):
            mc.expand(host, "%NOPE%/x")

    def test_pipe_api_unreachable_is_host_error(self):
        with self.assertRaises(mc.HostError):
            mc.Host().pipe_api("claude-setup-kit-no-such-pipe", "/version", timeout=1)

    def test_powershell_runner_encodes_utf16(self):
        host = FakeHost()
        host.cmds = {}
        captured = {}

        def run(argv, timeout=20):
            captured["argv"] = argv
            return 0, "ok\n", ""
        host.run = run
        host.ps = lambda script, tag=None, timeout=60: mc.Host.ps(host, script, tag, timeout)
        self.assertEqual(host.ps("Get-Date", tag="t"), "ok\n")
        self.assertEqual(captured["argv"][:2], ["powershell", "-NoProfile"])
        self.assertIn("-EncodedCommand", captured["argv"])


if __name__ == "__main__":
    unittest.main()
