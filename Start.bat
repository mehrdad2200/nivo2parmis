@echo off
setlocal
cd /d "%~dp0"
set PY=
py --version >nul 2>nul && set PY=py
if not defined PY ( python --version >nul 2>nul && set PY=python )
if not defined PY (
  echo Python is not installed.
  echo Opening the download page. Install it, tick "Add Python to PATH",
  echo then double-click Start.bat again.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% -c "import cryptography, tzdata, tkinter" >nul 2>nul || (
  echo Installing required packages - one time only, needs internet...
  %PY% -m pip install --quiet cryptography tzdata
)
%PY% run_gui.py
if errorlevel 1 (
  echo.
  echo Something went wrong. Please send the message above.
  pause
)
