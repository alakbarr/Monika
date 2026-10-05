---
name: daily-catalyst-and-opportunity-playbook
description: "Daily catalyst screening, opportunity selection, and 3-pillar execution."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [daily_catalyst, market_drivers, opportunity_screener, buy_sell_playbook, macro_sentiment_technical]
---

# Daily Catalyst & Opportunity Playbook — Kurasi Penggerak Pasar & Matriks 3-Pilar

Panduan institusional untuk menyajikan evaluasi harian pasar secara komprehensif, terstruktur, dan anti-AI slop. Playbook ini diaktifkan ketika pengguna meminta pemantauan berita harian, seleksi peluang pair terbaik, dan panduan menentukan keputusan buy/sell berbasis konfluensi **Berita (Makro)**, **Sentimen (Positioning)**, dan **Teknikal (Price Action)**.

Playbook ini bersifat **agnostik**: berlaku universal untuk sembarang instrumen (Forex, Emas/XAUUSD, Minyak, Indeks, Crypto) dan sembarang agenda berita.

---

## 1. PROTOKOL ALUR PIKIR & TOOL GATHERING

Sebelum menyusun jawaban, AI Agent wajib memanggil dan menggabungkan data dari tools berikut:
1. `get_economic_calendar`: Membaca seluruh rilis berita hari ini (`hours_ahead=24`).
2. `get_news_digest` / `get_news_items`: Menangkap tema narasi makro dan geopolitik aktif.
3. `trigger_market_scan`: Memindai setup teknikal pada watchlist mayor & komoditas.
4. `get_retail_sentiment` & `get_cot_report`: Memeriksa posisi crowding retail vs institusional.
5. `get_market_session` & `get_dxy`: Mengidentifikasi rezim likuiditas sesi saat ini dan tren dolar.
6. `get_smc_zones` & `get_optimal_intraday_levels`: Menentukan zona level kunci HTF (H4/H1) pada pair terpilih.

---

## 2. STRUKTUR STANDAR OUTPUT WAJIB (3-BAGIAN INSTITUSIONAL)

Agen HARUS menyajikan analisis dalam format 3 bagian yang tegas dan dapat dieksekusi:

### BAGIAN 1: Tabel Kurasi Katalis Penggerak Pasar Hari Ini
Sajikan tabel bersih yang mengklasifikasikan event berdasarkan tingkat pengaruh (Tier-1 High Impact vs Tier-2 Secondary):

| Jam (WIB / UTC) | Mata Uang | Event / Katalis | Level | Konsensus vs Sebelumnya | Skenario Arah Dampak Pasar |
| :--- | :---: | :--- | :---: | :---: | :--- |
| *e.g. 19:30 WIB* | USD | *Core PCE Price Index (MoM)* | **Tier-1** | Cons: 0.3% \| Prev: 0.2% | **Hot (>0.4%)**: Hawkish Fed, USD rally, XAU/EUR under pressure.<br/>**Cool (<0.2%)**: Dovish repricing, USD dump, XAU/EUR rally. |
| *e.g. 15:00 WIB* | EUR | *German Ifo Business Climate* | **Tier-2** | Cons: 86.0 \| Prev: 85.8 | Sentimen pertumbuhan kawasan Eurozone. |

*Pedoman Evaluasi Katalis*:
- Pisahkan berita 'Noise' dengan berita pengubah ekspektasi suku bunga / pertumbuhan (Tier-1).
- Tandai potensi revisi bulan sebelumnya jika relevan.

---

### BAGIAN 2: Watchlist Pasangan Pilihan Hari Ini (Top 2–3 Opportunities)
Pilih hanya **2 hingga 3 instrumen** yang memiliki konfluensi tertinggi antara tema berita hari ini dan struktur teknikal HTF yang bersih. Jangan berikan daftar terlalu panjang.

Untuk setiap pair pilihan, sajikan:
1. **Nama Pair & Bias Utama**: (e.g. `XAUUSD` — Bias: *Bullish on Dip*).
2. **Katalis Pendorong**: Mengapa pair ini paling responsif terhadap berita hari ini (e.g. Emas sensitif terhadap deviasi yield riil USD).
3. **Peta Struktur Teknikal HTF**:
   - Level Kunci H4/H1: Zona Order Block / FVG unmitigated terdekat.
   - Skenario Jalur Harga: Di mana area diskon ideal untuk mencari entri.

---

### BAGIAN 3: Matriks Keputusan 3-Pilar (Buy / Sell Execution Rules)
Berikan panduan objektif mengenai apa saja syarat yang HARUS terpenuhi sebelum menarik pelatuk:

#### Pilar 1: Ambang Deviasi Berita (News Surprise Delta)
- **Aturan Deviasi Nyata**: Tetapkan angka ambang batas minimum kejutan (*surprise threshold*).
  - *Contoh*: "Hanya valid mencari buy EURUSD jika data rilis meleset $\ge -0.2\%$ di bawah konsensus."
- **Aturan Data Inline / Ambigu**: Jika data rilis persis sesuai konsensus (inline $\pm 0.05\%$), perlakukan sebagai non-event yang memicu whipsaw/choppy $\implies$ **Dilarang breakout chasing, fokus pada range fading atau wait-and-see**.

#### Pilar 2: Filter Sentimen & Positioning (Contrarian Check)
- **Rasio Retail Sentiment (SSI)**:
  - Jika Retail Long $> 70\%$ $\implies$ Cari setup **SELL** (institusi menyapu likuiditas ritel).
  - Jika Retail Short $> 70\%$ $\implies$ Cari setup **BUY**.
  - Jika Retail berada di zona netral (45%–55%) $\implies$ Gunakan panduan murni arah tren dan berita.
- **CFTC COT Positioning**: Konfirmasi apakah posisi spekulatif institusi sedang overextended (jenuh beli/jual).

#### Pilar 3: Trigger Eksekusi Teknikal Intraday (Price Action Confirmation)
- **Protokol Blackout Waktu**: Wajib patuhi jendela blackout berita $\pm 15$ menit sebelum dan sesudah rilis. Jangan pasang market order saat lilin berita pertama meledak.
- **Syarat Validasi Entri Pasca-Rilis (M15 / H1)**:
  1. *Liquidity Sweep*: Terjadi sapuan likuiditas (Asian High/Low atau Session High/Low) diikuti penolakan tajam (panjang wick $> 35\%$).
  2. *Change of Character (CHoCH)*: Struktur internal M15 berbalik arah mengonfirmasi transfer kontrol pasar.
  3. *Mitigasi FVG / IFVG*: Harga kembali masuk (*pullback*) ke zona Fair Value Gap atau Inverted FVG yang baru terbentuk.
- **Batas Risiko Objektif**: Letakkan Stop Loss di luar swing sweep ekstrem, bukan di level acak. Targetkan minimum Risk-to-Reward 1:2.
