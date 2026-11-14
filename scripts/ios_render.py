#!/usr/bin/env python3
"""Render iOS防漏配置 (V2Box / Shadowrocket / Stash & Karing) from --nodes JSON or local Clash Verge.

Reuses `templates/clash-profile.template.yaml` and `scripts/render.py` so iOS devices share the exact
same primary exit node, optional Google split exit node, IPv6-off posture, STUN block, and 116-rule routing table.

Outputs (written ONLY into --out <dir> with mode 0700/0600 on Unix; never into the git repo):
  - v2box-xray.json         Xray-core client JSON for V2Box clipboard import (UseIPv4 + ::/0 block)
  - v2box-uris.txt          Standard share URIs fallback
  - stash-karing-clash.yaml Clash Meta YAML for Stash / Karing (PROCESS-NAME stripped)
  - shadowrocket.conf       Shadowrocket configuration (ipv6=false + DEST-PORT STUN REJECT)

Never prints node servers, IPs, ports, UUIDs, passwords, or keys to stdout/stderr.
"""
import argparse
import base64
import datetime as dt
import html
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
VENDOR = ROOT / "system" / "updater" / "vendor"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))

from ruamel.yaml import YAML  # noqa: E402
import mirror_check as mc  # noqa: E402
import render  # noqa: E402

FORBIDDEN_SELECTORS = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "GLOBAL"}
XRAY_SUPPORTED_TYPES = {"vless", "trojan", "ss", "shadowsocks", "socks5", "socks", "vmess"}
TARGET_FILES = {
    "v2box": "v2box-xray.json",
    "uris": "v2box-uris.txt",
    "clash": "stash-karing-clash.yaml",
    "shadowrocket": "shadowrocket.conf",
}


def load_group_names(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    params = dict(manifest["params"])
    local = Path(manifest_path).parent / "mirror.params.json"
    if local.is_file():
        local_data = json.loads(local.read_text(encoding="utf-8-sig"))
        for key in ("exit_group", "google_group", "clash_api"):
            if key in local_data:
                params[key] = local_data[key]
    return params


def _find_clash_runtime_path(host, manifest):
    comp = next((c for c in manifest.get("components", []) if c.get("id") == "clash.dns"), None)
    if comp:
        raw_path = (comp.get("args") or {}).get("runtime_config")
        if raw_path:
            p = Path(mc.expand(host, raw_path))
            if p.is_file():
                return p
    if host.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            cand = Path(appdata) / "io.github.clash-verge-rev.clash-verge-rev" / "clash-verge.yaml"
            if cand.is_file():
                return cand
    else:
        cand = Path.home() / "Library" / "Application Support" / "io.github.clash-verge-rev.clash-verge-rev" / "clash-verge.yaml"
        if cand.is_file():
            return cand
    return None


def extract_proxies_from_local_clash(manifest_path):
    host = mc.Host()
    manifest = mc.load_manifest(str(manifest_path), host.platform)
    params = manifest["params"]
    api = params["clash_api"]
    exit_group = params["exit_group"]
    google_group = params["google_group"]

    try:
        exit_data = host.api(api, "/proxies/" + quote(exit_group), timeout=4)
    except mc.HostError as exc:
        raise render.RenderError(
            "无法从本机 Clash 读取分组『%s』（%s）；请确认 Clash Verge 已运行并导入配置，或改用 --nodes <节点.json>"
            % (exit_group, exc)
        )
    node1_name = str(exit_data.get("now") or "").strip()
    if not node1_name or node1_name.upper() in FORBIDDEN_SELECTORS:
        raise render.RenderError("本机 Clash『%s』当前选中节点无效: %r" % (exit_group, node1_name))

    node2_name = None
    try:
        g_data = host.api(api, "/proxies/" + quote(google_group), timeout=4)
        g_now = str(g_data.get("now") or "").strip()
        if g_now and g_now != node1_name and g_now.upper() not in FORBIDDEN_SELECTORS:
            node2_name = g_now
    except mc.HostError:
        pass

    runtime_path = _find_clash_runtime_path(host, manifest)
    if not runtime_path:
        raise render.RenderError("找不到本机 Clash 运行时配置 clash-verge.yaml，请改用 --nodes <节点.json>")

    yaml = YAML(typ="safe")
    parsed = yaml.load(runtime_path.read_text(encoding="utf-8-sig")) or {}
    proxies_list = list(parsed.get("proxies") or [])
    by_name = {str(item.get("name", "")): dict(item) for item in proxies_list if isinstance(item, dict) and item.get("name")}

    if node1_name not in by_name or (node2_name and node2_name not in by_name):
        profiles_yaml = runtime_path.parent / "profiles.yaml"
        if profiles_yaml.is_file():
            pdata = yaml.load(profiles_yaml.read_text(encoding="utf-8-sig")) or {}
            cur_uid = pdata.get("current")
            for item in (pdata.get("items") or []):
                if isinstance(item, dict) and item.get("uid") == cur_uid and item.get("file"):
                    prof_file = runtime_path.parent / "profiles" / str(item["file"])
                    if prof_file.is_file():
                        prof_data = yaml.load(prof_file.read_text(encoding="utf-8-sig")) or {}
                        for pr in (prof_data.get("proxies") or []):
                            if isinstance(pr, dict) and pr.get("name"):
                                by_name.setdefault(str(pr["name"]), dict(pr))

    if node1_name not in by_name:
        raise render.RenderError("在 %s 中找不到节点 %r 的完整参数，请改用 --nodes <节点.json>" % (runtime_path.name, node1_name))

    node_input = {"NODE1_PROXY": by_name[node1_name]}
    if node2_name and node2_name in by_name:
        node_input["NODE2_PROXY"] = by_name[node2_name]
    return node_input


def build_clash_model(node_values, exit_group, google_group):
    tmpl = (ROOT / "templates" / "clash-profile.template.yaml").read_text(encoding="utf-8")
    values = {"EXIT_GROUP": exit_group, "GOOGLE_GROUP": google_group, **node_values}
    rendered = render.render_text(tmpl, values, "templates/clash-profile.template.yaml")
    yaml = YAML(typ="safe")
    model = yaml.load(rendered) or {}
    return rendered, model


def build_stash_karing_yaml(rendered_yaml, has_google_split):
    header = (
        "# claude-setup-kit iOS Stash / Karing 配置（由 clash-profile.template.yaml 自动转换）\n"
        "# 模式：%s；已内置 ipv6: false、116 条分流与 STUN REJECT 规则（已剔除桌面 PROCESS-NAME）。\n"
        % ("双节点智能分流" if has_google_split else "单出口共用")
    )
    kept = []
    for line in rendered_yaml.splitlines(keepends=True):
        if line.lstrip().startswith("- PROCESS-NAME,"):
            continue
        kept.append(line)
    return header + "".join(kept)


def _xray_stream_settings(proxy, ptype):
    net = str(proxy.get("network") or "tcp").strip().lower()
    stream = {"network": net}
    if net == "ws":
        ws = proxy.get("ws-opts") or {}
        ws_cfg = {"path": str(ws.get("path") or "/")}
        headers = ws.get("headers") or {}
        if isinstance(headers, dict) and headers:
            ws_cfg["headers"] = {str(k): str(v) for k, v in headers.items()}
        stream["wsSettings"] = ws_cfg
    elif net == "xhttp":
        xh = proxy.get("xhttp-opts") or {}
        stream["xhttpSettings"] = {
            "host": str(xh.get("host") or ""),
            "path": str(xh.get("path") or "/"),
            "mode": str(xh.get("mode") or "auto"),
        }

    ropts = proxy.get("reality-opts")
    if isinstance(ropts, dict) and ropts.get("public-key"):
        stream["security"] = "reality"
        # Deliberately omit Clash-specific support-x25519mlkem768 so Xray-core JSON parsers never choke on unknown keys.
        stream["realitySettings"] = {
            "serverName": str(proxy.get("servername") or proxy.get("sni") or proxy["server"]),
            "fingerprint": str(proxy.get("client-fingerprint") or "chrome"),
            "publicKey": str(ropts.get("public-key") or ""),
            "shortId": str(ropts.get("short-id") or ""),
            "spiderX": "",
        }
    elif proxy.get("tls") or ptype == "trojan":
        stream["security"] = "tls"
        tls_cfg = {
            "serverName": str(proxy.get("servername") or proxy.get("sni") or proxy["server"]),
            "allowInsecure": bool(proxy.get("skip-cert-verify", False)),
        }
        if proxy.get("client-fingerprint"):
            tls_cfg["fingerprint"] = str(proxy["client-fingerprint"])
        stream["tlsSettings"] = tls_cfg
    return stream


def proxy_to_xray_outbound(proxy, tag):
    ptype = str(proxy.get("type") or "").strip().lower()
    if ptype in render.FORBIDDEN_PROXY_TYPES:
        raise render.RenderError("%s 类型不能是 %s" % (tag, ptype))
    if ptype not in XRAY_SUPPORTED_TYPES:
        raise render.RenderError(
            "V2Box (Xray-core) 暂不支持协议 %r；请改用 VLESS / Trojan / Shadowsocks / SOCKS5 / VMess，或在 iOS 使用 Karing/Stash 导入 stash-karing-clash.yaml"
            % ptype
        )
    server = str(proxy["server"])
    port = int(proxy["port"])

    if ptype == "vless":
        user = {"id": str(proxy["uuid"]), "encryption": "none"}
        if proxy.get("flow"):
            user["flow"] = str(proxy["flow"])
        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {"vnext": [{"address": server, "port": port, "users": [user]}]},
            "streamSettings": _xray_stream_settings(proxy, ptype),
        }

    if ptype == "trojan":
        return {
            "tag": tag,
            "protocol": "trojan",
            "settings": {"servers": [{"address": server, "port": port, "password": str(proxy["password"])}]},
            "streamSettings": _xray_stream_settings(proxy, ptype),
        }

    if ptype in ("ss", "shadowsocks"):
        return {
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": server,
                        "port": port,
                        "method": str(proxy["cipher"]),
                        "password": str(proxy["password"]),
                        "uot": True,
                    }
                ]
            },
        }

    if ptype in ("socks5", "socks"):
        srv = {"address": server, "port": port}
        if proxy.get("username") is not None:
            srv["users"] = [{"user": str(proxy["username"]), "pass": str(proxy.get("password") or "")}]
        return {"tag": tag, "protocol": "socks", "settings": {"servers": [srv]}}

    # vmess
    out = {
        "tag": tag,
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": server,
                    "port": port,
                    "users": [
                        {
                            "id": str(proxy["uuid"]),
                            "alterId": int(proxy.get("alterId") or 0),
                            "security": str(proxy.get("cipher") or "auto"),
                        }
                    ],
                }
            ]
        },
    }
    if proxy.get("tls") or proxy.get("network") not in (None, "", "tcp"):
        out["streamSettings"] = _xray_stream_settings(proxy, ptype)
    return out


def _map_rule_target(raw_target, exit_group, google_group):
    if raw_target == exit_group:
        return "claude-exit"
    if raw_target == google_group:
        return "google-exit"
    if raw_target == "DIRECT":
        return "direct"
    if raw_target == "REJECT":
        return "block"
    return "claude-exit"


def build_v2box_xray_json(model, exit_group, google_group, node1, node2):
    outbounds = [proxy_to_xray_outbound(node1, "claude-exit")]
    if node2:
        outbounds.append(proxy_to_xray_outbound(node2, "google-exit"))
    outbounds.extend([
        {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}},
        {"tag": "block", "protocol": "blackhole"},
        {"tag": "dns-out", "protocol": "dns"},
    ])

    rules = [
        {"type": "field", "ip": ["1.1.1.1/32", "1.0.0.1/32"], "outboundTag": "claude-exit"},
        {"type": "field", "ip": ["223.5.5.5/32"], "outboundTag": "direct"},
        {"type": "field", "port": 53, "outboundTag": "dns-out"},
    ]

    stun_ports = []
    domain_batches = []  # preserve exact order between exit-group rules and google-group rules

    def push_domain(tag, pattern):
        if domain_batches and domain_batches[-1][0] == tag:
            if pattern not in domain_batches[-1][1]:
                domain_batches[-1][1].append(pattern)
        else:
            domain_batches.append((tag, [pattern]))

    cidr_v4 = {}
    for raw in model.get("rules") or []:
        parts = [p.strip() for p in str(raw).split(",")]
        if len(parts) < 2:
            continue
        rtype = parts[0].upper()
        if rtype in ("PROCESS-NAME", "IP-CIDR6", "MATCH", "GEOSITE", "GEOIP"):
            continue
        payload = parts[1]
        raw_target = parts[2] if len(parts) >= 3 else exit_group
        tag = _map_rule_target(raw_target, exit_group, google_group)

        if rtype == "DST-PORT" and tag == "block":
            if payload not in stun_ports:
                stun_ports.append(payload)
        elif rtype == "DOMAIN":
            push_domain(tag, "full:" + payload)
        elif rtype == "DOMAIN-SUFFIX":
            push_domain(tag, "domain:" + payload)
        elif rtype == "DOMAIN-KEYWORD":
            push_domain(tag, payload)
        elif rtype == "IP-CIDR":
            cidr_v4.setdefault(tag, [])
            if payload not in cidr_v4[tag]:
                cidr_v4[tag].append(payload)

    if stun_ports:
        rules.append({"type": "field", "port": ",".join(stun_ports), "outboundTag": "block"})
    rules.append({"type": "field", "ip": ["::/0"], "outboundTag": "block"})

    for tag, domains in domain_batches:
        rules.append({"type": "field", "domain": domains, "outboundTag": tag})
    for tag, cidrs in cidr_v4.items():
        rules.append({"type": "field", "ip": cidrs, "outboundTag": tag})

    # Bundled V2Box geosite/geoip only reliably cover standard `private` and `cn` (avoid geosite:anthropic/category-ntp).
    rules.append({"type": "field", "domain": ["geosite:private", "geosite:cn"], "outboundTag": "direct"})
    rules.append({"type": "field", "ip": ["geoip:private", "geoip:cn"], "outboundTag": "direct"})
    rules.append({"type": "field", "network": "tcp,udp", "outboundTag": "claude-exit"})

    label_nodes = "%s+%s" % (node1["name"], node2["name"]) if node2 else node1["name"]
    cfg = {
        "remarks": "Claude防漏智能分流(%s)" % label_nodes,
        "log": {"loglevel": "warning"},
        "dns": {
            "queryStrategy": "UseIPv4",
            "servers": [
                {"address": "223.5.5.5", "port": 53, "domains": ["geosite:cn"]},
                "https://1.1.1.1/dns-query",
            ],
        },
        "inbounds": [
            {
                "tag": "tun-in",
                "port": 10808,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            }
        ],
        "outbounds": outbounds,
        "routing": {"domainStrategy": "IPIfNonMatch", "rules": rules},
    }
    return json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"


def _node_uri_label(index, name):
    raw_name = str(name)
    if raw_name.startswith("Claude"):
        return raw_name
    if index == 0:
        return "Claude专用-" + raw_name
    if index == 1:
        return "Claude谷歌-" + raw_name
    return raw_name


def proxy_to_uri(proxy, display_name=None):
    ptype = str(proxy.get("type") or "").strip().lower()
    raw_label = str(display_name or proxy["name"])
    name = quote(raw_label, safe="")
    server = str(proxy["server"])
    host_fmt = "[%s]" % server if ":" in server else server
    port = int(proxy["port"])

    if ptype == "vless":
        q = [("encryption", "none")]
        if proxy.get("flow"):
            q.append(("flow", str(proxy["flow"])))
        ropts = proxy.get("reality-opts")
        if isinstance(ropts, dict) and ropts.get("public-key"):
            q.append(("security", "reality"))
            q.append(("sni", str(proxy.get("servername") or proxy.get("sni") or server)))
            q.append(("fp", str(proxy.get("client-fingerprint") or "chrome")))
            q.append(("pbk", str(ropts.get("public-key") or "")))
            if ropts.get("short-id") is not None:
                q.append(("sid", str(ropts.get("short-id") or "")))
        elif proxy.get("tls"):
            q.append(("security", "tls"))
            if proxy.get("servername") or proxy.get("sni"):
                q.append(("sni", str(proxy.get("servername") or proxy.get("sni"))))
            if proxy.get("client-fingerprint"):
                q.append(("fp", str(proxy["client-fingerprint"])))
        net = str(proxy.get("network") or "tcp").lower()
        q.append(("type", net))
        if net == "ws":
            ws = proxy.get("ws-opts") or {}
            if ws.get("path"):
                q.append(("path", str(ws["path"])))
            hdr = (ws.get("headers") or {}).get("Host")
            if hdr:
                q.append(("host", str(hdr)))
        elif net == "xhttp":
            xh = proxy.get("xhttp-opts") or {}
            if xh.get("host"):
                q.append(("host", str(xh["host"])))
            if xh.get("path"):
                q.append(("path", str(xh["path"])))
            if xh.get("mode"):
                q.append(("mode", str(xh["mode"])))
        return "vless://%s@%s:%d?%s#%s" % (proxy["uuid"], host_fmt, port, urlencode(q), name)

    if ptype == "trojan":
        q = []
        sni = proxy.get("sni") or proxy.get("servername")
        if sni:
            q.append(("sni", str(sni)))
        if proxy.get("skip-cert-verify"):
            q.append(("allowInsecure", "1"))
        suffix = ("?" + urlencode(q)) if q else ""
        return "trojan://%s@%s:%d%s#%s" % (quote(str(proxy["password"]), safe=""), host_fmt, port, suffix, name)

    if ptype in ("ss", "shadowsocks"):
        raw = "%s:%s" % (proxy["cipher"], proxy["password"])
        b64 = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        return "ss://%s@%s:%d#%s" % (b64, host_fmt, port, name)

    if ptype in ("socks5", "socks"):
        if proxy.get("username") is not None:
            raw = "%s:%s" % (proxy["username"], proxy.get("password") or "")
            b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
            return "socks://%s@%s:%d#%s" % (b64, host_fmt, port, name)
        return "socks://%s:%d#%s" % (host_fmt, port, name)

    if ptype == "vmess":
        ws = proxy.get("ws-opts") or {}
        payload = {
            "v": "2",
            "ps": raw_label,
            "add": server,
            "port": str(port),
            "id": str(proxy["uuid"]),
            "aid": str(proxy.get("alterId") or 0),
            "scy": str(proxy.get("cipher") or "auto"),
            "net": str(proxy.get("network") or "tcp"),
            "type": "none",
            "host": str((ws.get("headers") or {}).get("Host") or ""),
            "path": str(ws.get("path") or ""),
            "tls": "tls" if proxy.get("tls") else "",
            "sni": str(proxy.get("servername") or proxy.get("sni") or ""),
        }
        b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
        return "vmess://" + b64

    return ""


def build_v2box_uris(proxies):
    lines = [
        "# V2Box 节点导入链接（Configs → + → Scan QR Code 或 Import v2ray uri from clipboard）"
    ]
    for idx, p in enumerate(proxies):
        uri = proxy_to_uri(p, display_name=_node_uri_label(idx, p["name"]))
        if uri:
            lines.append(uri)
    return "\n".join(lines) + "\n"


def _shadowrocket_proxy_line(proxy):
    name = str(proxy["name"]).replace("=", "_")
    ptype = str(proxy.get("type") or "").strip().lower()
    server = str(proxy["server"])
    port = int(proxy["port"])

    if ptype == "vless":
        parts = ["vless", server, str(port), "uuid=%s" % proxy["uuid"]]
        if proxy.get("flow"):
            parts.append("flow=%s" % proxy["flow"])
        ropts = proxy.get("reality-opts")
        if isinstance(ropts, dict) and ropts.get("public-key"):
            parts.extend([
                "security=reality",
                "pbk=%s" % ropts.get("public-key"),
                "sid=%s" % (ropts.get("short-id") or ""),
                "sni=%s" % (proxy.get("servername") or proxy.get("sni") or server),
                "fingerprint=%s" % (proxy.get("client-fingerprint") or "chrome"),
            ])
        elif proxy.get("tls"):
            parts.extend([
                "tls=true",
                "sni=%s" % (proxy.get("servername") or proxy.get("sni") or server),
            ])
        if proxy.get("udp", True):
            parts.append("udp-relay=1")
        return "%s = %s" % (name, ", ".join(parts))

    if ptype == "trojan":
        parts = ["trojan", server, str(port), "password=%s" % proxy["password"]]
        if proxy.get("sni") or proxy.get("servername"):
            parts.append("sni=%s" % (proxy.get("sni") or proxy.get("servername")))
        parts.append("skip-cert-verify=%s" % ("true" if proxy.get("skip-cert-verify") else "false"))
        return "%s = %s" % (name, ", ".join(parts))

    if ptype in ("ss", "shadowsocks"):
        parts = ["ss", server, str(port), "encrypt-method=%s" % proxy["cipher"], "password=%s" % proxy["password"]]
        return "%s = %s" % (name, ", ".join(parts))

    if ptype in ("socks5", "socks"):
        parts = ["socks5", server, str(port)]
        if proxy.get("username") is not None:
            parts.append("username=%s" % proxy["username"])
            parts.append("password=%s" % (proxy.get("password") or ""))
        return "%s = %s" % (name, ", ".join(parts))

    if ptype == "vmess":
        parts = [
            "vmess", server, str(port),
            "username=%s" % proxy["uuid"],
            "method=%s" % (proxy.get("cipher") or "auto"),
        ]
        if proxy.get("tls"):
            parts.append("tls=true")
        return "%s = %s" % (name, ", ".join(parts))

    if ptype in ("hysteria2", "hy2"):
        parts = ["hysteria2", server, str(port), "password=%s" % proxy["password"]]
        if proxy.get("sni"):
            parts.append("sni=%s" % proxy["sni"])
        return "%s = %s" % (name, ", ".join(parts))

    raise render.RenderError("Shadowrocket 暂未映射协议: %s" % ptype)


def build_shadowrocket_conf(model, exit_group, google_group, proxies, has_google_split):
    proxy_lines = [_shadowrocket_proxy_line(p) for p in proxies]
    names = [str(p["name"]).replace("=", "_") for p in proxies]
    group_lines = ["%s = select, %s" % (exit_group, ", ".join(names))]
    if has_google_split and len(names) >= 2:
        group_lines.append("%s = select, %s" % (google_group, ", ".join(names[1:])))

    rule_lines = []
    for raw in model.get("rules") or []:
        parts = [p.strip() for p in str(raw).split(",")]
        if len(parts) < 2:
            continue
        rtype = parts[0].upper()
        if rtype in ("PROCESS-NAME", "IP-CIDR6"):
            continue
        if rtype == "GEOSITE":
            if parts[1].upper() == "CN" and len(parts) >= 3:
                rule_lines.append("DOMAIN-SUFFIX,cn,%s" % parts[2])
            continue
        if rtype == "DST-PORT":
            rule_lines.append("DEST-PORT,%s,%s" % (parts[1], parts[2]))
        elif rtype == "MATCH":
            rule_lines.append("FINAL,%s" % parts[1])
        else:
            rule_lines.append(",".join(parts))

    return "\n".join([
        "[General]",
        "bypass-system = true",
        "skip-proxy = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, localhost, *.local",
        "tun-excluded-routes = 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 255.255.255.255/32",
        "dns-server = https://1.1.1.1/dns-query",
        "fallback-dns-server = https://223.5.5.5/dns-query",
        "ipv6 = false",
        "prefer-ipv6 = false",
        "dns-direct-system = false",
        "udp-policy-not-supported-behaviour = REJECT",
        "stun-response-ip = 0.0.0.0",
        "stun-response-ipv6 = ::",
        "",
        "[Proxy]",
        *proxy_lines,
        "",
        "[Proxy Group]",
        *group_lines,
        "",
        "[Rule]",
        *rule_lines,
        "",
    ])


def copy_to_clipboard(text):
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        return "macOS 剪贴板（pbcopy）"
    if sys.platform.startswith("win"):
        subprocess.run(["clip"], input=text.encode("utf-16le"), check=True)
        return "Windows 剪贴板（clip）"
    raise render.RenderError("当前系统不支持自动写入剪贴板: %s" % sys.platform)


_QR_ECC_L = {
    1: (7, 1, 19, 0, 0), 2: (10, 1, 34, 0, 0), 3: (15, 1, 55, 0, 0),
    4: (20, 1, 80, 0, 0), 5: (26, 1, 108, 0, 0), 6: (18, 2, 68, 0, 0),
    7: (20, 2, 78, 0, 0), 8: (24, 2, 97, 0, 0), 9: (30, 2, 116, 0, 0),
    10: (18, 2, 68, 2, 69), 11: (20, 4, 81, 0, 0), 12: (24, 2, 92, 2, 93),
    13: (26, 4, 107, 0, 0), 14: (30, 3, 115, 1, 116), 15: (22, 5, 87, 1, 88),
}
_QR_ALIGN = {
    1: (), 2: (6, 18), 3: (6, 22), 4: (6, 26), 5: (6, 30), 6: (6, 34),
    7: (6, 22, 38), 8: (6, 24, 42), 9: (6, 26, 46), 10: (6, 28, 50),
    11: (6, 30, 54), 12: (6, 32, 58), 13: (6, 34, 62), 14: (6, 26, 46, 66), 15: (6, 26, 48, 70),
}
_QR_EXP = [0] * 512
_QR_LOG = [0] * 256
_qr_x = 1
for _qr_i in range(255):
    _QR_EXP[_qr_i] = _qr_x
    _QR_LOG[_qr_x] = _qr_i
    _qr_x <<= 1
    if _qr_x & 0x100:
        _qr_x ^= 0x11D
for _qr_i in range(255, 512):
    _QR_EXP[_qr_i] = _QR_EXP[_qr_i - 255]


def _qr_gf_mul(a, b):
    return 0 if (a == 0 or b == 0) else _QR_EXP[_QR_LOG[a] + _QR_LOG[b]]


def _qr_rs_rem(data, nsym):
    gen = [1]
    for i in range(nsym):
        nxt = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nxt[j] ^= c
            nxt[j + 1] ^= _qr_gf_mul(c, _QR_EXP[i])
        gen = nxt
    res = list(data) + [0] * nsym
    for i in range(len(data)):
        coef = res[i]
        if coef != 0:
            for j in range(1, len(gen)):
                res[i + j] ^= _qr_gf_mul(gen[j], coef)
    return res[len(data):]


def qr_matrix(text):
    """Minimal zero-dependency Byte-mode ECC-L QR encoder (versions 1-15, mask 0)."""
    raw = text.encode("utf-8")
    ver = None
    for v in range(1, 16):
        ec, b1, k1, b2, k2 = _QR_ECC_L[v]
        hdr_bytes = 2 if v <= 9 else 3
        if len(raw) + hdr_bytes <= (b1 * k1 + b2 * k2):
            ver = v
            break
    if ver is None:
        raise ValueError("内容过长，超出当前二维码编码上限（%d 字节）" % len(raw))

    ec, b1, k1, b2, k2 = _QR_ECC_L[ver]
    total_data = b1 * k1 + b2 * k2
    bits = []

    def push(val, width):
        for i in range(width - 1, -1, -1):
            bits.append((val >> i) & 1)

    push(0b0100, 4)
    push(len(raw), 8 if ver <= 9 else 16)
    for byte in raw:
        push(byte, 8)
    for _ in range(min(4, total_data * 8 - len(bits))):
        bits.append(0)
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pads = (0xEC, 0x11)
    idx = 0
    while len(cw) < total_data:
        cw.append(pads[idx % 2])
        idx += 1

    blocks, ecs = [], []
    pos = 0
    for cnt, k in ((b1, k1), (b2, k2)):
        for _ in range(cnt):
            blk = cw[pos:pos + k]
            pos += k
            blocks.append(blk)
            ecs.append(_qr_rs_rem(blk, ec))

    inter = []
    for i in range(max(k1, k2)):
        for blk in blocks:
            if i < len(blk):
                inter.append(blk[i])
    for i in range(ec):
        for e in ecs:
            inter.append(e[i])

    size = 17 + 4 * ver
    grid = [[None] * size for _ in range(size)]
    is_func = [[False] * size for _ in range(size)]

    def set_f(r, c, val):
        grid[r][c] = 1 if val else 0
        is_func[r][c] = True

    def finder(tr, tc):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = tr + dr, tc + dc
                if 0 <= r < size and 0 <= c < size:
                    dark = (0 <= dr <= 6 and (dc in (0, 6) or dr in (0, 6))) or (2 <= dr <= 4 and 2 <= dc <= 4)
                    set_f(r, c, dark)

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)
    for i in range(8, size - 8):
        set_f(6, i, i % 2 == 0)
        set_f(i, 6, i % 2 == 0)
    ac = _QR_ALIGN[ver]
    for r in ac:
        for c in ac:
            if (r == 6 and c in (6, ac[-1])) or (r == ac[-1] and c == 6):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    set_f(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    set_f(size - 8, 8, True)
    for i in range(9):
        if i != 6:
            if not is_func[8][i]:
                set_f(8, i, False)
            if not is_func[i][8]:
                set_f(i, 8, False)
    for i in range(8):
        set_f(8, size - 1 - i, False)
        set_f(size - 1 - i, 8, False)
    if ver >= 7:
        vbits = ver << 12
        rem = vbits
        for i in range(17, 11, -1):
            if rem & (1 << i):
                rem ^= 0x1F25 << (i - 12)
        vinfo = vbits | rem
        for i in range(6):
            for j in range(3):
                b = (vinfo >> (i * 3 + j)) & 1
                set_f(size - 11 + j, i, b)
                set_f(i, size - 11 + j, b)

    stream = []
    for byte in inter:
        for i in range(7, -1, -1):
            stream.append((byte >> i) & 1)
    si = 0
    up = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if up else range(size)
        for r in rows:
            for dc in (0, -1):
                c = col + dc
                if not is_func[r][c]:
                    bit = stream[si] if si < len(stream) else 0
                    si += 1
                    if (r + c) % 2 == 0:
                        bit ^= 1
                    grid[r][c] = bit
        up = not up
        col -= 2

    # Format info: ECC-L (01), mask 0 (000)
    fval = (0b01 << 3) | 0
    frem = fval << 10
    for i in range(14, 9, -1):
        if frem & (1 << i):
            frem ^= 0x537 << (i - 10)
    finfo = ((fval << 10) | frem) ^ 0x5412
    for i in range(6):
        set_f(8, i, (finfo >> (14 - i)) & 1)
    set_f(8, 7, (finfo >> 8) & 1)
    set_f(8, 8, (finfo >> 7) & 1)
    set_f(7, 8, (finfo >> 6) & 1)
    for i in range(6):
        set_f(5 - i, 8, (finfo >> (5 - i)) & 1)
    for i in range(7):
        set_f(size - 1 - i, 8, (finfo >> (14 - i)) & 1)
    for i in range(8):
        set_f(8, size - 8 + i, (finfo >> (7 - i)) & 1)
    return grid


def qr_svg(text, scale=7, border=4):
    grid = qr_matrix(text)
    n = len(grid)
    dim = n + border * 2
    px = dim * scale
    cmds = []
    for r, row in enumerate(grid):
        for c, bit in enumerate(row):
            if bit:
                cmds.append("M%d %dh1v1h-1z" % (c + border, r + border))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
        'width="{px}" height="{px}" shape-rendering="crispEdges">'
        '<rect width="100%" height="100%" fill="#ffffff"/>'
        '<path fill="#000000" d="{path}"/></svg>'
    ).format(dim=dim, px=px, path="".join(cmds))


def _is_rfc1918_lan(ip_str):
    try:
        addr = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False
    if addr.version != 4:
        return False
    return any(addr in net for net in (
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
    ))


def detect_lan_ipv4():
    """Return this computer's LAN IPv4 (192.168.x / 10.x / 172.16-31.x), ignoring Clash TUN 198.18.0.0/15."""
    if sys.platform == "darwin":
        for iface in ("en0", "en1", "en2", "en3"):
            try:
                out = subprocess.run(
                    ["ipconfig", "getifaddr", iface],
                    capture_output=True, text=True, check=False, timeout=2,
                ).stdout.strip()
                if _is_rfc1918_lan(out):
                    return out
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            out = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False, timeout=3).stdout
            for m in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)\b", out):
                if _is_rfc1918_lan(m.group(1)):
                    return m.group(1)
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if _is_rfc1918_lan(ip):
                return ip
    except OSError:
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("223.5.5.5", 53))
            cand = sock.getsockname()[0]
            if _is_rfc1918_lan(cand):
                return cand
    except OSError:
        pass
    return "127.0.0.1"


def _uri_lines_from_text(uris_text):
    return [line.strip() for line in uris_text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def build_v2box_routes_scheme():
    routes = [
        {
            "name": "route." + str(uuid.uuid5(uuid.NAMESPACE_DNS, "claude-setup-kit-block-ipv6")).upper(),
            "remark": "封死IPv6防漏",
            "isEnable": True,
            "type": "IP",
            "matchMode": "keyword",
            "tag": "block",
            "listIP": ["::/0"],
            "list": [],
        },
        {
            "name": "route." + str(uuid.uuid5(uuid.NAMESPACE_DNS, "claude-setup-kit-direct-cn-domain")).upper(),
            "remark": "大陆域名直连",
            "isEnable": True,
            "type": "Domain",
            "matchMode": "keyword",
            "tag": "direct",
            "listIP": [],
            "list": ["geosite:cn", "geosite:private"],
        },
        {
            "name": "route." + str(uuid.uuid5(uuid.NAMESPACE_DNS, "claude-setup-kit-direct-cn-ip")).upper(),
            "remark": "大陆与局域网IP直连",
            "isEnable": True,
            "type": "IP",
            "matchMode": "keyword",
            "tag": "direct",
            "listIP": ["geoip:cn", "geoip:private"],
            "list": [],
        },
    ]
    payload = base64.b64encode(json.dumps(routes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return "v2box://routes?multi=" + payload


def _safe_qr_svg(text, scale=6, border=4, fallback_msg="链接较长，请使用下方手机网页复制链接导入。"):
    try:
        return qr_svg(text, scale=scale, border=border)
    except ValueError:
        return "<p style='color:#92400e'>%s</p>" % html.escape(fallback_msg)


def _build_pc_html(res, info):
    node_desc = res["node1"]["name"]
    if res["node2"]:
        node_desc = "%s（主出口）+ %s（Google 分流）" % (res["node1"]["name"], res["node2"]["name"])
    uri_lines = _uri_lines_from_text(res["contents"]["v2box-uris.txt"])
    n1_label = _node_uri_label(0, res["node1"]["name"])
    primary_qr = _safe_qr_svg(uri_lines[0], scale=6, border=4) if uri_lines else "<p>暂无主节点链接</p>"

    split_qr_html = ""
    if len(uri_lines) > 1:
        n2_label = _node_uri_label(1, res["node2"]["name"]) if res["node2"] else "Claude谷歌-节点2"
        split_svg = _safe_qr_svg(uri_lines[1], scale=5, border=4)
        split_qr_html = """
  <details>
    <summary>可选备用节点（%s）：点这里展开二维码</summary>
    <div class="qrbox"><p>%s</p>%s</div>
  </details>""" % (html.escape(n2_label), html.escape(n2_label), split_svg)

    mobile_qr = qr_svg(info["mobile_url"], scale=6, border=4)

    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>iPhone 扫码导入 V2Box（%(n1_label)s）</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;max-width:720px;margin:28px auto;padding:0 18px;color:#111827;line-height:1.6;background:#f9fafb}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:24px;box-shadow:0 4px 16px rgba(0,0,0,.04);text-align:center;margin-bottom:18px}
.qr{margin:14px auto;display:inline-block;padding:12px;background:#fff;border:1px solid #d1d5db;border-radius:12px}
.url{font-family:ui-monospace,Menlo,monospace;font-size:14px;color:#2563eb;word-break:break-all;background:#eff6ff;padding:8px 12px;border-radius:8px;display:inline-block;margin:6px 0}
ol{text-align:left;max-width:560px;margin:14px auto 0;padding-left:22px}
li{margin:8px 0}
.note{margin-top:16px;padding:12px 14px;border-radius:10px;background:#fef3c7;color:#92400e;font-size:14px;text-align:left}
details{margin-top:16px;text-align:left;background:#f3f4f6;padding:12px 14px;border-radius:10px}
summary{cursor:pointer;font-weight:600}
.qrbox{display:inline-block;margin:10px 12px 0 0;text-align:center;background:#fff;padding:10px;border-radius:8px}
</style>
</head>
<body>
<div class="card">
  <h1>第 1 种（最简单）：V2Box App 直接扫码导入</h1>
  <p>导入后的新节点名称：<strong>%(n1_label)s</strong>（对应电脑端：%(nodes)s）</p>
  <div class="qr">%(primary_qr)s</div>
  <ol>
    <li>打开手机 <strong>V2Box</strong> → 点底部 <strong>配置</strong>（<code>Configs</code>）→ 点右上角 <code>+</code> → 点 <strong>扫描二维码</strong>（<code>Scan QR Code</code>）；</li>
    <li>直接扫上面这个大二维码，列表里会立刻多出 <strong><code>%(n1_label)s</code></strong>；</li>
    <li><strong>点一下选中 <code>%(n1_label)s</code></strong>；注意只导节点时 V2Box 默认是全局模式，需接着扫下方第 2 个码在手机页一键导入「封死 IPv6 + 国内域名直连（<code>geosite:cn</code>）+ 国内 IP 直连（<code>geoip:cn</code>）」3 条路由进 <strong>路由</strong>（<code>Route</code>），最后回 <strong>主页</strong>（<code>Home</code>）打开开关！</li>
  </ol>%(split_qr)s
  <div class="note">
    <strong>原生 App（Claude / Claude Duet）防漏提示：</strong><br>
    • <strong>必做</strong>：美区 App Store 下载；<code>设置 → 隐私与安全性 → 定位服务</code> 设为<strong>「永不」</strong>并关「本地网络」；务必<strong>先连上 VPN 再打开 App</strong>。<br>
    • <strong>【可选项（国行主力机可保留北京时间与原有习惯；专用机可按需开启）】</strong>：在「<code>设置 → 通用 → 语言与地区 → 地区</code>」改<strong>「美国」</strong>（语言保留简体中文），或在「日期与时间」改美国时区。本导入页在设定超时后自动关闭。
  </div>
</div>

<div class="card">
  <h2>第 2 种：手机相机扫码打开网页（导入国内自动分流与封死 IPv6 路由 / 复制节点 / 小火箭 / Stash / Karing）</h2>
  <p style="font-size:14px;color:#4b5563">保证 iPhone 和这台电脑连着同一个 Wi-Fi，用苹果自带「相机」扫下方二维码在 Safari 打开：</p>
  <div class="qr">%(mobile_qr)s</div>
  <div><span class="url">%(murl)s</span></div>
</div>
</body>
</html>
""" % {
        "n1_label": html.escape(n1_label),
        "nodes": html.escape(node_desc),
        "primary_qr": primary_qr,
        "split_qr": split_qr_html,
        "mobile_qr": mobile_qr,
        "murl": html.escape(info["mobile_url"]),
    }


def _build_mobile_html(res, info):
    node_desc = res["node1"]["name"]
    if res["node2"]:
        node_desc = "%s + %s（Google 分流）" % (res["node1"]["name"], res["node2"]["name"])
    n1_label = _node_uri_label(0, res["node1"]["name"])
    uris_only = "\n".join(_uri_lines_from_text(res["contents"]["v2box-uris.txt"]))
    uris_js = json.dumps(uris_only).replace("</", "<\\/")
    uris_escaped = html.escape(uris_only)
    v2_json = res["contents"]["v2box-xray.json"]
    v2_escaped = html.escape(v2_json)
    routes_scheme = build_v2box_routes_scheme()
    routes_js = json.dumps(routes_scheme).replace("</", "<\\/")
    routes_raw = html.escape(routes_scheme)
    sub_scheme = "v2box://install-config?url=" + quote(info["sub_url"], safe="")
    sr_scheme = "shadowrocket://config/add/" + info["shadowrocket_url"]
    stash_scheme = "stash://install-config?url=%s&name=%s" % (
        quote(info["clash_url"], safe=""),
        quote("Claude防漏分流", safe=""),
    )
    karing_scheme = "karing://install-config?url=%s&name=%s" % (
        quote(info["clash_url"], safe=""),
        quote("Claude防漏分流", safe=""),
    )

    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>一键导进 iPhone V2Box</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;margin:0;padding:18px;background:#f3f4f6;color:#111827;line-height:1.55}
.box{max-width:520px;margin:0 auto;background:#fff;border-radius:16px;padding:20px;box-shadow:0 4px 16px rgba(0,0,0,.06)}
h1{font-size:21px;margin:0 0 8px}
.sub{color:#4b5563;font-size:14px;margin:0 0 16px}
.btn1{display:block;width:100%%;border:0;border-radius:12px;padding:16px 14px;font-size:17px;font-weight:700;background:#16a34a;color:#fff;cursor:pointer;text-align:center;box-sizing:border-box}
.btn2,.btn3{display:block;width:100%%;border-radius:12px;padding:13px 14px;font-size:15px;font-weight:600;text-decoration:none;text-align:center;margin-top:12px;box-sizing:border-box}
.btn2{border:1px solid #2563eb;background:#eff6ff;color:#1d4ed8}
.btn3{border:1px solid #9ca3af;background:#f9fafb;color:#374151}
.msg{display:none;margin-top:12px;padding:12px;border-radius:10px;background:#ecfdf5;border:1px solid #86efac;color:#166534;font-size:14px;font-weight:600}
.warn{margin-top:14px;padding:12px;border-radius:10px;background:#fef3c7;color:#92400e;font-size:13px}
details{margin-top:14px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:10px 12px;font-size:14px}
summary{font-weight:600;cursor:pointer}
textarea{width:100%%;margin-top:8px;font-family:ui-monospace,Menlo,monospace;font-size:12px;border:1px solid #d1d5db;border-radius:8px;padding:8px;box-sizing:border-box}
.alt a{display:block;margin-top:8px;padding:10px 12px;background:#fff;border:1px solid #d1d5db;border-radius:8px;color:#111827;text-decoration:none;font-weight:600}
</style>
</head>
<body>
<div class="box">
  <h1>一键导进 iPhone V2Box</h1>
  <p class="sub">导入节点：<strong>%(n1_label)s</strong>（%(nodes)s）</p>

  <button type="button" class="btn1" onclick="copyAndOpen()">① 点我复制节点链接并打开 V2Box（推荐）</button>
  <div id="msg" class="msg"></div>

  <button type="button" class="btn2" onclick="copyRoutesAndOpen()" style="cursor:pointer">② 点我复制防漏分流路由并打开 V2Box（封死 IPv6 + 大陆直连）</button>
  <a class="btn3" href="%(sub_href)s">③ 一键唤起 V2Box 导入节点（备用）</a>

  <div class="warn">
    <strong>导入后用法：</strong><br>
    • 点 <strong>①</strong> 自动跳去 V2Box 后，点底部 <strong>配置</strong>（<code>Configs</code>）→ 右上角 <code>+</code> → 选 <strong>从剪贴板导入 v2ray uri</strong>（弹窗点「允许粘贴」），看到 <strong>%(n1_label)s</strong> 点中它。<br>
    • 点 <strong>②</strong> 会同时复制 3 条分流路由（<code>封死IPv6防漏</code> + <code>大陆域名直连</code> + <code>大陆与局域网IP直连</code>）并跳去 V2Box；如果未自动弹窗导入，点 <strong>路由</strong>（底部 <code>路由</code> 或 <code>设置 → 路由</code>）→ 右上角 <code>+</code> / 导入图标 → <strong>从剪贴板导入</strong>（允许粘贴），确认这 3 条规则右边的开关都是开启状态且未设为「全局」，再回 <strong>主页</strong>（<code>Home</code>）把连接开关关掉重连一次。<br>
    • <strong>原生 Claude / Claude Duet App 必做</strong>：美区 App Store 下载，定位设为<strong>「永不」</strong>并关「本地网络」，务必<strong>先连上 VPN 再打开</strong>。<br>
    • <strong>【可选项（国行主力机可保留北京时间与原有习惯；专用机可按需开启）】</strong>：改「<code>设置 → 通用 → 语言与地区 → 地区</code>」为<strong>「美国」</strong>，或改美国时区。
  </div>

  <details>
    <summary>如果上面自动复制受限：点此展开手动全选复制节点链接</summary>
    <textarea readonly rows="4" onclick="this.focus();this.select();this.setSelectionRange(0,999999)">%(uris_raw)s</textarea>
  </details>

  <details>
    <summary>手动复制 V2Box 路由口令（v2box://routes?multi=…）</summary>
    <textarea readonly rows="4" onclick="this.focus();this.select();this.setSelectionRange(0,999999)">%(routes_raw)s</textarea>
  </details>

  <details class="alt">
    <summary>如果你用的是小火箭 / Stash / Karing：点这里一键拉取</summary>
    <a href="%(sr_href)s">在 Shadowrocket（小火箭）中一键导入</a>
    <a href="%(stash_href)s">在 Stash 中一键导入</a>
    <a href="%(karing_href)s">在 Karing 中一键导入</a>
  </details>

  <details>
    <summary>高级选项：Xray / V2Ray 完整 JSON 配置（含 116 条分流规则）</summary>
    <textarea readonly rows="5" onclick="this.focus();this.select();this.setSelectionRange(0,999999)">%(v2_raw)s</textarea>
  </details>
</div>
<script>
var cfg = %(uris_js)s;
var routesCfg = %(routes_js)s;
var n1Label = %(n1_js)s;
function copyText(text) {
  var ok = false;
  try {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, ta.value.length);
    ok = document.execCommand("copy");
    document.body.removeChild(ta);
  } catch (e) {}
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(function () {});
    ok = true;
  }
  return ok;
}
function copyAndOpen() {
  var ok = copyText(cfg);
  var el = document.getElementById("msg");
  el.style.display = "block";
  el.textContent = ok
    ? "✅ 已复制节点链接！正在打开 V2Box… 进去后点底部 配置(Configs) → 右上角 + → 从剪贴板导入 v2ray uri（允许粘贴）即可看到「" + n1Label + "」！"
    : "⚠️ 自动复制受限，请点上方按钮③一键导入，或点下面展开框全选复制。";
  setTimeout(function () { window.location.href = "v2box://"; }, 350);
}
function copyRoutesAndOpen() {
  var ok = copyText(routesCfg);
  var el = document.getElementById("msg");
  el.style.display = "block";
  el.textContent = ok
    ? "✅ 已复制 3 条分流路由！正在打开 V2Box… 若未自动弹窗，请点 路由 → 右上角 + / 导入图标 → 从剪贴板导入（允许粘贴），确认 3 条规则全开启且非「全局」模式后回 主页 重连一次！"
    : "⚠️ 自动复制受限，请展开下方「手动复制 V2Box 路由口令」全选复制，再到 V2Box → 路由 → 从剪贴板导入。";
  setTimeout(function () { window.location.href = routesCfg; }, 350);
}
</script>
</body>
</html>
""" % {
        "n1_label": html.escape(n1_label),
        "nodes": html.escape(node_desc),
        "sub_href": html.escape(sub_scheme, quote=True),
        "uris_raw": uris_escaped,
        "routes_raw": routes_raw,
        "v2_raw": v2_escaped,
        "sr_href": html.escape(sr_scheme, quote=True),
        "stash_href": html.escape(stash_scheme, quote=True),
        "karing_href": html.escape(karing_scheme, quote=True),
        "uris_js": uris_js,
        "routes_js": routes_js,
        "n1_js": json.dumps(n1_label),
    }


def create_import_server(res, lan_ip=None, port=0):
    """Start a temporary LAN HTTP server under a random path code for 1-scan iOS import."""
    resolved_ip = lan_ip or detect_lan_ipv4()
    link_code = os.urandom(12).hex()
    prefix = "/" + link_code

    uris_only = "\n".join(_uri_lines_from_text(res["contents"]["v2box-uris.txt"]))
    sub_b64 = base64.b64encode(uris_only.encode("utf-8")).decode("ascii")

    server_holder = {}
    info = {}

    class ImportHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            return

        def _resolve_route(self):
            path = self.path.split("?", 1)[0]
            if path in (prefix, prefix + "/"):
                return "mobile_page", 200, "text/html; charset=utf-8", _build_mobile_html(res, info)
            if path == prefix + "/pc":
                return "pc_page", 200, "text/html; charset=utf-8", _build_pc_html(res, info)
            if path == prefix + "/sub.txt":
                return "sub_txt", 200, "text/plain; charset=utf-8", sub_b64
            if path == prefix + "/v2box-xray.json":
                return "v2box_json", 200, "application/json; charset=utf-8", res["contents"]["v2box-xray.json"]
            if path == prefix + "/stash-karing-clash.yaml":
                return "stash_karing", 200, "text/yaml; charset=utf-8", res["contents"]["stash-karing-clash.yaml"]
            if path == prefix + "/shadowrocket.conf":
                return "shadowrocket", 200, "text/plain; charset=utf-8", res["contents"]["shadowrocket.conf"]
            return None, 404, "text/plain; charset=utf-8", "Not Found"

        def _send(self, code, ctype, body, send_body=True):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if send_body:
                self.wfile.write(data)

        def do_HEAD(self):  # noqa: N802
            _, code, ctype, body = self._resolve_route()
            self._send(code, ctype, body, send_body=False)

        def do_GET(self):  # noqa: N802
            route_label, code, ctype, body = self._resolve_route()
            if route_label:
                print("[HTTP] endpoint requested: %s" % route_label, flush=True)
            self._send(code, ctype, body, send_body=True)

    server = ThreadingHTTPServer(("0.0.0.0", int(port)), ImportHandler)
    bound_port = server.server_address[1]
    base_lan = "http://%s:%d%s" % (resolved_ip, bound_port, prefix)
    info.update({
        "lan_ip": resolved_ip,
        "port": bound_port,
        "link_code": link_code,
        "pc_url": "http://127.0.0.1:%d%s/pc" % (bound_port, prefix),
        "mobile_url": base_lan + "/",
        "sub_url": base_lan + "/sub.txt",
        "v2box_url": base_lan + "/v2box-xray.json",
        "clash_url": base_lan + "/stash-karing-clash.yaml",
        "shadowrocket_url": base_lan + "/shadowrocket.conf",
    })
    server_holder["server"] = server
    return server, info


def open_local_browser(url):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except OSError:
        return False
    return False


def render_ios_configs(node_input, out_dir, manifest_path=None):
    manifest_path = Path(manifest_path) if manifest_path else (ROOT / "manifest.json")
    out_path = Path(out_dir)
    if out_path.exists():
        raise render.RenderError("输出目录已存在，不覆盖: %s" % out_path)

    groups = load_group_names(manifest_path)
    exit_group = groups["exit_group"]
    google_group = groups["google_group"]
    node_values = render.normalize_nodes(node_input)
    rendered_yaml, model = build_clash_model(node_values, exit_group, google_group)

    proxies = [dict(p) for p in (model.get("proxies") or []) if isinstance(p, dict)]
    if not proxies:
        raise render.RenderError("渲染后的配置没有有效代理节点")

    node1 = proxies[0]
    has_google_split = "NODE2_NAME" in node_values and len(proxies) >= 2
    node2 = proxies[1] if has_google_split else None

    files_content = {
        "v2box-xray.json": build_v2box_xray_json(model, exit_group, google_group, node1, node2),
        "v2box-uris.txt": build_v2box_uris(proxies),
        "stash-karing-clash.yaml": build_stash_karing_yaml(rendered_yaml, has_google_split),
        "shadowrocket.conf": build_shadowrocket_conf(model, exit_group, google_group, proxies, has_google_split),
    }

    try:
        out_path.mkdir(parents=True, exist_ok=False)
        if os.name != "nt":
            os.chmod(out_path, 0o700)
        for fname, content in files_content.items():
            fpath = out_path / fname
            fpath.write_text(content, encoding="utf-8")
            if os.name != "nt":
                os.chmod(fpath, 0o600)
    except Exception:
        if out_path.exists():
            shutil.rmtree(out_path)
        raise

    return {
        "out_dir": str(out_path),
        "files": list(files_content.keys()),
        "node1": {"name": node1["name"], "type": node1["type"]},
        "node2": {"name": node2["name"], "type": node2["type"]} if node2 else None,
        "google_split": has_google_split,
        "contents": files_content,
    }


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src_group = ap.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--nodes", help="私有节点 JSON 文件（格式与 render.py 相同）")
    src_group.add_argument("--from-local-clash", action="store_true", help="直接读取本机正在运行的 Clash Verge 主出口与 Google 分流节点")
    ap.add_argument("--out", help="私有输出目录（必须不存在，建议放在 Git 仓库之外）")
    ap.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    ap.add_argument("--copy", choices=tuple(TARGET_FILES), help="把指定配置文件写入系统剪贴板（不打印密钥）")
    ap.add_argument("--serve", action="store_true", help="启动局域网扫码导入页，用 iPhone 相机扫码即可把配置一键导入手机")
    ap.add_argument("--timeout", type=int, default=600, help="--serve 模式自动关闭超时（秒，默认 600）")
    ap.add_argument("--lan-ip", help="覆盖自动识别的局域网 IPv4（如 192.168.1.20）")
    ap.add_argument("--no-browser", action="store_true", help="--serve 模式下仅打印本地链接，不自动打开电脑浏览器")
    args = ap.parse_args(argv)

    if args.nodes and not Path(args.nodes).is_file():
        print("[ERROR] --nodes 文件不存在: %s" % args.nodes, file=sys.stderr)
        return 2

    try:
        if args.from_local_clash:
            node_input = extract_proxies_from_local_clash(args.manifest)
        else:
            raw = Path(args.nodes).read_text(encoding="utf-8-sig")
            node_input = json.loads(raw)

        out_dir = args.out or str(ROOT / "build" / ("ios-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
        res = render_ios_configs(node_input, out_dir, manifest_path=args.manifest)
        copied_to = None
        if args.copy:
            target = TARGET_FILES[args.copy]
            copied_to = "%s (%s)" % (copy_to_clipboard(res["contents"][target]), target)
    except (render.RenderError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print("[ERROR] iOS 配置生成失败: %s" % exc, file=sys.stderr)
        return 2

    print("[OK] 已生成 iOS 防漏配置文件目录: %s" % res["out_dir"])
    print("  主出口节点: %s (%s)" % (res["node1"]["name"], res["node1"]["type"]))
    if res["node2"]:
        print("  Google分流: %s (%s)" % (res["node2"]["name"], res["node2"]["type"]))
    else:
        print("  Google分流: 单出口共用主节点")
    print("  包含文件: %s" % ", ".join(res["files"]))
    if copied_to:
        print("  已复制进剪贴板: %s" % copied_to)

    if args.serve:
        if args.timeout <= 0:
            print("[ERROR] --timeout 必须大于 0", file=sys.stderr)
            return 2
        try:
            server, info = create_import_server(res, lan_ip=args.lan_ip)
        except OSError as exc:
            print("[ERROR] 无法启动局域网扫码导入服务: %s" % exc, file=sys.stderr)
            return 2
        print("[OK] 局域网扫码导入页已启动（%d 秒后自动关闭）: %s" % (args.timeout, info["pc_url"]))
        print("  手机同一 Wi-Fi 用「相机」扫网页里的二维码即可（或手机 Safari 打开 %s）" % info["mobile_url"])
        sys.stdout.flush()
        if not args.no_browser:
            open_local_browser(info["pc_url"])
        timer = threading.Timer(args.timeout, server.shutdown)
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            timer.cancel()
            server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
