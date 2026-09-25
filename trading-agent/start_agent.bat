@echo off
title Monika (MT5 Trading Agent Launcher)
cd /d "%~dp0"

:: ── Cari lokasi Git Bash ──────────────────────────────────────────────────
set "GIT_BASH="

:: 1. Cek direktori instalasi standar
if exist "%ProgramFiles%\Git\git-bash.exe" set "GIT_BASH=%ProgramFiles%\Git\git-bash.exe"
if not defined GIT_BASH if exist "%ProgramFiles(x86)%\Git\git-bash.exe" set "GIT_BASH=%ProgramFiles(x86)%\Git\git-bash.exe"
if not defined GIT_BASH if exist "%LocalAppData%\Programs\Git\git-bash.exe" set "GIT_BASH=%LocalAppData%\Programs\Git\git-bash.exe"

:: 2. Cek di PATH via where
if not defined GIT_BASH (
    for /f "tokens=*" %%i in ('where git-bash.exe 2^>nul') do (
        set "GIT_BASH=%%i"
        goto :found_git_bash
    )
)

:found_git_bash
if defined GIT_BASH (
    echo [OK] Git Bash ditemukan: "%GIT_BASH%"
    echo Meluncurkan Monika di Git Bash...
    start "" "%GIT_BASH%" --cd="%~dp0" -c "./start_agent.sh %*; read -p 'Press Enter to close window...'"
    exit /b 0
)

:: 3. Fallback jika git-bash.exe tidak ditemukan tapi bash.exe ada
set "BASH_EXE="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles%\Git\usr\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\usr\bin\bash.exe"

if not defined BASH_EXE (
    for /f "tokens=*" %%i in ('where bash.exe 2^>nul') do (
        set "BASH_EXE=%%i"
        goto :found_bash_exe
    )
)

:found_bash_exe
if defined BASH_EXE (
    echo [OK] Bash ditemukan: "%BASH_EXE%"
    echo Meluncurkan Monika via Bash...
    start "Monika (MT5 Trading Agent)" "%BASH_EXE%" --login -i -c "cd '%~dp0' && ./start_agent.sh %*; read -p 'Press Enter to close window...'"
    exit /b 0
)

echo ============================================================
echo [ERROR] Git Bash tidak ditemukan di sistem!
echo Pastikan Git for Windows sudah terinstall (https://git-scm.com/)
echo ============================================================
pause
exit /b 1
