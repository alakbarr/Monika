# Monika Central Banks Skill Package (`monika-central-banks-monetary-policy`)

Analysis of Central Bank Reaction Functions (Fed, ECB, BoE, BoJ, RBA), Neutral Rate (r*) Modeling, and the FX Algebraic Sign Invariant.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Contoh Penggunaan CLI

```bash
python scripts/cb_differential_calc.py \
  --base-currency GBP \
  --quote-currency JPY \
  --base-rate 4.75 \
  --quote-rate 0.25 \
  --base-inflation 2.6 \
  --quote-inflation 2.8
```
