# Reference 05: Deterministic Math, Bracket Invariants & 12-Point RiskGate

Dokumen ini menjelaskan spesifikasi matematika deterministik Monika, pembuatan bounding box harga tanpa mental math, perhitungan ukuran lot berbasis `Decimal` (`ROUND_FLOOR`), dan 12 pemeriksaan pra-eksekusi `RiskGate`.

---

## 1. Bounding Box Invariant & Opsi Bracket Konkret

Untuk menghilangkan kesalahan aritmatika mental dan halusinasi angka pada model LLM, sistem menghitung opsi bracket konkret secara deterministik sebelum agen mengambil keputusan:

### Presisi Desimal Per Aset:
- Pasangan FX Mayor (EURUSD, GBPUSD, AUDUSD, dll.): **5 desimal** (contoh: 1.08542).
- Pasangan JPY (USDJPY, EURJPY, dll.): **3 desimal** (contoh: 154.321).
- Komoditas (XAUUSD, XTIUSD, XBRUSD): **2 desimal** (contoh: 2685.50).
- Kripto (BTCUSD): **1 desimal** (contoh: 88450.5).

### Invarian Jarak Stop Loss & Take Profit:
1. **Lantai Kebisingan Minimum (Noise Floor)**:
   - FX Majors: $\text{SL Distance} \ge 1.25 \times \text{ATR}_{14}$.
   - Aset Volatil (Gold, Minyak, Crypto): $\text{SL Distance} \ge 1.35 \times \text{ATR}_{14}$.
2. **Batas Maksimal Stop Loss (Cap)**:
   - $\text{SL Distance} \le 3.0 \times \text{ATR}_{14}$ dan $\text{SL Distance} \le 1.0 \times \text{ADR}_{5\text{D}}$.
3. **Rasio Risk:Reward Minimum**:
   - $\text{TP Distance} \ge 1.50 \times \text{SL Distance}$ (Target R:R $\ge 1.50$).

---

## 2. Kalkulasi Ukuran Posisi Berbasis Fixed-Fractional `Decimal`

Seluruh operasi perhitungan lot menggunakan pustaka standar Python `decimal.Decimal` yang dibuat dari representasi teks (`str`):

$$\text{Dollar Risk Budget} = \text{Equity} \times \frac{\text{Effective Risk \%}}{100}$$
di mana:
$$\text{Effective Risk \%} = \min(2.0\%, \text{Base Risk \%} \times \text{VIX Mult} \times \text{Judge Mult} \times \text{TTL Mult} \times \text{Synergy Mult})$$

$$\text{SL Distance Pips} = \frac{|\text{Entry} - \text{Stop Loss}|}{\text{Pip Size}}$$

$$\text{Raw Lots} = \frac{\text{Dollar Risk Budget}}{\text{SL Distance Pips} \times \text{Pip Value USD}}$$

### Aturan Pembulatan Wajib:
Ukuran lot **wajib dibulatkan ke bawah (`ROUND_FLOOR`)** ke kelipatan `lot_step` terdekat:
$$\text{Lots} = \text{ROUND\_FLOOR}\left(\frac{\text{Raw Lots}}{\text{Lot Step}}\right) \times \text{Lot Step}$$
> [!IMPORTANT]
> Pembulatan ke atas (*round up*) dilarang keras karena akan menyebabkan risiko kerugian aktual melebihi anggaran risiko yang telah ditetapkan.

---

## 3. Protokol Audit 12-Titik RiskGate

Sebelum order diizinkan untuk dieksekusi, sistem menjalankan 12 pemeriksaan deterministik. Jika **SATU SAJA** gagal, order langsung ditolak (*fail-closed*):

| # | Nama Pengecekan | Kriteria Kelulusan |
|---|---|---|
| 1 | `valid_finite_inputs` | Semua angka terdefinisi, bernilai riil, positif, dan bukan NaN/Inf. |
| 2 | `directional_bracket_ordering` | `SL < Entry < TP` (untuk Buy) atau `TP < Entry < SL` (untuk Sell). |
| 3 | `noise_floor_protection` | Jarak SL $\ge 1.25\times\text{ATR}$ (FX) atau $\ge 1.35\times\text{ATR}$ (Volatil). |
| 4 | `max_stop_cap` | Jarak SL $\le 3.0\times\text{ATR}$ dan $\le 1.0\times\text{ADR}$. |
| 5 | `minimum_rr_ratio` | Rasio R:R terhitung $\ge 1.50$. |
| 6 | `spatial_dealing_range_anti_chasing` | Dilarang Buy jika $pos > 0.85$; dilarang Sell jika $pos < 0.15$. |
| 7 | `daily_drawdown_limit` | Total kerugian harian saat ini $< 3.0\%$ dari ekuitas awal. |
| 8 | `spread_spike_gate` | Spread saat ini $\le 2.0\times$ spread tipikal instrumen. |
| 9 | `rollover_blackout_window` | Jam saat ini di luar jendela rollover `21:55 - 22:15 UTC`. |
| 10 | `event_blackout_window` | Tidak berada dalam jendela rilis berita Tier-1 (-15m s/d +30m). |
| 11 | `systemic_crisis_gate` | VIX $\le 30.0$ dan HY OAS $< 450\text{ bps}$. |
| 12 | `stale_data_verified` | Data pasar segar atau penalti ukuran 50% telah diterapkan. |
