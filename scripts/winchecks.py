"""Windows 10/11 variants of the mirror_check checks (PowerShell queries, read-only).

Every function has the same signature as in mirror_check: (host, params, args) -> (status, evidence).
Names here override the common table when the platform is win32; new Windows-only checks are added.
"""
import ipaddress
import json
import re

import mirror_check as mc  # rebound by mirror_check.platform_checks() when it runs as __main__

PASS, FAIL, UNKNOWN, INFO = mc.PASS, mc.FAIL, mc.UNKNOWN, mc.INFO


def _ps_json(host, script, tag):
    out = host.ps(script + " | ConvertTo-Json -Compress -Depth 4", tag=tag).strip()
    if not out:
        return None
    return json.loads(out)


def _lines(host, script, tag):
    return [l.strip() for l in host.ps(script, tag=tag).splitlines() if l.strip()]


def _q(value):
    return "'" + str(value).replace("'", "''") + "'"


def check_tun_iface(host, p, a):
    try:
        ips = _lines(host, "Get-NetIPAddress -InterfaceAlias %s -AddressFamily IPv4 | ForEach-Object IPAddress" % _q(p["tun_device"]), "tun")
    except mc.HostError:
        return FAIL, "TUN 适配器 %s 不存在（Clash 的 TUN 没开）" % p["tun_device"]
    if p["tun_inet4"] not in ips:
        return FAIL, "%s 没有地址 %s（有 %s）" % (p["tun_device"], p["tun_inet4"], ips)
    return PASS, "%s %s" % (p["tun_device"], p["tun_inet4"])


def _resolve(host, name, server=None, tcp=False, tag="dns"):
    cmd = "Resolve-DnsName -Name %s -Type A -DnsOnly -QuickTimeout" % _q(name)
    if server:
        cmd += " -Server %s" % _q(server)
    if tcp:
        cmd += " -TcpOnly"
    cmd += " | Where-Object { $_.Type -eq 'A' } | ForEach-Object IPAddress"
    return _lines(host, cmd, tag)


def check_dns_local53(host, p, a):
    net = ipaddress.ip_network(p["fake_ip_prefix"])
    results = {}
    for label, tcp in (("udp", False), ("tcp", True)):
        try:
            results[label] = _resolve(host, p["probe_domain"], "127.0.0.1", tcp, "dns-" + label)
        except mc.HostError as exc:
            return FAIL, "127.0.0.1:53 %s 查询失败: %s" % (label, exc)
    bad = {k: v for k, v in results.items() if not v or not all(ipaddress.ip_address(i) in net for i in v)}
    if bad:
        return FAIL, "127.0.0.1:53 应答不是 fake-ip: %s" % bad
    try:
        sys_ips = _resolve(host, p["probe_domain"], tag="dns-system")
    except mc.HostError as exc:
        return FAIL, "系统解析失败: %s" % exc
    if not sys_ips or not all(ipaddress.ip_address(i) in net for i in sys_ips):
        return FAIL, "系统解析 %s 没走 Clash: %s" % (p["probe_domain"], sys_ips)
    return PASS, "udp=%s tcp=%s 系统解析=%s（均在 %s）" % (results["udp"], results["tcp"], sys_ips, net)


def check_system_dns(host, p, a):
    found = {}
    for svc in p["network_services"]:
        found[svc] = _lines(host, "Get-DnsClientServerAddress -InterfaceAlias %s -AddressFamily IPv4 | ForEach-Object { $_.ServerAddresses }" % _q(svc), "sysdns")
    accept = set(p.get("system_dns_accept") or [])
    if not accept:
        return INFO, "%s（Windows 的受管 DNS 值待 W2 实机确定，本项仅记录）" % found
    bad = {s: v for s, v in found.items() if not v or not set(v) <= accept}
    if bad:
        return FAIL, "不在接受列表 %s: %s" % (sorted(accept), bad)
    return PASS, "%s（接受值; 真实路径由 dns.local53 保证）" % found


def check_ipv6_off(host, p, a):
    problems, seen = [], []
    for svc in p["network_services"]:
        enabled = _lines(host, "(Get-NetAdapterBinding -Name %s -ComponentID ms_tcpip6).Enabled" % _q(svc), "ipv6-binding")
        state = (enabled[0] if enabled else "?")
        seen.append("%s IPv6 绑定=%s" % (svc, state))
        if state.lower() != "false":
            problems.append("%s 的 IPv6 绑定仍启用" % svc)
        # No IPv6 address at all is the good case: query quietly and exit 0 so an empty result is not an error.
        globals6 = _lines(host, "$a = @(Get-NetIPAddress -InterfaceAlias %s -AddressFamily IPv6 -ErrorAction SilentlyContinue); $a | Where-Object { $_.IPAddress -notlike 'fe80*' } | ForEach-Object IPAddress; exit 0" % _q(svc), "ipv6-addr")
        if globals6:
            problems.append("%s 有全局 IPv6 %s" % (svc, globals6))
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, ", ".join(seen) + "，无全局 IPv6"


def _registry_policy(host, p, key, want, app, label):
    if host.lstat(app) is None:
        return INFO, "未安装 %s（%s），跳过" % (label, app)
    try:
        data = _ps_json(host, "Get-ItemProperty -Path %s | Select-Object %s" % (_q(key), ",".join(want)), "reg-" + label)
    except mc.HostError:
        return FAIL, "注册表 %s 不存在（没有 %s 策略）" % (key, label)
    bad = {k: (data or {}).get(k) for k, v in want.items() if (data or {}).get(k) != v}
    if bad:
        return FAIL, "%s 值不对: %s" % (key, bad)
    return PASS, "%s %s" % (key, want)


def check_chrome_policy(host, p, a):
    return _registry_policy(host, p, p["chrome_policy_key"], p["chrome_policy"], p["chrome_app"], "Chrome")


def check_registry_policy(host, p, a):
    return _registry_policy(host, p, a["key"], p[a.get("values_param", "chrome_policy")], a["app"], a.get("label", a["key"]))


def check_firewall_enabled(host, p, a):
    data = _ps_json(host, "Get-NetFirewallProfile | Select-Object Name,Enabled", "fw-profile") or []
    if isinstance(data, dict):
        data = [data]
    off = [d["Name"] for d in data if not d.get("Enabled")]
    if off:
        return FAIL, "防火墙配置文件未启用: %s（规则在这些网络类型下不生效）" % off
    return PASS, "Domain/Private/Public 全部启用"


def check_firewall_rules(host, p, a):
    problems, seen = [], []
    for rule in a["rules"]:
        name = p["firewall_prefix"] + " " + rule["name"]
        try:
            # Enums as strings: ConvertTo-Json would otherwise emit numbers (Enabled True=1, Action Block=4, Direction Outbound=2).
            data = _ps_json(host, "Get-NetFirewallRule -DisplayName %s | Select-Object DisplayName,"
                                  "@{n='Enabled';e={[string]$_.Enabled}},@{n='Action';e={[string]$_.Action}},@{n='Direction';e={[string]$_.Direction}}" % _q(name), "fw-rule")
        except mc.HostError:
            problems.append("缺规则 %s" % name)
            continue
        if isinstance(data, list):
            data = data[0] if data else {}
        if data.get("Enabled") != "True" or data.get("Action") != rule["action"] or data.get("Direction") != rule["direction"]:
            problems.append("%s 状态不对: %s" % (name, data))
        seen.append(name)
    if problems:
        return FAIL, "; ".join(problems)
    return PASS, "%d 条规则存在且启用" % len(seen)


def check_scheduled_task(host, p, a):
    name = p["task_prefix"] + " " + a["name"]
    try:
        data = _ps_json(host, "$t = Get-ScheduledTask -TaskName %s; $i = $t | Get-ScheduledTaskInfo; [pscustomobject]@{State=[string]$t.State; LastTaskResult=$i.LastTaskResult; LastRunTime=[string]$i.LastRunTime}" % _q(name), "task")
    except mc.HostError:
        return FAIL, "计划任务 %s 不存在" % name
    accept = a.get("accept_result", [0, 267009])
    if data.get("State") not in ("Ready", "Running"):
        return FAIL, "%s 状态 %s" % (name, data.get("State"))
    if data.get("LastTaskResult") not in accept:
        return FAIL, "%s 最近结果 %s（接受 %s）" % (name, data.get("LastTaskResult"), accept)
    return PASS, "%s %s，最近结果 %s，上次运行 %s" % (name, data.get("State"), data.get("LastTaskResult"), data.get("LastRunTime"))


def check_watch_fresh(host, p, a):
    path = a.get("dir_win", p["watch_dir"]) + "\\last"
    try:
        text = host.read_text(path)
    except mc.HostError as exc:
        return FAIL, str(exc)
    parts = text.strip().split("\t")
    if len(parts) < 2:
        return FAIL, "last 格式异常: %r" % text
    age = (host.now() - mc._parse_iso(parts[0])).total_seconds()
    if age > p["watch_max_age_s"]:
        return FAIL, "最近记录 %.0f 秒前（上限 %s）" % (age, p["watch_max_age_s"])
    if parts[1] != "OK":
        return FAIL, "最近状态 %s: %s" % (parts[1], parts[2] if len(parts) > 2 else "")
    return PASS, "%s OK（%.0f 秒前）" % (parts[0], age)


def _nslookup_txt(host, name, server, chaos=False):
    argv = ["nslookup"] + (["-class=chaos"] if chaos else []) + ["-type=txt", name, server]
    rc, out, _ = host.run(argv, timeout=20)
    values = re.findall(r'"([^"]+)"', out)
    return values


def check_dns_upstream(host, p, a):
    data = mc._trace(host, p)
    who = _nslookup_txt(host, "whoami.cloudflare", "1.1.1.1", chaos=True)
    who_ip = who[0] if who else ""
    resolver = _nslookup_txt(host, "o-o.myaddr.l.google.com", "ns1.google.com")
    resolver_ip = next((x for x in resolver if "edns" not in x), "")
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
    rc, out, _ = host.run(["tzutil", "/g"])
    zone = out.strip()
    if zone in p["timezone_forbid_win"]:
        return FAIL, "时区 %s" % zone
    return PASS, "时区 %s" % zone


def check_language(host, p, a):
    langs = _lines(host, "(Get-WinUserLanguageList).LanguageTag", "lang")
    first = langs[0] if langs else "?"
    note = "ippure 浏览器语言项 +24 分" if first.lower().startswith("zh") else "ippure 浏览器语言项 0 分"
    return INFO, "语言顺序 %s；首位 %s（%s；可选步骤，不改也算通过）" % (langs, first, note)


CHECKS = {name[len("check_"):]: fn for name, fn in globals().items() if name.startswith("check_")}
