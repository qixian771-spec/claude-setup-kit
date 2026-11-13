#!/usr/bin/env python3
"""Render the {{PLACEHOLDER}} templates under system/, system-win/ and templates/ for THIS machine (macOS or Windows).

Writes only into the --out directory (default build/<component>-<UTC stamp>/, which must not
exist yet). Never touches /etc, /Library or the user's home. The installers in installers/lib
take the rendered directory as their only argument. Runs on the macOS system Python (3.9+) or Windows `py -3` (3.9+).

Values come from three places, later ones win:
  1. manifest.json params (tun_device, tun_inet4, exit_group, exit_node, network_services, ipv6_guard_label)
  2. mirror.params.json next to manifest.json (optional, git-ignored, per-machine overrides)
  3. --param KEY=VALUE on the command line
USER / HOME / UID are the console user (SUDO_USER when run under sudo); WIFI_IFACE is looked up
with networksetup. Node secrets for the Clash template come only from --nodes FILE (JSON).
"""
import argparse
import datetime as dt
import json
import os
try:
    import pwd  # Unix only
except ImportError:  # Windows
    pwd = None
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
# Optional parts of a template. A whole block between a "# {{IF KEY}}" line and a "# {{ENDIF}}" line, or a single
# line ending in "# {{IF KEY}}", is kept only when KEY was supplied (e.g. NODE3_* for an optional third node).
BLOCK_START = re.compile(r"^\s*#\s*\{\{IF ([A-Z0-9_]+)\}\}\s*$")
BLOCK_END = re.compile(r"^\s*#\s*\{\{ENDIF\}\}\s*$")
INLINE_IF = re.compile(r"\s*#\s*\{\{IF ([A-Z0-9_]+)\}\}\s*$")

COMPONENTS = {
    "direct-wall": ["system/pf.anchors/local.claude-direct-wall", "system/libexec/claude-direct-wall",
                    "system/LaunchDaemons/local.claude-direct-wall.plist"],
    "net-wall": ["system/pf.anchors/local.claude-net-wall", "system/libexec/claude-net-wall",
                 "system/LaunchDaemons/local.claude-net-wall.plist"],
    "leak-guard": ["system/pf.anchors/local.leak-guard", "system/libexec/leak-guard-loader",
                   "system/LaunchDaemons/local.leak-guard.plist"],
    "watch": ["system/libexec/net-guard-watch", "system/libexec/net-guard-watch-lib.sh",
              "system/LaunchDaemons/local.net-guard-watch.plist"],
    "ipv6-guard": ["system/userbin/ipv6-guard.sh", "system/LaunchDaemons/ipv6-guard.plist"],
    "updater": ["system/updater", "system/LaunchDaemons/local.claude-address-update.plist",
                "system/sudoers/claude-mac-env-mirror", "system/libexec/claude-pf-helper"],
    "claude-wall": ["system/userbin/claude-wall"],
    "clash": ["templates/clash-profile.template.yaml", "templates/clash-profile.script.js"],
    # Windows (W3+): the PowerShell scripts read PARAMS.txt instead of placeholders.
    "win-firewall": ["system-win/firewall"],
    "win-tasks": ["system-win/tasks", "system-win/firewall/common.ps1"],
    "win-tools": ["system-win/tools", "system-win/firewall/common.ps1"],
}


class RenderError(Exception):
    pass


class WinUser:
    """pwd-like record for Windows: pw_uid holds the SID (firewall rules are per SID)."""

    def __init__(self, name, home, sid):
        self.pw_name, self.pw_dir, self.pw_uid = name, home, sid


def platform_key():
    # CLAUDE_SETUP_KIT_PLATFORM is for tests/CI only: it pins the component tables to one platform.
    forced = os.environ.get("CLAUDE_SETUP_KIT_PLATFORM")
    if forced in ("darwin", "win32"):
        return forced
    return "win32" if sys.platform.startswith("win") else "darwin"


def powershell(script):
    import base64
    prelude = "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n$ErrorActionPreference='Stop'\n"
    encoded = base64.b64encode((prelude + script).encode("utf-16le")).decode("ascii")
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                          capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    if proc.returncode != 0:
        raise RenderError("PowerShell 失败: %s" % (proc.stderr.strip().splitlines()[0][:120] if proc.stderr.strip() else "rc=%s" % proc.returncode))
    return proc.stdout.strip()


def console_user():
    if platform_key() == "win32":
        name, home = os.environ.get("USERNAME"), os.environ.get("USERPROFILE")
        if not name or not home:
            raise RenderError("缺少 USERNAME / USERPROFILE 环境变量")
        sid = powershell("[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
        if not re.fullmatch(r"S-1-5-21-\d+-\d+-\d+-\d+", sid):
            raise RenderError("拿到的不是普通用户 SID: %s（不要用 SYSTEM/管理员提权的会话渲染）" % sid)
        return WinUser(name, home, sid)
    name = os.environ.get("SUDO_USER") or pwd.getpwuid(os.getuid()).pw_name
    entry = pwd.getpwnam(name)
    if entry.pw_uid == 0:
        raise RenderError("不能以 root 作为桌面用户渲染；请用普通用户运行（安装器会自己 sudo）")
    return entry


def wifi_iface(service):
    if platform_key() == "win32":
        # On Windows the "service" is the adapter's InterfaceAlias; the interface is the same name.
        aliases = powershell("Get-NetAdapter | ForEach-Object Name").splitlines()
        if service not in [a.strip() for a in aliases]:
            raise RenderError("Get-NetAdapter 里没有网卡 %r（有: %s）；用 --param network_services=<别名> 指定" % (service, ", ".join(a.strip() for a in aliases)))
        return service
    out = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True,
                         encoding="utf-8", errors="replace", timeout=20).stdout
    match = re.search(r"Hardware Port: %s\nDevice: (\S+)" % re.escape(service), out)
    if not match:
        raise RenderError("networksetup 里找不到网络服务 %r 的接口；用 --param network_services=<名字> 指定" % service)
    return match.group(1)


def load_params(manifest_path, overrides, lookup_iface=True):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    params = dict(manifest["params"])
    if platform_key() == "win32":
        params.update(manifest.get("params_win", {}))
    local = Path(manifest_path).parent / "mirror.params.json"
    if local.exists():
        extra = json.loads(local.read_text(encoding="utf-8-sig"))
        unknown = set(extra) - set(params)
        if unknown:
            raise RenderError("mirror.params.json 有未知参数: %s" % sorted(unknown))
        params.update(extra)
    for item in overrides:
        if "=" not in item:
            raise RenderError("--param 需要 KEY=VALUE: %s" % item)
        key, value = item.split("=", 1)
        if key not in params:
            raise RenderError("未知参数 %s" % key)
        params[key] = [v for v in value.split(",") if v] if isinstance(params[key], list) else value
    user = console_user()
    service = params["network_services"][0]
    values = {
        "USER": user.pw_name, "HOME": user.pw_dir, "UID": str(user.pw_uid),
        "USER_SID": str(user.pw_uid) if platform_key() == "win32" else "n/a",
        "TUN": params["tun_device"], "TUN_INET4": params["tun_inet4"],
        "EXIT_GROUP": params["exit_group"], "EXIT_GROUP_URLENC": quote(params["exit_group"]),
        "EXIT_NODE": params["exit_node"], "WIFI_SERVICE": service,
        "GOOGLE_GROUP": params["google_group"],
        "WIFI_IFACE": wifi_iface(service) if lookup_iface else "{{WIFI_IFACE}}",
        "IPV6_LABEL": params["ipv6_guard_label"],
        "TIMEZONE_WIN": params.get("timezone_win", "n/a"),
    }
    for key, value in values.items():
        if not value:
            raise RenderError("参数 %s 为空" % key)
        if "{{" in value and key != "WIFI_IFACE":
            raise RenderError("参数 %s 的值不能含占位符" % key)
    return values


FORBIDDEN_PROXY_TYPES = {"direct", "reject", "reject-drop", "pass", "dns"}


def _as_bool(val, default=False):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _yaml_scalar(val):
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    s = str(val)
    if "\n" in s or "\r" in s:
        raise RenderError("节点字段值不能含换行符")
    return "'" + s.replace("'", "''") + "'"


def _yaml_mapping_lines(mapping, indent):
    lines = []
    pad = " " * indent
    for k, v in mapping.items():
        if v is None:
            continue
        key = str(k).strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
            raise RenderError("非法 Clash 节点字段名: %r" % k)
        if isinstance(v, dict):
            if not v:
                continue
            lines.append("%s%s:" % (pad, key))
            lines.extend(_yaml_mapping_lines(v, indent + 2))
        elif isinstance(v, list):
            if not v:
                continue
            lines.append("%s%s:" % (pad, key))
            for item in v:
                if isinstance(item, (dict, list)):
                    raise RenderError("字段 %s 的列表元素只支持标量" % key)
                lines.append("%s- %s" % (" " * (indent + 2), _yaml_scalar(item)))
        else:
            lines.append("%s%s: %s" % (pad, key, _yaml_scalar(v)))
    return lines


def _format_proxy_yaml(proxy, label):
    if not isinstance(proxy, dict):
        raise RenderError("%s 必须是 JSON 对象" % label)
    name = str(proxy.get("name", "")).strip()
    ptype = str(proxy.get("type", "")).strip().lower()
    server = str(proxy.get("server", "")).strip()
    raw_port = proxy.get("port")
    if not name or not ptype or not server or raw_port is None or raw_port == "":
        raise RenderError("%s 缺少必填字段 name / type / server / port" % label)
    if ptype in FORBIDDEN_PROXY_TYPES:
        raise RenderError("%s 的 type 不能是 %s" % (label, ptype))
    try:
        port = int(str(raw_port).strip())
    except ValueError:
        raise RenderError("%s 的 port 必须是整数: %r" % (label, raw_port))
    if not (1 <= port <= 65535):
        raise RenderError("%s 的 port 超出 1..65535: %d" % (label, port))
    ordered = {"name": name, "type": ptype, "server": server, "port": port}
    for k, v in proxy.items():
        if k not in ("name", "type", "server", "port"):
            ordered[k] = v
    raw_lines = _yaml_mapping_lines(ordered, 2)
    first = "- " + raw_lines[0][2:]
    return name, "\n".join([first] + raw_lines[1:])


def _build_typed_proxy(slot, data):
    prefix = "NODE%d_" % slot
    raw_type = str(data.get(prefix + "TYPE", "")).strip().lower()
    type_aliases = {"shadowsocks": "ss", "hy2": "hysteria2"}
    ptype = type_aliases.get(raw_type, raw_type)

    def req(suffix):
        val = data.get(prefix + suffix)
        if val is None or str(val).strip() == "":
            raise RenderError("NODE%d (%s) 缺少 %s%s" % (slot, ptype, prefix, suffix))
        return str(val).strip()

    def opt(suffix):
        val = data.get(prefix + suffix)
        if val is None or str(val).strip() == "":
            return None
        return val

    proxy = {
        "name": req("NAME"),
        "type": ptype,
        "server": req("SERVER"),
        "port": req("PORT"),
    }
    if ptype == "ss":
        proxy["cipher"] = req("CIPHER")
        proxy["password"] = req("PASSWORD")
        proxy["udp"] = _as_bool(opt("UDP"), True)
        if opt("PLUGIN"):
            proxy["plugin"] = str(opt("PLUGIN")).strip()
        if isinstance(data.get(prefix + "PLUGIN_OPTS"), dict):
            proxy["plugin-opts"] = data[prefix + "PLUGIN_OPTS"]
    elif ptype == "trojan":
        proxy["password"] = req("PASSWORD")
        if opt("SNI"):
            proxy["sni"] = str(opt("SNI")).strip()
        proxy["skip-cert-verify"] = _as_bool(opt("SKIP_CERT_VERIFY"), False)
        proxy["udp"] = _as_bool(opt("UDP"), True)
        if opt("NETWORK"):
            proxy["network"] = str(opt("NETWORK")).strip()
        if opt("WS_PATH") or opt("WS_HOST"):
            ws = {}
            if opt("WS_PATH"):
                ws["path"] = str(opt("WS_PATH")).strip()
            if opt("WS_HOST"):
                ws["headers"] = {"Host": str(opt("WS_HOST")).strip()}
            proxy["ws-opts"] = ws
    elif ptype == "vless":
        proxy["uuid"] = req("UUID")
        proxy["network"] = str(opt("NETWORK") or "tcp").strip()
        proxy["tls"] = _as_bool(opt("TLS"), True)
        proxy["udp"] = _as_bool(opt("UDP"), True)
        if opt("FLOW"):
            proxy["flow"] = str(opt("FLOW")).strip()
        elif opt("REALITY_PUBLIC_KEY") and proxy["network"] == "tcp":
            proxy["flow"] = "xtls-rprx-vision"
        sni = opt("SNI") or opt("SERVERNAME") or opt("HOST")
        if sni:
            proxy["servername"] = str(sni).strip()
        proxy["client-fingerprint"] = str(opt("CLIENT_FINGERPRINT") or "chrome").strip()
        if opt("SKIP_CERT_VERIFY") is not None:
            proxy["skip-cert-verify"] = _as_bool(opt("SKIP_CERT_VERIFY"), False)
        if opt("REALITY_PUBLIC_KEY"):
            ropts = {
                "public-key": str(opt("REALITY_PUBLIC_KEY")).strip(),
                "support-x25519mlkem768": True,
            }
            if opt("REALITY_SHORT_ID") is not None:
                ropts["short-id"] = str(opt("REALITY_SHORT_ID")).strip()
            proxy["reality-opts"] = ropts
        if opt("WS_PATH") or opt("WS_HOST"):
            ws = {}
            if opt("WS_PATH"):
                ws["path"] = str(opt("WS_PATH")).strip()
            if opt("WS_HOST"):
                ws["headers"] = {"Host": str(opt("WS_HOST")).strip()}
            proxy["ws-opts"] = ws
    elif ptype == "vmess":
        proxy["uuid"] = req("UUID")
        proxy["alterId"] = int(str(opt("ALTERID") or "0").strip())
        proxy["cipher"] = str(opt("CIPHER") or "auto").strip()
        proxy["udp"] = _as_bool(opt("UDP"), True)
        if opt("TLS") is not None:
            proxy["tls"] = _as_bool(opt("TLS"), False)
        if opt("NETWORK"):
            proxy["network"] = str(opt("NETWORK")).strip()
        sni = opt("SNI") or opt("SERVERNAME")
        if sni:
            proxy["servername"] = str(sni).strip()
        if opt("WS_PATH") or opt("WS_HOST"):
            ws = {}
            if opt("WS_PATH"):
                ws["path"] = str(opt("WS_PATH")).strip()
            if opt("WS_HOST"):
                ws["headers"] = {"Host": str(opt("WS_HOST")).strip()}
            proxy["ws-opts"] = ws
    elif ptype in ("socks5", "http"):
        if opt("USERNAME") is not None:
            proxy["username"] = str(opt("USERNAME"))
        if opt("PASSWORD") is not None:
            proxy["password"] = str(opt("PASSWORD"))
        if opt("TLS") is not None:
            proxy["tls"] = _as_bool(opt("TLS"), False)
        if opt("SKIP_CERT_VERIFY") is not None:
            proxy["skip-cert-verify"] = _as_bool(opt("SKIP_CERT_VERIFY"), False)
        if ptype == "socks5":
            proxy["udp"] = _as_bool(opt("UDP"), False)
    elif ptype == "hysteria2":
        proxy["password"] = req("PASSWORD")
        if opt("SNI"):
            proxy["sni"] = str(opt("SNI")).strip()
        proxy["skip-cert-verify"] = _as_bool(opt("SKIP_CERT_VERIFY"), False)
        if opt("OBFS"):
            proxy["obfs"] = str(opt("OBFS")).strip()
        if opt("OBFS_PASSWORD"):
            proxy["obfs-password"] = str(opt("OBFS_PASSWORD"))
        if opt("UP"):
            proxy["up"] = str(opt("UP")).strip()
        if opt("DOWN"):
            proxy["down"] = str(opt("DOWN")).strip()
    elif ptype in ("tuic", "anytls"):
        if ptype == "tuic":
            proxy["uuid"] = req("UUID")
        proxy["password"] = req("PASSWORD")
        if opt("SNI"):
            proxy["sni"] = str(opt("SNI")).strip()
        proxy["udp"] = _as_bool(opt("UDP"), True)
    else:
        raise RenderError(
            "NODE%d_TYPE=%r 暂未内置字段映射；可直接传 \"NODE%d_PROXY\": {<Clash proxies 原样对象>} 支持任意 Clash 协议"
            % (slot, raw_type, slot)
        )
    return _format_proxy_yaml(proxy, "NODE%d" % slot)


def normalize_nodes(data):
    if not isinstance(data, dict) or not data or not all(re.fullmatch(r"NODE[1-4]_[A-Z0-9_]+", str(k)) for k in data):
        raise RenderError("--nodes 文件必须是 {\"NODE1_NAME\": ..., \"NODE1_SERVER\": ...} 或 {\"NODE1_PROXY\": {...}} 这样的 JSON 对象")
    out = {}
    for slot in (1, 2, 3):
        prefix = "NODE%d_" % slot
        slot_keys = [k for k in data if k.startswith(prefix)]
        if not slot_keys:
            continue
        if prefix + "PROXY" in data:
            name, yaml_block = _format_proxy_yaml(data[prefix + "PROXY"], prefix + "PROXY")
            out[prefix + "NAME"] = name
            out["CUSTOM_NODE%d" % slot] = yaml_block
        elif prefix + "TYPE" in data:
            name, yaml_block = _build_typed_proxy(slot, data)
            out[prefix + "NAME"] = name
            out["CUSTOM_NODE%d" % slot] = yaml_block
        else:
            for k in slot_keys:
                out[k] = str(data[k])
    for k in data:
        if k.startswith("NODE4_"):
            out[k] = str(data[k])
    if "NODE3_NAME" in out and "NODE2_NAME" not in out:
        raise RenderError("提供了 NODE3 但未提供 NODE2；第 2 个节点请使用 NODE2_*")
    return out


def load_nodes(path):
    if not Path(path).is_file():
        raise RenderError("--nodes 文件不存在: %s" % path)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise RenderError("--nodes 不是合法 JSON: %s" % exc)
    return normalize_nodes(data)


def apply_conditionals(text, values, source):
    out, skipping, depth = [], False, 0
    for line in text.splitlines(keepends=True):
        start = BLOCK_START.match(line)
        if start:
            if depth:
                raise RenderError("%s: {{IF}} 不能嵌套" % source)
            depth, skipping = 1, start.group(1) not in values
            continue
        if BLOCK_END.match(line):
            if not depth:
                raise RenderError("%s: 多余的 {{ENDIF}}" % source)
            depth, skipping = 0, False
            continue
        if skipping:
            continue
        inline = INLINE_IF.search(line)
        if inline:
            if inline.group(1) not in values:
                continue
            line = line[:inline.start()] + ("\n" if line.endswith("\n") else "")
        out.append(line)
    if depth:
        raise RenderError("%s: {{IF}} 没有对应的 {{ENDIF}}" % source)
    return "".join(out)


def render_text(text, values, source):
    vals = dict(values)
    for slot in (1, 2, 3):
        if ("NODE%d_NAME" % slot) in vals and ("CUSTOM_NODE%d" % slot) not in vals:
            vals["DEFAULT_NODE%d" % slot] = "1"
    text = apply_conditionals(text, vals, source)

    def sub(match):
        key = match.group(1)
        if key not in vals:
            raise RenderError("%s: 没有参数可填 {{%s}}" % (source, key))
        return vals[key]
    return PLACEHOLDER.sub(sub, text)


def render_component(name, values, out_dir):
    if name not in COMPONENTS:
        raise RenderError("未知组件 %s（可选: %s）" % (name, ", ".join(COMPONENTS)))
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise RenderError("输出目录已存在，不覆盖: %s" % out_dir)
    try:
        return _render_into(name, values, out_dir)
    except Exception:
        # Leave nothing behind on any failure (bad parameter, undecodable file, I/O error), so the same --out can
        # be retried after the cause is fixed.
        if out_dir.exists():
            import shutil
            shutil.rmtree(out_dir)
        raise


def _render_into(name, values, out_dir):
    written = []
    for rel in COMPONENTS[name]:
        src = ROOT / rel
        files = sorted(p for p in src.rglob("*") if p.is_file()) if src.is_dir() else [src]
        for path in files:
            if "__pycache__" in path.parts:
                continue
            target = out_dir / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = path.read_bytes()
            if "vendor" in path.parts or path.name.endswith("LICENSE"):
                target.write_bytes(raw)
            else:
                # Every template file is UTF-8 text; a decode failure is a packaging error.
                text = render_text(raw.decode("utf-8"), values, str(path.relative_to(ROOT)))
                target.write_text(text, encoding="utf-8")
            target.chmod(path.stat().st_mode & 0o777)
            written.append(str(target.relative_to(out_dir)))
    leftovers = []
    for rel in written:
        path = out_dir / rel
        if "vendor" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        leftovers += ["%s: {{%s}}" % (rel, m) for m in PLACEHOLDER.findall(text)]
    if leftovers:
        raise RenderError("渲染后仍有占位符: " + "; ".join(leftovers))
    summary = "\n".join(
        "%s=%s" % (k, v)
        for k, v in values.items()
        if not k.startswith(("NODE", "CUSTOM_NODE", "DEFAULT_NODE"))
    )
    # BOM so Windows PowerShell/Notepad read the Chinese adapter names correctly; harmless on macOS.
    (out_dir / "PARAMS.txt").write_text("component=%s\n%s\n" % (name, summary), encoding="utf-8-sig")
    return written


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        # Windows consoles default to GBK; the tables use ✅/❌ and Chinese.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--component", required=True, choices=sorted(COMPONENTS))
    ap.add_argument("--out", help="输出目录（必须不存在）；默认 build/<component>-<UTC 时间>")
    ap.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--nodes", help="clash 组件：节点参数 JSON（NODE1_NAME、NODE1_SERVER…）")
    ap.add_argument("--print-params", action="store_true", help="只打印将使用的参数，不渲染")
    args = ap.parse_args(argv)
    try:
        values = load_params(args.manifest, args.param)
        if args.nodes:
            values.update(load_nodes(args.nodes))
        if args.print_params:
            for k, v in values.items():
                if not k.startswith("NODE"):
                    print("%s=%s" % (k, v))
            return 0
        out = args.out or str(ROOT / "build" / ("%s-%s" % (args.component, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))))
        written = render_component(args.component, values, out)
    except RenderError as exc:
        print("[ERROR] %s" % exc, file=sys.stderr)
        return 2
    print(out)
    for rel in written:
        if "vendor" not in rel:
            print("  " + rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
