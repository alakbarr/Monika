# Monika SMC/ICT Price Action Skill Package (`monika-smc-ict-price-action`)

Institutional Smart Money Concepts (SMC/ICT), 3-Zone Spatial Dealing Range (pos), Anti-Chasing Floor/Ceiling, and 20-Point Confluence Scorecard.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
python scripts/smc_confluence_calc.py \
  --close 1.08250 \
  --high20 1.09600 \
  --low20 1.08050 \
  --atr14 0.00380 \
  --pdl 1.08100 \
  --confluence-score 13
```
