# claude-setup-kit watch (Windows): runs as SYSTEM every minute from the scheduled task.
# Checks the firewall rules, the TUN adapter, Clash mode/exit (named pipe) and writes
# C:\ProgramData\claude-setup-kit\watch\last (+ history.log). Only alerts; never changes rules.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Dir = 'C:\ProgramData\claude-setup-kit\watch'
$Tun = '{{TUN}}'
$ExpectedExit = '{{EXIT_NODE}}'
$ExitGroup = '{{EXIT_GROUP}}'
$Rules = 'net-wall v4', 'net-wall v6', 'leak-guard dns udp', 'leak-guard dns tcp', 'leak-guard stun udp', 'leak-guard stun tcp', 'leak-guard user-public tcp', 'leak-guard user-public udp'
$state = 'OK'; $notes = @()
function Raise([string]$s) { $order = @{ OK = 0; WARN = 1; FAILED = 2 }; if ($order[$s] -gt $order[$script:state]) { $script:state = $s } }

if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Path $Dir | Out-Null }
$missing = @()
foreach ($n in $Rules) {
    $r = Get-NetFirewallRule -DisplayName "claude-setup-kit: $n" -ErrorAction SilentlyContinue
    if (-not $r -or -not $r.Enabled) { $missing += $n }
}
if ($missing.Count -gt 0) { Raise 'FAILED'; $notes += "防火墙规则缺失或被禁用: $($missing -join ', ')（重新双击 安装防火墙规则.cmd）" }
$profiles = Get-NetFirewallProfile | Where-Object { -not $_.Enabled } | ForEach-Object Name
if ($profiles) { Raise 'FAILED'; $notes += "防火墙配置文件未启用: $($profiles -join ', ')" }
if (-not (Get-NetAdapter -Name $Tun -ErrorAction SilentlyContinue)) { Raise 'WARN'; $notes += "Clash TUN（$Tun）不在：本用户公网会被防火墙拦截而断网，请检查 Clash" }

function Clash-Get([string]$Path) {
    $pipe = New-Object System.IO.Pipes.NamedPipeClientStream('.', 'verge-mihomo', [System.IO.Pipes.PipeDirection]::InOut)
    try {
        $pipe.Connect(2000)
        $bytes = [System.Text.Encoding]::ASCII.GetBytes("GET $Path HTTP/1.1`r`nHost: localhost`r`nConnection: close`r`n`r`n")
        $pipe.Write($bytes, 0, $bytes.Length); $pipe.Flush()
        $reader = New-Object System.IO.StreamReader($pipe, [System.Text.Encoding]::UTF8)
        $raw = $reader.ReadToEnd()
    } finally { $pipe.Dispose() }
    $idx = $raw.IndexOf("`r`n`r`n")
    if ($idx -lt 0 -or $raw -notmatch '^HTTP/1\.\d 200') { throw "controller returned: $($raw.Split("`n")[0])" }
    return ($raw.Substring($idx + 4) | ConvertFrom-Json)
}
try {
    $cfg = Clash-Get '/configs'
    if ($cfg.mode -ne 'rule') { Raise 'WARN'; $notes += "Clash 不是「规则」模式（当前: $($cfg.mode)）" }
    $grp = Clash-Get ('/proxies/' + [uri]::EscapeDataString($ExitGroup))
    if ($grp.now -ne $ExpectedExit) { Raise 'WARN'; $notes += "$ExitGroup 不是 $ExpectedExit（当前: $($grp.now)）" }
} catch { Raise 'WARN'; $notes += "Clash 控制接口查询失败（Clash 没在运行？）: $($_.Exception.Message)" }

$stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$message = if ($notes.Count) { $notes -join '；' } else { '全部正常' }
$line = "$stamp`t$state`t$message"
$previous = if (Test-Path "$Dir\last") { (Get-Content "$Dir\last" -Encoding UTF8 -Raw).Trim() } else { '' }
[System.IO.File]::WriteAllText("$Dir\last", "$line`n", (New-Object System.Text.UTF8Encoding $false))
[System.IO.File]::AppendAllText("$Dir\history.log", "$line`n", (New-Object System.Text.UTF8Encoding $false))
$lastNotify = if (Test-Path "$Dir\last-notify") { [int64](Get-Content "$Dir\last-notify") } else { 0 }
$now = [int64][double]::Parse((Get-Date -UFormat %s))
if ($state -ne 'OK' -and (($previous -notmatch [regex]::Escape("$state`t$message")) -or ($now - $lastNotify) -ge 1800)) {
    Start-Process -FilePath 'msg.exe' -ArgumentList @('*', '/TIME:30', "网络防护 $state：$message") -WindowStyle Hidden -ErrorAction SilentlyContinue
    Set-Content "$Dir\last-notify" $now
}
