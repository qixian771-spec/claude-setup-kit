#!/usr/bin/env python3
"""Reconcile this Mac against manifest.json. Read-only: never writes, loads or restarts anything.

Exit codes: 0 all components PASS; 1 at least one FAIL; 2 no FAIL but at least one
component could not be determined (needs sudo, tool missing, network unreachable, --no-network).
INFO and MANUAL components never affect the exit code. Runs on the macOS system Python (3.9+).
"""
import argparse
import datetime as dt
import http.client
import ipaddress
import json
import os
import base64
import plistlib
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

try:
    import pwd  # Unix only
except ImportError:  # Windows
    pwd = None

ROOT = Path(__file__).resolve().parent.parent
PASS, FAIL, UNKNOWN, INFO, MANUAL = "PASS", "FAIL", "UNKNOWN", "INFO", "MANUAL"
MARK = {PASS: "✅", FAIL: "❌", UNKNOWN: "❓", INFO: "ℹ️", MANUAL: "👉"}


class HostError(Exception):
    """A query could not be made (missing tool, timeout, unreadable file)."""


class NeedSudo(HostError):
    """A privileged query was refused; rerun with sudo."""


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_path)


def platform_key():
    # Only macOS and Windows have component tables; anything else (Linux CI runners) uses the macOS set.
    # CLAUDE_SETUP_KIT_PLATFORM is for tests/CI only: it pins the tables to one platform.
    forced = os.environ.get("CLAUDE_SETUP_KIT_PLATFORM")
    if forced in ("darwin", "win32"):
        return forced
    return "win32" if sys.platform.startswith("win") else "darwin"


class Host:
    """Every query the checks make goes through here, so tests can replace it."""

    def __init__(self):
        self.calls = []
        self.platform = platform_key()

    def run(self, argv, timeout=20):
        self.calls.append(list(argv))
        try:
            # C locale: tools print English and /bin/sh (bash 3.2) parses scripts predictably.
            env = dict(os.environ, LC_ALL="C")
            proc = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, env=env)
        except FileNotFoundError:
            raise HostError("缺少工具: %s" % argv[0])
        except subprocess.TimeoutExpired:
            raise HostError("超时: %s" % " ".join(argv))
        return proc.returncode, proc.stdout, proc.stderr

    def priv(self, argv, timeout=20):
        if os.geteuid() == 0:
            return self.run(argv, timeout)
        rc, out, err = self.run(["sudo", "-n"] + list(argv), timeout)
        if rc != 0 and ("password" in err or "a terminal is required" in err or err.startswith("sudo:")):
            raise NeedSudo("需要 sudo: %s" % " ".join(argv))
        return rc, out, err

    def read_text(self, path):
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise HostError("读不到 %s: %s" % (path, exc.strerror))

    def lstat(self, path):
        try:
            return os.lstat(path)
        except OSError:
            return None

    def is_link(self, path):
        return os.path.islink(path)

    def read_bytes(self, path):
        try:
            return Path(path).read_bytes()
        except OSError as exc:
            raise HostError("读不到 %s: %s" % (path, exc.strerror))

    def http_get(self, url, timeout=10):
        parts = urlsplit(url)
        if parts.scheme == "unix":
            conn = UnixHTTPConnection(parts.path, timeout)
            target = "/"
            headers = {}
        elif parts.scheme == "pipe":
            # Clash Verge on Windows serves the controller on a named pipe; see pipe_api().
            raise HostError("pipe:// 走 pipe_api")
        elif parts.scheme == "http":
            conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
            target = parts.path or "/"
            headers = {}
            secret = os.environ.get("MIHOMO_SECRET")
            if secret:
                headers["Authorization"] = "Bearer " + secret
        else:
            raise HostError("不支持的 API 地址: %s" % url)
        return conn, target, headers

    def pipe_api(self, name, path, timeout=10):
        """Minimal HTTP/1.1 over a Windows named pipe (\\\\.\\pipe\\<name>)."""
        pipe = "\\\\.\\pipe\\" + name
        request = ("GET %s HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n" % path).encode("ascii")
        try:
            with open(pipe, "r+b", buffering=0) as handle:
                handle.write(request)
                raw = b""
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    raw += chunk
                    if b"\r\n\r\n" in raw:
                        head, _, body = raw.partition(b"\r\n\r\n")
                        m = re.search(rb"(?i)content-length:\s*(\d+)", head)
                        if m and len(body) >= int(m.group(1)):
                            break
        except OSError as exc:
            raise HostError("命名管道不可达 %s: %s" % (pipe, exc))
        head, _, body = raw.partition(b"\r\n\r\n")
        status = head.split(b" ", 2)
        if len(status) < 2 or status[1] != b"200":
            raise HostError("API %s 返回 %s" % (path, status[1].decode("ascii", "replace") if len(status) > 1 else "?"))
        return json.loads(body.decode("utf-8", "replace"))

    def ps(self, script, tag=None, timeout=60):
        """Run a PowerShell snippet (UTF-8 output, errors stop); returns stdout. `tag` only names it for tests."""
        prelude = "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n$ProgressPreference='SilentlyContinue'\n$ErrorActionPreference='Stop'\n"
        encoded = base64.b64encode((prelude + script).encode("utf-16le")).decode("ascii")
        rc, out, err = self.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-EncodedCommand", encoded], timeout=timeout)
        if rc != 0:
            raise HostError("PowerShell 失败（%s）: %s" % (tag or "脚本", clixml_error(err) or "rc=%s" % rc))
        return out

    def api(self, base, path, timeout=10):
        if base.startswith("pipe://"):
            return self.pipe_api(base[len("pipe://"):], path, timeout)
        conn, prefix, headers = self.http_get(base, timeout)
        try:
            conn.request("GET", path if prefix == "/" else prefix.rstrip("/") + path, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", "replace")
        except (OSError, http.client.HTTPException) as exc:
            raise HostError("API 不可达 %s: %s" % (base, exc))
        finally:
            conn.close()
        if resp.status != 200:
            raise HostError("API %s 返回 %s" % (path, resp.status))
        return json.loads(body)

    def console_uid(self):
        if pwd is None:
            return None  # Windows: identity is the SID, see winchecks
        if "SUDO_UID" in os.environ:
            return int(os.environ["SUDO_UID"])
        return os.getuid()

    def home(self):
        if pwd is None:
            return Path(os.environ["USERPROFILE"])
        return Path(pwd.getpwuid(self.console_uid()).pw_dir)

    def console_name(self):
        if pwd is None:
            return os.environ.get("USERNAME", "")
        return pwd.getpwuid(self.console_uid()).pw_name

    def env(self, name):
        value = os.environ.get(name)
        if not value:
            raise HostError("环境变量 %%%s%% 没有设置" % name)
        return value

    def now(self):
        return dt.datetime.now(dt.timezone.utc)


def clixml_error(stderr):
    """PowerShell writes errors as CLIXML on stderr; return the first human-readable error line."""
    text = stderr.strip()
    if not text:
        return ""
    if text.startswith("#< CLIXML"):
        parts = re.findall(r'<S S="Error">(.*?)</S>', text, re.S)
        text = " ".join(parts) if parts else text
        text = text.replace("_x000D__x000A_", "\n").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text.strip().splitlines()[0][:160]


def expand(host, path):
    path = str(path)
    if path.startswith("~/"):
        return str(host.home() / path[2:])
    m = re.match(r"^%([A-Z_]+)%/(.*)$", path)
    if m:  # Windows %APPDATA%/... style entries
        return os.path.join(host.env(m.group(1)), m.group(2).replace("/", os.sep))
    return path


# ---------------------------------------------------------------- checks
# Each check returns (status, evidence). Raising HostError/NeedSudo yields UNKNOWN.

def check_os(host, p, a):
    if host.platform == "darwin":
        rc, out, _ = host.run(["sw_vers", "-productVersion"])
        return PASS, "macOS %s" % out.strip()
    if host.platform == "win32":
        out = host.ps("(Get-CimInstance Win32_OperatingSystem) | ForEach-Object { $_.Caption + ' ' + $_.Version }", tag="os")
        return PASS, out.strip()
    return FAIL, "不支持的平台: %s" % host.platform


def check_clash_api(host, p, a):
    data = host.api(p["clash_api"], "/version")
    return PASS, "mihomo %s（%s）" % (data.get("version"), p["clash_api"])


def check_clash_mode(host, p, a):
    mode = host.api(p["clash_api"], "/configs").get("mode")
    expect = a.get("expect", "rule")
    return (PASS if mode == expect else FAIL), "mode=%s（要求 %s）" % (mode, expect)


def check_clash_tun(host, p, a):
    cfg = host.api(p["clash_api"], "/configs")
    tun = cfg.get("tun") or {}
    problems = []
    if not tun.get("enable"):
        problems.append("tun.enable=false")
    if tun.get("device") != p["tun_device"]:
        problems.append("device=%s" % tun.get("device"))
    addrs = tun.get("inet4-address") or []
    if not any(x.split("/")[0] == p["tun_inet4"] for x in addrs):
        problems.append("inet4=%s" % addrs)
    if cfg.get("ipv6"):
        problems.append("ipv6=true")
    hijack = tun.get("dns-hijack") or []
    if not any("53" in h for h in hijack):
        problems.append("dns-hijack=%s" % hijack)
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "device=%s inet4=%s ipv6=false dns-hijack=%s" % (tun["device"], addrs, hijack)


def check_clash_exit_group(host, p, a):
    group = p["exit_group"]
    data = host.api(p["clash_api"], "/proxies/" + quote(group))
    members = data.get("all") or []
    problems = []
    if data.get("type") != "Selector":
        problems.append("type=%s（要求 Selector）" % data.get("type"))
    bad = [m for m in members if m.upper() in ("DIRECT", "REJECT")]
    if bad:
        problems.append("成员含 %s" % bad)
    if data.get("now") != p["exit_node"]:
        problems.append("当前=%s（要求 %s）" % (data.get("now"), p["exit_node"]))
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "%s: Selector now=%s 成员=%s" % (group, data.get("now"), members)


def check_clash_rules(host, p, a):
    rules = host.api(p["clash_api"], "/rules").get("rules") or []
    group = p["exit_group"]
    have = {(r.get("type"), str(r.get("payload")), r.get("proxy")) for r in rules}
    missing = []
    for suffix in p["claude_suffixes"]:
        if ("DomainSuffix", suffix, group) not in have:
            missing.append("DOMAIN-SUFFIX,%s,%s" % (suffix, group))
    for port in p["stun_ports"]:
        if ("DstPort", str(port), "REJECT") not in have:
            missing.append("DST-PORT,%s,REJECT" % port)
    if ("GeoSite", "CN", "DIRECT") not in have:
        missing.append("GEOSITE,CN,DIRECT")
    if ("Match", "", group) not in have:
        missing.append("MATCH,%s" % group)
    leaks = [r for r in rules if r.get("proxy") == "DIRECT"
             and any(s in str(r.get("payload")) for s in p["claude_suffixes"])]
    if leaks:
        missing.append("Claude 域名走 DIRECT: %s" % [r.get("payload") for r in leaks])
    if missing:
        return FAIL, "缺/错: " + "; ".join(missing)
    return PASS, "%d 条规则，必需项齐全" % len(rules)


def check_clash_google_exit(host, p, a):
    group = p["google_group"]
    try:
        data = host.api(p["clash_api"], "/proxies/" + quote(group))
    except HostError as exc:
        if "返回 404" in str(exc):
            return FAIL, "分组 %s 不存在" % group
        raise
    members = data.get("all") or []
    problems = []
    if data.get("type") != "Selector":
        problems.append("type=%s（要求 Selector）" % data.get("type"))
    if any(m.upper() in ("DIRECT", "REJECT") for m in members):
        problems.append("成员含 DIRECT/REJECT")
    if data.get("now") == p["exit_node"]:
        problems.append("当前选中的是 Claude 出口 %s（Google 会把它判成中国；换成别的节点）" % p["exit_node"])
    rules = host.api(p["clash_api"], "/rules").get("rules") or []
    def index(pred):
        return next((i for i, r in enumerate(rules) if pred(r)), None)
    for suffix in p["google_suffixes"]:
        i = index(lambda r: r.get("type") == "DomainSuffix" and r.get("payload") == suffix and r.get("proxy") == group)
        if i is None:
            problems.append("缺 DOMAIN-SUFFIX,%s,%s" % (suffix, group))
    geo = index(lambda r: r.get("type") == "GeoSite" and str(r.get("payload")).lower() == "geolocation-!cn")
    first_google = index(lambda r: r.get("proxy") == group)
    if geo is not None and first_google is not None and first_google > geo:
        problems.append("Google 规则排在 GEOSITE,geolocation-!cn 之后，会被它抢走")
    for exact in ("storage.googleapis.com", "fonts.googleapis.com", "fonts.gstatic.com"):
        j = index(lambda r: r.get("type") == "Domain" and r.get("payload") == exact)
        if j is not None and first_google is not None and j > first_google:
            problems.append("%s 的精确规则排在 Google 后缀规则之后（Claude 的资源会跟着走 Google 出口）" % exact)
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "%s: Selector now=%s 成员=%s；%d 条 Google 规则在 GEOSITE 之前" % (group, data.get("now"), members, len(p["google_suffixes"]))


def _dns_block(text):
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.rstrip() == "dns:"), None)
    if start is None:
        raise HostError("运行配置里没有 dns: 段")
    block = []
    for line in lines[start + 1:]:
        if line and not line[0].isspace():
            break
        block.append(line)
    return block


def check_clash_dns_config(host, p, a):
    text = host.read_text(expand(host, p["clash_runtime_config"]))
    block = _dns_block(text)
    joined = "\n".join(block)
    group = p["exit_group"]
    problems = []

    def key(name):
        m = re.search(r"^\s*%s:\s*(.*)$" % re.escape(name), joined, re.M)
        return m.group(1).strip().strip("'\"") if m else None

    if key("enable") != "true":
        problems.append("enable!=true")
    if key("listen") != "127.0.0.1:53":
        problems.append("listen=%s" % key("listen"))
    if key("enhanced-mode") != "fake-ip":
        problems.append("enhanced-mode=%s" % key("enhanced-mode"))
    if key("ipv6") != "false":
        problems.append("dns.ipv6=%s" % key("ipv6"))
    if re.search(r"^\s*fallback:", joined, re.M):
        problems.append("存在 fallback")

    def entries(name):
        out, grab = [], False
        for line in block:
            if re.match(r"^\s*%s:\s*$" % re.escape(name), line):
                grab = True
                continue
            if grab:
                m = re.match(r"^\s*-\s*(.+)$", line)
                if m:
                    out.append(m.group(1).strip().strip("'\""))
                else:
                    break
        return out

    default = entries("default-nameserver")
    if not default or not all(re.match(r"https://\d+\.\d+\.\d+\.\d+/", d) for d in default):
        problems.append("default-nameserver 不是字面 IP 的 DoH: %s" % default)
    ns = entries("nameserver")
    if not ns or not all(n.endswith("#" + group) for n in ns):
        problems.append("nameserver 未全部经 #%s: %s" % (group, ns))
    policy = {}
    for i, line in enumerate(block):
        m = re.match(r"^\s*'?(\+\.[\w.-]+)'?:\s*$", line)
        if m and i + 1 < len(block):
            v = re.match(r"^\s*-\s*(.+)$", block[i + 1])
            policy[m.group(1)] = v.group(1).strip().strip("'\"") if v else ""
    for suffix in p["claude_suffixes"]:
        v = policy.get("+." + suffix, "")
        if not (v.startswith("https://") and v.endswith("#" + group)):
            problems.append("nameserver-policy +.%s=%s" % (suffix, v or "缺"))
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "listen=127.0.0.1:53 fake-ip, %d 条 nameserver 经 #%s, Claude 策略齐全, 无 fallback" % (len(ns), group)


def check_tun_iface(host, p, a):
    rc, out, _ = host.run(["ifconfig", p["tun_device"]])
    if rc != 0:
        return FAIL, "接口 %s 不存在" % p["tun_device"]
    if not re.search(r"^\s*inet %s\b" % re.escape(p["tun_inet4"]), out, re.M):
        return FAIL, "%s 没有地址 %s" % (p["tun_device"], p["tun_inet4"])
    return PASS, "%s inet %s" % (p["tun_device"], p["tun_inet4"])


def _dig(host, extra, name, rtype="A", server="127.0.0.1"):
    rc, out, _ = host.run(["dig", "+short", "+time=3", "+tries=1"] + extra + ["@" + server, name, rtype])
    if rc != 0:
        raise HostError("dig 失败 rc=%s (%s)" % (rc, name))
    return [l.strip() for l in out.splitlines() if l.strip()]


def check_dns_local53(host, p, a):
    net = ipaddress.ip_network(p["fake_ip_prefix"])
    results = {}
    for label, extra in (("udp", []), ("tcp", ["+tcp"])):
        answers = _dig(host, extra, p["probe_domain"])
        ips = [x for x in answers if re.match(r"^\d+\.\d+\.\d+\.\d+$", x)]
        results[label] = ips
    bad = {k: v for k, v in results.items() if not v or not all(ipaddress.ip_address(i) in net for i in v)}
    if bad:
        return FAIL, "127.0.0.1:53 应答不是 fake-ip: %s" % bad
    rc, out, _ = host.run(["dscacheutil", "-q", "host", "-a", "name", p["probe_domain"]])
    sys_ips = re.findall(r"ip_address:\s*(\S+)", out)
    if not sys_ips or not all(ipaddress.ip_address(i) in net for i in sys_ips):
        return FAIL, "系统解析 %s 没走 Clash: %s" % (p["probe_domain"], sys_ips)
    return PASS, "udp=%s tcp=%s 系统解析=%s（均在 %s）" % (results["udp"], results["tcp"], sys_ips, net)


def check_system_dns(host, p, a):
    accept = set(p["system_dns_accept"])
    found = {}
    for svc in p["network_services"]:
        rc, out, _ = host.run(["networksetup", "-getdnsservers", svc])
        if rc != 0:
            raise HostError("networksetup -getdnsservers %s 失败" % svc)
        values = [l.strip() for l in out.splitlines() if re.match(r"^[\d.:a-fA-F]+$", l.strip())]
        found[svc] = values
    bad = {s: v for s, v in found.items() if not v or not set(v) <= accept}
    if bad:
        return FAIL, "不在接受列表 %s: %s" % (sorted(accept), bad)
    return PASS, "%s（接受值; 真实路径由 dns.local53 与 pf.020 保证）" % found


def _hardware_device(host, service):
    rc, out, _ = host.run(["networksetup", "-listallhardwareports"])
    m = re.search(r"Hardware Port: %s\nDevice: (\S+)" % re.escape(service), out)
    return m.group(1) if m else None


def check_ipv6_off(host, p, a):
    problems, seen = [], []
    for svc in p["network_services"]:
        rc, out, _ = host.run(["networksetup", "-getinfo", svc])
        m = re.search(r"^IPv6: (.+)$", out, re.M)
        state = m.group(1).strip() if m else "?"
        seen.append("%s IPv6=%s" % (svc, state))
        if state != "Off":
            problems.append("%s IPv6=%s" % (svc, state))
        dev = _hardware_device(host, svc)
        if dev:
            rc, out, _ = host.run(["ifconfig", dev])
            globals6 = [x for x in re.findall(r"inet6 (\S+)", out) if not x.startswith("fe80")]
            if globals6:
                problems.append("%s 有全局 IPv6 %s" % (dev, globals6))
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, ", ".join(seen) + "，接口无全局 IPv6"


def check_pf_enabled(host, p, a):
    rc, out, _ = host.priv(["pfctl", "-si"])
    if "Status: Enabled" not in out:
        return FAIL, "PF 未启用"
    m = re.search(r"Status: Enabled for (.+?)\s{2,}", out)
    return PASS, "Enabled for %s" % (m.group(1) if m else "?")


def check_pf_anchor(host, p, a):
    st = host.lstat(a["file"])
    problems = []
    if st is None:
        problems.append("规则文件不存在 %s" % a["file"])
    elif host.is_link(a["file"]) or st.st_uid != 0 or (st.st_mode & 0o777) != 0o644:
        problems.append("规则文件权限不是 root:644")
    rc, out, _ = host.priv(["pfctl", "-a", a["anchor"], "-sr"])
    missing = [l for l in a["labels"] if 'label "%s"' % l not in out]
    if missing:
        problems.append("锚点缺规则 label %s" % missing)
    if a.get("user_rule"):
        uids = {int(x) for x in re.findall(r"user = (\d+)", out)}
        want = host.console_uid()
        if uids != {want}:
            problems.append("user 规则 UID=%s，当前用户是 %s" % (sorted(uids), want))
    table = a.get("table")
    detail = ""
    if table:
        rc, tout, _ = host.priv(["pfctl", "-a", a["anchor"], "-t", table["name"], "-T", "show"])
        values = {l.strip() for l in tout.splitlines() if l.strip()}
        if table["mode"] == "nonempty" and not values:
            problems.append("表 %s 为空" % table["name"])
        if table["mode"] == "equals" and values != set(table["values"]):
            problems.append("表 %s=%s（要求 %s）" % (table["name"], sorted(values), table["values"]))
        detail = " 表 %s=%s" % (table["name"], sorted(values))
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "%d 条 label 齐全%s" % (len(a["labels"]), detail)


def check_pf_conf_loads(host, p, a):
    text = host.read_text("/etc/pf.conf")
    active = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    missing = [l for l in a["lines"] if l not in active]
    if missing:
        return FAIL, "pf.conf 缺: %s" % missing
    return PASS, "%d 条 load anchor 行齐全" % len(a["lines"])


def _file_problem(host, path, mode, uid=0):
    st = host.lstat(path)
    if st is None:
        return "%s 不存在" % path
    if host.is_link(path):
        return "%s 是符号链接" % path
    if uid is not None and st.st_uid != uid:
        return "%s 属主 uid=%s（要求 %s）" % (path, st.st_uid, uid)
    if mode is not None and (st.st_mode & 0o777) != int(mode, 8):
        return "%s 权限 %o（要求 %s）" % (path, st.st_mode & 0o777, mode)
    return None


def check_root_file(host, p, a):
    items = [a] + list(a.get("also") or [])
    problems = [x for x in (_file_problem(host, i["path"], i["mode"]) for i in items) if x]
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "root 持有，权限正确: %s" % [i["path"] for i in items]


def check_user_file(host, p, a):
    path = expand(host, a["path"])
    st = host.lstat(path)
    if st is None:
        return FAIL, "%s 不存在" % path
    if a.get("executable") and not (st.st_mode & 0o111):
        return FAIL, "%s 不可执行" % path
    return PASS, path


def check_launch_daemon(host, p, a):
    label = p[a["label_param"]] if "label_param" in a else a["label"]
    plist = "/Library/LaunchDaemons/%s.plist" % label
    problem = _file_problem(host, plist, "644")
    if problem:
        return FAIL, problem
    rc, out, _ = host.run(["launchctl", "print", "system/" + label])
    if rc != 0:
        return FAIL, "%s 未装载（launchctl print rc=%s）" % (label, rc)
    m = re.search(r"last exit code = (-?\d+)", out)
    code = int(m.group(1)) if m else None
    accept = a.get("accept_exit", [0])
    if m and code not in accept:
        return FAIL, "%s 最近退出码 %s（接受 %s）" % (label, code, accept)
    return PASS, "已装载，最近退出码 %s" % (code if m else "未运行过")


def _parse_iso(value):
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value)


def check_watch_fresh(host, p, a):
    rc, out, err = host.priv(["cat", a["dir"] + "/last"])
    if rc != 0:
        return FAIL, "读不到 %s/last: %s" % (a["dir"], err.strip())
    parts = out.strip().split("\t")
    if len(parts) < 2:
        return FAIL, "last 格式异常: %r" % out
    age = (host.now() - _parse_iso(parts[0])).total_seconds()
    if age > p["watch_max_age_s"]:
        return FAIL, "最近记录 %.0f 秒前（上限 %s）" % (age, p["watch_max_age_s"])
    if parts[1] != "OK":
        return FAIL, "最近状态 %s: %s" % (parts[1], parts[2] if len(parts) > 2 else "")
    return PASS, "%s OK（%.0f 秒前）" % (parts[0], age)


def check_updater_fresh(host, p, a):
    problem = _file_problem(host, a["package"] + "/sha256.json", "644")
    if problem:
        return FAIL, problem
    log = expand(host, a["state_log"])
    rc, out, _ = host.run(["tail", "-n", "200", log])
    if rc != 0:
        return FAIL, "读不到 %s" % log
    latest = None
    for line in out.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("status") == "APPLIED" and rec.get("finished_utc"):
            latest = rec["finished_utc"]
    if latest is None:
        return FAIL, "日志里没有 APPLIED 记录"
    age_h = (host.now() - _parse_iso(latest)).total_seconds() / 3600
    if age_h > p["updater_max_age_h"]:
        return FAIL, "最近 APPLIED 在 %.1f 小时前（上限 %s）" % (age_h, p["updater_max_age_h"])
    return PASS, "最近 APPLIED %s（%.1f 小时前）" % (latest, age_h)


def check_chrome_policy(host, p, a):
    if host.lstat(p["chrome_app"]) is None:
        return INFO, "未安装 Chrome（%s），跳过" % p["chrome_app"]
    want = p["chrome_policy"]
    user = host.console_name()
    for path in ("/Library/Managed Preferences/com.google.Chrome.plist",
                 "/Library/Managed Preferences/%s/com.google.Chrome.plist" % user):
        if host.lstat(path) is None:
            continue
        try:
            data = plistlib.loads(host.read_bytes(path))
        except (HostError, ValueError) as exc:
            return FAIL, "%s 无法解析: %s" % (path, exc)
        bad = {k: data.get(k) for k, v in want.items() if data.get(k) != v}
        if bad:
            return FAIL, "%s 值不对: %s" % (path, bad)
        rc, out, _ = host.priv(["profiles", "-P"])
        if p["chrome_profile_identifier"] not in out:
            return FAIL, "%s 存在但没有描述文件支撑（会被系统清掉）" % path
        return PASS, "%s 由描述文件 %s 管理，%s" % (path, p["chrome_profile_identifier"], want)
    rc, out, _ = host.priv(["profiles", "-P"])
    if p["chrome_profile_identifier"] in out:
        return FAIL, "描述文件已装但 Managed Preferences 里没有 Chrome 策略（重启或重新登录后再查）"
    return FAIL, "没有 Chrome 管理策略（Managed Preferences 无文件，描述文件未安装）"


def check_manual(host, p, a):
    return MANUAL, a["text"]


def check_claude_wall(host, p, a):
    path = expand(host, a["path"])
    st = host.lstat(path)
    if st is None or not (st.st_mode & 0o111):
        return FAIL, "%s 不存在或不可执行" % path
    rc, out, err = host.run([path, "status"], timeout=60)
    tail = (out.strip().splitlines() or [""])[-1]
    if rc == 6:
        return FAIL, "退出码 6（自检守护异常）: %s" % tail
    if rc != 0:
        return FAIL, "退出码 %s: %s" % (rc, (err.strip() or tail))
    return PASS, " / ".join(l.strip() for l in out.strip().splitlines() if ":" in l)[:160]


def _trace(host, p):
    rc, out, err = host.run(["curl", "-sS", "-m", "15", p["trace_url"]], timeout=20)
    if rc != 0:
        raise HostError("curl %s 失败 rc=%s %s" % (p["trace_url"], rc, err.strip()[:80]))
    data = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    if "ip" not in data:
        raise HostError("trace 没有 ip 字段")
    return data


def check_exit_ip(host, p, a):
    data = _trace(host, p)
    if data.get("loc") in p["exit_country_forbid"]:
        return FAIL, "出口 %s 在 %s（禁止 %s）" % (data["ip"], data.get("loc"), p["exit_country_forbid"])
    return PASS, "出口 %s loc=%s colo=%s" % (data["ip"], data.get("loc"), data.get("colo"))


def check_dns_upstream(host, p, a):
    data = _trace(host, p)
    who = _dig(host, ["CH"], "whoami.cloudflare", "TXT", "1.1.1.1")
    who_ip = who[0].strip('"') if who else ""
    resolver = _dig(host, [], "o-o.myaddr.l.google.com", "TXT", "ns1.google.com")
    resolver_ip = next((x.strip('"') for x in resolver if "edns" not in x), "")
    problems = []
    if who_ip != data["ip"]:
        problems.append("DNS 出口 %s ≠ HTTPS 出口 %s" % (who_ip or "无应答", data["ip"]))
    ranges = [ipaddress.ip_network(r) for r in p["dns_upstream_ranges"][p["dns_upstream_provider"]]]
    try:
        inside = any(ipaddress.ip_address(resolver_ip) in r for r in ranges)
    except ValueError:
        inside = False
    if not inside:
        problems.append("解析器 %s 不属于 %s" % (resolver_ip or "无应答", p["dns_upstream_provider"]))
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "DNS 出口 %s = HTTPS 出口；解析器 %s ∈ %s" % (who_ip, resolver_ip, p["dns_upstream_provider"])


def check_timezone(host, p, a):
    rc, out, _ = host.run(["readlink", "/etc/localtime"])
    zone = out.strip().split("zoneinfo/")[-1] if "zoneinfo/" in out else out.strip()
    if any(zone.startswith(x) for x in p["timezone_forbid_prefix"]):
        return FAIL, "时区 %s" % zone
    return PASS, "时区 %s" % zone


def check_language(host, p, a):
    rc, out, _ = host.run(["defaults", "read", "-g", "AppleLanguages"])
    langs = re.findall(r'"([^"]+)"', out)
    first = langs[0] if langs else "?"
    note = "ippure 浏览器语言项 +24 分" if first.lower().startswith("zh") else "ippure 浏览器语言项 0 分"
    return INFO, "语言顺序 %s；首位 %s（%s；可选步骤，不改也算通过）" % (langs, first, note)


CHECKS = {name[len("check_"):]: fn for name, fn in globals().items() if name.startswith("check_")}
CHECKS["macos"] = check_os  # older manifests
NETWORK_CHECKS = {"exit_ip", "dns_upstream"}


def platform_checks(platform):
    """Check table for a platform: Windows variants (scripts/winchecks.py) override the common ones."""
    table = dict(CHECKS)
    if platform == "win32":
        import winchecks
        # When this file runs as __main__ a plain `import mirror_check` would be a second
        # module object with its own HostError class; bind winchecks to this one.
        winchecks.mc = sys.modules[__name__]
        table.update(winchecks.CHECKS)
    return table


# ---------------------------------------------------------------- runner

def load_manifest(path, platform=None):
    """Manifest with only this platform's components; params merged with params_<platform> (win32 → params_win)."""
    platform = platform or platform_key()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != 1:
        raise ValueError("manifest format 不支持: %s" % data.get("format"))
    ids = [c["id"] for c in data["components"]]
    if len(ids) != len(set(ids)):
        raise ValueError("manifest 有重复的 id")
    table = platform_checks(platform)
    comps = [c for c in data["components"] if platform in c.get("platforms", ["darwin"])]
    for c in comps:
        if c["check"] not in table:
            raise ValueError("%s: 平台 %s 没有 check %s" % (c["id"], platform, c["check"]))
    params = dict(data["params"])
    if platform == "win32":
        params.update(data.get("params_win", {}))
    return {"format": 1, "name": data.get("name"), "platform": platform, "params": params,
            "components": comps, "steps": data.get("steps_win" if platform == "win32" else "steps", []),
            "all_components": data["components"]}


def run_component(host, params, comp, network=True):
    fn = platform_checks(host.platform)[comp["check"]]
    if comp["check"] in NETWORK_CHECKS and not network:
        status, evidence = UNKNOWN, "--no-network，未实测"
    else:
        try:
            status, evidence = fn(host, params, comp.get("args") or {})
        except NeedSudo as exc:
            status, evidence = UNKNOWN, "%s（用 sudo 重跑）" % exc
        except HostError as exc:
            status, evidence = UNKNOWN, str(exc)
    item = {"id": comp["id"], "layer": comp["layer"], "title": comp["title"],
            "status": status, "evidence": evidence}
    if status not in (PASS, INFO):
        item["next"] = comp.get("next_win", comp.get("next", "")) if host.platform == "win32" else comp.get("next", "")
    return item


def exit_code(items):
    statuses = {i["status"] for i in items}
    if FAIL in statuses:
        return 1
    if UNKNOWN in statuses:
        return 2
    return 0


def render(items, params, code, platform="darwin"):
    lines = ["# mirror-check  平台=%s 出口分组=%s 节点=%s TUN=%s" % (platform, params["exit_group"], params["exit_node"], params["tun_device"]), ""]
    for i in items:
        lines.append("%s %-16s %s" % (MARK[i["status"]], i["id"], i["title"]))
        lines.append("    %s" % i["evidence"])
        if i.get("next"):
            lines.append("    下一步: %s" % i["next"])
    counts = {s: sum(1 for i in items if i["status"] == s) for s in MARK}
    lines.append("")
    lines.append("合计: ✅ %d  ❌ %d  ❓ %d  ℹ️ %d  👉 %d  → exit %d" % (
        counts[PASS], counts[FAIL], counts[UNKNOWN], counts[INFO], counts[MANUAL], code))
    return "\n".join(lines)


def apply_overrides(params, overrides):
    for item in overrides:
        if "=" not in item:
            raise ValueError("--param 需要 key=value: %s" % item)
        key, value = item.split("=", 1)
        if key not in params:
            raise ValueError("未知参数 %s" % key)
        if isinstance(params[key], list):
            params[key] = [v for v in value.split(",") if v]
        elif isinstance(params[key], int) and not isinstance(params[key], bool):
            params[key] = int(value)
        else:
            params[key] = value
    return params


def main(argv=None, host=None):
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles default to GBK; the tables use ✅/❌ and Chinese.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    ap.add_argument("--json", action="store_true", help="输出 JSON 而不是表格")
    ap.add_argument("--only", help="只跑这些 id（逗号分隔）")
    ap.add_argument("--no-network", action="store_true", help="跳过出口/DNS 实测（结果记为 ❓）")
    ap.add_argument("--param", action="append", default=[], help="覆盖 manifest params，如 exit_node=节点名")
    ap.add_argument("--platform", choices=("darwin", "win32"), help="（测试/CI 用）按这个平台选组件，默认自动")
    args = ap.parse_args(argv)
    host = host or Host()
    if args.platform:
        host.platform = args.platform
    manifest = load_manifest(args.manifest, host.platform)
    params = dict(manifest["params"])
    local = Path(args.manifest).parent / "mirror.params.json"
    if local.exists():
        # Per-machine overrides (git-ignored); same keys as manifest params.
        params = apply_overrides(params, ["%s=%s" % (k, v) for k, v in json.loads(local.read_text(encoding="utf-8-sig")).items()])
    params = apply_overrides(params, args.param)
    comps = manifest["components"]
    if args.only:
        wanted = set(args.only.split(","))
        unknown = wanted - {c["id"] for c in comps}
        if unknown:
            ap.error("未知 id: %s" % sorted(unknown))
        comps = [c for c in comps if c["id"] in wanted]
    items = [run_component(host, params, c, network=not args.no_network) for c in comps]
    code = exit_code(items)
    if args.json:
        print(json.dumps({"generated_utc": host.now().isoformat(), "manifest": args.manifest, "platform": host.platform,
                          "params": params, "exit": code, "items": items}, ensure_ascii=False, indent=2))
    else:
        print(render(items, params, code, host.platform))
    return code


if __name__ == "__main__":
    sys.exit(main())
