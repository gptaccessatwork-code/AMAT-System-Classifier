@echo off
setlocal
cd /d "%~dp0"
py -3 "%~dp0app.py"
if errorlevel 1 pause
endlocal
