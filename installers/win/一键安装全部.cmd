@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
if not exist installers\logs mkdir installers\logs
set "LOG=%CD%\installers\logs\一键安装全部-%RANDOM%.log"
echo == 一键安装全部（防火墙、守护、IPv6、浏览器策略、体检、时区）
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\system-win\all\install-all.ps1" -Repo "%CD%" -Log "%LOG%"
set "code=%ERRORLEVEL%"
if exist "%LOG%" (type "%LOG%") else (echo 没有日志：多半是 UAC 被取消，什么都没改。)
echo.
echo 退出码 %code%    日志: %LOG%
pause
exit /b %code%
