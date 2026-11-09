# Reference: Session Killzones & Post-Event Orderflow Absorption

Dokumen ini menjelaskan jadwal siklus likuiditas sesi global, mekanisme manipulasi Judas Swing, dan protokol penyerapan volatilitas 3 fase.

---

## 1. Jadwal Sesi Global & Karakteristik Orderflow

| Sesi / Jendela | Waktu (UTC) | Karakteristik Utama | Tindakan Trader |
|---|---|---|---|
| **Tokyo Session** | 00:00 - 06:00 | Volatilitas rendah di EUR/GBP, fokus pada JPY dan AUD | Range trading atau ikuti tren Asia untuk pasangan Asia |
| **London Open** | 07:00 - 10:00 | Peningkatan volume tajam, pembentukan range harian | Pantau sapuan likuiditas sesi Asia |
| **Judas Swing Alert** | 07:00 - 08:30 | Manipulasi awal oleh institusi untuk memancing breakout palsu | Tunggu sweep batas range Asia + konfirmasi MSS |
| **London-NY Overlap** | 12:00 - 16:00 | Likuiditas puncak harian pasar finansial global | Window terbaik untuk eksekusi breakout & trend continuation |
| **NY Afternoon** | 16:00 - 20:00 | London Fix pada 16:00 UTC, volume melandai setelah 18:00 | Hindari entri baru setelah 18:00 UTC |
| **Rollover Blackout** | 21:55 - 22:15 | Penutupan buku harian perbankan, spread melonjak 5x-15x | **HARD BLOCK: Dilarang eksekusi order** |

---

## 2. Protokol 3-Fase Pasca-Rilis Berita Tier-1

1. **Phase 1: Strict Blackout (`0 - 15m`)**:
   - Dilarang membuka posisi baru.
   - Spread melebar ekstrem dan risiko slippage unhedged sangat tinggi.
2. **Phase 2: Event Anchor Range (`15 - 60m`)**:
   - Catat `Event High`, `Event Low`, dan `Event Midpoint (50%)`.
   - Amati reaksi likuiditas pada batas-batas range ini.
3. **Phase 3: Acceptance vs. Sweep (`1 - 4h`)**:
   - **Acceptance**: Harga bertahan dan ditutup di luar range $\rightarrow$ Ikuti ekspansi tren baru.
   - **Sweep & Fade**: Terjadi penolakan dengan ekor panjang $>50\%$ dan candle ditutup kembali ke dalam range $\rightarrow$ Eksekusi pembalikan arah (*fade the sweep*).
