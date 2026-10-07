# WEB-TRD-POSITIONS — Position Ledger   archetype: A2 Ledger   audited: it.1

## Lenses A–M
- **A. Hierarki**: Toolbar jendela (Toggle Open/Closed, Filter, Unit PnL USD/PIPS/R, Bulk BE, Close All) → Header Kolom Sticky → Baris Posisi.
- **B. Arsitektur**: Menampilkan seluruh tiket posisi aktif MetaTrader 5 dengan data kuantitatif lengkap.
- **C. Safety**: Tombol "CLOSE ALL" memicu modal konfirmasi darurat `ConfirmModal` (T4). Tombol modify SL/TP memiliki modal edit.
- **D. Tampilan Data**: Header tabel posisi seluruhnya rata kiri, padahal kolom numerik (Lots, Entry, SL, TP, PnL) harus rata kanan (UX-012). Tidak ada baris total permanen (pinned totals).
- **E. State Komponen**: Memiliki state loading (skeleton), empty compact (`[ LEDGER CLEAR ]`), dan populated.
- **F. Aksesibilitas**: Header tidak memiliki atribut `aria-sort` (UX-012).
- **G. Ergonomi**: Tidak ada navigasi seleksi baris keyboard (j/k) (UX-016).
- **H. Responsif**: Tabel dibungkus dalam `.table-responsive` dengan scroll horizontal jika viewport sempit.
- **I. Feedback**: Tombol aksi memicu efek suara audio typewriter.
- **J. Token**: Menggunakan `color-mix()` pada sticky header (UX-013).
- **K. Retro Authenticity**: WindowFrame memiliki kontrol collapse dan minimize fungsional.

## Archetype Rules (A2 Ledger)
- Right-aligned tabular numerals: GAGAL (Header kolom numerik rata kiri).
- Sort indicator + aria-sort: Sebagian (indikator visual ada, `aria-sort` tidak ada).
- Selection = inverted row: GAGAL (belum ada model seleksi keyboard terbalik).
- Totals pinned: GAGAL (tidak ada baris ringkasan total di bawah tabel).

## Pattern Hunt (P1–P24)
- **P1 Flat Hierarchy**: FOUND UX-012 (Header tabel rata kiri dan tidak ada totals row).
- **P2-P10**: NONE.
- **P11 Dead Controls**: NONE (Semua tombol tabel aktif).
- **P12 Contrast**: NONE.
- **P13 Type Floor**: NONE.
- **P14 Keyboard Focus**: FOUND UX-016 (Navigasi keyboard j/k baris belum diimplementasikan).
- **P15 Token Leakage**: FOUND UX-013 (`color-mix` di thead).
- **P16-P24**: NONE.

## Evaluasi Tugas Kritis
- **T1: Assess Exposure**: Posisi aktif langsung terlihat dengan volume dan floating P&L.
- **T3: Manual Order Entry**: Didukung via tombol "Manual Order" yang membuka `ManualOrderDrawer`.
