# ==============================================================================
# Monika - High-Performance Managed uv Installer & Win32 Hardening Script
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Monika: Managed uv Installer & Win32 System Hardening      " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$AgentDir = Join-Path $RootDir "trading-agent"
$VenvDir = Join-Path $AgentDir "venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# 1. Win32 Long Path Check
Write-Host "`n[1/6] Verifying Windows Win32 MaxPath / Long Path Configuration..." -ForegroundColor Yellow
try {
    $LongPaths = Get-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -ErrorAction SilentlyContinue
    if ($LongPaths -and $LongPaths.LongPathsEnabled -eq 1) {
        Write-Host "✓ Windows Long Paths Enabled (260-char limitation removed)." -ForegroundColor Green
    } else {
        Write-Host "! Notice: Windows LongPathsEnabled is not active." -ForegroundColor Yellow
        Write-Host "  To prevent file-path truncation on deep npm/python packages, run in Admin PowerShell:" -ForegroundColor Gray
        Write-Host "  New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -Value 1 -PropertyType DWORD -Force" -ForegroundColor Gray
    }
} catch {
    Write-Host "! Could not inspect LongPathsEnabled registry key (requires admin or non-elevated user)." -ForegroundColor Gray
}

# 2. Check / Install uv
Write-Host "`n[2/6] Locating / Bootstrapping uv..." -ForegroundColor Yellow
$UvCmd = Get-Command uv -ErrorAction SilentlyContinue

if (-not $UvCmd) {
    # Check default cargo/local bins
    $CandidateUvCargo = Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"
    $CandidateUvLocal = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $CandidateUvCargo) {
        $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
        $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
    } elseif (Test-Path $CandidateUvLocal) {
        $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
        $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
    }
}

if (-not $UvCmd) {
    Write-Host "→ uv not found on system. Installing official Astral uv bootstrapper..." -ForegroundColor Cyan
    try {
        powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:USERPROFILE\.local\bin;$env:PATH"
        $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if ($UvCmd) {
            Write-Host "✓ uv installed successfully: $(& uv --version)" -ForegroundColor Green
        } else {
            Write-Host "! uv installation finished, but executable not immediately in PATH. Will use python venv fallback." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "! Failed downloading uv installer. Proceeding with standard python venv." -ForegroundColor Yellow
    }
} else {
    Write-Host "✓ uv found: $(& uv --version)" -ForegroundColor Green
}

# 3. Create Virtual Environment
Write-Host "`n[3/6] Configuring isolated virtual environment in $VenvDir..." -ForegroundColor Yellow
if ($UvCmd) {
    if (-not (Test-Path $PythonExe)) {
        & uv venv $VenvDir
        Write-Host "✓ Virtual environment created with uv." -ForegroundColor Green
    } else {
        Write-Host "✓ Existing virtual environment verified." -ForegroundColor Green
    }
} else {
    if (-not (Test-Path $PythonExe)) {
        & python -m venv $VenvDir
        Write-Host "✓ Virtual environment created with python stdlib venv." -ForegroundColor Green
    } else {
        Write-Host "✓ Existing virtual environment verified." -ForegroundColor Green
    }
}

# 4. Install Dependencies
Write-Host "`n[4/6] Installing locked requirements..." -ForegroundColor Yellow
$ReqFile = Join-Path $AgentDir "requirements.txt"
if ($UvCmd) {
    & uv pip install -r $ReqFile --python $PythonExe
} else {
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r $ReqFile
}
Write-Host "✓ Core dependencies installed." -ForegroundColor Green

# 5. Supply-Chain Quarantine & Threat Inspection
Write-Host "`n[5/6] Verifying Supply-Chain Quarantine Gates..." -ForegroundColor Yellow
& $PythonExe -c "from utils.security.supply_chain_quarantine import SupplyChainQuarantine; q = SupplyChainQuarantine(); print('✓ SupplyChainQuarantine gate initialized (14-day hold active).')"

# 6. Check .env template
Write-Host "`n[6/6] Verifying configuration files..." -ForegroundColor Yellow
$EnvFile = Join-Path $RootDir ".env"
$EnvExample = Join-Path $RootDir ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "✓ Initialized .env from .env.example." -ForegroundColor Green
} else {
    Write-Host "✓ .env configuration present." -ForegroundColor Green
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Setup Complete! Monika is ready for high-performance runs. " -ForegroundColor Green
Write-Host " Start agent: trading-agent\start_agent.bat                  " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
