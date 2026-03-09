@echo off
title Build Removal Bot EXE
cd /d "%~dp0"

echo ========================================
echo   Building Removal Bot .exe
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed. Run RemovalBot.bat first to install Python.
    pause
    exit /b 1
)

:: Install build dependencies
echo Installing build tools...
pip install pyinstaller selenium webdriver-manager

echo.
echo Building executable...
pyinstaller --onefile --windowed --name RemovalBot --icon=NONE removal_bot.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Your .exe is at: dist\RemovalBot.exe
    echo You can copy it anywhere and double-click to run.
    echo.
    explorer dist
) else (
    echo.
    echo BUILD FAILED. Check errors above.
)

pause
