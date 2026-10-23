# Shared helpers for the Windows installers. Dot-sourced by install-*.ps1 / uninstall-*.ps1.
# Every script is run elevated by its .cmd launcher and takes -Build <render.py output dir>.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$script:Prefix = 'claude-setup-kit:'

function Need-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw '需要管理员权限（双击 installers\win 里的 .cmd 会自动提权）'
    }
}

function Read-Params([string]$Build) {
    if (-not $Build -or -not (Test-Path (Join-Path $Build 'PARAMS.txt'))) { throw "用法: -Build <render.py 输出目录>（缺 PARAMS.txt）" }
    $h = @{}
    Get-Content (Join-Path $Build 'PARAMS.txt') -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=(.*)$') { $h[$matches[1]] = $matches[2] }
    }
    foreach ($k in 'USER', 'USER_SID', 'WIFI_IFACE', 'TUN') { if (-not $h[$k]) { throw "PARAMS.txt 缺 $k" } }
    return $h
}

function Rule-Name([string]$Name) { return "$script:Prefix $Name" }

function Refuse-Existing([string[]]$Names) {
    foreach ($n in $Names) {
        if (Get-NetFirewallRule -DisplayName (Rule-Name $n) -ErrorAction SilentlyContinue) {
            throw "已存在，拒绝覆盖: $(Rule-Name $n)（要重装先运行 卸载）"
        }
    }
}

function Assert-Rule([string]$Name) {
    $r = Get-NetFirewallRule -DisplayName (Rule-Name $Name)
    if (-not $r.Enabled -or $r.Action -ne 'Block' -or $r.Direction -ne 'Outbound') { throw "装后验证失败: $(Rule-Name $Name)" }
}

# The interface-scoped outbound block must never touch the TUN adapter: refuse if the alias is the TUN.
function Assert-Physical([hashtable]$P) {
    if ($P['WIFI_IFACE'] -eq $P['TUN']) { throw "网卡别名不能是 TUN 适配器（$($P['TUN'])）" }
    if (-not (Get-NetAdapter -Name $P['WIFI_IFACE'] -ErrorAction SilentlyContinue)) { throw "找不到网卡 $($P['WIFI_IFACE'])（用 --param network_services= 指定）" }
}

# Self-elevation: .cmd launchers call the worker with -File (no nested quoting); a non-admin run relaunches the
# same script through UAC with the same parameters, waits, and exits with the elevated run's exit code.
# If UAC is cancelled Start-Process throws and the script stops — nothing was changed.
function Enter-Elevated([System.Collections.IDictionary]$Bound, [string]$ScriptPath) {
    $pr = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if ($pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { return }
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $ScriptPath + '"'))
    foreach ($k in $Bound.Keys) { $argList += "-$k"; $argList += ('"' + [string]$Bound[$k] + '"') }
    $proc = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList $argList
    exit $proc.ExitCode
}

# Runs the body with its output transcribed to $Log (UTF-8). A failure is written as [ERROR] and exits 1;
# the last line is always EXIT=<code> so whoever reads the log can judge it.
function Invoke-Logged([string]$Log, [scriptblock]$Body) {
    if ($Log) { Start-Transcript -Path $Log -Append | Out-Null }
    $code = 0
    try { & $Body } catch { Write-Output ('[ERROR] ' + $_.Exception.Message); $code = 1 }
    Write-Output "EXIT=$code"
    if ($Log) { Stop-Transcript | Out-Null }
    exit $code
}
