#!/usr/bin/env python3
"""Zero-friction initializer for claude-setup-kit (macOS & Windows).

Prevents AI agents from getting stuck on Step 0 or forgetting Claude privacy switches:
  1. Auto-detects the active Clash exit node, physical network service/adapter, and any existing macOS IPv6 guard
     label, then writes/merges `mirror.params.json` (existing user-specified keys are never overwritten).
  2. Safely backs up and supplements `~/.claude/settings.json` with the 14 official Claude privacy/telemetry opt-out
     switches (existing settings are never overwritten).

Never switches Clash nodes, never restarts Clash/Claude, never probes Anthropic hosts, and never runs sudo.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mirror_check as mc  # noqa: E402

PRIVACY_ENV_DEFAULTS = (
    ("DISABLE_TELEMETRY", "1"),
    ("DISABLE_ERROR_REPORTING", "1"),
    ("DISABLE_FEEDBACK_COMMAND", "1"),
    ("DISABLE_BUG_COMMAND", "1"),
    ("CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY", "1"),
    ("CLAUDE_CODE_ENABLE_TELEMETRY", "0"),
    ("CLAUDE_CODE_ENABLE_FEEDBACK_SURVEY_FOR_OTEL", "0"),
    ("OTEL_METRICS_EXPORTER", "none"),
    ("OTEL_LOGS_EXPORTER", "none"),
    ("OTEL_TRACES_EXPORTER", "none"),
    ("DO_NOT_TRACK", "1"),
    ("CLAUDE_CODE_DISABLE_VITALS_EMITTER", "1"),
    ("CLAUDE_CODE_SUPPRESS_SESSION_ATTRIBUTION", "1"),
)

PRIVACY_TOP_DEFAULTS = (
    ("skipWebFetchPreflight", True),
)

FORBIDDEN_NODES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "GLOBAL"}


def detect_clash_exit(host, params):
    api = params["clash_api"]
    group = params["exit_group"]
    info = {
        "clash_reachable": False,
        "exit_group_present": False,
        "detected_node": None,
        "group_members": [],
        "hint": None,
    }
    try:
        data = host.api(api, "/proxies/" + quote(group), timeout=4)
        info["clash_reachable"] = True
        info["exit_group_present"] = True
        info["group_members"] = [str(x) for x in (data.get("all") or [])]
        now = str(data.get("now") or "").strip()
        if now and now.upper() not in FORBIDDEN_NODES:
            info["detected_node"] = now
        return info
    except mc.HostError as exc:
        if "返回 404" not in str(exc):
            return info
        info["clash_reachable"] = True

    try:
        rules = host.api(api, "/rules", timeout=4).get("rules") or []
        proxies = host.api(api, "/proxies", timeout=4).get("proxies") or {}
    except mc.HostError:
        return info

    match_rule = next((r for r in reversed(rules) if r.get("type") == "Match"), None)
    cand_group = match_rule.get("proxy") if match_rule else None
    if cand_group and cand_group in proxies and proxies[cand_group].get("type") == "Selector":
        now = str(proxies[cand_group].get("now") or "").strip()
        if now and now.upper() not in FORBIDDEN_NODES and now in proxies:
            info["detected_node"] = now
            info["hint"] = "当前 Clash 尚未导入『%s』分组，正在使用 %r → 节点 %r（S1 渲染时可直接将此节点作为 NODE1）" % (
                group, cand_group, now
            )
    return info


def detect_network_service_mac():
    try:
        route_out = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=8,
        ).stdout
        m_if = re.search(r"^\s*interface:\s*(\S+)", route_out, re.M)
        iface = m_if.group(1) if m_if else None
        ports_out = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=8,
        ).stdout
        if iface and not iface.startswith("utun"):
            m_svc = re.search(r"Hardware Port:\s*(.+)\nDevice:\s*%s\b" % re.escape(iface), ports_out)
            if m_svc:
                svc = m_svc.group(1).strip()
                chk = subprocess.run(
                    ["networksetup", "-getinfo", svc],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=8,
                )
                if chk.returncode == 0:
                    return svc
    except (OSError, subprocess.SubprocessError):
        pass
    return "Wi-Fi"


def detect_network_services_win(tun_device):
    script = (
        "$tun = '%s'; "
        "$r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InterfaceAlias -ne $tun } | Sort-Object RouteMetric | Select-Object -First 1; "
        "$pri = if ($r -and $r.InterfaceAlias) { @($r.InterfaceAlias) } else { "
        "@((Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Name -ne $tun } | Select-Object -First 1).Name) }; "
        "$hw = @(Get-NetAdapter | Where-Object { $_.Name -ne $tun -and $_.HardwareInterface -eq $true } | ForEach-Object { $_.Name }); "
        "@($pri + $hw) | Where-Object { $_ } | Select-Object -Unique"
    ) % tun_device.replace("'", "''")
    try:
        import base64
        prelude = "[Console]::OutputEncoding=[Text.Encoding]::UTF8\n$ErrorActionPreference='SilentlyContinue'\n"
        enc = base64.b64encode((prelude + script).encode("utf-16le")).decode("ascii")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
            capture_output=True, encoding="utf-8", errors="replace", timeout=15,
        ).stdout.strip()
        if out:
            return [line.strip() for line in out.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    return []


def detect_ipv6_guard_label_mac():
    daemons = Path("/Library/LaunchDaemons")
    if not daemons.is_dir():
        return None
    try:
        matches = sorted(
            p.stem for p in daemons.glob("*ipv6*.plist")
            if p.is_file() and not p.stem.startswith("com.apple.")
        )
    except OSError:
        return None
    if not matches:
        return None
    if "local.ipv6-guard" in matches:
        return "local.ipv6-guard"
    return matches[0]


def _check_no_symlinks(target, stop_at):
    cur = target
    stop_resolved = stop_at.resolve()
    while True:
        if cur.is_symlink():
            raise RuntimeError("拒绝跟随符号链接: %s" % cur)
        if cur == stop_at or cur == cur.parent:
            break
        try:
            if cur.exists() and cur.resolve() == stop_resolved:
                break
        except OSError:
            pass
        cur = cur.parent


def supplement_claude_privacy(home=None, read_only=False):
    home = Path(home) if home else Path.home()
    claude_dir = home / ".claude"
    settings_path = claude_dir / "settings.json"
    _check_no_symlinks(settings_path, home)

    raw_bytes = None
    if settings_path.exists():
        if not settings_path.is_file():
            raise RuntimeError("settings.json 不是普通文件: %s" % settings_path)
        raw_bytes = settings_path.read_bytes()
        data = json.loads(raw_bytes.decode("utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
            raise RuntimeError("settings.json 或其 env 字段不是 JSON 对象: %s" % settings_path)
    else:
        data = {}

    env = dict(data.get("env") or {})
    missing_env = [k for k, _ in PRIVACY_ENV_DEFAULTS if k not in env]
    missing_top = [k for k, _ in PRIVACY_TOP_DEFAULTS if k not in data]
    missing_all = missing_env + missing_top

    if read_only or not missing_all:
        return {
            "path": str(settings_path),
            "changed": False,
            "backup": None,
            "added_keys": [],
            "missing_keys": missing_all,
        }

    claude_dir.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if raw_bytes is not None:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        fd, bk_name = tempfile.mkstemp(prefix="settings.privacy-backup-%s-" % stamp, suffix=".json", dir=str(claude_dir))
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        backup_path = Path(bk_name)
        if backup_path.read_bytes() != raw_bytes:
            raise RuntimeError("settings.json 备份校验失败: %s" % backup_path)

    new_data = dict(data)
    new_env = dict(new_data.get("env") or {})
    for k, v in PRIVACY_ENV_DEFAULTS:
        if k not in new_env:
            new_env[k] = v
    new_data["env"] = new_env
    for k, v in PRIVACY_TOP_DEFAULTS:
        if k not in new_data:
            new_data[k] = v

    serialized = json.dumps(new_data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".settings-supplement-", suffix=".json", dir=str(claude_dir))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        if raw_bytes is not None and settings_path.read_bytes() != raw_bytes:
            raise RuntimeError("settings.json 在写入期间被其他进程改动，已中止替换")
        os.replace(str(tmp_path), str(settings_path))
        if json.loads(settings_path.read_text(encoding="utf-8")) != new_data:
            raise RuntimeError("settings.json 写入后回读不一致")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return {
        "path": str(settings_path),
        "changed": True,
        "backup": str(backup_path) if backup_path else None,
        "added_keys": missing_all,
        "missing_keys": [],
    }


def run_auto_init(manifest_path=None, home=None, read_only=False, privacy_only=False, exit_node_override=None):
    manifest_path = Path(manifest_path) if manifest_path else (ROOT / "manifest.json")
    host = mc.Host()
    manifest = mc.load_manifest(str(manifest_path), host.platform)
    params = dict(manifest["params"])
    local_path = manifest_path.parent / "mirror.params.json"
    existing = {}
    if local_path.exists():
        existing = json.loads(local_path.read_text(encoding="utf-8-sig"))

    updated = dict(existing)
    clash_info = {"clash_reachable": False, "exit_group_present": False, "detected_node": None, "hint": None}

    if not privacy_only:
        merged_params = dict(params, **existing)
        clash_info = detect_clash_exit(host, merged_params)
        if exit_node_override:
            updated["exit_node"] = exit_node_override
        elif clash_info.get("exit_group_present") and clash_info.get("detected_node"):
            members = clash_info.get("group_members") or []
            if "exit_node" not in updated or (members and updated["exit_node"] not in members):
                updated["exit_node"] = clash_info["detected_node"]

        if "network_services" not in updated:
            if host.platform == "win32":
                svcs = detect_network_services_win(merged_params["tun_device"])
                if svcs:
                    updated["network_services"] = svcs
            else:
                svc = detect_network_service_mac()
                if svc:
                    updated["network_services"] = [svc]

        if host.platform != "win32" and "ipv6_guard_label" not in updated:
            label = detect_ipv6_guard_label_mac()
            if label and label != params["ipv6_guard_label"]:
                updated["ipv6_guard_label"] = label

        if not read_only and (updated != existing or not local_path.exists()):
            local_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    privacy = supplement_claude_privacy(home=home, read_only=read_only)
    return {
        "platform": host.platform,
        "params_file": str(local_path),
        "params_exists": local_path.exists(),
        "params_data": updated,
        "clash": clash_info,
        "privacy": privacy,
    }


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(ROOT / "manifest.json"))
    ap.add_argument("--exit-node", help="直接指定 Claude 固定出口节点名写入 mirror.params.json")
    ap.add_argument("--read-only", action="store_true", help="只探测不写入任何文件")
    ap.add_argument("--privacy-only", action="store_true", help="只备份并补齐 ~/.claude/settings.json 隐私静音开关")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        print("[ERROR] 请用普通桌面用户运行 auto_init.py，不要用 sudo", file=sys.stderr)
        return 2

    try:
        res = run_auto_init(
            manifest_path=args.manifest,
            read_only=args.read_only,
            privacy_only=args.privacy_only,
            exit_node_override=args.exit_node,
        )
    except Exception as exc:
        print("[ERROR] auto_init 失败: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print("=== claude-setup-kit 自动初始化（防漏傻瓜模式） ===")
    if not args.privacy_only:
        pdata = res["params_data"]
        if pdata.get("exit_node"):
            print("[OK] 本机参数 %s：%s" % (res["params_file"], json.dumps(pdata, ensure_ascii=False)))
        else:
            print("[待填] 尚未检测到 Clash 出口节点：请先打开 Clash Verge 或运行 `python3 scripts/auto_init.py --exit-node <你的节点名>`")
        if res["clash"].get("hint"):
            print("[提示] " + res["clash"]["hint"])
    priv = res["privacy"]
    if priv["changed"]:
        print("[OK] 已补齐 Claude 官方隐私静音开关（新增 %d 项，原配置已备份至 %s）" % (len(priv["added_keys"]), priv["backup"]))
    elif not priv["missing_keys"]:
        print("[OK] Claude 官方隐私静音开关 14 项已齐全（%s）" % priv["path"])
    else:
        print("[待补] Claude 官方隐私静音开关缺 %d 项：%s" % (len(priv["missing_keys"]), ", ".join(priv["missing_keys"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
