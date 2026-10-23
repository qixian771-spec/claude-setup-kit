"""Fixture tests for scripts/mirror_check.py. No real commands run; a FakeHost answers everything."""
import contextlib
import datetime as dt
import io
import json
import plistlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import os

os.environ.setdefault("CLAUDE_SETUP_KIT_PLATFORM", "darwin")  # the fixtures describe the macOS reference machine
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mirror_check as mc  # noqa: E402

# A private copy: the repo root may hold a git-ignored mirror.params.json with
# per-machine overrides, and the fixtures must see the manifest defaults only.
_TMP = tempfile.TemporaryDirectory(prefix="mirror-manifest-")
MANIFEST = str(Path(_TMP.name) / "manifest.json")
shutil.copy(ROOT / "manifest.json", MANIFEST)
HOME = "/Users/tester"
NOW = dt.datetime(2026, 10, 22, 22, 37, 0, tzinfo=dt.timezone.utc)
GROUP_PATH = "/proxies/%E5%87%BA%E5%8F%A3%E9%80%89%E6%8B%A9"
GOOGLE_PATH = "/proxies/Google%E5%87%BA%E5%8F%A3"

RULES_010 = '''pass out quick on utun1024 from any to <claude_wall_targets> no state label "claude-wall-tun"
block drop out quick inet from any to <claude_wall_targets> label "claude-wall-ipv4"
block drop out quick inet6 from any to <claude_wall_targets> label "claude-wall-ipv6"
'''
RULES_011 = RULES_010.replace("claude_wall_targets", "claude_wall_nets").replace("claude-wall-", "claude-net-wall-")
RULES_020 = '''pass out quick on lo0 all no state label "leak-guard-local"
pass out quick on utun1024 all no state label "leak-guard-tun"
block drop out quick proto tcp from any to any port = 53 label "leak-guard-dns"
block drop out quick proto udp from any to any port = 53 label "leak-guard-dns"
block drop out quick proto tcp from any to any port = 3478 label "leak-guard-stun"
block drop out quick proto tcp from any to ! <leak_guard_local> user = 501 label "leak-guard-user-public"
block drop out quick proto udp from any to ! <leak_guard_local> user = 501 label "leak-guard-user-public"
'''
PF_CONF = '''scrub-anchor "com.apple/*"
anchor "com.apple/*"
load anchor "com.apple" from "/etc/pf.anchors/com.apple"
# Exact confirmed Claude destinations
load anchor "com.apple/010.local.claude-direct-wall" from "/etc/pf.anchors/local.claude-direct-wall"
load anchor "com.apple/020.local.leak-guard" from "/etc/pf.anchors/local.leak-guard"
'''
RUNTIME_CONFIG = '''mixed-port: 7890
mode: rule
ipv6: false
dns:
  enable: true
  listen: 127.0.0.1:53
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  default-nameserver:
  - https://223.5.5.5/dns-query#DIRECT
  proxy-server-nameserver:
  - https://223.5.5.5/dns-query#DIRECT
  nameserver:
  - https://1.1.1.1/dns-query#出口选择
  nameserver-policy:
    +.anthropic.com:
    - https://1.1.1.1/dns-query#出口选择
    +.claude.ai:
    - https://1.1.1.1/dns-query#出口选择
    +.claude.com:
    - https://1.1.1.1/dns-query#出口选择
    +.claude.app:
    - https://1.1.1.1/dns-query#出口选择
    +.claudeusercontent.com:
    - https://1.1.1.1/dns-query#出口选择
    +.claudemcpcontent.com:
    - https://1.1.1.1/dns-query#出口选择
    geosite:cn:
    - https://223.5.5.5/dns-query#DIRECT
tun:
  device: utun1024
  enable: true
'''
BASE_CONFIG = "mixed-port: 7890\nmode: rule\nexternal-controller-unix: /tmp/verge/verge-mihomo.sock\ntun:\n  stack: gvisor\n"
UPDATER_LOG = "\n".join([
    json.dumps({"status": "APPLIED", "finished_utc": "2026-10-22T22:15:11.468705+00:00"}),
    json.dumps({"report": "x", "status": "STOPPED_OLD_TARGETS_NOT_REMOVED", "new_candidates": []}),
    json.dumps({"status": "STOPPED_OLD_TARGETS_NOT_REMOVED", "finished_utc": "2026-10-22T22:30:13+00:00"}),
]) + "\n"
IPV6_GUARD_PLIST = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>local.ipv6-guard</string>
<key>ProgramArguments</key><array><string>/usr/local/libexec/ipv6-guard.sh</string></array>
<key>StandardErrorPath</key><string>/var/log/ipv6-guard.err</string>
<key>StandardOutPath</key><string>/var/log/ipv6-guard.out</string>
</dict></plist>
"""
CHROME_POLICY = plistlib.dumps({"DnsOverHttpsMode": "off", "WebRtcIPHandling": "disable_non_proxied_udp"})


class Stat:
    def __init__(self, uid, mode):
        self.st_uid, self.st_mode = uid, mode


def dig(*extra, server="127.0.0.1", name="www.cloudflare.com", rtype="A"):
    return ("dig", "+short", "+time=3", "+tries=1") + extra + ("@" + server, name, rtype)


def baseline_cmds():
    cmds = {
        ("sw_vers", "-productVersion"): (0, "26.5.2\n", ""),
        ("ifconfig", "utun1024"): (0, "utun1024: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1500\n\tinet 198.18.0.1 --> 198.18.0.1 netmask 0xfffffffc\n", ""),
        dig(): (0, "198.18.0.50\n", ""),
        dig("+tcp"): (0, "198.18.0.50\n", ""),
        ("dscacheutil", "-q", "host", "-a", "name", "www.cloudflare.com"): (0, "name: www.cloudflare.com\nip_address: 198.18.0.50\n", ""),
        ("networksetup", "-getdnsservers", "Wi-Fi"): (0, "114.114.114.114\n", ""),
        ("networksetup", "-getinfo", "Wi-Fi"): (0, "DHCP Configuration\nIP address: 192.168.1.8\nRouter: 192.168.1.1\nIPv6: Off\n", ""),
        ("networksetup", "-listallhardwareports"): (0, "\nHardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa:bb\n\nHardware Port: Thunderbolt Bridge\nDevice: bridge0\n", ""),
        ("ifconfig", "en0"): (0, "en0: flags=8863<UP> mtu 1500\n\tinet6 fe80::1%en0 prefixlen 64\n\tinet 192.168.1.8 netmask 0xffffff00\n", ""),
        ("pfctl", "-si"): (0, "Status: Enabled for 0 days 01:46:49           Debug: Urgent\n", ""),
        ("pfctl", "-a", "com.apple/010.local.claude-direct-wall", "-sr"): (0, RULES_010, ""),
        ("pfctl", "-a", "com.apple/011.local.claude-net-wall", "-sr"): (0, RULES_011, ""),
        ("pfctl", "-a", "com.apple/020.local.leak-guard", "-sr"): (0, RULES_020, ""),
        ("pfctl", "-a", "com.apple/010.local.claude-direct-wall", "-t", "claude_wall_targets", "-T", "show"): (0, "   160.79.104.10\n   2607:6bc0::10\n", ""),
        ("pfctl", "-a", "com.apple/011.local.claude-net-wall", "-t", "claude_wall_nets", "-T", "show"): (0, "   160.79.104.0/21\n   2607:6bc0::/32\n", ""),
        ("cat", "/var/db/NetGuardWatch/last"): (0, "2026-10-22T22:36:23Z\tOK\t全部正常\n", ""),
        ("tail", "-n", "200", HOME + "/Library/Application Support/ClaudeDirectWallUpdater/stdout.log"): (0, UPDATER_LOG, ""),
        ("profiles", "-P"): (0, "_computerlevel[1] attribute: profileIdentifier: local.claude-mac-env-mirror.chrome\n", ""),
        (HOME + "/.local/bin/claude-wall", "status"): (0, "PF: 已启用，两处锚点均装载\nDNS: fake-ip 正常\n守护: 正常（2026-10-22T22:36:23Z）\n", ""),
        ("curl", "-sS", "-m", "15", "https://www.cloudflare.com/cdn-cgi/trace"): (0, "ip=203.0.113.166\ncolo=LAX\nloc=US\n", ""),
        dig("CH", server="1.1.1.1", name="whoami.cloudflare", rtype="TXT"): (0, '"203.0.113.166"\n', ""),
        dig(server="ns1.google.com", name="o-o.myaddr.l.google.com", rtype="TXT"): (0, '"2400:cb00:445:1024::ac46:cd0a"\n', ""),
        ("readlink", "/etc/localtime"): (0, "/var/db/timezone/zoneinfo/America/Los_Angeles\n", ""),
        ("defaults", "read", "-g", "AppleLanguages"): (0, '(\n    "zh-Hans-US",\n    "zh-Hant-US",\n    "en-US"\n)\n', ""),
    }
    for label, code in (("local.claude-direct-wall", 0), ("local.claude-net-wall", 0), ("local.leak-guard", 0),
                        ("local.claude-address-update", 1), ("local.net-guard-watch", 0), ("local.ipv6-guard", 0)):
        cmds[("launchctl", "print", "system/" + label)] = (0, "system/%s = {\n\tstate = not running\n\tlast exit code = %d\n}\n" % (label, code), "")
    return cmds


def baseline_stats():
    stats = {
        "/etc/pf.anchors/local.claude-direct-wall": Stat(0, 0o100644),
        "/etc/pf.anchors/local.claude-net-wall": Stat(0, 0o100644),
        "/etc/pf.anchors/local.leak-guard": Stat(0, 0o100644),
        "/usr/local/libexec/claude-direct-wall": Stat(0, 0o100755),
        "/usr/local/libexec/claude-net-wall": Stat(0, 0o100755),
        "/usr/local/libexec/leak-guard-loader": Stat(0, 0o100755),
        "/usr/local/libexec/net-guard-watch": Stat(0, 0o100755),
        "/usr/local/libexec/net-guard-watch-lib.sh": Stat(0, 0o100644),
        "/Library/Application Support/ClaudeDirectWallUpdater/sha256.json": Stat(0, 0o100644),
        "/Applications/Google Chrome.app": Stat(0, 0o40755),
        "/Library/Managed Preferences/com.google.Chrome.plist": Stat(0, 0o100644),
        HOME + "/.local/bin/ipv6-guard.sh": Stat(501, 0o100755),
        "/usr/local/libexec/ipv6-guard.sh": Stat(0, 0o100755),
        HOME + "/.local/bin/claude-wall": Stat(501, 0o100755),
    }
    for label in ("local.claude-direct-wall", "local.claude-net-wall", "local.leak-guard",
                  "local.claude-address-update", "local.net-guard-watch", "local.ipv6-guard"):
        stats["/Library/LaunchDaemons/%s.plist" % label] = Stat(0, 0o100644)
    return stats


def baseline_apis():
    return {
        "/version": {"meta": True, "version": "v1.19.29"},
        "/configs": {"mode": "rule", "ipv6": False, "mixed-port": 7890,
                     "tun": {"enable": True, "device": "utun1024", "inet4-address": ["198.18.0.1/30"],
                             "dns-hijack": ["any:53", "tcp://any:53"]}},
        GROUP_PATH: {"type": "Selector", "now": "丽萨美国", "all": ["丽萨美国", "204美国", "韩国43", "76美国"]},
        GOOGLE_PATH: {"type": "Selector", "now": "韩国43", "all": ["韩国43", "76美国"]},
        "/rules": {"rules": [
            {"type": "DstPort", "payload": "3478", "proxy": "REJECT"},
            {"type": "DstPort", "payload": "5349", "proxy": "REJECT"},
            {"type": "DstPort", "payload": "19302", "proxy": "REJECT"},
        ] + [{"type": "DomainSuffix", "payload": s, "proxy": "出口选择"} for s in (
            "anthropic.com", "claude.ai", "claude.com", "claude.app", "claudeusercontent.com", "claudemcpcontent.com")] + [
            {"type": "Domain", "payload": "storage.googleapis.com", "proxy": "出口选择"},
            {"type": "Domain", "payload": "fonts.googleapis.com", "proxy": "出口选择"},
            {"type": "Domain", "payload": "fonts.gstatic.com", "proxy": "出口选择"},
        ] + [{"type": "DomainSuffix", "payload": s, "proxy": "Google出口"} for s in (
            "google.com", "googleapis.com", "gstatic.com", "googleusercontent.com")] + [
            {"type": "GeoSite", "payload": "private", "proxy": "DIRECT"},
            {"type": "GeoSite", "payload": "CN", "proxy": "DIRECT"},
            {"type": "GeoSite", "payload": "geolocation-!cn", "proxy": "出口选择"},
            {"type": "GeoIP", "payload": "cn", "proxy": "DIRECT"},
            {"type": "Match", "payload": "", "proxy": "出口选择"},
        ]},
    }


class FakeHost:
    def __init__(self, sudo=True, macos=True, uid=501, now=NOW):
        self.cmds, self.stats, self.apis = baseline_cmds(), baseline_stats(), baseline_apis()
        self.files = {"/etc/pf.conf": PF_CONF,
                      HOME + "/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml": RUNTIME_CONFIG,
                      HOME + "/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/config.yaml": BASE_CONFIG}
        self.bytes = {"/Library/Managed Preferences/com.google.Chrome.plist": CHROME_POLICY,
                      "/Library/LaunchDaemons/local.ipv6-guard.plist": IPV6_GUARD_PLIST}
        self.links = set()
        self.sudo, self.macos, self.uid, self._now = sudo, macos, uid, now
        self.platform = "darwin" if macos else "linux"
        self.ps_outputs = {}
        self.calls, self.priv_calls = [], []

    def run(self, argv, timeout=20):
        # On a Windows runner pathlib builds the home-relative arguments with "\\"; the fixture keys use "/".
        # (Not self._norm: the Windows fixture overrides that to map the other way for its file tables.)
        argv = [str(a).replace("\\", "/") for a in argv]
        self.calls.append(list(argv))
        key = tuple(argv)
        if key not in self.cmds:
            raise mc.HostError("缺少工具: %s" % argv[0])
        return self.cmds[key]

    def priv(self, argv, timeout=20):
        self.priv_calls.append(list(argv))
        if not self.sudo:
            raise mc.NeedSudo("需要 sudo: %s" % " ".join(argv))
        return self.run(argv, timeout)

    # Paths built with pathlib on a Windows runner use "\\"; the fixture keys use "/".
    @staticmethod
    def _norm(path):
        return str(path).replace("\\", "/")

    def _lookup(self, table, path):
        key = next((k for k in table if self._norm(k) == self._norm(path)), None)
        return key

    def read_text(self, path):
        key = self._lookup(self.files, path)
        if key is None:
            raise mc.HostError("读不到 %s" % path)
        return self.files[key]

    def read_bytes(self, path):
        key = self._lookup(self.bytes, path)
        if key is None:
            raise mc.HostError("读不到 %s" % path)
        return self.bytes[key]

    def lstat(self, path):
        key = self._lookup(self.stats, path)
        return self.stats.get(key) if key is not None else None

    def is_link(self, path):
        return path in self.links

    def api(self, base, path, timeout=10):
        if path not in self.apis:
            if path.startswith("/proxies/") and "/version" in self.apis:
                raise mc.HostError("API %s 返回 404" % path)  # core up, group missing
            raise mc.HostError("API 不可达 %s" % base)
        return self.apis[path]

    def ps(self, script, tag=None, timeout=60):
        self.calls.append(["powershell", tag or script[:40]])
        if tag not in self.ps_outputs:
            raise mc.HostError("PowerShell 失败（%s）" % tag)
        return self.ps_outputs[tag]

    def console_uid(self):
        return self.uid

    def home(self):
        return Path(HOME)

    def console_name(self):
        return "tester"

    def now(self):
        return self._now

    def is_macos(self):
        return self.macos


def run(host, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = mc.main(["--manifest", MANIFEST] + list(argv), host=host)
    return code, out.getvalue()


def run_json(host, *argv):
    code, out = run(host, "--json", *argv)
    data = json.loads(out)
    return code, {i["id"]: i for i in data["items"]}, data


class ManifestTests(unittest.TestCase):
    def test_manifest_loads_and_every_component_has_next(self):
        data = mc.load_manifest(MANIFEST)
        self.assertEqual(data["format"], 1)
        for comp in data["components"]:
            self.assertTrue(comp.get("next"), comp["id"])
            self.assertIn(comp["check"], mc.CHECKS)
            self.assertTrue(comp["layer"] and comp["title"])

    def test_duplicate_id_rejected(self):
        data = json.loads(Path(MANIFEST).read_text(encoding="utf-8"))
        data["components"].append(dict(data["components"][0]))
        path = Path(self.id() + ".json")
        path.write_text(json.dumps(data), encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                mc.load_manifest(str(path))
        finally:
            path.unlink()


class BaselineTests(unittest.TestCase):
    def test_reference_mac_passes_everything(self):
        code, items, data = run_json(FakeHost())
        failing = {k: v for k, v in items.items() if v["status"] not in (mc.PASS, mc.INFO, mc.MANUAL)}
        self.assertEqual(failing, {})
        self.assertEqual(code, 0)
        self.assertEqual(items["sys.language"]["status"], mc.INFO)
        self.assertEqual(items["browser.webrtc"]["status"], mc.MANUAL)
        self.assertEqual(data["exit"], 0)

    def test_table_output_lists_every_component(self):
        code, out = run(FakeHost())
        for comp in mc.load_manifest(MANIFEST)["components"]:
            self.assertIn(comp["id"], out)
        self.assertIn("→ exit 0", out)

    def test_read_only_commands_only(self):
        host = FakeHost()
        run_json(host)
        read_only = {
            "sw_vers": None, "ifconfig": None, "dig": None, "dscacheutil": None, "readlink": None,
            "defaults": lambda a: a[1] == "read", "networksetup": lambda a: a[1].startswith(("-get", "-list")),
            "pfctl": lambda a: set(a[1:]) & {"-si", "-sr", "show"} and "-f" not in a and "-k" not in a,
            "launchctl": lambda a: a[1] == "print", "cat": None, "tail": None, "profiles": lambda a: a[1] == "-P",
            "curl": lambda a: a[1] == "-sS", HOME + "/.local/bin/claude-wall": lambda a: a[1] == "status",
        }
        for argv in host.calls:
            self.assertIn(argv[0], read_only, argv)
            rule = read_only[argv[0]]
            self.assertTrue(rule is None or rule(argv), argv)

    def test_source_has_no_write_paths(self):
        source = (ROOT / "scripts" / "mirror_check.py").read_text(encoding="utf-8")
        # pipe_api opens the Clash controller pipe read/write to send one GET; nothing else may open files for writing.
        head, _, rest = source.partition("    def pipe_api(")
        _, _, tail = rest.partition("    def ps(")
        scanned = head + tail
        for token in ("write_text", "write_bytes", "os.remove", "shutil", "open(", "unlink", "rename"):
            self.assertNotIn(token, scanned, token)
        self.assertEqual(source.count("subprocess.run("), 1)
        for token in ("write_text", "write_bytes", "os.remove", "shutil", "unlink"):
            self.assertNotIn(token, (ROOT / "scripts" / "winchecks.py").read_text(encoding="utf-8"), token)


class DriftTests(unittest.TestCase):
    def test_chrome_policy_missing_is_the_known_drift(self):
        host = FakeHost()
        del host.stats["/Library/Managed Preferences/com.google.Chrome.plist"]
        host.cmds[("profiles", "-P")] = (0, "There are no configuration profiles installed\n", "")
        code, items, _ = run_json(host)
        self.assertEqual(code, 1)
        self.assertEqual(items["chrome.policy"]["status"], mc.FAIL)
        self.assertIn("mobileconfig", items["chrome.policy"]["next"])

    def test_chrome_policy_without_profile_is_not_durable(self):
        host = FakeHost()
        host.cmds[("profiles", "-P")] = (0, "There are no configuration profiles installed\n", "")
        _, items, _ = run_json(host, "--only", "chrome.policy")
        self.assertEqual(items["chrome.policy"]["status"], mc.FAIL)
        self.assertIn("描述文件", items["chrome.policy"]["evidence"])

    def test_chrome_policy_wrong_value(self):
        host = FakeHost()
        host.bytes["/Library/Managed Preferences/com.google.Chrome.plist"] = plistlib.dumps({"WebRtcIPHandling": "default"})
        _, items, _ = run_json(host, "--only", "chrome.policy")
        self.assertEqual(items["chrome.policy"]["status"], mc.FAIL)

    def test_chrome_absent_is_info(self):
        host = FakeHost()
        del host.stats["/Applications/Google Chrome.app"]
        code, items, _ = run_json(host, "--only", "chrome.policy")
        self.assertEqual(items["chrome.policy"]["status"], mc.INFO)
        self.assertEqual(code, 0)

    def test_system_dns_accepts_clash_managed_value_but_not_others(self):
        host = FakeHost()
        _, items, _ = run_json(host, "--only", "dns.system")
        self.assertEqual(items["dns.system"]["status"], mc.PASS)
        host.cmds[("networksetup", "-getdnsservers", "Wi-Fi")] = (0, "127.0.0.1\n", "")
        _, items, _ = run_json(host, "--only", "dns.system")
        self.assertEqual(items["dns.system"]["status"], mc.PASS)
        host.cmds[("networksetup", "-getdnsservers", "Wi-Fi")] = (0, "8.8.8.8\n", "")
        _, items, _ = run_json(host, "--only", "dns.system")
        self.assertEqual(items["dns.system"]["status"], mc.FAIL)
        host.cmds[("networksetup", "-getdnsservers", "Wi-Fi")] = (0, "There aren't any DNS Servers set on Wi-Fi.\n", "")
        _, items, _ = run_json(host, "--only", "dns.system")
        self.assertEqual(items["dns.system"]["status"], mc.FAIL)


class ClashTests(unittest.TestCase):
    def test_mode_global_fails(self):
        host = FakeHost()
        host.apis["/configs"]["mode"] = "global"
        _, items, _ = run_json(host, "--only", "clash.mode")
        self.assertEqual(items["clash.mode"]["status"], mc.FAIL)

    def test_api_unreachable_is_unknown(self):
        host = FakeHost()
        host.apis = {}
        code, items, _ = run_json(host, "--only", "clash.core,clash.mode")
        self.assertEqual({i["status"] for i in items.values()}, {mc.UNKNOWN})
        self.assertEqual(code, 2)

    def test_tun_problems(self):
        host = FakeHost()
        host.apis["/configs"]["tun"]["device"] = "utun9"
        host.apis["/configs"]["ipv6"] = True
        _, items, _ = run_json(host, "--only", "clash.tun")
        self.assertEqual(items["clash.tun"]["status"], mc.FAIL)
        self.assertIn("device=utun9", items["clash.tun"]["evidence"])
        self.assertIn("ipv6=true", items["clash.tun"]["evidence"])

    def test_exit_group_direct_member_or_wrong_node(self):
        host = FakeHost()
        host.apis[GROUP_PATH]["all"].append("DIRECT")
        _, items, _ = run_json(host, "--only", "clash.exit")
        self.assertIn("DIRECT", items["clash.exit"]["evidence"])
        host = FakeHost()
        host.apis[GROUP_PATH]["now"] = "204美国"
        _, items, _ = run_json(host, "--only", "clash.exit")
        self.assertEqual(items["clash.exit"]["status"], mc.FAIL)
        self.assertIn("丽萨美国", items["clash.exit"]["evidence"])

    def test_exit_node_param_override(self):
        host = FakeHost()
        host.apis[GROUP_PATH]["now"] = "204美国"
        _, items, data = run_json(host, "--only", "clash.exit", "--param", "exit_node=204美国")
        self.assertEqual(items["clash.exit"]["status"], mc.PASS)
        self.assertEqual(data["params"]["exit_node"], "204美国")

    def test_rules_missing_suffix_and_direct_leak(self):
        host = FakeHost()
        rules = host.apis["/rules"]["rules"]
        rules[:] = [r for r in rules if r["payload"] != "claude.ai"]
        rules.insert(0, {"type": "DomainSuffix", "payload": "claude.com", "proxy": "DIRECT"})
        _, items, _ = run_json(host, "--only", "clash.rules")
        self.assertEqual(items["clash.rules"]["status"], mc.FAIL)
        self.assertIn("DOMAIN-SUFFIX,claude.ai", items["clash.rules"]["evidence"])
        self.assertIn("走 DIRECT", items["clash.rules"]["evidence"])

    def test_rules_final_direct_fails(self):
        host = FakeHost()
        host.apis["/rules"]["rules"][-1]["proxy"] = "DIRECT"
        _, items, _ = run_json(host, "--only", "clash.rules")
        self.assertIn("MATCH", items["clash.rules"]["evidence"])

    def test_dns_config_fallback_or_unproxied_nameserver(self):
        host = FakeHost()
        key = next(k for k in host.files if k.endswith("clash-verge.yaml"))
        host.files[key] = RUNTIME_CONFIG.replace("  nameserver-policy:", "  fallback:\n  - https://8.8.8.8/dns-query\n  nameserver-policy:")
        _, items, _ = run_json(host, "--only", "clash.dns")
        self.assertIn("fallback", items["clash.dns"]["evidence"])
        host.files[key] = RUNTIME_CONFIG.replace("  - https://1.1.1.1/dns-query#出口选择\n  nameserver-policy", "  - https://1.1.1.1/dns-query\n  nameserver-policy")
        _, items, _ = run_json(host, "--only", "clash.dns")
        self.assertIn("nameserver 未全部经", items["clash.dns"]["evidence"])

    def test_dns_config_missing_claude_policy_or_plain_bootstrap(self):
        host = FakeHost()
        key = next(k for k in host.files if k.endswith("clash-verge.yaml"))
        host.files[key] = RUNTIME_CONFIG.replace("    +.claude.app:\n    - https://1.1.1.1/dns-query#出口选择\n", "")
        _, items, _ = run_json(host, "--only", "clash.dns")
        self.assertIn("+.claude.app=缺", items["clash.dns"]["evidence"])
        host.files[key] = RUNTIME_CONFIG.replace("- https://223.5.5.5/dns-query#DIRECT\n  proxy-server", "- 223.5.5.5\n  proxy-server")
        _, items, _ = run_json(host, "--only", "clash.dns")
        self.assertIn("default-nameserver", items["clash.dns"]["evidence"])

    def test_runtime_config_unreadable_is_unknown(self):
        host = FakeHost()
        host.files = {"/etc/pf.conf": PF_CONF}
        code, items, _ = run_json(host, "--only", "clash.dns")
        self.assertEqual(items["clash.dns"]["status"], mc.UNKNOWN)
        self.assertEqual(code, 2)


class BaseConfigTests(unittest.TestCase):
    def test_base_config_with_embedded_profile_fails(self):
        host = FakeHost()
        key = next(k for k in host.files if k.endswith("/config.yaml"))
        host.files[key] = BASE_CONFIG + "proxies:\n- name: x\nproxy-groups:\n- name: y\nrules:\n- MATCH,y\n"
        _, items, _ = run_json(host, "--only", "clash.base_config")
        self.assertEqual(items["clash.base_config"]["status"], mc.FAIL)
        self.assertIn("proxies", items["clash.base_config"]["evidence"])
        _, items, _ = run_json(FakeHost(), "--only", "clash.base_config")
        self.assertEqual(items["clash.base_config"]["status"], mc.PASS)


class GoogleExitTests(unittest.TestCase):
    def test_reference_google_group_passes(self):
        _, items, _ = run_json(FakeHost(), "--only", "clash.google_exit")
        self.assertEqual(items["clash.google_exit"]["status"], mc.PASS)
        self.assertIn("韩国43", items["clash.google_exit"]["evidence"])

    def test_group_missing_or_pointing_at_claude_exit(self):
        host = FakeHost()
        del host.apis[GOOGLE_PATH]
        _, items, _ = run_json(host, "--only", "clash.google_exit")
        self.assertIn("不存在", items["clash.google_exit"]["evidence"])
        host = FakeHost()
        host.apis[GOOGLE_PATH]["now"] = "丽萨美国"
        _, items, _ = run_json(host, "--only", "clash.google_exit")
        self.assertIn("当前选中的是 Claude 出口", items["clash.google_exit"]["evidence"])

    def test_rule_order_matters(self):
        host = FakeHost()
        rules = host.apis["/rules"]["rules"]
        google = [r for r in rules if r["proxy"] == "Google出口"]
        rules[:] = [r for r in rules if r["proxy"] != "Google出口"]
        rules[-1:-1] = google  # after GEOSITE,geolocation-!cn, before MATCH (the v1 mistake)
        _, items, _ = run_json(host, "--only", "clash.google_exit")
        self.assertIn("排在 GEOSITE,geolocation-!cn 之后", items["clash.google_exit"]["evidence"])
        host = FakeHost()
        rules = host.apis["/rules"]["rules"]
        storage = next(r for r in rules if r["payload"] == "storage.googleapis.com")
        rules.remove(storage); rules.insert(rules.index(next(r for r in rules if r["payload"] == "geolocation-!cn")), storage)
        _, items, _ = run_json(host, "--only", "clash.google_exit")
        self.assertIn("storage.googleapis.com 的精确规则排在 Google 后缀规则之后", items["clash.google_exit"]["evidence"])

    def test_missing_suffix_rule(self):
        host = FakeHost()
        host.apis["/rules"]["rules"] = [r for r in host.apis["/rules"]["rules"] if r["payload"] != "gstatic.com" or r["proxy"] != "Google出口"]
        _, items, _ = run_json(host, "--only", "clash.google_exit")
        self.assertIn("缺 DOMAIN-SUFFIX,gstatic.com,Google出口", items["clash.google_exit"]["evidence"])


class NetworkLayerTests(unittest.TestCase):
    def test_tun_interface_missing(self):
        host = FakeHost()
        host.cmds[("ifconfig", "utun1024")] = (1, "", "ifconfig: interface utun1024 does not exist\n")
        _, items, _ = run_json(host, "--only", "net.tun_iface")
        self.assertEqual(items["net.tun_iface"]["status"], mc.FAIL)

    def test_local53_not_fake_ip_or_tcp_dead(self):
        host = FakeHost()
        host.cmds[dig()] = (0, "104.16.123.96\n", "")
        _, items, _ = run_json(host, "--only", "dns.local53")
        self.assertIn("不是 fake-ip", items["dns.local53"]["evidence"])
        host = FakeHost()
        host.cmds[dig("+tcp")] = (0, "", "")
        _, items, _ = run_json(host, "--only", "dns.local53")
        self.assertIn("tcp", items["dns.local53"]["evidence"])

    def test_system_resolver_bypassing_clash(self):
        host = FakeHost()
        host.cmds[("dscacheutil", "-q", "host", "-a", "name", "www.cloudflare.com")] = (0, "name: www.cloudflare.com\nip_address: 104.16.123.96\n", "")
        _, items, _ = run_json(host, "--only", "dns.local53")
        self.assertIn("没走 Clash", items["dns.local53"]["evidence"])

    def test_ipv6_on_or_global_address(self):
        host = FakeHost()
        host.cmds[("networksetup", "-getinfo", "Wi-Fi")] = (0, "IPv6: Automatic\n", "")
        _, items, _ = run_json(host, "--only", "net.ipv6_off")
        self.assertIn("IPv6=Automatic", items["net.ipv6_off"]["evidence"])
        host = FakeHost()
        host.cmds[("ifconfig", "en0")] = (0, "\tinet6 fe80::1%en0\n\tinet6 2400:1234::5 prefixlen 64\n", "")  # redact-allow: deliberate sample
        _, items, _ = run_json(host, "--only", "net.ipv6_off")
        self.assertIn("2400:1234::5", items["net.ipv6_off"]["evidence"])  # redact-allow: deliberate sample

    def test_exit_in_forbidden_country(self):
        host = FakeHost()
        host.cmds[("curl", "-sS", "-m", "15", "https://www.cloudflare.com/cdn-cgi/trace")] = (0, "ip=198.51.100.4\ncolo=SHA\nloc=CN\n", "")
        _, items, _ = run_json(host, "--only", "net.exit_ip")
        self.assertEqual(items["net.exit_ip"]["status"], mc.FAIL)

    def test_exit_probe_failure_is_unknown(self):
        host = FakeHost()
        host.cmds[("curl", "-sS", "-m", "15", "https://www.cloudflare.com/cdn-cgi/trace")] = (28, "", "curl: (28) timed out\n")
        code, items, _ = run_json(host, "--only", "net.exit_ip,dns.upstream")
        self.assertEqual({i["status"] for i in items.values()}, {mc.UNKNOWN})
        self.assertEqual(code, 2)

    def test_dns_upstream_mismatch_or_foreign_resolver(self):
        host = FakeHost()
        host.cmds[dig("CH", server="1.1.1.1", name="whoami.cloudflare", rtype="TXT")] = (0, '"198.51.100.8"\n', "")
        _, items, _ = run_json(host, "--only", "dns.upstream")
        self.assertIn("≠ HTTPS 出口", items["dns.upstream"]["evidence"])
        host = FakeHost()
        host.cmds[dig(server="ns1.google.com", name="o-o.myaddr.l.google.com", rtype="TXT")] = (0, '"114.114.114.114"\n', "")
        _, items, _ = run_json(host, "--only", "dns.upstream")
        self.assertIn("不属于 cloudflare", items["dns.upstream"]["evidence"])

    def test_no_network_marks_probes_unknown(self):
        code, items, _ = run_json(FakeHost(), "--no-network")
        self.assertEqual(items["net.exit_ip"]["status"], mc.UNKNOWN)
        self.assertEqual(items["dns.upstream"]["status"], mc.UNKNOWN)
        self.assertEqual(code, 2)


class FirewallTests(unittest.TestCase):
    def test_need_sudo_is_unknown_not_fail(self):
        host = FakeHost(sudo=False)
        code, items, _ = run_json(host, "--only", "pf.enabled,pf.010,watch.fresh")
        self.assertEqual({i["status"] for i in items.values()}, {mc.UNKNOWN})
        self.assertTrue(all("sudo" in i["evidence"] for i in items.values()))
        self.assertEqual(code, 2)

    def test_anchor_missing_label(self):
        host = FakeHost()
        host.cmds[("pfctl", "-a", "com.apple/020.local.leak-guard", "-sr")] = (0, RULES_020.replace('label "leak-guard-stun"', 'label "x"'), "")
        _, items, _ = run_json(host, "--only", "pf.020")
        self.assertIn("leak-guard-stun", items["pf.020"]["evidence"])

    def test_user_rule_must_match_console_uid(self):
        host = FakeHost(uid=502)
        _, items, _ = run_json(host, "--only", "pf.020")
        self.assertIn("当前用户是 502", items["pf.020"]["evidence"])

    def test_table_contents(self):
        host = FakeHost()
        host.cmds[("pfctl", "-a", "com.apple/010.local.claude-direct-wall", "-t", "claude_wall_targets", "-T", "show")] = (0, "", "")
        _, items, _ = run_json(host, "--only", "pf.010")
        self.assertIn("为空", items["pf.010"]["evidence"])
        host = FakeHost()
        host.cmds[("pfctl", "-a", "com.apple/011.local.claude-net-wall", "-t", "claude_wall_nets", "-T", "show")] = (0, "   160.79.104.0/21\n", "")
        _, items, _ = run_json(host, "--only", "pf.011")
        self.assertEqual(items["pf.011"]["status"], mc.FAIL)

    def test_rule_file_permissions_and_symlink(self):
        host = FakeHost()
        host.stats["/etc/pf.anchors/local.leak-guard"] = Stat(501, 0o100644)
        _, items, _ = run_json(host, "--only", "pf.020")
        self.assertIn("root:644", items["pf.020"]["evidence"])
        host = FakeHost()
        host.links.add("/usr/local/libexec/leak-guard-loader")
        _, items, _ = run_json(host, "--only", "loader.020")
        self.assertIn("符号链接", items["loader.020"]["evidence"])

    def test_pf_conf_missing_load_line(self):
        host = FakeHost()
        host.files["/etc/pf.conf"] = PF_CONF.replace('load anchor "com.apple/020', '# load anchor "com.apple/020')
        _, items, _ = run_json(host, "--only", "pf.conf")
        self.assertIn("020", items["pf.conf"]["evidence"])
        self.assertEqual(items["pf.conf"]["status"], mc.FAIL)

    def test_pf_disabled(self):
        host = FakeHost()
        host.cmds[("pfctl", "-si")] = (0, "Status: Disabled\n", "")
        _, items, _ = run_json(host, "--only", "pf.enabled")
        self.assertEqual(items["pf.enabled"]["status"], mc.FAIL)


class DaemonTests(unittest.TestCase):
    def test_daemon_not_loaded_or_bad_exit(self):
        host = FakeHost()
        host.cmds[("launchctl", "print", "system/local.leak-guard")] = (113, "", "Could not find service\n")
        _, items, _ = run_json(host, "--only", "daemon.020")
        self.assertIn("未装载", items["daemon.020"]["evidence"])
        host = FakeHost()
        host.cmds[("launchctl", "print", "system/local.net-guard-watch")] = (0, "\tlast exit code = 6\n", "")
        _, items, _ = run_json(host, "--only", "daemon.watch")
        self.assertIn("退出码 6", items["daemon.watch"]["evidence"])

    def test_updater_accepts_conservative_stop_exit_1(self):
        _, items, _ = run_json(FakeHost(), "--only", "daemon.updater")
        self.assertEqual(items["daemon.updater"]["status"], mc.PASS)

    def test_plist_missing(self):
        host = FakeHost()
        del host.stats["/Library/LaunchDaemons/local.ipv6-guard.plist"]
        _, items, _ = run_json(host, "--only", "daemon.ipv6")
        self.assertIn("不存在", items["daemon.ipv6"]["evidence"])

    def test_watch_stale_or_not_ok(self):
        host = FakeHost(now=NOW + dt.timedelta(minutes=10))
        _, items, _ = run_json(host, "--only", "watch.fresh")
        self.assertIn("秒前", items["watch.fresh"]["evidence"])
        self.assertEqual(items["watch.fresh"]["status"], mc.FAIL)
        host = FakeHost()
        host.cmds[("cat", "/var/db/NetGuardWatch/last")] = (0, "2026-10-22T22:36:23Z\tWARN\tTUN 异常\n", "")
        _, items, _ = run_json(host, "--only", "watch.fresh")
        self.assertIn("WARN", items["watch.fresh"]["evidence"])

    def test_updater_old_or_no_applied(self):
        host = FakeHost(now=NOW + dt.timedelta(hours=7))
        _, items, _ = run_json(host, "--only", "updater.fresh")
        self.assertIn("小时前", items["updater.fresh"]["evidence"])
        self.assertEqual(items["updater.fresh"]["status"], mc.FAIL)
        host = FakeHost()
        host.cmds[("tail", "-n", "200", HOME + "/Library/Application Support/ClaudeDirectWallUpdater/stdout.log")] = (0, "not json\n", "")
        _, items, _ = run_json(host, "--only", "updater.fresh")
        self.assertIn("没有 APPLIED", items["updater.fresh"]["evidence"])

    def test_claude_wall_exit_codes(self):
        host = FakeHost()
        host.cmds[(HOME + "/.local/bin/claude-wall", "status")] = (6, "守护: 最近一次结果是 900 秒前\n", "")
        _, items, _ = run_json(host, "--only", "tool.claude_wall")
        self.assertIn("退出码 6", items["tool.claude_wall"]["evidence"])
        host = FakeHost()
        del host.stats[HOME + "/.local/bin/claude-wall"]
        _, items, _ = run_json(host, "--only", "tool.claude_wall")
        self.assertIn("不存在", items["tool.claude_wall"]["evidence"])


class SystemTests(unittest.TestCase):
    def test_unsupported_platform(self):
        status, evidence = mc.check_os(FakeHost(macos=False), {}, {})
        self.assertEqual(status, mc.FAIL)
        self.assertIn("linux", evidence)

    def test_timezone_in_asia(self):
        host = FakeHost()
        host.cmds[("readlink", "/etc/localtime")] = (0, "/var/db/timezone/zoneinfo/Asia/Shanghai\n", "")
        _, items, _ = run_json(host, "--only", "sys.timezone")
        self.assertEqual(items["sys.timezone"]["status"], mc.FAIL)

    def test_timezone_of_a_non_chinese_asian_exit_is_fine(self):
        # Tokyo/Singapore/Seoul nodes are legitimate exits; only mainland China / Hong Kong / Macau are rejected.
        host = FakeHost()
        host.cmds[("readlink", "/etc/localtime")] = (0, "/var/db/timezone/zoneinfo/Asia/Tokyo\n", "")
        _, items, _ = run_json(host, "--only", "sys.timezone")
        self.assertEqual(items["sys.timezone"]["status"], mc.PASS)
        host.cmds[("readlink", "/etc/localtime")] = (0, "/var/db/timezone/zoneinfo/Asia/Hong_Kong\n", "")
        _, items, _ = run_json(host, "--only", "sys.timezone")
        self.assertEqual(items["sys.timezone"]["status"], mc.FAIL)

    def test_chrome_in_user_applications_is_checked_not_skipped(self):
        host = FakeHost()
        del host.stats["/Applications/Google Chrome.app"]
        host.stats[HOME + "/Applications/Google Chrome.app"] = Stat(501, 0o40755)
        _, items, _ = run_json(host, "--only", "chrome.policy")
        self.assertEqual(items["chrome.policy"]["status"], mc.PASS)

    def test_ipv6_guard_program_is_read_from_the_plist_and_must_be_root_owned(self):
        host = FakeHost()
        _, items, _ = run_json(host, "--only", "ipv6.script")
        self.assertEqual(items["ipv6.script"]["status"], mc.PASS)
        host.stats["/usr/local/libexec/ipv6-guard.sh"] = Stat(501, 0o100755)  # user-owned: a root daemon must not run it
        _, items, _ = run_json(host, "--only", "ipv6.script")
        self.assertEqual(items["ipv6.script"]["status"], mc.FAIL)
        self.assertIn("迁移IPv6守护", items["ipv6.script"]["evidence"])
        host.stats["/usr/local/libexec/ipv6-guard.sh"] = Stat(0, 0o100775)  # group-writable: still no
        _, items, _ = run_json(host, "--only", "ipv6.script")
        self.assertEqual(items["ipv6.script"]["status"], mc.FAIL)
        # The old hand-installed guard: plist points into the user's home → ❌ whatever parameters say (there is no
        # parameter for the script path any more; the check reads what the daemon really executes).
        old = IPV6_GUARD_PLIST.replace(b"/usr/local/libexec/ipv6-guard.sh", (HOME + "/.local/bin/ipv6-guard.sh").encode()).replace(b"/var/log/ipv6-guard", (HOME + "/.ipv6-guard").encode())
        host.bytes["/Library/LaunchDaemons/local.ipv6-guard.plist"] = old
        host.stats["/usr/local/libexec/ipv6-guard.sh"] = Stat(0, 0o100755)
        _, items, _ = run_json(host, "--only", "ipv6.script")
        self.assertEqual(items["ipv6.script"]["status"], mc.FAIL)
        with self.assertRaises(ValueError):
            run(host, "--param", "ipv6_guard_script=/bin/sh")  # the bypass parameter no longer exists

    def test_privileged_commands_go_through_the_root_helper_when_installed(self):
        host = FakeHost()
        host.stats[mc.PF_HELPER] = Stat(0, 0o100755)
        host.cmds[("sudo", "-n", mc.PF_HELPER, "info")] = (0, "Status: Enabled\n", "")
        rc, out, _ = mc.Host.priv(host, ["pfctl", "-si"])
        self.assertEqual(out, "Status: Enabled\n")
        self.assertEqual(mc.helper_argv(["pfctl", "-a", "com.apple/010.local.claude-direct-wall", "-sr"]), ["rules", "com.apple/010.local.claude-direct-wall"])
        self.assertIsNone(mc.helper_argv(["pfctl", "-a", "com.apple/999.other", "-sr"]))  # not one of the kit's anchors
        self.assertEqual(mc.helper_argv(["pfctl", "-a", "com.apple/011.local.claude-net-wall", "-t", "t", "-T", "show"]), ["table", "com.apple/011.local.claude-net-wall", "t"])
        self.assertEqual(mc.helper_argv(["cat", "/var/db/NetGuardWatch/last"]), ["watch-last"])
        self.assertEqual(mc.helper_argv(["profiles", "-P"]), ["profiles"])
        self.assertIsNone(mc.helper_argv(["pfctl", "-d"]))

    def test_language_is_info_either_way(self):
        host = FakeHost()
        host.cmds[("defaults", "read", "-g", "AppleLanguages")] = (0, '(\n    "en-US",\n    "zh-Hans-US"\n)\n', "")
        code, items, _ = run_json(host, "--only", "sys.language")
        self.assertEqual(items["sys.language"]["status"], mc.INFO)
        self.assertIn("0 分", items["sys.language"]["evidence"])
        self.assertEqual(code, 0)


class CliTests(unittest.TestCase):
    def test_unknown_only_id_errors(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                run(FakeHost(), "--only", "nope")

    def test_unknown_param_errors(self):
        with self.assertRaises(ValueError):
            run(FakeHost(), "--param", "bogus=1")

    def test_list_param_override(self):
        host = FakeHost()
        host.cmds[("networksetup", "-getdnsservers", "Ethernet")] = (0, "127.0.0.1\n", "")
        host.cmds[("networksetup", "-getinfo", "Ethernet")] = (0, "IPv6: Off\n", "")
        _, items, _ = run_json(host, "--only", "dns.system,net.ipv6_off", "--param", "network_services=Ethernet")
        self.assertEqual(items["dns.system"]["status"], mc.PASS)
        self.assertEqual(items["net.ipv6_off"]["status"], mc.PASS)

    def test_local_params_file_keeps_list_types(self):
        local = Path(MANIFEST).parent / "mirror.params.json"
        local.write_text(json.dumps({"network_services": ["Ethernet"]}), encoding="utf-8")
        try:
            host = FakeHost()
            host.cmds[("networksetup", "-getdnsservers", "Ethernet")] = (0, "127.0.0.1\n", "")
            _, items, data = run_json(host, "--only", "dns.system")
            self.assertEqual(data["params"]["network_services"], ["Ethernet"])
            self.assertEqual(items["dns.system"]["status"], mc.PASS)
            local.write_text(json.dumps({"nope": 1}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    run(FakeHost(), "--only", "os")
        finally:
            local.unlink()

    def test_json_shape(self):
        code, out = run(FakeHost(), "--json", "--only", "os")
        data = json.loads(out)
        self.assertEqual(set(data), {"generated_utc", "manifest", "platform", "params", "note", "exit", "items"})
        self.assertEqual(data["items"][0]["id"], "os")
        self.assertNotIn("next", data["items"][0])

    def test_missing_params_file_is_announced_in_the_header(self):
        # A stranger's machine without mirror.params.json is compared against the reference node; the text and the
        # JSON both say so up front instead of leaving it to next_step.
        local = Path(MANIFEST).parent / "mirror.params.json"
        self.assertFalse(local.exists())
        code, out = run(FakeHost(), "--only", "os")
        self.assertIn("提醒: 仓库根目录没有 mirror.params.json", out.splitlines()[1])
        _, jout = run(FakeHost(), "--json", "--only", "os")
        self.assertIn("mirror.params.json", json.loads(jout)["note"])
        local.write_text(json.dumps({"exit_node": "丽萨美国"}), encoding="utf-8")
        try:
            code, out = run(FakeHost(), "--only", "os")
            self.assertNotIn("提醒:", out)
        finally:
            local.unlink()

    def test_failing_item_carries_next(self):
        host = FakeHost()
        host.apis["/configs"]["mode"] = "global"
        code, out = run(host, "--only", "clash.mode")
        self.assertIn("下一步:", out)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
