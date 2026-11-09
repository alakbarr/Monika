---
name: monika-central-banks-monetary-policy
description: Institutional monetary policy analysis covering the 5 major central banks (Fed, ECB, BoE, BoJ, RBA), reaction functions, neutral rate (r*) modeling, and the FX Algebraic Sign Invariant.
version: 1.0.0
tags: [trading, forex, macro, central-banks, monetary-policy, interest-rates]
---

# Monika Central Banks & Monetary Policy Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Fungsi Reaksi 5 Bank Sentral Utama

1. **Federal Reserve (Fed - USD)**:
   - **Mandat Ganda**: Inflasi Core PCE 2.0% & Lapangan Kerja Penuh.
   - **Sahm Rule Indicator**: Kenaikan rata-rata 3 bulan tingkat pengangguran (U-3) $\ge 0.50\%$ dari titik terendah 12 bulan terakhir menandakan resesi $\rightarrow$ Fed akan memotong suku bunga darurat.
   - **Neutral Rate ($r^*$)**: $2.75\% - 3.00\%$.
   - **Prioritas Sinyal**: Probabilitas CME FedWatch, pidato Ketua Powell dan Gubernur Waller.
2. **European Central Bank (ECB - EUR)**:
   - **Mandat Simetris**: Target inflasi HICP 2.0%.
   - **Neutral Rate ($r^*$)**: $2.00\% - 2.25\%$.
   - **Fragmentasi Kedaulatan (TPI)**: Jika spread imbal hasil obligasi Italia-Jerman 10-tahun (BTP-Bund) melebar $>200-250\text{ bps}$, ECB terpaksa menghentikan pengetatan untuk mencegah krisis utang zona euro.
3. **Bank of England (BoE - GBP)**:
   - **Mandat Inflasi**: Target CPI 2.0%.
   - **Neutral Rate ($r^*$)**: $3.25\% - 3.50\%$.
   - **Lantai Hawkish**: Inflasi jasa (*Services CPI*) $>5.0\%$ dan upah sektor swasta (*Private Regular Pay*) adalah jangkar penentu suku bunga BoE. Amati pemisahan suara (hawkish/neutral/dovish) dalam MPC.
4. **Bank of Japan (BoJ - JPY)**:
   - **Mandat Spiral Upah Positif**: Target CPI 2.0% yang didukung negosiasi upah musim semi (*Shunto* $\ge 5.0\%$ total / $\ge 3.5\%$ base pay).
   - **Neutral Rate ($r^*$)**: $0.75\% - 1.00\%$.
   - **Zona Intervensi Kementerian Keuangan (MoF)**: Waspadai intervensi fisik saat USD/JPY menyentuh $155.00 - 160.00+$ atau depresiasi JPY melebihi $4\%$ dalam 2 minggu.
5. **Reserve Bank of Australia (RBA - AUD)**:
   - **Target Rentang**: Trimmed Mean CPI $2.0\% - 3.0\%$.
   - **Neutral Rate ($r^*$)**: $3.50\% - 3.75\%$.
   - **Transmisi Eksternal**: Ketergantungan tinggi pada pertumbuhan kredit China dan harga ekspor bijih besi (*Iron Ore*).

---

## 2. Invarian Aljabar Pasangan FX (Algebraic Sign Invariant)

Dalam trading valuta asing, bias suatu pasangan mata uang adalah selisih aljabar dari bias masing-masing mata uang konstituennya:
$$\text{Bias}(\text{BASE/QUOTE}) = \text{Bias}(\text{BASE}) - \text{Bias}(\text{QUOTE})$$

- Skor Makro Mata Uang dihitung dalam skala $-10$ (Sangat Dovish) hingga $+10$ (Sangat Hawkish).
- Contoh:
  - Bias USD = $+6.5$ (Hawkish)
  - Bias EUR = $+1.5$ (Netral/Dovish)
  - Bias EUR/USD = $+1.5 - (+6.5) = -5.0$ (**Kuat Bearish EUR/USD**)

Jalankan kalkulasi deterministik melalui CLI:
```bash
python scripts/cb_differential_calc.py --base-currency EUR --quote-currency USD --base-rate 3.25 --quote-rate 4.75 --base-r-star 2.125 --quote-r-star 2.875 --base-inflation 2.4 --quote-inflation 2.8
```

---

## 3. 7 Saluran Non-Rate Override

Jika terdapat salah satu dari 7 kondisi berikut, arah suku bunga murni dapat dikesampingkan (*overridden*):
1. **Geopolitik & Perang**: Pelarian ke USD, Gold, atau CHF mengabaikan diferensial imbal hasil.
2. **Krisis Perbankan / Likuiditas**: Peningkatan fasilitas diskonto Fed (BTFP/SRF) memicu penguatan likuiditas defensif.
3. **Fiscal Dominance**: Defisit fiskal AS yang masif menyebabkan penerbitan obligasi berlebih (*bear steepening*).
4. **Terms of Trade & Komoditas**: Lonjakan minyak mentah memperkuat CAD dan melemahkan JPY/EUR.
5. **Twin Deficits**: Pelemahan struktural mata uang dengan defisit ganda di saat resesi.
6. **Intervensi Mata Uang Fisik**: Pembelian langsung JPY oleh BoJ/MoF atau CNH oleh PBoC.
7. **Safe-Haven Flow Reversals**: Aksi unwind posisi *carry trade* saat volatilitas global melonjak.
