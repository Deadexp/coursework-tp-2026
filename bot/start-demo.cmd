@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install-demo.cmd first.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Create .env using .env.example and add your Telegram token.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m bot.main --demo
pause
