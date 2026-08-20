@echo off
echo ===================================================
echo   RUTE TRADING SYSTEM - ONE-CLICK INSTALLER
echo ===================================================

echo [1/3] Installing Backend Dependencies...
cd backend
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo Note: You may need to install TA-Lib manually.
    echo Visit: https://github.com/cgohlke/talib-build/releases
    pause
    exit /b
)

echo.
echo [2/3] Building Frontend...
cd ..
call npm install
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed.
    pause
    exit /b
)

echo.
echo [3/3] Setup Complete!
echo.
echo To start the system, run "start_rute.bat"
pause
