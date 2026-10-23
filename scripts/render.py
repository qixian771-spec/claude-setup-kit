#!/usr/bin/env python3
"""Render the {{PLACEHOLDER}} templates under system/ and templates/ for THIS Mac.

Writes only into the --out directory (default build/<component>-<UTC stamp>/, which must not
exist yet). Never touches /etc, /Library or the user's home. The installers in installers/lib
take the rendered directory as their only argument. Runs on the macOS system Python (3.9+).

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
                "system/sudoers/claude-mac-env-mirror"],
    "claude-wall": ["system/userbin/claude-wall"],
    "clash": ["templates/clash-profile.template.yaml", "templates/clash-profile.script.js"],
}


class RenderError(Exception):
    pass


class WinUser:
    """pwd-like record for Windows: pw_uid holds the SID (firewall rules are per SID)."""

    def __init__(self, name, home, sid):
        self.pw_name, self.pw_dir, self.pw_uid = name, home, sid


def platform_key():
    return "win32" if sys.platform.startswith("win") else sys.platform


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
        extra = json.loads(local.read_text(encoding="utf-8"))
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
        "WIFI_IFACE": wifi_iface(service) if lookup_iface else "{{WIFI_IFACE}}",
        "IPV6_LABEL": params["ipv6_guard_label"],
    }
    for key, value in values.items():
        if not value:
            raise RenderError("参数 %s 为空" % key)
        if "{{" in value and key != "WIFI_IFACE":
            raise RenderError("参数 %s 的值不能含占位符" % key)
    return values


def load_nodes(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(re.fullmatch(r"NODE\d+_[A-Z_]+", k) for k in data):
        raise RenderError("--nodes 文件必须是 {\"NODE1_NAME\": ..., \"NODE1_SERVER\": ...} 这样的 JSON 对象")
    return {k: str(v) for k, v in data.items()}


def render_text(text, values, source):
    def sub(match):
        key = match.group(1)
        if key not in values:
            raise RenderError("%s: 没有参数可填 {{%s}}" % (source, key))
        return values[key]
    return PLACEHOLDER.sub(sub, text)


def render_component(name, values, out_dir):
    if name not in COMPONENTS:
        raise RenderError("未知组件 %s（可选: %s）" % (name, ", ".join(COMPONENTS)))
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise RenderError("输出目录已存在，不覆盖: %s" % out_dir)
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
    summary = "\n".join("%s=%s" % (k, v) for k, v in values.items() if not k.startswith("NODE"))
    (out_dir / "PARAMS.txt").write_text("component=%s\n%s\n" % (name, summary), encoding="utf-8")
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
