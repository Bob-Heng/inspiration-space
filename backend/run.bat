@echo off
rem Start backend (dev mode)
cd /d %~dp0
if not exist venv (
    python -m venv venv
    venv\Scripts\python -m pip install -r requirements.txt
)
venv\Scripts\uvicorn app.main:app --reload --port 8000
