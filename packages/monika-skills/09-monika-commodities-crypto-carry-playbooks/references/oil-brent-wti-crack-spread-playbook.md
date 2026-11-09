# Reference: Crude Oil (WTI & Brent) & Refinery Crack Spread Playbook

Dokumen ini memuat parameter kuantitatif arbitrase statistik spread Brent-WTI dan marjin kilang 3:2:1.

---

## 1. Model Arbitrase Statistik Brent-WTI

$$\text{Spread} = P_{\text{Brent}} - P_{\text{WTI}}$$

- **Baseline Historis**: Mean $\mu = \$4.50$, Standard Deviation $\sigma = \$0.85$.
- **Aturan Eksekusi Arbitrase**:
  - $Z = \frac{\text{Spread} - 4.50}{0.85}$
  - Jika $Z \ge +2.0\sigma$ (Spread $\ge \$6.20$): Spread terlalu lebar $\rightarrow$ Buka posisi **Short Brent / Long WTI**.
  - Jika $Z \le -2.0\sigma$ (Spread $\le \$2.80$): Spread terlalu sempit $\rightarrow$ Buka posisi **Long Brent / Short WTI**.
  - Target exit: Saat spread kembali ke mean historis ($Z = 0.0$).

---

## 2. Margin Kilang 3:2:1 (Refinery Crack Spread)

$$\text{Crack Spread} (\$/\text{bbl}) = \frac{2 \times P_{\text{Gasoline}}(\$/\text{gal}) \times 42 + 1 \times P_{\text{Distillate}}(\$/\text{gal}) \times 42 - 3 \times P_{\text{Crude}}(\$/\text{bbl})}{3}$$

- Crack Spread $> \$25/\text{bbl}$: Margin kilang sangat kuat $\rightarrow$ Kilang akan meningkatkan throughput dan membeli lebih banyak minyak mentah (*Bullish Crude*).
- Crack Spread $< \$15/\text{bbl}$: Margin kilang tertekan $\rightarrow$ Penurunan permintaan minyak mentah (*Bearish Crude*).
