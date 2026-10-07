# SYSTEM-MAP — Monika AI Quantitative Workstation

## 1. Persona & Konteks Operasional
- **Persona Utama**: Senior Quantitative Trading Operator / Institutional Risk Supervisor.
- **Mental Model**: "Am I safe? What needs me now? What is my exposure?" (Kaidah 3 detik, 0 klik).
- **Karakteristik Operasi**: 95% monitoring tenang, 5% respons insiden bertekanan tinggi. Membutuhkan glanceability tinggi, zero fake precision, data freshness eksplisit, dan perlindungan deterministik terhadap aksi destruktif.

## 2. Lima Tugas Kritis (Critical Tasks)
1. **T1: Assess State (Evaluasi Status & Paparan)**
   - Sasaran: Mengetahui mode (PAPER/LIVE), koneksi broker/WS, P&L harian, dan jarak ke batas drawdown dalam ≤3 detik tanpa klik.
   - Surface Terkait: `WEB-SHELL-HEADER`, `WEB-SHELL-STATUSBAR`, `WEB-TRD-OVERVIEW`, `TUI-DASH-OVERVIEW`.
2. **T2: Respond to Signal (Evaluasi & Respons Sinyal Baru)**
   - Sasaran: Membaca tesis, menilai usia data/confidence, membuka Decision Dossier, mengeksekusi atau mendiskualifikasi sinyal.
   - Surface Terkait: `WEB-TRD-SIGNALS`, `WEB-DLG-DOSSIER`, `TUI-DASH-SIGNALS`.
3. **T3: Place Manual Order (Entri Order Manual & Cek Risiko)**
   - Sasaran: Membuka drawer order manual, memverifikasi margin & pre-trade risk checks, konfirmasi eksekusi via mouse/keyboard.
   - Surface Terkait: `WEB-DRW-MANUAL-ORDER`, `WEB-TRD-POSITIONS`.
4. **T4: Emergency Halt (Aktivasi Kill Switch Seketika)**
   - Sasaran: Menghentikan seluruh perdagangan dan melikuidasi/membekukan posisi dari workspace mana pun via shortcut/tombol dengan konfirmasi eksplisit dan feedback seketika.
   - Surface Terkait: `WEB-SHELL-STATUSBAR`, `WEB-DLG-CONFIRM`, `TUI-DASH-KILLMODAL`.
5. **T5: Diagnose Silence (Diagnosis Ketiadaan Eksekusi)**
   - Sasaran: Menemukan alasan kenapa bot tidak entry (apakah terblokir RiskGate, data feed stale, koneksi putus, atau tidak ada setup lolos) dalam ≤2 navigasi.
   - Surface Terkait: `WEB-INT-GRAPH`, `WEB-INT-DEBATES`, `WEB-LED-RISK`, `WEB-TEL-OBSERVABILITY`, `TUI-DASH-TREE`.

## 3. Technology Stack & Runtime Architecture
- **Web Dashboard**:
  - Runtime: React 19.2, Vite 6.4, TypeScript 5.7.
  - State & Routing: Zustand 4.5 (`dashboardStore.ts`), Tab-based view router (`App.tsx`).
  - Rendering: Recharts 2.15, TradingView Lightweight-Charts 5.2, Xterm.js 6.0 (PTY terminal), Lucide-React.
  - Styling: CSS Variables / Tokens (`tokens.ts`, `index.css`), zero-blur 1990s retro OS window styling.
- **Terminal UI (TUI)**:
  - Runtime: Python 3.12+, Textual (`cli/tui.py`, `cli/tui_chat.py`), Rich console.
  - Platform Layer: `cli/platform_compat.py` (Windows VT mode, UTF-8 enforce, terminal color depth detection).
- **Backend Telemetri**:
  - FastAPI async server, WebSocket live streaming, Polling fallback, PostgreSQL 16+ telemetry store.

## 4. Lokasi Token, Komponen & Aset Kunci
- **Design Tokens**: `trading-agent/logging_observability/dashboard/frontend/src/theme/tokens.ts`
- **Global CSS**: `trading-agent/logging_observability/dashboard/frontend/src/index.css`
- **Design Spec**: `DESIGN.md`
- **Shell Layout**: `trading-agent/logging_observability/dashboard/frontend/src/components/layout/`
- **Panel Components**: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/`
- **UI Primitives**: `trading-agent/logging_observability/dashboard/frontend/src/components/ui/`
- **TUI Source**: `trading-agent/cli/`
