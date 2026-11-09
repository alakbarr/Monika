# Monika COT Positioning Skill Package (`monika-cot-positioning-anti-crowding`)

CFTC Commitment of Traders (COT) Quantitative Crowding Analysis, Contrarian Positioning Discipline, and 5 Institutional Synergy States.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
python scripts/cot_synergy_calc.py \
  --cot-52w-pct 89.5 \
  --tech-dir buy \
  --macro-dir buy \
  --sent-dir sell \
  --tech-conf 80 \
  --macro-conf 85 \
  --sent-conf 65
```
