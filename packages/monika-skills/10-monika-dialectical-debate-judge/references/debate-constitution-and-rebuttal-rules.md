# Reference: Universal Debate Constitution & Rebuttal Attenuation Mechanics

Dokumen ini menjelaskan konstitusi debat multi-agen, aturan mitigasi sanggahan (-3 poin), dan format pertukaran argumen.

---

## 1. Konstitusi Debat Multi-Agen Monika

Setiap agen debat terikat pada 3 aturan absolut:
1. **Separation of Advocacy (Pemisahan Advokasi)**:
   - Bull Analyst dilarang mengakui argumen bearish tanpa mengajukan solusi mitigasi struktural.
   - Bear Dissenter dilarang menyetujui setup bullish tanpa mengekspos skenario terburuk (*worst-case scenario*).
2. **Kewajiban Sitasi Angka Minimal 2 Data**:
   - Dilarang membuat pernyataan kualitatif kosong (misal: "harga sudah terlalu tinggi"). Wajib diganti dengan: "harga berada pada posisi dealing range $pos = 0.88$, yang melanggar batas anti-chasing $0.85$".
3. **Standar Penilaian Objektif 1 - 10**:
   - Skor diberikan berdasarkan bukti empiris, bukan retorika bahasa.

---

## 2. Mekanisme Atenuasi Sanggahan Ronde 2

$$\text{Attenuated Score}_{\text{Opponent}} = \max\left(1.0, \text{Initial Score}_{\text{Opponent}} - 3.0 \times \mathbb{I}(\text{Rebuttal Quality} \ge 7.0)\right)$$

- Jika Bull Rebuttal Quality $\ge 7.0 \rightarrow$ Ancaman risiko Bear didiskon sebesar **-3.0 poin**.
- Jika Bear Rebuttal Quality $\ge 7.0 \rightarrow$ Kekuatan kasus Bull didiskon sebesar **-3.0 poin**.
- Diskon ini merefleksikan prinsip bahwa ancaman yang telah diantisipasi dengan level mitigasi terukur tidak lagi memiliki bobot destruktif penuh.
