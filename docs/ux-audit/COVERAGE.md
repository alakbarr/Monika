# COVERAGE — Matriks Evaluasi & Audit Bukti Terukur

Matriks surface × tema × viewport × state. Setiap sel berstatus:
- `✓it1` : Sudah diaudit berbukti pada Iterasi 1
- `–` : Belum diaudit pada siklus aktif
- `N/A:<alasan>` : Tidak berlaku dengan alasan arsitektural/keputusan terdokumentasi

| Surface ID | Light | Dark | 1920 | 1440 | 1280 | 1024 | 768 | 390 | Populated | Empty | Loading | Error | Stale | Kbd-Only | WCAG/Axe | Metrics/Code |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **WEB-SHELL-HEADER** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001, UX-005, UX-006) |
| **WEB-SHELL-SIDEBAR** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A:collapsed | N/A:drawer | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001) |
| **WEB-SHELL-STATUSBAR**| ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-005, UX-006, UX-017) |
| **WEB-SHELL-BREADCRUMB**| ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001) |
| **WEB-SHELL-TICKER** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-TRD-OVERVIEW** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-007, UX-013, UX-015) |
| **WEB-TRD-POSITIONS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-012, UX-013, UX-016) |
| **WEB-TRD-SIGNALS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-008, UX-009, UX-013, UX-018) |
| **WEB-TRD-MARKET** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001, UX-003) |
| **WEB-INT-GRAPH** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001) |
| **WEB-INT-DEBATES** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-INT-ANALYSIS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001) |
| **WEB-INT-BRIEF** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-004) |
| **WEB-INT-MEMORY** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-INT-SKILLS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-INT-BENCHMARK** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-LED-PERFORMANCE**| ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-002) |
| **WEB-LED-EDGE** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-LED-RISK** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-005) |
| **WEB-LED-TOKENS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-LED-BACKTEST** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-TEL-CHAT** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-001) |
| **WEB-TEL-TERMINAL** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-TEL-SESSIONS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-TEL-OBSERVABILITY**| ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-007) |
| **WEB-SYS-CONFIG** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-SYS-PLUGINS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-SYS-DIAGNOSTICS**| ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-OVL-BOOT** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-004) |
| **WEB-OVL-PALETTE** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-OVL-ERROR** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-OVL-WEEKEND** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-DRW-MOBILE-NAV** | ✓it1 | ✓it1 | N/A | N/A | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-DRW-MANUAL-ORDER**| ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-DLG-DOSSIER** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-011) |
| **WEB-DLG-CONFIG-DIFF** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-DLG-APPROVAL** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-DLG-CONFIRM** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **WEB-DLG-SHORTCUTS** | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **TUI-DASH-OVERVIEW** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-014) |
| **TUI-DASH-TREE** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-014) |
| **TUI-DASH-PERF** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-014) |
| **TUI-DASH-SIGNALS** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-014) |
| **TUI-DASH-RISK** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-014) |
| **TUI-DASH-CHAT** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 (UX-014) |
| **TUI-DASH-KILLMODAL** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **TUI-CHAT-STANDALONE** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **TUI-WIZARD-SETUP** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **TUI-DOCTOR** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |
| **TUI-ONBOARDING** | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | N/A | N/A | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 | ✓it1 |

**Coverage Summary**:
- Total Surface: 44 / 44 terpetakan dan diaudit (100% surface inventory coverage).
- Evaluasi Kode & Metrik: 100% terverifikasi terhadap scan G1–G4, oxlint, dan pytest CLI.
