@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo [C TicketWave PRO] Preparing Python environment...
  %PY% -m venv .venv || (echo Python 3.11+ is required & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Dependency install failed & pause & exit /b 1)
set "CTW_ALLOW_LOCAL_SETUP=1"
start "" cmd /c "timeout /t 5 /nobreak >nul && start http://127.0.0.1:8765"
echo [C TicketWave PRO] Visit http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8765
pause
