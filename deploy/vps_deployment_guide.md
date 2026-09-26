# Monika — VPS & Containerized Deployment Guide

Panduan resmi deployment produksi **Monika (AI MT5 Trading Agent)** pada Virtual Private Server (Linux Ubuntu 22.04 / 24.04 LTS).

---

## 1. Arsitektur Deployment VPS (Linux Live Trading)

Karena library resmi MetaTrader 5 Python adalah modul C-extension khusus Windows, Monika menggunakan arsitektur **Adaptive RPC Bridge (`mt5linux` / RPyC)** untuk menjalankan trading live secara native dan stabil di lingkungan Linux VPS:

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
│                        │     mt5server.exe (RPC Server)  │  │
│                        └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Keunggulan Arsitektur:
1. **Transparan**: Monika secara otomatis menginjeksi adapter kompatibilitas (`execution/mt5_compat.py`) ke `sys.modules["MetaTrader5"]`. Seluruh modul (`mt5_client.py`, `position_synchronizer.py`, `self_healing_executor.py`, dll.) beroperasi tanpa perlu modifikasi baris kode apa pun.
2. **Dual-Environment Ready**:
   - Jika dijalankan di **Windows**: otomatis menggunakan paket native `MetaTrader5` berkecepatan tinggi.
   - Jika dijalankan di **Linux VPS**: otomatis mengaktifkan RPC Proxy ke `mt5server.exe` pada host/port yang ditentukan.
   - Jika terminal tidak aktif: fallback aman dengan seluruh konstanta ENUM resmi MT5 tersedia (paper-trading dan mock test tetap lulus 100%).

---

## 2. Persyaratan Minimum VPS

- **OS**: Ubuntu 22.04 LTS atau 24.04 LTS (x86_64)
- **CPU**: 2 vCPU
- **RAM**: 4 GB (8 GB direkomendasikan untuk simultaneous MT5 + LLM streaming + Dashboard)
- **Disk**: 40 GB NVMe SSD
- **Network**: Latensi broker rendah (< 50ms ke broker server FBS/lainnya)

---

## 3. Opsi A: Deployment Cepat Menggunakan Docker Compose (Direkomendasikan)

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

### Langkah 2: Clone Repository & Siapkan Konfigurasi Lingkungan
```bash
git clone https://github.com/your-repo/monika.git /opt/monika
cd /opt/monika

# Siapkan file .env dari template
cp .env.example .env
nano .env  # Isi kredensial API LLM & MT5
```

Pastikan variabel berikut disesuaikan untuk RPC Bridge di VPS:
```ini
MT5_LINUX_HOST=mt5-wine
MT5_LINUX_PORT=18812
```

### Langkah 3: Siapkan Terminal MT5 & `mt5server.exe`
Salin folder instalasi MetaTrader 5 dari Windows ke direktori `/opt/mt5` di VPS (atau mount volume), pastikan file `terminal64.exe` dan `mt5server.exe` tersedia:
```bash
mkdir -p /opt/mt5
# Salin terminal64.exe dan mt5server.exe ke /opt/mt5
```

### Langkah 4: Jalankan Stack Produksi
```bash
# Build dan jalankan seluruh container (DB, Agent, MT5)
docker compose -f deploy/docker-compose.vps.yml up -d --build

# Pantau log startup agen
docker compose -f deploy/docker-compose.vps.yml logs -f agent
```

---

## 4. Opsi B: Deployment Standalone Tanpa Docker (Systemd Service)

Jika ingin menjalankan Monika secara native di host Linux VPS:

1. **Pasang Wine & Xvfb**:
   ```bash
   sudo dpkg --add-architecture i386
   sudo apt-get update && sudo apt-get install -y wine wine64 wine32 xvfb
   ```
2. **Pasang Dependencies Python**:
   ```bash
   pip install -r trading-agent/requirements.txt
   ```
   *(Secara otomatis menginstal `mt5linux` dan `rpyc` di Linux).*

3. **Jalankan Xvfb dan MT5 Server**:
   ```bash
   # Jalankan display virtual
   Xvfb :99 -screen 0 1024x768x16 &
   export DISPLAY=:99

   # Jalankan MetaTrader 5 terminal
   wine /path/to/terminal64.exe /portable &

   # Jalankan MT5 RPC Server (port 18812)
   wine /path/to/mt5server.exe -p 18812 &
   ```

4. **Jalankan Monika**:
   ```bash
   export MT5_LINUX_HOST=127.0.0.1
   export MT5_LINUX_PORT=18812
   bash trading-agent/start_agent.sh
   ```

---

## 5. Struktur Layanan `docker-compose.vps.yml`

| Service | Image / Build | Fungsi | Port Host |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | Database PostgreSQL + ekstensi pgvector | `127.0.0.1:5432` |
| `agent` | `Dockerfile` | Monika Core (Python 3.11, Schedulers, FastAPI) | `127.0.0.1:8000` |
| `mt5-wine` | `deploy/Dockerfile.mt5-wine` | Headless MetaTrader 5 via Wine + `mt5server.exe` RPC Bridge | `127.0.0.1:18812` |

---

## 6. Reverse Proxy Nginx untuk Dashboard UI & WebSockets

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

## 7. Cold-Start & Health Monitoring

1. **Watchdog Deadlock Diagnostics**: Jika container mengalami deadlock saat inisialisasi, `StartupWatchdog` secara otomatis mencetak stack traceback semua thread ke stderr dan keluar dengan exit code `75` agar Docker me-restart container secara otomatis.
2. **Preflight Verification**: Saat startup, agen memverifikasi broker ping, rekonsiliasi posisi in-flight, dan kesegaran quote harga sebelum scheduler diaktifkan.
3. **Emergency Stop**: Gunakan perintah Telegram `/kill` atau Dashboard UI untuk menutup seluruh posisi seketika saat darurat.
