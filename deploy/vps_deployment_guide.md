# Monika — VPS & Containerized Deployment Guide

Official production deployment guide for **Monika (Autonomous AI MT5 Trading Agent)** on Linux Virtual Private Servers (Ubuntu 22.04 / 24.04 LTS).

---

## 1. VPS Deployment Architecture (Arsitektur Deployment VPS)

Because the official MetaTrader 5 Python library is a Windows-specific C-extension, Monika provides an **Adaptive Execution Layer** supporting multiple deployment modes:

```
┌─────────────────────────────────────────────────────────────┐
│                       VPS Host (Linux)                      │
│                                                             │
│  ┌────────────────┐    ┌─────────────────────────────────┐  │
│  │   PostgreSQL   │    │          Monika Core            │  │
│  │   + pgvector   │<──>│    (TradingAgent Orchestrator)  │  │
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

### Architectural Benefits:
1. **Transparent**: Monika injects compatibility shims (`execution/mt5_compat.py`) into `sys.modules["MetaTrader5"]`. All upstream modules (`mt5_client.py`, `position_synchronizer.py`, `self_healing_executor.py`, etc.) operate without code changes.
2. **Dual-Environment Ready**:
   - **Windows**: Automatically utilizes the high-speed native `MetaTrader5` package.
   - **Linux VPS**: Automatically routes through the RPC proxy to Wine MT5 or a Remote Windows Gateway.
   - **Paper Trading Sandbox**: Fully autonomous simulation mode that does not require Wine or any broker terminal files.

---

## 2. Minimum Hardware Requirements (Persyaratan Minimum VPS)

- **OS**: Ubuntu 22.04 LTS or 24.04 LTS (x86_64)
- **CPU**: 2 vCPUs
- **RAM**: 4 GB (8 GB recommended for concurrent LLM streaming, dashboard, and database)
- **Storage**: 40 GB NVMe SSD
- **Network**: Low broker network latency (< 50ms to your broker trade server)

---

## 3. Option A: Docker Compose Deployment (Recommended)

### Step 1: Install Docker & Docker Compose on the VPS
```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### Step 2: Clone Repository & Configure Environment
```bash
git clone https://github.com/your-repo/monika.git /opt/monika
cd /opt/monika

# Initialize .env from template
cp .env.example .env
nano .env  # Configure AI API keys & broker credentials
```

For Wine RPC bridge deployments, verify:
```ini
MT5_LINUX_HOST=mt5-wine
MT5_LINUX_PORT=18812
```

### Step 3: Choose an Execution Mode on the VPS
- **Mode 1: Paper Trading Sandbox (Recommended)**:
  100% native Linux execution without requiring Wine or terminal files. All reasoning loops, sentiment ingestion, technical screening, and paper executions run seamlessly.
- **Mode 2: Remote Windows MT5 Gateway (Highest Stability for Live Accounts)**:
  Run MetaTrader 5 on a Windows desktop or Windows VPS, set `EXECUTION_ADAPTER=remote_gateway`, and point the gateway URL to the Windows host IP.
- **Mode 3: Headless MT5 in Wine**:
  To run the MT5 binary directly inside the containerized Linux environment:
  ```bash
  mkdir -p /opt/mt5
  # Copy MetaTrader 5 directory (containing terminal64.exe) to /opt/mt5
  ```

### Step 4: Launch Production Stack
```bash
# Build and start all services (DB, Agent, MT5)
docker compose -f deploy/docker-compose.vps.yml up -d --build

# Monitor agent logs
docker compose -f deploy/docker-compose.vps.yml logs -f agent
```

---

## 4. Option B: Standalone Systemd Service Deployment

To run Monika natively on a Linux host without Docker:

1. **Install Wine & Xvfb**:
   ```bash
   sudo dpkg --add-architecture i386
   sudo apt-get update && sudo apt-get install -y wine wine64 wine32 xvfb
   ```
2. **Install Python Dependencies**:
   ```bash
   pip install -r trading-agent/requirements.txt
   ```
   *(Automatically installs `mt5linux` and `rpyc` on Linux).*

3. **Start Xvfb and MT5 RPC Bridge**:
   ```bash
   # Start virtual display
   Xvfb :99 -screen 0 1024x768x16 &
   export DISPLAY=:99

   # Start MetaTrader 5 terminal
   wine /path/to/terminal64.exe /portable &

   # Start RPyC server
   wine python -m rpyc.cli.rpyc_classic --port 18812 &
   ```

4. **Launch Monika**:
   ```bash
   export MT5_LINUX_HOST=127.0.0.1
   export MT5_LINUX_PORT=18812
   bash trading-agent/start_agent.sh
   ```

---

## 5. Services in `docker-compose.vps.yml`

| Service | Image / Build | Role | Host Port |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | PostgreSQL database with pgvector extension | `127.0.0.1:5432` |
| `agent` | `Dockerfile` | Monika Core (Python 3.11, Schedulers, FastAPI) | `127.0.0.1:8000` |
| `mt5-wine` | `deploy/Dockerfile.mt5-wine` | Headless MetaTrader 5 via Wine + RPyC RPC Bridge | `127.0.0.1:18812` |

---

## 6. Nginx Reverse Proxy for Dashboard UI & WebSockets

To expose the Web Dashboard securely over HTTPS / WSS:

```nginx
server {
    server_name monika.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 7. Observability & Health Monitoring

1. **Watchdog Deadlock Diagnostics**: If an initialization deadlock is encountered, `StartupWatchdog` prints full thread stack traces to stderr and exits with status `75`, prompting Docker to restart the container cleanly.
2. **Preflight Verification**: On startup, the agent validates broker latency, reconciles open orders, and checks quote freshness before starting execution schedulers.
3. **Emergency Circuit Breaker**: Use the `/kill` Telegram command or the Web Dashboard UI to liquidate open exposure during market anomalies.
