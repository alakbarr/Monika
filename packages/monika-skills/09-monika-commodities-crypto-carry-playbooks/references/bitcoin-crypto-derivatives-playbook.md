# Reference: Bitcoin & Crypto Derivatives Playbook

Dokumen ini menjelaskan metrik derivatif pasar kripto, suku bunga pendanaan (funding rate), dan arus masuk ETF Spot.

---

## 1. Arus Dana Bersih ETF Spot AS (Spot ETF Net Flows)

- Data dilaporkan setiap penutupan pasar New York (sekitar 01:00 - 04:00 UTC).
- **Arus Masuk Masif ($>+\$200\text{M}$)**: Memperkuat struktur support harga spot.
- **Arus Keluar Masif ($<-\$150\text{M}$)**: Tanda likuidasi modal institusional.

---

## 2. Perpetual Funding Rate & Open Interest Liquidation

- **Tingkat Pendanaan Normal**: $+0.005\%$ hingga $+0.015\%$ per 8 jam.
- **Squeeze Warning**:
  - Funding Rate $\ge +0.05\%$: Biaya pemegang posisi long sangat mahal. Sedikit penurunan harga spot akan memicu likuidasi beruntun (*long liquidation cascade*).
  - Funding Rate $\le -0.02\%$: Spekulan menumpuk posisi short. Sangat rentan terhadap *short squeeze* agresif ke atas level likuiditas tertinggi 24 jam.
