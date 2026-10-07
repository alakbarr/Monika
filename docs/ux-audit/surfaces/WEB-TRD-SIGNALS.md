# WEB-TRD-SIGNALS — Signals & Triggers   archetype: A3 Queue   audited: it.1

## Lenses A–M
- **A. Hierarki**: Sub-tabs (SIGNALS & TRIGGERS vs ORDER AUDIT TRAIL) → Kartu Sinyal Kandidat / Tabel Log Order.
- **B. Arsitektur**: Menampilkan sinyal perdagangan yang diproduksi oleh modul kuantitatif dan trigger otomatis (Time stop, TTL expiry, Price level).
- **C. Safety**: Mengintegrasikan `DecisionDossierModal` untuk audit pre-trade thesis dan verifikasi RiskGate sebelum eksekusi.
- **D. Tampilan Data**: Tabel Order Audit Trail memuntahkan raw JSON panjang di kolom PARAMS dan RESULT tanpa expandable summary (UX-008). Menggunakan `toLocaleString()` lokal browser (UX-009).
- **E. State Komponen**: Kartu sinyal memiliki chip lifecycle, namun sinyal expired tidak dikelompokkan ke grup terlipat (UX-018).
- **F. Aksesibilitas**: Warna badge price level menggunakan raw string `'cyan'` yang gagal kontras (UX-013).
- **G. Ergonomi**: Kartu sinyal belum mendukung shortcut keyboard j/k untuk navigasi cepat.
- **H. Responsif**: Kartu sinyal menggunakan grid CSS fleksibel.
- **I. Feedback**: Klik dossier membuka modal instan.
- **J. Token**: Menggunakan raw `cyan` dan `color-mix()` (UX-013).
- **K. Retro Authenticity**: Header tab menggunakan Card kustom tanpa WindowFrame standar retro.

## Archetype Rules (A3 Queue)
- Lifecycle states visible: Sebagian (status ada tapi expired tidak dipisahkan ke grup collapsed).
- Dedupe/group: GAGAL (sinyal identik berulang tanpa badge `×2` atau agregasi).
- Human summary first, payload expandable: GAGAL di Order Audit Trail (memuntahkan raw JSON).

## Pattern Hunt (P1–P24)
- **P1-P4**: NONE.
- **P5 Raw Machine Output**: FOUND UX-008 (Raw JSON di kolom tabel audit order).
- **P6 Time Inconsistency**: FOUND UX-009 (`toLocaleString` di baris order).
- **P7 Stale Data**: FOUND UX-017 (Sinyal tidak menunjukkan status expired/stale secara dithered).
- **P8 Truncation**: NONE.
- **P9 State Gaps**: NONE.
- **P10 Repeats Not Deduped**: FOUND UX-018 (Sinyal identik tidak dikelompokkan).
- **P11 Dead Controls**: NONE.
- **P12 Contrast**: FOUND UX-013 (`cyan` text on light paper).
- **P13 Type Floor**: NONE.
- **P14-P15**: FOUND UX-013 (`color-mix` dan `cyan`).
- **P16-P24**: NONE.

## Evaluasi Tugas Kritis
- **T2: Respond to New Signal**: Berfungsi via klik ke `DecisionDossierModal`, namun terhambat keterbacaan akibat ketiadaan deduplikasi sinyal berulang.
