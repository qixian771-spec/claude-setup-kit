@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
set "LOG=installers\logs\win-firewall-%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%-%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log"
set "LOG=%LOG: =0%"
if not exist installers\logs mkdir installers\logs
echo == 开始：Windows 防火墙规则（Anthropic 整段、物理 DNS/STUN、本用户公网只走 TUN） > "%LOG%"
for /f "delims=" %%B in ('py -3 scripts\render.py --component win-firewall 2^>^>"%LOG%"') do if not defined BUILD set "BUILD=%%B"
if not defined BUILD (
  echo 渲染失败，没有安装任何东西 >> "%LOG%"
  echo EXIT=2 >> "%LOG%"
  type "%LOG%"
  pause
  exit /b 2
)
echo 渲染目录: %BUILD% >> "%LOG%"
type "%BUILD%\PARAMS.txt" >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"& ''%CD%\%BUILD%\system-win\firewall\install-firewall.ps1'' -Build ''%CD%\%BUILD%'' *>> ''%CD%\%LOG%''; exit $LASTEXITCODE\"'; exit $p.ExitCode"
set "code=%ERRORLEVEL%"
echo EXIT=%code% >> "%LOG%"
type "%LOG%"
echo.
echo 日志: %LOG%
pause
exit /b %code%
