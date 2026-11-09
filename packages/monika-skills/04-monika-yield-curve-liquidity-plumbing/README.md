# Monika Yield Curve & Liquidity Plumbing Skill (`monika-yield-curve-liquidity-plumbing`)

Quantitative Modeling of US Treasury Yield Curve (2s10s, Real Yields, Breakeven), Federal Reserve Systemic Net Liquidity (WALCL - TGA - RRP), and Credit Stress Gates.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Eksekusi CLI

```bash
python scripts/macro_liquidity_calc.py \
  --walcl 7050 \
  --tga 820 \
  --rrp 210 \
  --prev-net-liq 6100 \
  --us10y 4.45 \
  --us2y 4.25 \
  --tips10y 2.10 \
  --vix 18.2 \
  --hy-oas 355
```
