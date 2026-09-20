# ==============================================================================
# Monika (MT5 Trading Agent) - Windows One-Click Installer
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Monika: Institutional Trading Agent - Windows Installer   " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$AgentDir = Join-Path $RootDir "trading-agent"
$VenvDir = Join-Path $AgentDir "venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# 1. Check Python installation
Write-Host "`n[1/5] Checking Python environment..." -ForegroundColor Yellow
$SystemPython = Get-Command python -ErrorAction SilentlyContinue
if (-not $SystemPython) {
    Write-Host "Error: Python 3.10+ is required but not found in PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/downloads/ and check 'Add Python to PATH'." -ForegroundColor Red
    exit 1
}

$PyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "Detected Python $PyVer" -ForegroundColor Green

# 2. Check / Setup Virtual Environment
Write-Host "`n[2/5] Setting up virtual environment in $VenvDir..." -ForegroundColor Yellow
if (-not (Test-Path $PythonExe)) {
    & python -m venv $VenvDir
    Write-Host "Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "Existing virtual environment found." -ForegroundColor Green
}

# 3. Install dependencies via uv or pip
Write-Host "`n[3/5] Installing core dependencies..." -ForegroundColor Yellow
$UvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($UvCmd) {
    Write-Host "Using fast uv installer..." -ForegroundColor Green
    & uv pip install -r (Join-Path $AgentDir "requirements.txt") --python $PythonExe
} else {
    Write-Host "Using standard pip installer..." -ForegroundColor Gray
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $AgentDir "requirements.txt")
}

# 4. Initialize environment configuration
Write-Host "`n[4/5] Checking environment configuration..." -ForegroundColor Yellow
$EnvFile = Join-Path $RootDir ".env"
$EnvExample = Join-Path $RootDir ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created .env from template (.env.example)." -ForegroundColor Green
} else {
    Write-Host "Configuration file (.env) already present." -ForegroundColor Green
}

# 5. Run setup doctor
Write-Host "`n[5/5] Running environment doctor..." -ForegroundColor Yellow
Push-Location $AgentDir
try {
    & $PythonExe -m cli.main doctor
} catch {
    Write-Host "Doctor inspection completed." -ForegroundColor Gray
} finally {
    Pop-Location
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Installation Complete! Run 'trading-agent\start_agent.bat' " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
