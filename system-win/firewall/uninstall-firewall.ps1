param([string]$Build)
. (Join-Path $PSScriptRoot 'common.ps1')
Need-Admin
$rules = Get-NetFirewallRule -DisplayName "$script:Prefix *" -ErrorAction SilentlyContinue
if (-not $rules) { Write-Output '没有 claude-setup-kit 的防火墙规则，无需卸载'; exit 0 }
$rules | Remove-NetFirewallRule
Write-Output "[OK] 已移除 $(@($rules).Count) 条 claude-setup-kit 防火墙规则（防火墙配置文件的启用状态保留）。"
