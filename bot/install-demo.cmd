@echo off
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 with Python Launcher is required. See DEMO-WINDOWS.md.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo Failed to create the Python environment.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
if errorlevel 1 (
  echo Installation failed. Check the error above and your internet connection.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
echo Ready. Add your Telegram token to .env using Notepad.
echo Then run start-demo.cmd. See DEMO-WINDOWS.md for instructions.
pause
