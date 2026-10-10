@echo off
setlocal
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
"%ROOT_DIR%\trading-agent\venv\Scripts\python.exe" -m cli.main %*
endlocal
