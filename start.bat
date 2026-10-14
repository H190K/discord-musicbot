@echo off
rem Start the music bot on Windows (double-click this file).
rem The launcher creates .venv and installs everything it needs on first run.
cd /d "%~dp0"

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python 3.10 or newer is required but was not found.
    echo Download it from https://www.python.org/downloads/
    echo During setup, tick "Add python.exe to PATH".
    pause
    exit /b 1
)

%PYTHON_CMD% launcher.py %*
if errorlevel 1 (
    echo.
    echo The bot stopped with an error. See the messages above.
    pause
    exit /b 1
)
