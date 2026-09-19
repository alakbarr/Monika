@echo off
title Monika Setup Bootstrapper
setlocal enabledelayedexpansion

echo ============================================================
echo   MONIKA - Autonomous MT5 Trading Agent Setup Bootstrapper
echo ============================================================
echo.

set "ROOT_DIR=%~dp0"
set "AGENT_DIR=%ROOT_DIR%trading-agent"

:: 1. Check Python
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in PATH. Please install Python 3.11 or higher.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo [OK] Python %PY_VER% detected.

:: 2. Setup Virtual Environment
echo.
echo [2/5] Setting up virtual environment...
if not exist "%AGENT_DIR%\venv\Scripts\python.exe" (
    echo Creating virtual environment at %AGENT_DIR%\venv...
    python -m venv "%AGENT_DIR%\venv"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

call "%AGENT_DIR%\venv\Scripts\activate.bat"

:: 3. Install Python Dependencies
echo.
echo [3/5] Installing core dependencies...
python -m pip install --upgrade pip >nul 2>&1
pip install -r "%AGENT_DIR%\requirements.txt"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install Python dependencies. Check network or requirements.txt.
    pause
    exit /b 1
)
echo [OK] Python dependencies installed.

:: 4. Environment File Initialization
echo.
echo [4/5] Checking environment configuration...
if not exist "%ROOT_DIR%\.env" (
    if exist "%ROOT_DIR%\.env.example" (
        copy "%ROOT_DIR%\.env.example" "%ROOT_DIR%\.env" >nul
        echo [OK] Initialized .env from .env.example template.
    ) else (
        echo [WARN] .env.example not found in root.
    )
) else (
    echo [OK] .env already exists.
)

:: 5. Install Frontend Dependencies if Node is present
echo.
echo [5/5] Checking dashboard frontend dependencies...
where npm >nul 2>&1
if %ERRORLEVEL% equ 0 (
    if not exist "%AGENT_DIR%\logging_observability\dashboard\frontend\node_modules" (
        echo Installing Vite/React dashboard dependencies...
        pushd "%AGENT_DIR%\logging_observability\dashboard\frontend"
        call npm install --silent
        popd
        echo [OK] Dashboard frontend dependencies installed.
    ) else (
        echo [OK] Dashboard frontend dependencies already installed.
    )
) else (
    echo [INFO] Node.js/npm not detected. Dashboard frontend build skipped (can be done later).
)

echo.
echo ============================================================
echo   Dependencies ready. Launching Monika Interactive Setup...
echo ============================================================
echo.

pushd "%AGENT_DIR%"
set PYTHONPATH=%AGENT_DIR%
python -m cli.main setup
popd

echo.
echo Setup completed. You can start the agent anytime using trading-agent\start_agent.bat
pause
