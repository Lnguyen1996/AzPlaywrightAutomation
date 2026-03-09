@echo off
title Removal Bot
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Installing Python 3.12...
    echo.
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo Failed to install Python automatically.
        echo Please install Python manually from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during install.
        pause
        exit /b 1
    )
    echo.
    echo Python installed. Refreshing PATH...
    :: Refresh PATH by pulling from registry
    for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYSPATH=%%B"
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USRPATH=%%B"
    set "PATH=%SYSPATH%;%USRPATH%"
)

:: Install dependencies if needed
if not exist ".deps_installed" (
    echo Installing dependencies...
    pip install selenium webdriver-manager
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo. > .deps_installed
)

:: Launch the bot
echo Starting Removal Bot...
python removal_bot.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to start. Try deleting .deps_installed and run again.
    pause
)
