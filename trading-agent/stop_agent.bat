@echo off
title Stop Monika (MT5 Trading Agent)
echo Stopping Monika (MT5 Trading Agent) processes...

:: Terminate Python CLI/main processes
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Monika*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Administrator: Monika*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq AI Trading Agent*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Administrator: AI Trading Agent*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Claude AI Trading Agent*" 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Administrator: Claude AI Trading Agent*" 2>nul

:: Terminate Vite / Node.js development server on port 5173 if running
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do (
    echo Terminating Dashboard frontend process on port 5173 [PID %%a]...
    taskkill /F /PID %%a 2>nul
)

:: Terminate 9Router AI Gateway on port 20128 if running
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :20128 ^| findstr LISTENING') do (
    echo Terminating 9Router AI Gateway process on port 20128 [PID %%a]...
    taskkill /F /PID %%a 2>nul
)

:: Terminate Windows Terminal if running
echo Terminating Windows Terminal tabs...
taskkill /F /IM WindowsTerminal.exe 2>nul

:: Terminate MT5 terminal (terminal64.exe)
echo Checking for MetaTrader 5 terminal...
taskkill /F /IM terminal64.exe 2>nul && echo [OK] MetaTrader 5 terminal stopped. || echo [INFO] MetaTrader 5 tidak sedang berjalan.

echo All processes stopped successfully.
pause
