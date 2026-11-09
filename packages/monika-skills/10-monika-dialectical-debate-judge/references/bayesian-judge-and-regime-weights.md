# Reference: Chief Investment Judge Bayesian Arbitration & Regime Weight Matrix

Dokumen ini menjelaskan pembobotan rezim pasar, kalibrasi skor Brier, dan mandat anti-fence-sitting.

---

## 1. Matriks Bobot Domain Berdasarkan Rezim Pasar

| Rezim Pasar | Bobot Teknikal | Bobot Makro | Bobot Sentimen | Karakteristik Keputusan |
|---|---|---|---|---|
| **Trending** | 50% | 35% | 15% | Momentum teknikal dan kelanjutan tren mendominasi |
| **Ranging** | 40% | 30% | 30% | Ekstrem sentimen dan batas range teknikal menjadi kunci |
| **Volatile** | 35% | 45% | 20% | Katalis makro mendikte arah di tengah noise volatilitas |
| **Crisis** | 25% | 55% | 20% | Fundamental likuiditas & pelarian modal mengesampingkan teknikal |

---

## 2. Kalibrasi Skor Brier Agen

Setiap analis memiliki riwayat ketepatan prediksi yang diukur melalui Brier Score ($B_i \in [0.0, 1.0]$):
$$w_i = \frac{1 / B_i}{\sum_{j} (1 / B_j)}$$
Bobot akhir dibatasi pada rentang $[0.15, 0.65]$ untuk mencegah dominasi mutlak satu agen.

---

## 3. Mandat Anti-Fence-Sitting

Trader institusional dibayar untuk mengambil risiko terukur saat keunggulan probabilitas (*edge*) hadir:
- Jika $\text{Active Criteria Met} \ge 3$ dari 5 dan $|\text{Bull Score} - \text{Bear Score}| \ge 1.5$:
  - Hakim **DILARANG KERAS** memutuskan `HOLD`.
  - Hakim wajib memenangkan pihak dengan skor tertinggi dan mengalokasikan ukuran posisi yang terkalibrasi secara Bayesian:
    - $\ge 8.0 \rightarrow$ **1.00x**
    - $6.5 - 7.9 \rightarrow$ **0.75x**
    - $5.0 - 6.4 \rightarrow$ **0.50x**
    - $< 5.0 \rightarrow$ **0.25x**
