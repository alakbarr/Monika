# Reference: Orderbook Microstructure & Slippage Defense Protocols

Dokumen ini menjelaskan metrik Orderbook Imbalance ($OBI$) dan protokol pertahanan terhadap slippage eksekusi.

---

## 1. Perhitungan Orderbook Imbalance ($OBI$)

$$OBI = \frac{V_{\text{bid}} - V_{\text{ask}}}{V_{\text{bid}} + V_{\text{ask}}}$$

- **Nilai $OBI \in [-1.0, +1.0]$**:
  - $OBI > +0.30$: Likuiditas pembeli mendominasi antrean buku pesanan. Probabilitas penembusan ke atas tinggi.
  - $OBI < -0.30$: Likuiditas penjual mendominasi antrean buku pesanan. Probabilitas penembusan ke bawah tinggi.
  - $-0.30 \le OBI \le +0.30$: Buku pesanan seimbang.

---

## 2. Rasio Pelebaran Spread & Pertahanan Slippage

$$\text{Spread Ratio} = \frac{\text{Current Spread}}{\text{Typical Spread}}$$

1. **Kondisi Normal ($\text{Spread Ratio} \le 1.30\text{x}$)**:
   - Eksekusi market order atau limit order diizinkan secara penuh.
2. **Kondisi Waspada ($1.30\text{x} < \text{Spread Ratio} \le 2.00\text{x}$)**:
   - Dilarang mengeksekusi market order. Gunakan **Limit Order Only** untuk menghindari slippage negatif.
3. **Kondisi Ekstrem / Spike ($\text{Spread Ratio} > 2.00\text{x}$)**:
   - **EXECUTION REJECTED**. Likuiditas lokal mengering atau penyedia likuiditas sedang menarik kuotasi harga.
