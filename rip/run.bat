@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ---- find Python: prefer the "py" launcher, then "python", then default install path ----
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
)
if not defined PY (
  echo [!] Python not found.
  echo     Install Python 3 from https://www.python.org/downloads/
  echo     During install, CHECK "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [*] Using Python: %PY%
echo [*] Checking dependencies ^(fastapi, uvicorn^)...
"%PY%" -c "import fastapi, uvicorn" 2>nul || "%PY%" -m pip install -r requirements.txt

echo [*] Starting server... a browser will open at http://localhost:8000
"%PY%" app.py

echo.
echo [*] Server stopped. Your records are safe in data\graveyard.db
pause
