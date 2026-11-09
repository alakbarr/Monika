# Monika Data Gathering Skill Package (`monika-data-gathering`)

Protocol for 5-Phase Sequential Market Telemetry Extraction, TTL Verification, Session Timing, and Untrusted Content Security Isolation.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

Jalankan script validasi telemetri tanpa dependensi eksternal:
```bash
# Cek sesi aktif dan blackout
python scripts/telemetry_validator.py --now-utc "2026-11-10T14:30:00Z" --symbol EURUSD

# Cek TTL data dengan JSON timestamp
python scripts/telemetry_validator.py --now-utc "2026-11-10T14:30:00Z" --timestamps-json '{"fedwatch":"2026-11-10T01:00:00Z","vix":"2026-11-10T12:00:00Z"}'
```
