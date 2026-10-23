# Installs the watch and/or ipv6-guard scheduled tasks (SYSTEM, every minute) from a render.py build dir.
param([Parameter(Mandatory = $true)][string]$Build, [ValidateSet('watch', 'ipv6-guard', 'all')][string]$Only = 'all')
. (Join-Path $PSScriptRoot '..\firewall\common.ps1')
Need-Admin
$P = Read-Params $Build
$Root = 'C:\ProgramData\claude-setup-kit'
$wanted = if ($Only -eq 'all') { @('watch', 'ipv6-guard') } else { @($Only) }
foreach ($t in $wanted) {
    if (Get-ScheduledTask -TaskName "claude-setup-kit $t" -ErrorAction SilentlyContinue) { throw "已存在，拒绝覆盖: 计划任务 claude-setup-kit $t（要重装先运行 卸载）" }
    if (Test-Path "$Root\$t.ps1") { throw "已存在，拒绝覆盖: $Root\$t.ps1" }
}
if ($wanted -contains 'ipv6-guard') { Assert-Physical $P }
if (-not (Test-Path $Root)) { New-Item -ItemType Directory -Path $Root | Out-Null }
# Scripts run as SYSTEM: only administrators may write them.
$acl = Get-Acl $Root; $acl.SetAccessRuleProtection($true, $false)
foreach ($id in 'NT AUTHORITY\SYSTEM', 'BUILTIN\Administrators') { $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($id, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))) }
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule('BUILTIN\Users', 'ReadAndExecute', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
Set-Acl $Root $acl
foreach ($t in $wanted) {
    Copy-Item (Join-Path $Build "system-win\tasks\$t.ps1") "$Root\$t.ps1"
    if (Select-String -Path "$Root\$t.ps1" -Pattern '\{\{[A-Z_]+\}\}' -Quiet) { Remove-Item "$Root\$t.ps1"; throw "$t.ps1 还有未渲染的占位符" }
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Root\$t.ps1`""
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable
    Register-ScheduledTask -TaskName "claude-setup-kit $t" -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
    Start-ScheduledTask -TaskName "claude-setup-kit $t"
}
if ($wanted -contains 'ipv6-guard') {
    Start-Sleep -Seconds 5
    if ((Get-NetAdapterBinding -Name $P['WIFI_IFACE'] -ComponentID ms_tcpip6).Enabled) { throw "IPv6 绑定没有被关掉（看 $Root\ipv6-guard.log）" }
    Write-Output "[OK] $($P['WIFI_IFACE']) 的 IPv6 已解绑，计划任务 claude-setup-kit ipv6-guard 每分钟复查。"
}
if ($wanted -contains 'watch') {
    Start-Sleep -Seconds 8
    if (-not (Test-Path "$Root\watch\last")) { throw "守护跑过一次后没有写结果（看计划任务 claude-setup-kit watch 的历史）" }
    Write-Output "[OK] 自检守护已装（每分钟）。最近一次："
    Get-Content "$Root\watch\last" -Encoding UTF8
}
