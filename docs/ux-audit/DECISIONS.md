# DECISIONS — Log Keputusan Desain & Arsitektur UI/UX

File ini mencatat seluruh keputusan pemilik (`D-xx`) yang dihasilkan dari wawancara `/grill-me`. Pertanyaan yang sudah tercatat di sini **tidak akan ditanyakan ulang** pada iterasi berikutnya kecuali ada perubahan bukti empiris.

---

## D-01: Penanganan Kontrol Titlebar Jendela Retro [ _ ] [ □ ] [ × ]
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-004 (6 kontrol mati di `BriefTab` dan `BootSequence`), P11 / Lens K.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): Fungsional penuh atau hapus — `_` (collapse body), `□` (maximize viewport), dan `×` hanya pada jendela yang bisa ditutup/modal; hilangkan seluruh tombol dekoratif mati.
  - B: Hanya sediakan `_` dan `□`, hapus `×` pada panel kerja.
  - C: Jadikan titlebar murni statis tanpa tombol kontrol.
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Seluruh jendela menggunakan komponen terstandarisasi `WindowFrame`.
  2. Hapus tag `<span>` tiruan yang mati pada `BriefTab` dan `BootSequence`.
  3. Tombol `×` hanya di-render jika prop `onClose` diberikan secara eksplisit.

---

## D-02: Kebijakan Zona Waktu Resmi (Timezone Policy)
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-009 (Format waktu bercampur antara browser locale, UTC, dan LOC), P6 / Lens D.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): UTC Institusional seragam di seluruh tabel & log dengan label eksplisit UTC/Z, usia relatif di sub-teks (2m ago), dan waktu lokal via hover/tooltip.
  - B: Global toggle tersinkronisasi di Header.
  - C: Dual display berdampingan (UTC / LOC).
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Hapus pemanggilan `toLocaleString()` tanpa timezone di `SignalsTriggersPanel` dan `PositionsTable`.
  2. Seluruh timestamp diformat menggunakan helper seragam `fmt.utc()` dengan label `UTC` atau sufiks `Z`.
  3. Usia relatif (`x ago`) diletakkan di meta baris, dan tooltip menampilkan waktu lokal pengguna.

---

## D-03: Manajemen Antrean & Deduplikasi Sinyal
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-018 (Sinyal identik berulang dan bercampur dengan sinyal expired), A3 / P10.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): Agregasi otomatis sinyal identik dengan badge '×N' dan pindahkan sinyal kadaluarsa ke grup terlipat 'Expired (N) ▸' bergaya dithered.
  - B: Tambahkan tab filter lifecycle eksplisit tanpa agregasi.
  - C: Auto-purge sinyal kadaluarsa dari antrean aktif.
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Di `SignalsTriggersPanel.tsx`, kelompokkan sinyal aktif berdasarkan tuple `(symbol, direction, strategy)`.
  2. Tampilkan badge counter `×N` beserta waktu pertama & terakhir terdeteksi.
  3. Sinyal yang telah melewati TTL dipindahkan ke accordion terlipat "EXPIRED SIGNALS ▸" dengan styling dithered retro.

---

## D-04: Penempatan Tombol Fisik Emergency Kill Switch
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-005 (Kill Switch tidak ada di persistent chrome Header/Statusbar), C / P3 / T4.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): Letakkan di tepi kanan Header Taskbar (Fitts' infinite edge) dengan jarak ≥12px dari tombol lain, dilindungi modal konfirmasi ringkas rincian posisi terbuka.
  - B: Letakkan di tepi kanan Global Status Bar.
  - C: Hadir di kedua tempat (Header dan Status Bar).
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Tambahkan tombol `[ 🚨 EMERGENCY HALT ]` pada tepi paling kanan `Header.tsx` dengan margin kiri ≥12px.
  2. Menekan tombol memicu `ConfirmModal` yang merinci jumlah posisi terbuka dan peringatan likuidasi pasar instan.
  3. Setelah dieksekusi, persistent banner `[ SYSTEM HALTED: TRADING SUSPENDED ]` muncul di atas seluruh workspace dengan panduan resume.
