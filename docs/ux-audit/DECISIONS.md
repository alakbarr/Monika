# Design & Architectural Decisions Log (/grill-me)

> **Document Version:** 1.0.0 · Owner Alignment Ledger  
> **Rule:** Only decisions that strictly belong to the system owner (color semantics, information architecture, functional behaviors, safety chrome) are recorded here.

---

## Decision D1: Zero / N-A Value Semantic Presentation
- **Status:** APPROVED (Option A - Netral Murni)
- **Selection:** `$0.00` neutral ink tanpa tanda `+` dan tanpa badge `PROFIT`. Win Rate saat 0 trade tampil `—` (em-dash) dengan bar kosong.

---

## Decision D2: Live Trading Hazard Chrome Transformation
- **Status:** APPROVED (Option A - Active Hazard Chrome)
- **Selection:** Outline topbar dan jendela beralih ke warna koral (`#E25B45`) dengan pinstripe diagonal 45° dan pill `[● LIVE CAPITAL]` menyala permanen saat mode LIVE aktif.

---

## Decision D3: Window Titlebar vs Dedicated Toolbar Separation
- **Status:** APPROVED (Option A - Dua Tingkat Retro Asli)
- **Selection:** Titlebar murni untuk identitas dan kontrol window `[_][□]`. Tombol aksi (`NEW ORDER`, `CLOSE ALL`, unit selector, filter) pindah ke baris toolbar khusus (`.win-toolbar`) setinggi 30px di bawah titlebar.

---

## Decision D4: Window Control Buttons Behavior (`_`, `□`, `×`)
- **Status:** APPROVED (Option A - Kontrol Jujur)
- **Selection:** Window permanen (Ledger, Signals, Telegraph) hanya menampilkan `[_]` (collapse) dan `[□]` (maximize); hapus tombol close `[×]` palsu. Dialog dan drawer tetap memiliki `[×]`.

---

## Decision D5: Display Timezone Policy & Smooth Switcher
- **Status:** APPROVED (User-Configurable Switcher)
- **Selection:** User dapat memilih tampilan waktu dalam `UTC` atau `LOKAL`.
  - **Runtime & Pipeline Safety:** Seluruh data backend, pipeline WebSocket, dan database tetap 100% ISO UTC standar tanpa mutasi data.
  - **Seamless UX:** Header menyediakan quick-toggle interaktif `[UTC ⇄ LOCAL]`. State disimpan di `dashboardStore` (persist ke `localStorage`).
  - **Eksplisit:** Semua stempel waktu menampilkan akhiran zona waktu (misal: `19:25:30 UTC` atau `02:25:30 +07`). Zero ambiguitas saat rilis berita ekonomi.

