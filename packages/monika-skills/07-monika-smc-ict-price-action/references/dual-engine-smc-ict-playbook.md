# Reference: Dual-Engine SMC/ICT Playbook

Dokumen ini merinci arsitektur eksekusi Engine 1 (Trend Continuation / POI Retest) dan Engine 2 (Turtle Soup Liquidity Sweep).

---

## 1. Engine 1: Trend Continuation & POI Retest

- **Kondisi Aktivasi**:
  - Tren time frame tinggi (D1 & H4) berada dalam momentum ekspansi yang sehat.
  - Nilai $pos$ berada di zona Discount (untuk Buy) atau Premium (untuk Sell).
  - Skor Priced-In $< 7.0$ (aliran likuiditas belum jenuh).
- **Kriteria Setup**:
  1. Identifikasi *Displacement Candle* yang menciptakan Order Block (OB) atau Fair Value Gap (FVG) baru.
  2. Tunggu harga melakukan *retracement* masuk ke area FVG/OB.
  3. Konfirmasi reaksi penolakan harga (*rejection candle*) pada time frame H1 atau M15 sebelum penempatan order limit/market.

---

## 2. Engine 2: Turtle Soup Liquidity Sweep + MSS

- **Kondisi Aktivasi**:
  - Tren sebelumnya mengalami perlambatan momentum atau skor Priced-In $\ge 8.0$.
  - Posisi spekulan COT berada di atas persentil ke-85 atau di bawah persentil ke-15.
- **Kriteria Setup**:
  1. **Liquidity Pool Target**: Identifikasi likuiditas beli di atas Previous Day High (PDH) / Equal Highs, atau likuiditas jual di bawah Previous Day Low (PDL) / Equal Lows.
  2. **The Sweep**: Harga menembus level likuiditas tersebut dengan ekor candle panjang (*wick sweep*) di mana body candle gagal ditutup di luar level tersebut.
  3. **Market Structure Shift (MSS)**: Amati pergeseran struktur mikro pada candle M15 yang menembus *swing point* terdekat.
  4. **Entri Retest**: Masuk berlawanan arah pada FVG yang ditinggalkan oleh pergerakan MSS.
