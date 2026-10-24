# ==============================================================================
# Monika Algorithmic Trading System - Automated Windows VPS Installer
# Designed for clean Windows Server 2022 / 2025 and Windows 10/11 VPS instances.
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# Set TLS 1.2 / 1.3 for secure web downloads
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "         MONIKA ALGORITHMIC TRADING SYSTEM - WINDOWS VPS SETUP        " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Welcome to the automated Monika installation wizard for Windows VPS."
Write-Host "This script configures Python runtime, firewall ingress, credentials,"
Write-Host "database persistence, and background service autostart." -ForegroundColor Gray
Write-Host ""

# Determine Monika Project Root Directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Split-Path -Parent $ScriptDir
Set-Location -Path $RootDir

# 1. Administrator Elevation Check
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "[!] Note: Not running as Administrator. Windows Firewall and Task Scheduler" -ForegroundColor Yellow
    Write-Host "    features require elevated privileges. Re-running with elevation..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Definition)`"" -Verb RunAs
    exit 0
}

# 2. Public IP Detection
$PublicIP = "YOUR_VPS_IP"
try {
    $PublicIP = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 5 -UseBasicParsing).Trim()
} catch {
    try {
        $PublicIP = (Invoke-RestMethod -Uri "https://ifconfig.me/ip" -TimeoutSec 5 -UseBasicParsing).Trim()
    } catch {
        $PublicIP = "127.0.0.1"
    }
}

# 3. Python 3.14 Runtime Verification & Silent Installation
Write-Host "`n[1/5] Verifying Python 3.14 runtime environment..." -ForegroundColor Blue

$PythonCmd = $null
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $ver = python --version 2>&1
    if ($ver -match "Python 3\.1[4-9]") {
        $PythonCmd = "python"
        Write-Host "[OK] Detected compatible Python runtime: $ver" -ForegroundColor Green
    }
}
if (-not $PythonCmd -and (Get-Command "py" -ErrorAction SilentlyContinue)) {
    $ver = py -3 --version 2>&1
    if ($ver -match "Python 3\.1[4-9]") {
        $PythonCmd = "py -3"
        Write-Host "[OK] Detected compatible Python runtime via py launcher: $ver" -ForegroundColor Green
    }
}

if (-not $PythonCmd) {
    Write-Host "[*] Python 3.14 was not found in PATH. Initiating automated silent install..." -ForegroundColor Yellow
    $InstallerPath = Join-Path $env:TEMP "python-3.14.0-amd64.exe"
    Write-Host "[*] Downloading official installer from python.org..." -ForegroundColor Gray
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.14.0/python-3.14.0-amd64.exe" -OutFile $InstallerPath -UseBasicParsing

    Write-Host "[*] Installing Python 3.14 (AllUsers=1, PrependPath=1)..." -ForegroundColor Gray
    $installProc = Start-Process -FilePath $InstallerPath -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -PassThru
    Remove-Item $InstallerPath -Force -ErrorAction SilentlyContinue

    if ($installProc.ExitCode -ne 0) {
        Write-Host "[ERROR] Python 3.14 installation exited with code $($installProc.ExitCode)." -ForegroundColor Red
        exit 1
    }

    # Refresh PATH environment variable in current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $PythonCmd = "python"
    Write-Host "[OK] Python 3.14 successfully installed and registered to system PATH." -ForegroundColor Green
}

# 4. Virtual Environment & Dependencies
Write-Host "`n[2/5] Initializing virtual environment and installing dependencies..." -ForegroundColor Blue
$VenvDir = Join-Path $RootDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Creating virtual environment at venv..." -ForegroundColor Gray
    & $PythonCmd -m venv $VenvDir
}

Write-Host "[*] Upgrading pip and installing required packages..." -ForegroundColor Gray
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r (Join-Path $RootDir "requirements.txt") --quiet
& $VenvPython -m pip install -e . --no-deps --quiet
Write-Host "[OK] Virtual environment and dependencies are ready." -ForegroundColor Green

# 5. Windows Defender Firewall Configuration (Port 8000)
Write-Host "`n[3/5] Configuring Windows Defender Firewall ingress rules..." -ForegroundColor Blue
try {
    $ExistingRule = Get-NetFirewallRule -DisplayName "Monika Trading Dashboard" -ErrorAction SilentlyContinue
    if (-not $ExistingRule) {
        New-NetFirewallRule -DisplayName "Monika Trading Dashboard" `
                            -Description "Inbound access to Monika Web Dashboard and Observability REST API" `
                            -Direction Inbound `
                            -LocalPort 8000 `
                            -Protocol TCP `
                            -Action Allow | Out-Null
        Write-Host "[OK] Inbound firewall rule created for TCP port 8000." -ForegroundColor Green
    } else {
        Write-Host "[OK] Firewall rule for Monika Dashboard (Port 8000) already active." -ForegroundColor Green
    }
} catch {
    Write-Host "[WARN] Could not automatically configure firewall rule: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 6. Interactive Configuration & Secrets Setup
Write-Host "`n[4/5] Configuring Environment Secrets & Parameters..." -ForegroundColor Blue

$EnvFile = Join-Path $RootDir ".env"
if (-not (Test-Path $EnvFile)) {
    $EnvExample = Join-Path $RootDir ".env.example"
    if (Test-Path $EnvExample) {
        Copy-Item -Path $EnvExample -Destination $EnvFile
        Write-Host "[OK] Initialized .env from .env.example." -ForegroundColor Green
    } else {
        New-Item -Path $EnvFile -ItemType File | Out-Null
    }
}

function Set-EnvVar($key, $val) {
    $content = Get-Content -Path $EnvFile -Raw -Encoding UTF8
    if ($content -match "(?m)^$key=") {
        $content = $content -replace "(?m)^$key=.*", "$key=$val"
    } else {
        $content = $content.TrimEnd() + "`r`n$key=$val`r`n"
    }
    Set-Content -Path $EnvFile -Value $content -Encoding UTF8
}

function Get-EnvVar($key) {
    $line = (Get-Content -Path $EnvFile -Encoding UTF8 | Where-Object { $_ -match "^$key=" }) | Select-Object -First 1
    if ($line) { return $line.Substring($key.Length + 1).Trim() }
    return ""
}

# Prompt: Trading Mode
Write-Host ""
Write-Host "Select Trading Mode:" -ForegroundColor White
Write-Host "  1) Paper Trading Sandbox (Safe, simulated funds - Recommended for initial setup)"
Write-Host "  2) Live MT5 Broker Execution (Connects directly to live/demo MT5 terminal)"
$modeChoice = Read-Host "Enter choice [1 or 2, default: 1]"
if ($modeChoice -eq "2") {
    Set-EnvVar "PAPER_TRADING_ENABLED" "false"
    Set-EnvVar "PAPER_TRADING_MODE" "false"
    Write-Host "[!] Live broker execution selected." -ForegroundColor Yellow
} else {
    Set-EnvVar "PAPER_TRADING_ENABLED" "true"
    Set-EnvVar "PAPER_TRADING_MODE" "true"
    Write-Host "[i] Paper trading simulation selected." -ForegroundColor Green
}

# Prompt: Google Gemini API Key
Write-Host ""
Write-Host "AI Brain Configuration (Google Gemini API):" -ForegroundColor White
$existingGemini = Get-EnvVar "GEMINI_API_KEY"
if ($existingGemini -and $existingGemini -ne "your_gemini_api_key_here") {
    Write-Host "[OK] GEMINI_API_KEY already configured in .env." -ForegroundColor Green
} else {
    Write-Host "Enter your Google Gemini API Key (Get a free key at https://aistudio.google.com/):"
    $geminiInput = Read-Host "GEMINI_API_KEY"
    if ($geminiInput) {
        Set-EnvVar "GEMINI_API_KEY" $geminiInput.Trim()
        Set-EnvVar "GEMINI_API_KEYS" $geminiInput.Trim()
        Write-Host "[OK] GEMINI_API_KEY saved." -ForegroundColor Green
    }
}

# Prompt: MetaTrader 5 Terminal Credentials
Write-Host ""
Write-Host "MetaTrader 5 Account Configuration:" -ForegroundColor White
$existingMT5Login = Get-EnvVar "MT5_LOGIN"
if ($existingMT5Login -and $existingMT5Login -ne "12345678") {
    Write-Host "[OK] MT5 account credentials already present in .env." -ForegroundColor Green
} else {
    $mt5Login = Read-Host "MT5 Account Login (e.g. 12345678, press Enter to skip for paper trading)"
    if ($mt5Login) {
        $mt5Pass = Read-Host "MT5 Password"
        $mt5Server = Read-Host "MT5 Server Name (e.g. MetaQuotes-Demo)"
        Set-EnvVar "MT5_LOGIN" $mt5Login.Trim()
        Set-EnvVar "MT5_ACCOUNT" $mt5Login.Trim()
        Set-EnvVar "MT5_PASSWORD" $mt5Pass.Trim()
        Set-EnvVar "MT5_SERVER" $mt5Server.Trim()
        Write-Host "[OK] MT5 credentials stored securely." -ForegroundColor Green
    }
}

# Prompt: Database Configuration
Write-Host ""
Write-Host "Database Storage Configuration:" -ForegroundColor White
Write-Host "Do you have an external PostgreSQL database URL (e.g. Supabase, Neon, cloud DB)?"
$useExtDb = Read-Host "Use external DATABASE_URL? (y/N)"
if ($useExtDb -match "^[Yy]") {
    $dbUrl = Read-Host "Enter full async DATABASE_URL (e.g. postgresql+asyncpg://user:pass@host:5432/db)"
    if ($dbUrl) {
        Set-EnvVar "DATABASE_URL" $dbUrl.Trim()
        Set-EnvVar "MONIKA_TIER" "full"
        Set-Content -Path (Join-Path $RootDir ".monika_tier") -Value "full" -Encoding UTF8
        Write-Host "[OK] External PostgreSQL DATABASE_URL configured (Full Package)." -ForegroundColor Green
    }
} else {
    Set-EnvVar "DATABASE_URL" "sqlite+aiosqlite:///data/monika.db"
    Set-EnvVar "MONIKA_TIER" "trial"
    Set-Content -Path (Join-Path $RootDir ".monika_tier") -Value "trial" -Encoding UTF8
    Write-Host "[OK] Zero-configuration SQLite database selected for standalone Windows VPS (Trial Package)." -ForegroundColor Green
}

# Prompt: Telegram Notifications
Write-Host ""
Write-Host "Telegram Notifications (Optional):" -ForegroundColor White
$enableTg = Read-Host "Enable Telegram trade execution alerts & emergency control? (y/N)"
if ($enableTg -match "^[Yy]") {
    $tgToken = Read-Host "Enter Telegram Bot Token (from @BotFather)"
    $tgChatId = Read-Host "Enter Telegram Chat ID (from @userinfobot)"
    if ($tgToken -and $tgChatId) {
        Set-EnvVar "TELEGRAM_BOT_TOKEN" $tgToken.Trim()
        Set-EnvVar "TELEGRAM_ADMIN_CHAT_ID" $tgChatId.Trim()
        Write-Host "[OK] Telegram credentials saved." -ForegroundColor Green
        try {
            $testMsg = "🚀 Monika Algorithmic Trading successfully initialized on Windows VPS ($PublicIP)!"
            Invoke-RestMethod -Uri "https://api.telegram.org/bot$($tgToken.Trim())/sendMessage" `
                              -Method Post `
                              -Body @{ chat_id = $tgChatId.Trim(); text = $testMsg } `
                              -TimeoutSec 5 | Out-Null
            Write-Host "[OK] Telegram test verification message sent successfully." -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Could not dispatch Telegram test message: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# Dashboard Security Key
Write-Host ""
Write-Host "Dashboard Remote Access Security:" -ForegroundColor White
$existingDashKey = Get-EnvVar "DASHBOARD_API_KEY"
if (-not $existingDashKey -or $existingDashKey -eq "change_me_to_a_random_token") {
    $rngBytes = New-Object byte[] 16
    (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($rngBytes)
    $newDashKey = [BitConverter]::ToString($rngBytes).Replace("-", "").ToLower()
    Set-EnvVar "DASHBOARD_API_KEY" $newDashKey
    Set-EnvVar "DASHBOARD_SECRET" $newDashKey
    $existingDashKey = $newDashKey
}
Set-EnvVar "DASHBOARD_BIND_IP" "0.0.0.0"
Set-EnvVar "DASHBOARD_HOST" "0.0.0.0"
Write-Host "[OK] Dashboard configured on 0.0.0.0:8000 with access token: $existingDashKey" -ForegroundColor Green

# 7. Autostart & Keep-Alive Task (Optional)
Write-Host "`n[5/5] Background Autostart & Keep-Alive Setup..." -ForegroundColor Blue
$autostart = Read-Host "Create a Windows Scheduled Task to run Monika automatically 24/7 on boot? (Y/n)"
if (-not $autostart -or $autostart -match "^[Yy]") {
    $TaskName = "MonikaTradingAgent"
    $BatchLauncher = Join-Path $RootDir "start_monika.bat"
    try {
        $action = New-ScheduledTaskAction -Execute $BatchLauncher -Argument "run" -WorkingDirectory $RootDir
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -Force | Out-Null
        Write-Host "[OK] Windows Scheduled Task '$TaskName' registered for 24/7 operation." -ForegroundColor Green
    } catch {
        # Fallback to current user task if SYSTEM elevation fails
        try {
            $userTrigger = New-ScheduledTaskTrigger -AtLogOn
            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $userTrigger -Settings $settings -Force | Out-Null
            Write-Host "[OK] Windows Scheduled Task '$TaskName' registered for current user logon." -ForegroundColor Green
        } catch {
            Write-Host "[WARN] Task Scheduler registration skipped: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# Final Output & Summary
Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "         MONIKA IS READY FOR OPERATION ON WINDOWS VPS!                " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Web Dashboard URL:    " -NoNewline
Write-Host "http://${PublicIP}:8000" -ForegroundColor Cyan
Write-Host "Dashboard API Key:    " -NoNewline
Write-Host "$existingDashKey" -ForegroundColor Yellow
Write-Host ""
Write-Host "Management Cheat Sheet:" -ForegroundColor White
Write-Host "  * Start Monika:     Double-click start_monika.bat or run .\start_monika.bat" -ForegroundColor Cyan
Write-Host "  * Run Self-Doctor:  .\venv\Scripts\python.exe -m monika.interfaces.cli.main doctor --offline" -ForegroundColor Cyan
Write-Host "  * Emergency Stop:   curl -X POST http://localhost:8000/api/v1/kill -H `"X-API-Key: $existingDashKey`"" -ForegroundColor Red
Write-Host ""
Write-Host "Installation completed successfully." -ForegroundColor Green
Write-Host ""
