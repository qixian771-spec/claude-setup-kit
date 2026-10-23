# claude-wall.ps1 (Windows): health check for the claude-setup-kit protections. Read-only.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\claude-setup-kit\claude-wall.ps1" [status|watch]
# Exit 0 = everything healthy, 6 = the watch task is missing/stale/not OK, 1 = a protection is missing.
param([ValidateSet('status', 'watch')][string]$Mode = 'status')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Tun = '{{TUN}}'
$Rules = 'net-wall v4', 'net-wall v6', 'leak-guard dns udp', 'leak-guard dns tcp', 'leak-guard stun udp', 'leak-guard stun tcp', 'leak-guard user-public tcp', 'leak-guard user-public udp'
$code = 0
if ($Mode -eq 'status') {
    $missing = @($Rules | Where-Object { $r = Get-NetFirewallRule -DisplayName "claude-setup-kit: $_" -ErrorAction SilentlyContinue; -not $r -or -not $r.Enabled })
    if ($missing.Count) { "防火墙: 缺 $($missing.Count) 条规则（$($missing -join ', ')）"; $code = 1 } else { "防火墙: $($Rules.Count) 条规则齐全并启用" }
    $off = @(Get-NetFirewallProfile | Where-Object { -not $_.Enabled } | ForEach-Object Name)
    if ($off.Count) { "防火墙配置文件未启用: $($off -join ', ')"; $code = 1 }
    if (Get-NetAdapter -Name $Tun -ErrorAction SilentlyContinue) { "TUN: $Tun 在" } else { "TUN: $Tun 不在（Clash 没开 TUN）"; if ($code -eq 0) { $code = 1 } }
    try {
        $ips = @(Resolve-DnsName -Name www.cloudflare.com -Type A -Server 127.0.0.1 -DnsOnly -QuickTimeout | Where-Object Type -eq 'A' | ForEach-Object IPAddress)
        if ($ips -and ($ips | Where-Object { $_ -like '198.18.*' -or $_ -like '198.19.*' })) { "DNS: fake-ip 正常" } else { "DNS: 127.0.0.1:53 应答不是 fake-ip ($($ips -join ','))"; $code = 1 }
    } catch { "DNS: 127.0.0.1:53 无应答（Clash 没在运行？）"; $code = 1 }
}
$last = 'C:\ProgramData\claude-setup-kit\watch\last'
if (-not (Test-Path $last)) { "守护: 未安装或还没有结果（$last）"; exit 6 }
$line = (Get-Content $last -Encoding UTF8 -Raw).Trim(); $parts = $line -split "`t"
$age = [int]((Get-Date).ToUniversalTime() - [datetime]::ParseExact($parts[0], 'yyyy-MM-ddTHH:mm:ssZ', $null, 'AssumeUniversal')).TotalSeconds
if ($Mode -eq 'watch') {
    "最近一次: $line"
    $hist = 'C:\ProgramData\claude-setup-kit\watch\history.log'
    if (Test-Path $hist) { "24 小时内非 OK 记录:"; $since = (Get-Date).ToUniversalTime().AddHours(-24).ToString('yyyy-MM-ddTHH:mm:ssZ'); Get-Content $hist -Encoding UTF8 | Where-Object { $_ -ge $since -and $_ -notmatch "`tOK`t" } | Select-Object -Last 5 | ForEach-Object { "  $_" } }
}
if ($age -gt 180) { "守护: 最近一次结果是 $age 秒前（$($parts[0])），守护可能没在运行"; exit 6 }
if ($parts[1] -ne 'OK') { "守护: $($parts[1])（$($parts[0])）$($parts[2])"; exit 6 }
"守护: 正常（$($parts[0])）"
exit $code
