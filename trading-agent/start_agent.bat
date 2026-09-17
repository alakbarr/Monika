@echo off
title Monika (MT5 Trading Agent)
cd /d "%~dp0"

:: ── Baca argumen mode (default: paper) ──────────────────────────────────────
set TRADE_MODE=paper
if /i "%~1"=="live" set TRADE_MODE=live
if /i "%~1"=="paper" set TRADE_MODE=paper

echo ============================================================
echo  MONIKA - MT5 Trading Agent
echo  Mode: %TRADE_MODE%
echo ============================================================

:: ── Activate virtual environment if present ──────────────────────────────────
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
)

:: ── 1. Buka MT5 Terminal (sekali di awal, TIDAK direstart saat loop) ─────────
echo [1/4] Membuka MetaTrader 5 Terminal...
set MT5_PATH=
for /f "usebackq tokens=1* delims==" %%A in (`findstr /i "^MT5_PATH" .env 2^>nul`) do (
    set "MT5_PATH=%%~B"
)
if defined MT5_PATH (
    call set "MT5_PATH=%%MT5_PATH:/=\%%"
)
if defined MT5_PATH (
    if exist "%MT5_PATH%" (
        start "" "%MT5_PATH%"
        echo [OK] MetaTrader 5 dibuka: %MT5_PATH%
    ) else (
        echo [WARN] MT5 terminal tidak ditemukan di: %MT5_PATH%
    )
) else (
    echo [WARN] MT5_PATH tidak ada di .env -- lewati pembukaan MT5.
)

:: ── 2. Jalankan Dashboard Frontend di window terpisah ────────────────────────
echo [2/4] Menjalankan Dashboard Frontend (localhost:5173)...
start "Monika Dashboard Frontend" cmd /k "cd /d %~dp0logging_observability\dashboard\frontend && npm run dev"

:: ── 3. Run database migrations ───────────────────────────────────────────────
echo [3/4] Checking and running database migrations...
python -m alembic upgrade head
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Alembic migration failed! Please check database connection.
    pause
    exit /b %ERRORLEVEL%
)

:: ── 4. Restart-loop: jalankan agent via CLI ──────────────────────────────────
echo [4/4] Menjalankan Monika via CLI (mode: %TRADE_MODE%)...

:loop
echo Starting Monika (MT5 Trading Agent) in %TRADE_MODE% mode...
if /i "%TRADE_MODE%"=="live" (
    python -m cli.main run --mode live --confirm-live
) else (
    python -m cli.main run --mode paper
)

if exist "data\clean_shutdown.flag" (
    del "data\clean_shutdown.flag"
    echo Agent stopped gracefully by operator command. Exiting.
    goto end
)
echo Agent exited or crashed (Code %ERRORLEVEL%). Restarting in 30 seconds...
echo (MT5 Terminal tetap berjalan - tidak perlu restart)
timeout /t 30
goto loop

:end
echo Monika stopped.
pause
