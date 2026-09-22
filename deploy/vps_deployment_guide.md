# Monika v2 — VPS & Containerized Deployment Guide

Panduan resmi deployment produksi **Monika (AI MT5 Trading Agent)** pada Virtual Private Server (Linux Ubuntu 22.04 / 24.04 LTS).

---

## 1. Arsitektur Deployment VPS

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
│                               IPC / IPC Socket / Bridge     │
│                                         ▼                   │
│                        ┌─────────────────────────────────┐  │
│                        │       Headless MT5 (Wine)       │  │
│                        │     Xvfb + terminal64.exe       │  │
│                        │     EA Bridge / Heartbeats      │  │
│                        └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Persyaratan Minimum VPS

- **OS**: Ubuntu 22.04 LTS atau 24.04 LTS (x86_64)
- **CPU**: 2 vCPU
- **RAM**: 4 GB (8 GB direkomendasikan untuk simultaneous MT5 + LLM streaming + Dashboard)
- **Disk**: 40 GB NVMe SSD
- **Network**: Latensi broker rendah (< 50ms ke broker server FBS/lainnya)

---

## 3. Langkah Instalasi Cepat (Quickstart via Docker)

### Langkah 1: Pasang Docker & Docker Compose di VPS
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

### Langkah 2: Clone Repository & Konfigurasi Lingkungan
```bash
git clone https://github.com/your-repo/monika.git /opt/monika
cd /opt/monika

# Siapkan file .env dari template
cp .env.example .env
nano .env  # Isi kredensial API & MT5
```

### Langkah 3: Jalankan Stack Produksi
```bash
# Build dan jalankan seluruh container (DB, Agent, MT5)
docker compose -f deploy/docker-compose.vps.yml up -d --build

# Pantau log startup
docker compose -f deploy/docker-compose.vps.yml logs -f agent
```

---

## 4. Struktur Layanan `docker-compose.vps.yml`

| Service | Image / Build | Fungsi | Port Host |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | Database PostgreSQL + ekstensi pgvector | `127.0.0.1:5432` |
| `agent` | `Dockerfile` | Monika Core (Python 3.11, Schedulers, FastAPI) | `127.0.0.1:8000` |
| `mt5-wine` | `deploy/Dockerfile.mt5-wine` | Headless MetaTrader 5 via Wine & Xvfb | Local bridge |

---

## 5. Reverse Proxy Nginx untuk Dashboard UI & WebSockets

Untuk mengakses Web Dashboard dari internet dengan aman (HTTPS / WSS), pasang Nginx di VPS:

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

## 6. Cold-Start & Health Monitoring

1. **Watchdog Deadlock Diagnostics**: Jika container mengalami deadlock saat inisialisasi, `StartupWatchdog` secara otomatis mencetak stack traceback semua thread ke stderr dan keluar dengan exit code `75` agar Docker me-restart container secara otomatis.
2. **Preflight Verification**: Saat startup, agen memverifikasi broker ping, rekonsiliasi posisi in-flight, dan kesegaran quote harga sebelum scheduler diaktifkan.
3. **Emergency Stop**: Gunakan perintah Telegram `/kill` atau Dashboard UI untuk menutup seluruh posisi seketika saat darurat.
