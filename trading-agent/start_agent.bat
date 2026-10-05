@echo off
title Monika Trading Agent Launcher
setlocal enabledelayedexpansion

:: ── Normalize working directory ───────────────────────────────────────────
set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"
cd /d "%CURRENT_DIR%"

echo ============================================================
echo   MONIKA - Autonomous MT5 Trading Agent (Windows Native)
echo ============================================================
echo.

:: ── 1. Auto-Compile MQL5 EA Bridge if MetaEditor is available ───────────────
set "METAEDITOR="
if exist "%ProgramFiles%\FBS MetaTrader 5\metaeditor64.exe" set "METAEDITOR=%ProgramFiles%\FBS MetaTrader 5\metaeditor64.exe"
if not defined METAEDITOR if exist "%ProgramFiles%\MetaTrader 5\metaeditor64.exe" set "METAEDITOR=%ProgramFiles%\MetaTrader 5\metaeditor64.exe"
if not defined METAEDITOR (
    for /d %%d in ("%ProgramFiles%\*MetaTrader*") do (
        if exist "%%d\metaeditor64.exe" set "METAEDITOR=%%d\metaeditor64.exe"
    )
)

if defined METAEDITOR (
    if exist "%CURRENT_DIR%\execution\ea_bridge\AIAgent_EA.mq5" (
        echo [*] Verifying and compiling AIAgent_EA.mq5...
        "%METAEDITOR%" /compile:"%CURRENT_DIR%\execution\ea_bridge\AIAgent_EA.mq5" /log:"%CURRENT_DIR%\execution\ea_bridge\compile.log" >nul 2>&1
        if exist "%CURRENT_DIR%\execution\ea_bridge\AIAgent_EA.ex5" (
            echo [OK] AIAgent_EA.ex5 ready for execution.
            if exist "%CURRENT_DIR%\execution\ea_bridge\compile.log" del "%CURRENT_DIR%\execution\ea_bridge\compile.log" 2>nul
        ) else (
            echo [WARN] Compilation of AIAgent_EA.mq5 failed. Inspect execution\ea_bridge\compile.log
        )
    )
)

:: ── 2. Locate Python Interpreter (Local venv or system) ─────────────────────
set "PYTHON_EXE=%CURRENT_DIR%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%CURRENT_DIR%\..\venv\Scripts\python.exe"
)
if not exist "%PYTHON_EXE%" (
    python --version >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python not found. Please run start_monika.bat in the root folder.
        pause
        exit /b 1
    )
)

echo [OK] Using Python: "%PYTHON_EXE%"

:: ── 3. Launch Browser to Dashboard (Background) ───────────────────────────
start "" cmd /c "timeout /t 3 >nul && start http://localhost:8000"

:: ── 4. Execute Monika Agent Main Loop ─────────────────────────────────────
set "PYTHONPATH=%CURRENT_DIR%"
set "TRADE_MODE=%~1"
if not defined TRADE_MODE set "TRADE_MODE=paper"

echo.
echo [*] Starting Monika Trading Agent (Mode: %TRADE_MODE%)...
echo [*] Web Dashboard accessible at: http://localhost:8000
echo.

:run_loop
"%PYTHON_EXE%" -m cli.main run %*
set "EXIT_CODE=%ERRORLEVEL%"

if exist "%CURRENT_DIR%\data\clean_shutdown.flag" (
    del "%CURRENT_DIR%\data\clean_shutdown.flag" 2>nul
    echo.
    echo [*] Monika agent has shut down normally.
    pause
    exit /b 0
)

echo.
echo [!] Monika agent stopped or exited unexpectedly (Exit Code: %EXIT_CODE%).
echo [*] Auto-restarting in 10 seconds... (Press Ctrl+C to abort)
timeout /t 10
goto :run_loop
