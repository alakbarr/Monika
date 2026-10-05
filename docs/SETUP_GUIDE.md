# Monika - Panduan Instalasi dan Pengaturan Sistem / System Setup and Installation Guide

Daftar Bahasa / Language Index:
- [Bahasa Indonesia](#panduan-bahasa-indonesia)
- [English Guide](#english-guide)

---

<a name="panduan-bahasa-indonesia"></a>
# Panduan Bahasa Indonesia

## 1. Pendahuluan dan Ringkasan Arsitektur

Monika adalah framework agen riset kuantitatif dan supervisi transaksi otonom berbasis kecerdasan buatan untuk MetaTrader 5 (MT5). Sistem ini dibangun dengan prinsip utama: **AI Proposes, Mechanical Fortress Disposes**. Model bahasa besar (Large Language Model / LLM) bertugas menganalisis narasi makroekonomi, struktur pasar (Smart Money Concepts / SMC), dan melakukan debat adversarial (Bull vs Bear). Seluruh perhitungan matematika floating-point, ukuran posisi lot, dan batasan risiko modal dikelola secara deterministik oleh modul Python dan RiskGate yang tidak dapat dilewati.

Dokumen ini menyediakan instruksi instalasi lengkap, mulai dari tahap evaluasi awal tanpa risiko hingga deployment tingkat institusional pada server VPS.

---

## 2. Perbandingan Paket Instalasi: Trial vs Full

Monika menyediakan dua profil paket instalasi yang dirancang untuk kebutuhan berbeda:

| Parameter | Trial Package (Rekomendasi Awal) | Full Package (Produksi & Institusional) |
| :--- | :--- | :--- |
| Tujuan Utama | Evaluasi analitik pasar dan simulasi strategi | Eksekusi transaksi riil dan pemantauan multi-proses |
| Estimasi Waktu Setup | 2 hingga 3 menit | 10 hingga 15 menit |
| Mesin Database | SQLite lokal (Otomatis dibuat di data/monika.db) | PostgreSQL 16+ dengan ekstensi pgvector |
| Eksekusi Transaksi | Pure Paper Trading Sandbox (Simulasi internal) | Dual Engine: Paper Trading dan MT5 Live Broker IPC |
| MetaTrader 5 | Opsional (Sistem berjalan tanpa aplikasi MT5) | Wajib terpasang untuk routing order ke broker |
| Model Kecerdasan Buatan | Google Gemini Free Tier (Rotasi multi-key) | Multi-Provider Matrix (Claude, GPT, Gemini, Groq) |
| Antarmuka Pengguna | Terminal CLI Interaktif dan Supervisi Telegram | React 19 Web Cockpit, Terminal UI (TUI), Telegram |
| AI Routing Gateway | Koneksi langsung ke API provider | 9Router Local Gateway (Port 20128) |
| Prediksi Volatilitas | ATR (14) dan Average Daily Range (ADR) | Google TimesFM 3.0 Neural Quantile Forecaster |

> [!NOTE]
> Sistem mendukung migrasi bertahap. Anda dapat menginstal Trial Package terlebih dahulu, lalu menjalankan perintah `python -m cli.main upgrade` saat siap beralih ke Full Package. Seluruh riwayat analisis akan dipertahankan.

---

## 3. Prasyarat Sistem Minimum

### Spesifikasi Perangkat Keras
- CPU: 2 Core (Trial) / 4 Core atau lebih (Full)
- RAM: Minimum 2 GB (Trial) / 4 GB hingga 8 GB (Full)
- Ruang Penyimpanan: Minimum 1 GB ruang kosong (Trial) / 5 GB ruang kosong (Full, mencakup bobot TimesFM dan log PostgreSQL)

### Sistem Operasi yang Didukung
- Windows 10 / 11 (64-bit) atau Windows Server 2019/2022 (Direkomendasikan untuk live MT5)
- Linux: Ubuntu 22.04 LTS atau Ubuntu 24.04 LTS (Natif untuk Paper Trading, Wine/Docker untuk live MT5)
- macOS: Apple Silicon (M1/M2/M3) atau Intel x64 (Khusus mode Paper Trading dan Web Dashboard)

### Dependensi Dasar
- Python: Versi 3.11 atau 3.12 (64-bit)
- Git: Versi terbaru
- Node.js & npm: Versi 18 LTS ke atas (Hanya diperlukan untuk Full Package Web Dashboard)

---

## 4. Persiapan Kredensial Kecerdasan Buatan (Google Gemini Free Tier)

Monika membutuhkan kredensial LLM untuk menjalankan pipeline analisis. Google menyediakan akses gratis tanpa kewajiban kartu kredit.

### Prosedur Mendapatkan API Key
1. Kunjungi konsol resmi: https://aistudio.google.com/apikey
2. Masuk menggunakan akun Google Anda.
3. Klik tombol **Create API Key**.
4. Salin string kunci yang diawali dengan format `AIzaSy...`.

### Manajemen Kuota dan Strategi Multi-Key
Google Gemini Free Tier memberlakukan batas kuota harian (Request per Day / RPD):
- Gemini 3.5 / 3.6 / 3.7 / 3.8 Flash: 20 RPD
- Gemini 3.1 / 3.5 Flash Lite: 500 RPD

Untuk siklus analisis berkelanjutan, satu API key dapat mengalami throttling (Error 429). Monika menyediakan fitur *Key Rotation Pool*:
- Buat 2 hingga 3 API key (dapat dibuat di dalam proyek Google Cloud yang sama atau berbeda).
- Pada saat menjalankan wizard setup, masukkan seluruh kunci dipisahkan tanda koma:
  `AIzaSyKey1..., AIzaSyKey2..., AIzaSyKey3...`
- Monika akan memvalidasi setiap kunci secara otomatis menggunakan uji 1-token dan merotasi pemanggilan antar kunci secara bergantian.

---

## 5. Prosedur Instalasi Windows (Satu Titik Masuk)

Instalasi pada sistem operasi Windows menggunakan launcher tunggal `start_monika.bat` di root direktori.

### Langkah Instalasi
1. Unduh atau clone repository:
   ```cmd
   git clone https://github.com/alakbarr/Monika.git
   cd Monika
   ```
2. Jalankan launcher utama:
   ```cmd
   start_monika.bat
   ```
3. Launcher akan mengeksekusi alur verifikasi otomatis:
   - Memeriksa ketersediaan Python 3.11+. Jika belum terpasang, sistem menawarkan instalasi instan melalui Windows Package Manager (`winget`).
   - Membuat virtual environment di folder `trading-agent\venv`.
   - Menginstal dependensi Python dari file `requirements.txt`.
   - Membuka Interactive Setup Wizard:
     - Pilih opsi `[1] Trial Package` untuk konfigurasi cepat tanpa database eksternal.
     - Masukkan API key Google Gemini yang telah disiapkan.
     - Tentukan konfigurasi Telegram jika ingin pemantauan jarak jauh.
4. Selesai. Agen langsung aktif dan memantau instrumen pasar.

---

## 6. Prosedur Instalasi Linux / macOS / Server VPS Ubuntu

Pada sistem berbasis Unix, seluruh alur dikelola melalui script `start_monika.sh`.

### Langkah Instalasi
1. Masuk ke terminal dan unduh kode sumber:
   ```bash
   git clone https://github.com/alakbarr/Monika.git
   cd Monika
   ```
2. Berikan izin eksekusi dan jalankan script:
   ```bash
   chmod +x start_monika.sh
   ./start_monika.sh
   ```
3. Script akan memverifikasi runtime Python 3, menyusun virtual environment di `trading-agent/venv`, dan mengarahkan operator ke wizard setup interaktif.

### Deployment VPS 24/7 Berbasis Systemd (Opsi Lanjutan)
Untuk menjalankan Monika sebagai background service yang otomatis restart saat server reboot:
1. Salin template service ke systemd:
   ```bash
   sudo cp trading-agent/systemd/monika.service /etc/systemd/system/
   sudo nano /etc/systemd/system/monika.service
   ```
2. Sesuaikan direktori kerja dan user, lalu aktifkan:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable monika
   sudo systemctl start monika
   sudo systemctl status monika
   ```

---

## 7. Prosedur Kontainerisasi Docker pada VPS

Bagi pengguna VPS yang menginginkan isolasi penuh tanpa mengkonfigurasi dependensi host:
1. Pastikan Docker dan Docker Compose telah terpasang di VPS:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin
   ```
2. Salin file template environment:
   ```bash
   cp trading-agent/.env.example .env
   nano .env
   ```
3. Jalankan container orchestration:
   ```bash
   docker compose -f deploy/docker-compose.vps.yml up -d --build
   ```
   Langkah ini akan menyalakan kontainer PostgreSQL 16 dengan pgvector, kontainer runtime Monika, dan kontainer headless MT5 Wine secara otomatis.

---

## 8. Konfigurasi MetaTrader 5 dan MQL5 Watchdog EA

### Pure Paper Trading Sandbox (Trial Mode)
Pada Trial Package, Monika mengaktifkan emulator broker internal (`execution/order_emulator.py`). Seluruh order, slippage simulasi, dan trailing stop dihitung berdasarkan data tick tanpa membuka aplikasi MT5. Tidak ada risiko dana riil.

### Menghubungkan ke Terminal MetaTrader 5 (Full Mode)
Jika beralih ke live execution pada Windows:
1. Buka terminal MetaTrader 5 Desktop.
2. Pastikan tombol **Algo Trading** pada toolbar utama terminal berwarna hijau (aktif).
3. Masuk ke menu: **Tools -> Options -> Expert Advisors**.
   - Centang **Allow automated trading**.
   - Centang **Allow WebRequest for listed URL** (tambahkan `http://localhost`).
4. Kompilasi Expert Advisor Pengawas (`AIAgent_EA.mq5`):
   - Buka MetaEditor di MT5.
   - Buka file `trading-agent/execution/ea_bridge/AIAgent_EA.mq5`.
   - Tekan F7 untuk kompilasi hingga menghasilkan file `AIAgent_EA.ex5`.
   - Pasang EA tersebut ke salah satu chart di terminal MT5. EA ini berfungsi sebagai *dead-man's switch* yang otomatis mengamankan posisi terbuka jika proses Python terputus lebih dari 120 detik.

---

## 9. Konfigurasi Notifikasi dan Supervisi Telegram

Integrasi Telegram memungkinkan operator menerima kartu analisis, persetujuan sinyal, dan perintah kendali darurat langsung dari ponsel.

### Prosedur Konfigurasi
1. Hubungi `@BotFather` di aplikasi Telegram.
2. Kirim perintah `/newbot` dan ikuti petunjuk hingga menerima token otentikasi HTTP API:
   Contoh format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
3. Hubungi `@userinfobot` di Telegram untuk mengetahui User ID numerik Anda:
   Contoh format: `987654321`
4. Masukkan kedua nilai tersebut ke dalam file `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_ADMIN_CHAT_ID=987654321
   ```
5. Perintah utama pada bot:
   - `/status`: Menampilkan status koneksi broker, equity, dan task yang berjalan.
   - `/positions`: Menampilkan seluruh tiket posisi terbuka beserta level SL/TP.
   - `/brief`: Mengambil ringkasan narasi fundamental dan bias mata uang terkini.
   - `/risk`: Memeriksa persentase drawdown harian terhadap pagu RiskGate.
   - `/pause` dan `/resume`: Menghentikan sementara atau melanjutkan eksekusi otonom.
   - `/kill`: Perintah darurat untuk melikuidasi posisi aktif dan membekukan agen.

---

## 10. Prosedur Upgrade Paket: Dari Trial ke Full

Jika Anda telah menguji Monika dalam mode Trial dan ingin mengaktifkan Web Dashboard, database PostgreSQL, dan integrasi penuh:

Jalankan perintah upgrade interaktif:
```bash
python -m cli.main upgrade
```

### Tahapan yang Dijalankan oleh Assistant Upgrade
1. **Verifikasi Database**: Mengonfirmasi koneksi PostgreSQL. Jika belum memiliki server PostgreSQL lokal, wizard menawarkan inisialisasi otomatis kontainer Docker `monika-postgres` dan menjalankan migrasi skema tabel via Alembic.
2. **Dashboard Web Frontend**: Memeriksa runtime Node.js dan menginstal paket npm di folder `logging_observability/dashboard/frontend`.
3. **9Router AI Gateway**: Mengaktifkan gateway proxy lokal untuk load balancing model.
4. **Bobot Google TimesFM 3.0**: Menawarkan opsi unduh file bobot model deep learning (~1.3 GB) dari Hugging Face untuk analisis quantile volatilitas.
5. **Pembaruan Konfigurasi**: Mengubah parameter `installation_tier: full` pada file `config/settings.yaml`.

---

## 11. Diagnostik Sistem dan Healthcheck

Sebelum mengoperasikan sistem dalam waktu lama, selalu jalankan modul diagnostik:

```bash
python -m cli.main doctor
```

### Opsi Perintah Tambahan
- Mode Offline (tanpa probe API): `python -m cli.main doctor --offline`
- Perbaikan Otomatis: `python -m cli.main doctor --fix`  
  (Otomatis membuat folder yang hilang, memperbaiki izin file, dan menjalankan migrasi skema yang tertinggal).
- Mode Detail: `python -m cli.main doctor -v`

---

## 12. Panduan Penanganan Kendala Teknis (Troubleshooting FAQ)

### Masalah 1: Error 429 (Resource Exhausted / Rate Limit Exceeded)
- **Penyebab**: Batas kuota gratis Google Gemini telah habis untuk hari tersebut.
- **Solusi**: 
  1. Tambahkan 2 atau 3 API key tambahan di file `.env` pada variabel `GEMINI_API_KEYS=key1,key2,key3`.
  2. Ganti profil operasional ke mode hemat:
     ```bash
     python -m cli.main setup --section llm
     ```
     Pilih profil **6 (Low Latency - Cost-Optimized)** yang mengarahkan tugas ringan ke Gemini Flash-Lite.

### Masalah 2: MT5 Initialize Failed
- **Penyebab**: Path aplikasi `terminal64.exe` tidak tepat, atau MT5 terpasang pada arsitektur 32-bit.
- **Solusi**: Buka file `.env` dan verifikasi nilai `MT5_PATH`. Pastikan mengarah ke binary 64-bit yang valid, misalnya:
  `MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe`

### Masalah 3: Warning "Algo Trading Off"
- **Penyebab**: Fitur automated trading pada terminal MT5 belum diaktifkan secara manual.
- **Solusi**: Klik tombol **Algo Trading** pada toolbar atas aplikasi MT5 hingga berwarna hijau.

### Masalah 4: SQLite Database Locked
- **Penyebab**: Terjadi akses paralel terhadap file database SQLite saat multi-proses berjalan.
- **Solusi**: Pastikan tidak ada dua instance Monika yang berjalan bersamaan. Untuk penggunaan multi-proses intensif, lakukan upgrade ke PostgreSQL menggunakan perintah `python -m cli.main upgrade`.

---

## 13. Referensi Perintah CLI

| Perintah | Deskripsi Fungsi |
| :--- | :--- |
| `python -m cli.main run` | Memulai daemon agen trading Monika |
| `python -m cli.main setup` | Membuka wizard konfigurasi terminal |
| `python -m cli.main upgrade` | Memulai wizard upgrade Trial ke Full Package |
| `python -m cli.main doctor` | Menjalankan inspeksi kesehatan sistem dan dependensi |
| `python -m cli.main status` | Menampilkan metrik operasional dan kesehatan subsistem |
| `python -m cli.main positions` | Menampilkan tabel posisi trading aktif |
| `python -m cli.main analyze [SYMBOL]` | Menjalankan satu siklus analisis ad-hoc untuk instrumen tertentu |
| `python -m cli.main chat` | Membuka sesi percakapan interaktif berbasis teks dengan agen |
| `python -m cli.main tui` | Membuka antarmuka Terminal UI berbasis Textual |
| `python -m cli.main kill` | Perintah darurat: menutup seluruh posisi dan mematikan sistem |

---
---

<a name="english-guide"></a>
# English Guide

## 1. Introduction and Architectural Overview

Monika is an open-source, domain-specific autonomous quantitative research framework and trading agent harness designed for MetaTrader 5 (MT5). The architecture is strictly grounded on the philosophy: **AI Proposes, Mechanical Fortress Disposes**. Large Language Models (LLMs) synthesize macroeconomic context, analyze market microstructures (Smart Money Concepts / SMC), and deliberate over hypotheses via multi-agent Bull/Bear adversarial debate. However, all floating-point calculations, ATR-based lot sizing, portfolio correlations, and risk boundaries are governed deterministically by immutable Python safety gates (RiskGate).

This document serves as the formal technical manual for installing, configuring, and verifying Monika across local development machines, headless Linux instances, and remote VPS deployments.

---

## 2. Package Tier Architecture: Trial vs Full

Monika provides two distinct operational profiles tailored for different deployment stages:

| Dimension | Trial Package (Recommended First) | Full Package (Production & Institutional) |
| :--- | :--- | :--- |
| Primary Objective | Frictionless evaluation of agent reasoning and pipelines | Live institutional execution, multi-process architecture |
| Setup Duration | 2 to 3 minutes | 10 to 15 minutes |
| Persistence Engine | Embedded SQLite (Auto-initialized at data/monika.db) | PostgreSQL 16+ with pgvector extension |
| Trade Execution | Pure Internal Paper Trading Sandbox (Safe simulation) | Dual Engine: Paper Trading and Native MT5 IPC Bridge |
| MT5 Requirement | Optional (Framework operates without MT5 software) | Mandatory for live broker order routing |
| LLM Fabric | Google Gemini Free Tier (Multi-key rotation pool) | Multi-Provider Matrix (Claude, GPT, Gemini, Groq) |
| User Interface | Interactive Terminal CLI and Telegram Supervision | React 19 Web Cockpit, Terminal UI (TUI), Telegram |
| Model Gateway | Direct connection to provider endpoints | 9Router AI Gateway on localhost:20128 |
| Forecasting Engine | Technical Range Analytics (ATR / ADR) | Google TimesFM 3.0 Neural Quantile Forecaster |

> [!NOTE]
> The transition between tiers is fully non-destructive. You can evaluate the system using the Trial Package, then execute `python -m cli.main upgrade` to migrate to the Full Package. All session data and paper trades are preserved.

---

## 3. Minimum System Requirements

### Hardware Specifications
- Processor: 2 Cores (Trial) / 4 Cores or higher (Full)
- Memory (RAM): Minimum 2 GB (Trial) / 4 GB to 8 GB (Full)
- Disk Storage: 1 GB available storage (Trial) / 5 GB available storage (Full, including TimesFM model weights and database storage)

### Operating System Support
- Windows 10 / 11 (64-bit) or Windows Server 2019/2022 (Required for native MT5 IPC)
- Linux: Ubuntu 22.04 LTS or Ubuntu 24.04 LTS (Native for Paper Trading; Wine/RPC for headless MT5 execution)
- macOS: Apple Silicon (M1/M2/M3) or Intel x64 (Paper trading sandbox and observability dashboard only)

### Runtime Dependencies
- Python: Version 3.11 or 3.12 (64-bit)
- Git: Latest release
- Node.js & npm: Version 18 LTS or higher (Required exclusively for compiling the Full Package Web Dashboard)

---

## 4. Artificial Intelligence Credentials Setup (Google Gemini Free Tier)

Monika relies on large language models for macro narrative synthesis and adversarial arbitration. Google provides generous free access without requiring credit card registration.

### Key Acquisition Procedure
1. Navigate to the official Google AI Studio portal: https://aistudio.google.com/apikey
2. Sign in with a standard Google account.
3. Select **Create API Key**.
4. Copy the resulting key string prefixed with `AIzaSy...`.

### Rate Limit Economics and Multi-Key Pool Architecture
Free tier limits operate under daily Request per Day (RPD) quotas:
- Gemini 3.5 / 3.6 / 3.7 / 3.8 Flash: 20 RPD
- Gemini 3.1 / 3.5 Flash Lite: 500 RPD

To prevent operational pauses during multi-stage evaluation cycles:
- Generate 2 to 3 API keys across your Google Cloud projects.
- When prompted during setup, input the keys separated by commas:
  `AIzaSyKey1..., AIzaSyKey2..., AIzaSyKey3...`
- Monika automatically runs a lightweight 1-token probe verification on each key and manages active quota rotation during runtime.

---

## 5. Windows Installation Procedure (Unified Single Entry Point)

On Windows operating systems, the complete installation, environment bootstrap, and startup sequence is managed via `start_monika.bat` in the root repository directory.

### Execution Steps
1. Clone the repository:
   ```cmd
   git clone https://github.com/alakbarr/Monika.git
   cd Monika
   ```
2. Double-click or execute the root launcher:
   ```cmd
   start_monika.bat
   ```
3. The script executes the following automated pipeline:
   - Validates system Python 3.11+. If missing, offers automated installation via `winget`.
   - Bootstraps an isolated virtual environment at `trading-agent\venv`.
   - Resolves and installs dependencies from `requirements.txt`.
   - Detects missing configuration and launches the Interactive Setup Wizard:
     - Select `[1] Trial Package` for zero-configuration setup.
     - Paste your configured Gemini API key pool.
     - Optionally supply Telegram bot credentials.
4. Setup completes, and the daemon initializes immediately.

---

## 6. Linux / macOS / Ubuntu VPS Installation Procedure

On Unix-based operating systems, execution is driven by `start_monika.sh`.

### Execution Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/alakbarr/Monika.git
   cd Monika
   ```
2. Grant execution permissions and launch:
   ```bash
   chmod +x start_monika.sh
   ./start_monika.sh
   ```
3. The script verifies dependencies, initializes `trading-agent/venv`, and launches the setup wizard.

### 24/7 VPS Systemd Daemon Integration
For persistent background operation across server restarts:
1. Copy the systemd unit file:
   ```bash
   sudo cp trading-agent/systemd/monika.service /etc/systemd/system/
   sudo nano /etc/systemd/system/monika.service
   ```
2. Configure active user and directory paths, then register the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable monika
   sudo systemctl start monika
   sudo systemctl status monika
   ```

---

## 7. Containerized Docker Deployment on VPS

For zero-host-configuration deployment on headless Linux servers:
1. Ensure Docker Engine and Docker Compose are installed:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin
   ```
2. Initialize environment credentials:
   ```bash
   cp trading-agent/.env.example .env
   nano .env
   ```
3. Orchestrate the stack:
   ```bash
   docker compose -f deploy/docker-compose.vps.yml up -d --build
   ```
   This deploys PostgreSQL 16 with pgvector, the Monika trading daemon, and a Wine-isolated MetaTrader 5 container.

---

## 8. MetaTrader 5 and MQL5 Watchdog EA Configuration

### Internal Paper Trading Simulation (Trial Mode)
Under the Trial Package, Monika activates `execution/order_emulator.py`. Market movements, synthetic spreads, order fills, and trailing stops are simulated internally without opening MetaTrader 5. Zero risk to trading capital.

### MetaTrader 5 Desktop Bridge (Full Mode)
When deploying live execution on Windows:
1. Launch MetaTrader 5 Desktop.
2. Confirm the **Algo Trading** button in the main toolbar is active (green).
3. Navigate to: **Tools -> Options -> Expert Advisors**.
   - Check **Allow automated trading**.
   - Check **Allow WebRequest for listed URL** (add `http://localhost`).
4. Compile the Watchdog Expert Advisor (`AIAgent_EA.mq5`):
   - Open MetaEditor within MT5.
   - Open `trading-agent/execution/ea_bridge/AIAgent_EA.mq5`.
   - Compile (F7) to generate `AIAgent_EA.ex5`.
   - Attach the compiled EA to an active chart. The EA monitors `heartbeat.txt` and executes defensive liquidations if the Python agent loses contact for more than 120 seconds.

---

## 9. Telegram Bot Supervision and Mobile Cards

Integrating Telegram allows remote operators to inspect analysis transcripts, receive alerts, and issue emergency controls.

### Setup Instructions
1. Message `@BotFather` on Telegram.
2. Submit `/newbot` and follow prompts to obtain your HTTP API Token:
   Example: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
3. Message `@userinfobot` to retrieve your numeric Account ID:
   Example: `987654321`
4. Add these entries to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_ADMIN_CHAT_ID=987654321
   ```
5. Key remote operational commands:
   - `/status`: System health, equity, and active background tasks.
   - `/positions`: Active broker tickets and real-time PnL.
   - `/brief`: Latest Stage 1 macroeconomic narrative.
   - `/risk`: Utilization of daily drawdown boundaries.
   - `/pause` and `/resume`: Suspend or resume autonomous signal dispatching.
   - `/kill`: Emergency kill switch to liquidate positions and halt processes.

---

## 10. Upgrading from Trial to Full Package

To unlock the React 19 Web Dashboard, PostgreSQL storage, and live execution bridges:

Execute the automated upgrade subcommand:
```bash
python -m cli.main upgrade
```

### Upgrade Pipeline Stages
1. **Database Migration**: Tests PostgreSQL connectivity, provides automated Docker spawning if absent, and runs schema migrations via Alembic.
2. **Dashboard Compilation**: Installs npm dependencies in `logging_observability/dashboard/frontend`.
3. **9Router Configuration**: Enables the local routing gateway on port 20128.
4. **Google TimesFM 3.0 Weights**: Optionally downloads neural volatility checkpoint weights (~1.3 GB) from Hugging Face.
5. **Config Persistence**: Writes `installation_tier: full` to `config/settings.yaml`.

---

## 11. System Diagnostics and Self-Healing Engine

Verify your environment configuration before running extended operations:

```bash
python -m cli.main doctor
```

### Advanced Diagnostic Flags
- Offline Validation (skips API pings): `python -m cli.main doctor --offline`
- Automated Remediation: `python -m cli.main doctor --fix`  
  (Automatically repairs missing directories, file permissions, and missing table migrations).
- Verbose Inspection: `python -m cli.main doctor -v`

---

## 12. Troubleshooting and Technical FAQ

### Issue 1: HTTP 429 (Resource Exhausted / Rate Limit Reached)
- **Root Cause**: The active Google Gemini API key exceeded its daily allowance.
- **Remediation**:
  1. Add multiple keys to `.env`: `GEMINI_API_KEYS=key1,key2,key3`.
  2. Switch to cost-optimized routing:
     ```bash
     python -m cli.main setup --section llm
     ```
     Select profile **6 (Low Latency - Cost-Optimized)** to route secondary tasks to Flash-Lite.

### Issue 2: MetaTrader 5 Initialize Failed
- **Root Cause**: Invalid `MT5_PATH` or 32-bit terminal executable.
- **Remediation**: Verify the `MT5_PATH` setting in `.env` points to a 64-bit binary:
  `MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe`

### Issue 3: Warning "Algo Trading Off"
- **Root Cause**: Automated trading is disabled in the terminal interface.
- **Remediation**: Toggle the **Algo Trading** button in the MetaTrader 5 top navigation toolbar until green.

### Issue 4: SQLite Database Locked
- **Root Cause**: Concurrent read/write contention across processes on SQLite WAL files.
- **Remediation**: Ensure only one agent instance runs against the database. For multi-process requirements, upgrade to PostgreSQL via `python -m cli.main upgrade`.

---

## 13. Comprehensive CLI Reference

| Command | Operational Purpose |
| :--- | :--- |
| `python -m cli.main run` | Launch the core trading agent daemon |
| `python -m cli.main setup` | Launch interactive terminal configuration wizard |
| `python -m cli.main upgrade` | Launch interactive Trial-to-Full package upgrade |
| `python -m cli.main doctor` | Execute system diagnostics and environment validation |
| `python -m cli.main status` | Inspect system health, account metrics, and active tasks |
| `python -m cli.main positions` | Print real-time table of open broker orders |
| `python -m cli.main analyze [SYMBOL]` | Trigger an on-demand multi-timeframe analysis cycle |
| `python -m cli.main chat` | Start interactive terminal conversation REPL with agent |
| `python -m cli.main tui` | Launch the full-screen terminal interface (Textual) |
| `python -m cli.main kill` | Emergency halt: liquidate exposure and terminate daemon |
