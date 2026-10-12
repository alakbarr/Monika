---
name: economic-indicator-nowcasting-and-transmission
description: "Macroeconomic release nowcasting, indicator decomposition, and transmission."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [nowcasting, leading_indicators, pre_event_analysis, macro_transmission, non_linear_dynamics, real_yields, priced_in]
---

# Macro Economic Indicator Nowcasting & Transmission Playbook

Panduan institusional untuk menyajikan analisis prediktif sebelum rilis data ekonomi (PCE, CPI, NFP, GDP, PMI, dll.), membongkar bukti rantai indikator utama (leading indicators), mengidentifikasi potensi kegagalan prediksi (falsification vectors), dan mengurai transmisi non-linier lintas aset (mengapa data panas tidak selalu membuat USD menguat dan Emas/EUR jatuh).

Playbook ini bersifat **universal & agnostik**: berlaku untuk SEMBARANG rilis data ekonomi makro dan SEMBARANG instrumen trading.

---

## 1. PROTOKOL ALUR PIKIR & PENGUMPULAN DATA

Saat pengguna meminta analisis prediktif data makro pra-rilis (*pre-event predictive analysis*), AI Agent wajib menjalankan penelusuran terstruktur:
1. `get_economic_calendar`: Membaca konsensus pasar, angka periode sebelumnya, dan jadwal rilis rincian.
2. `get_macro_priced_in_score`: Memeriksa apakah ekspektasi sudah terdiskon secara berlebihan di pasar (skala 1–10).
3. `get_treasury_yields` & `get_bond_yield_spreads`: Membaca yield obligasi 2Y, 10Y, serta 10Y TIPS Real Yield (`DFII10`) dan 10Y Breakeven Inflation (`T10YIE`).
4. `get_cot_report` & `get_retail_sentiment`: Memeriksa posisi posisi spekulatif institusi dan sentimen ritel.
5. `get_dxy` & `get_smc_zones`: Memetakan level teknikal HTF pada aset target (e.g. XAUUSD, EURUSD).
6. `web_search`: Mengumpulkan estimasi model nowcasting bank sentral (Cleveland Fed Inflation Nowcasting, Atlanta Fed GDPNow, consensus whisper numbers).

---

## 2. STRUKTUR STANDAR OUTPUT WAJIB (4-PILAR INSTITUSIONAL)

Jawaban agen HARUS terstruktur dalam 4 pilar analisis ilmiah dan bebas dari linieritas naif:

### PILAR 1: Matriks Proyeksi Nowcasting vs Konsensus Pasar
Sajikan estimasi probabilitas arah rilis:

| Metrik Rilis Target | Konsensus Pasar | Angka Sebelumnya | Proyeksi Indikatif Sistem | Estimasi Arah Kejutan | Tingkat Keyakinan |
| :--- | :---: | :---: | :---: | :---: | :---: |
| *e.g. Core PCE Price Index (MoM)* | **0.3%** | 0.2% | **0.24% – 0.28%** | **Inline to Slight Miss** | Moderat (70%) |

*Pilihan Arah Kejutan*:
- **Hawkish Beat**: Rilis melebihi konsensus di atas ambang toleransi normal.
- **Inline**: Rilis berada di dalam rentang margin kesalahan konsensus ($\pm 0.05\%$).
- **Dovish Miss**: Rilis di bawah ekspektasi pasar secara signifikan.

---

### PILAR 2: Dekomposisi Indikator Utama (Evidence Chain / Rantai Bukti)
Jelaskan secara deduktif dari mana kesimpulan tersebut ditarik. Kelompokkan berdasarkan data proksi pembentuknya:

#### A. Jika Menganalisis Inflasi (PCE / CPI):
1. **Komponen PPI Terkait Langsung**: PPI Final Demand, terutama komponen jasa layanan kesehatan (*healthcare reimbursement*), tiket pesawat (*airfares*), dan manajemen portofolio yang langsung masuk ke formula PCE.
2. **Komponen CPI Terdahulu**: Sektor barang inti (*Core Goods*), harga kendaraan bekas Manheim, dan harga energi spot.
3. **Sub-Indeks ISM**: ISM Services Prices Paid dan ISM Manufacturing Prices Paid sebagai proksi tekanan biaya input korporasi.
4. **Perbedaan Metodologi PCE vs CPI**:
   - Bobot Shelter/Perumahan: CPI memiliki bobot shelter sangat besar (~34%), sedangkan PCE hanya ~15%.
   - Bobot Layanan Medis: PCE memberikan bobot jauh lebih tinggi untuk layanan medis yang disubsidi pemerintah (Medicare/Medicaid) yang ditarik dari PPI.

#### B. Jika Menganalisis Ketenagakerjaan (NFP / Payroll):
1. **ADP Private Employment**: Perubahan tenaga kerja sektor swasta.
2. **Initial Jobless Claims (4-Week Moving Average)**: Tren klaim pengangguran mingguan (klaim naik $\implies$ pasar kerja mendingin).
3. **Sub-Indeks ISM Employment**: Angka di bawah 50 menandakan kontraksi rekrutmen tenaga kerja.
4. **Challenger Job Cuts & JOLTS Quits Rate**: Tingkat pemutusan hubungan kerja dan rasio pengunduran diri sukarela.

#### C. Jika Menganalisis Pertumbuhan (GDP / Retail Sales):
1. **Nowcast Model Institusional**: Atlanta Fed GDPNow dan NY Fed Staff Nowcast.
2. **Retail Sales Control Group**: Penjualan ritel inti yang langsung masuk ke perhitungan pengeluaran konsumen riil GDP.
3. **Neraca Perdagangan & Inventori**: Kontribusi ekspor neto dan akumulasi stok barang dagang.

---

### PILAR 3: Vektor Falsifikasi & Risiko Kegagalan Prediksi (Why Could We Be Wrong?)
Sajikan secara jujur dan transparan faktor-faktor yang bisa membuat proyeksi meleset:
1. **Revisi Baseline Bulan Sebelumnya**: Kejutan rilis netto dihitung dari:
   $$\text{Net Surprise} = (\text{Aktual}_t - \text{Konsensus}_t) + (\text{Revisi}_{t-1} - \text{Angka Awal}_{t-1})$$
   Jika angka bulan ini mengalahkan konsensus $+0.1\%$, namun angka bulan lalu direvisi turun $-0.3\%$, reaksi pasar riil akan membaca data tersebut sebagai **negatif (dovish)**.
2. **Distorsi Penyesuaian Musiman (Seasonal Adjustment Quirks)**: Anomali kalender, cuaca ekstrem, atau libur musiman yang mendistorsi model smoothing statistik pemerintah.
3. **Tingkat Respons Survei (Response Rate)**: Penurunan partisipasi survei bulanan yang memicu volatilitas tinggi pada angka rilis awal (*flash estimate*).

---

### PILAR 4: Transmisi Makro Non-Linier Lintas Aset (Membongkar Mitos Linier)
Tegaskan bahwa pasar finansial **TIDAK PERNAH** bergerak secara mekanis linier naif ("data panas = USD naik, Gold/EUR turun"). Uraikan 4 mekanisme non-linier kritis:

#### 1. Efek "Priced-in" & Asimetri Reaksi (Sell-the-News Dynamic)
- Jika pasar sudah mendiskon skenario hawkish sebesar $\ge 80\%$ (skor Priced-In $\ge 8/10$), rilis data yang panas hanya menghasilkan lonjakan sesaat (*spike and fade*) karena pelaku pasar institusional memanfaatkannya untuk likuidasi profit (*take profit*).
- Sebaliknya, jika data sedikit saja meleset (*miss*), terjadi de-pricing masif yang memicu pembalikan arah tajam dan agresif ke arah sebaliknya.

#### 2. Mekanisme Imbal Hasil Riil (Real Yields) untuk Emas (XAUUSD)
Emas bereaksi terhadap **Imbal Hasil Riil (Real Yield)**, bukan imbal hasil nominal:
$$\Delta \text{Real Yield} \approx \Delta \text{Nominal Yield (10Y)} - \Delta \text{Breakeven Inflation (10Y)}$$
- **Mengapa Emas Bisa RALLY Saat Inflasi Panas?**:
  Jika rilis inflasi panas memicu lonjakan ekspektasi inflasi jangka panjang (+15 bps) lebih tinggi daripada kenaikan yield nominal obligasi (+8 bps), maka **Yield Riil justru TURUN (-7 bps)**. Turunnya yield riil menurunkan opportunity cost memegang emas, sehingga **Emas melesat NAIK meski inflasi tinggi!**

#### 3. Tekanan Mandat Ganda & Rezim Stagflasi (Growth vs Inflation Conflict)
- Jika inflasi tinggi terjadi di tengah data pertumbuhan atau ketenagakerjaan yang melambat, pasar mulai mencemaskan risiko stagflasi / resesi.
- Kenaikan suku bunga lebih lanjut dipandang akan merusak ekonomi, sehingga yield kurva mengalami *inversion*, memicu aliran modal *safe haven* ke Emas dan obligasi jangka panjang, serta melemahkan mata uang pro-siklikal seperti EUR.

#### 4. Dampak Sentimen Pasar Global (Risk-On vs Risk-Off)
- Perhatikan apakah USD saat ini bertindak sebagai *high-yielding carry currency* atau sebagai *safe-haven liquid asset*.
- Pada EURUSD: Jika data panas memicu aksi jual pada bursa saham global (S&P 500 drop), aliran penghindaran risiko dapat memperkuat USD. Namun jika pasar menyambut data sebagai konfirmasi resiliensi ekonomi ("soft landing"), sentimen *risk-on* dapat menopang EURUSD.
