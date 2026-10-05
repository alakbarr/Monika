# ==============================================================================
# Monika - Autonomous MT5 Trading Agent (PowerShell Modern Setup)
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  MONIKA - Autonomous MT5 Trading Agent Setup Bootstrapper  " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$RootDir = $PSScriptRoot
$AgentDir = Join-Path $RootDir "trading-agent"
$VenvDir = Join-Path $AgentDir "venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# 1. Verify Python
Write-Host "[1/4] Checking Python 3.11+ installation..." -ForegroundColor Yellow
$SysPy = Get-Command python -ErrorAction SilentlyContinue
if (-not $SysPy) {
    Write-Host "[!] Python is not found in PATH." -ForegroundColor Red
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($Winget) {
        $ans = Read-Host "Install Python 3.11 automatically via winget? (y/n)"
        if ($ans -eq "y") {
            winget install -e --id Python.Python.3.11 --scope user
            Write-Host "[OK] Python installed. Please restart your PowerShell terminal." -ForegroundColor Green
            exit 0
        }
    }
    Write-Host "Please install Python 3.11+ from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

$PyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "[OK] Detected Python $PyVer" -ForegroundColor Green

# 2. Virtual Environment
Write-Host "`n[2/4] Setting up virtual environment in $VenvDir..." -ForegroundColor Yellow
if (-not (Test-Path $PythonExe)) {
    & python -m venv $VenvDir
    Write-Host "[OK] Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "[OK] Virtual environment already exists." -ForegroundColor Green
}

# 3. Core dependencies
Write-Host "`n[3/4] Installing core dependencies (< 30s)..." -ForegroundColor Yellow
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
& $PythonExe -m pip install --upgrade pip 2>$null | Out-Null
& $PipExe install -r (Join-Path $AgentDir "requirements.txt")
Write-Host "[OK] Core dependencies installed successfully." -ForegroundColor Green

# 4. Check .env
Write-Host "`n[4/4] Checking environment configuration..." -ForegroundColor Yellow
$EnvPath = Join-Path $RootDir ".env"
$EnvEx = Join-Path $RootDir ".env.example"
if (-not (Test-Path $EnvPath) -and (Test-Path $EnvEx)) {
    Copy-Item $EnvEx $EnvPath
    Write-Host "[OK] Initialized .env from template." -ForegroundColor Green
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  Dependencies ready. Launching Monika Interactive Setup...  " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

Push-Location $AgentDir
$env:PYTHONPATH = $AgentDir
try {
    & $PythonExe -m cli.main setup
} finally {
    Pop-Location
}

Write-Host "`nSetup complete! You can start Monika anytime by running: start_monika.bat" -ForegroundColor Cyan
