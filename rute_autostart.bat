@echo off
:: RUTE Auto-Start on Windows Login (runs silently in background)
:: Skips startup if the backend is already running on port 8001
cd /d D:\RUTE\backend
netstat -ano | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 exit /b 0
start "" /min venv\Scripts\pythonw.exe run_backend.py
