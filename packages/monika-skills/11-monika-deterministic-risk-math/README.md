# Monika Deterministic Risk Math Skill Package (`monika-deterministic-risk-math`)

Pure Deterministic Mathematical Fortress: Pre-Computed Zero-Arithmetic Bounding Boxes (LONG_OPTION_A / SHORT_OPTION_B), Fixed-Fractional Decimal (ROUND_FLOOR) Lot Sizing, and 12-Point RiskGate Auditing.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
# 1. Generate Pre-Computed Brackets
python scripts/monika_quant_engine.py brackets \
  --symbol EURUSD \
  --price 1.08500 \
  --atr14 0.00400 \
  --adr5d 0.00800

# 2. Calculate Decimal ROUND_FLOOR Position Size
python scripts/monika_quant_engine.py size \
  --equity 10000 \
  --base-risk-pct 1.0 \
  --entry 1.08500 \
  --sl 1.08000 \
  --symbol EURUSD

# 3. Execute 12-Point Pre-Execution RiskGate Audit
python scripts/monika_quant_engine.py risk-gate \
  --symbol EURUSD \
  --direction buy \
  --entry 1.08500 \
  --sl 1.08000 \
  --tp 1.09400 \
  --atr14 0.00400 \
  --adr5d 0.00800 \
  --pos 0.25 \
  --equity 10000
```
