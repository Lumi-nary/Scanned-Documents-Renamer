@echo off
title Build Scanned Documents Renamer Installer
cd /d "%~dp0\.."

echo =====================================================================
echo   1. Compiling Standalone Application with PyInstaller
echo =====================================================================
python build_exe.py
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed!
    exit /b %errorlevel%
)

echo.
echo =====================================================================
echo   2. Checking for Inno Setup Compiler (ISCC)
echo =====================================================================

set "ISCC_PATH="
where iscc >nul 2>&1 && set "ISCC_PATH=iscc"
if not defined ISCC_PATH if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if defined ISCC_PATH goto :RUN_ISCC

echo [INFO] Inno Setup compiler was not found on your system.
echo.
echo The portable standalone application is ready to run at:
echo   dist\ScannedDocumentsRenamer\ScannedDocumentsRenamer.exe
echo.
echo To also generate the Setup Wizard installer (.exe):
echo   Run in terminal: winget install JRSoftware.InnoSetup
echo   Then re-run this script.
echo.
goto :END

:RUN_ISCC
echo Found Inno Setup at: "%ISCC_PATH%"
echo Compiling Setup Installer wizard...
"%ISCC_PATH%" "installer\setup.iss"
if %errorlevel% equ 0 (
    echo.
    echo =====================================================================
    echo   SETUP INSTALLER GENERATED SUCCESSFULLY!
    echo =====================================================================
    echo Installer file: dist\installer\ScannedDocumentsRenamer_Setup_v2.0.0.exe
    echo.
) else (
    echo [ERROR] Inno Setup compilation failed.
)

:END
