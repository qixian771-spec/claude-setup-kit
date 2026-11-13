# claude-setup-kit ipv6-guard (Windows): every minute as SYSTEM, keep IPv6 unbound on all physical adapters.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Adapter = '{{WIFI_IFACE}}'
$Tun = '{{TUN}}'
$Log = 'C:\ProgramData\claude-setup-kit\ipv6-guard.log'
$targets = @($Adapter) + @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne $Tun -and $_.HardwareInterface -eq $true } | ForEach-Object { $_.Name }) | Select-Object -Unique
foreach ($name in $targets) {
    $b = Get-NetAdapterBinding -Name $name -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue
    if ($b -and $b.Enabled) {
        Disable-NetAdapterBinding -Name $name -ComponentID ms_tcpip6 -Confirm:$false
        Add-Content $Log ("[{0}] {1} 的 IPv6 绑定被打开过，已重新关闭" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $name) -Encoding UTF8
    }
}
