param([string]$Build, [ValidateSet('watch', 'ipv6-guard', 'all')][string]$Only = 'all')
. (Join-Path $PSScriptRoot '..\firewall\common.ps1')
Need-Admin
$Root = 'C:\ProgramData\claude-setup-kit'
$wanted = if ($Only -eq 'all') { @('watch', 'ipv6-guard') } else { @($Only) }
foreach ($t in $wanted) {
    if (Get-ScheduledTask -TaskName "claude-setup-kit $t" -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName "claude-setup-kit $t" -Confirm:$false }
    if (Test-Path "$Root\$t.ps1") { Remove-Item "$Root\$t.ps1" }
}
Write-Output "[OK] 已移除计划任务: $($wanted -join ', ')（$Root 下的日志与 watch 历史保留；IPv6 保持当前状态）。"
