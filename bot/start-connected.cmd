@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install-demo.cmd first. It installs dependencies for both modes.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Create .env using .env.example. See CONNECTED-WINDOWS.md.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m bot.main --connected
pause
