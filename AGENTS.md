# Panduan Utama AI Trading Agent (AI Assistant Guide)

Selamat datang! File ini adalah instruksi utama bagi sistem AI (seperti Gemini, Claude, atau asisten lainnya) yang bertugas membaca, memahami, atau mengedit codebase proyek ini.

## Aturan Utama yang Wajib Dipatuhi

1. **SELALU BACA `INDEX.md` TERLEBIH DAHULU:**
   Sebelum melakukan eksplorasi, penambahan fitur, pencarian akar masalah (debugging), atau modifikasi codebase apa pun, Anda **WAJIB** merujuk pada file `INDEX.md`. File tersebut berisi indeks komprehensif dari seluruh struktur direktori, file, fungsi, kelas, data, dan variabel di dalam program ini.

2. **Perhatikan dan Perbarui Table of Content di INDEX.md:**
   Terdapat Table of Content (ToC) pada bagian teratas `INDEX.md`. Anda **WAJIB** membaca ToC tersebut terlebih dahulu untuk menemukan di baris (line) mana informasi yang Anda cari berada, lalu gunakan referensi baris tersebut saat mengakses file `INDEX.md`. **PERHATIAN**: Jika Anda melakukan modifikasi codebase, Anda harus mengedit konten `INDEX.md` secara manual (lihat Aturan 8), LALU Anda **WAJIB** menjalankan skrip pembaru ToC dengan perintah: `python scripts/update_index_toc.py` agar referensi baris di ToC tetap akurat. Jangan pernah terbalik atau hanya menjalankan skrip tanpa mengedit isinya!

3. **Jadikan Index Sebagai Patokan Navigasi:**
   Gunakan informasi dari `INDEX.md` untuk mengidentifikasi dengan presisi file mana saja yang berkaitan dengan tujuan atau instruksi dari pengguna. Jangan menebak letak file; pastikan lokasi dan dependensinya tepat berdasarkan apa yang tercatat di dalam index.

4. **Pahami Gambaran Besar Sistem:**
   Selain indeks teknis, Anda harus merujuk pada file arsitektur dan prinsip utama proyek yang terletak di `trading-agent/spesifikasi_final_ai_trading_agent.md`. Dokumen spesifikasi tersebut menjelaskan bagaimana setiap modul terhubung, serta memuat batasan-batasan teknis yang tidak boleh dilanggar (misalnya, sistem *rule-based* vs AI, batasan API, dan sistem *kill-switch*).

5. **Baca dan Pahami Sebelum Mengedit:**
   Ketika Anda telah menemukan file target melalui `INDEX.md`, selalu luangkan waktu untuk membaca isi file tersebut secara menyeluruh agar modifikasi yang Anda buat tepat sasaran dan selaras dengan *codebase* eksisting.

6. **Gunakan Mode Hemat Token (Caveman & RTK):**
   Untuk setiap interaksi atau pekerjaan coding pada direktori ini, **selalu** operasikan asisten dalam mode hemat token. Pastikan skill `caveman` selalu diaktifkan (via slash command `/caveman` atau instruksi serupa) untuk output percakapan, dan gunakan RTK untuk mengompresi output dari shell command.

7. **DILARANG KERAS MEMBACA FILE `.env`:**
   Sistem AI tidak diizinkan dalam kondisi apa pun untuk membuka, membaca, atau mengekstrak isi dari file `.env` di direktori ini demi menjaga keamanan kredensial pengguna.

8. **UPDATE KONTEN `INDEX.md` & `STRUKTUR.md` SETELAH MODIFIKASI:**
   Jika Anda menambahkan/menghapus file, kelas, fungsi, atau variabel, Anda **WAJIB SECARA MANUAL MENGEDIT KONTEN** file `INDEX.md` dan `STRUKTUR.md` agar dokumentasi tetap akurat dengan keadaan *codebase*. Anda **TIDAK BOLEH HANYA** menjalankan skrip `update_index_toc.py` karena skrip tersebut hanya mengupdate nomor baris ToC, BUKAN mendeteksi atau menulis konten baru ke dalam index. Setelah selesai mengedit konten secara manual, barulah jalankan skrip `update_index_toc.py`.

9. **WAJIB MELAKUKAN PENGUJIAN (UNIT TESTING):**
   Setiap selesai melakukan modifikasi, Anda harus menjalankan skrip pengujian (menggunakan pytest). 
   - Jika ada class, metode, atau fungsi tambahan/perubahan, skrip pengujian yang bersangkutan harus diperbarui atau disesuaikan.
   - Jika ada modul baru yang ditambahkan ke dalam codebase, Anda **wajib** membuat file unit test baru khusus untuk modul tersebut sebelum modifikasi dianggap selesai.

10. **DILARANG KERAS MENGHAPUS ATAU MENGKOSONGKAN FILE TANPA PERSETUJUAN EKSPLISIT:**
    Sistem AI dilarang melakukan penimpaan file kosong (0 bytes) atau menghapus file tanpa konfirmasi eksplisit dari pengguna. Selalu pastikan file ditulis kembali secara utuh ketika dilakukan modifikasi.

Dengan mematuhi instruksi ini, pengembangan *AI Trading Agent* akan terkelola dengan baik, mencegah duplikasi pekerjaan, dan menjaga integritas keseluruhan arsitektur.

---

## Quick Start & Key Commands

### Install & Configure
```bash
# Install deps (Python + Dashboard)
make install
# or manually:
pip install -r trading-agent/requirements.txt
cd trading-agent/logging_observability/dashboard/frontend && npm install

# Configure
cp .env.example .env
# Edit .env with required keys (ANTHROPIC_API_KEY, DATABASE_URL, MT5_*, TELEGRAM_*)
```

### Run (dry-run mode by default)
```bash
# Windows:
trading-agent\start_agent.bat
# Linux/macOS:
bash trading-agent/start_agent.sh
# or via Makefile:
make run
```

### Key Commands Reference
| Task | Command |
|------|---------|
| Run tests | `make test` or `PYTHONPATH=trading-agent pytest trading-agent/tests` |
| Run single test | `PYTHONPATH=trading-agent pytest trading-agent/tests/path/to/test.py::test_name -v` |
| Run agent (dry-run) | `python -m main --dry-run` (from trading-agent/) |
| DB migrations | `cd trading-agent && alembic upgrade head` |
| Clean pycache | `make clean` |

---

## Architecture Highlights

- **Entry point**: `trading-agent/main.py` — `TradingAgent` class orchestrates 18+ concurrent async tasks
- **Config**: `trading-agent/config/settings.yaml` loaded via `config/settings.py` (scraping sources reside in `settings.yaml:scraping.sources`)
- **LLM routing**: Centralized in `settings.yaml:llm.task_roles` — 30+ roles with provider fallbacks
- **Database**: PostgreSQL (asyncpg + SQLAlchemy 2.0), alembic migrations in `trading-agent/database/migrations/`
- **MT5 execution**: `execution/mt5_client.py` + `execution/execution_service.py` + EA bridge via heartbeat files
- **Schedulers**: `scheduler/` — GraphCycleScheduler (8h), NewsWatcher (5m), TriggerChecker (2m), PositionGuardian, TrailingStopManager, etc.
- **Analysis pipeline**: Stage 1 (fundamental) → Stage 2 (per-asset with debate) → RiskGate → Execution
- **Paper trading**: Enabled by default (`paper_trading.enabled: true`), accumulates trades before live

---

## Critical Gotchas

1. **PostgreSQL required** — SQLite fails startup checks for live/paper mode (locking issues with async)
2. **`paper_trading.enabled: true` mandatory** — Agent refuses to start without it (safety)
3. **MT5_PATH must exist** — Even for dry-run, validates at startup (warns if missing)
4. **Dry-run default** — Start scripts run with `--dry-run`; live requires `auto_execute: true` + 50+ paper trades @ 55% win rate
5. **Settings validation** — Startup runs extensive checks (model names, tool handlers, DB schema, API keys); fails fast on critical issues
6. **Task roles must match** — Any `get_client_for_task('role')` call must have corresponding entry in `llm.task_roles`
7. **Auto-restart loops** — Start scripts restart agent on crash (30s delay); Ctrl+C twice to stop completely

---

## Testing Notes

- `pytest.ini` configures `pythonpath = trading-agent` and `asyncio_mode = auto`
- Tests organized by module: `tests/analysis/`, `tests/execution/`, `tests/scheduler/`, etc.
- Integration tests require DB + API keys; unit tests mock heavily
- Run focused: `pytest trading-agent/tests/execution/test_execution_service.py -v`

---

## Environment Variables (from .env.example)

**Required**: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `MT5_ACCOUNT`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`  
**Recommended**: `GEMINI_API_KEY` (or `GEMINI_API_KEYS` for rotation), `FRED_API_KEY`, `FINNHUB_API_KEY`  
**Optional**: `EIA_API_KEY`, `DASHBOARD_PORT`, `MT5_COMMON_FILES_PATH`

---

## File Structure (Key Directories)

```
trading-agent/
├── main.py                    # Entry point, orchestrator
├── config/
│   └── settings.yaml          # Main config (includes scraping.sources)
├── analysis/                  # LLM pipeline, debate, tools
├── scheduler/                 # Background tasks (cycle, news, triggers, guardians)
├── execution/                 # MT5 client, execution service, EA bridge
├── risk/                      # Risk gate, position sizing
├── database/                  # SQLAlchemy models, async DB, alembic
├── logging_observability/     # Activity logger, FastAPI dashboard
├── telegram_bot/              # Telegram interface
├── utils/                     # 50+ utility modules
└── tests/                     # Test suite (mirrors source structure)
```

---

## Common Tasks for Agents

- **Add new LLM role**: Edit `settings.yaml:llm.task_roles` + verify in startup check (scans for `get_client_for_task`)
- **Add scheduler task**: Create in `scheduler/`, register in `main.py:TradingAgent._init_components()` + `start()`
- **Modify risk params**: `settings.yaml:trading.risk` — validated at startup (warns on aggressive values)
- **Debug MT5 issues**: Check `execution/mt5_client.py` + heartbeat writer (`execution/ea_bridge/heartbeat_writer.py`)
- **Dashboard**: React frontend in `logging_observability/dashboard/frontend/`, API in `logging_observability/dashboard/api.py`