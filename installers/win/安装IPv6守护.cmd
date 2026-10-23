@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
if not exist installers\logs mkdir installers\logs
set "LOG=installers\logs\win-ipv6-%RANDOM%.log"
echo == 开始：关闭物理网卡 IPv6 并用计划任务守住 > "%LOG%"
for /f "delims=" %%B in ('py -3 scripts\render.py --component win-tasks 2^>^>"%LOG%"') do if not defined BUILD set "BUILD=%%B"
if not defined BUILD (
  echo 渲染失败，没有安装任何东西 >> "%LOG%"
  echo EXIT=2 >> "%LOG%"
  type "%LOG%"
  pause
  exit /b 2
)
echo 渲染目录: %BUILD% >> "%LOG%"
type "%BUILD%\PARAMS.txt" >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"& ''%CD%\%BUILD%\system-win\tasks\install-tasks.ps1'' -Build ''%CD%\%BUILD%'' -Only ipv6-guard *>> ''%CD%\%LOG%''; exit $LASTEXITCODE\"'; exit $p.ExitCode"
set "code=%ERRORLEVEL%"
echo EXIT=%code% >> "%LOG%"
type "%LOG%"
echo.
echo 日志: %LOG%
pause
exit /b %code%
