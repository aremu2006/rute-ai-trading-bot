@echo off
echo =======================================
echo   RUTE BACKEND STARTUP SCRIPT
echo =======================================
cd /d "D:\RUTE\backend"

echo [1/3] Setting up virtual environment...
if not exist venv\Scripts\python.exe (
    python3.13 -m venv venv
)
venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo Virtual environment is broken. Recreating...
    rmdir /s /q venv
    python3.13 -m venv venv
)

echo [2/3] Installing required packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/3] Starting AI Backend Server...
python run_backend.py
pause
