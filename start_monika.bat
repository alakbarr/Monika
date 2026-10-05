@echo off
title Monika Trading Agent Launcher
setlocal enabledelayedexpansion

:: ============================================================
::   MONIKA - Autonomous MT5 Trading Agent (One-Click Launcher)
:: ============================================================

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

set "AGENT_DIR=%ROOT_DIR%\trading-agent"
set "VENV_DIR=%AGENT_DIR%\venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

echo ============================================================
echo   MONIKA - Autonomous MT5 Quantitative Trading Agent
echo ============================================================
echo.

:: ── 1. Verify System Python (Python >= 3.11 required) ────────
set "SYS_PYTHON="
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 set "SYS_PYTHON=python"
if not defined SYS_PYTHON (
    py -3 --version >nul 2>&1
    if %ERRORLEVEL% equ 0 set "SYS_PYTHON=py -3"
)

if defined SYS_PYTHON goto :python_found

echo [!] Python is not found in your system PATH.
where winget >nul 2>&1
if %ERRORLEVEL% neq 0 goto :manual_python

echo [*] Windows Package Manager (winget) detected.
set "INSTALL_PY=y"
set /p INSTALL_PY="Install Python 3.11 automatically via winget? (y/n) [default: y]: "
if /i "!INSTALL_PY!"=="y" (
    echo [*] Downloading and installing Python 3.11...
    winget install -e --id Python.Python.3.11 --scope user
    echo.
    echo [OK] Python installed successfully. Please restart this launcher.
    pause
    exit /b 0
)

:manual_python
echo [ERROR] Please install Python 3.11+ from https://www.python.org/downloads/
echo Remember to check "Add Python to PATH" during installation.
pause
exit /b 1

:python_found

for /f "tokens=2 delims= " %%v in ('!SYS_PYTHON! --version 2^>^&1') do set "PY_VER=%%v"
echo [OK] System Python detected: !SYS_PYTHON! (!PY_VER!)

:: ── 2. Setup Virtual Environment & Install Dependencies ──────
if not exist "%PYTHON_EXE%" (
    echo.
    echo [*] [1/3] Creating virtual environment at trading-agent\venv...
    !SYS_PYTHON! -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.

    echo [*] [2/3] Installing dependencies - this takes 1-2 minutes on first run...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
    "%VENV_DIR%\Scripts\pip.exe" install -r "%AGENT_DIR%\requirements.txt"
    if %ERRORLEVEL% neq 0 (
        echo [WARN] Some dependencies encountered warnings. Continuing to pre-flight checks...
    ) else (
        echo [OK] All dependencies installed successfully.
    )
) else (
    echo [OK] Python virtual environment ready.
)

:: ── 3. Check Setup Configuration (.env) ──────────────────────
if /i "%~1"=="setup" (
    shift
    goto :force_setup
)
if /i "%~1"=="--setup" (
    shift
    goto :force_setup
)

set "ENV_EXISTS=0"
if exist "%ROOT_DIR%\.env" set "ENV_EXISTS=1"
if exist "%AGENT_DIR%\.env" set "ENV_EXISTS=1"

if "!ENV_EXISTS!"=="0" goto :run_initial_setup
goto :tier_selection

:run_initial_setup
echo.
echo [*] [3/3] Monika is not yet configured.
echo [*] Launching Interactive Setup Wizard...
echo.

:force_setup
pushd "%AGENT_DIR%"
set "PYTHONPATH=%AGENT_DIR%"
"%PYTHON_EXE%" -m cli.main setup
set "SETUP_ERR=%ERRORLEVEL%"
if %SETUP_ERR% neq 0 (
    echo.
    echo [ERROR] Setup wizard did not finish. Run start_monika.bat again when ready.
    popd
    pause
    exit /b 1
)

echo.
echo [*] Running automated system health verification: Doctor --fix...
"%PYTHON_EXE%" -m cli.main doctor --fix
popd
echo.
echo [OK] Setup and system verification completed successfully!
echo.

:tier_selection
:: ── 4. Detect or Select Installation Tier (Trial vs Full) ────
set "CURRENT_TIER="
if exist "%ROOT_DIR%\.monika_tier" set /p CURRENT_TIER=<"%ROOT_DIR%\.monika_tier"
if not defined CURRENT_TIER if exist "%AGENT_DIR%\.monika_tier" set /p CURRENT_TIER=<"%AGENT_DIR%\.monika_tier"
if not defined CURRENT_TIER set "CURRENT_TIER=trial"

if /i "%~1"=="full" (
    set "CURRENT_TIER=full"
    shift
)
if /i "%~1"=="trial" (
    set "CURRENT_TIER=trial"
    shift
)

echo.
echo ============================================================
echo   MONIKA PACKAGE SELECTION / RUNNING TIER:
echo ============================================================
if /i "!CURRENT_TIER!"=="full" goto :tier_menu_full

:tier_menu_trial
echo   1. [1] Continue with Trial Package [Active Default]
echo          - Paper Trading + SQLite + CLI / Telegram
echo   2. [2] Switch to Full Package
echo          - PostgreSQL + React Web Dashboard + 9Router AI Gateway
set "DEFAULT_CHOICE=1"
goto :tier_menu_prompt

:tier_menu_full
echo   1. [1] Switch to Trial Package
echo          - Paper Trading + SQLite + CLI / Telegram
echo   2. [2] Continue with Full Package [Active Default]
echo          - PostgreSQL + React Web Dashboard + 9Router AI Gateway
set "DEFAULT_CHOICE=2"
goto :tier_menu_prompt

:tier_menu_prompt
echo   3. [S] Re-run Guided Setup Wizard
echo   4. [Q] Quit
echo ============================================================
set "TIER_CHOICE="
set /p TIER_CHOICE="Select an option [1/2/S/Q, default: !DEFAULT_CHOICE!]: "
if not defined TIER_CHOICE set "TIER_CHOICE=!DEFAULT_CHOICE!"

set "TIER_KEY=!TIER_CHOICE:~0,1!"

if /i "!TIER_KEY!"=="q" (
    echo [*] Exiting Monika launcher.
    exit /b 0
)
if /i "!TIER_KEY!"=="s" (
    goto :force_setup
)
if "!TIER_KEY!"=="2" (
    set "CURRENT_TIER=full"
) else if /i "!TIER_KEY!"=="f" (
    set "CURRENT_TIER=full"
) else (
    set "CURRENT_TIER=trial"
)

echo !CURRENT_TIER!>"%ROOT_DIR%\.monika_tier"
echo !CURRENT_TIER!>"%AGENT_DIR%\.monika_tier"

echo.
if /i "!CURRENT_TIER!"=="trial" (
    set "MONIKA_TIER=trial"
    set "DATABASE_URL=sqlite+aiosqlite:///data/monika.db"
    set "PAPER_TRADING_MODE=true"
    echo [*] Active Package Tier: Trial Package
    echo [*] Engine: Zero-Config SQLite + Paper Trading Simulation.
    echo [*] Control: Interactive CLI + Telegram Alerts.
    echo [*] Note: Upgrade anytime to Full Package via: python -m cli.main upgrade
) else (
    set "MONIKA_TIER=full"
    set "DATABASE_URL="
    set "PAPER_TRADING_MODE="
    echo [*] Active Package Tier: Full Package
    echo [*] Engine: Enterprise PostgreSQL + 9Router AI Gateway + Web Dashboard.
    start "" cmd /c "%SystemRoot%\System32\timeout.exe /t 3 >nul 2>&1 && start http://localhost:8000"
)
echo.

:: ── 5. Run Monika Trading Agent ──────────────────────────────
pushd "%AGENT_DIR%"
set "PYTHONPATH=%AGENT_DIR%"

:run_loop
"%PYTHON_EXE%" -m cli.main run %*
set "EXIT_CODE=%ERRORLEVEL%"

if exist "%AGENT_DIR%\data\clean_shutdown.flag" (
    del "%AGENT_DIR%\data\clean_shutdown.flag" 2>nul
    echo.
    echo [*] Monika agent has shut down gracefully.
    popd
    pause
    exit /b 0
)

if %EXIT_CODE% equ 0 (
    echo.
    echo [*] Monika agent execution ended successfully.
    popd
    pause
    exit /b 0
)

echo.
echo ============================================================
echo [!] Monika agent exited with code %EXIT_CODE%.
echo ============================================================
echo   [R] Retry running Monika
echo   [D] Run Doctor diagnostics and auto-repair (doctor --fix)
echo   [S] Run Setup Wizard to reconfigure settings
echo   [T] Switch Package Tier (Trial ^<--^> Full)
echo   [Q] Quit
echo ============================================================
set "ERR_CHOICE=r"
set /p ERR_CHOICE="Select an action [R=Retry / D=Doctor / S=Setup / T=Switch Tier / Q=Quit, default: R]: "

if /i "!ERR_CHOICE!"=="d" (
    echo.
    echo [*] Running Monika Doctor diagnostics and auto-repair...
    "%PYTHON_EXE%" -m cli.main doctor --fix
    echo.
    echo [*] Press any key to retry running Monika...
    pause >nul
    goto :run_loop
)

if /i "!ERR_CHOICE!"=="s" (
    "%PYTHON_EXE%" -m cli.main setup
    goto :run_loop
)

if /i "!ERR_CHOICE!"=="t" (
    if /i "!CURRENT_TIER!"=="trial" (
        set "CURRENT_TIER=full"
        set "MONIKA_TIER=full"
        set "DATABASE_URL="
        set "PAPER_TRADING_MODE="
        echo full>"%ROOT_DIR%\.monika_tier"
        echo full>"%AGENT_DIR%\.monika_tier"
        echo [*] Switched tier to: Full Package.
    ) else (
        set "CURRENT_TIER=trial"
        set "MONIKA_TIER=trial"
        set "DATABASE_URL=sqlite+aiosqlite:///data/monika.db"
        set "PAPER_TRADING_MODE=true"
        echo trial>"%ROOT_DIR%\.monika_tier"
        echo trial>"%AGENT_DIR%\.monika_tier"
        echo [*] Switched tier to: Trial Package (SQLite + Paper Trading).
    )
    goto :run_loop
)

if /i "!ERR_CHOICE!"=="q" (
    echo [*] Exiting Monika launcher.
    popd
    exit /b %EXIT_CODE%
)

:: Default: Retry
echo [*] Retrying Monika launch in 3 seconds...
%SystemRoot%\System32\timeout.exe /t 3 >nul 2>&1 || ping 127.0.0.1 -n 4 >nul 2>&1
goto :run_loop
