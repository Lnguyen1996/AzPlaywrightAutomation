@echo off
echo ========================================
echo   Removal Bot - Setup
echo ========================================
echo.

echo Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip install failed. Make sure Python is installed and in your PATH.
    echo Install Python from: winget install Python.Python.3.12
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo To run the bot:
echo   python removal_bot.py
echo.
echo To attach to existing Firefox, start Firefox first with:
echo   "C:\Program Files\Mozilla Firefox\firefox.exe" --marionette --start-debugger-server 2828
echo.
pause
