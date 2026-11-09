---
name: monika-smc-ict-price-action
description: Institutional price action analysis using Smart Money Concepts (SMC/ICT), 3-Zone Spatial Dealing Range (pos), Anti-Chasing boundaries, Dual-Engine setup protocol, and the 20-Point Confluence Scorecard.
version: 1.0.0
tags: [trading, smc, ict, price-action, dealing-range, order-blocks, fair-value-gaps, confluence]
---

# Monika SMC/ICT Price Action & Dealing Range Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. 3-Zone Spatial Dealing Range ($pos$)

Posisi relatif harga dihitung terhadap rentang tertinggi dan terendah 20-bar:
$$pos = \frac{\text{Close} - \text{Low}_{20}}{\text{High}_{20} - \text{Low}_{20}}$$

```
1.00 ─── [20-Bar High / Extreme Premium] ──────────────────────────
0.85 ─── [Anti-Chasing Ceiling] -> BUY DILARANG di atas 0.85!
         PREMIUM ZONE (0.65 - 1.00): Hanya valid untuk SELL
0.65 ─── [Batas Bawah Premium] ────────────────────────────────────
0.60 ─── [Batas Atas Equilibrium Chop]
         EQUILIBRIUM CHOP ZONE (0.40 - 0.60): WAJIB HOLD (Tanpa Impuls Kuat)
0.40 ─── [Batas Bawah Equilibrium Chop] ───────────────────────────
0.35 ─── [Batas Atas Discount]
         DISCOUNT ZONE (0.00 - 0.35): Hanya valid untuk BUY
0.15 ─── [Anti-Chasing Floor] -> SELL DILARANG di bawah 0.15!
0.00 ─── [20-Bar Low / Extreme Discount] ─────────────────────────
```

### Aturan Eksekusi Berbasis Zona Spasial:
1. **Discount Zone ($pos \le 0.35$ atau $\le 0.40$ dekat PDL/PWL)**:
   - Hanya valid untuk mencari entri `BUY`. Order `SELL` dilarang kecuali terjadi *Confirmed Structural Breakdown*.
2. **Equilibrium Chop Zone ($0.40 \le pos \le 0.60$)**:
   - Area nilai wajar tanpa keunggulan matematis diskon/premi. **Wajib HOLD** kecuali terdapat impuls kuantitatif kuat ($\text{ADX} \ge 25$, EMA/MACD searah).
3. **Premium Zone ($pos \ge 0.65$ atau $\ge 0.60$ dekat PDH/PWH)**:
   - Hanya valid untuk mencari entri `SELL`. Order `BUY` dilarang kecuali terjadi *Confirmed Structural Breakout*.
4. **Anti-Chasing Hard Gate**:
   - **Blokir Beli**: Dilarang mengeksekusi `BUY` jika $pos > 0.85$.
   - **Blokir Jual**: Dilarang mengeksekusi `SELL` jika $pos < 0.15$.

---

## 2. Protokol Dual-Engine SMC/ICT

1. **Engine 1: Standard Trend & Breakout Retest**:
   - Beroperasi searah tren time frame tinggi (D1/H4).
   - Menunggu mitigasi pada Order Block (OB) atau Fair Value Gap (FVG) yang belum terisi di area Discount (untuk Buy) atau Premium (untuk Sell).
   - Membutuhkan candle displacement tegas ($\text{Body} > 70\%$ candle range dan rentang pergerakan $> 1.5\times\text{ATR}$).
2. **Engine 2: Contra-Macro Turtle Soup Sweep + MSS**:
   - Beroperasi saat pergerakan harga sebelumnya mengalami kejenuhan (*exhaustion*).
   - Menunggu harga menyapu likuiditas di atas PDH/PWH atau di bawah PDL/PWL dengan ekor candle panjang (*wick sweep*).
   - Konfirmasi penutupan candle M15/H1 kembali ke dalam range disertai Market Structure Shift (MSS) sebelum masuk berlawanan arah.

---

## 3. Kartu Skor Konfluensi 20-Poin (20-Point Scorecard)

Total skor dihitung dari **14 Poin Inti (Core Regimes)** + **6 Poin Bonus**:
- **Regime A (Trend-Following)**: D1 Trend (+3), H4 Structure (+3), H1 Alignment (+2), OB/FVG Location (+3), Dynamic S/R (+3).
- **Regime B (Range/Reversal)**: Key S/R Extreme (+3), Multi-Bar Rejection (+3), Oscillator Divergence (+2), Dealing Range Extreme (+3), Volume Exhaustion (+3).
- **6 Poin Bonus**:
  1. COT Positioning Alignment (+1)
  2. Killzone / Session Timing Alignment (+1)
  3. News Catalyst Freshness (+1)
  4. Intermarket Yield/DXY Confluence (+1)
  5. Multi-Month Key Level Interaction (+1)
  6. Volume Ratio $> 1.5\times$ Surge (+1)

### Ambang Batas Eksekusi:
- **Skor $\ge 13$ Poin**: `FULL_CONFLUENCE` $\rightarrow$ Alokasi Risiko Penuh (**1.00x**).
- **Skor $11 - 12$ Poin**: `STRONG_CONFLUENCE` $\rightarrow$ Alokasi Tiga Perempat (**0.75x**).
- **Skor $10$ Poin**: `MODERATE_CONFLUENCE` $\rightarrow$ Alokasi Setengah (**0.50x**).
- **Skor $< 10$ Poin**: `SUB_THRESHOLD` $\rightarrow$ **Ditolak Otomatis (0.00x)**.

Jalankan evaluasi CLI:
```bash
python scripts/smc_confluence_calc.py --close 1.0820 --high20 1.0950 --low20 1.0800 --atr14 0.0040 --confluence-score 12
```
