@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
if not exist installers\logs mkdir installers\logs
set "LOG=%CD%\installers\logs\一键撤回全部-%RANDOM%.log"
echo == 一键撤回全部（照安装前快照恢复）
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\system-win\all\uninstall-all.ps1" -Repo "%CD%" -Log "%LOG%"
set "code=%ERRORLEVEL%"
if exist "%LOG%" (type "%LOG%") else (echo 没有日志：多半是 UAC 被取消，什么都没改。)
echo.
echo 退出码 %code%    日志: %LOG%
pause
exit /b %code%
