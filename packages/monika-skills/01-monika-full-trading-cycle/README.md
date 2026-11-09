# Monika Full Trading Cycle Skill Package (`monika-full-trading-cycle`)

End-to-End Institutional Algorithmic Trading Analysis & Quantitative Risk Gate System for Claude Code, Codex, Cursor, Google Antigravity, and Agensi.io.

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## Fitur Utama

- **Stage 0: Telemetry & Timing**: Validasi data TTL, deteksi sesi institusional (Tokyo, London Open, Judas Swing, London-NY Overlap), dan proteksi Rollover Blackout (`21:55-22:15 UTC`).
- **Stage 1: Macro & Systemic Plumbing**: Analisis 5 Bank Sentral, dekomposisi kurva imbal hasil 2s10s, likuiditas sistemik ($\text{WALCL} - \text{TGA} - \text{RRP}$), dan inflasi breakeven 10Y.
- **Stage 2: 3-Specialist SMC/ICT**: Triangulasi domain teknikal (45%), makro (35%), dan sentimen kontrarian (20%), posisi spasial dealing range ($pos$), serta 5 status sinergi institusional.
- **Stage 3: 2-Round Dialectical Debate**: Debat multi-agen adversarial antara Bull Advocate dan Bear Dissenter, atenuasi sanggahan ronde 2 (-3 poin), dan arbitrase Bayesian Chief Judge.
- **Stage 4: Deterministic Risk Fortress**: Bounding box harga konkret `LONG_OPTION_A` & `SHORT_OPTION_B` tanpa mental math, lot sizing `Decimal` (`ROUND_FLOOR`), dan audit 12-titik `RiskGate`.

---

## Struktur Direktori

```
01-monika-full-trading-cycle/
├── SKILL.md                          # Dokumentasi instruksi skill utama
├── README.md                         # Panduan instalasi dan penggunaan
├── references/                       # Playbook referensi mendalam untuk setiap tahap
│   ├── 01-data-and-session-rules.md
│   ├── 02-macro-and-plumbing-playbook.md
│   ├── 03-smc-ict-and-synergy-matrix.md
│   ├── 04-dialectical-debate-and-judge.md
│   └── 05-deterministic-math-and-riskgate.md
├── scripts/                          # Mesin matematika CLI Python (stdlib-only)
│   └── monika_quant_engine.py
└── templates/                        # Template dokumen pelaporan
    └── full-institutional-dossier.md
```

---

## Panduan Instalasi Cepat

### Claude Code
Salin folder ini ke dalam folder skill Claude Code Anda:
```bash
cp -r 01-monika-full-trading-cycle ~/.claude/skills/monika-full-trading-cycle
```

### Cursor & OpenAI Codex
Tambahkan path folder ini ke dalam konfigurasi agent atau load instruksi `SKILL.md` ke dalam rules workspace.

### Pengujian Mandiri CLI
Pastikan Python 3.10+ terinstal. Jalankan CLI deterministik tanpa dependensi tambahan:
```bash
python scripts/monika_quant_engine.py --help
```
