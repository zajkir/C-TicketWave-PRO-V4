@echo off
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
set CTW_DATA_DIR=%CD%\data
set CTW_LOCAL_DEV_TOKENS=1
set CTW_PUBLIC_BASE_URL=http://127.0.0.1:8765
set CTW_SECURE_COOKIES=0
start "" http://127.0.0.1:8765
python main.py
pause
