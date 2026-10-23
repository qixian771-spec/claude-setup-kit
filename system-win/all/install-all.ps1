# One-shot Windows install: firewall rules, watch + IPv6 tasks, Chrome/Edge policies, claude-wall.ps1, time zone.
# Run elevated from the repo root (installers\win\一键安装全部.cmd does that). Before touching anything it records
# the settings it is about to change in C:\ProgramData\claude-setup-kit\before.json, which 一键撤回全部 restores.
# Stops at the first failure; nothing is retried or skipped.
param([Parameter(Mandatory = $true)][string]$Repo, [string]$Log)
. (Join-Path $PSScriptRoot '..\firewall\common.ps1')
Enter-Elevated $PSBoundParameters $PSCommandPath
Invoke-Logged $Log {
    Need-Admin
    # Everything below renders and installs for the current identity. If UAC was answered as another administrator,
    # the firewall SID and the per-user tools would belong to that account: stop before touching anything.
    $console = (Get-CimInstance Win32_ComputerSystem).UserName
    if (-not $console) { throw '无法确定桌面登录用户（例如远程桌面会话）：一键安装需要在本机桌面上运行' }
    $me = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $csid = (New-Object System.Security.Principal.NTAccount($console)).Translate([System.Security.Principal.SecurityIdentifier]).Value
    if ($csid -ne $me.User.Value) { throw "UAC 用的是 $($me.Name)，不是桌面用户 $console：一键安装会把规则和工具装给错误的账号。请让桌面用户自己是管理员，或分步双击各安装器" }
    Set-Location $Repo
    $root = 'C:\ProgramData\claude-setup-kit'
    if (-not (Test-Path $root)) { New-Item -ItemType Directory -Path $root | Out-Null }

    function Step([string]$Title, [scriptblock]$Body) {
        Write-Output ""; Write-Output "== $Title =="
        & $Body
    }
    function Render([string]$Component) {
        $out = & py -3 scripts\render.py --component $Component 2>&1
        if ($LASTEXITCODE -ne 0) { throw "render $Component 失败: $($out -join ' ')" }
        $dir = ($out | Select-Object -First 1).ToString().Trim()
        if (-not (Test-Path (Join-Path $dir 'PARAMS.txt'))) { throw "render $Component 没有产出目录" }
        return $dir
    }
    function RunPs([string]$Script, [string[]]$Arguments) {
        # Capture, then print: child output written straight to the console is transcribed garbled (doubled CJK).
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments 2>&1 | Out-String
        $code = $LASTEXITCODE
        Write-Output $out.TrimEnd()
        if ($code -ne 0) { throw "$([IO.Path]::GetFileName($Script)) 退出码 $code" }
    }

    Step '0/6 记录安装前状态（一键撤回照它恢复）' {
        $snap = "$root\before.json"
        if (Test-Path $snap) { Write-Output "已有 $snap（保留最早的那份，不覆盖）" } else {
            $s = [ordered]@{
                taken = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                firewall_profiles = @(Get-NetFirewallProfile | ForEach-Object { [ordered]@{ name = $_.Name; enabled = [bool]$_.Enabled } })
                timezone = (Get-TimeZone).Id
                ipv6_binding = @(Get-NetAdapterBinding -ComponentID ms_tcpip6 | ForEach-Object { [ordered]@{ adapter = $_.Name; enabled = [bool]$_.Enabled } })
                chrome_policy_existed = [bool](Test-Path 'HKLM:\SOFTWARE\Policies\Google\Chrome')
                edge_policy_existed = [bool](Test-Path 'HKLM:\SOFTWARE\Policies\Microsoft\Edge')
            }
            [IO.File]::WriteAllText($snap, ($s | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding $false))
            Write-Output "已写入 $snap"
        }
    }
    # Steps already installed by an earlier run are verified and skipped, so the one-click run can be resumed.
    Step '1/6 防火墙规则' {
        if (@(Get-NetFirewallRule -DisplayName 'claude-setup-kit: *' -ErrorAction SilentlyContinue | Where-Object Enabled -eq 'True').Count -eq 8) { Write-Output '已装（8 条规则都在且启用），跳过' }
        else { $b = Render 'win-firewall'; RunPs (Join-Path $b 'system-win\firewall\install-firewall.ps1') @('-Build', $b) }
    }
    Step '2/6 自检守护 + IPv6 守护（计划任务）' {
        $have = @('watch', 'ipv6-guard' | Where-Object { Get-ScheduledTask -TaskName "claude-setup-kit $_" -ErrorAction SilentlyContinue })
        $need = @('watch', 'ipv6-guard' | Where-Object { $have -notcontains $_ })
        if ($have) { Write-Output ('已装，跳过: ' + ($have -join ', ')) }
        if ($need.Count -eq 2) { $only = 'all' } elseif ($need.Count -eq 1) { $only = $need[0] } else { $only = $null }
        if ($only) { $b = Render 'win-tasks'; RunPs (Join-Path $b 'system-win\tasks\install-tasks.ps1') @('-Build', $b, '-Only', $only) }
    }
    Step '3/6 Chrome / Edge 策略' {
        # Same two values as installers\win\*策略.reg, written directly: reg.exe cannot open the Chinese-named .reg files.
        foreach ($key in 'HKLM:\SOFTWARE\Policies\Google\Chrome', 'HKLM:\SOFTWARE\Policies\Microsoft\Edge') {
            if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
            New-ItemProperty -Path $key -Name 'WebRtcIPHandling' -Value 'disable_non_proxied_udp' -PropertyType String -Force | Out-Null
            New-ItemProperty -Path $key -Name 'DnsOverHttpsMode' -Value 'off' -PropertyType String -Force | Out-Null
            $v = Get-ItemProperty -Path $key
            if ($v.WebRtcIPHandling -ne 'disable_non_proxied_udp' -or $v.DnsOverHttpsMode -ne 'off') { throw "$key 写入后回读不对" }
            Write-Output "[OK] $key：WebRtcIPHandling=disable_non_proxied_udp，DnsOverHttpsMode=off"
        }
    }
    $script:ToolsBuild = $null
    Step '4/6 体检工具 claude-wall.ps1' {
        $script:ToolsBuild = Render 'win-tools'
        if (Test-Path (Join-Path $env:LOCALAPPDATA 'claude-setup-kit\claude-wall.ps1')) { Write-Output '已装，跳过' }
        else { RunPs (Join-Path $script:ToolsBuild 'system-win\tools\install-tools.ps1') @('-Build', $script:ToolsBuild) }
    }
    Step '5/6 时区' { RunPs (Join-Path $script:ToolsBuild 'system-win\tools\set-timezone.ps1') @('-Build', $script:ToolsBuild) }
    Step '6/6 完成' { Write-Output '[OK] 全部组件已安装。撤回：双击 installers\win\一键撤回全部.cmd' }
}
