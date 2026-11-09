# Reference: TTL & CFTC COT Contract Specifications

Dokumen ini memuat daftar kode kontrak resmi CFTC COT dan rincian batas umur data (TTL).

---

## 1. Kode Kontrak CFTC COT Legacy Futures

| Simbol Trading | Aset Acuan | Kode Kontrak CFTC | Kategori Laporan |
|---|---|---|---|
| `EURUSD` | Euro FX | `099741` | Chicago Mercantile Exchange (CME) |
| `GBPUSD` | British Pound | `096742` | Chicago Mercantile Exchange (CME) |
| `USDJPY` | Japanese Yen | `097741` | Chicago Mercantile Exchange (CME) |
| `AUDUSD` | Australian Dollar | `232741` | Chicago Mercantile Exchange (CME) |
| `USDCAD` | Canadian Dollar | `090741` | Chicago Mercantile Exchange (CME) |
| `USDCHF` | Swiss Franc | `092741` | Chicago Mercantile Exchange (CME) |
| `XAUUSD` | Gold (100 Troy Oz) | `088691` | Commodity Exchange (COMEX) |
| `XTIUSD` | WTI Crude Oil (Light Sweet) | `067651` | New York Mercantile Exchange (NYMEX) |
| `XBRUSD` | Brent Crude Oil | `06765T` | Intercontinental Exchange (ICE) |
| `BTCUSD` | Bitcoin Futures | `133741` | Chicago Mercantile Exchange (CME) |

---

## 2. Metrik Analisis Kunci COT

1. **Non-Commercial Net Positioning**: Total Kontrak Long dikurangi Total Kontrak Short dari spekulan besar (Hedge Funds & CTA).
2. **4-Week Net Change ($\Delta_{4\text{W}}$)**: Mengukur arah akselerasi likuiditas spekulatif selama 1 bulan terakhir.
3. **52-Week Percentile Rank ($0\% - 100\%$)**:
   - Nilai $> 85\%$: Posisi spekulan sangat jenuh beli (*crowded long*). Waspadai aksi *long squeeze* / pembalikan arah.
   - Nilai $< 15\%$: Posisi spekulan sangat jenuh jual (*crowded short*). Waspadai aksi *short squeeze* / *short covering*.
   - Nilai $40\% - 60\%$: Posisi netral, ruang pergerakan masih leluasa.
