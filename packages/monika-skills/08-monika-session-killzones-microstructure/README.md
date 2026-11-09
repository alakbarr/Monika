# Monika Session Killzones & Microstructure Skill Package (`monika-session-killzones-microstructure`)

Intraday Session Killzones, London Judas Swing Manipulation, Day-of-Week Liquidity Cycles, Orderbook Imbalance (OBI), and Spread Defense.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
python scripts/session_microstructure_calc.py \
  --spread-current 1.4 \
  --spread-typical 1.1 \
  --bid-vol 210 \
  --ask-vol 120 \
  --now-utc "2026-11-10T14:15:00Z"
```
