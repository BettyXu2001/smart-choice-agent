@echo off
cd /d %~dp0

if not defined CHOICE_AGENT_SESSION_SECRET (
    echo Set CHOICE_AGENT_SESSION_SECRET to a persistent secret of at least 32 bytes first.
    echo See README.md for local setup. The .env file is not loaded automatically.
    pause
    exit /b 1
)
set CHOICE_AGENT_COOKIE_SECURE=false

call .venv\Scripts\activate

start http://127.0.0.1:8000/

python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000

pause