# Reference 04: Dialectical Debate & Bayesian Judge Playbook

Dokumen ini menjelaskan tata cara pelaksanaan debat multi-agen adversarial 2 ronde antara *Bull Advocate* dan *Bear Dissenter*, aturan atenuasi sanggahan, serta mekanisme arbitrase *Chief Investment Judge*.

---

## 1. Konstitusi Debat Adversarial Universal

1. **Larangan Kompromi ("Both sides have merit")**:
   - Analis Bull wajib berfokus penuh mencari celah keuntungan pembeli dan mengekspos risiko penjual.
   - Analis Bear wajib bertindak sebagai *Red-Team Skeptic*, mencari setiap alasan mengapa perdagangan akan gagal (stop run, likuiditas palsu, divergensi makro).
2. **Kewajiban Sitasi Angka Minimal 2 Data**:
   - Setiap argumen wajib menyertakan minimal 2 angka eksak dari telemetri (contoh: "Harga menyentuh 1.0820 di mana terdapat 1.25x ATR noise floor dan COT net positioning di persentil ke-88").
3. **Jangkar Penilaian Eksplisit (1 - 10)**:
   - `1 - 3`: Spekulatif / Lemah / Tidak didukung bukti struktural.
   - `4 - 6`: Menengah / Memiliki sinyal teknikal tetapi ada konflik makro.
   - `7 - 8`: Kuat / Aliran dana institusional terkonfirmasi multi-domain.
   - `9 - 10`: Sangat Kuat / Selaras sempurna secara teknikal, makro, dan likuiditas.

---

## 2. Struktur Debat 2-Ronde

### Ronde 1: Pengajuan Kasus Utama
- **Bull Advocate**:
  - Menyusun hipotesis pembelian konkret (`LONG_OPTION_A`).
  - Menjelaskan zona demand, diskon harga, dan katalis kenaikan.
  - Memberikan skor kekuatan kasus Bull (1 - 10).
- **Bear Dissenter**:
  - Menyusun hipotesis penjualan konkret (`SHORT_OPTION_B`) atau tesis pembatalan (*veto thesis*).
  - Mengidentifikasi titik rentan stop loss pembeli dan potensi sapuan likuiditas.
  - Memberikan rekomendasi: `PROCEED`, `REDUCE_SIZE`, atau `ABORT`, serta skor keparahan risiko (1 - 10).

### Ronde 2: Dialectical Rebuttal (Sanggahan & Pertahanan)
- Masing-masing analis menanggapi poin-poin terkuat yang diajukan lawan.
- **Aturan Atenuasi Mekanis (-3 Poin)**:
  - Jika Bull Advocate berhasil mematahkan kekhawatiran utama Bear Dissenter dengan bukti struktural valid (skor kualitas sanggahan $\ge 7$), maka skor ancaman Bear **otomatis dipotong 3 poin** (dengan lantai minimum 1.0).
  - Begitu pula sebaliknya, jika sanggahan Bear dinilai $\ge 7$, skor kekuatan Bull dipotong 3 poin.

---

## 3. Arbitrase Bayesian Chief Investment Judge

Chief Judge mengambil alih pengambilan keputusan setelah Ronde 2 selesai:

1. **Matriks Bobot Berdasarkan Rezim Pasar**:
   - `trending`: Bobot Teknikal 50%, Makro 35%, Sentimen 15%.
   - `ranging`: Bobot Teknikal 40%, Makro 30%, Sentimen 30%.
   - `volatile`: Bobot Teknikal 35%, Makro 45%, Sentimen 20%.
   - `crisis`: Bobot Teknikal 25%, Makro 55%, Sentimen 20%.
2. **Kalibrasi Skor Brier**:
   - Setiap analis dinilai berdasarkan akurasi historis (skor Brier $B_i$, di mana nilai lebih kecil berarti lebih akurat).
   - Bobot keagenan dihitung: $w_i = (1 / B_i) / \sum (1 / B_j)$ dengan rentang batas aman $[0.15, 0.65]$.
3. **Mandat Anti-Fence-Sitting**:
   - Jika setup memenuhi $\ge 3$ dari 5 kriteria peluang aktif dan selisih skor Bull vs Bear $\ge 1.5$ poin, Hakim **DILARANG** memilih `HOLD` hanya karena keraguan abstrak.
   - Hakim wajib memilih arah pemenang dan mengalibrasikan risiko melalui *Bayesian Risk Multiplier*:
     - Skor Pemenang $\ge 8.0 \rightarrow$ **1.00x** (Full Allocation)
     - Skor Pemenang $\ge 6.5 \rightarrow$ **0.75x** (Three-Quarter Allocation)
     - Skor Pemenang $\ge 5.0 \rightarrow$ **0.50x** (Half Allocation)
     - Skor Pemenang $< 5.0 \rightarrow$ **0.25x** (Quarter Probe Allocation)
