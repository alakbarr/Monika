# Reference: 3-Phase Post-Event Orderflow Absorption Playbook

Dokumen ini memuat diagram alur teknis dan aturan eksekusi 3 fase penyerapan rilis berita ekonomi berdampak tinggi (Tier-1).

---

## 1. Diagram Alur 3-Fase

```
Rilis Berita Tier-1 (T = 0)
        │
        ▼
[Phase 1: 0 - 15m] ───> STRICT EXECUTION BLACKOUT (No Trades Allowed)
        │
        ▼
[Phase 2: 15 - 60m] ──> Konstruksi Event Anchor Range:
                        - Event High
                        - Event Low
                        - Event Midpoint (50%)
        │
        ▼
[Phase 3: 1 - 4h] ────> Evaluasi Reaksi Likuiditas:
                        ├─> Structural Acceptance (2x M15 Close di luar range + Retest) ──> TRADE BREAKOUT
                        └─> Liquidity Sweep & Fade (Wick >50% + Close kembali ke range) ──> TRADE REVERSAL
```

---

## 2. Parameter Filter Validasi Eksekusi

1. **Volume Ratio Filter**:
   - Candle konfirmasi pada Fase 3 wajib memiliki volume transaksi minimal $1.5\times$ rata-rata volume 20-bar untuk menghindari *bull/bear trap*.
2. **Kondisi Invalidasi Range**:
   - Jika rentang *Event Anchor Range* melebihi $2.5\times\text{ATR}$ harian, pasar berada dalam status dislokasi harga ekstrem. Batalkan eksekusi hingga hari perdagangan berikutnya.
