# WEB-SHELL-HEADER — Header Taskbar   archetype: A10 Shell   audited: it.1

## Lenses A–M
- **A. Hierarki**: Elemen L0 (Mode PAPER/LIVE, status Engine, Drawdown, WS, MT5, Jam) padat dan berada di sticky topbar.
- **B. Arsitektur Informasi**: Mengakomodasi identitas brand, mode sistem, status koneksi, audio, tema, command palette, dan jam. Namun menduplikasi data dengan `GlobalStatusBar` (UX-006).
- **C. Safety & Trust**: Mode badge hadir jelas (`monika-mode-pill`), namun tidak memiliki tombol Emergency Kill Switch seketika (UX-005).
- **D. Tampilan Data**: Menampilkan drawdown dalam format angka tabular. Menggunakan toggle jam UTC/LOC.
- **E. State Komponen**: Status indicator WS & MT5 memiliki tooltip dan status connected/disconnected.
- **F. Aksesibilitas**: Tombol tombol kontrol memiliki `aria-label` yang baik.
- **G. Ergonomi**: Shortcut `⌘K` dan `?` bekerja mulus.
- **H. Responsif**: Menyediakan hamburger toggle `#mobile-nav-toggle` untuk layar sempit `<1024px`.
- **I. Feedback Audio**: Didukung oleh audio synthesizer retro click/toggle.
- **J. Konsistensi Token**: Terdapat 1 pelanggaran font `<11px` (UX-001, glyph pill 9px).
- **K. Retro Authenticity**: Desain tombol mekanis bertingkat 2px outline dengan offset shadow 2px.

## Archetype Rules (A10 Shell)
- L0 safety items present: mode badge ada, tetapi kill switch absen.
- Status bar carries non-duplicated facts: gagal (jam, mode, dan status koneksi terduplikasi dengan status bar).

## Pattern Hunt (P1–P24)
- **P1 Flat Hierarchy**: NONE (Hierarki ukuran jelas, brand → mode pill → engine pill → actions).
- **P2 Zero Semantics**: NONE (Drawdown 0 ditampilkan netral).
- **P3 Safety Context Missing**: FOUND UX-005 (Kill Switch tidak ada di header).
- **P4 Duplicated Facts**: FOUND UX-006 (Mode, MT5/WS, jam terduplikasi di statusbar).
- **P5 Raw Machine Output**: NONE.
- **P6 Time Inconsistency**: FOUND UX-009 (Toggle jam UTC/LOC tanpa sinkronisasi global dengan seluruh tabel data).
- **P7 Stale Data**: FOUND UX-017 (Ketika WS disconnected, indikator berubah merah tapi jam tetap berdetik lokal tanpa peringatan data stale).
- **P8 Truncation**: NONE.
- **P9 State Gaps**: NONE.
- **P10 Repeats**: NONE.
- **P11 Dead Controls**: NONE (Semua tombol header memiliki fungsi).
- **P12 Contrast**: FOUND UX-002 (Teks ink pada kanvas desktop light theme 4.43:1).
- **P13 Type Floor**: FOUND UX-001 (Pill glyph 9px).
- **P14 Target Size**: NONE (Target touch ≥36px).
- **P15 Token Leakage**: NONE.
- **P16 Space Misallocation**: NONE.
- **P17 Sibling Inconsistency**: NONE.
- **P18 Unclear Affordance**: NONE.
- **P19 Responsive Breakage**: NONE.
- **P20 Irreversible Actions**: NONE.
- **P21 Live Updates**: NONE.
- **P22 Data Viz**: NONE.
- **P23 Wayfinding**: NONE.
- **P24 Microcopy**: NONE.

## Evaluasi Tugas Kritis
- **T1: Assess State**: Cepat (≤2s), mode dan drawdown langsung terbaca.
- **T4: Emergency Halt**: GAGAL (Tidak ada tombol halt langsung di header).
