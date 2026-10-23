@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
if not exist installers\logs mkdir installers\logs
set "LOG=installers\logs\win-firewall-uninstall-%RANDOM%.log"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"& ''%CD%\system-win\firewall\uninstall-firewall.ps1'' *>> ''%CD%\%LOG%''; exit $LASTEXITCODE\"'; exit $p.ExitCode"
set "code=%ERRORLEVEL%"
echo EXIT=%code% >> "%LOG%"
type "%LOG%"
pause
exit /b %code%
