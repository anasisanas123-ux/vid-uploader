@echo off
cd /d "%~dp0"
if not exist .venv (
    echo Creating virtual environment...
    py -3.11 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if not exist .env copy .env.example .env >nul
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
