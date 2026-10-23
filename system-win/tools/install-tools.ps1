# Installs claude-wall.ps1 into %LOCALAPPDATA%\claude-setup-kit (user level, no admin). Refuses to overwrite.
param([Parameter(Mandatory = $true)][string]$Build)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$src = Join-Path $Build 'system-win\tools\claude-wall.ps1'
if (-not (Test-Path $src)) { throw "缺少渲染文件: $src" }
if (Select-String -Path $src -Pattern '\{\{[A-Z_]+\}\}' -Quiet) { throw 'claude-wall.ps1 还有未渲染的占位符' }
$dir = Join-Path $env:LOCALAPPDATA 'claude-setup-kit'
$dst = Join-Path $dir 'claude-wall.ps1'
if (Test-Path $dst) { throw "已存在，拒绝覆盖: $dst（要重装先删掉它）" }
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
Copy-Item $src $dst
"[OK] claude-wall.ps1 已装到 $dst。用法: powershell -NoProfile -ExecutionPolicy Bypass -File `"$dst`" status"
& powershell -NoProfile -ExecutionPolicy Bypass -File $dst status
"claude-wall status 退出码 $LASTEXITCODE（6 = 守护未装/异常，1 = 有防护缺失；装齐其他组件后会变 0）"
