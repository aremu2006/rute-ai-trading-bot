@echo off
title RUTE Trading Bot Backend
echo.
echo  ==========================================
echo   RUTE AI Trading Bot - Backend Server
echo  ==========================================
echo.
echo  Starting backend on http://localhost:8000
echo  Keep this window open while using the extension.
echo  Press Ctrl+C to stop the server.
echo.
cd /d D:\RUTE\backend
call venv\Scripts\activate.bat
python run_backend.py
pause
