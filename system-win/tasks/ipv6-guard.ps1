# claude-setup-kit ipv6-guard (Windows): every minute as SYSTEM, keep IPv6 unbound on the physical adapter.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Adapter = '{{WIFI_IFACE}}'
$Log = 'C:\ProgramData\claude-setup-kit\ipv6-guard.log'
$b = Get-NetAdapterBinding -Name $Adapter -ComponentID ms_tcpip6
if ($b.Enabled) {
    Disable-NetAdapterBinding -Name $Adapter -ComponentID ms_tcpip6 -Confirm:$false
    Add-Content $Log ("[{0}] {1} 的 IPv6 绑定被打开过，已重新关闭" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Adapter) -Encoding UTF8
}
