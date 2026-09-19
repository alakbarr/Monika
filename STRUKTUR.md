# ==================================================
# CODEBASE DIRECTORY STRUCTURE — MONIKA (MT5 TRADING AGENT)
# ==================================================

Monika/
├── .github
│   ├── workflows
│   │   └── ci.yml
│   ├── ISSUE_TEMPLATE
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── pull_request_template.md
├── .dockerignore
├── .env.example
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── contoh_pertanyaan.md
├── DESIGN.md
├── Dockerfile
├── docker-compose.yml
├── docs
│   └── images
│       ├── 01_trading_desk_overview.png
│       ├── 02_trading_desk_signals.png
│       ├── 03_trading_desk_market.png
│       ├── 04_market_intelligence_pipeline_dag.png
│       ├── 05_market_intelligence_macro_brief.png
│       ├── 06_ledger_risk_limits.png
│       ├── 07_ledger_llm_token_audit.png
│       ├── 08_telegraph_desk_console_chat.png
│       ├── 09_system_configuration.png
│       └── 10_terminal_ui_tui.png
├── GEMINI.md
├── INDEX.md
├── LICENSE
├── Makefile
├── pyproject.toml
├── pyrightconfig.json
├── pytest.ini
├── README.md
├── SECURITY.md
├── STRUKTUR.md
├── scripts
│   ├── deep_dependency_audit.py
│   ├── download_timesfm_weights.py
│   ├── fix_venv_entrypoints.py
│   ├── generate_model_quadrant.py
│   ├── generate_showcase_screenshots.py
│   ├── reset_paper_trades.py
│   └── update_index_toc.py
└── trading-agent
    ├── docker-compose.yml
    ├── docker-compose.linux.yml
    ├── Dockerfile
    ├── main.py
    ├── Makefile
    ├── README.md
    ├── run_benchmark.py
    ├── spesifikasi_final_ai_trading_agent.md
    ├── start_agent.bat
    ├── start_agent.sh
    ├── stop_agent.bat
    ├── systemd
    │   └── tradeagent.service
    ├── cli
    │   ├── __init__.py
    │   ├── analysis_tree.py
    │   ├── busy_input.py
    │   ├── doctor.py
    │   ├── main.py
    │   ├── platform_compat.py
    │   ├── profile_manager.py
    │   ├── setup_wizard.py
    │   ├── sparklines.py
    │   ├── theme.py
    │   ├── tui.py
    │   └── tui_chat.py
    ├── agent
    │   ├── __init__.py
    │   ├── agent_loop.py
    │   ├── startup_checks.py
    │   ├── task_registry.py
    │   └── monitors
    │       ├── __init__.py
    │       ├── db_health.py
    │       ├── drawdown_monitor.py
    │       ├── paper_trade_monitor.py
    │       ├── scraper_loop.py
    │       └── startup_watchdog.py
    ├── config
    │   ├── atomic_writer.py
    │   ├── hot_reload.py
    │   ├── key_validator.py
    │   ├── migrations.py
    │   ├── schemas.py
    │   ├── settings.py
    │   └── settings.yaml
    ├── analysis
    │   ├── event_broadcaster.py
    │   ├── scenario_tree.py
    │   ├── subagent_blackboard.py
    │   ├── subagent_spawner.py
    │   ├── arbitration
    │   │   └── signal_arbitrator.py
    │   ├── calculators
    │   │   ├── adaptive_policy.py
    │   │   ├── confluence_calculator.py
    │   │   ├── daily_range_calculator.py
    │   │   ├── economic_surprise.py
    │   │   ├── intraday_level_optimizer.py
    │   │   ├── invariant_calculator.py
    │   │   ├── liquidity_sweep_detector.py
    │   │   ├── macro_bias_filter.py
    │   │   ├── macro_priced_in_calculator.py
    │   │   ├── regime_classifier.py
    │   │   ├── stage1_priced_in.py
    │   │   ├── timesfm_alpha.py
    │   │   ├── unified_threshold_calculator.py
    │   │   └── volume_profile.py
    │   ├── debate
    │   │   ├── adjustment_validator.py
    │   │   ├── aggressive_risk_llm.py
    │   │   ├── bear_analyst.py
    │   │   ├── bull_analyst.py
    │   │   ├── conservative_risk_llm.py
    │   │   ├── deterministic_risk.py
    │   │   ├── fact_sheet.py
    │   │   ├── investment_judge.py
    │   │   ├── macro_bear_analyst.py
    │   │   ├── macro_bull_analyst.py
    │   │   ├── macro_debate_validator.py
    │   │   ├── macro_judge.py
    │   │   ├── neutral_risk_llm.py
    │   │   └── portfolio_manager.py
    │   ├── grounding
    │   │   ├── __init__.py
    │   │   └── provenance_tagger.py
    │   ├── harness
    │   │   ├── __init__.py
    │   │   ├── agent_harness.py
    │   │   ├── context_compressor.py
    │   │   ├── error_classifier.py
    │   │   ├── harness_state.py
    │   │   ├── message_repair.py
    │   │   ├── stall_guard.py
    │   │   ├── structured_output.py
    │   │   ├── symbol_segment_planner.py
    │   │   ├── tool_batch_planner.py
    │   │   ├── tool_repair.py
    │   │   ├── trade_stop_gates.py
    │   │   └── verification_evidence_ledger.py
    │   ├── memory
    │   │   ├── alpha_calculator.py
    │   │   ├── background_review.py
    │   │   ├── chronicle_writer.py
    │   │   ├── decision_log.py
    │   │   ├── failure_taxonomy.py
    │   │   ├── layered_memory.py
    │   │   ├── lesson_consolidator.py
    │   │   ├── outcome_linker.py
    │   │   ├── playbook_ledger.py
    │   │   ├── reflector.py
    │   │   ├── session_search.py
    │   │   ├── skill_crystallizer.py
    │   │   ├── skill_curator.py
    │   │   ├── skill_evolution.py
    │   │   └── working_scratchpad.py
    │   ├── prefetch
    │   │   ├── digest_slice_generator.py
    │   │   ├── macro_preprocessor.py
    │   │   ├── news_digest.py
    │   │   ├── sentiment_aggregator.py
    │   │   ├── stage1_prefetcher.py
    │   │   └── stage2_prefetcher.py
    │   ├── providers
    │   │   ├── anthropic_provider.py
    │   │   ├── base_provider.py
    │   │   ├── capabilities.py
    │   │   ├── deepseek_provider.py
    │   │   ├── error_classifier.py
    │   │   ├── gemini_provider.py
    │   │   ├── groq_provider.py
    │   │   ├── llm_factory.py
    │   │   ├── ollama_provider.py
    │   │   ├── openai_provider.py
    │   │   ├── openrouter_provider.py
    │   │   ├── pricing_catalog.py
    │   │   ├── provider_failover_classifier.py
    │   │   ├── structured_fallback.py
    │   │   └── typesafe_provider.py
    │   ├── schemas
    │   │   ├── pydantic_schemas.py
    │   │   └── schemas.py
    │   ├── stages
    │   │   ├── fundamental_stage.py
    │   │   ├── per_asset_stage.py
    │   │   ├── per_asset
    │   │   │   ├── __init__.py
    │   │   │   ├── context_builder.py
    │   │   │   ├── runner.py
    │   │   │   ├── specialist_pipeline.py
    │   │   │   └── verifiers.py
    │   │   └── preflight_gate.py
    │   ├── strategies
    │   │   ├── base_strategy.py
    │   │   ├── btc_donchian_breakout.py
    │   │   ├── decay_monitor.py
    │   │   ├── gap_fade.py
    │   │   ├── liquidity_sweep_edge.py
    │   │   ├── pretrade_gate.py
    │   │   ├── registry.py
    │   │   ├── tsm_momentum.py
    │   │   ├── xau_trend_engine.py
    │   │   ├── xti_pairs_readiness.py
    │   │   └── synthesized
    │   │       ├── alpha_eurusd_6d622a.py
    │   │       ├── alpha_usdjpy_13a603.py
    │   │       ├── alpha_xauusd_94ad53.py
    │   │       ├── alpha_xauusd_b01980.py
    │   │       ├── alpha_xbrusd_e55dbf.py
    │   │       └── alpha_xtiusd_f30ff5.py
    │   ├── subagent
    │   │   ├── __init__.py
    │   │   └── isolated_harness.py
    │   ├── tools
    │   │   ├── base_handler.py
    │   │   ├── composite_tools.py
    │   │   ├── executor.py
    │   │   ├── registry.py
    │   │   ├── tool_executor.py
    │   │   ├── tool_guardrails.py
    │   │   ├── tool_registry.py
    │   │   ├── tools_definitions.py
    │   │   ├── domain
    │   │   │   ├── execution_handlers.py
    │   │   │   ├── macro_handlers.py
    │   │   │   ├── position_handlers.py
    │   │   │   ├── sentiment_handlers.py
    │   │   │   └── technical_handlers.py
    │   │   └── handlers
    │   │       ├── __init__.py
    │   │       ├── analysis_submit.py
    │   │       ├── category_loader.py
    │   │       ├── db_tools.py
    │   │       ├── intelligence.py
    │   │       ├── macro_data.py
    │   │       ├── market_data.py
    │   │       ├── phase_transition.py
    │   │       ├── position_mgmt.py
    │   │       ├── ptc_handler.py
    │   │       ├── scratchpad.py
    │   │       ├── sentiment_data.py
    │   │       ├── system_info.py
    │   │       ├── timesfm.py
    │   │       ├── trade_intel.py
    │   │       ├── verified_snapshot.py
    │   │       ├── macro_tools.py
    │   │       ├── market_data_tools.py
    │   │       ├── news_tools.py
    │   │       ├── sentiment_tools.py
    │   │       ├── smc_tools.py
    │   │       └── trading_tools.py
    │   └── validators
    │       ├── adjudication_verifier.py
    │       ├── adversarial_check.py
    │       ├── confluence_verifier.py
    │       ├── core_data_validator.py
    │       ├── float_coercion.py
    │       ├── fundamental_verifier.py
    │       ├── in_harness_grounding.py
    │       ├── market_snapshot.py
    │       ├── output_verifier.py
    │       └── precommit_gate.py

    ├── backtest
    │   ├── alpha_validation.py
    │   ├── decision_memory.py
    │   ├── monte_carlo_engine.py
    │   ├── offline_signal_engine.py
    │   ├── outcome_evaluator.py
    │   ├── point_in_time_engine.py
    │   ├── report_generator.py
    │   ├── statistical_tests.py
    │   ├── time_machine.py
    │   └── walk_forward_engine.py
    ├── benchmark
    │   ├── results
    │   │   ├── model_all.csv
    │   │   ├── model_cheap_efficient.csv
    │   │   ├── model_cheap_smart.csv
    │   │   ├── model_high_intelligence.csv
    │   │   └── model_quadrant_analysis.html
    │   ├── alpha_arena.py
    │   ├── db_access.py
    │   ├── db_models.py
    │   ├── deterministic.py
    │   ├── invoker.py
    │   ├── judge.py
    │   ├── model_registry.py
    │   ├── pricing.py
    │   ├── prompt_evolution.py
    │   ├── report.py
    │   ├── runner.py
    │   ├── task_specs.py
    │   └── trade_trajectory_logger.py
    ├── cli
    │   ├── doctor.py
    │   ├── main.py
    │   ├── profile_manager.py
    │   └── setup_wizard.py
    ├── config
    │   ├── atomic_writer.py
    │   ├── hot_reload.py
    │   ├── key_validator.py
    │   ├── migrations.py
    │   ├── schemas.py
    │   ├── settings.py
    │   ├── settings.yaml
    │   ├── MACRO_REALITY.md
    │   └── TRADING_SOUL.md
    ├── data_sources
    │   ├── academic_search.py
    │   ├── bond_yields_fetcher.py
    │   ├── bond_yields_yfinance.py
    │   ├── central_bank_watch.py
    │   ├── cftc_cot.py
    │   ├── coinglass_funding.py
    │   ├── dxy_yfinance.py
    │   ├── eia_oil_inventory.py
    │   ├── fear_greed.py
    │   ├── fred_treasury_yield.py
    │   ├── validators.py
    │   ├── vix_yfinance.py
    │   ├── web_reader.py
    │   └── web_search.py
    ├── database
    │   ├── adapters.py
    │   ├── async_db.py
    │   ├── cleanup.py
    │   ├── db.py
    │   ├── event_store.py
    │   ├── models.py
    │   ├── safe_ops.py
    │   ├── domain_models
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── market.py
    │   │   ├── trading.py
    │   │   ├── memory.py
    │   │   ├── analysis.py
    │   │   ├── system.py
    │   │   └── news.py
    │   └── migrations
    │       ├── archive
    │       ├── env.py
    │       └── versions
    ├── execution
    │   ├── backends
    │   │   ├── __init__.py
    │   │   └── base.py
    │   ├── broker_adapter.py
    │   ├── effect_gate.py
    │   ├── execution_service.py
    │   ├── health_check.py
    │   ├── mt5_client.py
    │   ├── order_emulator.py
    │   ├── rate_throttler.py
    │   ├── service
    │   │   ├── __init__.py
    │   │   ├── audit_logger.py
    │   │   ├── base.py
    │   │   ├── emergency_manager.py
    │   │   ├── order_creator.py
    │   │   ├── order_executor.py
    │   │   ├── position_synchronizer.py
    │   │   ├── reconciliation.py
    │   │   ├── risk_evaluator.py
    │   │   ├── sizing_calculator.py
    │   │   └── state_machine.py
    │   ├── verification_engine.py
    │   └── ea_bridge
    │       ├── AIAgent_EA.mq5
    │       └── heartbeat_writer.py
    ├── graph
    │   ├── reactive_graph.py
    │   ├── state.py
    │   ├── workflow.py
    │   ├── checkpointers
    │   │   ├── __init__.py
    │   │   └── sqlite_checkpointer.py
    │   └── nodes
    │       ├── data_node.py
    │       ├── debate
    │       │   ├── __init__.py
    │       │   ├── aggressive_risk_node.py
    │       │   ├── bear_dissent_node.py
    │       │   ├── bull_advocate_node.py
    │       │   ├── conservative_risk_node.py
    │       │   ├── debate_judge_node.py
    │       │   ├── helpers.py
    │       │   ├── neutral_risk_node.py
    │       │   ├── portfolio_judge_node.py
    │       │   ├── rebuttal_node.py
    │       │   ├── risk_evaluator_node.py
    │       │   ├── round_robin_risk_nodes.py
    │       │   └── subgraph.py
    │       ├── debate_node.py
    │       ├── execution_node.py
    │       ├── fundamental_node.py
    │       ├── per_asset_node.py
    │       ├── plan_refinement_node.py
    │       ├── reflection_node.py
    │       ├── risk_gate_node.py
    │       └── state_pruner.py
    ├── indicators
    │   ├── microstructure.py
    │   ├── order_flow.py
    │   ├── regime_detector.py
    │   ├── structure.py
    │   ├── technical.py
    │   └── timesfm_engine.py
    ├── logging_observability
    │   ├── activity_logger.py
    │   ├── metrics_exporter.py
    │   ├── report_writer.py
    │   ├── reporting
    │   │   ├── __init__.py
    │   │   └── tearsheet_generator.py
    │   ├── tracing
    │   │   ├── __init__.py
    │   │   ├── context.py
    │   │   ├── exporters.py
    │   │   ├── otlp_exporter.py
    │   │   ├── spans.py
    │   │   └── tracer.py
    │   └── dashboard
    │       ├── api.py
    │       ├── rbac.py
    │       ├── routes
    │       │   ├── __init__.py
    │       │   ├── common.py
    │       │   ├── config.py
    │       │   ├── observability.py
    │       │   ├── system.py
    │       │   ├── tokens.py
    │       │   ├── trace_search.py
    │       │   ├── trace_search.py
    │       │   ├── trading.py
    │       │   └── websocket.py
    │       └── frontend
    │           ├── package.json
    │           ├── tsconfig.app.json
    │           ├── tsconfig.node.json
    │           ├── vite.config.ts
    │           └── src
    │               ├── App.css
    │               ├── App.tsx
    │               ├── index.css
    │               ├── main.tsx
    │               ├── vite-env.d.ts
    │               ├── components
    │               │   ├── charts
    │               │   │   ├── DecisionDistribution.tsx
    │               │   │   ├── EquityChart.tsx
    │               │   │   ├── FactorHeatmap.tsx
    │               │   │   ├── VixSparkline.tsx
    │               │   │   └── WinRateGauge.tsx
    │               │   ├── layout
    │               │   │   ├── BreadcrumbBar.tsx
    │               │   │   ├── GlobalStatusBar.tsx
    │               │   │   ├── Header.tsx
    │               │   │   ├── MobileNavDrawer.tsx
    │               │   │   ├── navigation.ts
    │               │   │   └── Sidebar.tsx
    │               │   ├── panels
    │               │   │   ├── ActivityFeed.tsx
    │               │   │   ├── AgentChatPanel.tsx
    │               │   │   ├── AgentStatusBar.tsx
    │               │   │   ├── AnalysisGrid.tsx
    │               │   │   ├── ConfigEditorPanel.tsx
    │               │   │   ├── DebateOutcomesPanel.tsx
    │               │   │   ├── EdgeMetricsPanel.tsx
    │               │   │   ├── GraphVisualizerPanel.tsx
    │               │   │   ├── MarketDataPanel.tsx
    │               │   │   ├── ObservabilityPanel.tsx
    │               │   │   ├── PerformancePanel.tsx
    │               │   │   ├── PositionsTable.tsx
    │               │   │   ├── RetroCockpitBar.tsx
    │               │   │   ├── RiskPanel.tsx
    │               │   │   ├── SessionBrowserPanel.tsx
    │               │   │   ├── SignalsTriggersPanel.tsx
    │               │   │   ├── SystemPanel.tsx
    │               │   │   ├── TokenAuditPanel.tsx
    │               │   │   ├── config
    │               │   │   │   ├── ConfigDiffModal.tsx
    │               │   │   │   └── ConfigSection.tsx
    │               │   │   ├── graph
    │               │   │   │   ├── GraphControls.tsx
    │               │   │   │   ├── GraphEdge.tsx
    │               │   │   │   ├── GraphInspector.tsx
    │               │   │   │   ├── GraphNode.tsx
    │               │   │   │   └── graphUtils.ts
    │               │   │   └── tokens
    │               │   │       ├── TokenCharts.tsx
    │               │   │       └── TokenRoleTable.tsx
    │               │   └── ui
    │               │       ├── AnalogDial.tsx
    │               │       ├── Badge.tsx
    │               │       ├── BootSequence.tsx
    │               │       ├── Card.tsx
    │               │       ├── ConfirmModal.tsx
    │               │       ├── EmptyState.tsx
    │               │       ├── ErrorBoundary.tsx
    │               │       ├── KeyboardShortcutsPanel.tsx
    │               │       ├── LedgerTable.tsx
    │               │       ├── MetricCard.tsx
    │               │       ├── MonikaInfiniteIcon.tsx
    │               │       ├── RetroIcons.tsx
    │               │       ├── RetroVuMeter.tsx
    │               │       ├── SegmentedProgressBar.tsx
    │               │       ├── Skeleton.tsx
    │               │       ├── StatusIndicator.tsx
    │               │       ├── ThemeToggle.tsx
    │               │       ├── TickerTape.tsx
    │               │       ├── TypewriterButton.tsx
    │               │       ├── VintageIcons.tsx
    │               │       └── WindowFrame.tsx
    │               ├── hooks
    │               │   ├── useAgentChatWs.ts
    │               │   ├── usePolling.ts
    │               │   └── useWebSocket.ts
    │               ├── lib
    │               │   ├── api.ts
    │               │   ├── formatters.ts
    │               │   └── soundEffects.ts
    │               ├── store
    │               │   └── dashboardStore.ts
    │               └── types
    │                   └── api.ts
    ├── risk
    │   ├── correlation_matrix.py
    │   ├── execution_simulator.py
    │   ├── portfolio_correlation_gate.py
    │   ├── position_sizing.py
    │   └── risk_gate.py
    ├── scheduler
    │   ├── active_calendar_poller.py
    │   ├── alpha_discovery_scheduler.py
    │   ├── cycle_scheduler.py
    │   ├── digest_slice_scheduler.py
    │   ├── edge_strategy_runner.py
    │   ├── flash_crash_detector.py
    │   ├── graph_cycle_scheduler.py
    │   ├── macro_data_scheduler.py
    │   ├── market_data_scheduler.py
    │   ├── news_watcher.py
    │   ├── order_reconciler.py
    │   ├── position_exit_reviewer.py
    │   ├── position_guardian.py
    │   ├── position_supervisor.py
    │   ├── post_release_analyzer.py
    │   ├── scraper_runner.py
    │   ├── strategy_synthesis_scheduler.py
    │   ├── trailing_stop_manager.py
    │   └── trigger_checker.py
    ├── scrapers
    │   ├── base_scraper.py
    │   ├── models.py
    │   ├── calendar
    │   │   ├── calendar_finnhub.py
    │   │   ├── calendar_forexfactory.py
    │   │   └── calendar_investing.py
    │   ├── macro
    │   │   └── cme_fedwatch.py
    │   ├── news
    │   │   ├── kitco_news.py
    │   │   ├── rss_base.py
    │   │   ├── rss_bloomberg.py
    │   │   ├── rss_boe.py
    │   │   ├── rss_boj.py
    │   │   ├── rss_cnbc.py
    │   │   ├── rss_coindesk.py
    │   │   ├── rss_dow_jones.py
    │   │   ├── rss_ecb.py
    │   │   ├── rss_fed.py
    │   │   ├── rss_forexlive.py
    │   │   ├── rss_ft.py
    │   │   ├── rss_fxstreet.py
    │   │   ├── rss_investing.py
    │   │   ├── rss_marketwatch.py
    │   │   ├── rss_rba.py
    │   │   ├── rss_reuters.py
    │   │   ├── rss_wsj.py
    │   │   └── tradingview_news.py
    │   ├── sentiment
    │   │   ├── binance_sentiment.py
    │   │   ├── fxssi_sentiment.py
    │   │   └── myfxbook_sentiment.py
    │   └── social
    │       └── twitter_watch.py
    ├── skills
    │   ├── curator.py
    │   ├── loader.py
    │   ├── usage_tracker.py
    │   ├── crystallized
    │   └── trading
    │       ├── adjudication_framework.md
    │       ├── caveman_mode.md
    │       ├── central_banks_framework.md
    │       ├── commodity_analysis.md
    │       ├── crypto_analysis.md
    │       ├── event_probability_playbook.md
    │       ├── lessons_learned.md
    │       ├── liquidity_and_macro_edge.md
    │       ├── macro_analysis_framework.md
    │       ├── market_dynamics_framework.md
    │       ├── performance_notes.md
    │       ├── risk_management_principles.md
    │       ├── session_timing_rules.md
    │       ├── smc_ict_playbook.md
    │       └── telegram_persona.md
    ├── telegram_bot
    │   ├── bot.py
    │   ├── chat_agent.py
    │   ├── chat_compaction.py
    │   ├── chat_tool_router.py
    │   ├── command_router.py
    │   ├── topic_manager.py
    │   ├── vintage_formatter.py
    │   └── voice_handler.py
    ├── scripts
    │   ├── audit_token_usage.py
    │   ├── check_openrouter_keys.py
    │   ├── remediate_budget_history.py
    │   └── sanitize_news_language.py
    ├── utils
        ├── chart_generator.py
        ├── clock.py
        ├── constants.py
        ├── analytics
        │   ├── adversarial_outcome_tracker.py
        │   ├── agent_performance_monitor.py
        │   ├── analysis_tracker.py
        │   ├── cds_outcome_tracker.py
        │   ├── cost_tracker.py
        │   ├── pricing.py
        │   ├── edge_tracker.py
        │   ├── news_classification_tracker.py
        │   ├── paper_tracker.py
        │   ├── specialist_tracker.py
        │   ├── strategy_edge_tracker.py
        │   ├── token_auditor.py
        │   ├── trade_autopsy.py
        │   └── performance_reviewer.py
        ├── api
        │   ├── claude_rate_limiter.py
        │   ├── credential_pool.py
        │   ├── gemini_rate_limiter.py
        │   ├── groq_rate_limiter.py
        │   ├── http_retry.py
        │   ├── openrouter_rate_limiter.py
        │   └── streaming.py
        ├── calibration
        │   ├── cds_threshold_calibrator.py
        │   ├── confidence_calibrator.py
        │   ├── cot_thresholds.py
        │   └── prescreen_calibrator.py
        ├── infra
        │   ├── audit_settings_keys.py
        │   ├── container.py
        │   ├── db_backup.py
        │   ├── event_loop.py
        │   ├── log_redactor.py
        │   ├── notifier.py
        │   └── platform_compat.py
        ├── llm
        │   ├── adaptive_thinking.py
        │   ├── cache_breakpoint_manager.py
        │   ├── cache_miss_detector.py
        │   ├── caveman_compressor.py
        │   ├── constrained_sampling.py
        │   ├── context_compaction.py
        │   ├── context_tracker.py
        │   ├── credential_pool.py
        │   ├── cycle_budget_guard.py
        │   ├── data_dedup.py
        │   ├── deferred_dispatcher.py
        │   ├── memory_compressor.py
        │   ├── model_capabilities.py
        │   ├── model_discipline.py
        │   ├── prompt_ab_test.py
        │   ├── prompt_assembler.py
        │   ├── prompt_caching.py
        │   ├── prompt_compressor.py
        │   ├── prompt_tiering.py
        │   ├── prompt_tiers.py
        │   ├── spill_subsystem.py
        │   └── tool_condenser.py
        ├── market
        │   ├── bias_utils.py
        │   ├── brent_yfinance.py
        │   ├── currency_utils.py
        │   ├── direction.py
        │   ├── dynamic_correlation.py
        │   ├── instrument_identity.py
        │   ├── news_impact_keywords.py
        │   ├── session_info.py
        │   ├── swap_estimator.py
        │   └── usd_strength_proxy.py
        ├── plugins
        │   ├── __init__.py
        │   ├── extension_loader.py
        │   └── manager.py
        ├── protocol
        │   ├── brief_contamination_guard.py
        │   ├── coherence_flag_tracker.py
        │   ├── context_coherence.py
        │   ├── context_snapshot.py
        │   ├── cross_agent_sync.py
        │   ├── enhanced_cds.py
        │   ├── event_bus.py
        │   └── ssvp_coordinator.py
        ├── scheduling
        │   └── wall_clock.py
        ├── security
        │   ├── __init__.py
        │   └── threat_scanner.py
        ├── typesafe
        │   ├── __init__.py
        │   └── jev_primitives.py
        └── validation
            ├── data_temporal_validator.py
            ├── data_validator.py
            ├── indicator_sanitizer.py
            └── tool_response_validator.py
    ├── logging_observability
    │   ├── activity_logger.py
    │   ├── tearsheet_generator.py
    │   ├── dashboard
    │   │   ├── api.py
    │   │   ├── rbac.py
    │   │   ├── routes
    │   │   │   ├── __init__.py
    │   │   │   ├── common.py
    │   │   │   ├── config.py
    │   │   │   ├── observability.py
    │   │   │   ├── system.py
    │   │   │   ├── tokens.py
    │   │   │   ├── trading.py
    │   │   │   └── websocket.py
    │   │   └── frontend
    │   │       └── src
    │   │           ├── components
    │   │           │   └── panels
    │   │           │       ├── config
    │   │           │       │   ├── ConfigDiffModal.tsx
    │   │           │       │   └── ConfigSection.tsx
    │   │           │       ├── graph
    │   │           │       │   ├── GraphControls.tsx
    │   │           │       │   ├── GraphEdge.tsx
    │   │           │       │   ├── GraphInspector.tsx
    │   │           │       │   └── GraphNode.tsx
    │   │           │       ├── tokens
    │   │           │       │   ├── TokenCharts.tsx
    │   │           │       │   └── TokenRoleTable.tsx
    │   │           │       ├── ConfigEditorPanel.tsx
    │   │           │       ├── GraphVisualizerPanel.tsx
    │   │           │       └── TokenAuditPanel.tsx
    │   │           ├── lib
    │   │           │   └── api.ts
    │   │           └── types
    │   │               └── api.ts
    │   └── tracing
    │       ├── context.py
    │       ├── exporters.py
    │       ├── otlp_exporter.py
    │       ├── spans.py
    │       └── tracer.py
    └── tests
        ├── test_audit_remediation_consolidated.py
        ├── test_audit_round2_remediation.py
        ├── test_audit_round3_remediation.py
        ├── test_cli.py
        ├── test_cli_theme.py
        ├── test_event_probability_flow.py
        ├── test_m2_empirical_stress.py
        ├── test_telegram_vintage_formatter.py
        ├── test_audit_round2_remediation.py
        ├── test_audit_round3_remediation.py
        ├── test_audit_round4_remediation.py
        ├── test_audit_remediation_consolidated.py
        ├── agent
        │   ├── test_agent_loop.py
        │   ├── test_pgvector_startup_check.py
        │   └── test_task_registry.py
        ├── analysis
        │   ├── harness
        │   │   ├── test_agent_harness.py
        │   │   ├── test_context_compressor.py
        │   │   ├── test_error_classifier.py
        │   │   └── test_trade_stop_and_segment_planner.py
        │   ├── memory
        │   │   ├── test_playbook_ledger.py
        │   │   └── test_skill_curator.py
        │   ├── tools
        │   │   ├── test_news_tools.py
        │   │   └── test_tool_guardrails.py
        │   ├── providers
        │   │   ├── test_prompt_caching_enhancements.py
        │   │   └── test_typesafe_provider.py
        │   ├── strategies
        │   │   ├── test_strategy_registry_summary.py
        │   │   └── test_synthesized_strategy_resilience.py
        │   ├── test_jev_news_classifier.py
        │   ├── test_jev_verifiers_and_builders.py
        │   ├── test_level_optimizer_rr_pairing.py
        │   └── test_skill_crystallizer_curation.py
        ├── cli
        │   ├── test_analysis_tree.py
        │   ├── test_busy_input.py
        │   ├── test_doctor_and_profile.py
        │   ├── test_platform_compat.py
        │   ├── test_sparklines.py
        │   ├── test_theme_packs.py
        │   └── test_tui_components.py
        ├── execution
        │   ├── test_mt5_client.py
        │   ├── test_mt5_priority_queue.py
        │   ├── test_mt5_tick_poller.py
        │   ├── test_order_emulator.py
        │   ├── test_order_reconciliation.py
        │   ├── test_phase1_remediation.py
        │   ├── test_phase2_remediation.py
        │   ├── test_phase3_remediation.py
        │   ├── test_phase4_remediation.py
        │   └── test_rate_throttler.py
        ├── logging_observability
        │   ├── test_activity_logger.py
        │   ├── test_dashboard_api.py
        │   ├── test_dashboard_observability_endpoints.py
        │   ├── test_dashboard_phase2.py
        │   ├── test_modular_routes.py
        │   ├── test_tearsheet_generator.py
        │   └── test_tracing.py
        ├── scheduler
        │   ├── test_alpha_discovery_closed_loop.py
        │   ├── test_scraper_runner.py
        │   ├── test_strategy_synthesis_historical_sandbox.py
        │   └── test_strategy_synthesis_scheduler.py
        ├── scrapers
        │   └── test_base_scraper.py
        ├── skills
        │   ├── test_event_probability_playbook.py
        │   ├── test_event_probability_stress.py
        │   └── test_playbook_stress_challenge.py
        ├── utils
        │   ├── test_context_tracker.py
        │   └── test_paper_trading_streak_policy.py
        └── telegram_bot
            ├── test_backtest_command.py
            ├── test_chat_agent_deep_research_stress.py
            ├── test_chat_agent_stress_challenge.py
            ├── test_chat_database_access.py
            ├── test_chat_tool_router_semantic.py
            ├── test_chat_tool_router_stress.py
            ├── test_session_approval.py
            └── test_telegram_enhancements.py