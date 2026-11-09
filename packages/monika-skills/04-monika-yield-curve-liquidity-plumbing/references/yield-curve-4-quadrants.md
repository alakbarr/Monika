# Reference: US Sovereign Yield Curve 4-Quadrant Regimes

Dokumen ini memuat pohon keputusan analitis untuk kurva imbal hasil obligasi pemerintah AS (2s10s) dan dekomposisi ekspektasi inflasi.

---

## 1. Pohon Keputusan 4-Kuadran Kurva Imbal Hasil

```
                     Perubahan Kemiringan Kurva (Slope 2s10s)
                                       │
            ┌──────────────────────────┴──────────────────────────┐
      Slope Curam (Steepening)                              Slope Landai/Inversi (Flattening)
            │                                                     │
      ┌─────┴─────┐                                         ┌─────┴─────┐
      │           │                                         │           │
Imbal Hasil  Imbal Hasil                               Imbal Hasil  Imbal Hasil
   Turun        Naik                                      Turun        Naik
      │           │                                         │           │
Bull Steepener Bear Steepener                         Bull Flattener Bear Flattener
(Fed Cuts/      (Fiscal Supply/                        (Safe-Haven/   (Hawkish Fed/
 Recession)     Term Premium)                          Slowdown)      Persistent Inf)
```

---

## 2. Dekomposisi Ekspektasi Inflasi Breakeven

$$\text{10Y Breakeven Inflation} = \text{US10Y Nominal Yield} - \text{10Y TIPS Real Yield}$$

- **Breakeven Naik + Nominal Naik**: Pasar memperhitungkan percepatan inflasi (*Reflationary Regime*). Komoditas dan aset riil (Minyak, Emas, Tembaga) diuntungkan.
- **Breakeven Turun + Nominal Naik**: Kenaikan imbal hasil murni didorong oleh lonjakan *Real Yield* $\rightarrow$ Pengetatan kondisi finansial riil. Sangat menekan harga Emas dan Kripto.
- **Breakeven Turun + Nominal Turun**: Rezim deflasioner / perlambatan ekonomi tajam.
