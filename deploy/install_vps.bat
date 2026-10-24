@echo off
title Monika Windows VPS Installer
setlocal

:: Determine directory where this script resides
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

echo ============================================================
echo   Launching Monika Automated Windows VPS Installer...
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\install_vps.ps1"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Installation exited with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

echo.
pause
exit /b 0
