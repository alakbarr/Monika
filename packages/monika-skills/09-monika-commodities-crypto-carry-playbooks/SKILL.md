---
name: monika-commodities-crypto-carry-playbooks
description: Institutional trading playbooks for non-FX major asset classes and quantitative strategies: Gold (XAUUSD Real Yields/SGE), Crude Oil (WTI/Brent Stat-Arb & 3:2:1 Crack Spread), Bitcoin (Spot ETF flows & funding squeeze), and FX Carry Trade (Carry-to-Risk CR & Unwind Ladder).
version: 1.0.0
tags: [trading, commodities, gold, crude-oil, crypto, bitcoin, carry-trade, stat-arb]
---

# Monika Commodities, Crypto & Carry Playbooks Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Playbook Emas Institusional (`XAUUSD`)

1. **Matriks TIPS 10Y Real Yield vs. DXY**:
   - Dalam kondisi normal, Emas berkorelasi negatif kuat terhadap US 10-Year TIPS Real Yield.
2. **Rezim Non-Linearitas & Debasemen Fiskal**:
   - Jika $\text{TIPS Real Yield} > 2.00\%$ namun Emas tetap reli bersamaan dengan DXY $\rightarrow$ Pasar berada dalam **Rezim Stres Utang Fiskal Kedaulatan**. Pembelian bank sentral (PBoC, negara EM) mengalahkan transmisi suku bunga riil.
3. **Premi Fisik Shanghai Gold Exchange (SGE)**:
   - Pantau spread harga fisik Shanghai vs. Spot London. Premi $>+\$30/\text{oz}$ menandakan arus impor emas fisik masif dari Barat ke Timur.
4. **Jendela Likuiditas London Fix**:
   - London AM Fix (10:30 London) dan London PM Fix (15:00 London). Waspadai sapuan likuiditas tajam pada 15 menit sebelum dan sesudah penetapan harga fix ini.

---

## 2. Playbook Minyak Mentah (`XTIUSD` & `XBRUSD`)

1. **Arbitrase Statistik Spread Brent–WTI**:
   $$\text{Spread} = \text{Brent} - \text{WTI}$$
   $$Z\text{-Score} = \frac{\text{Spread} - \mu_{\text{historical}}}{\sigma_{\text{historical}}}$$
   - Secara historis, Brent diperdagangkan dengan premi rata-rata $\approx \$4.00 - \$5.00$ di atas WTI.
   - Jika $|Z| \ge 2.0\sigma$: Peluang *statistical arbitrage* (ekspektasi *mean reversion*).
2. **Refinery 3:2:1 Crack Spread**:
   $$\text{Crack Spread} = \frac{2 \times \text{Gasoline} \times 42 + 1 \times \text{Distillate} \times 42 - 3 \times \text{Crude}}{3}$$
   - Mengukur margin keuntungan kilang minyak mentah. Crack spread yang anjlok di bawah $\$15/\text{bbl}$ menandakan permintaan konsumen melemah dan kilang akan memangkas pembelian minyak mentah.
3. **Kejutan Inventori Mingguan EIA (Rabu 15:30 UTC)**:
   - Hitung *Net Total Inventory Surprise* (Crude + Cushing Hub + Gasoline + Distillates).

---

## 3. Playbook Kripto & Bitcoin (`BTCUSD`)

1. **Arus Bersih Harian Spot ETF AS (`IBIT`, `FBTC`)**:
   - Arus masuk bersih $>+\$200\text{M}$ mencerminkan akumulasi institusional terstruktur.
   - Arus keluar berturut-turut $>3$ hari mengindikasikan rotasi modal keluar dari aset berisiko.
2. **Perpetual Funding Rate & Open Interest**:
   - Funding Rate 8-jam $\ge +0.05\%$: Posisi long over-leveraged $\rightarrow$ Risiko tinggi *long squeeze flush*.
   - Funding Rate 8-jam $\le -0.02\%$: Posisi short menumpuk $\rightarrow$ Risiko *short squeeze rally*.
3. **CME Futures Basis & Weekend Gaps**:
   - Pantau selisih harga penutupan CME Bitcoin Futures hari Jumat dengan harga Spot hari Minggu malam (23:00 UTC). Gap harga cenderung terisi (*filled*) dalam 48 jam pertama perdagangan.

---

## 4. Playbook FX Carry Trade

1. **Rasio Carry-to-Risk ($\text{CR}$)**:
   $$\text{CR} = \frac{\text{Long Currency Rate} - \text{Short Currency Rate}}{\text{Implied Volatility (1M)}}$$
   - $\text{CR} \ge 0.50$: Setup Carry sangat atraktif (hasil bunga melebihi risiko volatilitas).
   - $\text{CR} < 0.25$: Setup Carry tidak sepadan dengan risiko.
2. **Tangga Darurat Unwind Carry (VIX-Driven Exit Ladder)**:
   - **VIX $> 22.0$**: Pangkas ukuran posisi carry trade sebesar **50%**.
   - **VIX $> 28.0$**: **EMERGENCY EXIT**. Tutup seluruh posisi beli carry; putar arah menjadi beli mata uang safe haven pendana (*Long JPY/CHF*).

Jalankan evaluasi CLI:
```bash
python scripts/asset_special_calc.py --asset OIL --brent-price 76.50 --wti-price 71.80 --gasoline-price 2.15 --distillate-price 2.45 --crude-price 71.80
```
