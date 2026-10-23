# Windows counterpart of PF anchors 011 + 020: on the PHYSICAL adapter only, block outbound
# traffic to Anthropic's networks, to DNS/DoT and STUN ports, and (for this user's SID) to every
# public address. The TUN adapter is not touched, so everything that goes through Clash still works.
param([Parameter(Mandatory = $true)][string]$Build, [string]$Log)
. (Join-Path $PSScriptRoot 'common.ps1')
Enter-Elevated $PSBoundParameters $PSCommandPath
Invoke-Logged $Log {
    Need-Admin
    $P = Read-Params $Build
    Assert-Physical $P
    $iface = $P['WIFI_IFACE']; $sid = $P['USER_SID']
    # The user-public rules key on USER_SID. When UAC was answered with another administrator's password the
    # elevated process renders as that admin, so refuse unless the SID is the desktop (console) user's.
    $console = (Get-CimInstance Win32_ComputerSystem).UserName
    if ($console) {
        $csid = (New-Object System.Security.Principal.NTAccount($console)).Translate([System.Security.Principal.SecurityIdentifier]).Value
        if ($csid -ne $sid) { throw "USER_SID $sid 不是桌面登录用户 $console（$csid）：UAC 用了另一个管理员账号，渲染拿到的是它的 SID。请在桌面用户自己的账号下双击 安装防火墙规则.cmd（它在提权前渲染），不要用一键安装" }
    }

    $names = 'net-wall v4', 'net-wall v6', 'leak-guard dns udp', 'leak-guard dns tcp', 'leak-guard stun udp', 'leak-guard stun tcp', 'leak-guard user-public tcp', 'leak-guard user-public udp'
    Refuse-Existing $names

    # The user-public rules only make sense when the Clash core runs as SYSTEM (service mode); otherwise it
    # would block the core itself and this machine would lose all public connectivity.
    $svc = Get-Service clash_verge_service -ErrorAction SilentlyContinue
    if (-not $svc -or $svc.Status -ne 'Running') { throw 'Clash Verge 服务模式没有在运行（clash_verge_service）：先在 Clash Verge 设置里安装服务模式并开 TUN，否则装上 user-public 规则会断网' }
    if (-not (Get-NetAdapter -Name $P['TUN'] -ErrorAction SilentlyContinue)) { throw "TUN 适配器 $($P['TUN']) 不在：先在 Clash Verge 里开 TUN 模式" }

    Set-NetFirewallProfile -Profile Domain, Private, Public -Enabled True
    $sddl = "D:(A;;CC;;;$sid)"
    $public4 = '0.0.0.0-9.255.255.255', '11.0.0.0-100.63.255.255', '100.128.0.0-126.255.255.255', '128.0.0.0-169.253.255.255', '169.255.0.0-172.15.255.255', '172.32.0.0-192.167.255.255', '192.169.0.0-198.17.255.255', '198.20.0.0-223.255.255.255'  # redact-allow: the whole public IPv4 space minus private/CGNAT/fake-ip ranges

    New-NetFirewallRule -DisplayName (Rule-Name 'net-wall v4') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -RemoteAddress '160.79.104.0/21' -Description 'claude-setup-kit: Anthropic IPv4 only via TUN' | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'net-wall v6') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -RemoteAddress '2607:6bc0::/32' -Description 'claude-setup-kit: Anthropic IPv6 only via TUN' | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'leak-guard dns udp') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -Protocol UDP -RemotePort 53, 853 | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'leak-guard dns tcp') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -Protocol TCP -RemotePort 53, 853 | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'leak-guard stun udp') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -Protocol UDP -RemotePort 3478, 5349, 19302 | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'leak-guard stun tcp') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -Protocol TCP -RemotePort 3478, 5349, 19302 | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'leak-guard user-public tcp') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -Protocol TCP -RemoteAddress $public4 -LocalUser $sddl | Out-Null
    New-NetFirewallRule -DisplayName (Rule-Name 'leak-guard user-public udp') -Direction Outbound -Action Block -Profile Any -InterfaceAlias $iface -Protocol UDP -RemoteAddress $public4 -LocalUser $sddl | Out-Null

    foreach ($n in $names) { Assert-Rule $n }
    Write-Output "[OK] 防火墙规则已装（$($names.Count) 条，网卡 $iface，用户 $($P['USER'])）：Anthropic 整段、物理 DNS/STUN、本用户公网只准走 $($P['TUN'])。"
}
