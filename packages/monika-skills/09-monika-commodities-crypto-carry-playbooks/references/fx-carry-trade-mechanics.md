# Reference: FX Carry Trade Mechanics & Unwind Protocol

Dokumen ini menjelaskan perhitungan rasio Carry-to-Risk dan tangga darurat penutupan posisi saat terjadi lonjakan volatilitas.

---

## 1. Rasio Carry-to-Risk ($\text{CR}$)

$$\text{CR} = \frac{R_{\text{target}} - R_{\text{funding}}}{\sigma_{\text{implied}}}$$

- $R_{\text{target}}$: Suku bunga acuan mata uang yang dibeli (contoh: USD, GBP, AUD, MXN).
- $R_{\text{funding}}$: Suku bunga acuan mata uang pendana (contoh: JPY, CHF).
- $\sigma_{\text{implied}}$: Implied Volatility opsi 1-bulan.
- **Standar Institusional**:
  - $\text{CR} \ge 0.50$: Setup Carry prima.
  - $\text{CR} < 0.25$: Setup tidak layak diperdagangkan (*negative asymmetry*).

---

## 2. Tangga Darurat Penutupan Posisi (Carry Unwind Protocol)

| Level VIX | Status Portofolio Carry | Tindakan Manajemen Risiko |
|---|---|---|
| $\text{VIX} \le 20.0$ | Lingkungan Stabil | Pertahankan posisi carry normal (100% ukuran) |
| $20.0 < \text{VIX} \le 25.0$ | Peringatan Volatilitas | Pangkas eksposur carry trade sebesar 50% |
| $25.0 < \text{VIX} \le 30.0$ | Stres Likuiditas Global | Tutup seluruh posisi carry long |
| $\text{VIX} > 30.0$ | Krisis / Panic Unwind | **Balik arah menjadi Long JPY atau Long CHF** |
