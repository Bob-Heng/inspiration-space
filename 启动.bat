@echo off
rem Start InspirationSpace backend + frontend in separate windows
cd /d %~dp0
start "InspirationSpace-Backend" cmd /k backend\run.bat
start "InspirationSpace-Frontend" cmd /k frontend\run.bat
echo Backend: http://localhost:8000   Frontend: http://localhost:5173
