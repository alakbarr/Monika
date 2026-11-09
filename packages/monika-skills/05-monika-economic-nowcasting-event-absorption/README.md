# Monika Economic Nowcasting Skill Package (`monika-economic-nowcasting-event-absorption`)

Macroeconomic Nowcasting, Net Surprise with Prior Revisions, Canonical 4-Method Priced-In Scoring, and 3-Phase Post-Event Orderflow Absorption Protocol.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
python scripts/event_nowcast_calc.py \
  --actual 2.7 \
  --consensus 2.6 \
  --previous 2.6 \
  --prior-revision 0.1 \
  --priced-in-fedwatch 7.5 \
  --priced-in-cot 6.0 \
  --priced-in-exhaustion 7.0 \
  --priced-in-historical 6.5
```
