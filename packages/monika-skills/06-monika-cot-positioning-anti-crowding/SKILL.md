---
name: monika-cot-positioning-anti-crowding
description: Institutional positioning analysis via CFTC COT reports, Contrarian Crowd Exhaustion Discipline, 3-Specialist domain triangulation (Technical 45%, Macro 35%, Sentiment 20%), and the 5 Institutional Synergy States.
version: 1.0.0
tags: [trading, cot, positioning, anti-crowding, institutional-flow, contrarian, sentiment]
---

# Monika COT Positioning & Anti-Crowding Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Hierarki Partisipan CFTC COT 3-Tier

Laporan Commitment of Traders (COT) membedah struktur kepemilikan kontrak berjangka menjadi 3 kelompok:
1. **Commercial Hedgers (Produsen / Bank Komersial)**:
   - Menggunakan pasar untuk lindung nilai bisnis riil (bukan mencari spekulasi murni).
   - Bertindak sebagai jangkar nilai fundamental di titik ekstrem. Jika Commercial Hedgers melakukan akumulasi masif saat harga turun $\rightarrow$ Sinyal dasar harga kuat.
2. **Non-Commercial Large Speculators (Hedge Funds / Commodity Trading Advisors)**:
   - Pengikut tren (*trend followers*) bervolume besar.
   - **Kerentanan Squeeze**: Jika posisi bersih berada di atas persentil ke-85 atau di bawah persentil ke-15, setiap kejutan makro minor akan memicu likuidasi paksa (*unwind squeeze*).
3. **Non-Reportable Retail (Trader Ritel Kecil)**:
   - Digunakan sebagai indikator kontrarian murni di level ekstrem.

---

## 2. Disiplin Kelelahan Kerumunan Kontrarian (Contrarian Discipline)

> [!IMPORTANT]
> **Larangan Mengikuti Konsensus Ekstrem**:
> Dilarang menyimpulkan "spekulan memegang rekor posisi beli terbanyak, maka harga pasti akan terus naik". Tanpa suntikan likuiditas makro baru, posisi rekor beli berarti **tidak ada lagi pembeli marjinal yang tersisa di pasar**, membuka jalan bagi aksi pembalikan tajam (*bull trap*).

---

## 3. Triangulasi 3 Spesialis & 5 Status Sinergi Institusional

Dewan spesialis Monika membagi analisis menjadi 3 pilar:
- **Technical Specialist (45%)**: Murni mengukur aksi harga, struktur market shift, dan zona diskon/premi.
- **Macro Specialist (35%)**: Murni mengukur diferensial suku bunga, imbal hasil obligasi, dan siklus likuiditas.
- **Sentiment Specialist (20%)**: Murni mengukur posisi spekulan COT dan sentimen kerumunan dengan lensa kontrarian.

### Matriks 5 Status Sinergi Institusional:
1. `uncrowded_institutional_synergy` (Pengganda: **1.10x**):
   - Teknikal dan Makro selaras searah; posisi spekulan COT belum jenuh.
   - **Tingkat Kemenangan Historis: 81.8%**. Kondisi eksekusi paling ideal.
2. `institutional_contrarian_synergy` (Pengganda: **1.08x**):
   - Teknikal dan Makro selaras searah; trader ritel/sentimen terjebak melawan arah institusi.
3. `crowded_unanimous_exhaustion` (Pengganda: **0.82x** atau paksa `HOLD`):
   - Teknikal, Makro, dan Sentimen semuanya searah di level ekstrem ($>85\%$ atau $<15\%$).
   - **Risiko Pembalikan: 72.7% - 80%**. Dilarang membuka posisi baru sebelum terjadi pembersihan likuiditas (*liquidity flush*).
4. `crowded_tech_sent_trap_vs_macro` (Pengganda: **0.85x**):
   - Sinyal teknikal dan kerumunan ritel melawan arah fundamental makro.
   - **Risiko Jebakan Ritel: 71.4%**. Waspadai pembalikan mendadak saat makro kembali mengendalikan pasar.
5. `technical_macro_conflict` (Pengganda: **0.88x**):
   - Terdapat benturan antara teknikal dan makro. Terapkan penalti ukuran dan tunggu konfirmasi lanjutan.

Jalankan evaluasi CLI:
```bash
python scripts/cot_synergy_calc.py --cot-52w-pct 91.0 --tech-dir buy --macro-dir buy --sent-dir buy
```
