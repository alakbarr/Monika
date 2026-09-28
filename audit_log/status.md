# Master Audit Status Tracker

Buku besar tunggal pelacakan status seluruh temuan masalah di setiap audit round.
**Perhatian**: File ini tidak boleh dihapus atau ditimpa di round berikutnya; setiap round baru hanya menambahkan baris baru ke tabel ini serta mengisi kolom verifikasi untuk masalah dari round sebelumnya.

## Aturan Kolom
- **Round**: Nomor round audit tempat masalah ditemukan dan diperbaiki.
- **ID**: Identifier unik masalah (format: `ISSUE-R<round>-<nomor>`).
- **File & Location**: Path file dan baris target.
- **Kategori**: `Bug` / `Inkonsistensi` / `Integrasi Belum Sempurna` / `Tech Debt` / `Code Smell`.
- **Deskripsi Masalah**: Ringkasan esensi masalah yang diperbaiki.
- **Status**: `Selesai` / `Partial` (Diisi oleh agent yang memperbaiki di round tersebut).
- **Verifikasi**: `Closed` / `Open` (Dikosongkan untuk masalah round baru saat ini; hanya diisi oleh agent pada round berikutnya setelah memverifikasi).

---

## Tabel Status Investigasi & Remediasi

| Round | ID | File & Location | Kategori | Deskripsi Masalah | Status | Verifikasi |
|:---:|:---|:---|:---|:---|:---:|:---:|
| 1 | ISSUE-R1-01 | `trading-agent/indicators/alpha_zoo/meta.py:53` | Bug | Missing typing import `Any` in `meta.py` | Selesai | |
| 1 | ISSUE-R1-02 | `trading-agent/backtest/statistical_tests.py:187` | Bug | Missing typing import `Any` in `statistical_tests.py` | Selesai | |
| 1 | ISSUE-R1-03 | `trading-agent/backtest/run_card.py:162` | Bug | Missing typing imports `Union`, `Tuple`, `Sequence` in `run_card.py` | Selesai | |
| 1 | ISSUE-R1-04 | `trading-agent/analysis/strategies/evidence_store.py:274` | Bug | Missing typing import `Tuple` in `evidence_store.py` | Selesai | |
| 1 | ISSUE-R1-05 | `trading-agent/analysis/memory/playbook_lifecycle.py:140` | Bug | Missing typing import `Tuple` in `playbook_lifecycle.py` | Selesai | |
| 1 | ISSUE-R1-06 | `trading-agent/risk/risk_gate.py:1868, 1887` | Bug | Undefined variable `res` and missing `List` import in `RiskGate` | Selesai | |
| 1 | ISSUE-R1-07 | `trading-agent/risk/risk_gate.py` | Bug | Dynamic asset spread check fallback and real drawdown calculation | Selesai | |
| 1 | ISSUE-R1-08 | `trading-agent/analysis/schemas/trade_proposal.py:26` | Inkonsistensi | Minimum R:R ratio discrepancy between schema (1.5:1) and gate (1.3:1) | Selesai | |
| 1 | ISSUE-R1-09 | `trading-agent/risk/crypto_audit_ledger.py:173` | Bug | Missing `Tuple` import and enforce fail-closed hash tamper invariant | Selesai | |
| 1 | ISSUE-R1-10 | `trading-agent/execution/ea_bridge/AIAgent_EA.mq5:43` | Bug | Heartbeat timeout disparity between EA (60s) and watchdog (120s) | Selesai | |
| 1 | ISSUE-R1-11 | `trading-agent/execution/service/order_executor.py:61` | Inkonsistensi | Loose paper trading graduation gate (enforced 55% win rate over 50 trades) | Selesai | |
| 1 | ISSUE-R1-12 | `trading-agent/cli/main.py:1766` | Bug | Missing `plugin_name` argument in `monika plugin disable` command | Selesai | |
| 1 | ISSUE-R1-13 | `trading-agent/config/settings.py` | Integrasi Belum Sempurna | Missing `${ENV_VAR}` string interpolation in configuration loader | Selesai | |
| 1 | ISSUE-R1-14 | `trading-agent/security/credential_vault.py` | Tech Debt | Hardened vault cipher using CTR mode with random nonces | Selesai | |
| 1 | ISSUE-R1-15 | `trading-agent/plugins/loader.py:55-70` | Bug | Plugin loader topological sorting failed on manifests with `m.name` | Selesai | |
| 1 | ISSUE-R1-16 | `trading-agent/logging_observability/tracing/context.py:13` | Code Smell | Shared mutable default dict in `ContextVar` causing race conditions | Selesai | |
| 1 | ISSUE-R1-17 | `stop_agent.bat:27` | Bug | Indiscriminate taskkill of `WindowsTerminal.exe` instead of agent PID | Selesai | |
| 1 | ISSUE-R1-18 | `trading-agent/backtest/report_generator.py:120` | Bug | Sortino ratio downside deviation divided by N_down instead of N; empty curve crash | Selesai | |
| 1 | ISSUE-R1-19 | `trading-agent/backtest/walk_forward_engine.py:145` | Bug | Walk-forward engine passed `equity_curve` as dict/generator instead of list | Selesai | |
| 1 | ISSUE-R1-20 | `trading-agent/indicators/microstructure.py:167` | Bug | Microstructure Kyle's lambda `ZeroDivisionError` during zero volume variance | Selesai | |
| 1 | ISSUE-R1-21 | `trading-agent/data_sources/vix_yfinance.py` | Integrasi Belum Sempurna | Mock session compatibility with `scalar_one_or_none` in yfinance fetchers | Selesai | |
| 1 | ISSUE-R1-22 | `trading-agent/agent/state_rewind.py:122` | Bug | Financial carrier messages deactivated during `/undo` state rewind | Selesai | |
| 1 | ISSUE-R1-23 | `trading-agent/database/migrations/versions/0001_initial_schema.py` | Inkonsistensi | Squashed migration omitted `llm_benchmark` tables and missing columns | Selesai | |
| 1 | ISSUE-R1-24 | `contoh_pertanyaan.md` | Bug | Missing macro event benchmark query file causing 9 test failures | Selesai | |
| 1 | ISSUE-R1-25 | `trading-agent/analysis/debate/*.py` | Inkonsistensi | Restored debate persona temperature and system prompt defaults | Selesai | |
| 1 | ISSUE-R1-26 | `trading-agent/analysis/tools/domain/file_tools.py` | Bug | Universal tool safe path check rejected Windows system temp directory | Selesai | |
| 1 | ISSUE-R1-27 | `trading-agent/tests/analysis/test_macro_playbook_runner.py:108` | Bug | Macro playbook runner test path portability resolution | Selesai | |
| 1 | ISSUE-R1-28 | `trading-agent/security/terminal_guard.py:165` | Bug | Strict `safe_root` isolation without temp bypass when explicitly provided | Selesai | |
| 1 | ISSUE-R1-29 | `trading-agent/analysis/debate/portfolio_manager.py:72` | Bug | Fail-closed institutional protection on LLM parse errors | Selesai | |
