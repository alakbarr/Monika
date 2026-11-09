# Reference 03: SMC/ICT, Dealing Range & Synergy Matrix

Dokumen ini menjelaskan integrasi konsep Smart Money Concepts (SMC/ICT), dekomposisi posisi spasial *Dealing Range* 20-bar, dewan 3 spesialis, dan matriks 5 status sinergi institusional.

---

## 1. Posisi Spasial Dealing Range ($pos$)

Posisi harga relatif diukur terhadap rentang tertinggi dan terendah 20-bar (H4 atau D1):
$$pos = \frac{\text{Close} - \text{Low}_{20}}{\text{High}_{20} - \text{Low}_{20}}$$

```
1.00 ─── [High 20-bar / Extreme Premium] ──────────────────────────
0.85 ─── [Anti-Chasing Buy Ceiling] -> Dilarang BUY di atas level ini!
         PREMIUM ZONE (0.65 - 1.00): Hanya valid untuk SELL
0.65 ─── [Batas Bawah Premium] ────────────────────────────────────
0.60 ─── [Batas Atas Equilibrium Chop]
         EQUILIBRIUM CHOP ZONE (0.40 - 0.60): WAJIB HOLD (Kecuali Impuls Kuat)
0.40 ─── [Batas Bawah Equilibrium Chop] ───────────────────────────
0.35 ─── [Batas Atas Discount]
         DISCOUNT ZONE (0.00 - 0.35): Hanya valid untuk BUY
0.15 ─── [Anti-Chasing Sell Floor] -> Dilarang SELL di bawah level ini!
0.00 ─── [Low 20-bar / Extreme Discount] ─────────────────────────
```

### Aturan Eksekusi Berbasis Zona:
1. **Discount Zone ($pos \le 0.35$ atau $\le 0.40$ dekat PDL/PWL)**:
   - Valid untuk mencari konfirmasi `BUY`. Order `SELL` ditolak kecuali terjadi *Confirmed Structural Breakdown*.
2. **Premium Zone ($pos \ge 0.65$ atau $\ge 0.60$ dekat PDH/PWH)**:
   - Valid untuk mencari konfirmasi `SELL`. Order `BUY` ditolak kecuali terjadi *Confirmed Structural Breakout*.
3. **Equilibrium Chop Zone ($0.40 \le pos \le 0.60$)**:
   - Pasar berada di area fair value tanpa diskon atau premi. **Wajib HOLD** kecuali terdapat impuls kuantitatif terkonfirmasi ($\text{ADX} \ge 25$, EMA/MACD searah).
4. **Anti-Chasing Hard Gate**:
   - Dilarang membuka posisi `BUY` jika $pos > 0.85$ (risiko beli di pucuk).
   - Dilarang membuka posisi `SELL` jika $pos < 0.15$ (risiko jual di dasar).

---

## 2. Protokol Dual-Engine SMC/ICT

1. **Engine 1: Standard Trend & Breakout Retest**:
   - Mengikuti tren dominan time frame tinggi (D1/H4).
   - Masuk pada mitigasi Order Block (OB) atau Fair Value Gap (FVG) yang belum terisi di area Discount (untuk Buy) atau Premium (untuk Sell).
   - Displacement wajib memiliki rasio candle body $> 70\%$ dan rentang pergerakan $> 1.5\times\text{ATR}$.
2. **Engine 2: Contra-Macro Turtle Soup Sweep + MSS**:
   - Diterapkan saat bias makro jangka menengah sudah jenuh (*Priced-In Score $\ge 8.0$* atau posisi COT di persentil ekstrem).
   - Menunggu harga menyapu likuiditas batas atas (PDH/PWH) atau batas bawah (PDL/PWL) dengan ekor candle panjang (*wick sweep*).
   - Konfirmasi Market Structure Shift (MSS) pada M15 atau H1 sebelum mengeksekusi perdagangan pembalikan arah.

---

## 3. Triangulasi 3 Spesialis & 5 Status Sinergi Institusional

Dewan spesialis dipecah menjadi 3 peran independen:
- **Technical Analyst (45%)**: Murni membaca price action, struktur pasar, dan indikator teknikal.
- **Macro Analyst (35%)**: Murni membaca suku bunga, inflasi, imbal hasil obligasi, dan berita fundamental.
- **Sentiment Analyst (20%)**: Murni membaca posisi CFTC COT dan partisipasi ritel dengan prinsip kontrarian.

Skor Komposit Terbobot:
$$\text{Score} = \sum (w_i \times d_i \times c_i)$$
di mana $d_i \in \{+1, -1, 0\}$, $w_{\text{tech}}=0.45$, $w_{\text{macro}}=0.35$, $w_{\text{sent}}=0.20$.

### 5 Status Sinergi Institusional:
1. `uncrowded_institutional_synergy`:
   - Kondisi: Teknikal searah Makro, Sentimen belum jenuh.
   - **Edge Historis: 81.8% akurasi**. Pengganda ukuran: **1.10x**.
2. `institutional_contrarian_synergy`:
   - Kondisi: Teknikal searah Makro, Posisi ritel melawan arah institusional.
   - **Edge Historis: Jebakan ritel terkonfirmasi**. Pengganda ukuran: **1.08x**.
3. `crowded_unanimous_exhaustion`:
   - Kondisi: Teknikal, Makro, dan Sentimen semuanya searah di level ekstrem (COT $>85\%$ atau $<15\%$).
   - **Risiko: 72.7% - 80% jebakan pembalikan**. Pengganda ukuran: **0.82x** atau paksa `HOLD`.
4. `crowded_tech_sent_trap_vs_macro`:
   - Kondisi: Teknikal dan Sentimen melawan arah fundamental makro.
   - **Risiko: 71.4% jebakan manipulasi teknikal**. Pengganda ukuran: **0.85x**.
5. `technical_macro_conflict`:
   - Kondisi: Teknikal berlawanan dengan Makro.
   - **Tindakan**: Penalti ukuran **0.88x** atau tunggu resolusi struktural.
