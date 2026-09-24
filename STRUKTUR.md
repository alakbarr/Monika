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
├── deploy
│   ├── Dockerfile.mt5-wine
│   ├── docker-compose.vps.yml
│   ├── entrypoint_mt5.sh
│   └── vps_deployment_guide.md
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
├── prompt_benchmark.md
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
│   ├── install.ps1
│   ├── install.sh
│   ├── reset_paper_trades.py
│   ├── run_tests.bat
│   ├── run_tests.sh
│   └── update_index_toc.py
└── trading-agent
    ├── docker-compose.yml
    ├── docker-compose.linux.yml
    ├── Dockerfile
    ├── bootstrap.py
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
    │   ├── onboarding_trader.py
    │   ├── overlays
    │   │   ├── __init__.py
    │   │   ├── approval_modal.py
    │   │   └── plugin_install_modal.py
    │   ├── platform_compat.py
    │   ├── plugins.py
    │   ├── profile_manager.py
    │   ├── setup_wizard.py
    │   ├── sparklines.py
    │   ├── theme.py
    │   ├── tui.py
    │   └── tui_chat.py
    ├── agent
    │   ├── __init__.py
    │   ├── agent_loop.py
    │   ├── chat_agent.py
    │   ├── startup_checks.py
    │   ├── task_registry.py
    │   ├── turn_lease_manager.py
    │   └── monitors
    │       ├── __init__.py
    │       ├── db_health.py
    │       ├── drawdown_monitor.py
    │       ├── paper_trade_monitor.py
    │       ├── scraper_loop.py
    │       └── startup_watchdog.py
    ├── config
    │   ├── atomic_writer.py
    │   ├── config_manager.py
    │   ├── config_migrations.py
    │   ├── hot_reload.py
    │   ├── key_validator.py
    │   ├── migrations.py
    │   ├── plugins
    │   │   └── discord_alert.yaml
    │   ├── plugin_catalog.yaml
    │   ├── schemas.py
    │   ├── security.py
    │   ├── settings.py
    │   └── settings.yaml
    ├── analysis
    │   ├── event_broadcaster.py
    │   ├── macro_pipeline_plugin.py
    │   ├── pipeline_plugin.py
    │   ├── prompt_sections.py
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
    │   │   ├── repetition_guard.py
    │   │   ├── stall_guard.py
    │   │   ├── structured_output.py
    │   │   ├── symbol_segment_planner.py
    │   │   ├── tool_batch_planner.py
    │   │   ├── tool_repair.py
    │   │   ├── trade_stop_gates.py
    │   │   └── verification_evidence_ledger.py
    │   ├── mcp
    │   │   ├── __init__.py
    │   │   ├── client.py
    │   │   ├── protocol.py
    │   │   ├── server.py
    │   │   └── servers
    │   │       ├── __init__.py
    │   │       ├── fetch_server.py
    │   │       ├── filesystem_server.py
    │   │       └── sqlite_server.py
    │   ├── memory
    │   │   ├── alpha_calculator.py
    │   │   ├── background_review.py
    │   │   ├── chronicle_writer.py
    │   │   ├── counterfactual_simulator.py
    │   │   ├── decision_log.py
    │   │   ├── failure_taxonomy.py
    │   │   ├── frozen_snapshot.py
    │   │   ├── layered_memory.py
    │   │   ├── lesson_consolidator.py
    │   │   ├── negative_constraint_generator.py
    │   │   ├── outcome_linker.py
    │   │   ├── playbook_ledger.py
    │   │   ├── playbook_lifecycle.py
    │   │   ├── playbook_linter.py
    │   │   ├── progressive_loader.py
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
    │   │   ├── nine_router_provider.py
    │   │   ├── ollama_provider.py
    │   │   ├── openai_provider.py
    │   │   ├── openrouter_provider.py
    │   │   ├── pricing_catalog.py
    │   │   ├── provider_failover_classifier.py
    │   │   ├── provider_registry.py
    │   │   ├── runtime_model_registry.py
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
    │   │   │   ├── specialist_council.py
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
    │   │   ├── strategy_plugin.py
    │   │   ├── tsm_momentum.py
    │   │   ├── xau_trend_engine.py
    │   │   ├── xti_pairs_readiness.py
    │   │   └── synthesized
    │   │       ├── alpha_btcusd_467904.py
    │   │       ├── alpha_eurusd_6d622a.py
    │   │       ├── alpha_gbpusd_e73efc.py
    │   │       ├── alpha_usdjpy_13a603.py
    │   │       ├── alpha_xauusd_3af460.py
    │   │       ├── alpha_xauusd_94ad53.py
    │   │       ├── alpha_xauusd_b01980.py
    │   │       ├── alpha_xbrusd_e55dbf.py
    │   │       └── alpha_xtiusd_f30ff5.py
    │   ├── subagent
    │   │   ├── __init__.py
    │   │   ├── adhoc_manager.py
    │   │   └── isolated_harness.py
    │   ├── tools
    │   │   ├── base_handler.py
    │   │   ├── composite_tools.py
    │   │   ├── executor.py
    │   │   ├── loop_guard.py
    │   │   ├── registry.py
    │   │   ├── tool_catalog.py
    │   │   ├── tool_executor.py
    │   │   ├── tool_guardrails.py
    │   │   ├── tool_plugin.py
    │   │   ├── tool_registry.py
    │   │   ├── tool_result_storage.py
    │   │   ├── tool_spill.py
    │   │   ├── tools_definitions.py
    │   │   ├── unified_registry.py
    │   │   ├── quant_sandbox
    │   │   │   ├── __init__.py
    │   │   │   └── rpc_server.py
    │   │   ├── kernel
    │   │   │   ├── __init__.py
    │   │   │   ├── env_sanitizer.py
    │   │   │   ├── output_spiller.py
    │   │   │   ├── persistent_kernel.py
    │   │   │   └── sandbox_runner.py
    │   │   ├── domain
    │   │   │   ├── execution_handlers.py
    │   │   │   ├── macro_handlers.py
    │   │   │   ├── position_handlers.py
    │   │   │   ├── sentiment_handlers.py
    │   │   │   ├── spill_reader_tool.py
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
    │   │       ├── skills_tools.py
    │   │       ├── smc_tools.py
    │   │       └── trading_tools.py
    │   └── validators
    │       ├── adjudication_verifier.py
    │       ├── adversarial_check.py
    │       ├── confluence_verifier.py
    │       ├── core_data_validator.py
    │       ├── cross_timeframe_gate.py
    │       ├── float_coercion.py
    │       ├── fundamental_verifier.py
    │       ├── in_harness_grounding.py
    │       ├── market_snapshot.py
    │       ├── output_verifier.py
    │       └── precommit_gate.py

    ├── backtest
    │   ├── alpha_validation.py
    │   ├── benchmark_tracker.py
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
    │   ├── paired_evaluator.py
    │   ├── pricing.py
    │   ├── prompt_evolution.py
    │   ├── report.py
    │   ├── runner.py
    │   ├── task_specs.py
    │   ├── token_drift_tracker.py
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
    │   ├── circuit_breaker.py
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
    ├── evals
    │   ├── fixtures
    │   │   ├── risk_trap_daily_dd.json
    │   │   ├── risk_trap_spread_spike.json
    │   │   ├── smc_bear_sweep.json
    │   │   ├── smc_bull_displacement.json
    │   │   └── smc_choppy_trap.json
    │   ├── oracles
    │   │   ├── macro_regime_oracle.py
    │   │   ├── risk_compliance_oracle.py
    │   │   ├── smc_geometry_oracle.py
    │   │   └── trade_discipline_oracle.py
    │   ├── eval_metrics.py
    │   ├── eval_runner.py
    │   ├── runner.py
    │   └── simulation_clock.py
    ├── execution
    │   ├── broker_adapter.py
    │   ├── broker_plugin.py
    │   ├── broker_registry.py
    │   ├── effect_gate.py
    │   ├── execution_service.py
    │   ├── health_check.py
    │   ├── idempotency_guard.py
    │   ├── mt5_client.py
    │   ├── order_emulator.py
    │   ├── paper_tracker.py
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
    │   │   ├── self_healing_executor.py
    │   │   ├── sizing_calculator.py
    │   │   ├── state_machine.py
    │   │   └── trade_confirm.py
    │   ├── verification_engine.py
    │   └── ea_bridge
    │       ├── AIAgent_EA.mq5
    │       ├── heartbeat_writer.py
    │       └── watchdog.py
    ├── graph
    │   ├── reactive_graph.py
    │   ├── state.py
    │   ├── workflow.py
    │   ├── checkpointers
    │   │   ├── __init__.py
    │   │   ├── dual_checkpointer.py
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
    ├── harness
    │   ├── __init__.py
    │   ├── adapters
    │   │   ├── __init__.py
    │   │   └── functional_adapter.py
    │   ├── context.py
    │   ├── contract.py
    │   ├── engine.py
    │   └── installer.py
    ├── plugin_kernel
    │   └── __init__.py
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
    │   ├── operator_feedback.py
    │   ├── report_writer.py
    │   ├── token_budgeter.py
    │   ├── trading_cycle_event_log.py
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
    │       │   ├── backtest.py
    │       │   ├── common.py
    │       │   ├── config.py
    │       │   ├── intelligence.py
    │       │   ├── memory.py
    │       │   ├── observability.py
    │       │   ├── plugins.py
    │       │   ├── system.py
    │       │   ├── tokens.py
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
│   │   ├── BacktestPanel.tsx
    │               │   │   ├── ConfigEditorPanel.tsx
    │               │   │   ├── DebateOutcomesPanel.tsx
    │               │   │   ├── EdgeMetricsPanel.tsx
    │               │   │   ├── GraphVisualizerPanel.tsx
    │               │   │   ├── MarketDataPanel.tsx
    │               │   │   ├── MemoryBrowserPanel.tsx
    │               │   │   ├── ObservabilityPanel.tsx
    │               │   │   ├── PerformancePanel.tsx
    │               │   │   ├── PluginManagerPanel.tsx
    │               │   │   ├── PositionsTable.tsx
    │               │   │   ├── RetroCockpitBar.tsx
    │               │   │   ├── RiskPanel.tsx
    │               │   │   ├── SessionBrowserPanel.tsx
    │               │   │   ├── SignalsTriggersPanel.tsx
    │               │   │   ├── SkillManagerPanel.tsx
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
    │               │       ├── ApprovalModal.tsx
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
    │               │       ├── WeekendGapBanner.tsx
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
    │               ├── theme
    │               │   └── tokens.ts
    │               └── types
    │                   └── api.ts
    ├── plugins
    │   ├── __init__.py
    │   ├── loader.py
    │   ├── manifest.py
    │   ├── alerts
    │   │   └── discord_alert
    │   │       ├── discord_alert.py
    │   │       └── plugin.yaml
    │   ├── analysis_pipelines
    │   │   ├── macro_to_asset
    │   │   │   ├── macro_to_asset_pipeline.py
    │   │   │   └── plugin.yaml
    │   │   └── technical_scalping
    │   │       ├── plugin.yaml
    │   │       └── scalping_pipeline.py
    │   ├── brokers
    │   │   ├── mt5_local
    │   │   │   ├── mt5_plugin.py
    │   │   │   └── plugin.yaml
    │   │   └── paper_trading
    │   │       ├── paper_plugin.py
    │   │       └── plugin.yaml
    │   ├── indicators
    │   │   └── custom_indicator
    │   │       ├── custom_indicator.py
    │   │       └── plugin.yaml
    │   └── scrapers
    │       └── example_scraper
    │           ├── example_scraper.py
    │           └── plugin.yaml
    ├── provider
    │   ├── __init__.py
    │   ├── credential_pool.py
    │   └── error_taxonomy.py
    ├── risk
    │   ├── approval_hub.py
    │   ├── correlation_matrix.py
    │   ├── execution_simulator.py
    │   ├── portfolio_correlation_gate.py
    │   ├── position_sizing.py
    │   ├── risk_gate.py
    │   ├── risk_rule_plugin.py
    │   ├── trade_proposal.py
    │   └── invariants
    │       ├── __init__.py
    │       ├── position_count_invariant.py
    │       ├── registry.py
    │       ├── risk_gate_invariant.py
    │       └── state_immutability_invariant.py
    ├── security
    │   ├── __init__.py
    │   └── credential_vault.py
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
    │   ├── playbook_curator.py
    │   ├── position_exit_reviewer.py
    │   ├── position_guardian.py
    │   ├── position_supervisor.py
    │   ├── post_release_analyzer.py
    │   ├── scraper_runner.py
    │   ├── strategy_synthesis_scheduler.py
    │   ├── task_plugin.py
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
    ├── services
    │   ├── __init__.py
    │   ├── market_data_service.py
    │   ├── portfolio_service.py
    │   └── system_status_service.py
    ├── skills
    │   ├── curator.py
    │   ├── loader.py
    │   ├── trading_skill_linter.py
    │   ├── usage_tracker.py
    │   ├── crystallized
    │   │   └── eurusd_trend.md
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
    │   ├── fuzzy_router.py
    │   ├── topic_manager.py
    │   ├── vintage_formatter.py
    │   ├── voice_handler.py
    │   └── voice_safety_gate.py
    ├── scripts
    │   ├── audit_token_usage.py
    │   ├── check_openrouter_keys.py
    │   ├── remediate_budget_history.py
    │   └── sanitize_news_language.py
    ├── utils
        ├── chart_generator.py
        ├── clock.py
        ├── constants.py
        ├── retry_decorator.py
        ├── turn_marker.py
        ├── analytics
        │   ├── adversarial_outcome_tracker.py
        │   ├── agent_performance_monitor.py
        │   ├── analysis_tracker.py
        │   ├── cds_outcome_tracker.py
        │   ├── cost_tracker.py
        │   ├── models_dev_sync.py
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
        │   ├── env_file_manager.py
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
        │   ├── embedding.py
        │   ├── memory_compressor.py
        │   ├── model_capabilities.py
        │   ├── model_discipline.py
        │   ├── prompt_ab_test.py
        │   ├── prompt_assembler.py
        │   ├── prompt_caching.py
        │   ├── prompt_compressor.py
        │   ├── prompt_disciplines.py
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
        ├── streaming
        │   ├── __init__.py
        │   └── stream_scrubber.py
        ├── storage
        │   └── spill_store.py
        ├── security
        │   ├── __init__.py
        │   ├── threat_detector.py
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
    │   │   │   ├── backtest.py
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
        ├── test_fase0_critical_fixes.py
        ├── test_phase1_critical_fixes.py
        ├── agent
        │   ├── test_agent_loop.py
        │   ├── test_pgvector_startup_check.py
        │   ├── test_startup_watchdog_enhancement.py
        │   ├── test_task_registry.py
        │   └── test_turn_lease_manager.py
        ├── analysis
        │   ├── arbitration
        │   │   └── test_recency_brier_weighting.py
        │   ├── grounding
        │   │   └── test_extended_grounding.py
        │   ├── harness
        │   │   ├── test_agent_harness.py
        │   │   ├── test_context_compressor.py
        │   │   ├── test_error_classifier.py
        │   │   ├── test_prompt_cache_architecture.py
        │   │   ├── test_structured_context_engine.py
        │   │   └── test_trade_stop_and_segment_planner.py
        │   ├── memory
        │   │   ├── test_negative_constraint_generator.py
        │   │   ├── test_playbook_ledger.py
        │   │   ├── test_playbook_lifecycle.py
        │   │   └── test_skill_curator.py
        │   ├── tools
        │   │   ├── test_news_tools.py
        │   │   └── test_tool_guardrails.py
        │   ├── providers
        │   │   ├── test_capabilities.py
        │   │   ├── test_credential_pool_routing.py
        │   │   ├── test_failover_expanded.py
        │   │   ├── test_fallback_wrapper_cooldown.py
        │   │   ├── test_nine_router_provider.py
        │   │   ├── test_prompt_caching_enhancements.py
        │   │   ├── test_provider_registry.py
        │   │   ├── test_structured_fallback.py
        │   │   └── test_typesafe_provider.py
        │   ├── strategies
        │   │   ├── test_strategy_registry_summary.py
        │   │   └── test_synthesized_strategy_resilience.py
        │   ├── test_agent_harness_steering_truncation.py
│   │   ├── test_news_digest.py
        │   ├── test_cross_timeframe_gate.py
        │   ├── test_frozen_memory_snapshot.py
        │   ├── test_jev_news_classifier.py
        │   ├── test_jev_verifiers_and_builders.py
        │   ├── test_level_optimizer_rr_pairing.py
        │   ├── test_pipeline_plugins.py
        │   ├── test_regime_and_factor_parity.py
        │   └── test_skill_crystallizer_curation.py
        ├── backtest
        │   ├── test_alpha_validation.py
        │   ├── test_benchmark_tracker.py
        │   ├── test_langgraph_backtest_parity.py
        │   ├── test_monte_carlo_block_bootstrap.py
        │   ├── test_offline_signal_engine_no_lookahead.py
        │   ├── test_outcome_evaluator.py
        │   ├── test_outcome_evaluator_dynamic_friction.py
        │   ├── test_outcome_evaluator_realism.py
        │   ├── test_point_in_time_engine.py
        │   ├── test_point_in_time_full_mode.py
        │   ├── test_report_generator_daily_sharpe_sortino.py
        │   ├── test_statistical_tests.py
        │   ├── test_time_machine.py
        │   └── test_walk_forward_purged.py
        ├── benchmark
        │   └── test_paired_evaluator.py
        ├── cli
        │   ├── test_analysis_tree.py
        │   ├── test_approval_modal.py
        │   ├── test_busy_input.py
        │   ├── test_doctor_and_profile.py
        │   ├── test_platform_compat.py
        │   ├── test_plugin_cli.py
        │   ├── test_sparklines.py
        │   ├── test_theme_packs.py
        │   └── test_tui_components.py
        ├── config
        │   ├── test_atomic_writer.py
        │   ├── test_config_manager.py
        │   ├── test_config_migrations.py
        │   ├── test_config_schemas.py
        │   ├── test_hot_reload.py
        │   ├── test_key_validator.py
        │   ├── test_migrations.py
        │   ├── test_modular_config.py
        │   ├── test_settings.py
        │   ├── test_settings_llm.py
        │   └── test_settings_task_roles.py
        ├── data_sources
        │   └── test_circuit_breaker.py
        ├── deploy
        │   └── test_deployment_configs.py
        ├── evals
        │   ├── __init__.py
        │   ├── test_eval_metrics_and_ab_runner.py
        │   ├── test_offline_evals.py
        │   ├── test_offline_oracles.py
        │   └── test_simulation_and_oracles.py
        ├── execution
        │   ├── test_broker_plugins.py
        │   ├── test_broker_registry.py
        │   ├── test_ea_watchdog.py
        │   ├── test_idempotency_guard.py
        │   ├── test_mt5_client.py
        │   ├── test_mt5_priority_queue.py
        │   ├── test_mt5_tick_poller.py
        │   ├── test_order_emulator.py
        │   ├── test_order_reconciliation.py
        │   ├── test_partial_fill_and_slippage.py
        │   ├── test_phase1_remediation.py
        │   ├── test_phase2_remediation.py
        │   ├── test_phase3_remediation.py
        │   ├── test_phase4_remediation.py
        │   └── test_rate_throttler.py
        ├── graph
        │   └── test_workflow_authoritative_checkpointer.py
        ├── harness
        │   ├── test_domain_plugins_integration.py
        │   ├── test_functional_compatibility.py
        │   ├── test_installer_service.py
        │   ├── test_message_repair.py
        │   ├── test_plugin_engine.py
        │   ├── test_plugin_kernel_namespace.py
        │   ├── test_repetition_and_candidate.py
        │   ├── test_threat_scanner.py
        │   ├── test_trading_agent_harness_integration.py
        │   └── test_unified_plugin_engine.py
        ├── logging_observability
        │   ├── test_activity_logger.py
        │   ├── test_cost_tracking_dashboard.py
        │   ├── test_cycle_event_log_and_feedback.py
        │   ├── test_dashboard_api.py
        │   ├── test_dashboard_memory_routes.py
        │   ├── test_dashboard_observability_endpoints.py
        │   ├── test_dashboard_phase2.py
        │   ├── test_dashboard_plugins_routes.py
        │   ├── test_modular_routes.py
        │   ├── test_tearsheet_generator.py
        │   ├── test_tracing.py
        │   └── test_websocket_stream_scrubber.py
        ├── perf
        │   ├── test_memory_budget.py
        │   └── test_microstructure_perf.py
        ├── plugins
        │   ├── test_plugin_manifest_and_loader.py
        │   └── test_reference_plugins.py
        ├── provider
        │   ├── __init__.py
        │   ├── test_credential_pool.py
        │   ├── test_error_taxonomy.py
        │   └── test_role_fallback_chain.py
        ├── risk
        │   ├── test_invariants_and_replay.py
        │   ├── test_risk_rule_pipeline.py
        │   └── test_trade_proposal.py
        ├── security
        │   └── test_credential_vault.py
        ├── scheduler
        │   ├── test_alpha_discovery_closed_loop.py
        │   ├── test_news_watcher_turn_lease.py
        │   ├── test_scraper_runner.py
        │   ├── test_strategy_synthesis_historical_sandbox.py
        │   ├── test_strategy_synthesis_scheduler.py
        │   └── test_task_plugin_lifecycle.py
        ├── scrapers
        │   └── test_base_scraper.py
        ├── skills
        │   ├── test_event_probability_playbook.py
        │   ├── test_event_probability_stress.py
        │   ├── test_playbook_stress_challenge.py
        │   └── test_progressive_playbook_disclosure.py
        ├── support
        │   └── replay_provider.py
        ├── utils
        │   ├── test_container_hierarchical.py
        │   ├── test_context_tracker.py
        │   ├── test_event_bus_enhancements.py
        │   ├── test_paper_trading_streak_policy.py
        │   ├── test_plugins_extended.py
        │   ├── test_spill_store.py
        │   └── test_stream_scrubber.py
        └── telegram_bot
            ├── test_backtest_command.py
            ├── test_chat_agent_deep_research_stress.py
            ├── test_chat_agent_stress_challenge.py
            ├── test_chat_database_access.py
            ├── test_chat_tool_router_semantic.py
            ├── test_chat_tool_router_stress.py
            ├── test_plugins_telegram.py
            ├── test_session_approval.py
            └── test_telegram_enhancements.py