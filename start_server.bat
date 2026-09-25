@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment is missing. Run setup.bat first.
  pause
  exit /b 1
)

echo Starting AMAT System Matcher...
echo Open http://localhost:8080 in a browser.
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
endlocal
