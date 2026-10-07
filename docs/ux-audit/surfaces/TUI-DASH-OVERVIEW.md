# TUI-DASH-OVERVIEW — Terminal TUI Overview   archetype: A1 Monitor   audited: it.1

## Lenses A–M
- **A. Hierarki**: Top LiveTickerBanner (simbol, harga, panah tren, sparkline) → Body Split (PositionsTable + ActivityLog + Macro/Rates) → Bottom StatusBar (context gauge, tokens, WS, latency) → Footer (Key hints).
- **B. Arsitektur Informasi**: Mengikuti kaidah monitor terminal multi-pane.
- **C. Safety**: Tombol `k` membuka `KillConfirmModalScreen` seketika. Menampilkan status `[EMERGENCY]`, `[ACTIVE]`, `[WARNING]`, `[OFFLINE]`.
- **D. Tampilan Data**: Menggunakan unicode braille sparklines untuk visualisasi PnL & VIX.
- **E. State Komponen**: Menangani empty quotes feed ("AWAITING ACTIVE TICK DATA...").
- **F. Aksesibilitas**: Menyediakan theme `high_contrast` dan mendeteksi variabel lingkungan `NO_COLOR`.
- **G. Ergonomi**: Navigasi keyboard penuh (`Tab`, `p` pause, `k` kill, `r` refresh, `c` chat).
- **H. Responsif Terminal**: Menerapkan dynamic progressive width budget (`width_budget.py`): pada terminal sempit `< 90 cols`, kolom sekunder (ID, Type, SL, TP) otomatis dihilangkan demi mempertahankan visibilitas Symbol, Side, Lots, Entry, PnL.
- **I. Feedback**: Toast notifications saat data diperbarui atau aksi dieksekusi.
- **J. Konsistensi Token**: Preset tema `modern_dark` membawa warna indigo dan slate modern yang melanggar aturan tema retro-vintage terkunci (UX-014).
- **K. Retro Authenticity**: Otentik terminal CRT dengan karakter ANSI/Braille.

## Archetype Rules (A11 TUI)
- Min size behavior: Adaptif dengan pemangkasan kolom di bawah 90 cols.
- Color tiers: Mendukung truecolor, 256, 16, dan NO_COLOR.
- Focus without color: Menggunakan border penunjuk kursor aktif.
- Safety parity: Lulus penuh (Emergency kill switch modal tersedia via shortcut `k`).

## Pattern Hunt (P1–P24)
- **P1-P13**: NONE.
- **P14 Focus Indicator**: NONE.
- **P15 Token Leakage**: FOUND UX-014 (Aksen indigo `#818CF8` pada preset modern_dark).
- **P16-P24**: NONE.

## Evaluasi Tugas Kritis
- **T1: Assess State**: Lulus dalam terminal SSH (harga, posisi, VIX, PnL langsung terlihat).
- **T4: Emergency Halt**: Lulus penuh (Tekan `k` → muncul modal konfirmasi darurat dengan rincian likuidasi).
