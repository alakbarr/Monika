# WEB-SHELL-STATUSBAR — Global Status Bar   archetype: A10 Shell   audited: it.1

## Lenses A–M
- **A. Hierarki**: Bilah horizontal paling bawah layar, berfungsi sebagai L5 Chrome / L0 telemetry.
- **B. Arsitektur Informasi**: Mengulang fakta dari Header (Mode, WS, MT5, Jam).
- **C. Safety & Trust**: Tidak memiliki tombol Kill Switch (UX-005). Hanya menampilkan status Engine Online/Paused.
- **D. Tampilan Data**: Menampilkan posisi terbuka, timestamp heartbeat, VIX regime, WS, MT5, dan jam UTC.
- **E. State Komponen**: Status tag WS/MT5 berubah warna sesuai kondisi koneksi.
- **F. Aksesibilitas**: Menggunakan role="status" dan aria-label="Global Trading Status Bar".
- **G. Ergonomi**: Posisi statis di dasar viewport.
- **H. Responsif**: Menggunakan class `.status-bar-secondary` yang menyembunyikan item sekunder di viewport kecil.
- **I. Motion/Audio**: Statis tanpa animasi.
- **J. Konsistensi Token**: Menggunakan font monospace `tabular-nums`.
- **K. Retro Authenticity**: Pembatas vertikal `│` dan border solid.

## Archetype Rules (A10 Shell)
- L0 safety items: Mode ada, tapi tombol Kill Switch tidak ada.
- Status bar carries non-duplicated facts: GAGAL (duplikasi dengan Header).

## Pattern Hunt (P1–P24)
- **P1 Flat Hierarchy**: NONE.
- **P2 Zero Semantics**: NONE (Jumlah posisi 0 ditampilkan normal).
- **P3 Safety Context**: FOUND UX-005 (Kill Switch tidak ada di footer/statusbar).
- **P4 Duplicated Facts**: FOUND UX-006 (Mode, MT5/WS, jam terduplikasi).
- **P5 Raw Machine Output**: NONE.
- **P6 Time Inconsistency**: NONE (Statusbar menggunakan format eksplisit UTC).
- **P7 Stale Data**: FOUND UX-017 (Heartbeat timestamp tidak berubah menjadi badge 'STALE' ketika koneksi terputus).
- **P8-P11**: NONE.
- **P12 Contrast**: NONE.
- **P13 Type Floor**: NONE (Teks terendah 11px).
- **P14-P24**: NONE.
