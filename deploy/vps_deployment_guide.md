# Monika — Complete VPS Deployment & Operations Guide (Windows & Linux)

Official production documentation for deploying and operating **Monika (Autonomous AI Quantitative Trading Agent)** on Linux and Windows Virtual Private Servers (VPS).

---

## 1. VPS Deployment Architecture (Arsitektur Deployment VPS)

Because the official MetaTrader 5 Python client library is compiled as a Windows-specific C-extension, Monika features an **Adaptive Execution Layer** that natively supports both Windows environments and containerized Linux servers:

```
┌─────────────────────────────────────────────────────────────┐
│                       VPS Host (Linux)                      │
│                                                             │
│  ┌────────────────┐    ┌─────────────────────────────────┐  │
│  │   PostgreSQL   │    │          Monika Core            │  │
│  │   + pgvector   │<──>│    (Monika Orchestrator)        │  │
│  │   Port: 5432   │    │    Dashboard API & Schedulers   │  │
│  └────────────────┘    └────────────────┬────────────────┘  │
│                                         │                   │
│                               mt5linux RPC Bridge (Port 18812)
│                                         ▼                   │
│                        ┌─────────────────────────────────┐  │
│                        │       Headless MT5 (Wine)       │  │
│                        │     Xvfb + terminal64.exe       │  │
│                        │     RPyC RPC Server Bridge      │  │
│                        └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Strengths:
1. **Seamless Protocol Injection**: Monika injects transparent compatibility shims (`src/monika/infrastructure/brokers/mt5_compat.py`) directly into `sys.modules["MetaTrader5"]`. All upstream analytical modules (`mt5_client.py`, `position_synchronizer.py`, `self_healing_executor.py`) function identically across environments without code changes.
2. **Multi-Environment Adaptability**:
   - **Windows Server VPS**: Leverages the high-speed native `MetaTrader5` binary integration.
   - **Linux VPS**: Automatically routes trade execution to a containerized headless Wine MT5 instance or a remote Windows gateway.
   - **Paper Trading Sandbox**: Fully autonomous local simulation mode that runs anywhere without requiring Wine, Windows, or broker terminal files.

---

## 2. Minimum Hardware Requirements & Sizing (Persyaratan Minimum VPS)

| Component | Minimum Requirements | Recommended Production Tier | Notes |
| :--- | :--- | :--- | :--- |
| **Operating System** | Ubuntu 22.04 / 24.04 LTS (x86_64) or Windows Server 2022/2025 | Ubuntu 24.04 LTS (x86_64) | KVM VPS with root / Administrator access |
| **Processor (vCPU)**| 2 vCPUs | 4 vCPUs | Technical indicators, graph execution & LLM streaming |
| **RAM** | 4 GB | 8 GB | Supports PostgreSQL database, dashboard, & Wine/MT5 |
| **Storage** | 40 GB NVMe SSD | 60+ GB NVMe SSD | Trade journals, tick caches, & vector embeddings |
| **Network** | 100 Mbps port, Unmetered | 1 Gbps port | Low latency to broker trading servers (< 20 ms) |

> [!NOTE]
> **Is Google TimesFM mandatory for running Monika?**<br>
> No. TimesFM is an optional foundation machine learning model for zero-shot volatility forecasting. If TimesFM is not installed, Monika automatically falls back to high-precision statistical volatility engines (ATR, Historical Realized Volatility, and Covariance Matrices) with zero errors. If you elect to install TimesFM on a CPU-only VPS, allocate at least 4 vCPUs and 8 GB RAM.

### Datacenter Location Strategy (Broker Latency)
To minimize execution slippage and trade routing latency, provision your VPS in a datacenter closest to your broker's matching engine:
- **London (LD4 / Slough)**: Standard for European, UK, and global multi-asset brokers.
- **Frankfurt (FR2)**: Continental European regulated brokers.
- **New York (NY4 / Secaucus)**: US equity, commodity, and crypto spot trading hubs.
- **Singapore (SG1) / Tokyo (TY3)**: Asia-Pacific broker networks.

---

## 3. Option A: Automated Linux VPS Deployment (Ubuntu / Debian)

For Linux cloud servers, Monika provides an interactive **Automated 1-Command Installer** that configures Docker, system dependencies, database persistence, and security tokens seamlessly.

### Step 1: Connect to Your VPS via SSH
Open your local terminal or PowerShell and establish an SSH connection:
```bash
ssh root@YOUR_VPS_IP
```

### Step 2: Clone the Monika Repository
```bash
git clone https://github.com/your-username/monika.git /opt/monika
cd /opt/monika
```

### Step 3: Run the Automated Installer
Execute the interactive setup script:
```bash
bash deploy/install_vps.sh
```

The installer performs the following operations automatically:
1. Verifies the OS environment and installs Docker and the Docker Compose plugin if missing.
2. Prompts you to select your **Trading Mode** (Paper Trading Sandbox vs Live MT5 Broker Execution).
3. Configures your **AI Provider** (e.g., Google Gemini API key from Google AI Studio).
4. Configures **PostgreSQL Storage**:
   - **Existing Database**: If you supply an external PostgreSQL connection string (`DATABASE_URL`), Monika binds directly to it and avoids launching an unnecessary local database container.
   - **Local Database**: If you do not have an external database, Monika automatically provisions a local PostgreSQL container with secure, randomly generated credentials.
5. Connects optional **Telegram Notifications** and sends a live verification test message to your Telegram account.
6. Generates a secure **DASHBOARD_API_KEY** and binds the dashboard listener to `0.0.0.0:8000`.
7. Builds and launches all containerized services in the background using `docker compose`.

### Step 4: Access the Observability Dashboard
Once deployment completes, open your browser and navigate to:
```
http://YOUR_VPS_IP:8000
```
- The built-in authentication modal will prompt for your **DASHBOARD_API_KEY** (displayed upon installer completion and stored in `.env`).
- Enter the key to access real-time cockpit metrics, risk boundaries, positions, and telemetry.

---

## 4. Option B: Windows VPS Deployment (Native 1-Click Setup)

Windows VPS offers the most straightforward path for traders wishing to run MetaTrader 5 natively alongside Monika.

### Step 1: Connect via Remote Desktop (RDP)
1. Open **Remote Desktop Connection** (Windows built-in) or Microsoft Remote Desktop (macOS/iOS/Android).
2. Enter your Windows VPS IP address, Username (`Administrator`), and Password.

### Step 2: Clone or Download Monika
Open PowerShell on the Windows VPS and clone the repository:
```powershell
git clone https://github.com/your-username/monika.git C:\Monika
cd C:\Monika
```

### Step 3: Run the Windows VPS Installer (`deploy/install_vps.bat`)
Run the automated Windows VPS installer by double-clicking `deploy\install_vps.bat` or executing it from PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File deploy\install_vps.ps1
```
The automated Windows installer will:
1. Verify Python 3.14. If absent, it downloads and installs Python 3.14 silently via PowerShell.
2. Configure Windows Defender Firewall to allow inbound TCP traffic on port 8000 for remote dashboard access.
3. Detect your Windows VPS public IP address and configure `DASHBOARD_BIND_IP=0.0.0.0` with a secure access key.
4. Initialize an isolated virtual environment (`venv`) and install all required dependencies.
5. Guide configuration of Trading Mode (Paper Trading vs Live MT5), Gemini API keys, Database (Cloud PostgreSQL vs SQLite), and Telegram alerts with an automated test ping.
6. Optionally register Monika as a 24/7 background Windows Scheduled Task so it stays running even when your Remote Desktop session is disconnected.

### Step 4: Daily Operation via `start_monika.bat`
For ongoing daily operations, simply double-click `start_monika.bat` in the root folder, or access the remote dashboard at `http://YOUR_WINDOWS_VPS_IP:8000`.

---

## 5. MetaTrader 5 Execution Options on Linux VPS

When running on Linux, choose from three versatile execution patterns:

### Mode 1: Paper Trading Sandbox (Recommended for Evaluation)
- Requires zero Windows or MetaTrader 5 terminal binaries.
- All analytical loops (SMC, Order Flow, Macro Sentiment, Technical Screening, Risk Gate) run natively on Linux.
- Trades are simulated with realistic spread, slippage, and balance tracking.

### Mode 2: Headless MT5 in Wine (Automated Installation)
- Monika includes a specialized Wine execution container (`deploy/Dockerfile.mt5-wine`).
- The startup script `deploy/entrypoint_mt5.sh` automatically downloads and installs the official `mt5setup.exe` in Wine without manual intervention.
- Alternatively, copy an existing MetaTrader 5 installation directory from Windows into `/opt/mt5` on the VPS.

### Mode 3: Remote Windows Gateway
- Run MetaTrader 5 on a local Windows machine or low-cost Windows VPS.
- Run Monika's AI orchestration engine on your Linux VPS.
- Bridge them over encrypted HTTP by setting `EXECUTION_ADAPTER=remote_gateway` in `.env`.

---

## 6. Daily Operations & System Maintenance

### Essential Docker Commands (Linux VPS):
| Action | Command |
| :--- | :--- |
| **Stream Live Logs** | `docker compose -f deploy/docker-compose.vps.yml logs -f agent` |
| **Restart Agent Service** | `docker compose -f deploy/docker-compose.vps.yml restart agent` |
| **Stop All Services** | `docker compose -f deploy/docker-compose.vps.yml down` |
| **Apply Code Updates** | `git pull && docker compose -f deploy/docker-compose.vps.yml build agent && docker compose -f deploy/docker-compose.vps.yml up -d` |

### Self-Diagnostic Health Verification:
Verify the integrity of all subsystems, configurations, and network endpoints at any time:
```bash
# On Linux (standalone / venv):
venv/bin/python -m monika.interfaces.cli.main doctor --offline

# On Windows VPS:
venv\Scripts\python.exe -m monika.interfaces.cli.main doctor --offline
```

### Emergency Kill Switch:
To immediately halt trade processing, cancel pending proposals, and close positions:
- **Via Web Dashboard**: Click the prominent red **EMERGENCY KILL SWITCH** button in the header bar.
- **Via REST API (cURL)**:
```bash
curl -X POST http://localhost:8000/api/v1/kill -H "X-API-Key: YOUR_DASHBOARD_API_KEY"
```
- **Via Telegram**: Send `/kill` directly to your Monika Telegram bot.

---

## 7. Security Best Practices & Hardening

1. **Firewall Rules (UFW)**: Expose only necessary ingress ports (SSH and Dashboard):
   ```bash
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22/tcp
   sudo ufw allow 8000/tcp
   sudo ufw enable
   ```
2. **Environment Variable Protection**: Keep `.env` strictly confidential with restricted permissions (`chmod 600 .env`). Never commit `.env` to public repositories.
3. **Robust Dashboard API Authentication**: Ensure `DASHBOARD_API_KEY` is configured with a high-entropy secret token to safeguard telemetry and operational controls.
