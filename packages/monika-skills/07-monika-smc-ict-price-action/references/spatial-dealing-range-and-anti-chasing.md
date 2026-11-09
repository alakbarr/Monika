# Reference: Spatial Dealing Range Mechanics & Anti-Chasing Invariants

Dokumen ini menjelaskan dasar matematis perhitungan posisi harga dalam rentang dealing range 20-bar dan batas pelarangan mengejar harga (*anti-chasing*).

---

## 1. Rumus Normalisasi Dealing Range ($pos$)

$$\text{Dealing Range Position } pos = \frac{\text{Current Close} - \text{Low}_{20\text{-bar}}}{\text{High}_{20\text{-bar}} - \text{Low}_{20\text{-bar}}}$$

Nilai $pos$ selalu ternormalisasi dalam interval $[0.0, 1.0]$:
- $pos = 0.0$: Harga berada tepat di titik terendah 20 candle terakhir.
- $pos = 0.5$: Harga berada tepat di tengah rentang (*fair value equilibrium*).
- $pos = 1.0$: Harga berada tepat di titik tertinggi 20 candle terakhir.

---

## 2. Tabel Klasifikasi Zona Spasial

| Rentang $pos$ | Klasifikasi Zona | Sifat Eksekusi | Arah yang Diizinkan |
|---|---|---|---|
| $0.00 \le pos < 0.15$ | Extreme Discount (Anti-Chasing) | Jenuh Jual Ekstrem | BUY saja (**SELL DILARANG KERAS**) |
| $0.15 \le pos \le 0.35$ | Standard Discount Zone | Keunggulan Nilai Beli | BUY (Target Premium) |
| $0.35 < pos < 0.40$ | Transition Discount | Buffer | BUY jika dekat PDL/PWL |
| $0.40 \le pos \le 0.60$ | Equilibrium Chop Zone | Nilai Wajar / Tanpa Diskon | **MANDATORY HOLD** (Kecuali Impuls ADX $\ge 25$) |
| $0.60 < pos < 0.65$ | Transition Premium | Buffer | SELL jika dekat PDH/PWH |
| $0.65 \le pos \le 0.85$ | Standard Premium Zone | Keunggulan Nilai Jual | SELL (Target Discount) |
| $0.85 < pos \le 1.00$ | Extreme Premium (Anti-Chasing) | Jenuh Beli Ekstrem | SELL saja (**BUY DILARANG KERAS**) |
