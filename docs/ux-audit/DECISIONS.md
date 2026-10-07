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

---

## D-05: Penanganan L0 Safety Mode Pill di Header Taskbar
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-019 (Mode Paper/Live hanya ada di statusbar bawah, tidak terlihat di Header taskbar atas), Lens C / P3.
- **Opsi Dipertimbangkan**:
  - A: L0 Mode Pill permanen dengan border hazard retro 2px dithered/coral pada chrome taskbar saat LIVE.
  - B (Dipilih): Tampilkan pill teks ringkas `[ PAPER ]` / `[ LIVE ]` di Header tanpa garis hazard khusus pada bingkai taskbar.
  - C: Tambahkan banner ribbon kuning/merah 20px terdedikasi di bawah Header saat LIVE.
- **Keputusan**: **Opsi B** (Owner).
- **Konsekuensi Implementasi**:
  1. Tambahkan L0 Mode Pill ringkas di sebelah kiri `Header.tsx` samping logo: `[ 🟢 PAPER ]` atau `[ 🔴 LIVE ]`.
  2. Tanpa border hazard pada seluruh frame; cukup visual pill yang jelas dan akurat terhadap `tradingMode`.

---

## D-06: Hierarki Tipografi L1 Hero Net Daily P&L di CockpitBar
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-020 (Net P&L Cockpit hanya 17px, setara metrik sekunder, gagal squint test L1 primacy), Lens A / P16.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): Tingkatkan Net P&L menjadi L1 Display Numeral 28px (font-precision bold tabular) dengan label stacked di atas 'NET DAILY P&L' (11px caps), dan kelompokkan metrik sekunder ke recessed instrument well tersendiri.
  - B: Tingkatkan menjadi 22px tetap satu baris.
  - C: Pertahankan ukuran seragam 16px.
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Di `CockpitBar.tsx`, hero number Net Daily P&L diatur ke font 28px `fontFamily: 'var(--font-precision)'`, `fontWeight: 800`.
  2. Label `NET DAILY P&L` diletakkan di atas hero value dengan ukuran 11px uppercase `var(--color-ink-muted)`.
  3. Metrik sekunder (Win Rate, Exposure, Sharpe) dikelompokkan dalam recessed well terpisah di sebelah kanan.

---

## D-07: Alokasi Ruang & Compact Ribbon saat Ledger Posisi Kosong
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-022 (Empty state tabel posisi memakan ~170px, mendesak sinyal dan feed ke bawah lipatan layar), Lens A / P16.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): Kolaps badan tabel menjadi compact ribbon ~44px ('LEDGER CLEAR // 0 OPEN EXPOSURE' + tombol '+ NEW ORDER') saat kosong; luaskan otomatis ke tabel grid penuh saat ada posisi aktif.
  - B: Header tabel penuh dengan 1 baris kosong ~36px.
  - C: Pertahankan kotak empty state tinggi ~170px.
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Di `PositionsTable.tsx`, jika `openPositions.length === 0`, render compact sunken ribbon baris tunggal setinggi ~44px dengan teks `LEDGER CLEAR // NO OPEN EXPOSURE` dan tombol aksi cepat `[ + NEW ORDER ]`.
  2. Jika `openPositions.length > 0`, render tabel lengkap dengan pagination, sorting, dan pinned footer totals.

---

## D-08: Tata Letak Responsif TUI 80×24 & Function-Key Bar
- **Tanggal**: 2026-10-07
- **Dasar Temuan**: UX-024 (Pada terminal 80×24, split horizontal tui.py terpotong dan tidak ada panduan tombol fungsi F-keys), Lens M / P17.
- **Opsi Dipertimbangkan**:
  - A (Dipilih): Pada lebar <100 kolom, susun panel secara bertumpuk (stacked) agar tidak terpotong, serta tambahkan persistent Function-Key Bar bergaya retro di baris paling bawah: [F1 Help] [F2 Desk] [F3 Intel] [F8 Pause] [F9 Kill] [F10 Quit].
  - B: Hanya tambahkan F-Key bar tanpa layout adaptif.
  - C: Pertahankan status quo.
- **Keputusan**: **Opsi A** (Owner).
- **Konsekuensi Implementasi**:
  1. Di `trading-agent/cli/tui.py`, deteksi lebar terminal dan susun panel overview secara vertikal jika kolom < 100.
  2. Tambahkan persistent bottom strip widget `FunctionKeyBar` berisi panduan shortcut F1 s.d. F10 bergaya Norton Commander / DOS.

