# Reference 02: Macro, Central Banks & Liquidity Plumbing Playbook

Dokumen ini merangkum aturan analitis untuk fungsi reaksi bank sentral, struktur kurva imbal hasil obligasi, dan pipa likuiditas sistemik perbankan AS.

---

## 1. Fungsi Reaksi 5 Bank Sentral Utama

1. **Federal Reserve (Fed - USD)**:
   - **Mandat Ganda**: Stabilitas Harga (Core PCE 2.0%) dan Lapangan Kerja Maksimum (Sahm Rule $\ge 0.50\%$ mengindikasikan resesi).
   - **Suku Bunga Netral ($r^*$)**: Estimasi $2.75\% - 3.00\%$.
   - **Indikator Kunci**: Probabilitas pasar CME FedWatch, pidato Ketua Powell dan Gubernur Waller, inflasi Supercore (Core Services ex-Housing).
2. **European Central Bank (ECB - EUR)**:
   - **Mandat Tunggal Simetris**: Target inflasi HICP 2.0%.
   - **Suku Bunga Netral ($r^*$)**: Estimasi $2.00\% - 2.25\%$.
   - **Indikator Kunci**: Upah Ternegosiasi (*Negotiated Wages*), HICP Sektor Jasa, dan Spread Obligasi Italia-Jerman (BTP-Bund). Jika spread BTP-Bund $>200-250\text{ bps}$, aktifkan risiko fragmentasi kedaulatan (TPI).
3. **Bank of England (BoE - GBP)**:
   - **Mandat Inflasi**: Target CPI 2.0%.
   - **Suku Bunga Netral ($r^*$)**: Estimasi $3.25\% - 3.50\%$.
   - **Indikator Kunci**: Pertumbuhan Upah Reguler Sektor Swasta (*Private Regular Pay*) dan CPI Jasa (tingkat di atas $5.0\%$ adalah batas lantai hawkish). Perhatikan pemisahan suara 3 arah di MPC.
4. **Bank of Japan (BoJ - JPY)**:
   - **Mandat Stabilitas Harga Berkelanjutan**: Target CPI 2.0% didorong oleh spiral pertumbuhan upah positif.
   - **Suku Bunga Netral ($r^*$)**: Estimasi $0.75\% - 1.00\%$.
   - **Indikator Kunci**: Hasil negosiasi upah musim semi (*Shunto* $\ge 5.0\%$ total / $\ge 3.5\%$ base pay), Tokyo CPI sebagai indikator pendahulu 3 minggu, serta risiko intervensi Kementerian Keuangan Jepang (MoF) saat USD/JPY menyentuh $155.00 - 160.00$ atau mengalami depresiasi $>4\%$ dalam 2 minggu.
5. **Reserve Bank of Australia (RBA - AUD)**:
   - **Mandat Fleksibel**: Target inflasi 2.0% - 3.0% (Trimmed Mean CPI).
   - **Suku Bunga Netral ($r^*$)**: Estimasi $3.50\% - 3.75\%$.
   - **Indikator Kunci**: Impuls kredit China, harga ekspor bijih besi (*Iron Ore*), dan laporan tenaga kerja domestik.

### Invarian Aljabar Pasangan FX
Bias struktural suatu pasangan mata uang dihitung secara matematis:
$$\text{Bias}(\text{BASE/QUOTE}) = \text{Bias}(\text{BASE}) - \text{Bias}(\text{QUOTE})$$
Jika Bias EUR = +4 dan Bias USD = +7 $\rightarrow$ Bias EUR/USD = $4 - 7 = -3$ (**Bearish EUR/USD**).

---

## 2. Struktur Kurva Imbal Hasil 4-Kuadran (2s10s)

Dekomposisi imbal hasil nominal 10-tahun:
$$\text{Nominal 10Y} = \text{10Y TIPS Real Yield} + \text{10Y Breakeven Inflation}$$

| Kuadran Kurva | Pergerakan Yield | Konteks Makro | Implikasi Pasar |
|---|---|---|---|
| **Bull Steepener** | 2Y turun lebih cepat dari 10Y | Pemotongan suku bunga Fed agresif / ekspektasi resesi | USD Bearish, Gold Sangat Bullish, Saham Defensif |
| **Bear Steepener** | 10Y naik lebih cepat dari 2Y | Pasokan utang fiskal melimpah / term premium melonjak | USD Kuat, Gold Tertekan kecuali narasi debasemen fiskal |
| **Bull Flattener** | 10Y turun lebih cepat dari 2Y | Pelarian ke aset aman (*flight-to-safety*) / perlambatan pertumbuhan | Gold Bullish, JPY & CHF Kuat, Aset Berisiko Tertekan |
| **Bear Flattener** | 2Y naik lebih cepat dari 10Y | Pengetatan moneter hawkish / kejutan inflasi persisten | USD Sangat Bullish, Gold & Crypto Tertekan Hebat |

---

## 3. Pipa Likuiditas Sistemik AS & Spread Kredit

Formula likuiditas bersih perbankan AS:
$$\text{Net Liquidity} = \text{Fed Total Assets (WALCL)} - \text{Treasury General Account (TGA)} - \text{Overnight Reverse Repo (ON RRP)}$$

- **Ekspansi Likuiditas ($\Delta > +\$25B$)**: TGA berkurang (pemerintah AS membelanjakan uang) atau saldo RRP mengalir masuk ke cadangan bank $\rightarrow$ Sangat mendukung aset berisiko (BTC, Saham, Emas).
- **Kontraksi Likuiditas ($\Delta < -\$25B$)**: TGA naik (penarikan pajak atau penerbitan obligasi baru menyerap kas) dan Quantitative Tightening (QT) $\rightarrow$ Tekanan likuiditas pada pasar keuangan.
- **Spread Kredit High-Yield (HY OAS)**:
  - $< 350\text{ bps}$: Kondisi pasar kredit kondusif (*benign risk environment*).
  - $> 450\text{ bps}$: **HARD VETO**. Tekanan kredit perbankan/korporasi tinggi; dilarang membuka posisi beli pada aset berisiko.
