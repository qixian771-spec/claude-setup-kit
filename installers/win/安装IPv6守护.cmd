@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
if not exist installers\logs mkdir installers\logs
set "LOG=%CD%\installers\logs\安装IPv6守护-%RANDOM%.log"
echo == 关闭物理网卡 IPv6 并用计划任务守住
for /f "delims=" %%B in ('py -3 scripts\render.py --component win-tasks 2^>"%LOG%.render.txt"') do if not defined BUILD set "BUILD=%%B"
if not defined BUILD (
  echo 渲染失败，没有安装任何东西：
  type "%LOG%.render.txt"
  pause
  exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%BUILD%\system-win\tasks\install-tasks.ps1" -Build "%BUILD%" -Only ipv6-guard -Log "%LOG%"
set "code=%ERRORLEVEL%"
if exist "%LOG%" (type "%LOG%") else (echo 没有日志：多半是 UAC 被取消，什么都没改。)
echo.
echo 退出码 %code%    日志: %LOG%
pause
exit /b %code%
