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
| 1 | ISSUE-R1-01 | `trading-agent/indicators/alpha_zoo/meta.py:53` | Bug | Missing typing import `Any` in `meta.py` | Selesai | Closed |
| 1 | ISSUE-R1-02 | `trading-agent/backtest/statistical_tests.py:187` | Bug | Missing typing import `Any` in `statistical_tests.py` | Selesai | Closed |
| 1 | ISSUE-R1-03 | `trading-agent/backtest/run_card.py:162` | Bug | Missing typing imports `Union`, `Tuple`, `Sequence` in `run_card.py` | Selesai | Closed |
| 1 | ISSUE-R1-04 | `trading-agent/analysis/strategies/evidence_store.py:274` | Bug | Missing typing import `Tuple` in `evidence_store.py` | Selesai | Closed |
| 1 | ISSUE-R1-05 | `trading-agent/analysis/memory/playbook_lifecycle.py:140` | Bug | Missing typing import `Tuple` in `playbook_lifecycle.py` | Selesai | Closed |
| 1 | ISSUE-R1-06 | `trading-agent/risk/risk_gate.py:1868, 1887` | Bug | Undefined variable `res` and missing `List` import in `RiskGate` | Selesai | Closed |
| 1 | ISSUE-R1-07 | `trading-agent/risk/risk_gate.py` | Bug | Dynamic asset spread check fallback and real drawdown calculation | Selesai | Closed |
| 1 | ISSUE-R1-08 | `trading-agent/analysis/schemas/trade_proposal.py:26` | Inkonsistensi | Minimum R:R ratio discrepancy between schema (1.5:1) and gate (1.3:1) | Selesai | Closed |
| 1 | ISSUE-R1-09 | `trading-agent/risk/crypto_audit_ledger.py:173` | Bug | Missing `Tuple` import and enforce fail-closed hash tamper invariant | Selesai | Closed |
| 1 | ISSUE-R1-10 | `trading-agent/execution/ea_bridge/AIAgent_EA.mq5:43` | Bug | Heartbeat timeout disparity between EA (60s) and watchdog (120s) | Selesai | Closed |
| 1 | ISSUE-R1-11 | `trading-agent/execution/service/order_executor.py:61` | Inkonsistensi | Loose paper trading graduation gate (enforced 55% win rate over 50 trades) | Selesai | Closed |
| 1 | ISSUE-R1-12 | `trading-agent/cli/main.py:1766` | Bug | Missing `plugin_name` argument in `monika plugin disable` command | Selesai | Closed |
| 1 | ISSUE-R1-13 | `trading-agent/config/settings.py` | Integrasi Belum Sempurna | Missing `${ENV_VAR}` string interpolation in configuration loader | Selesai | Closed |
| 1 | ISSUE-R1-14 | `trading-agent/security/credential_vault.py` | Tech Debt | Hardened vault cipher using CTR mode with random nonces | Selesai | Closed |
| 1 | ISSUE-R1-15 | `trading-agent/plugins/loader.py:55-70` | Bug | Plugin loader topological sorting failed on manifests with `m.name` | Selesai | Closed |
| 1 | ISSUE-R1-16 | `trading-agent/logging_observability/tracing/context.py:13` | Code Smell | Shared mutable default dict in `ContextVar` causing race conditions | Selesai | Closed |
| 1 | ISSUE-R1-17 | `stop_agent.bat:27` | Bug | Indiscriminate taskkill of `WindowsTerminal.exe` instead of agent PID | Selesai | Closed |
| 1 | ISSUE-R1-18 | `trading-agent/backtest/report_generator.py:120` | Bug | Sortino ratio downside deviation divided by N_down instead of N; empty curve crash | Selesai | Closed |
| 1 | ISSUE-R1-19 | `trading-agent/backtest/walk_forward_engine.py:145` | Bug | Walk-forward engine passed `equity_curve` as dict/generator instead of list | Selesai | Closed |
| 1 | ISSUE-R1-20 | `trading-agent/indicators/microstructure.py:167` | Bug | Microstructure Kyle's lambda `ZeroDivisionError` during zero volume variance | Selesai | Closed |
| 1 | ISSUE-R1-21 | `trading-agent/data_sources/vix_yfinance.py` | Integrasi Belum Sempurna | Mock session compatibility with `scalar_one_or_none` in yfinance fetchers | Selesai | Closed |
| 1 | ISSUE-R1-22 | `trading-agent/agent/state_rewind.py:122` | Bug | Financial carrier messages deactivated during `/undo` state rewind | Selesai | Closed |
| 1 | ISSUE-R1-23 | `trading-agent/database/migrations/versions/0001_initial_schema.py` | Inkonsistensi | Squashed migration omitted `llm_benchmark` tables and missing columns | Selesai | Closed |
| 1 | ISSUE-R1-24 | `contoh_pertanyaan.md` | Bug | Missing macro event benchmark query file causing 9 test failures | Selesai | Closed |
| 1 | ISSUE-R1-25 | `trading-agent/analysis/debate/*.py` | Inkonsistensi | Restored debate persona temperature and system prompt defaults | Selesai | Closed |
| 1 | ISSUE-R1-26 | `trading-agent/analysis/tools/domain/file_tools.py` | Bug | Universal tool safe path check rejected Windows system temp directory | Selesai | Closed |
| 1 | ISSUE-R1-27 | `trading-agent/tests/analysis/test_macro_playbook_runner.py:108` | Bug | Macro playbook runner test path portability resolution | Selesai | Closed |
| 1 | ISSUE-R1-28 | `trading-agent/security/terminal_guard.py:165` | Bug | Strict `safe_root` isolation without temp bypass when explicitly provided | Selesai | Closed |
| 1 | ISSUE-R1-29 | `trading-agent/analysis/debate/portfolio_manager.py:72` | Bug | Fail-closed institutional protection on LLM parse errors | Selesai | Closed |
| 2 | ISSUE-R2-01 | `trading-agent/analysis/harness/message_repair.py:84` | Bug | Empty assistant turns after pruning tool calls causing 400 Bad Request on provider APIs | Selesai | |
| 2 | ISSUE-R2-02 | `trading-agent/analysis/harness/agent_harness.py:348` | Bug | Silent swallow of pre-execute turn state persistence failure violating fail-closed audit invariant | Selesai | |
| 2 | ISSUE-R2-03 | `trading-agent/agent/turn_stop_gates.py:108` | Bug | Unsubmitted trade intent regex check evaluated against non-string object failing to stop turn | Selesai | |
| 2 | ISSUE-R2-04 | `trading-agent/agent/turn_lease_manager.py:72` | Integrasi Belum Sempurna | Missing `attach_harness` method breaking unexpired turn lease steering event coalescence | Selesai | |
| 2 | ISSUE-R2-05 | `trading-agent/execution/service/order_executor.py:61` | Bug | Missing ESTOP sentinel file verification prior to order proposal submission and trade execution | Selesai | |
| 2 | ISSUE-R2-06 | `trading-agent/gateway/acp_server.py:192` | Bug | Disconnected turn cancellation handling leaving background prompt worker threads running | Selesai | |
| 2 | ISSUE-R2-07 | `trading-agent/gateway/pairing.py:48, 126` | Bug | Iteration concurrency mutation `RuntimeError` on pairing store dict during background persistence | Selesai | |
| 2 | ISSUE-R2-08 | `trading-agent/telegram_bot/chat_agent.py:180` | Bug | Message edit burst rate limit exceeding Telegram API flood threshold causing 429 bans | Selesai | |
| 2 | ISSUE-R2-09 | `trading-agent/cli/main.py:126` | Bug | Subcommand execution return code ignored, exiting process with 0 even when command failed | Selesai | |
| 2 | ISSUE-R2-10 | `trading-agent/config/hot_reload.py:75` | Bug | `risk_dict` extraction failure and fallback causing `AttributeError` on non-risk YAML reload | Selesai | |
| 2 | ISSUE-R2-11 | `trading-agent/backtest/point_in_time_engine.py:228` | Inkonsistensi | Point-in-time replay engine omitted trade settlement and outcome evaluation vs live engine | Selesai | |
| 2 | ISSUE-R2-12 | `trading-agent/scrapers/calendar/calendar_forexfactory.py:115` | Bug | ForexFactory scraper failed to reset time cursor across table day transitions and crashed on "All Day" | Selesai | |
| 2 | ISSUE-R2-13 | `trading-agent/analysis/tools/environments/tier1_inprocess.py:84` | Bug | Synchronous Tier-1 tool execution lacked hard execution timeout enforcement risking event loop lockup | Selesai | |
| 2 | ISSUE-R2-14 | `trading-agent/analysis/tools/core/coercion.py:42` | Bug | Argument coercion coerced unknown truthy-like strings unconditionally to True instead of safe fallback | Selesai | |
| 2 | ISSUE-R2-15 | `trading-agent/database/db.py:12` | Bug | Missing typing import `Any` causing runtime syntax error in DB engine kwargs typing | Selesai | |
| 2 | ISSUE-R2-16 | `trading-agent/execution/backends/local_backend.py:14` | Inkonsistensi | Inconsistent error typing and connection retry backoff in local backend | Selesai | |
| 2 | ISSUE-R2-17 | `trading-agent/execution/mt5_client.py:284` | Bug | In-flight reconciliation block missing `try:` wrapper causing syntax / exception handling defect | Selesai | |
| 2 | ISSUE-R2-18 | `trading-agent/execution/service/emergency_manager.py:112` | Bug | Equity extraction returning coroutine / MagicMock causing `TypeError: '<=' not supported` | Selesai | |
| 2 | ISSUE-R2-19 | `trading-agent/execution/service/risk_evaluator.py:180` | Bug | Account info equity extraction failed to await coroutines and safely cast numeric types | Selesai | |
| 2 | ISSUE-R2-20 | `trading-agent/risk/risk_gate.py:821` | Bug | `_check_max_spread` failed-closed unconditionally on un-injected MT5 client during offline tests | Selesai | |
| 2 | ISSUE-R2-21 | `trading-agent/execution/order_emulator.py:387` | Bug | ClientOrderEmulator failed SL modification when executed in standalone simulation mode | Selesai | |
| 2 | ISSUE-R2-22 | `trading-agent/tests/execution/test_mt5_compat.py:153` | Bug | Leaked `MetaTrader5` MagicMock in `sys.modules` from preceding tests causing test isolation failure | Selesai | |
| 2 | ISSUE-R2-23 | `trading-agent/analysis/grounding/provenance_tagger.py:86` | Inkonsistensi | Gold contract size hardcoded to 100 instead of dynamic asset specification query | Selesai | |
| 2 | ISSUE-R2-24 | `trading-agent/analysis/validators/in_harness_grounding.py:45` | Bug | In-harness validator failed to normalize symbol aliases across broker platforms | Selesai | |
| 2 | ISSUE-R2-25 | `trading-agent/analysis/validators/market_snapshot.py:112` | Bug | Zero division crash in market snapshot ATR normalization when bar high equals low | Selesai | |
| 2 | ISSUE-R2-26 | `trading-agent/analysis/strategies/tsm_momentum.py:64` | Bug | Lookback window bounds check missing, causing IndexError on truncated candle feeds | Selesai | |
| 2 | ISSUE-R2-27 | `trading-agent/analysis/mcp/client.py:92` | Bug | Unclosed async subprocess pipes and zombie reader tasks on MCP client shutdown | Selesai | |
| 2 | ISSUE-R2-28 | `trading-agent/analysis/mcp/mcp_death_supervisor.py:118` | Tech Debt | Child process kill timeout lack of SIGKILL / TerminateProcess fallback on Windows | Selesai | |
| 2 | ISSUE-R2-29 | `trading-agent/analysis/memory/layered_memory.py:145` | Code Smell | Duplicated chronicle context fetching across layered memory retrieval passes | Selesai | |
| 2 | ISSUE-R2-30 | `trading-agent/analysis/memory/outcome_linker.py:78` | Bug | Missing timezone awareness normalization on closed trade timestamps during reflection linking | Selesai | |
| 2 | ISSUE-R2-31 | `trading-agent/analysis/memory/skill_ast_audit.py:42` | Bug | AST auditor rejected valid Python 3.12+ type parameter syntax in custom synthesized strategies | Selesai | |
| 2 | ISSUE-R2-32 | `trading-agent/analysis/memory/skill_crystallizer.py:110` | Bug | Unescaped markdown characters in crystallized playbook frontmatter breaking YAML parser | Selesai | |
| 2 | ISSUE-R2-33 | `trading-agent/database/adapters.py:65` | Integrasi Belum Sempurna | Missing async context manager exit handler in session adapter bridge | Selesai | |
| 2 | ISSUE-R2-34 | `trading-agent/database/fts5_cjk.py:38` | Bug | SQLite FTS5 CJK tokenizer regex catastrophic backtracking on long unstructured market texts | Selesai | |
| 2 | ISSUE-R2-35 | `trading-agent/database/session_db_wal.py:52` | Bug | WAL autocheckpoint pragmas not executed on read-only session pool connections | Selesai | |
| 2 | ISSUE-R2-36 | `trading-agent/plugins/brokers/mt5_local/mt5_plugin.py:88` | Integrasi Belum Sempurna | MT5 local broker plugin missing order fill event dispatch to unified EventBus | Selesai | |
| 2 | ISSUE-R2-37 | `trading-agent/risk/position_sizing.py:142` | Bug | PositionSizer failed to convert Decimal contract size to float causing operator TypeError | Selesai | |
| 2 | ISSUE-R2-38 | `trading-agent/security/credential_vault.py:98` | Tech Debt | Credential vault key derivation lacked PBKDF2 iteration parameter configuration | Selesai | |
| 2 | ISSUE-R2-39 | `trading-agent/security/terminal_guard.py:112` | Bug | Terminal guard path normalization failed to resolve Windows short 8.3 file paths | Selesai | |
| 2 | ISSUE-R2-40 | `trading-agent/agent/moa_loop.py:142` | Bug | MoA alternating generator lacked empty round check causing IndexError when candidate list was empty | Selesai | |
| 2 | ISSUE-R2-41 | `trading-agent/agent/turn_liveness.py:65` | Bug | Turn liveness generation counter failed to increment on unhandled exceptions | Selesai | |
| 2 | ISSUE-R2-42 | `trading-agent/analysis/calculators/confluence_calculator.py:88` | Bug | Confluence calculator divided by zero when all weight parameters were zero | Selesai | |
| 2 | ISSUE-R2-43 | `trading-agent/analysis/calculators/intraday_level_optimizer.py:134` | Inkonsistensi | SL offset tolerance direction flipped for short sell proposals | Selesai | |
| 2 | ISSUE-R2-44 | `trading-agent/analysis/calculators/macro_bias_filter.py:92` | Bug | Macro bias filter threw KeyError when fed unfamiliar currency codes | Selesai | |
| 2 | ISSUE-R2-45 | `trading-agent/analysis/debate/adjustment_validator.py:76` | Bug | Missing validation on debate judge recommended leverage multiplier bounds | Selesai | |
