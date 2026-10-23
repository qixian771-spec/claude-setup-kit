# Sets the Windows time zone (needs admin). The zone id comes from the render params (TIMEZONE_WIN).
param([Parameter(Mandatory = $true)][string]$Build, [string]$Log)
. (Join-Path $PSScriptRoot '..\firewall\common.ps1')
Enter-Elevated $PSBoundParameters $PSCommandPath
Invoke-Logged $Log {
    Need-Admin
    $P = Read-Params $Build
    $zone = $P['TIMEZONE_WIN']
    if (-not $zone) { throw 'PARAMS.txt 缺 TIMEZONE_WIN' }
    if (-not (Get-TimeZone -ListAvailable | Where-Object Id -eq $zone)) { throw "未知时区 id: $zone（用 tzutil /l 查看）" }
    $before = (Get-TimeZone).Id
    tzutil /s $zone
    $after = (Get-TimeZone).Id
    if ($after -ne $zone) { throw "时区没有改成功（现在是 $after）" }
    "[OK] 时区 $before → $after"
}
