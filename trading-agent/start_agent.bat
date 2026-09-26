@echo off
title Monika (MT5 Trading Agent Launcher)

:: ── Normalisasi direktori kerja (hilangkan trailing backslash) ───────────
set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"
cd /d "%CURRENT_DIR%"

:: ── Handler untuk Tab Internal Windows Terminal ──────────────────────────
if "%~1"=="--tab-agent" goto :run_tab_agent
if "%~1"=="--tab-dashboard" goto :run_tab_dashboard
if "%~1"=="--tab-router" goto :run_tab_router

:: ── Auto-Compile MQL5 EA Bridge ──────────────────────────────────────────
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
        echo [*] Memeriksa ^& mengompilasi AIAgent_EA.mq5...
        "%METAEDITOR%" /compile:"%CURRENT_DIR%\execution\ea_bridge\AIAgent_EA.mq5" /log:"%CURRENT_DIR%\execution\ea_bridge\compile.log" >nul 2>&1
        if exist "%CURRENT_DIR%\execution\ea_bridge\AIAgent_EA.ex5" (
            echo [OK] AIAgent_EA.ex5 siap digunakan.
            if exist "%CURRENT_DIR%\execution\ea_bridge\compile.log" del "%CURRENT_DIR%\execution\ea_bridge\compile.log" 2>nul
        ) else (
            echo [WARN] Kompilasi AIAgent_EA.mq5 gagal. Cek execution\ea_bridge\compile.log
        )
    )
)

:: ── Cari lokasi Git Bash / Mintty ───────────────────────────────────────────
set "GIT_DIR="
if exist "%ProgramFiles%\Git" set "GIT_DIR=%ProgramFiles%\Git"
if not defined GIT_DIR if exist "%ProgramFiles(x86)%\Git" set "GIT_DIR=%ProgramFiles(x86)%\Git"
if not defined GIT_DIR if exist "%LocalAppData%\Programs\Git" set "GIT_DIR=%LocalAppData%\Programs\Git"

set "MINTTY_EXE="
set "BASH_EXE="
set "GIT_ICON="

if defined GIT_DIR (
    if exist "%GIT_DIR%\usr\bin\mintty.exe" set "MINTTY_EXE=%GIT_DIR%\usr\bin\mintty.exe"
    if exist "%GIT_DIR%\bin\bash.exe" set "BASH_EXE=%GIT_DIR%\bin\bash.exe"
    if not defined BASH_EXE if exist "%GIT_DIR%\usr\bin\bash.exe" set "BASH_EXE=%GIT_DIR%\usr\bin\bash.exe"
    if exist "%GIT_DIR%\git-bash.exe" set "GIT_ICON=%GIT_DIR%\git-bash.exe"
)

:: Cek di PATH jika belum ditemukan
if not defined BASH_EXE (
    for /f "tokens=*" %%i in ('where bash.exe 2^>nul') do (
        set "BASH_EXE=%%i"
        goto :launch_bash
    )
)

:launch_bash
:: ── Cek apakah Windows Terminal (wt.exe) tersedia untuk Opsi 3 (Tab) ──────
set "WT_EXE="
where wt.exe >nul 2>&1 && set "WT_EXE=wt.exe"
if not defined WT_EXE if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" set "WT_EXE=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"

if defined WT_EXE (
    echo [OK] Windows Terminal ditemukan: "%WT_EXE%"
    echo Meluncurkan Monika dalam 3 Tab Windows Terminal...
    set "TRADE_ARGS=%*"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$c = $env:CURRENT_DIR; $extra = $env:TRADE_ARGS; $arg = '-w _new --title \"Monika Agent\" -d \"' + $c + '\" cmd /k \"\"' + $c + '\start_agent.bat\"\" --tab-agent ' + $extra + ' ; new-tab --title \"Dashboard Frontend\" -d \"' + $c + '\logging_observability\dashboard\frontend\" cmd /k \"\"' + $c + '\start_agent.bat\"\" --tab-dashboard ; new-tab --title \"9Router Gateway\" -d \"' + $c + '\" cmd /k \"\"' + $c + '\start_agent.bat\"\" --tab-router'; Start-Process wt.exe -ArgumentList $arg"
    if %ERRORLEVEL% equ 0 (
        ping 127.0.0.1 -n 3 >nul 2>&1
        exit /b 0
    ) else (
        echo [WARN] Gagal membuka Windows Terminal. Beralih ke fallback Git Bash...
    )
)

:: ── Fallback jika Windows Terminal tidak tersedia (Single Window) ──────────
if defined MINTTY_EXE (
    echo [OK] Git Bash Mintty ditemukan: "%MINTTY_EXE%"
    echo Meluncurkan Monika di Git Bash...
    start "Monika (MT5 Trading Agent)" "%MINTTY_EXE%" -i "%GIT_ICON%" -t "Monika (MT5 Trading Agent)" -e /usr/bin/bash --login -i -c "cd '%CURRENT_DIR%' && ./start_agent.sh %*; echo; read -p 'Press Enter to close window...'"
    exit /b 0
)

if defined BASH_EXE (
    echo [OK] Bash ditemukan: "%BASH_EXE%"
    echo Meluncurkan Monika via Bash...
    start "Monika (MT5 Trading Agent)" "%BASH_EXE%" --login -i -c "cd '%CURRENT_DIR%' && ./start_agent.sh %*; echo; read -p 'Press Enter to close window...'"
    exit /b 0
)

echo ============================================================
echo [ERROR] Git Bash tidak ditemukan di sistem!
echo Pastikan Git for Windows sudah terinstall (https://git-scm.com/)
echo ============================================================
pause
exit /b 1

:: ── Tab Handlers (dieksekusi di dalam masing-masing tab) ───────────────────
:run_tab_agent
title Monika Agent
cd /d "%CURRENT_DIR%"
echo ============================================================
echo [Tab 1/3] Monika Trading Agent
echo ============================================================
set "BASH_CMD="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_CMD=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_CMD if exist "%ProgramFiles%\Git\usr\bin\bash.exe" set "BASH_CMD=%ProgramFiles%\Git\usr\bin\bash.exe"
if not defined BASH_CMD set "BASH_CMD=bash.exe"
"%BASH_CMD%" --login -i -c "MONIKA_EXTERNAL_SERVICES=1 ./start_agent.sh %2 %3 %4 %5"
echo.
echo Monika Agent telah berhenti.
pause
exit /b 0

:run_tab_dashboard
title Dashboard Frontend
cd /d "%CURRENT_DIR%\logging_observability\dashboard\frontend"
echo ============================================================
echo [Tab 2/3] Dashboard Frontend (http://localhost:5173)
echo ============================================================
call npm run dev
echo.
echo Dashboard Frontend telah berhenti.
pause
exit /b 0

:run_tab_router
title 9Router Gateway
cd /d "%CURRENT_DIR%"
echo ============================================================
echo [Tab 3/3] 9Router AI Gateway (http://localhost:20128)
echo ============================================================
where 9router >nul 2>&1
if %ERRORLEVEL% equ 0 (
    9router --no-browser --skip-update
) else (
    call npx -y 9router --no-browser --skip-update
)
echo.
echo 9Router Gateway telah berhenti.
pause
exit /b 0
