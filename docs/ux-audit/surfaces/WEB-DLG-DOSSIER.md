# WEB-DLG-DOSSIER — Decision Dossier Modal   archetype: A9 Overlay / A4 Reading   audited: it.1

## Lenses A–M
- **A. Hierarki**: Header Modal (Judul, Simbol, Keputusan, Confidence) → 5 Stage Cards (Stage 1 Macro, Stage 2 Tactical, Stage 3 Debate, Stage 4 RiskGate, Stage 5 Execution Telemetry) → Footer Aksi (Copy Receipt, Export JSON, Close).
- **B. Arsitektur Informasi**: Sangat komprehensif, memetakan seluruh siklus hidup pemikiran multi-agen dari awal hingga tiket MT5.
- **C. Safety & Trust**: Menyediakan SHA-256 chain cryptographic verification untuk membuktikan integritas rantai reasoning tanpa manipulasi.
- **D. Tampilan Data**: Menampilkan confidence percentage, R:R, harga SL/TP terverifikasi.
- **E. State Komponen**: GAGAL: Terjadi pelanggaran React Rules of Hooks di `DecisionDossierModal.tsx:141` akibat pemanggilan `React.useEffect` setelah early return `if (!isOpen) return null;` (UX-011).
- **F. Aksesibilitas**: Menggunakan role="dialog", aria-modal="true", dan listener tombol Escape.
- **G. Ergonomi**: Tombol "Copy Receipt" memformat ringkasan teks terstruktur rapi ke clipboard operator.
- **H. Responsif**: Max-width dibatasi pada 920px dengan max-height `90vh` dan overflow scroll vertikal.
- **I. Feedback**: Tombol salin memberikan konfirmasi visual `[COPIED!]` selama 2.5 detik.
- **J. Token**: Menggunakan token CSS yang rapi.
- **K. Retro Authenticity**: Window titlebar bernuansa retro dengan aksen categorical salmon/yellow.

## Archetype Rules (A9 Overlay)
- Purpose line → consequences → actions: Memenuhi.
- Focus trap / return: Sebagian (Escape menutup modal, focus trap belum sempurna).
- Esc closes: Ada listener keydown.

## Pattern Hunt (P1–P24)
- **P1-P10**: NONE.
- **P11 Dead Controls**: NONE.
- **P12 Contrast**: NONE.
- **P13 Type Floor**: NONE.
- **P14-P17**: NONE.
- **P18 Unclear Affordance / Hook Bug**: FOUND UX-011 (React Hook dipanggil secara kondisional).
- **P19-P24**: NONE.

## Evaluasi Tugas Kritis
- **T2: Respond to New Signal**: Berfungsi sangat baik sebagai dokumen justifikasi perdagangan.
