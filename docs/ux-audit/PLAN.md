# PLAN — Rencana Implementasi Delta Bebas Debt

Rencana kerja terstruktur hasil audit Iterasi 1 dan keputusan `/grill-me` (D-01 s.d. D-04). Setiap task memiliki referensi temuan terverifikasi, file target, tindakan terukur, dan gerbang verifikasi.

---

## Milestone 0 (M0): Fondasi, Token Integrity & Tipografi
- **M0-01 (UX-001): Type Floor Enforcement**
  - *Files*: `trading-agent/logging_observability/dashboard/frontend/src/index.css`, `CandlestickChart.tsx`, `FactorHeatmap.tsx`, `BreadcrumbBar.tsx`, `Sidebar.tsx`, `AgentChatPanel.tsx`, `GraphInspector.tsx`.
  - *Action*: Tingkatkan seluruh font berukuran `<11px` (8px, 9px, 10px, 10.5px) menjadi minimal `11px` (untuk label kapital/caps) atau `12px` (untuk angka/data).
  - *Verify Gate*: G3 (Hasil `python scripts/ux_audit_baseline_scan.py` harus 0 pelanggaran).
- **M0-02 (UX-002): Perbaikan Kontras WCAG 2.2 AA**
  - *Files*: `src/index.css`, `src/theme/tokens.ts`.
  - *Action*:
    1. Perbaiki warna teks di atas desktop canvas light (`#877F75`): gunakan panel background atau kontraskan warna kanvas.
    2. Tingkatkan kontras outline gelap pada canvas dark: ubah `--color-edge` menjadi minimal 3.0:1.
    3. Sesuaikan token `--color-profit` dan `--color-loss` saat di atas surface sunken `--color-paper-sunken` agar mencapai ≥4.5:1.
  - *Verify Gate*: G2 (Semua pasangan di `contrast_check.py` berstatus `PASS`).
- **M0-03 (UX-003): Eliminasi Raw Hex Leakage**
  - *Files*: Seluruh file di `src/components/charts/` dan `src/components/panels/`.
  - *Action*: Migrasi 225 raw hex menjadi token CSS variables (`var(--color-profit)`, `var(--color-loss)`, `var(--color-ink)`, dll.).
  - *Verify Gate*: G1 (0 raw hex di luar `tokens.ts` dan `index.css`).
- **M0-04 (UX-009, D-02): Standarisasi Formatter UTC**
  - *Files*: `src/lib/formatters.ts`, `SignalsTriggersPanel.tsx`, `PositionsTable.tsx`.
  - *Action*: Buat fungsi `fmt.utc()` institusional terpusat. Hapus pemanggilan `toLocaleString()` lokal tanpa zona waktu.
  - *Verify Gate*: G12.
- **M0-05 (UX-013): Pembersihan Modern CSS Leakage**
  - *Files*: `SignalsTriggersPanel.tsx`, `PositionsTable.tsx`, `ActivityFeed.tsx`.
  - *Action*: Hapus seluruh penggunaan `color-mix()` dan raw string `'cyan'`, ganti dengan token retro resmi (`var(--color-win-blue)`, `var(--color-paper-subtle)`).
  - *Verify Gate*: G1.

---

## Milestone 1 (M1): Komponen Inti & Safety Fortress
- **M1-01 (UX-004, D-01): Standardisasi Titlebar WindowFrame & Eliminasi Dead Buttons**
  - *Files*: `src/components/ui/WindowFrame.tsx`, `src/App.tsx`, `src/components/ui/BootSequence.tsx`.
  - *Action*: Hapus kontrol mati `<span>` pada `BriefTab` dan `BootSequence`. Pastikan tombol `_` dan `□` berfungsi konsisten di seluruh jendela; tombol `×` hanya tampil jika `onClose` didefinisikan.
  - *Verify Gate*: G4, G13.
- **M1-02 (UX-005, D-04): Integrasi Persistent Emergency Kill Switch**
  - *Files*: `src/components/layout/Header.tsx`.
  - *Action*: Tambahkan tombol fisik `[ 🚨 EMERGENCY HALT ]` pada tepi paling kanan Header Taskbar (Fitts' edge) dengan margin kiri ≥12px. Hubungkan ke `ConfirmModal` darurat untuk memvalidasi likuidasi posisi terbuka MT5.
  - *Verify Gate*: G7, G12 (Tugas Kritis T4 terverifikasi 0-klik akses dari semua workspace).
- **M1-03 (UX-006): Eliminasi Duplikasi Chrome Header vs Statusbar**
  - *Files*: `src/components/layout/Header.tsx`, `src/components/layout/GlobalStatusBar.tsx`.
  - *Action*: Header mempertahankan L0 Safety Mode Pill dan jam interaktif; Statusbar mempertahankan ringkasan status engine, posisi aktif, dan heartbeat telemetri. Hapus duplikasi titik WS/MT5 dan jam ganda.
  - *Verify Gate*: G12.
- **M1-04 (UX-010): Otentisitas Retro Focus Pinstripes & Elevasi**
  - *Files*: `src/components/ui/WindowFrame.tsx`, `src/index.css`.
  - *Action*: Implementasikan efek pinstripes retro pada titlebar jendela aktif (`data-focused="true"`) menggunakan repeating linear gradient dengan spacer flex, dan bayangan terangkat `--shadow-elevated`.
  - *Verify Gate*: G12.
- **M1-05 (UX-011): Perbaikan React Rules-of-Hooks pada DecisionDossierModal**
  - *Files*: `src/components/panels/DecisionDossierModal.tsx`.
  - *Action*: Pindahkan `React.useEffect` penanganan tombol Escape ke atas sebelum percabangan early return `if (!isOpen) return null;`.
  - *Verify Gate*: `npm run lint` (`oxlint` 0 errors).
- **M1-06 (UX-017): Status Visual STALE & Dither saat Disconnected**
  - *Files*: `src/store/dashboardStore.ts`, `src/components/panels/CockpitBar.tsx`, `src/components/panels/PositionsTable.tsx`.
  - *Action*: Saat `wsConnected: false`, tampilkan badge `[ STALE FEED ]` dengan styling dithered retro dan teks "last known" pada harga dan P&L.
  - *Verify Gate*: G12.

---

## Milestone 2 (M2): Tata Letak Workspace & Ergonomi Data
- **M2-01 (UX-008): Disclosure Rapi pada Order Audit Trail**
  - *Files*: `src/components/panels/SignalsTriggersPanel.tsx`.
  - *Action*: Sembunyikan raw JSON params/result di balik tombol expandable `[PAYLOAD]` yang membuka sunken mono well.
  - *Verify Gate*: G12.
- **M2-02 (UX-012): Penyelarasan Header Tabel Posisi & Pinned Totals**
  - *Files*: `src/components/panels/PositionsTable.tsx`.
  - *Action*: Kolom numerik (Volume, Entry, Market, SL, TP, Swap, P&L) menggunakan header rata kanan (`textAlign: 'right'`), tambahkan atribut `aria-sort`, dan tambahkan baris total tersemat (pinned totals row) di bagian bawah.
  - *Verify Gate*: G12.
- **M2-03 (UX-015): Penyelarasan CockpitBar sebagai Well/Toolbar Terstandarisasi**
  - *Files*: `src/components/panels/CockpitBar.tsx`.
  - *Action*: Hilangkan kelas tiruan `.win-window` jika tanpa titlebar, jadikan komponen ini sebagai sunken instrument well terpadu atau lengkapi dengan titlebar kategorikal `INSTRUMENT CLUSTER`.
  - *Verify Gate*: G12.
- **M2-04 (UX-018, D-03): Deduplikasi Sinyal & Grup Terlipat Expired**
  - *Files*: `src/components/panels/SignalsTriggersPanel.tsx`.
  - *Action*: Agregasi sinyal identik berulang dengan badge `×N`. Pindahkan sinyal yang telah melewati TTL ke grup terlipat `[ EXPIRED SIGNALS (N) ▸ ]` bergaya dithered.
  - *Verify Gate*: G12.

---

## Milestone 3 (M3): State Streams & Aksesibilitas
- **M3-01 (UX-007): Kontrol Pause / Resume pada Stream Log Telegraph**
  - *Files*: `src/components/panels/ActivityFeed.tsx`, `src/components/panels/ObservabilityPanel.tsx`.
  - *Action*: Tambahkan tombol `[ ⏸ PAUSE STREAM ]` / `[ ▶ RESUME ]` di toolbar telegraph (memenuhi WCAG 2.2.2).
  - *Verify Gate*: G6, G7.
- **M3-02 (UX-016): Inverted Selection & Navigasi Keyboard Baris**
  - *Files*: `src/components/panels/PositionsTable.tsx`, `src/index.css`.
  - *Action*: Dukung navigasi baris `j`/`k` / panah keyboard dengan seleksi terbalik retro (`background: var(--color-ink); color: var(--color-paper-raised);`).
  - *Verify Gate*: G7.

---

## Milestone 4 (M4): Polish & Ergonomi TUI
- **M4-01 (UX-014): Penyelarasan Tema Retro TUI**
  - *Files*: `trading-agent/cli/theme.py`.
  - *Action*: Bersihkan warna indigo `#818CF8` dan slate modern dari preset `modern_dark`, selaraskan menjadi skema CRT phosphor amber / obsidian retro.
  - *Verify Gate*: G11, `pytest trading-agent/tests/cli -v`.

---

## Milestone 5 (M5): Hardening, Verifikasi Gates & Dokumentasi
- **M5-01**: Eksekusi seluruh gerbang verifikasi (G1 scan, G2 contrast, G3 type floor, G4 affordance, oxlint, build, dan pytest).
- **M5-02**: Sinkronisasi dokumentasi `INDEX.md`, `STRUCTURE.md`, dan eksekusi `python scripts/update_index_toc.py`.
