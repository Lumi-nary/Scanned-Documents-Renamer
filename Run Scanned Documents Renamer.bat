@echo off
title Scanned Documents Renamer
cd /d "%~dp0"

echo Starting Scanned Documents Renamer Desktop Application...

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw app.py
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        python app.py
    ) else (
        echo [ERROR] Python is not found in your PATH.
        echo Please install Python 3.10+ from python.org or the Microsoft Store.
        pause
    )
)
