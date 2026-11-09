# Monika Commodities, Crypto & Carry Playbooks (`monika-commodities-crypto-carry-playbooks`)

Specialized Quantitative and Fundamental Trading Playbooks for Gold (XAUUSD), Crude Oil (Brent-WTI Stat-Arb & Crack Spread), Bitcoin (Derivatives & ETF Flow), and FX Carry Trades.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
# Evaluasi Carry Trade
python scripts/asset_special_calc.py --asset CARRY --long-rate 4.75 --short-rate 0.25 --implied-vol 8.5 --vix 17.5

# Evaluasi Arbitrase Minyak Mentah
python scripts/asset_special_calc.py --asset OIL --brent-price 78.50 --wti-price 72.00

# Evaluasi Bitcoin
python scripts/asset_special_calc.py --asset BTC --etf-net-inflow-m 250 --funding-rate-8h 0.015
```
