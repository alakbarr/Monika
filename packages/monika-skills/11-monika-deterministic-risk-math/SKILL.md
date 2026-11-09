---
name: monika-deterministic-risk-math
description: Pure deterministic mathematical fortress for algorithmic trading: Pre-computed zero-arithmetic price brackets (LONG_OPTION_A / SHORT_OPTION_B), fixed-fractional decimal.Decimal (ROUND_FLOOR) position sizing, and 12-point RiskGate pre-execution auditing.
version: 1.0.0
tags: [trading, risk-management, math, position-sizing, decimal, risk-gate, brackets]
---

# Monika Deterministic Risk Math & Mechanical Fortress Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Zero-Mental-Arithmetic Bracket Invariant

Untuk mencegah halusinasi angka dan kesalahan floating-point pada LLM, sistem menghitung opsi bracket konkret secara deterministik sebelum agen mengambil keputusan:

### Presisi Desimal Per Aset:
- Pasangan FX Mayor (EURUSD, GBPUSD, AUDUSD, dll.): **5 desimal** (contoh: 1.08500).
- Pasangan JPY (USDJPY, EURJPY, dll.): **3 desimal** (contoh: 154.250).
- Komoditas (XAUUSD, XTIUSD, XBRUSD): **2 desimal** (contoh: 2685.50).
- Kripto (BTCUSD): **1 desimal** (contoh: 88450.0).

### Invarian Bounding Box:
- **Lantai Kebisingan (Noise Floor)**: $\text{SL Distance} \ge 1.25\times\text{ATR}$ (FX) atau $\ge 1.35\times\text{ATR}$ (Aset Volatil / Komoditas / Kripto).
- **Maksimal Stop Cap**: $\text{SL Distance} \le 3.0\times\text{ATR}$ dan $\le 1.0\times\text{ADR}$.
- **Target Rasio R:R**: $\text{TP Distance} \ge 1.50\times\text{SL Distance}$ (Target default $\ge 1.80$).

Dapatkan bracket konkret via CLI:
```bash
python scripts/monika_quant_engine.py brackets --symbol EURUSD --price 1.08500 --atr14 0.00400 --adr5d 0.00800
```

---

## 2. Kalkulasi Ukuran Posisi Berbasis Fixed-Fractional `Decimal`

Seluruh operasi perhitungan ukuran lot menggunakan pustaka Python `decimal.Decimal`:

$$\text{Dollar Risk Budget} = \text{Equity} \times \frac{\text{Effective Risk \%}}{100}$$
di mana:
$$\text{Effective Risk \%} = \min(2.0\%, \text{Base Risk \%} \times \text{VIX Mult} \times \text{Judge Mult} \times \text{TTL Mult} \times \text{Synergy Mult})$$

$$\text{Raw Lots} = \frac{\text{Dollar Risk Budget}}{\text{SL Distance (pips)} \times \text{Pip Value USD}}$$

### Aturan Pembulatan Wajib:
Ukuran lot **wajib dibulatkan ke bawah (`ROUND_FLOOR`)** ke kelipatan `lot_step` terdekat:
$$\text{Lots} = \text{ROUND\_FLOOR}\left(\frac{\text{Raw Lots}}{\text{Lot Step}}\right) \times \text{Lot Step}$$
> [!IMPORTANT]
> Pembulatan ke atas (*round up*) dilarang keras karena akan menyebabkan risiko kerugian aktual melebihi anggaran risiko yang telah ditetapkan.

Hitung ukuran lot presisi via CLI:
```bash
python scripts/monika_quant_engine.py size --equity 10000 --base-risk-pct 1.0 --entry 1.08500 --sl 1.08000 --symbol EURUSD
```

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

Jalankan audit 12-titik via CLI:
```bash
python scripts/monika_quant_engine.py risk-gate --symbol EURUSD --direction buy --entry 1.08500 --sl 1.08000 --tp 1.09400 --atr14 0.00400 --adr5d 0.00800 --pos 0.25 --equity 10000
```
