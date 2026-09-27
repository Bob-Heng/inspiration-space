@echo off
rem Start frontend (dev mode)
cd /d %~dp0
rem Fallback: Node.js is installed at C:\Program Files\nodejs
if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
if not exist node_modules npm install
npm run dev
