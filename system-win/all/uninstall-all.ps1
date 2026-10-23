# One-shot Windows uninstall: removes everything 一键安装全部 added and restores the recorded settings
# (firewall profiles, time zone, IPv6 bindings) from C:\ProgramData\claude-setup-kit\before.json.
param([Parameter(Mandatory = $true)][string]$Repo, [string]$Log)
. (Join-Path $PSScriptRoot '..\firewall\common.ps1')
Enter-Elevated $PSBoundParameters $PSCommandPath
Invoke-Logged $Log {
    Need-Admin
    Set-Location $Repo
    $root = 'C:\ProgramData\claude-setup-kit'
    $snapPath = "$root\before.json"
    if (-not (Test-Path $snapPath)) { throw "没有 $snapPath：不知道安装前是什么样，停止（不猜）" }
    $snap = Get-Content $snapPath -Raw -Encoding UTF8 | ConvertFrom-Json

    Write-Output '== 1/5 防火墙规则 =='
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'system-win\firewall\uninstall-firewall.ps1') 2>&1 | Out-String; $c = $LASTEXITCODE; Write-Output $o.TrimEnd(); if ($c -ne 0) { throw '卸载防火墙规则失败' }
    Write-Output '== 2/5 计划任务 =='
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo 'system-win\tasks\uninstall-tasks.ps1') -Only all 2>&1 | Out-String; $c = $LASTEXITCODE; Write-Output $o.TrimEnd(); if ($c -ne 0) { throw '卸载计划任务失败' }
    Write-Output '== 3/5 Chrome / Edge 策略 =='
    foreach ($p in @(@{ key = 'HKLM:\SOFTWARE\Policies\Google\Chrome'; existed = $snap.chrome_policy_existed }, @{ key = 'HKLM:\SOFTWARE\Policies\Microsoft\Edge'; existed = $snap.edge_policy_existed })) {
        if (Test-Path $p.key) {
            foreach ($v in 'WebRtcIPHandling', 'DnsOverHttpsMode') { if ((Get-Item $p.key).Property -contains $v) { Remove-ItemProperty -Path $p.key -Name $v } }
            if (-not $p.existed -and -not (Get-Item $p.key).Property -and -not (Get-ChildItem $p.key)) { Remove-Item $p.key }
        }
        Write-Output "[OK] $($p.key) 已恢复"
    }
    Write-Output '== 4/5 体检工具 =='
    $wall = Join-Path $env:LOCALAPPDATA 'claude-setup-kit'
    if (Test-Path $wall) { Remove-Item $wall -Recurse; Write-Output "[OK] 已删 $wall" } else { Write-Output '没有体检工具' }
    Write-Output '== 5/5 恢复防火墙配置文件、时区、IPv6 =='
    # -Enabled is a GpoBoolean: it takes the strings 'True'/'False', not a [bool].
    foreach ($fp in $snap.firewall_profiles) { Set-NetFirewallProfile -Profile $fp.name -Enabled $(if ($fp.enabled) { 'True' } else { 'False' }) }
    foreach ($fp in $snap.firewall_profiles) { if ([bool](Get-NetFirewallProfile -Profile $fp.name).Enabled -ne [bool]$fp.enabled) { throw "防火墙配置文件 $($fp.name) 没有恢复" } }
    Write-Output ('防火墙配置文件: ' + ((Get-NetFirewallProfile | ForEach-Object { $_.Name + '=' + $_.Enabled }) -join ', '))
    tzutil /s $snap.timezone; if ((Get-TimeZone).Id -ne $snap.timezone) { throw "时区没有恢复成 $($snap.timezone)" }
    Write-Output "时区: $((Get-TimeZone).Id)"
    foreach ($b in $snap.ipv6_binding) {
        $now = Get-NetAdapterBinding -Name $b.adapter -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue
        if ($now -and [bool]$now.Enabled -ne [bool]$b.enabled) {
            if ($b.enabled) { Enable-NetAdapterBinding -Name $b.adapter -ComponentID ms_tcpip6 } else { Disable-NetAdapterBinding -Name $b.adapter -ComponentID ms_tcpip6 -Confirm:$false }
            Write-Output "IPv6 $($b.adapter) -> $($b.enabled)"
        }
    }
    $kept = "$env:USERPROFILE\claude-setup-kit-uninstalled-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Move-Item $root $kept
    Write-Output "[OK] 已全部撤回。守护历史与安装前快照移到 $kept（可自行删除）。Clash 的 TUN 请在 Clash Verge 里自己关。"
}
