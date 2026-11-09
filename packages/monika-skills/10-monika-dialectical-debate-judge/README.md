# Monika Dialectical Debate & Judge Skill Package (`monika-dialectical-debate-judge`)

Adversarial Multi-Agent Dialectical Debate System (Bull vs Bear + Rebuttal Attenuation) and Chief Investment Judge Bayesian Arbitration.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Panduan Penggunaan CLI

```bash
python scripts/debate_judge_calc.py \
  --bull-score 7.5 \
  --bear-score 5.5 \
  --bull-rebuttal 7.0 \
  --bear-rebuttal 4.0 \
  --regime trending \
  --active-criteria-met 4
```
