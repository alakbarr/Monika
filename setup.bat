@echo off
title Monika Setup Redirect
echo ============================================================
echo   MONIKA - Setup is now unified into start_monika.bat!
echo ============================================================
echo.
echo [*] Redirecting to start_monika.bat (single launcher for setup & run)...
echo.
cd /d "%~dp0"
call "%~dp0start_monika.bat" %*
