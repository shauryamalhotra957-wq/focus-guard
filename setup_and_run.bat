@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  set "FOCUS_PYTHON=python"
  python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>nul
  if errorlevel 1 (
    py -3.11 -c "import sys" >nul 2>nul
    if errorlevel 1 (
      echo A compatible Python installation was not found.
      echo Install 64-bit Python 3.11 from https://www.python.org/downloads/
      echo During setup, enable "Add python.exe to PATH", then run this file again.
      pause
      exit /b 1
    )
    set "FOCUS_PYTHON=py -3.11"
  )

  echo Creating the Focus Guard environment...
  call !FOCUS_PYTHON! -m venv .venv
  if errorlevel 1 goto :failed
)

echo Installing or checking dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo Starting Focus Guard...
".venv\Scripts\python.exe" main.py
exit /b %errorlevel%

:failed
echo.
echo Setup failed. Check the message above, then try again.
pause
exit /b 1
