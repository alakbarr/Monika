# Reference 01: Data Gathering, TTL & Session Timing Rules

Dokumen referensi ini merinci protokol ekstraksi telemetri 5 fase, batas kedaluwarsa data (TTL), aturan sesi trading global, dan penyerapan volatilitas pasca-berita.

---

## 1. Protokol Ekstraksi Telemetri 5 Fase

1. **Fase 1: Makro Global & Imbal Hasil Obligasi**
   - US 10-Year Treasury Yield (`US10Y`), 2-Year Treasury Yield (`US2Y`), spread 2s10s.
   - US 10-Year TIPS Real Yield (`DFII10`), US Dollar Index (`DXY`), VIX, S&P 500 (`SPX`).
   - Suku bunga acuan bank sentral (Fed Funds, ECB Deposit Facility, BoE Bank Rate, BoJ Policy Rate, RBA Cash Rate).
2. **Fase 2: Kalender Ekonomi & Berita Berdampak Tinggi**
   - Rilis data Tier-1 dalam 24 jam terakhir dan 24 jam ke depan (NFP, CPI, Core PCE, FOMC, ECB Rate Decision, ISM Services/Mfg, GDP).
   - Selalu cari nilai: `Actual`, `Consensus`, `Previous`, dan `Prior Revision`.
3. **Fase 3: Pemosisian Institusional CFTC COT**
   - Laporan Commitment of Traders (COT) kategori *Legacy Futures Only* atau *Disaggregated Futures*:
     - EUR: Kontrak `099741`
     - GBP: Kontrak `096742`
     - JPY: Kontrak `097741`
     - Gold: Kontrak `088691`
     - WTI: Kontrak `067651`
     - Brent: Kontrak `06765T`
     - BTC: Kontrak `133741`
   - Metrik kunci: `Non-Commercial Net Positioning`, `4-Week Net Change (Delta)`, `52-Week Percentile Rank (0-100%)`.
4. **Fase 4: Telemetri Teknikal Multi-Timeframe (D1, H4, H1)**
   - Candle Close, High 20-bar, Low 20-bar, Average True Range (ATR-14), Average Daily Range (ADR-5D).
   - EMA 9, 21, 50, 200; RSI-14; MACD (12, 26, 9); ADX-14.
   - Deteksi SMC: Order Blocks (OB) aktif yang belum termitigasi, Fair Value Gaps (FVG), dan Previous Day/Week High/Low (PDH/PDL/PWH/PWL).
5. **Fase 5: Verifikasi Silang & Pelabelan Keyakinan**
   - Beri label setiap poin data: `HIGH`, `MEDIUM`, `LOW`, atau `UNVERIFIED`.

---

## 2. Matriks Batas Kedaluwarsa Data (TTL) & Penalti Stale Data

| Domain Data | Batas Maksimal (TTL) | Tindakan Jika Melebihi Batas |
|---|---|---|
| Probabilitas FedWatch | 12 Jam | `STALE_DATA_WARNING` + Pangkas ukuran posisi 50% |
| Imbal Hasil Treasury & Real Yields | 24 Jam | `STALE_DATA_WARNING` + Pangkas ukuran posisi 50% |
| Suku Bunga Acuan Bank Sentral | 72 Jam | `STALE_DATA_WARNING` |
| Laporan CFTC COT | 7 Hari (168 Jam) | `STALE_DATA_WARNING` + Pangkas ukuran posisi 50% |
| Level VIX & Rezim Volatilitas | 4 Jam | Wajib perbarui sebelum eksekusi |
| Indikator Teknikal H4 | 5 Jam | Wajib perbarui candle H4 terbaru |
| Indikator Teknikal D1 | 24 Jam | Wajib perbarui candle D1 kemarin |

---

## 3. Sesi Trading, Killzones & Pemblokiran Rollover

- **Sesi Tokyo (`00:00 - 06:00 UTC`)**:
  - Rentang volatilitas terbatas untuk EUR/USD dan GBP/USD.
  - Sesi utama untuk eksekusi pasangan AUD/USD, USD/JPY, dan NZD/USD.
- **Sesi London Open & Judas Swing (`07:00 - 10:00 UTC`)**:
  - **07:00 - 08:30 UTC: Judas Swing Alert**: Pembuat pasar kerap melakukan manipulasi harga (*false breakout*) menyapu likuiditas batas atas/bawah sesi Asia.
  - Tunggu konfirmasi sapuan likuiditas (*liquidity sweep*) dan Market Structure Shift (MSS) pada M15/H1 sebelum masuk.
- **London-New York Overlap (`12:00 - 16:00 UTC`)**:
  - Puncak volume likuiditas dan order flow institusional harian.
  - Memenuhi syarat **+1 Confluence Bonus** dalam penilaian setup.
- **Sesi New York Siang (`16:00 - 20:00 UTC`)**:
  - Terjadi *London Fix* pada 16:00 UTC (aliran rebalancing portofolio akhir bulan).
  - Volatilitas cenderung menurun setelah 18:00 UTC.
- **Jendela Rollover Blackout (`21:55 - 22:15 UTC`)**:
  - **HARD EXECUTION BLOCK**: Seluruh bank dan pialang melakukan perpindahan buku harian (*daily rollover*).
  - Spread melebar 5x hingga 15x dari kondisi normal. Dilarang membuka posisi baru atau menempatkan order pasar.

---

## 4. Penyerapan Volatilitas Pasca-Berita (3-Phase Protocol)

Untuk rilis berita Tier-1 (NFP, CPI, FOMC, ECB):
- **Fase 1 (`0 - 15 Menit Pasca-Rilis`)**:
  - **Strict Execution Blackout**: Dilarang mengejar pergerakan impuls candle pertama. Slippage dan pelebaran spread berada di titik ekstrem.
- **Fase 2 (`15 - 60 Menit Pasca-Rilis`)**:
  - Petakan *Event Anchor Range*: catat `Event High`, `Event Low`, dan `Event Midpoint (50%)`.
  - Amati apakah harga membentuk konsolidasi di dalam range atau melakukan penolakan di batas ekstrem.
- **Fase 3 (`1 - 4 Jam Pasca-Rilis`)**:
  - Tentukan apakah terjadi:
    1. **Structural Acceptance**: Dua candle M15 ditutup di luar range dengan retest yang bertahan $\rightarrow$ Lanjutkan arah tren baru.
    2. **Liquidity Sweep & Fade**: Terjadi ekor panjang (*wick*) $>50\%$ di luar range kemudian candle ditutup kembali ke dalam range $\rightarrow$ Eksekusi pembalikan (*fade the move*).
