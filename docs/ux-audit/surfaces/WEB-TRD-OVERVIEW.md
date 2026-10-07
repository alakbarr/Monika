# WEB-TRD-OVERVIEW — Trading Desk Overview   archetype: A1 Monitor   audited: it.1

## Lenses A–M
- **A. Hierarki**: L1 Hero (CockpitBar: Daily P&L & Drawdown) → L2 Primary Object (PositionsTable) → L3 Queue (AnalysisGrid) → L4 Stream (ActivityFeed).
- **B. Arsitektur**: Grid 2-kolom: kolom kiri memuat tabel posisi & grid analisis, kolom kanan memuat feed telegraph aktivitas.
- **C. Safety**: Mode paper/live terpapar jelas via Header L0.
- **D. Tampilan Data**: Daily P&L menangani angka 0 dengan semantik netral `FLAT` dan warna abu-abu `ink-soft` (memenuhi P2). Win rate saat 0 trade menampilkan `—` bukan `0.0%` (memenuhi P2).
- **E. State Komponen**: `CockpitBar` memiliki visualisasi segmented progress bar untuk win rate.
- **F. Aksesibilitas**: `ActivityFeed` kekurangan tombol `Pause/Resume` saat streaming (UX-007).
- **G. Ergonomi**: Shortcut keyboard 1-5 beralih antar workspace.
- **H. Responsif**: Di bawah 1024px grid runtuh menjadi 1 kolom.
- **I. Motion/Audio**: Sound click pada tab switch.
- **J. Token**: Kebocoran `color-mix()` di `ActivityFeed.tsx:115` (UX-013).
- **K. Retro Authenticity**: `CockpitBar` menggunakan class `.win-window` tapi tidak memiliki titlebar (UX-015).

## Archetype Rules (A1 Monitor)
- Hero count ≤1 per region: Memenuhi (Daily P&L adalah hero tunggal).
- No fact repeated: Memenuhi.
- Modules sized by value: Memenuhi.
- Empty modules collapse: Posisi tabel memiliki empty state compact.

## Pattern Hunt (P1–P24)
- **P1 Flat Hierarchy**: NONE (Hierarki ukuran 28px hero vs 13px tabel sangat kontras).
- **P2 Zero Semantics**: NONE (FLAT dan — diimplementasikan dengan benar).
- **P3 Safety Context**: NONE.
- **P4 Duplicated Facts**: NONE.
- **P5 Raw Machine Output**: NONE (ActivityFeed memisahkan JSON di balik tombol `[PAYLOAD]`).
- **P6 Time Inconsistency**: NONE.
- **P7 Stale Data**: FOUND UX-017 (Data P&L tidak menampilkan badge STALE saat WS terputus).
- **P8-P12**: NONE.
- **P13 Type Floor**: NONE.
- **P14**: NONE.
- **P15 Token Leakage**: FOUND UX-013 (`color-mix` di ActivityFeed).
- **P16 Space Allocation**: FOUND UX-015 (`CockpitBar` bergaya window tanpa titlebar).
- **P17-P20**: NONE.
- **P21 Live Updates**: FOUND UX-007 (Feed telegraph tidak bisa di-pause).
- **P22-P24**: NONE.

## Evaluasi Tugas Kritis
- **T1: Assess State**: Lulus penuh (P&L, drawdown, status posisi terlihat dalam <3 detik).
