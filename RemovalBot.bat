@echo off
title Removal Bot
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Installing Python 3.12...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo Failed to install Python. Install from https://www.python.org/downloads/
        echo Check "Add Python to PATH" during install.
        pause
        exit /b 1
    )
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

:: Restart Firefox with Marionette so the bot can attach
echo.
echo Restarting Firefox with remote control enabled...
echo (Your tabs and session will be restored automatically)
echo.
taskkill /IM firefox.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul

:: Find Firefox path
set "FF="
if exist "C:\Program Files\Mozilla Firefox\firefox.exe" set "FF=C:\Program Files\Mozilla Firefox\firefox.exe"
if exist "C:\Program Files (x86)\Mozilla Firefox\firefox.exe" set "FF=C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
if "%FF%"=="" (
    where firefox >nul 2>&1
    if %errorlevel% equ 0 (
        set "FF=firefox"
    ) else (
        echo ERROR: Firefox not found. Install Firefox first.
        pause
        exit /b 1
    )
)

:: Launch Firefox with Marionette enabled (uses default profile, restores session)
start "" "%FF%" --marionette --start-debugger-server 2828
echo Firefox started with remote control on port 2828.
timeout /t 3 /nobreak >nul

:: Launch the bot
echo Starting Removal Bot...
python removal_bot.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Bot failed. Check above for details.
    pause
)
