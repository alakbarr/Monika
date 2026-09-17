# file: skills/trading/event_probability_playbook.md

# Event Probability Playbook — Central Bank Decisions & Macro Expectations

Playbook institusional untuk menganalisis probabilitas keputusan bank sentral (FOMC, ECB, BOE, BOJ), dekonstruksi ekspektasi pasar vs realita kebijakan, mitigasi risiko "sell-the-news", evaluasi asimetri penetapan harga aset, serta perumusan Trading Plan 3-Skenario terstruktur yang terintegrasi langsung dengan LangGraph Trading Engine Monika (`user_market_intel`).

---

## BAGIAN 1: PROTOKOL THINKING FLOW 5 TAHAP

Ketika menghadapi kueri atau peristiwa keputusan suku bunga dan event makro Tier-1, AI Agent WAJIB mengeksekusi 5 tahap penalaran berurutan:

```
[Tahap 1: Data Gathering & Multi-Source Grounding]
                       │
                       ▼
[Tahap 2: Priced-In Testing & Asymmetry Evaluation]
                       │
                       ▼
[Tahap 3: Historical Precedents Matching]
                       │
                       ▼
[Tahap 4: Press Conference & SEP Forward Guidance Decoding]
                       │
                       ▼
[Tahap 5: Multi-Scenario Trading Plan Formulation & LangGraph Handshake]
```

### Tahap 1: Data Gathering & Multi-Source Grounding
1. **Probabilitas Pasar Real-Time**:
   - Eksekusi tool `get_fedwatch_probabilities` (atau `web_search` jika database lokal kosong/stale).
   - Catat: probabilitas dominan saat ini, trajektori pergeseran 2 pekan terakhir (momentum repricing), dan laju repricing harian.
2. **Benchmark Imbal Hasil & Kurva Treasury**:
   - Eksekusi tool `get_treasury_yields` / `get_bond_yield_spreads`.
   - Catat: Yield US 2-Year (sensitif terhadap ekspektasi suku bunga jangka pendek), US 10-Year (kondisi finansial jangka panjang), spread kurva 2s10s (inversi vs un-inversion), dan TIPS yield (real interest rates).
3. **Katalis Data Keras (Hard Economic Data)**:
   - Inflasi: CPI headline YoY/MoM, Core CPI, Core PCE, dan inflasi jasa non-shelter ("Supercore Services ex-housing").
   - Tenaga Kerja: Non-Farm Payrolls (NFP), tingkat pengangguran resmi (U-3), dan laju upah rata-rata per jam (Average Hourly Earnings / AHE).
   - Pertumbuhan & Sektor Riil: GDP QoQ terestrimasi dan ISM Services/Manufacturing PMI.
4. **Struktur Internal Komite & Komunikasi Resmi**:
   - Catat voting split pertemuan sebelumnya (misal 9-3 mengindikasikan adanya faksi hawkish/dovish aktif yang vokal).
   - Pidato keynote Chair terakhir (misal Jackson Hole) dan sinyal dari dewan gubernur tetap (FOMC permanent voters).
5. **Positioning Institusional & Sentimen Ritel**:
   - Eksekusi `get_cot_report` untuk mengecek posisi neto Leveraged Funds pada DXY, Gold (XAUUSD), dan US Treasuries.
   - Eksekusi `get_retail_sentiment` / `get_fxssi_sentiment` untuk mengukur rasio crowding ritel.

---

### Tahap 2: Priced-In Testing (Uji Derajat Pemfaktoran Pasar)
Hitung skor pemfaktoran pasar (Priced-In Score) secara komposit pada skala 1-10 selaras dengan `market_dynamics_framework.md` dan `pydantic_schemas.py` dengan formula pembatasan eksplisit (clamping):

$$\text{Priced-In Score} = \min(10, \max(1, \text{Method 1} + \text{Repricing Momentum} + \text{Method 2} + \text{Method 3} + \text{Method 4}))$$

*(Catatan: Skor mentah/unclamped dapat mencapai hingga 19 pada kondisi konsensus ekstrem, sehingga wajib dibatasi maksimal 10 agar valid terhadap schema Pydantic dan evaluasi RiskGate).*

#### 1. Method 1: FedWatch Dominant Probability
| Probabilitas Dominan | Skor | Label | Karakteristik Reaksi |
|:---|:---|:---|:---|
| > 90% | 9-10 | Fully Priced In | Risiko pembalikan "sell-the-news" sangat tinggi. Hindari entri searah tren sebelum event. |
| 75-90% | 7-8 | Largely Priced In | Risiko sell-the-news tinggi. Kurangi ukuran posisi (lot size 0.5x-0.7x). |
| 55-75% | 5-6 | Partially Priced In | Ketidakpastian moderat; volatilitas dua arah seimbang. |
| 35-55% | 3-4 | Weakly Priced In | Potensi pergerakan terarah post-event cukup besar. |
| < 35% | 1-2 | NOT Priced In | Risiko kejutan absolut jika terealisasi. |

*Repricing Momentum Modifier*: Jika probabilitas melonjak >40% dalam 2 pekan terakhir (misal dari 50% ke 90%), tambahkan **+1 skor** untuk momentum repricing.

#### 2. Method 2: COT Extreme Positioning (Leveraged Funds)
Jika posisi spekulatif institusi telah overstretched searah ekspektasi konsensus, tambahkan **+3 skor**:
- Gold (XAUUSD): Net position > +200k (Overcrowded Long) atau < -80k (Overcrowded Short).
- EUR/USD: Net position > +150k atau < -150k.
- GBP/USD: Net position > +80k atau < -80k.
- JPY / AUD: Net position > +60k atau < -60k.

#### 3. Method 3: Price Run-Up vs ATR (H4, 20-bar lookback)
Ukur seberapa jauh harga telah bergerak mendahului katalis dibanding rentang normalnya:
- `run_up_vs_atr` > 4.0: Skor **+3** (Ekspansi ekstrem, rentan mean-reversion).
- `run_up_vs_atr` 2.5 - 4.0: Skor **+2** (Ekspansi tinggi).
- `run_up_vs_atr` 1.5 - 2.5: Skor **+1** (Ekspansi moderat).
- `run_up_vs_atr` < 1.5: Skor **+0** (Harga belum bergerak signifikan).

#### 4. Method 4: News Narrative Saturation
- 5+ artikel media finansial Tier-1 mendominasi tema yang sama selama 3+ hari berturut-turut: Skor **+2**.
- 2-4 artikel dalam 1-2 hari: Skor **+1**.
- < 2 artikel: Skor **+0**.

#### Panduan Aksi Skor Komposit & Timing Eksekusi
| Skor Komposit | Label | Aturan Trading Monika |
|:---|:---|:---|
| **8-10** | **FULLY PRICED IN** | **DILARANG** membuka posisi baru searah konsensus sebelum rilis event. Wajib WAIT atau siapkan rencana *fade the move* pasca-konferensi pers. |
| **5-7** | **LARGELY PRICED IN** | Hanya entri pada konfluensi teknikal sangat tinggi. Pangkas lot size 30-50% (0.5x-0.7x). |
| **3-4** | **PARTIALLY PRICED IN** | Terapkan batas konfluensi standar Monika. |
| **1-2** | **NOT PRICED IN** | Risiko kejutan sejati. Posisi sebelum rilis bersifat spekulatif tinggi. |

**Jendela Timing Eksekusi (Event Timing Playbook)**:
- **PRE-EVENT (12-48 jam)**: Volatilitas mengalami kompresi. Jika skor priced-in >= 7, **DILARANG** melakukan breakout entry searah konsensus.
- **EVENT (0-4 jam)**: **JANGAN PERNAH** mengejar spike candle pertama rilis keputusan jam 14:00 EST / 18:00 UTC. Biarkan likuiditas awal tersapu bersih dan intisari press conference (18:30 UTC) terkonfirmasi. Disiplin eksekusi multi-timeframe:
  - **Intraday Execution (M15 / H1)**: Jendela entri dibuka 15-30 menit pasca-presser dimulai, HANYA SETELAH likuiditas awal tersapu dan terbentuk Market Structure Shift (MSS) serta FVG terkonfirmasi pada M15/H1.
  - **Macro Swing Execution (H4 / D1)**: Biarkan H4 candle menutup (22:00 UTC) untuk memvalidasi bahwa penutupan candle berada di luar range liquidity sweep sebelum membangun posisi swing bertahap.
- **POST-EVENT (4-48 jam)**: **JENDELA KUALITAS TERTINGGI**. Struktur pasar telah mereset, likuiditas telah disapu, dan arah tren sejati terkonfirmasi pasca-presser.

---

### Tahap 3: Historical Precedents Matching (Pencocokan Preseden Historis)
Bandingkan konstelasi data saat ini dengan Pustaka 5 Preseden Historis (Bagian 2) untuk mengidentifikasi bias sistematis pasar:
- Apakah Chair bertindak preemptif mendahului data resmi? (Analogi 1994 Greenspan).
- Apakah pasar sudah melakukan pengetatan sendiri lewat lonjakan yield Treasury? (Analogi 2013 Bernanke).
- Apakah ada krisis eksternal/global yang memicu aktivasi fungsi kerugian asimetris? (Analogi 2015 Yellen).
- Apakah pasar salah mengartikan pemotongan suku bunga teknis sebagai siklus pelonggaran masif? (Analogi 2019 Powell).
- Apakah ada kebocoran terarah (whisper leak) darurat jelang blackout period akibat lonjakan data unanchored? (Analogi 2022 Powell).

---

### Tahap 4: Press Conference & SEP Forward Guidance Decoding
Gunakan Framework Pemisahan Action vs Guidance (Bagian 4):
1. Dekonstruksi rilis angka jam 18:00 UTC / 14:00 EST sebagai peristiwa awal (Action).
2. Dekonstruksi rilis proyeksi Dot Plot (SEP) dan sesi tanya-jawab konferensi pers jam 18:30 UTC / 14:30 EST sebagai penentu arah sejati (Guidance).
3. Analisis nada linguistik Chair: apakah menegaskan "data-dependent meeting-by-meeting" (fleksibilitas) atau mengunci trajektori terminal rate.
4. Petakan ke dalam salah satu dari 4 Kuadran Kebijakan: *Hawkish Continuation*, *Dovish Hike (Sell-the-News)*, *Hawkish Cut (Bull Trap)*, atau *Dovish Easing Explosion*.

---

### Tahap 5: Multi-Scenario Trading Plan Formulation & LangGraph Handshake
1. Rumuskan 3 skenario mandiri yang mencakup:
   - Skenario A: Base Case (Probabilitas tertinggi konsensus).
   - Skenario B: Hawkish Shock / Surprise.
   - Skenario C: Dovish Reversal / Sell-the-News Reversal.
2. Setiap skenario wajib dilengkapi parameter konkret: Katalis, Reaksi Aset, Jendela Waktu Eksekusi (Intraday vs Swing), Trigger Level SMC/Teknikal, Batas Invalidasi/Stop Loss, Target TP1/TP2, dan Rasio Risiko (Risk Sizing).
3. Sambungkan hasil analisis ke tabel `user_market_intel` melalui tool `save_market_intelligence` untuk memandu siklus trading LangGraph Monika berikutnya.

---

## BAGIAN 2: PUSTAKA PRESEDEN HISTORIS KEJUTAN BANK SENTRAL & TRANSMISI MULTI-ASET

Di bawah ini adalah 5 preseden historis kanonikal di mana bank sentral (The Fed) mengejutkan atau melawan konsensus pasar, beserta transmisi terverifikasi pada 5 kelas aset utama:

| Kasus & Periode | Konteks & Ekspektasi Konsensus | Keputusan Aktual & Sinyal Fed | Transmisi Multi-Aset (DXY, Yields, Gold, Saham, Kripto) | Mekanisme Inti / Pembelajaran Sistem Monika |
|:---|:---|:---|:---|:---|
| **1. 1994 Greenspan Preemptive Strike ("Bond Market Massacre")**<br>*4 Feb 1994 – Feb 1995* | Inflasi trailing jinak (~2.5%), GDP tumbuh 3-4%. Konsensus mem-price in suku bunga flat/kenaikan bertahap (<20% probabilitas hike Feb 1994). | Kenaikan agresif preemptif: +25bp (Feb), +25bp (Mar), +25bp (Apr), +50bp (Mei), +50bp (Agu), +75bp (Nov), +50bp (Feb 1995). Total naik +300bp (3.0% ke 6.0%). | • **Yields**: US 10Y meledak +229 bps (5.75% ke 8.04%); US 30Y naik ke 8.16%. Kerugian pasar obligasi global ~$1.5 Triliun.<br>• **DXY**: Awalnya terkonsolidasi akibat friksi dagang AS-Jepang, lalu membentuk reli struktural super-bull 1995-2001.<br>• **Saham**: S&P 500 koreksi -8.9% di Q1 1994; ditutup flat (+1.5%) di akhir tahun.<br>• **Gold**: Tertahan dalam rentang sempit ($370–$395/oz), ditekan lonjakan yield riil.<br>• **Kripto (Analog Modern)**: Kompresi likuiditas global drastis; aset spekulatif berdurasi tinggi mengalami de-rating valuasi parah.<br>• **Sistemik**: Kebangkrutan Orange County (Des 1994) & Krisis Tequila Peso Meksiko. | **Preemptive Forward-Looking Tightening**:<br>Bank sentral sengaja mendahului kurva data inflasi riil untuk mematikan ekspektasi inflasi masa depan. Pasar yang hanya mengamati data lagging terhantam de-leveraging hebat. |
| **2. Sep 2013 Bernanke "No-Taper" Surprise**<br>*18 September 2013* | Pasca retorika "Taper Tantrum" Mei/Juni, survei Bloomberg & pasar futures mem-price in tapering $10B–$15B/bulan dengan probabilitas >75-80%. | FOMC vote 9-1: Menahan program QE $85 Miliar/bulan secara utuh ($40B MBS, $45B Treasuries). Tapering ditunda hingga Desember 2013. | • **Yields**: US 10Y anjlok -17 bps pada hari pengumuman (2.87% ke 2.70%); 2Y turun 6 bps.<br>• **DXY**: Terjun bebas -1.1% dalam sehari (81.2 ke 80.1) ke level terendah multi-bulan.<br>• **Gold**: Meledak +$55/oz (+4.2%) dari $1,305 ke $1,365 hanya dalam hitungan jam.<br>• **Saham**: S&P 500 melonjak +1.22% mencetak rekor All-Time High baru (1,725.52).<br>• **Kripto**: BTC ($130) terpicu oleh likuiditas global yang berkepanjangan, memulai reli parabolik ke $1,150 (+780%) pada Nov 2013. | **Endogenous Financial Conditions Feedback Loop**:<br>Lonjakan yield obligasi sebelum rapat telah mengetatkan kondisi finansial ekonomi riil. Pasar telah mengerjakan tugas Fed duluan, sehingga Fed tidak perlu melakukan pengetatan formal. |
| **3. Sep 2015 Yellen "China Shock / Global Risk" Hold**<br>*17 September 2015* | Pasar tenaga kerja AS sangat solid (pengangguran 5.1%). Konsensus kuat mem-price in September 2015 sebagai liftoff suku bunga pertama pasca ZIRP (0%). | FOMC vote 9-1: Mempertahankan suku bunga di 0.00–0.25% (Hold), secara eksplisit mengutip kekhawatiran pelambatan mendadak ekonomi China dan gejolak pasar finansial global. | • **Yields**: US 10Y turun -11 bps (2.30% ke 2.19%); US 2Y turun -13 bps (0.81% ke 0.68%).<br>• **DXY**: Melemah -0.7% (95.4 ke 94.7) sebelum kembali stabil.<br>• **Gold**: Reli +$14/oz (+1.25%) dari $1,118 ke $1,132 terdorong penurunan yield riil.<br>• **Saham**: Rebound sesaat lalu ditutup melemah (S&P -0.26%); pengakuan Fed atas kerapuhan ekonomi global justru memicu sentimen risk-off.<br>• **Kripto**: BTC stabil di $230–$240, mengokohkan akumulasi dasar sebelum bull run 2016-2017. | **Mandate Asymmetry & Risk Management Minimax**:<br>Fungsi kerugian asimetris: Bahaya memicu krisis likuiditas global/resesi jauh lebih fatal daripada bahaya menunda kenaikan suku bunga selama 6-12 pekan. |
| **4. Jul 2019 Powell "Mid-Cycle Adjustment" Hawkish Cut**<br>*31 Juli 2019* | Pasar mem-price in 100% kepastian cut 25bp, dan kurva futures memproyeksikan siklus pelonggaran agresif 75-100bp hingga akhir tahun akibat perang dagang. | Rate dipotong 25bp (ke 2.00–2.25%) & balance sheet runoff dihentikan lebih awal. Namun di presser jam 14:35 EDT, Powell menegaskan: *"It's a mid-cycle adjustment to policy, not the beginning of a long series of rate cuts."* | • **Yields**: US 2Y naik +4 bps (1.87% ke 1.91%); kurva inversion mereda sesaat.<br>• **DXY**: Menguat tajam +0.55% ke level tertinggi 2 tahun (98.68) — Dolar reli saat suku bunga dipotong!<br>• **Saham**: S&P 500 ambruk -1.09% (-33 poin) dan Dow -333 poin saat sesi presser berlangsung.<br>• **Gold**: Jatuh -$20/oz ($1,430 ke $1,410) karena ekspektasi pelonggaran masif dipangkas.<br>• **Kripto**: BTC turun ~3% ($10,100 ke $9,800), terkorelasi langsung dengan aksi jual aset berisiko. | **Forward Guidance Dichotomy (Hawkish Cut)**:<br>Keputusan aksi (Rate Cut) terpenuhi sempurna, namun komunikasi verbal menghancurkan harapan pelonggaran lanjutan. Jangan pernah membeli breakout sebelum konfirmasi nada press conference! |
| **5. Jun 2022 Powell 75bp Acceleration ("WSJ Leak & CPI Panic")**<br>*15 Juni 2022* | Panduan resmi sebelum blackout: 50bp ("75bp is not actively considered"). Pada Jumat blackout (10 Jun), CPI Mei meledak ke 8.6% & inflasi UMich naik ke 3.3%. | Senin 13 Jun 14:00 EDT: Nick Timiraos (WSJ) membocorkan artikel whisper hike 75bp. Rabu 15 Jun: Fed merealisasikan kenaikan darurat 75bp (terbesar sejak 1994) ke 1.50–1.75%. | • **Yields**: US 2Y meledak +55 bps dalam 2 hari (2.81% ke 3.36%), lompatan 2-hari terbesar sejak 1987; US 10Y menyentuh 3.48%.<br>• **DXY**: Melesat dari 104.0 ke 105.6 (+1.5%) mencetak rekor 20 tahun.<br>• **Saham**: S&P 500 ambles -5.8% pada 10-13 Jun (resmi masuk Bear Market). Saat pengumuman 15 Jun terjadi relief bounce +1.46% karena sudah 100% priced in via bocoran WSJ.<br>• **Gold**: Tumbang -$65/oz ($1,875 ke $1,810) akibat ledakan yield riil.<br>• **Kripto**: Kehancuran sistemik; BTC anjlok dari $30,000 ke $20,000 (-33%) memicu insolvensi likuidasi Celsius & Three Arrows Capital (3AC). | **Emergency Credibility Defense & Blackout Whisper Leak**:<br>Jika ekspektasi inflasi berisiko lepas kendali (unanchored), bank sentral akan mengorbankan forward guidance resmi dan memakai jurnalis proksi untuk mem-price in pasar dalam waktu 48 jam guna mencegah malapetaka likuiditas hari-H. |

---

## BAGIAN 3: TAKSONOMI 5 MEKANISME KEGAGALAN KONSENSUS PASAR VS BANK SENTRAL

1. **Mekanisme 1: Endogenous Financial Conditions Feedback Loop (Pasar Mengerjakan Tugas Fed Duluan)**
   - *Prinsip*: Pasar keuangan bertindak reaktif mendahului tanggal pertemuan. Jika yield obligasi melonjak tajam, spread kredit korporasi melebar, mortgage rates melesat, dan indeks dolar menguat ekstrem, Financial Conditions Index (FCI) telah mengetat secara mandiri.
   - *Dinamika Kegagalan*: Pengetatan pasar setara dengan 50–100 bps kenaikan suku bunga tanpa bank sentral mengeluarkan kebijakan resmi. Melakukan pengetatan tambahan di atas kondisi tersebut berisiko memicu kecelakaan finansial. Sebaliknya, jika pasar reli prematur melonggarkan FCI, bank sentral terpaksa bersikap lebih hawkish dari konsensus untuk membatalkannya.

2. **Mekanisme 2: Mandate Asymmetry & Risk Management Loss Function (Fungsi Kerugian Asimetris Minimax)**
   - *Prinsip*: Pelaku pasar dan ekonom memproyeksikan nilai rata-rata (modal/mean forecast), sedangkan dewan gubernur bank sentral mengoptimalkan fungsi kerugian *minimax* (meminimalkan keparahan skenario terburuk/tail-risk).
   - *Matriks Kerugian*:
     - *Type I Error* (Over-tightening): Pertumbuhan melambat 0.5%, dapat diatasi dengan pelonggaran cepat di kuartal berikutnya.
     - *Type II Error* (Under-tightening): Ekspektasi inflasi tidak berjangkar (unanchored), memicu spiral upah-harga tahun 1970-an yang memerlukan resesi parah untuk menyembuhkannya.
     - *Tail-Risk Finansial*: Ancaman devaluasi mata uang mitra dagang utama (China 2015) atau krisis likuiditas perbankan (SVB 2023) akan secara instan memicu kehati-hatian (*pause/hold*), mengesampingkan target inflasi jangka pendek.

3. **Mekanisme 3: Institutional Credibility & Political Independence Signaling (Pertahanan Independensi Moneter)**
   - *Prinsip*: Masalah inkonsistensi waktu (*time inconsistency*). Politisi dan pemerintah eksekutif memiliki horizon jangka pendek dan selalu menginginkan suku bunga rendah guna membiayai belanja atau memenangkan pemilu.
   - *Dinamika Sinyal*: Ketika ada tekanan terbuka dari Presiden, Menteri Keuangan, atau intervensi buyback obligasi sepihak yang menekan yield, tunduk pada tekanan tersebut akan menghancurkan premi risiko kedaulatan di mata investor obligasi global (*bond vigilantes*). Dewan gubernur memiliki dorongan institusional kuat untuk mengambil keputusan ortodoks dan tegas (hike atau hold hawkish) guna menegaskan otonomi independen bank sentral.

4. **Mekanisme 4: Information Asymmetry, Latent Data, & Global Spillover (Asimetri Data Berfrekuensi Tinggi)**
   - *Prinsip*: Pelaku ritel dan analis pasar bergantung pada data ekonomi lagging publik (CPI bulanan, NFP bulanan).
   - *Keunggulan Informasi*: Bank sentral memiliki akses eksklusif ke metrik transaksi real-time (arus likuiditas harian Fedwire, saldo kliring perbankan, data stres pengawasan perbankan internal/CAMELS, dan intelijen koordinasi likuiditas swap-line BIS Basel). Keputusan yang tampak "membingungkan" bagi publik biasanya didorong oleh retakan likuiditas tersembunyi yang belum dipublikasikan.

5. **Mekanisme 5: Forward Guidance Ambiguity & Noise-Trader Overinterpretation (Distorsi Konsensus atas Bahasa Bersyarat)**
   - *Prinsip*: Pejabat bank sentral selalu berbicara dalam distribusi probabilistik bersyarat (*conditional statements* / "data-dependent", "if appropriate").
   - *Perangkap Konsensus*: Partisipan pasar dan media keuangan yang didorong struktur taruhan biner (CME FedWatch) menyederhanakan sinyal bersyarat 60% menjadi kepastian 100%, sehingga membangun posisi spekulatif yang sangat padat (*overcrowded*). Saat Chair menolak berkomitmen pada lintasan lanjutan dalam konferensi pers, terjadi likuidasi paksa (*unwind squeeze*) yang membalikkan pergerakan harga secara brutal.

---

## BAGIAN 3.1: KRITERIA KUANTITATIF & KUALITATIF ANALOG MATCHING ENGINE

Untuk menentukan preseden historis mana yang paling relevan dengan situasi saat ini, subagent `worker_macro` atau `ChatAgent` WAJIB menguji metrik berikut:

### 1. Rubrik Skor Analogi Komposit (Analog Match Score: 0 - 100 Poin)
1. **Priced-In Crowding & Easing Cycle Mispricing (Bobot: 20 Poin)**:
   - FedWatch Probabilitas dominan > 85% dan momentum kenaikan probabilitas > 30% dalam 14 hari: +10 Poin.
   - Pasar mem-price in pemotongan suku bunga kumulatif agresif (> 75 bps) padahal Core PCE / inflasi jasa masih lengket (> 2.5%): +10 Poin (Memicu Analogi Powell 2019 / Hawkish Cut Trap).
2. **Financial Conditions Index (FCI) Divergence (Bobot: 25 Poin)**:
   - Yield US 10Y telah bergerak > 40 bps berlawanan atau mendahului arah kebijakan dalam 60 hari: +15 Poin.
   - Credit Spreads (US High Yield OAS) melebar > 75 bps: +10 Poin (Memicu Analogi Bernanke 2013).
3. **External / Global Contagion Risk (Bobot: 20 Poin)**:
   - Gejolak devaluasi mata uang mitra utama, krisis utang perbankan regional, atau indeks saham global turun > 7% dalam 30 hari: +20 Poin (Memicu Analogi Yellen 2015).
4. **Institutional Independence Friction (Bobot: 15 Poin)**:
   - Adanya kritik terbuka eksekutif pemerintah/Presiden terhadap kebijakan suku bunga, atau intervensi fiskal Departemen Keuangan yang menentang pengetatan: +15 Poin (Memicu Analogi Greenspan 1994 / Kredibilitas Sinyal).
5. **Whisper Leak / Blackout Breach Indicator (Bobot: 20 Poin)**:
   - Kemunculan artikel berita dari jurnalis terpercaya (misal WSJ / FT) pada masa blackout yang secara drastis mengubah proyeksi suku bunga: +20 Poin (Memicu Analogi Powell 2022).

### 2. Decision Tree Pemilihan Preseden Historis
```
[Mulai Evaluasi Event Makro]
       │
       ├─► Apakah ada kebocoran whisper resmi di masa blackout (WSJ leak)?
       │     └─► YA ──► [PRESEDEN 2022 POWELL]: Emergency Repricing. Waspadai relief rally pasca-hike.
       │
       ├─► Apakah pasar global sedang krisis/volatilitas tinggi (China/Banking/Perang)?
       │     └─► YA ──► [PRESEDEN 2015 YELLEN]: Minimax Hold. Risiko hold kejutan sangat tinggi.
       │
       ├─► Apakah US 10Y Yield sudah melonjak tajam mengetatkan kondisi finansial duluan?
       │     └─► YA ──► [PRESEDEN 2013 BERNANKE]: No-Action/No-Taper Surprise. Fade ekspektasi pengetatan.
       │
       ├─► Apakah ada tekanan politik terbuka DAN Chair ingin menegakkan reputasi independen?
       │     └─► YA ──► [PRESEDEN 1994 GREENSPAN]: Preemptive Hawkish Action. Bersiap menghadapi shock yield.
       │
       └─► Apakah pasar mem-price in siklus easing panjang padahal data inflasi masih lengket?
             └─► YA ──► [PRESEDEN 2019 POWELL]: Hawkish Cut Trap. Bersiap short aset berisiko pasca-presser.
```

---

## BAGIAN 4: FRAMEWORK PEMISAHAN KEPUTUSAN BUNGA (ACTION) VS FORWARD GUIDANCE

Keputusan bank sentral terdiri dari DUA peristiwa berurutan yang tidak boleh dicampuradukkan:

```
[18:00 UTC / 14:00 EST] ───────► KEPUTUSAN SUKU BUNGA & STATEMENT (Action)
                                  - Biner: Hike / Cut / Hold
                                  - Reaksi HFT / Algoritma (0-120 detik)
                                  - Waspada: Sering berupa Fakeout / Liquidity Sweep
                                             │
                                             ▼
[18:30 UTC / 14:30 EST] ───────► PROYEKSI SEP DOT PLOT & PRESS CONFERENCE (Forward Guidance)
                                  - Proyeksi median terminal rate, inflasi, GDP
                                  - Bahasa tubuh, retorika, & penegasan independensi Chair di Q&A
                                  - Menentukan ARAH TREN SEJATI (True Trend 4-48 jam)
```

### Matriks 4-Kuadran Interaksi Action vs Guidance

| Kuadran | Keputusan (Action) | Forward Guidance (SEP & Q&A) | Dampak Pasar (DXY, XAU, Saham, Kripto) | Strategi Trading Monika |
|:---|:---|:---|:---|:---|
| **1. Hawkish Continuation** | Hike / Tahan Tinggi | Dot Plot naik, Chair tegaskan inflasi belum selesai, tolak komitmen cut | DXY reli berkelanjutan; Yields naik; XAUUSD, Saham, BTCUSD tertekan kuat | Ikuti tren penguatan USD pasca-presser; cari setup Sell on Rally pada XAUUSD dan EURUSD setelah retest FVG H4. |
| **2. Dovish Hike (Sell-the-News)** | Hike terealisasi | Dot Plot melandai, Chair sebut suku bunga sudah restriktif, hindari komitmen hike lanjutan | DXY spike sesaat lalu dibanting turun; XAUUSD memantul tajam; Saham reli | **Fade initial spike!** JANGAN pasang order sebelum rilis! Biarkan spike awal menyapu likuiditas swing low, lalu pasang limit order atau tunggu konfirmasi pembalikan (liquidity sweep & MSS reclaim M15/H1) pasca-presser jika guidance terkonfirmasi dovish. |
| **3. Hawkish Cut (Bull Trap)** | Cut terealisasi | Chair sebut "mid-cycle adjustment", batasi ekspektasi cut berikutnya, dot plot naik | Equities & Emas jatuh pasca-reli sesaat; DXY rebound tajam | **Bull Trap Avoidance!** Jangan mengejar breakout buy saat rilis suku bunga! Tunggu konfirmasi presser, siapkan setup short selling pasca-breakdown MSS M15/H1. |
| **4. Dovish Easing Explosion** | Cut / Dovish Pause | Proyeksi cut agresif, Chair khawatir terhadap pelemahan pasar tenaga kerja | DXY anjlok tajam; XAUUSD, BTCUSD, & Equities melonjak eksponensial | **Momentum buy breakout!** Buy pullback ke discount zone H1 pada XAUUSD, EURUSD, BTCUSD; aktifkan TrailingStopManager. |

---

## BAGIAN 5: TEMPLATE OUTPUT INSTITUSIONAL 6 BAGIAN

Saat merespons analisis probabilitas event makro atau menghasilkan riset mendalam, sistem WAJIB menyajikan output terstruktur dalam Bahasa Indonesia dengan format institusional 6 bagian yang murni berfokus pada kedalaman analisis dan perumusan skenario:

```markdown
# Analisis Keputusan Kebijakan [Nama Bank Sentral: FOMC / ECB / BOE / BOJ / RBA] & Press Conference [Nama Chair / Governor]

## 1. Snapshot Data Terkini & Trajektori Ekspektasi Pasar
- Probabilitas Pasar (CME FedWatch / OIS / Swap Pricing): [Persentase dominan saat ini, trajektori pergeseran harian & 2-mingguan]
- Rangkaian Katalis Data Keras:
  - Internal Komite & Pertemuan Sebelumnya: [Voting split keputusan lalu, sinyal retorika penting]
  - Pidato & Sinyal Pimpinan: [Analisis pidato kunci pimpinan bank sentral, nada hawkish/dovish]
  - Tenaga Kerja & Kapasitas: [NFP/Unemployment (Fed), Wage Tracker (ECB), Wage pressures (BoE), Shunto (BoJ), Capacity utilisation (RBA)]
  - Inflasi Terkini: [Core PCE (Fed), HICP (ECB), CPI (BoE/BoJ), Trimmed Mean CPI (RBA)]
- Sintesis Narasi Konsensus Pasar: [Mengapa pasar mem-price in skenario tertentu sebagai base case yang kuat]

## 2. Uji Derajat Pemfaktoran Pasar (Priced-In Score) & Asimetri Risiko
- Uji Kepastian Mutlak: [Penjelasan mengapa probabilitas pasar bukan kepastian 100%]
- Perhitungan Priced-In Score (1-10): [Metrik Method 1-4 komposit terhitung]
- Titik Skeptisisme & Friksi:
  - Perpecahan Internal Komite: [Potensi faksi dovish/hawkish yang menahan diri berdasarkan voting split]
  - Friksi Kelembagaan & Politik: [Intervensi Departemen Keuangan/fiskal, buyback obligasi, tekanan politik eksekutif]
  - Asimetri Reaksi: [Evaluasi apakah risiko sell-the-news tinggi jika konsensus terealisasi]
- Kesimpulan Deviasi: [Seberapa besar kemungkinan deviasi / kejutan berdasarkan konvergensi sinyal independen]

## 3. Analisis Preseden Historis Kejutan Bank Sentral
[Uraian preseden historis yang relevan beserta mekanisme penyebabnya, merujuk pada Bagian 2 & 3 Playbook]:
- Kasus Relevan (misal: Greenspan 1994, Bernanke 2013, Yellen 2015, Powell 2019, atau Powell 2022): [Uraian analogi]
- Mekanisme Kegagalan Konsensus: [Pencocokan analogi dengan rubrik Analog Match Score]
- Pembelajaran untuk Siklus Saat Ini: [Evaluasi transmisi multi-aset berdasarkan preseden historis]

## 4. Dekonstruksi Proyeksi SEP & Prediksi Nada Press Conference
- Pola Komunikasi & Track Record Chair/Governor: [Karakteristik komunikasi, fleksibilitas data-dependent]
- Dekonstruksi Proyeksi (SEP Dot Plot / Staff Projections / Tenbo Report): [Arah terminal rate dan proyeksi inflasi]
- Pemisahan Keputusan Bunga (Action) vs Forward Guidance (Presser): [Klasifikasi ke dalam 4-Kuadran: Hawkish Continuation, Dovish Hike, Hawkish Cut, Dovish Easing]
- Skenario Paling Mungkin di Press Conference: [Prediksi nada bicara Q&A]

## 5. Trading Plan Multi-Skenario Terstruktur
- Skenario A: Base Case
  - Katalis: [Keputusan konsensus + Guidance sejalan]
  - Reaksi Aset: [Arah DXY/FX, Yields, Gold, Saham, Kripto]
  - Rencana Aksi: [Eksekusi timing: wait for initial spike liquidity sweep, lalu konfirmasi FVG/MSS]
- Skenario B: Hawkish Shock
  - Katalis: [Hike kejutan atau Dot Plot/Forward guidance jauh lebih restriktif]
  - Reaksi Aset: [Penguatan tajam mata uang, lonjakan yield, penurunan risk assets/emas]
  - Rencana Aksi: [Short setup pada pair inverse, buy USD/yield continuation]
- Skenario C: Dovish Reversal / Sell-The-News
  - Katalis: [Cut kejutan, atau Hike dengan forward guidance dovish / terminal rate dipangkas]
  - Reaksi Aset: [Pelemahan tajam mata uang, reli relief pada emas/risk assets]
  - Rencana Aksi: [Fade move / liquidity sweep reclaim pada diskon H1]

## 6. Handshake ke LangGraph Execution Engine (user_market_intel)
- Transmisi ke user_market_intel: [Penyimpanan direktif via save_market_intelligence]
- Mapping ke Stage 1 & Stage 2: [Pengawalan bias makro dan batasan invalidasi per-asset]
- Constraint RiskGate: [Penerapan batas priced-in >=8 (WAIT) atau lot size reduction 0.5x-0.7x jika priced-in 5-7]
```

> **ATURAN PENTING MENGENAI TRADING PLAN DI CHAT:**
> 1. **Fokus Riset**: Jika operator HANYA meminta analisis probabilitas, peluang keputusan, sejarah, atau prediksi press conference, sistem **DILARANG MEMAKSAKAN** penulisan setup teknikal/trading plan (Entry, SL, TP) di dalam chat. Berikan jawaban analitis murni yang berkualitas tinggi, mendalam, dan komprehensif.
> 2. **Pengecualian**: Detail Trading Plan teknikal (Entry, SL, TP) HANYA disajikan jika operator secara eksplisit meminta trading plan dalam kuerinya (misal: *"buatkan trading plan untuk XAUUSD pasca-FOMC"*).
> 3. **Background Auto-Persistence**: Sistem secara otomatis di latar belakang (background) menyimpan ringkasan hasil analisis ini ke database (`user_market_intel`). Data ini akan otomatis diteruskan dan diserap oleh sistem Monika saat menjalankan siklus **Analisis Makro (Stage 1)** dan **Pembuatan Trading Plan Per-Asset (Stage 2)** pada siklus LangGraph terjadwal.


---

## BAGIAN 6: INTEGRASI LANGGRAPH & DATABASE ENGINE

1. **Alur Penyimpanan (Chat Agent → Database)**:
   - Chat Agent atau operator memicu penyimpanan market intelligence dengan memanggil tool `save_market_intelligence`:
     ```python
     save_market_intelligence(
         title="FOMC September 2026 Scenario Watch",
         summary="Base case Hike 25bp with neutral Q&A. Watch XAUUSD sell-the-news reversal at 2500 OB.",
         full_content="[Konten Lengkap 3 Skenario]",
         intel_type="deep_research",
         affected_symbols="EURUSD,XAUUSD,USDJPY",
         directive="scenario_watch",
         target_cycle="until_event",
         expires_in_hours=24
     )
     ```
2. **Injeksi Siklus Berjalan (Database → LangGraph Nodes)**:
   - Data otomatis dimuat oleh `data_node.py` ke dalam state `user_market_intel`.
   - `fundamental_node.py` (Stage 1) menyelaraskan bias makro global dengan batas skenario.
   - `per_asset_node.py` dan `debate` nodes (Stage 2) memvalidasi apakah level teknikal SMC berada dalam koridor invalidasi trading plan skenario.
   - `risk_gate_node.py` memberlakukan penolakan keras (hard block) jika priced-in >= 9, mandat WAIT (disallow new consensus positions) jika priced-in >= 8 menjelang event, serta pembatasan lot size (0.5x-0.7x) dan kenaikan threshold konfluensi (+2) jika event makro berperingkat priced-in 5-7 (LARGELY PRICED IN) atau berstatus caution.
