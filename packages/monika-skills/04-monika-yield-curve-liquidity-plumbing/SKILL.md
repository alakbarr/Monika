---
name: monika-yield-curve-liquidity-plumbing
description: Quantitative analysis of US sovereign yield curve dynamics (2s10s, 10Y TIPS real yields, breakeven inflation), Federal Reserve systemic liquidity plumbing (WALCL - TGA - RRP), Treasury QRA debt issuance mix, and HY OAS credit spreads.
version: 1.0.0
tags: [trading, macro, yield-curve, liquidity, fed-plumbing, credit-spreads, vix]
---

# Monika Yield Curve & Systemic Liquidity Plumbing Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Analisis Kurva Imbal Hasil 4-Kuadran

Dekomposisi imbal hasil obligasi nominal 10-tahun:
$$\text{Nominal 10Y} = \text{10Y TIPS Real Yield} + \text{10Y Breakeven Inflation}$$

1. **Bull Steepener (2Y Yield Turun > 10Y Yield Turun)**:
   - Pasar memperhitungkan pemotongan suku bunga Fed yang cepat akibat perlambatan ekonomi.
   - **Implikasi**: USD Melemah, Gold Sangat Bullish, Saham Defensif mengungguli siklikal.
2. **Bear Steepener (10Y Yield Naik > 2Y Yield Naik)**:
   - Didorong oleh lonjakan pasokan utang Treasury AS (*term premium*) atau kekhawatiran defisit fiskal jangka panjang.
   - **Implikasi**: USD Menguat, Tekanan pada Valuasi Saham & Gold (kecuali narasi *fiscal debasement* mendominasi).
3. **Bull Flattener (10Y Yield Turun > 2Y Yield Turun)**:
   - Aliran pelarian ke aset aman (*flight-to-safety*) akibat guncangan geopolitik atau pelemahan pertumbuhan global.
   - **Implikasi**: Penguatan mata uang safe haven (CHF, JPY), Gold Bullish.
4. **Bear Flattener (2Y Yield Naik > 10Y Yield Naik)**:
   - Sinyal pengetatan moneter hawkish atau kejutan inflasi persisten jangka pendek.
   - **Implikasi**: USD Sangat Kuat, Tekanan Berat pada Gold, Saham Berisiko, dan Kripto.

---

## 2. Pipa Likuiditas Sistemik Perbankan AS

Formula likuiditas bersih perbankan AS:
$$\text{Net Liquidity} = \text{WALCL (Fed Balance Sheet)} - \text{TGA (Treasury Account)} - \text{ON RRP (Reverse Repo)}$$

- **Dampak Saldo TGA**:
  - TGA Naik $\rightarrow$ Kas diserap dari cadangan perbankan ke rekening Treasury $\rightarrow$ **Likuiditas Menyusut**.
  - TGA Turun $\rightarrow$ Kas pemerintah dibelanjakan kembali ke ekonomi $\rightarrow$ **Likuiditas Bertambah**.
- **Dampak Saldo RRP**:
  - Saldo RRP dialihkan ke pembelian Surat Utang Jangka Pendek (T-Bills) $\rightarrow$ Cadangan bank tetap terlindungi.
- **Treasury Quarterly Refunding Announcement (QRA)**:
  - Proporsi penerbitan tinggi pada **T-Bills** ($< 1$ tahun) $\rightarrow$ Netral/Positif untuk likuiditas.
  - Proporsi penerbitan tinggi pada **Kupon Obligasi 10Y/30Y** $\rightarrow$ Menyedot likuiditas institusional & memicu *Bear Steepening*.

Jalankan kalkulasi melalui CLI:
```bash
python scripts/macro_liquidity_calc.py --walcl 7100 --tga 780 --rrp 250 --prev-net-liq 6000 --us10y 4.40 --us2y 4.20 --tips10y 2.05 --vix 17.5 --hy-oas 335
```

---

## 3. Gerbang Risiko VIX & Spread Kredit (HY OAS)

- **Matriks 5-Rezim VIX**:
  - `Risk-On` ($<15.0$): Multiplier **1.00x**
  - `Carry/Range` ($15.0 - 20.0$): Multiplier **1.00x**
  - `Caution` ($20.0 - 25.0$): Multiplier **0.75x**
  - `Stress` ($25.0 - 30.0$): Multiplier **0.50x**
  - `Crisis` ($>30.0$): Multiplier **0.25x** (atau penolakan total pada aset berisiko tinggi)
- **High-Yield Option-Adjusted Spread (HY OAS)**:
  - $< 350\text{ bps}$: Lingkungan kredit sehat dan likuid.
  - $> 450\text{ bps}$: **HARD VETO**. Terdapat tekanan gagal bayar obligasi korporasi; dilarang membuka posisi `BUY` pada BTC, Indeks Saham, dan pasangan *Carry Trade*.
