# ==================================================
# CODEBASE DIRECTORY STRUCTURE — MONIKA (MT5 TRADING AGENT)
# ==================================================

Monika/
├── .dockerignore
├── .env.example
├── .git-blame-ignore-revs
├── .gitattributes
├── .github
│   ├── ISSUE_TEMPLATE
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── pull_request_template.md
│   └── workflows
│       └── ci.yml
├── .gitignore
├── .importlinter
├── .pre-commit-config.yaml
├── AGENTS.md
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── DESIGN.md
├── Dockerfile
├── GEMINI.md
├── INDEX.md
├── LICENSE
├── Makefile
├── PRD.md
├── README.md
├── SECURITY.md
├── STRUCTURE.md
├── monika.bat
├── deploy
│   ├── Dockerfile.mt5-wine
│   ├── docker-compose.vps.yml
│   ├── entrypoint_mt5.sh
│   └── vps_deployment_guide.md
├── docker-compose.yml
├── docs
│   ├── ROADMAP_SRC_MONIKA.md
│   ├── SETUP_GUIDE.md
│   ├── images
│   │   ├── 02_trading_desk_signals.png
│   │   ├── 03_trading_desk_market.png
│   │   ├── 04_market_intelligence_pipeline_dag.png
│   │   ├── 05_market_intelligence_macro_brief.png
│   │   ├── 06_ledger_risk_limits.png
│   │   ├── 07_ledger_llm_token_audit.png
│   │   ├── 08_telegraph_desk_console_chat.png
│   │   ├── 09_system_configuration.png
│   │   ├── 10_terminal_ui_tui.png
│   │   ├── 10_terminal_ui_tui.svg
│   │   └── dashboard
│   ├── quality
│   │   └── baseline.json
│   └── ux-audit
│       ├── AUDIT.md
│       ├── COVERAGE.md
│       ├── DECISIONS.md
│       ├── FINDINGS.md
│       ├── PLAN.md
│       ├── STATE.md
│       ├── SURFACES.md
│       ├── SYSTEM-MAP.md
│       ├── evidence
│       ├── iterations
│       │   ├── 01
│       │   │   └── summary.md
│       │   └── 02
│       │       └── summary.md
│       └── surfaces
│           ├── TUI-DASH-OVERVIEW.md
│           ├── WEB-DLG-DOSSIER.md
│           ├── WEB-SHELL-HEADER.md
│           ├── WEB-SHELL-STATUSBAR.md
│           ├── WEB-TRD-OVERVIEW.md
│           ├── WEB-TRD-POSITIONS.md
│           └── WEB-TRD-SIGNALS.md
├── frontend
│   ├── .env.example
│   ├── .gitignore
│   ├── README.md
│   ├── eslint.config.js
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   ├── dist
│   └── src
│       ├── App.tsx
│       ├── main.tsx
│       ├── components
│       ├── hooks
│       ├── services
│       └── types
├── pyproject.toml

├── pyrightconfig.json
├── pytest.ini
├── scripts
│   ├── analyze_news_classification_mismatches.py
│   ├── audit_token_usage.py
│   ├── benchmark_debate_openrouter.py
│   ├── benchmark_news_classification_openrouter.py
│   ├── benchmark_stage1_openrouter.py
│   ├── benchmark_stage2_openrouter.py
│   ├── build_curated_benchmark_fixtures.py
│   ├── capture_dashboard_screenshots.js
│   ├── capture_tui_screenshots.py
│   ├── check_all_models.py
│   ├── check_env_keys.py
│   ├── check_incomplete.py
│   ├── check_scrapers
│   │   ├── __init__.py
│   │   ├── check_calendar.py
│   │   ├── check_cme.py
│   │   ├── check_news.py
│   │   ├── check_sentiment.py
│   │   └── check_twitter.py
│   ├── compile_alphas_to_catalog.py
│   ├── consolidate_sqlite_dbs.py
│   ├── convert_tui_svg_to_png.js
│   ├── download_timesfm_weights.py
│   ├── extract_production_fixtures.py
│   ├── extract_realistic_fixtures.py
│   ├── generate_full_benchmark_dashboard.py
│   ├── generate_model_quadrant.py
│   ├── heal_kill_switch_state.py
│   ├── migrate_runtime_home.py
│   ├── migrate_sqlite_to_canonical.py
│   ├── reset_paper_trades.py
│   ├── run_tests.bat
│   ├── run_tests.sh
│   ├── update_benchmark_table.py
│   ├── update_economic_calendar.py
│   ├── update_index_toc.py
│   └── ux_audit_baseline_scan.py
├── skills-lock.json
├── start_monika.bat
├── start_monika.sh
├── typings
│   ├── MetaTrader5
│   │   └── __init__.pyi
│   ├── bottleneck
│   │   └── __init__.pyi
│   ├── concurrent_log_handler
│   │   └── __init__.pyi
│   ├── hmmlearn
│   │   ├── __init__.pyi
│   │   └── hmm.pyi
│   ├── ib_insync
│   │   └── __init__.pyi
│   ├── mt5linux
│   │   └── __init__.pyi
│   ├── uvloop
│   │   └── __init__.pyi
│   └── weasyprint
│       └── __init__.pyi
├── src
│   └── monika
│       ├── __init__.py
│       ├── application
│       │   ├── agent
│       │   │   ├── __init__.py
│       │   │   ├── agent_loop.py
│       │   │   ├── auxiliary_model_router.py
│       │   │   ├── bounded_response.py
│       │   │   ├── chat_agent.py
│       │   │   ├── chat_compaction.py
│       │   │   ├── chat_tool_router.py
│       │   │   ├── deadline.py
│       │   │   ├── empty_response_guard.py
│       │   │   ├── error_classifier.py
│       │   │   ├── estop.py
│       │   │   ├── harness
│       │   │   │   ├── __init__.py
│       │   │   │   ├── agent_harness.py
│       │   │   │   ├── context_compressor.py
│       │   │   │   ├── error_classifier.py
│       │   │   │   ├── harness_state.py
│       │   │   │   ├── message_repair.py
│       │   │   │   ├── repetition_guard.py
│       │   │   │   ├── stall_guard.py
│       │   │   │   ├── structured_output.py
│       │   │   │   ├── symbol_segment_planner.py
│       │   │   │   ├── tool_batch_planner.py
│       │   │   │   ├── tool_repair.py
│       │   │   │   ├── trade_stop_gates.py
│       │   │   │   └── verification_evidence_ledger.py
│       │   │   ├── moa_alternation.py
│       │   │   ├── moa_loop.py
│       │   │   ├── moa_trace.py
│       │   │   ├── monitors
│       │   │   │   ├── __init__.py
│       │   │   │   ├── db_health.py
│       │   │   │   ├── drawdown_monitor.py
│       │   │   │   ├── margin_monitor.py
│       │   │   │   ├── paper_trade_monitor.py
│       │   │   │   ├── scraper_loop.py
│       │   │   │   └── startup_watchdog.py
│       │   │   ├── readonly_replay_cache.py
│       │   │   ├── repetition_guard.py
│       │   │   ├── scratchpad_guard.py
│       │   │   ├── socket_lifecycle_guard.py
│       │   │   ├── startup_checks.py
│       │   │   ├── state_rewind.py
│       │   │   ├── task_registry.py
│       │   │   ├── thinking_timeout_guidance.py
│       │   │   ├── three_part_context_compressor.py
│       │   │   ├── trajectory_compressor.py
│       │   │   ├── turn_lease_manager.py
│       │   │   ├── turn_liveness.py
│       │   │   ├── turn_phase_machine.py
│       │   │   ├── turn_preflight_gate.py
│       │   │   ├── turn_stop_gates.py
│       │   │   └── turn_tool_round.py
│       │   ├── analysis
│       │   │   ├── __init__.py
│       │   │   ├── arbitration
│       │   │   │   ├── __init__.py
│       │   │   │   └── signal_arbitrator.py
│       │   │   ├── calculators
│       │   │   │   ├── __pycache__
│       │   │   │   │   ├── __init__.cpython-314.pyc
│       │   │   │   │   ├── adaptive_policy.cpython-314.pyc
│       │   │   │   │   ├── cointegration.cpython-314.pyc
│       │   │   │   │   ├── confluence_calculator.cpython-314.pyc
│       │   │   │   │   ├── copula_tail_risk.cpython-314.pyc
│       │   │   │   │   ├── daily_range_calculator.cpython-314.pyc
│       │   │   │   │   ├── economic_surprise.cpython-314.pyc
│       │   │   │   │   ├── evt_tail_calculator.cpython-314.pyc
│       │   │   │   │   ├── factor_ic.cpython-314.pyc
│       │   │   │   │   ├── garch_volatility.cpython-314.pyc
│       │   │   │   │   ├── hierarchical_risk_parity.cpython-314.pyc
│       │   │   │   │   ├── hmm_regime.cpython-314.pyc
│       │   │   │   │   ├── intraday_level_optimizer.cpython-314.pyc
│       │   │   │   │   ├── invariant_calculator.cpython-314.pyc
│       │   │   │   │   ├── leading_indicator_mapper.cpython-314.pyc
│       │   │   │   │   ├── liquidity_sweep_detector.cpython-314.pyc
│       │   │   │   │   ├── macro_bias_filter.cpython-314.pyc
│       │   │   │   │   ├── macro_priced_in_calculator.cpython-314.pyc
│       │   │   │   │   ├── options_volatility_hedging.cpython-314.pyc
│       │   │   │   │   ├── quant_plateau_optimizer.cpython-314.pyc
│       │   │   │   │   ├── quantlib_core.cpython-314.pyc
│       │   │   │   │   ├── regime_classifier.cpython-314.pyc
│       │   │   │   │   ├── rolling_correlation_calculator.cpython-314.pyc
│       │   │   │   │   ├── seasonality.cpython-314.pyc
│       │   │   │   │   ├── stage1_priced_in.cpython-314.pyc
│       │   │   │   │   ├── taylor_rule.cpython-314.pyc
│       │   │   │   │   ├── timesfm_alpha.cpython-314.pyc
│       │   │   │   │   ├── timesfm_residual_validator.cpython-314.pyc
│       │   │   │   │   ├── unified_threshold_calculator.cpython-314.pyc
│       │   │   │   │   ├── universal_cb_differ.cpython-314.pyc
│       │   │   │   │   ├── universal_liquidity_analyzer.cpython-314.pyc
│       │   │   │   │   ├── universal_macro_analyzer.cpython-314.pyc
│       │   │   │   │   └── volume_profile.cpython-314.pyc
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adaptive_policy.py
│       │   │   │   ├── cointegration.py
│       │   │   │   ├── confluence_calculator.py
│       │   │   │   ├── copula_tail_risk.py
│       │   │   │   ├── daily_range_calculator.py
│       │   │   │   ├── economic_surprise.py
│       │   │   │   ├── evt_tail_calculator.py
│       │   │   │   ├── factor_ic.py
│       │   │   │   ├── garch_volatility.py
│       │   │   │   ├── hierarchical_risk_parity.py
│       │   │   │   ├── hmm_regime.py
│       │   │   │   ├── intraday_level_optimizer.py
│       │   │   │   ├── invariant_calculator.py
│       │   │   │   ├── leading_indicator_mapper.py
│       │   │   │   ├── liquidity_sweep_detector.py
│       │   │   │   ├── macro_bias_filter.py
│       │   │   │   ├── macro_priced_in_calculator.py
│       │   │   │   ├── options_volatility_hedging.py
│       │   │   │   ├── quant_plateau_optimizer.py
│       │   │   │   ├── quantlib_core.py
│       │   │   │   ├── regime_classifier.py
│       │   │   │   ├── rolling_correlation_calculator.py
│       │   │   │   ├── seasonality.py
│       │   │   │   ├── stage1_priced_in.py
│       │   │   │   ├── taylor_rule.py
│       │   │   │   ├── timesfm_alpha.py
│       │   │   │   ├── timesfm_residual_validator.py
│       │   │   │   ├── unified_threshold_calculator.py
│       │   │   │   ├── universal_cb_differ.py
│       │   │   │   ├── universal_liquidity_analyzer.py
│       │   │   │   ├── universal_macro_analyzer.py
│       │   │   │   └── volume_profile.py
│       │   │   ├── debate
│       │   │   │   ├── __pycache__
│       │   │   │   │   ├── __init__.cpython-314.pyc
│       │   │   │   │   ├── adjustment_validator.cpython-314.pyc
│       │   │   │   │   ├── aggressive_risk_llm.cpython-314.pyc
│       │   │   │   │   ├── bear_analyst.cpython-314.pyc
│       │   │   │   │   ├── blackboard.cpython-314.pyc
│       │   │   │   │   ├── bull_analyst.cpython-314.pyc
│       │   │   │   │   ├── conservative_risk_llm.cpython-314.pyc
│       │   │   │   │   ├── deterministic_risk.cpython-314.pyc
│       │   │   │   │   ├── discussion_engine.cpython-314.pyc
│       │   │   │   │   ├── exact_decimal_math.cpython-314.pyc
│       │   │   │   │   ├── fact_sheet.cpython-314.pyc
│       │   │   │   │   ├── investment_judge.cpython-314.pyc
│       │   │   │   │   ├── macro_bear_analyst.cpython-314.pyc
│       │   │   │   │   ├── macro_bull_analyst.cpython-314.pyc
│       │   │   │   │   ├── macro_debate_validator.cpython-314.pyc
│       │   │   │   │   ├── macro_judge.cpython-314.pyc
│       │   │   │   │   ├── multi_persona_risk_llm.cpython-314.pyc
│       │   │   │   │   ├── neutral_risk_llm.cpython-314.pyc
│       │   │   │   │   └── portfolio_manager.cpython-314.pyc
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adjustment_validator.py
│       │   │   │   ├── aggressive_risk_llm.py
│       │   │   │   ├── bear_analyst.py
│       │   │   │   ├── blackboard.py
│       │   │   │   ├── bull_analyst.py
│       │   │   │   ├── conservative_risk_llm.py
│       │   │   │   ├── deterministic_risk.py
│       │   │   │   ├── discussion_engine.py
│       │   │   │   ├── exact_decimal_math.py
│       │   │   │   ├── fact_sheet.py
│       │   │   │   ├── investment_judge.py
│       │   │   │   ├── macro_bear_analyst.py
│       │   │   │   ├── macro_bull_analyst.py
│       │   │   │   ├── macro_debate_validator.py
│       │   │   │   ├── macro_judge.py
│       │   │   │   ├── multi_persona_risk_llm.py
│       │   │   │   ├── neutral_risk_llm.py
│       │   │   │   └── portfolio_manager.py
│       │   │   ├── event_broadcaster.py
│       │   │   ├── grounding
│       │   │   │   ├── __init__.py
│       │   │   │   ├── declared_figures.py
│       │   │   │   ├── provenance_tagger.py
│       │   │   │   └── surgical_redaction.py
│       │   │   ├── harness
│       │   │   │   ├── __init__.py
│       │   │   │   ├── agent_harness.py
│       │   │   │   ├── context_compressor.py
│       │   │   │   ├── error_classifier.py
│       │   │   │   ├── harness_state.py
│       │   │   │   ├── message_repair.py
│       │   │   │   ├── repetition_guard.py
│       │   │   │   ├── stall_guard.py
│       │   │   │   ├── structured_output.py
│       │   │   │   ├── symbol_segment_planner.py
│       │   │   │   ├── tool_batch_planner.py
│       │   │   │   ├── tool_repair.py
│       │   │   │   ├── trade_stop_gates.py
│       │   │   │   └── verification_evidence_ledger.py
│       │   │   ├── journal
│       │   │   │   ├── __init__.py
│       │   │   │   ├── attribution_engine.py
│       │   │   │   ├── behavioral_diagnostics.py
│       │   │   │   ├── journal_parser.py
│       │   │   │   └── shadow_extractor.py
│       │   │   ├── macro_pipeline_plugin.py
│       │   │   ├── mcp
│       │   │   │   ├── __init__.py
│       │   │   │   ├── client.py
│       │   │   │   ├── dispatcher.py
│       │   │   │   ├── event_bridge.py
│       │   │   │   ├── mcp_death_supervisor.py
│       │   │   │   ├── mcp_schema_cache.py
│       │   │   │   ├── mcp_serve.py
│       │   │   │   ├── oauth_handler.py
│       │   │   │   ├── protocol.py
│       │   │   │   ├── server.py
│       │   │   │   └── servers
│       │   │   │       ├── __init__.py
│       │   │   │       ├── excel_server.py
│       │   │   │       ├── fetch_server.py
│       │   │   │       ├── filesystem_server.py
│       │   │   │       ├── google_sheets_server.py
│       │   │   └── sqlite_server.py
│       │   │   ├── memory
│       │   │   │   ├── __pycache__
│       │   │   │   │   ├── __init__.cpython-314.pyc
│       │   │   │   │   ├── alpha_calculator.cpython-314.pyc
│       │   │   │   │   ├── background_review.cpython-314.pyc
│       │   │   │   │   ├── background_review_fork.cpython-314.pyc
│       │   │   │   │   ├── chronicle_writer.cpython-314.pyc
│       │   │   │   │   ├── context_engine.cpython-314.pyc
│       │   │   │   │   ├── counterfactual_simulator.cpython-314.pyc
│       │   │   │   │   ├── decision_log.cpython-314.pyc
│       │   │   │   │   ├── failure_taxonomy.cpython-314.pyc
│       │   │   │   │   ├── frozen_snapshot.cpython-314.pyc
│       │   │   │   │   ├── layered_memory.cpython-314.pyc
│       │   │   │   │   ├── lesson_consolidator.cpython-314.pyc
│       │   │   │   │   ├── mechanical_anchor_index.cpython-314.pyc
│       │   │   │   │   ├── memory_lifecycle_gc.cpython-314.pyc
│       │   │   │   │   ├── negative_constraint_generator.cpython-314.pyc
│       │   │   │   │   ├── outcome_linker.cpython-314.pyc
│       │   │   │   │   ├── playbook_ledger.cpython-314.pyc
│       │   │   │   │   ├── playbook_lifecycle.cpython-314.pyc
│       │   │   │   │   ├── playbook_linter.cpython-314.pyc
│       │   │   │   │   ├── progressive_loader.cpython-314.pyc
│       │   │   │   │   ├── prompt_cache_boundary.cpython-314.pyc
│       │   │   │   │   ├── reflector.cpython-314.pyc
│       │   │   │   │   ├── session_search.cpython-314.pyc
│       │   │   │   │   ├── sharegpt_exporter.cpython-314.pyc
│       │   │   │   │   ├── skill_ast_audit.cpython-314.pyc
│       │   │   │   │   ├── skill_crystallizer.cpython-314.pyc
│       │   │   │   │   ├── skill_curator.cpython-314.pyc
│       │   │   │   │   ├── skill_evolution.cpython-314.pyc
│       │   │   │   │   ├── skill_ledger_sha.cpython-314.pyc
│       │   │   │   │   ├── trajectory_compressor.cpython-314.pyc
│       │   │   │   │   └── working_scratchpad.cpython-314.pyc
│       │   │   │   ├── __init__.py
│       │   │   │   ├── alpha_calculator.py
│       │   │   │   ├── background_review.py
│       │   │   │   ├── background_review_fork.py
│       │   │   │   ├── chronicle_writer.py
│       │   │   │   ├── context_engine.py
│       │   │   │   ├── counterfactual_simulator.py
│       │   │   │   ├── decision_log.py
│       │   │   │   ├── failure_taxonomy.py
│       │   │   │   ├── frozen_snapshot.py
│       │   │   │   ├── layered_memory.py
│       │   │   │   ├── lesson_consolidator.py
│       │   │   │   ├── mechanical_anchor_index.py
│       │   │   │   ├── memory_lifecycle_gc.py
│       │   │   │   ├── negative_constraint_generator.py
│       │   │   │   ├── outcome_linker.py
│       │   │   │   ├── playbook_ledger.py
│       │   │   │   ├── playbook_lifecycle.py
│       │   │   │   ├── playbook_linter.py
│       │   │   │   ├── progressive_loader.py
│       │   │   │   ├── prompt_cache_boundary.py
│       │   │   │   ├── reflector.py
│       │   │   │   ├── session_search.py
│       │   │   │   ├── sharegpt_exporter.py
│       │   │   │   ├── skill_ast_audit.py
│       │   │   │   ├── skill_crystallizer.py
│       │   │   │   ├── skill_curator.py
│       │   │   │   ├── skill_evolution.py
│       │   │   │   ├── skill_ledger_sha.py
│       │   │   │   ├── trajectory_compressor.py
│       │   │   │   └── working_scratchpad.py
│       │   │   ├── pipeline_plugin.py
│       │   │   ├── prefetch
│       │   │   │   ├── __init__.py
│       │   │   │   ├── digest_slice_generator.py
│       │   │   │   ├── macro_preprocessor.py
│       │   │   │   ├── news_digest
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── base.py
│       │   │   │   │   ├── classification.py
│       │   │   │   │   ├── constants.py
│       │   │   │   │   ├── generation.py
│       │   │   │   │   ├── helpers.py
│       │   │   │   │   ├── macro_context.py
│       │   │   │   │   ├── processor.py
│       │   │   │   │   ├── summaries.py
│       │   │   │   │   └── verification.py
│       │   │   │   ├── news_digest.py
│       │   │   │   ├── pipeline.py
│       │   │   │   ├── sentiment_aggregator.py
│       │   │   │   ├── stage1_prefetcher.py
│       │   │   │   └── stage2_prefetcher.py
│       │   │   ├── prompt
│       │   │   │   ├── __init__.py
│       │   │   │   └── prompt_assembler.py
│       │   │   ├── prompt_sections.py
│       │   │   ├── research
│       │   │   │   └── macro_playbook_runner.py
│       │   │   ├── scenario_tree.py
│       │   │   ├── schemas
│       │   │   │   ├── __init__.py
│       │   │   │   ├── pydantic_schemas.py
│       │   │   │   └── schemas.py
│       │   │   ├── stages
│       │   │   │   ├── __init__.py
│       │   │   │   ├── fundamental_stage.py
│       │   │   │   ├── fundamental_stage_recovery.py
│       │   │   │   ├── per_asset
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── context_builder.py
│       │   │   │   │   ├── runner.py
│       │   │   │   │   ├── specialist_council.py
│       │   │   │   │   ├── specialist_pipeline.py
│       │   │   │   │   └── verifiers.py
│       │   │   │   ├── per_asset_stage.py
│       │   │   │   └── preflight_gate.py
│       │   │   ├── strategies
│       │   │   │   ├── __pycache__
│       │   │   │   │   ├── __init__.cpython-314.pyc
│       │   │   │   │   ├── base_strategy.cpython-314.pyc
│       │   │   │   │   ├── bb_volume_profile.cpython-314.pyc
│       │   │   │   │   ├── btc_donchian_breakout.cpython-314.pyc
│       │   │   │   │   ├── decay_monitor.cpython-314.pyc
│       │   │   │   │   ├── evidence_store.cpython-314.pyc
│       │   │   │   │   ├── gap_fade.cpython-314.pyc
│       │   │   │   │   ├── hypothesis_registry.cpython-314.pyc
│       │   │   │   │   ├── liquidity_sweep_edge.cpython-314.pyc
│       │   │   │   │   ├── pretrade_gate.cpython-314.pyc
│       │   │   │   │   ├── registry.cpython-314.pyc
│       │   │   │   │   ├── smc_fvg.cpython-314.pyc
│       │   │   │   │   ├── strategy_plugin.cpython-314.pyc
│       │   │   │   │   ├── tri_convergent_alpha.cpython-314.pyc
│       │   │   │   │   ├── tsm_momentum.cpython-314.pyc
│       │   │   │   │   ├── xau_trend_engine.cpython-314.pyc
│       │   │   │   │   └── xti_pairs_readiness.cpython-314.pyc
│       │   │   │   ├── synthesized
│       │   │   │   │   ├── __pycache__
│       │   │   │   │   │   ├── __init__.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_27c20d.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_3a4246.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_5f9ce8.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_8acf60.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_932927.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_aacbcf.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_abe552.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_c2eab6.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_ce0c59.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_de5e1e.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_audusd_eb3084.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_1230d3.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_486acc.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_50c0eb.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_52d670.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_8b05ec.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_96feb9.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_adf9b6.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_b22661.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_bd9200.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_cbd98f.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_ce0d23.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_db91cc.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_btcusd_f91b83.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_6c25e3.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_6d622a.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_76877d.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_8060ed.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_920843.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_974ead.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_a25dcb.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_b7af66.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_c89ba5.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_eurusd_fa2e45.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_1c9869.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_1fb4c5.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_4947d0.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_634767.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_867953.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_9f0652.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_b14ef8.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_b3f4b6.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_gbpusd_e73efc.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_131b6e.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_13a603.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_159711.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_41ec5b.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_4a7cd2.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_55884a.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_7c9264.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_8102fa.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_da40ef.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_usdjpy_e3c1b2.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_133dfb.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_3af460.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_5044bf.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_59cf5d.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_5e8d45.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_61842a.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_63216a.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_6e46d9.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_72bf31.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_7358c1.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_754250.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_75d1dc.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_78210e.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_94ad53.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_96d26b.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_a6d004.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_a84e8d.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_b01980.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_b256b3.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_b68a11.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_bb1cfa.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_ca7c75.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xauusd_dfbed8.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_042cd9.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_0d2342.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_0f1bd3.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_176316.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_3e1575.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_3fe51d.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_5af3d8.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_6e7089.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_87e8fa.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_945526.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_9e8436.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_beb0e3.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_d4aee9.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_d7ab4a.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_e55dbf.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_e87a0b.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_eadd31.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xbrusd_ec8f88.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_09ce88.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_16dc64.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_1793d0.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_2c4e39.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_374fa7.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_403155.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_43ae5f.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_487183.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_592069.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_83031c.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_880297.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_9ffd6d.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_dae3f9.cpython-314.pyc
│       │   │   │   │   │   ├── alpha_xtiusd_f30ff5.cpython-314.pyc
│       │   │   │   │   │   └── alpha_xtiusd_fd5506.cpython-314.pyc
│       │   │   │   │   ├── quarantine
│       │   │   │   │   │   └── alpha_btcusd_467904.py
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── alpha_audusd_27c20d.py
│       │   │   │   │   ├── alpha_audusd_3a4246.py
│       │   │   │   │   ├── alpha_audusd_5f9ce8.py
│       │   │   │   │   ├── alpha_audusd_8acf60.py
│       │   │   │   │   ├── alpha_audusd_932927.py
│       │   │   │   │   ├── alpha_audusd_aacbcf.py
│       │   │   │   │   ├── alpha_audusd_abe552.py
│       │   │   │   │   ├── alpha_audusd_c2eab6.py
│       │   │   │   │   ├── alpha_audusd_ce0c59.py
│       │   │   │   │   ├── alpha_audusd_de5e1e.py
│       │   │   │   │   ├── alpha_audusd_eb3084.py
│       │   │   │   │   ├── alpha_btcusd_1230d3.py
│       │   │   │   │   ├── alpha_btcusd_486acc.py
│       │   │   │   │   ├── alpha_btcusd_50c0eb.py
│       │   │   │   │   ├── alpha_btcusd_52d670.py
│       │   │   │   │   ├── alpha_btcusd_8b05ec.py
│       │   │   │   │   ├── alpha_btcusd_96feb9.py
│       │   │   │   │   ├── alpha_btcusd_adf9b6.py
│       │   │   │   │   ├── alpha_btcusd_b22661.py
│       │   │   │   │   ├── alpha_btcusd_bd9200.py
│       │   │   │   │   ├── alpha_btcusd_cbd98f.py
│       │   │   │   │   ├── alpha_btcusd_ce0d23.py
│       │   │   │   │   ├── alpha_btcusd_db91cc.py
│       │   │   │   │   ├── alpha_btcusd_f91b83.py
│       │   │   │   │   ├── alpha_eurusd_6c25e3.py
│       │   │   │   │   ├── alpha_eurusd_6d622a.py
│       │   │   │   │   ├── alpha_eurusd_76877d.py
│       │   │   │   │   ├── alpha_eurusd_8060ed.py
│       │   │   │   │   ├── alpha_eurusd_920843.py
│       │   │   │   │   ├── alpha_eurusd_974ead.py
│       │   │   │   │   ├── alpha_eurusd_a25dcb.py
│       │   │   │   │   ├── alpha_eurusd_b7af66.py
│       │   │   │   │   ├── alpha_eurusd_c89ba5.py
│       │   │   │   │   ├── alpha_eurusd_fa2e45.py
│       │   │   │   │   ├── alpha_gbpusd_1c9869.py
│       │   │   │   │   ├── alpha_gbpusd_1fb4c5.py
│       │   │   │   │   ├── alpha_gbpusd_4947d0.py
│       │   │   │   │   ├── alpha_gbpusd_634767.py
│       │   │   │   │   ├── alpha_gbpusd_867953.py
│       │   │   │   │   ├── alpha_gbpusd_9f0652.py
│       │   │   │   │   ├── alpha_gbpusd_b14ef8.py
│       │   │   │   │   ├── alpha_gbpusd_b3f4b6.py
│       │   │   │   │   ├── alpha_gbpusd_e73efc.py
│       │   │   │   │   ├── alpha_usdjpy_131b6e.py
│       │   │   │   │   ├── alpha_usdjpy_13a603.py
│       │   │   │   │   ├── alpha_usdjpy_159711.py
│       │   │   │   │   ├── alpha_usdjpy_41ec5b.py
│       │   │   │   │   ├── alpha_usdjpy_4a7cd2.py
│       │   │   │   │   ├── alpha_usdjpy_55884a.py
│       │   │   │   │   ├── alpha_usdjpy_7c9264.py
│       │   │   │   │   ├── alpha_usdjpy_8102fa.py
│       │   │   │   │   ├── alpha_usdjpy_da40ef.py
│       │   │   │   │   ├── alpha_usdjpy_e3c1b2.py
│       │   │   │   │   ├── alpha_xauusd_133dfb.py
│       │   │   │   │   ├── alpha_xauusd_3af460.py
│       │   │   │   │   ├── alpha_xauusd_5044bf.py
│       │   │   │   │   ├── alpha_xauusd_59cf5d.py
│       │   │   │   │   ├── alpha_xauusd_5e8d45.py
│       │   │   │   │   ├── alpha_xauusd_61842a.py
│       │   │   │   │   ├── alpha_xauusd_63216a.py
│       │   │   │   │   ├── alpha_xauusd_6e46d9.py
│       │   │   │   │   ├── alpha_xauusd_72bf31.py
│       │   │   │   │   ├── alpha_xauusd_7358c1.py
│       │   │   │   │   ├── alpha_xauusd_754250.py
│       │   │   │   │   ├── alpha_xauusd_75d1dc.py
│       │   │   │   │   ├── alpha_xauusd_78210e.py
│       │   │   │   │   ├── alpha_xauusd_94ad53.py
│       │   │   │   │   ├── alpha_xauusd_96d26b.py
│       │   │   │   │   ├── alpha_xauusd_a6d004.py
│       │   │   │   │   ├── alpha_xauusd_a84e8d.py
│       │   │   │   │   ├── alpha_xauusd_b01980.py
│       │   │   │   │   ├── alpha_xauusd_b256b3.py
│       │   │   │   │   ├── alpha_xauusd_b68a11.py
│       │   │   │   │   ├── alpha_xauusd_bb1cfa.py
│       │   │   │   │   ├── alpha_xauusd_ca7c75.py
│       │   │   │   │   ├── alpha_xauusd_dfbed8.py
│       │   │   │   │   ├── alpha_xbrusd_042cd9.py
│       │   │   │   │   ├── alpha_xbrusd_0d2342.py
│       │   │   │   │   ├── alpha_xbrusd_0f1bd3.py
│       │   │   │   │   ├── alpha_xbrusd_176316.py
│       │   │   │   │   ├── alpha_xbrusd_3e1575.py
│       │   │   │   │   ├── alpha_xbrusd_3fe51d.py
│       │   │   │   │   ├── alpha_xbrusd_5af3d8.py
│       │   │   │   │   ├── alpha_xbrusd_6e7089.py
│       │   │   │   │   ├── alpha_xbrusd_87e8fa.py
│       │   │   │   │   ├── alpha_xbrusd_945526.py
│       │   │   │   │   ├── alpha_xbrusd_9e8436.py
│       │   │   │   │   ├── alpha_xbrusd_beb0e3.py
│       │   │   │   │   ├── alpha_xbrusd_d4aee9.py
│       │   │   │   │   ├── alpha_xbrusd_d7ab4a.py
│       │   │   │   │   ├── alpha_xbrusd_e55dbf.py
│       │   │   │   │   ├── alpha_xbrusd_e87a0b.py
│       │   │   │   │   ├── alpha_xbrusd_eadd31.py
│       │   │   │   │   ├── alpha_xbrusd_ec8f88.py
│       │   │   │   │   ├── alpha_xtiusd_09ce88.py
│       │   │   │   │   ├── alpha_xtiusd_16dc64.py
│       │   │   │   │   ├── alpha_xtiusd_1793d0.py
│       │   │   │   │   ├── alpha_xtiusd_2c4e39.py
│       │   │   │   │   ├── alpha_xtiusd_374fa7.py
│       │   │   │   │   ├── alpha_xtiusd_403155.py
│       │   │   │   │   ├── alpha_xtiusd_43ae5f.py
│       │   │   │   │   ├── alpha_xtiusd_487183.py
│       │   │   │   │   ├── alpha_xtiusd_592069.py
│       │   │   │   │   ├── alpha_xtiusd_83031c.py
│       │   │   │   │   ├── alpha_xtiusd_880297.py
│       │   │   │   │   ├── alpha_xtiusd_9ffd6d.py
│       │   │   │   │   ├── alpha_xtiusd_dae3f9.py
│       │   │   │   │   ├── alpha_xtiusd_f30ff5.py
│       │   │   │   │   └── alpha_xtiusd_fd5506.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base_strategy.py
│       │   │   │   ├── bb_volume_profile.py
│       │   │   │   ├── btc_donchian_breakout.py
│       │   │   │   ├── decay_monitor.py
│       │   │   │   ├── evidence_store.py
│       │   │   │   ├── gap_fade.py
│       │   │   │   ├── hypothesis_registry.py
│       │   │   │   ├── liquidity_sweep_edge.py
│       │   │   │   ├── pretrade_gate.py
│       │   │   │   ├── registry.py
│       │   │   │   ├── smc_fvg.py
│       │   │   │   ├── strategy_plugin.py
│       │   │   │   ├── tri_convergent_alpha.py
│       │   │   │   ├── tsm_momentum.py
│       │   │   │   ├── xau_trend_engine.py
│       │   │   │   └── xti_pairs_readiness.py
│       │   │   ├── subagent
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adhoc_manager.py
│       │   │   │   └── isolated_harness.py
│       │   │   ├── subagent_blackboard.py
│       │   │   ├── subagent_spawner.py
│       │   │   └── validators
│       │   │       ├── __init__.py
│       │   │       ├── adjudication_verifier.py
│       │   │       ├── adversarial_check.py
│       │   │       ├── confluence_verifier.py
│       │   │       ├── core_data_validator.py
│       │   │       ├── cross_timeframe_gate.py
│       │   │       ├── float_coercion.py
│       │   │       ├── fundamental_verifier.py
│       │   │       ├── in_harness_grounding.py
│       │   │       ├── market_snapshot.py
│       │   │       ├── output_verifier.py
│       │   │       └── precommit_gate.py
│       │   │   └── tools
│       │   │       ├── __init__.py
│       │   │       ├── base_handler.py
│       │   │       ├── composite_tools.py
│       │   │       ├── core
│       │   │       │   ├── __init__.py
│       │   │       │   ├── coercion.py
│       │   │       │   ├── decorator.py
│       │   │       │   ├── definition.py
│       │   │       │   ├── dispatcher.py
│       │   │       │   └── toolset_registry.py
│       │   │       ├── definitions
│       │   │       │   ├── __init__.py
│       │   │       │   ├── base.py
│       │   │       │   ├── groups.py
│       │   │       │   ├── intelligence.py
│       │   │       │   ├── macro.py
│       │   │       │   ├── market.py
│       │   │       │   ├── smc.py
│       │   │       │   ├── system.py
│       │   │       │   └── trading.py
│       │   │       ├── domain
│       │   │       │   ├── __init__.py
│       │   │       │   ├── browser_tool.py
│       │   │       │   ├── clarify_tool.py
│       │   │       │   ├── code_execution_tool.py
│       │   │       │   ├── code_search_tool.py
│       │   │       │   ├── computer_use_tool.py
│       │   │       │   ├── cron_tool.py
│       │   │       │   ├── delegate_tool.py
│       │   │       │   ├── execution_handlers.py
│       │   │       │   ├── file_tools.py
│       │   │       │   ├── kanban_tools.py
│       │   │       │   ├── macro_handlers.py
│       │   │       │   ├── multimodal_tools.py
│       │   │       │   ├── position_handlers.py
│       │   │       │   ├── sentiment_handlers.py
│       │   │       │   ├── skill_tools.py
│       │   │       │   ├── spill_reader_tool.py
│       │   │       │   ├── technical_handlers.py
│       │   │       │   ├── terminal_tools.py
│       │   │       │   ├── todo_tool.py
│       │   │       │   ├── tool_search_tools.py
│       │   │       │   └── web_tools.py
│       │   │       ├── environments
│       │   │       │   ├── __init__.py
│       │   │       │   ├── base_environment.py
│       │   │       │   ├── pty_query_responder.py
│       │   │       │   ├── tier1_inprocess.py
│       │   │       │   ├── tier2_kernel.py
│       │   │       │   └── tier3_docker.py
│       │   │       ├── executor.py
│       │   │       ├── file_patch_engine.py
│       │   │       ├── handlers
│       │   │       │   ├── __init__.py
│       │   │       │   ├── advanced_quant_tools.py
│       │   │       │   ├── analysis_submit.py
│       │   │       │   ├── analytical_query_builder.py
│       │   │       │   ├── behavioral_alert_tool.py
│       │   │       │   ├── broker_profile_tool.py
│       │   │       │   ├── category_loader.py
│       │   │       │   ├── chart_bridge_tools.py
│       │   │       │   ├── db_tools.py
│       │   │       │   ├── execution_handlers.py
│       │   │       │   ├── intelligence.py
│       │   │       │   ├── macro_data.py
│       │   │       │   ├── macro_tools.py
│       │   │       │   ├── market_data.py
│       │   │       │   ├── market_data_tools.py
│       │   │       │   ├── news_tools.py
│       │   │       │   ├── pattern_similarity_tools.py
│       │   │       │   ├── phase_transition.py
│       │   │       │   ├── position_mgmt.py
│       │   │       │   ├── ptc_handler.py
│       │   │       │   ├── scratchpad.py
│       │   │       │   ├── sentiment_data.py
│       │   │       │   ├── sentiment_tools.py
│       │   │       │   ├── skills_tools.py
│       │   │       │   ├── smc_tools.py
│       │   │       │   ├── system_info.py
│       │   │       │   ├── timesfm.py
│       │   │       │   ├── trade_intel
│       │   │       │   │   ├── __init__.py
│       │   │       │   │   ├── base.py
│       │   │       │   │   ├── debate.py
│       │   │       │   │   ├── operations.py
│       │   │       │   │   ├── performance.py
│       │   │       │   │   ├── registry.py
│       │   │       │   │   ├── reporting.py
│       │   │       │   │   └── simulation.py
│       │   │       │   ├── trade_intel.py
│       │   │       │   ├── trading_tools.py
│       │   │       │   └── verified_snapshot.py
│       │   │       ├── kernel
│       │   │       │   ├── __init__.py
│       │   │       │   ├── code_execution_rpc.py
│       │   │       │   ├── env_sanitizer.py
│       │   │       │   ├── output_spiller.py
│       │   │       │   ├── persistent_kernel.py
│       │   │       │   ├── persistent_session_kernel.py
│       │   │       │   └── sandbox_runner.py
│       │   │       ├── loop_guard.py
│       │   │       ├── mixins
│       │   │       │   ├── __init__.py
│       │   │       │   ├── analysis_submission.py
│       │   │       │   ├── analysis_validation.py
│       │   │       │   ├── base.py
│       │   │       │   ├── brief_submission.py
│       │   │       │   └── system_tools.py
│       │   │       ├── quant_sandbox
│       │   │       │   ├── __init__.py
│       │   │       │   └── rpc_server.py
│       │   │       ├── registry.py
│       │   │       ├── terminal_process_engine.py
│       │   │       ├── tool_catalog.py
│       │   │       ├── tool_executor.py
│       │   │       ├── tool_guardrails.py
│       │   │       ├── tool_plugin.py
│       │   │       ├── tool_registry.py
│       │   │       ├── tool_result_storage.py
│       │   │       ├── tool_search_engine.py
│       │   │       ├── tool_selector.py
│       │   │       ├── tool_spill.py
│       │   │       ├── tools_definitions.py
│       │   │       └── unified_registry.py
│       │   ├── graph
│       │   │   ├── __init__.py
│       │   │   ├── grounding.py
│       │   │   ├── nodes
│       │   │   │   ├── __init__.py
│       │   │   │   ├── data_node.py
│       │   │   │   ├── debate
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── bear_dissent_node.py
│       │   │   │   │   ├── bull_advocate_node.py
│       │   │   │   │   ├── debate_judge_node.py
│       │   │   │   │   ├── helpers.py
│       │   │   │   │   ├── rebuttal_node.py
│       │   │   │   │   ├── risk_evaluator_node.py
│       │   │   │   │   ├── round_robin_risk_nodes.py
│       │   │   │   │   └── subgraph.py
│       │   │   │   ├── debate_node.py
│       │   │   │   ├── execution_node.py
│       │   │   │   ├── fundamental_node.py
│       │   │   │   ├── per_asset_node.py
│       │   │   │   ├── plan_refinement_node.py
│       │   │   │   ├── reflection_node.py
│       │   │   │   ├── risk
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── level_synthesizer.py
│       │   │   │   │   ├── portfolio_synthesis.py
│       │   │   │   │   ├── proposal_notifier.py
│       │   │   │   │   ├── quant_arbitration.py
│       │   │   │   │   └── rejection_auditor.py
│       │   │   │   ├── risk_gate_node.py
│       │   │   │   └── state_pruner.py
│       │   │   ├── reactive_graph.py
│       │   │   ├── state.py
│       │   │   ├── team_compiler.py
│       │   │   └── workflow.py
│       │   ├── backtest
│       │   │   ├── __init__.py
│       │   │   ├── alpha_validation.py
│       │   │   ├── batch_scenario_runner.py
│       │   │   ├── benchmark_tracker.py
│       │   │   ├── decision_memory.py
│       │   │   ├── engines
│       │   │   │   ├── __init__.py
│       │   │   │   ├── crypto_engine.py
│       │   │   │   ├── equity_engine.py
│       │   │   │   ├── forex_engine.py
│       │   │   │   └── futures_engine.py
│       │   │   ├── fixtures
│       │   │   │   ├── full_replay_candles.json
│       │   │   │   └── replay_candles.json
│       │   │   ├── isolated_strategy_harness.py
│       │   │   ├── matrix_alignment.py
│       │   │   ├── monte_carlo_engine.py
│       │   │   ├── offline_signal_engine.py
│       │   │   ├── outcome_evaluator.py
│       │   │   ├── point_in_time_engine.py
│       │   │   ├── report_generator.py
│       │   │   ├── run_card.py
│       │   │   ├── statistical_tests.py
│       │   │   ├── time_machine.py
│       │   │   └── walk_forward_engine.py
│       │   ├── benchmark
│       │   │   ├── __init__.py
│       │   │   ├── alpha_arena.py
│       │   │   ├── config.py
│       │   │   ├── db_access.py
│       │   │   ├── db_models.py
│       │   │   ├── deterministic.py
│       │   │   ├── fixture_loader.py
│       │   │   ├── fixtures
│       │   │   ├── invoker.py
│       │   │   ├── judge.py
│       │   │   ├── model_registry.py
│       │   │   ├── paired_evaluator.py
│       │   │   ├── pricing.py
│       │   │   ├── prompt_evolution.py
│       │   │   ├── report.py
│       │   │   ├── results
│       │   │   ├── runner.py
│       │   │   ├── system_one_scorer.py
│       │   │   ├── task_specs.py
│       │   │   ├── token_drift_tracker.py
│       │   │   └── trade_trajectory_logger.py
│       │   ├── bootstrap.py
│       │   ├── evals
│       │   │   ├── __init__.py
│       │   │   ├── eval_metrics.py
│       │   │   ├── eval_runner.py
│       │   │   ├── hostile_market_probe.py
│       │   │   ├── oracles
│       │   │   │   ├── __init__.py
│       │   │   │   ├── macro_regime_oracle.py
│       │   │   │   ├── risk_compliance_oracle.py
│       │   │   │   ├── smc_geometry_oracle.py
│       │   │   │   ├── tool_safety_oracle.py
│       │   │   │   └── trade_discipline_oracle.py
│       │   │   ├── runner.py
│       │   │   └── simulation_clock.py
│       │   ├── execution
│       │   │   ├── __init__.py
│       │   │   ├── broker_registry.py
│       │   │   ├── effect_gate.py
│       │   │   ├── execution_service.py
│       │   │   ├── health_check.py
│       │   │   └── service
│       │   │       ├── __init__.py
│       │   │       ├── emergency_manager.py
│       │   │       ├── executors
│       │   │       │   ├── __init__.py
│       │   │       │   ├── analysis_executor.py
│       │   │       │   ├── analysis_preflight.py
│       │   │       │   ├── analysis_submission.py
│       │   │       │   ├── base.py
│       │   │       │   ├── paired_executor.py
│       │   │       │   ├── preplanned_executor.py
│       │   │       │   ├── proposal_executor.py
│       │   │       │   └── tranche_executor.py
│       │   │       ├── multi_account_adapter.py
│       │   │       ├── order_executor.py
│       │   │       ├── order_lifecycle_service.py
│       │   │       ├── position_synchronizer.py
│       │   │       ├── reconciliation.py
│       │   │       ├── risk_evaluator.py
│       │   │       ├── self_healing_executor.py
│       │   │       └── trade_confirm.py
│       │   ├── governance
│       │   │   ├── __init__.py
│       │   │   └── run_manifest.py
│       │   ├── harness
│       │   │   ├── __init__.py
│       │   │   ├── adapters
│       │   │   │   ├── __init__.py
│       │   │   │   └── functional_adapter.py
│       │   │   ├── context.py
│       │   │   ├── contract.py
│       │   │   ├── engine.py
│       │   │   ├── installer.py
│       │   │   └── lifecycle.py
│       │   ├── main.py
│       │   ├── plugins
│       │   │   ├── __init__.py
│       │   │   ├── alerts
│       │   │   │   └── discord_alert
│       │   │   ├── analysis_pipelines
│       │   │   │   ├── macro_to_asset
│       │   │   │   └── technical_scalping
│       │   │   ├── brokers
│       │   │   │   ├── mt5_local
│       │   │   │   └── paper_trading
│       │   │   ├── indicators
│       │   │   │   └── custom_indicator
│       │   │   ├── engine
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adapters
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   └── functional_adapter.py
│       │   │   │   ├── context.py
│       │   │   │   ├── contract.py
│       │   │   │   ├── engine.py
│       │   │   │   ├── installer.py
│       │   │   │   └── lifecycle.py
│       │   │   ├── kernel.py
│       │   │   ├── loader.py
│       │   │   ├── manifest.py
│       │   │   └── scrapers
│       │   │       └── example_scraper
│       │   ├── run_benchmark.py
│       │   ├── scheduler
│       │   │   ├── __init__.py
│       │   │   ├── active_calendar_poller.py
│       │   │   ├── adhoc_proxy.py
│       │   │   ├── alpha_discovery_scheduler.py
│       │   │   ├── cron_nlp_parser.py
│       │   │   ├── cycle_scheduler.py
│       │   │   ├── detached_cron_worker.py
│       │   │   ├── digest_slice_scheduler.py
│       │   │   ├── edge_strategy_runner.py
│       │   │   ├── flash_crash_detector.py
│       │   │   ├── graph_cycle_scheduler.py
│       │   │   ├── macro_data_scheduler.py
│       │   │   ├── market_data_scheduler.py
│       │   │   ├── news_watcher.py
│       │   │   ├── order_reconciler.py
│       │   │   ├── playbook_curator.py
│       │   │   ├── position_exit_reviewer.py
│       │   │   ├── position_guardian.py
│       │   │   ├── position_supervisor.py
│       │   │   ├── post_release_analyzer.py
│       │   │   ├── scraper_runner.py
│       │   │   ├── strategy_synthesis_scheduler.py
│       │   │   ├── task_plugin.py
│       │   │   ├── trailing_stop_manager.py
│       │   │   ├── trigger_checker.py
│       │   │   ├── unified_cron_engine.py
│       │   │   └── universal_cron_scheduler.py
│       │   ├── services
│       │   │   ├── __init__.py
│       │   │   ├── general_harness_service.py
│       │   │   ├── market_data_service.py
│       │   │   ├── market_intel_service.py
│       │   │   ├── portfolio_service.py
│       │   │   ├── system_status_service.py
│       │   │   └── trading_service.py
│       │   └── skills
│       │       ├── __init__.py
│       │       ├── continuous_learning.py
│       │       ├── curator.py
│       │       ├── loader.py
│       │       ├── skill_manager.py
│       │       ├── skills_guard.py
│       │       ├── skills_hub.py
│       │       ├── trading_skill_linter.py
│       │       ├── unified_runtime.py
│       │       └── usage_tracker.py
│       ├── core
│       │   ├── __init__.py
│       │   ├── exceptions.py
│       │   ├── paths.py
│       │   ├── analytics
│       │   │   ├── __init__.py
│       │   │   ├── adversarial_outcome_tracker.py
│       │   │   ├── agent_performance_monitor.py
│       │   │   ├── analysis_tracker.py
│       │   │   ├── cds_outcome_tracker.py
│       │   │   ├── chart_generator.py
│       │   │   ├── cost_tracker.py
│       │   │   ├── edge_tracker.py
│       │   │   ├── models_dev_sync.py
│       │   │   ├── news_classification_tracker.py
│       │   │   ├── paper_tracker.py
│       │   │   ├── pdf_report_generator.py
│       │   │   ├── performance_reviewer.py
│       │   │   ├── pricing.py
│       │   │   ├── specialist_tracker.py
│       │   │   ├── strategy_edge_tracker.py
│       │   │   ├── token_auditor.py
│       │   │   └── trade_autopsy.py
│       │   ├── calibration
│       │   │   ├── __init__.py
│       │   │   ├── cds_threshold_calibrator.py
│       │   │   ├── confidence_calibrator.py
│       │   │   ├── cot_thresholds.py
│       │   │   └── prescreen_calibrator.py
│       │   ├── config
│       │   │   ├── __init__.py
│       │   │   ├── atomic_writer.py
│       │   │   ├── config_manager.py
│       │   │   ├── config_migrations.py
│       │   │   ├── hot_reload.py
│       │   │   ├── key_validator.py
│       │   │   ├── migrations.py
│       │   │   ├── profile_applicator.py
│       │   │   ├── protocols.py
│       │   │   ├── schemas.py
│       │   │   ├── security.py
│       │   │   └── settings.py
│       │   ├── primitives
│       │   │   ├── __init__.py
│       │   │   ├── clock.py
│       │   │   ├── constants.py
│       │   │   ├── content_distiller.py
│       │   │   ├── event_bus.py
│       │   │   ├── jev_primitives.py
│       │   │   ├── prompt_primitives.py
│       │   │   ├── retry.py
│       │   │   ├── turn_marker.py
│       │   │   └── worktree.py
│       │   ├── security
│       │   │   ├── __init__.py
│       │   │   ├── credential_vault.py
│       │   │   ├── nt_guard.py
│       │   │   ├── prompt_injection_scanner.py
│       │   │   ├── ssrf_guard.py
│       │   │   ├── supply_chain_quarantine.py
│       │   │   ├── terminal_guard.py
│       │   │   ├── threat_detector.py
│       │   │   └── threat_scanner.py
│       │   ├── streaming
│       │   │   ├── __init__.py
│       │   │   ├── sanitizer.py
│       │   │   ├── stream_scrubber.py
│       │   │   └── streaming_lease.py
│       │   ├── telemetry
│       │   │   ├── __init__.py
│       │   │   ├── activity_logger.py
│       │   │   ├── delegation_live_log.py
│       │   │   ├── doctor.py
│       │   │   ├── metrics_exporter.py
│       │   │   ├── operator_feedback.py
│       │   │   ├── report_writer.py
│       │   │   ├── reporting
│       │   │   │   ├── __init__.py
│       │   │   │   ├── docx_report_generator.py
│       │   │   │   ├── pdf_report_generator.py
│       │   │   │   ├── pptx_deck_generator.py
│       │   │   │   └── tearsheet_generator.py
│       │   │   ├── run_card.py
│       │   │   ├── sinks.py
│       │   │   ├── token_budgeter.py
│       │   │   └── tracing
│       │   │       ├── __init__.py
│       │   │       ├── context.py
│       │   │       └── exporters.py
│       │   └── validation
│       │       ├── __init__.py
│       │       ├── data_temporal_validator.py
│       │       ├── data_validator.py
│       │       ├── indicator_sanitizer.py
│       │       └── tool_response_validator.py
│       │       ├── activity_logger.py
│       │       ├── delegation_live_log.py
│       │       ├── metrics_exporter.py
│       │       ├── operator_feedback.py
│       │       ├── report_writer.py
│       │       ├── reporting
│       │       │   ├── __init__.py
│       │       │   ├── docx_report_generator.py
│       │       │   ├── pdf_report_generator.py
│       │       │   ├── pptx_deck_generator.py
│       │       │   └── tearsheet_generator.py
│       │       ├── run_card.py
│       │       ├── sinks.py
│       │       ├── token_budgeter.py
│       │       ├── tracing
│       │       │   ├── __init__.py
│       │       │   ├── context.py
│       │       │   ├── exporters.py
│       │       │   ├── otlp_exporter.py
│       │       │   ├── spans.py
│       │       │   └── tracer.py
│       │       └── trading_cycle_event_log.py
│       ├── domain
│       │   ├── __init__.py
│       │   ├── entities
│       │   │   ├── __init__.py
│       │   │   ├── order.py
│       │   │   ├── order_status.py
│       │   │   ├── position.py
│       │   │   ├── snapshots.py
│       │   │   └── trade_trigger.py
│       │   ├── execution
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── broker_plugin.py
│       │   │   ├── order_creator.py
│       │   │   ├── order_emulator.py
│       │   │   ├── sizing_calculator.py
│       │   │   ├── state_machine.py
│       │   │   └── verification_engine.py
│       │   ├── indicators
│       │   │   ├── __init__.py
│       │   ├── market
│       │   │   ├── __init__.py
│       │   │   ├── bias_utils.py
│       │   │   ├── brent_yfinance.py
│       │   │   ├── currency_utils.py
│       │   │   ├── direction.py
│       │   │   ├── dynamic_correlation.py
│       │   │   ├── instrument_identity.py
│       │   │   ├── news_impact_keywords.py
│       │   │   ├── session_info.py
│       │   │   ├── swap_estimator.py
│       │   │   └── usd_strength_proxy.py
│       │   │   ├── alpha_zoo
│       │   │   │   ├── __init__.py
│       │   │   │   ├── academic_factors.py
│       │   │   │   ├── alpha101.py
│       │   │   │   ├── factors
│       │   │   │   ├── fundamental_factors.py
│       │   │   │   ├── meta.py
│       │   │   │   ├── microstructure_factors.py
│       │   │   │   ├── qlib158.py
│       │   │   │   ├── registry.py
│       │   │   │   └── vector_factor_engine.py
│       │   │   ├── candlestick_patterns.py
│       │   │   ├── chart_patterns.py
│       │   │   ├── divergence.py
│       │   │   ├── econometrics.py
│       │   │   ├── factor_primitives.py
│       │   │   ├── micro_alpha_zoo.py
│       │   │   ├── microstructure.py
│       │   │   ├── order_flow.py
│       │   │   ├── pattern_similarity
│       │   │   │   ├── __init__.py
│       │   │   │   ├── context_scorer.py
│       │   │   │   ├── context_verifier.py
│       │   │   │   ├── engine.py
│       │   │   │   ├── feature_extractor.py
│       │   │   │   ├── models.py
│       │   │   │   ├── normalizer.py
│       │   │   │   ├── outcome_analyzer.py
│       │   │   │   └── scanner.py
│       │   │   ├── regime_detector.py
│       │   │   ├── smc_advanced.py
│       │   │   ├── structure.py
│       │   │   └── technical.py
│       │   └── risk
│       │       ├── __init__.py
│       │       ├── approval_hub.py
│       │       ├── correlation_matrix.py
│       │       ├── crypto_audit_ledger.py
│       │       ├── evaluators
│       │       │   ├── __init__.py
│       │       │   ├── base.py
│       │       │   ├── execution_checks.py
│       │       │   ├── intelligence_checks.py
│       │       │   ├── market_checks.py
│       │       │   └── portfolio_checks.py
│       │       ├── execution_simulator.py
│       │       ├── instruments
│       │       │   ├── __init__.py
│       │       │   └── instruments.py
│       │       ├── invariants
│       │       │   ├── __init__.py
│       │       │   ├── position_count_invariant.py
│       │       │   ├── registry.py
│       │       │   ├── risk_gate_invariant.py
│       │       │   └── state_immutability_invariant.py
│       │       ├── pending_action.py
│       │       ├── portfolio_correlation_gate.py
│       │       ├── portfolio_optimizer.py
│       │       ├── ports.py
│       │       ├── position_sizing.py
│       │       ├── risk_gate.py
│       │       ├── risk_rule_plugin.py
│       │       └── trade_proposal.py
│       ├── infrastructure
│       │   ├── __init__.py
│       │   ├── api
│       │   │   ├── __init__.py
│       │   │   ├── claude_rate_limiter.py
│       │   │   ├── credential_pool.py
│       │   │   ├── credit_balance_tracker.py
│       │   │   ├── gemini_rate_limiter.py
│       │   │   ├── groq_rate_limiter.py
│       │   │   ├── http_retry.py
│       │   │   ├── openrouter_rate_limiter.py
│       │   │   └── streaming.py
│       │   ├── brokers
│       │   │   ├── __init__.py
│       │   │   ├── approval_transport.py
│       │   │   ├── audit_logger.py
│       │   │   ├── broker_adapter.py
│       │   │   ├── ea_bridge
│       │   │   │   ├── __init__.py
│       │   │   │   ├── contract_types.py
│       │   │   │   ├── file_protocol.py
│       │   │   │   ├── mql5_bridge.py
│       │   │   │   ├── rate_limiter.py
│       │   │   │   ├── types.py
│       │   │   │   └── watchdog.py
│       │   │   ├── ibkr_adapter.py
│       │   │   ├── idempotency_guard.py
│       │   │   ├── mt5_client.py
│       │   │   ├── mt5_compat.py
│       │   │   ├── paper_tracker.py
│       │   │   └── rate_throttler.py
│       │   ├── credentials
│       │   │   ├── __init__.py
│       │   │   ├── credential_pool.py
│       │   │   └── error_taxonomy.py
│       │   ├── database
│       │   │   ├── __init__.py
│       │   │   ├── base_repository.py
│       │   │   ├── clean_stale_proposals.py
│       │   │   ├── compat.py
│       │   │   ├── connection.py
│       │   │   ├── db.py
│       │   │   ├── domain_models
│       │   │   │   ├── __init__.py
│       │   │   │   ├── activity_logs.py
│       │   │   │   ├── base.py
│       │   │   │   ├── order_history.py
│       │   │   │   ├── positions.py
│       │   │   │   ├── price_data.py
│       │   │   │   ├── system_config.py
│       │   │   │   └── trade_proposals.py
│       │   │   ├── emergency_audit.py
│       │   │   ├── engine.py
│       │   │   ├── fts5_tokenizer.py
│       │   │   ├── migrations
│       │   │   │   ├── env.py
│       │   │   │   ├── script.py.mako
│       │   │   │   └── versions
│       │   │   │       ├── 0006_consolidate_and_numeric.py
│       │   │   │       ├── 001_initial_schema.py
│       │   │   │       ├── 002_add_fts5_virtual_tables.py
│       │   │   │       ├── 003_add_session_wal_and_pruning.py
│       │   │   │       ├── 004_add_user_market_intel.py
│       │   │   │       ├── 005_add_phase2_compression.py
│       │   │   │       ├── 006_add_phase3_runtime.py
│       │   │   │       ├── 007_add_phase4_rewind.py
│       │   │   │       └── 008_foreign_key_audit.py
│       │   │   ├── models.py
│       │   │   ├── phase2_compaction.py
│       │   │   ├── phase2_prune_ledger.py
│       │   │   ├── phase3_runtime.py
│       │   │   ├── prune_database.py
│       │   │   ├── repositories
│       │   │   │   ├── __init__.py
│       │   │   │   ├── activity_log_repository.py
│       │   │   │   ├── position_repository.py
│       │   │   │   ├── system_config_repository.py
│       │   │   │   └── trade_proposal_repository.py
│       │   │   ├── session_db.py
│       │   │   ├── session_db_wal.py
│       │   │   ├── sqlite_concurrency.py
│       │   │   └── user_market_intel.py
│       │   ├── data_ingestion
│       │   │   ├── __init__.py
│       │   │   ├── scrapers
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base_scraper.py
│       │   │   │   ├── calendar
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── calendar_forexfactory.py
│       │   │   │   │   └── calendar_investing.py
│       │   │   │   ├── macro
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── bank_indonesia.py
│       │   │   │   │   ├── bps_stats.py
│       │   │   │   │   ├── central_bank_doc_scraper.py
│       │   │   │   │   ├── cot_scraper.py
│       │   │   │   │   ├── esdm_scraper.py
│       │   │   │   │   ├── fed_calendar.py
│       │   │   │   │   ├── fitch_ratings.py
│       │   │   │   │   ├── moody_ratings.py
│       │   │   │   │   ├── s_and_p_ratings.py
│       │   │   │   │   └── sovereign_yield_spreads.py
│       │   │   │   ├── news
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── base_news.py
│       │   │   │   │   ├── bisnis_com.py
│       │   │   │   │   ├── bloomberg_commodities.py
│       │   │   │   │   ├── cnbc_indonesia.py
│       │   │   │   │   ├── content_fetcher.py
│       │   │   │   │   ├── detik_finance.py
│       │   │   │   │   ├── investing_news.py
│       │   │   │   │   ├── kontan.py
│       │   │   │   │   ├── reuters_commodities.py
│       │   │   │   │   └── web_search.py
│       │   │   │   ├── playwright_scraper.py
│       │   │   │   ├── scraper_factory.py
│       │   │   │   ├── sentiment
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── cme_fedwatch.py
│       │   │   │   │   ├── fear_and_greed.py
│       │   │   │   │   ├── fxstreet_sentiment.py
│       │   │   │   │   ├── myfxbook_sentiment.py
│       │   │   │   │   └── retail_sentiment.py
│       │   │   │   └── social
│       │   │   │       ├── __init__.py
│       │   │   │       ├── stocktwits.py
│       │   │   │       ├── twitter_nitter.py
│       │   │   │       └── twitter_scraper.py
│       │   │   └── sources
│       │   │       ├── __init__.py
│       │   │       ├── base_fetcher.py
│       │   │       ├── bi_rate.py
│       │   │       ├── cftc_cot.py
│       │   │       ├── crypto_fear_greed.py
│       │   │       ├── dxy_fred.py
│       │   │       ├── dxy_yfinance.py
│       │   │       ├── eia_petroleum.py
│       │   │       ├── gold_rates.py
│       │   │       ├── icdx_data.py
│       │   │       ├── idr_interbank.py
│       │   │       ├── idx_market.py
│       │   │       ├── metals_rates.py
│       │   │       ├── myfxbook_api.py
│       │   │       ├── news_fetcher.py
│       │   │       ├── oil_price.py
│       │   │       ├── oil_rates.py
│       │   │       ├── s_and_p_commodity.py
│       │   │       ├── treasury_yields.py
│       │   │       ├── us_cpi.py
│       │   │       ├── us_nonfarm_payrolls.py
│       │   │       ├── us_retail_sales.py
│       │   │       ├── vix_fetcher.py
│       │   │       ├── vix_yfinance.py
│       │   │       └── world_bank.py
│       │   ├── graph
│       │   │   ├── __init__.py
│       │   │   └── checkpointers
│       │   │       ├── __init__.py
│       │   │       ├── dual_checkpointer.py
│       │   │       └── sqlite_checkpointer.py
│       │   ├── ml
│       │   │   ├── __init__.py
│       │   │   └── timesfm_engine.py
│       │   ├── providers
│       │   │   ├── __init__.py
│       │   │   ├── ai21_provider.py
│       │   │   ├── anthropic_provider.py
│       │   │   ├── bedrock_provider.py
│       │   │   ├── cerebras_provider.py
│       │   │   ├── circuit_breaker.py
│       │   │   ├── cohere_provider.py
│       │   │   ├── deepseek_provider.py
│       │   │   ├── fireworks_provider.py
│       │   │   ├── gemini_provider.py
│       │   │   ├── groq_provider.py
│       │   │   ├── huggingface_provider.py
│       │   │   ├── llm_factory.py
│       │   │   ├── mistral_provider.py
│       │   │   ├── mock_provider.py
│       │   │   ├── ollama_provider.py
│       │   │   ├── openai_provider.py
│       │   │   ├── openrouter_provider.py
│       │   │   ├── perplexity_provider.py
│       │   │   ├── provider_failover_classifier.py
│       │   │   ├── provider_registry.py
│       │   │   ├── request_budget.py
│       │   │   ├── samba_provider.py
│       │   │   ├── streaming_think_scrubber.py
│       │   │   ├── together_provider.py
│       │   ├── mcp
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── dispatcher.py
│       │   │   ├── event_bridge.py
│       │   │   ├── mcp_death_supervisor.py
│       │   │   ├── mcp_schema_cache.py
│       │   │   ├── mcp_serve.py
│       │   │   ├── oauth_handler.py
│       │   │   ├── protocol.py
│       │   │   ├── server.py
│       │   │   └── servers
│       │   │       ├── __init__.py
│       │   │       ├── excel_server.py
│       │   │       ├── fetch_server.py
│       │   │       ├── filesystem_server.py
│       │   │       ├── google_sheets_server.py
│       │   │       └── sqlite_server.py
│       │   ├── notifications
│       │   │   ├── __init__.py
│       │   │   ├── discord_notifier.py
│       │   │   └── telegram_notifier.py
│       │   ├── infra
│       │   │   ├── __init__.py
│       │   │   ├── audit_settings_keys.py
│       │   │   ├── container.py
│       │   │   ├── db_backup.py
│       │   │   ├── discord_notifier.py
│       │   │   ├── env_file_manager.py
│       │   │   ├── event_loop.py
│       │   │   ├── log_redactor.py
│       │   │   ├── notifier.py
│       │   │   ├── paths.py
│       │   │   ├── platform_compat.py
│       │   │   └── worktree_manager.py
│       │   ├── llm
│       │   │   ├── __init__.py
│       │   │   ├── rate_limiting
│       │   │   │   ├── __init__.py
│       │   │   │   ├── claude_rate_limiter.py
│       │   │   │   ├── credential_pool.py
│       │   │   │   ├── credit_balance_tracker.py
│       │   │   │   ├── gemini_rate_limiter.py
│       │   │   │   ├── groq_rate_limiter.py
│       │   │   │   ├── http_retry.py
│       │   │   │   ├── openrouter_rate_limiter.py
│       │   │   │   └── streaming.py
│       │   │   ├── adaptive_thinking.py
│       │   │   ├── cache_breakpoint_manager.py
│       │   │   ├── cache_miss_detector.py
│       │   │   ├── caveman_compressor.py
│       │   │   ├── constrained_sampling.py
│       │   │   ├── context_compaction.py
│       │   │   ├── context_compressor.py
│       │   │   ├── context_tracker.py
│       │   │   ├── credential_pool.py
│       │   │   ├── cycle_budget_guard.py
│       │   │   ├── data_dedup.py
│       │   │   ├── deferred_dispatcher.py
│       │   │   ├── embedding.py
│       │   │   ├── llmlingua_compressor.py
│       │   │   ├── memory_compressor.py
│       │   │   ├── model_capabilities.py
│       │   │   ├── model_discipline.py
│       │   │   ├── prompt_ab_test.py
│       │   │   ├── prompt_assembler.py
│       │   │   ├── prompt_caching.py
│       │   │   ├── prompt_compressor.py
│       │   │   ├── prompt_disciplines.py
│       │   │   ├── prompt_tiering.py
│       │   │   ├── prompt_tiers.py
│       │   │   ├── semantic_cache.py
│       │   │   ├── spill_subsystem.py
│       │   │   └── tool_condenser.py
│       │   ├── storage
│       │   │   ├── __init__.py
│       │   │   ├── journal_helper.py
│       │   │   └── spill_store.py
│       │   └── sandboxes
│       │       ├── __init__.py
│       │       ├── base.py
│       │       ├── docker_backend.py
│       │       ├── local_backend.py
│       │       └── pty_bridge.py
│       └── interfaces
│           ├── __init__.py
│           ├── cli
│           │   ├── __init__.py
│           │   ├── analysis_tree.py
│           │   ├── busy_input.py
│           │   ├── chat
│           │   │   ├── __init__.py
│           │   │   ├── commands.py
│           │   │   ├── completer.py
│           │   │   ├── prompt.py
│           │   │   ├── renderer.py
│           │   │   ├── session.py
│           │   │   └── theme.py
│           │   ├── doctor.py
│           │   ├── main.py
│           │   ├── onboarding_trader.py
│           │   ├── overlays
│           │   │   ├── __init__.py
│           │   │   ├── approval_modal.py
│           │   │   └── plugin_install_modal.py
│           │   ├── platform_compat.py
│           │   ├── plugins.py
│           │   ├── profile_manager.py
│           │   ├── setup_wizard.py
│           │   ├── sparklines.py
│           │   ├── subcommands
│           │   │   ├── __init__.py
│           │   │   ├── base.py
│           │   │   ├── daemon.py
│           │   │   ├── mcp.py
│           │   │   ├── runcard.py
│           │   │   ├── simulation.py
│           │   │   ├── trading.py
│           │   │   └── upgrade.py
│           │   ├── theme.py
│           │   ├── tui.py
│           │   ├── tui_chat.py
│           │   └── width_budget.py
│           ├── dashboard
│           │   ├── __init__.py
│           │   ├── api.py
│           │   ├── log_streamer.py
│           │   ├── pty_bridge.py
│           │   ├── rbac.py
│           │   ├── routes
│           │   │   ├── __init__.py
│           │   │   ├── backtest.py
│           │   │   ├── benchmark.py
│           │   │   ├── common.py
│           │   │   ├── config.py
│           │   │   ├── intelligence.py
│           │   │   ├── mcp_server.py
│           │   │   ├── memory.py
│           │   │   ├── observability.py
│           │   │   ├── plugins.py
│           │   │   ├── system.py
│           │   │   ├── tokens.py
│           │   │   ├── trace_search.py
│           │   │   ├── trading.py
│           │   │   └── websocket.py
│           │   └── ws_ticket.py
│           ├── gateway
│           │   ├── __init__.py
│           │   ├── acp_server.py
│           │   ├── api_server.py
│           │   ├── bot_loop_guard.py
│           │   ├── channel_router.py
│           │   ├── delivery_ledger.py
│           │   ├── omnichannel_router.py
│           │   ├── omnichannel_streamer.py
│           │   ├── pairing.py
│           │   ├── platform_base.py
│           │   ├── platforms
│           │   │   ├── __init__.py
│           │   │   ├── discord_adapter.py
│           │   │   ├── slack_adapter.py
│           │   │   ├── telegram_adapter.py
│           │   │   └── webhook_adapter.py
│           │   ├── stream_consumer.py
│           │   ├── turn_lease.py
│           │   └── webhook_ingress.py
│           └── telegram
│               ├── __init__.py
│               ├── base.py
│               ├── bot.py
│               ├── chat_agent.py
│               ├── chat_compaction.py
│               ├── chat_tool_router.py
│               ├── command_router.py
│               ├── formatters
│               │   ├── __init__.py
│               │   └── text_builders.py
│               ├── fuzzy_router.py
│               ├── handlers
│               │   ├── __init__.py
│               │   ├── admin_commands.py
│               │   ├── callback_handler.py
│               │   ├── market_commands.py
│               │   ├── media_handlers.py
│               │   ├── system_commands.py
│               │   └── trading_commands.py
│               ├── message_formatter.py
│               ├── routers
│               │   ├── __init__.py
│               │   ├── admin_router.py
│               │   ├── market_router.py
│               │   ├── quant_router.py
│               │   ├── risk_router.py
│               │   └── trading_router.py
│               ├── sanitizer.py
│               ├── topic_manager.py
│               ├── voice_handler.py
│               └── voice_safety_gate.py
│           └── workspace
│               ├── __init__.py
│               └── journal_helper.py
└── tests
