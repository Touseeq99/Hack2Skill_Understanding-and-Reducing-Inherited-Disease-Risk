@echo off
rem One-command setup and start for Windows.
rem   run_demo.bat          set up (first time) and start the server, opens the patient app
rem   run_demo.bat reset    delete the demo database, re-seed it, then start
rem   run_demo.bat setup    set up only, do not start
rem   run_demo.bat ml       also install the optional ML layer (needs models\fastembed or internet for ~220 MB)
setlocal
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 or newer was not found. Install it from https://www.python.org and tick "Add python.exe to PATH".
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
set VPY=.venv\Scripts\python.exe
if not exist .venv\deps_ok.txt (
  echo Installing dependencies...
  %VPY% -m pip install --upgrade pip >nul
  %VPY% -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
  echo ok> .venv\deps_ok.txt
)
if /i "%1"=="ml" (
  echo Installing optional ML layer...
  %VPY% -m pip install fastembed numpy
  if errorlevel 1 exit /b 1
  set PYTHONIOENCODING=utf-8
  %VPY% -m eval.fetch_model
)
if /i "%1"=="reset" del /q inheritance_platform.db 2>nul
if not exist inheritance_platform.db (
  echo Seeding synthetic demo data...
  set PYTHONIOENCODING=utf-8
  %VPY% -m data.generate_seed
  if errorlevel 1 exit /b 1
  %VPY% -m data.seed_outcomes
  %VPY% -m data.seed_cases
)
if /i "%1"=="setup" (
  echo Setup complete. Start with: run_demo.bat
  exit /b 0
)
set PYTHONIOENCODING=utf-8
echo.
echo Patient app:        http://127.0.0.1:8000/app
echo Counsellor portal:  http://127.0.0.1:8000/portal
echo Dashboard:          http://127.0.0.1:8000/dashboard
echo Press Ctrl+C to stop.
start "" http://127.0.0.1:8000/app
%VPY% -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
