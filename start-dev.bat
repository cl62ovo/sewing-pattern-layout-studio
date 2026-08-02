@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo Missing .venv. Create it with: python -m venv .venv
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"

python -c "import plush_pattern_studio" >nul 2>&1
if errorlevel 1 (
  echo Installing the backend package into .venv...
  python -m pip install -e ".\services\backend[dev]"
  if errorlevel 1 (
    echo Backend package installation failed.
    pause
    exit /b 1
  )
)

call npm run dev
pause