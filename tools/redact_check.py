#!/usr/bin/env python3
"""Fail if anything that looks like a credential, node address or private path is in the repo.

Scans every tracked text file (or the paths given). Exit 0 = clean, 1 = hits, 2 = error.
Allowed by design: RFC-reserved and documentation addresses, public resolvers, Anthropic's
published networks, placeholders like {{NODE1_SERVER}}, and lines listed in tools/redact_allow.txt.
"""
import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW_FILE = ROOT / "tools" / "redact_allow.txt"
SKIP_DIRS = {".git", "build", "node_modules", "__pycache__", ".venv", "vendor"}
SKIP_SUFFIXES = {".png", ".webp", ".jpg", ".mobileconfig"}

PUBLIC_OK = [ipaddress.ip_network(n) for n in (
    "1.1.1.1/32", "1.0.0.1/32", "8.8.8.8/32", "8.8.4.4/32", "223.5.5.5/32", "223.6.6.6/32",
    "114.114.114.114/32", "119.29.29.29/32", "160.79.104.0/21", "2607:6bc0::/32", "2400:cb00::/32",
    "2606:4700::/32", "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
    "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22",
    "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2803:f800::/32", "2405:b500::/32", "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
    "64:ff9b::/96",  # NAT64 well-known prefix
)]
IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?(?![\w.])")
# Any colon-rich hex token; ipaddress decides whether it is really an address.
IPV6 = re.compile(r"(?<![\w:.])([0-9a-fA-F:]*:[0-9a-fA-F:]*:[0-9a-fA-F:]*)(?:/(\d{1,3}))?(?![\w:])")
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
LONG_SECRET = re.compile(r"(?<![\w/+=])[A-Za-z0-9+_=-]{40,}(?![\w/+=])")  # no "/" so paths never match
# key: value pairs whose value looks like real material (long, has digits), not code identifiers.
KEYWORDS = re.compile(r"(?i)\b(password|passwd|uuid|public-key|short-id|private[-_ ]?key|secret|token)\b\s*[:=]\s*['\"]?(?=[^\s'\"{}#,]*\d)([A-Za-z0-9+/_.=-]{12,})")
HOME_PATH = re.compile(r"/Users/(?!Shared\b|tester\b)[A-Za-z0-9._-]+")  # /Users/tester is the test fixture home
PLACEHOLDER = re.compile(r"\{\{[A-Z0-9_]+\}\}")
SHA_HEX = re.compile(r"\b[0-9a-f]{40,64}\b")


def ip_is_private_or_allowed(text, prefix):
    try:
        net = ipaddress.ip_network("%s/%s" % (text, prefix) if prefix is not None else text, strict=False)
    except ValueError:
        return True
    if not net.is_global or net.is_multicast or net.prefixlen == 0:
        return True  # private, loopback, link-local, multicast, TEST-NET, documentation ranges, catch-all
    return any(ok.version == net.version and net.subnet_of(ok) for ok in PUBLIC_OK)


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("git ls-files 失败: %s" % exc)
    return [ROOT / p.decode("utf-8") for p in out.split(b"\0") if p]


def scan_line(line):
    hits = []
    stripped = PLACEHOLDER.sub("", line)
    for m in IPV4.finditer(stripped):
        if not ip_is_private_or_allowed(m.group(1), m.group(2)):
            hits.append("公网 IPv4 %s" % m.group(0))
    for m in IPV6.finditer(stripped):
        try:
            ipaddress.ip_address(m.group(1))
        except ValueError:
            continue
        if not ip_is_private_or_allowed(m.group(1), m.group(2)):
            hits.append("公网 IPv6 %s" % m.group(0))
    for m in UUID.finditer(stripped):
        hits.append("UUID %s" % m.group(0))
    for m in KEYWORDS.finditer(stripped):
        hits.append("疑似凭据 %s=…" % m.group(1))
    for m in LONG_SECRET.finditer(stripped):
        token = m.group(0)
        identifier_like = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token) and ("_" in token or token.islower())
        if (not SHA_HEX.fullmatch(token) and not token.startswith(("http", "/")) and not identifier_like
                and sum(c.isdigit() for c in token) >= 2 and sum(c.isalpha() for c in token) >= 2):
            hits.append("长随机串 %s…" % token[:12])
    for m in HOME_PATH.finditer(stripped):
        hits.append("私人路径 %s" % m.group(0))
    return hits


def load_allow():
    if not ALLOW_FILE.exists():
        return set()
    return {l.strip() for l in ALLOW_FILE.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles default to a code page that cannot print the Chinese messages.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    paths = [Path(p).resolve() for p in (argv or sys.argv[1:])] or tracked_files()
    allow = load_allow()
    total = 0
    for path in paths:
        if any(part in SKIP_DIRS for part in path.parts) or path.suffix in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(ROOT)) if ROOT in path.parents else str(path)
        for number, line in enumerate(lines, 1):
            if line.strip() in allow or "redact-allow" in line:
                continue
            for hit in scan_line(line):
                print("%s:%d: %s" % (rel, number, hit))
                total += 1
    print("redact_check: %d 处命中" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
