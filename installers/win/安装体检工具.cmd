@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
if not exist installers\logs mkdir installers\logs
set "LOG=installers\logs\win-tools-%RANDOM%.log"
echo == 开始：claude-wall.ps1 体检脚本（用户级，不需要管理员） > "%LOG%"
for /f "delims=" %%B in ('py -3 scripts\render.py --component win-tools 2^>^>"%LOG%"') do if not defined BUILD set "BUILD=%%B"
if not defined BUILD (
  echo 渲染失败，没有安装任何东西 >> "%LOG%"
  echo EXIT=2 >> "%LOG%"
  type "%LOG%"
  pause
  exit /b 2
)
echo 渲染目录: %BUILD% >> "%LOG%"
type "%BUILD%\PARAMS.txt" >> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%BUILD%\system-win\tools\install-tools.ps1" -Build "%CD%\%BUILD%" >> "%LOG%" 2>&1
set "code=%ERRORLEVEL%"
echo EXIT=%code% >> "%LOG%"
type "%LOG%"
echo.
echo 日志: %LOG%
pause
exit /b %code%
