---
name: monika-dialectical-debate-judge
description: Adversarial multi-agent dialectical debate protocol (Bull Advocate vs Bear Dissenter), Round 2 Rebuttal Attenuation (-3 points), and Chief Investment Judge Bayesian arbitration with Regime Weight Matrices and Anti-Fence-Sitting mandates.
version: 1.0.0
tags: [trading, debate, adversarial, red-team, dialectical, bayesian-judge, risk-arbitration]
---

# Monika Dialectical Debate & Bayesian Judge Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Konstitusi Debat Multi-Agen Universal

Setiap debat investasi di dalam Monika tunduk pada 3 pilar konstitusi:
1. **Larangan Berkompromi**: Analis dilarang bersikap netral ("kedua belah pihak ada benarnya"). Analis Bull wajib berfokus mengeksploitasi peluang kenaikan; Analis Bear bertindak sebagai *Red-Team Skeptic* yang mencari kelemahan mekanis lawan.
2. **Kewajiban Sitasi Angka Minimal 2 Data**: Setiap klaim wajib menyebutkan minimal 2 angka eksak dari telemetri pasar (level harga, pip distance, basis point yield, atau skor persentil COT).
3. **Jangkar Penilaian Eksplisit (1 - 10)**:
   - `1 - 3`: Spekulatif / Lemah / Tidak didukung bukti struktural.
   - `4 - 6`: Menengah / Memiliki sinyal teknikal tetapi ada konflik makro.
   - `7 - 8`: Kuat / Aliran dana institusional terkonfirmasi multi-domain.
   - `9 - 10`: Sangat Kuat / Selaras sempurna secara teknikal, makro, dan likuiditas.

---

## 2. Struktur Debat 2-Ronde & Atenuasi Sanggahan (-3 Poin)

- **Ronde 1: Pengajuan Kasus Utama**:
  - `Bull Advocate`: Membangun hipotesis beli konkret (`LONG_OPTION_A`) dengan skor 1-10.
  - `Bear Dissenter`: Membangun hipotesis jual konkret (`SHORT_OPTION_B`) atau tesis pembatalan dengan rekomendasi (`PROCEED`, `REDUCE_SIZE`, `ABORT`) dan skor keparahan risiko 1-10.
- **Ronde 2: Dialectical Rebuttal**:
  - Pihak yang diserang memberikan sanggahan balik terhadap kelemahan yang dituduhkan.
  - **Aturan Atenuasi Mekanis**: Jika kualitas sanggahan dinilai $\ge 7.0$ (disertai bukti level teknikal atau data makro konkret), maka skor ancaman pihak lawan **otomatis dipotong 3 poin** (dengan lantai minimum 1.0).

---

## 3. Arbitrase Chief Investment Judge

Setelah Ronde 2, Chief Investment Judge memutuskan hasil akhir berdasarkan:

1. **Matriks Bobot Berdasarkan Rezim Pasar**:
   - `trending`: Bobot Teknikal 50%, Makro 35%, Sentimen 15%.
   - `ranging`: Bobot Teknikal 40%, Makro 30%, Sentimen 30%.
   - `volatile`: Bobot Teknikal 35%, Makro 45%, Sentimen 20%.
   - `crisis`: Bobot Teknikal 25%, Makro 55%, Sentimen 20%.
2. **Kalibrasi Skor Brier**:
   - Bobot keagenan dihitung secara matematis: $w_i = (1 / B_i) / \sum (1 / B_j)$ dengan batas $[0.15, 0.65]$.
3. **Mandat Anti-Fence-Sitting**:
   - Jika peluang aktif memenuhi $\ge 3$ kriteria dan selisih skor teratenuasi Bull vs Bear $\ge 1.5$ poin, Hakim **DILARANG** memilih `HOLD` hanya karena keraguan subjektif.
   - Hakim wajib memenangkan arah terbaik dengan mengalibrasikan *Bayesian Risk Multiplier*:
     - Skor Pemenang $\ge 8.0 \rightarrow$ **1.00x** (Full Allocation)
     - Skor Pemenang $\ge 6.5 \rightarrow$ **0.75x** (Three-Quarter Allocation)
     - Skor Pemenang $\ge 5.0 \rightarrow$ **0.50x** (Half Allocation)
     - Skor Pemenang $< 5.0 \rightarrow$ **0.25x** (Quarter Probe Allocation)

Jalankan evaluasi CLI:
```bash
python scripts/debate_judge_calc.py --bull-score 8.0 --bear-score 4.5 --bull-rebuttal 7.5 --bear-rebuttal 4.0 --regime trending
```
