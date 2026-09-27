# ==================================================
# CODEBASE DIRECTORY STRUCTURE — MONIKA (MT5 TRADING AGENT)
# ==================================================

Monika/
├── .github
│   ├── ISSUE_TEMPLATE
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── workflows
│   │   └── ci.yml
│   └── pull_request_template.md
├── deploy
│   ├── docker-compose.vps.yml
│   ├── Dockerfile.mt5-wine
│   ├── entrypoint_mt5.sh
│   └── vps_deployment_guide.md
├── docs
├── scripts
├── trading-agent
│   ├── agent
│   │   ├── monitors
│   │   │   ├── __init__.py
│   │   │   ├── db_health.py
│   │   │   ├── drawdown_monitor.py
│   │   │   ├── paper_trade_monitor.py
│   │   │   ├── scraper_loop.py
│   │   │   └── startup_watchdog.py
│   │   ├── __init__.py
│   │   ├── agent_loop.py
│   │   ├── auxiliary_model_router.py
│   │   ├── bounded_response.py
│   │   ├── chat_agent.py
│   │   ├── deadline.py
│   │   ├── empty_response_guard.py
│   │   ├── error_classifier.py
│   │   ├── estop.py
│   │   ├── moa_alternation.py
│   │   ├── moa_loop.py
│   │   ├── moa_trace.py
│   │   ├── repetition_guard.py
│   │   ├── scratchpad_guard.py
│   │   ├── socket_lifecycle_guard.py
│   │   ├── startup_checks.py
│   │   ├── state_rewind.py
│   │   ├── task_registry.py
│   │   ├── thinking_timeout_guidance.py
│   │   ├── three_part_context_compressor.py
│   │   ├── trajectory_compressor.py
│   │   ├── turn_lease_manager.py
│   │   ├── turn_liveness.py
│   │   ├── turn_phase_machine.py
│   │   ├── turn_preflight_gate.py
│   │   ├── turn_stop_gates.py
│   │   └── turn_tool_round.py
│   ├── analysis
│   │   ├── arbitration
│   │   │   ├── __init__.py
│   │   │   └── signal_arbitrator.py
│   │   ├── calculators
│   │   │   ├── __init__.py
│   │   │   ├── adaptive_policy.py
│   │   │   ├── confluence_calculator.py
│   │   │   ├── daily_range_calculator.py
│   │   │   ├── economic_surprise.py
│   │   │   ├── intraday_level_optimizer.py
│   │   │   ├── invariant_calculator.py
│   │   │   ├── liquidity_sweep_detector.py
│   │   │   ├── macro_bias_filter.py
│   │   │   ├── macro_priced_in_calculator.py
│   │   │   ├── quant_plateau_optimizer.py
│   │   │   ├── regime_classifier.py
│   │   │   ├── stage1_priced_in.py
│   │   │   ├── timesfm_alpha.py
│   │   │   ├── unified_threshold_calculator.py
│   │   │   └── volume_profile.py
│   │   ├── debate
│   │   │   ├── __init__.py
│   │   │   ├── adjustment_validator.py
│   │   │   ├── aggressive_risk_llm.py
│   │   │   ├── bear_analyst.py
│   │   │   ├── blackboard.py
│   │   │   ├── bull_analyst.py
│   │   │   ├── conservative_risk_llm.py
│   │   │   ├── deterministic_risk.py
│   │   │   ├── discussion_engine.py
│   │   │   ├── fact_sheet.py
│   │   │   ├── investment_judge.py
│   │   │   ├── macro_bear_analyst.py
│   │   │   ├── macro_bull_analyst.py
│   │   │   ├── macro_debate_validator.py
│   │   │   ├── macro_judge.py
│   │   │   ├── multi_persona_risk_llm.py
│   │   │   ├── neutral_risk_llm.py
│   │   │   └── portfolio_manager.py
│   │   ├── grounding
│   │   │   ├── __init__.py
│   │   │   └── provenance_tagger.py
│   │   ├── harness
│   │   │   ├── __init__.py
│   │   │   ├── agent_harness.py
│   │   │   ├── context_compressor.py
│   │   │   ├── error_classifier.py
│   │   │   ├── harness_state.py
│   │   │   ├── message_repair.py
│   │   │   ├── repetition_guard.py
│   │   │   ├── stall_guard.py
│   │   │   ├── structured_output.py
│   │   │   ├── symbol_segment_planner.py
│   │   │   ├── tool_batch_planner.py
│   │   │   ├── tool_repair.py
│   │   │   ├── trade_stop_gates.py
│   │   │   └── verification_evidence_ledger.py
│   │   ├── mcp
│   │   │   ├── servers
│   │   │   │   ├── __init__.py
│   │   │   │   ├── fetch_server.py
│   │   │   │   ├── filesystem_server.py
│   │   │   │   └── sqlite_server.py
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   ├── dispatcher.py
│   │   │   ├── event_bridge.py
│   │   │   ├── mcp_death_supervisor.py
│   │   │   ├── mcp_schema_cache.py
│   │   │   ├── mcp_serve.py
│   │   │   ├── oauth_handler.py
│   │   │   ├── protocol.py
│   │   │   └── server.py
│   │   ├── memory
│   │   │   ├── __init__.py
│   │   │   ├── alpha_calculator.py
│   │   │   ├── background_review.py
│   │   │   ├── background_review_fork.py
│   │   │   ├── chronicle_writer.py
│   │   │   ├── context_engine.py
│   │   │   ├── counterfactual_simulator.py
│   │   │   ├── decision_log.py
│   │   │   ├── failure_taxonomy.py
│   │   │   ├── frozen_snapshot.py
│   │   │   ├── layered_memory.py
│   │   │   ├── lesson_consolidator.py
│   │   │   ├── mechanical_anchor_index.py
│   │   │   ├── negative_constraint_generator.py
│   │   │   ├── outcome_linker.py
│   │   │   ├── playbook_ledger.py
│   │   │   ├── playbook_lifecycle.py
│   │   │   ├── playbook_linter.py
│   │   │   ├── progressive_loader.py
│   │   │   ├── prompt_cache_boundary.py
│   │   │   ├── reflector.py
│   │   │   ├── session_search.py
│   │   │   ├── sharegpt_exporter.py
│   │   │   ├── skill_ast_audit.py
│   │   │   ├── skill_crystallizer.py
│   │   │   ├── skill_curator.py
│   │   │   ├── skill_evolution.py
│   │   │   ├── skill_ledger_sha.py
│   │   │   ├── trajectory_compressor.py
│   │   │   └── working_scratchpad.py
│   │   ├── prefetch
│   │   │   ├── __init__.py
│   │   │   ├── digest_slice_generator.py
│   │   │   ├── macro_preprocessor.py
│   │   │   ├── news_digest.py
│   │   │   ├── sentiment_aggregator.py
│   │   │   ├── stage1_prefetcher.py
│   │   │   └── stage2_prefetcher.py
│   │   ├── providers
│   │   │   ├── __init__.py
│   │   │   ├── anthropic_provider.py
│   │   │   ├── backend_identity.py
│   │   │   ├── base_provider.py
│   │   │   ├── capabilities.py
│   │   │   ├── deepseek_provider.py
│   │   │   ├── error_classifier.py
│   │   │   ├── gemini_provider.py
│   │   │   ├── groq_provider.py
│   │   │   ├── llm_factory.py
│   │   │   ├── nine_router_provider.py
│   │   │   ├── ollama_provider.py
│   │   │   ├── openai_provider.py
│   │   │   ├── openrouter_provider.py
│   │   │   ├── pricing_catalog.py
│   │   │   ├── provider_failover_classifier.py
│   │   │   ├── provider_profile.py
│   │   │   ├── provider_registry.py
│   │   │   ├── runtime_model_registry.py
│   │   │   ├── streaming_think_scrubber.py
│   │   │   ├── structured_fallback.py
│   │   │   ├── trajectory_compressor.py
│   │   │   └── typesafe_provider.py
│   │   ├── schemas
│   │   │   ├── __init__.py
│   │   │   ├── pydantic_schemas.py
│   │   │   └── schemas.py
│   │   ├── stages
│   │   │   ├── per_asset
│   │   │   │   ├── __init__.py
│   │   │   │   ├── context_builder.py
│   │   │   │   ├── runner.py
│   │   │   │   ├── specialist_council.py
│   │   │   │   ├── specialist_pipeline.py
│   │   │   │   └── verifiers.py
│   │   │   ├── __init__.py
│   │   │   ├── fundamental_stage.py
│   │   │   ├── per_asset_stage.py
│   │   │   └── preflight_gate.py
│   │   ├── strategies
│   │   │   ├── synthesized
│   │   │   ├── __init__.py
│   │   │   ├── base_strategy.py
│   │   │   ├── btc_donchian_breakout.py
│   │   │   ├── decay_monitor.py
│   │   │   ├── gap_fade.py
│   │   │   ├── liquidity_sweep_edge.py
│   │   │   ├── pretrade_gate.py
│   │   │   ├── registry.py
│   │   │   ├── strategy_plugin.py
│   │   │   ├── tsm_momentum.py
│   │   │   ├── xau_trend_engine.py
│   │   │   └── xti_pairs_readiness.py
│   │   ├── subagent
│   │   │   ├── __init__.py
│   │   │   ├── adhoc_manager.py
│   │   │   └── isolated_harness.py
│   │   ├── tools
│   │   │   ├── core
│   │   │   │   ├── __init__.py
│   │   │   │   ├── coercion.py
│   │   │   │   ├── decorator.py
│   │   │   │   ├── definition.py
│   │   │   │   ├── dispatcher.py
│   │   │   │   └── toolset_registry.py
│   │   │   ├── domain
│   │   │   │   ├── __init__.py
│   │   │   │   ├── clarify_tool.py
│   │   │   │   ├── code_execution_tool.py
│   │   │   │   ├── code_search_tool.py
│   │   │   │   ├── computer_use_tool.py
│   │   │   │   ├── cron_tool.py
│   │   │   │   ├── delegate_tool.py
│   │   │   │   ├── execution_handlers.py
│   │   │   │   ├── file_tools.py
│   │   │   │   ├── kanban_tools.py
│   │   │   │   ├── macro_handlers.py
│   │   │   │   ├── multimodal_tools.py
│   │   │   │   ├── position_handlers.py
│   │   │   │   ├── sentiment_handlers.py
│   │   │   │   ├── skill_tools.py
│   │   │   │   ├── spill_reader_tool.py
│   │   │   │   ├── technical_handlers.py
│   │   │   │   ├── terminal_tools.py
│   │   │   │   ├── todo_tool.py
│   │   │   │   ├── tool_search_tools.py
│   │   │   │   └── web_tools.py
│   │   │   ├── environments
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base_environment.py
│   │   │   │   ├── pty_query_responder.py
│   │   │   │   ├── tier1_inprocess.py
│   │   │   │   ├── tier2_kernel.py
│   │   │   │   └── tier3_docker.py
│   │   │   ├── handlers
│   │   │   │   ├── __init__.py
│   │   │   │   ├── analysis_submit.py
│   │   │   │   ├── category_loader.py
│   │   │   │   ├── db_tools.py
│   │   │   │   ├── intelligence.py
│   │   │   │   ├── macro_data.py
│   │   │   │   ├── macro_tools.py
│   │   │   │   ├── market_data.py
│   │   │   │   ├── market_data_tools.py
│   │   │   │   ├── news_tools.py
│   │   │   │   ├── pattern_similarity_tools.py
│   │   │   │   ├── phase_transition.py
│   │   │   │   ├── position_mgmt.py
│   │   │   │   ├── ptc_handler.py
│   │   │   │   ├── scratchpad.py
│   │   │   │   ├── sentiment_data.py
│   │   │   │   ├── sentiment_tools.py
│   │   │   │   ├── skills_tools.py
│   │   │   │   ├── smc_tools.py
│   │   │   │   ├── system_info.py
│   │   │   │   ├── timesfm.py
│   │   │   │   ├── trade_intel.py
│   │   │   │   ├── trading_tools.py
│   │   │   │   └── verified_snapshot.py
│   │   │   ├── kernel
│   │   │   │   ├── code_execution_rpc.py
│   │   │   │   ├── env_sanitizer.py
│   │   │   │   ├── output_spiller.py
│   │   │   │   ├── persistent_kernel.py
│   │   │   │   ├── persistent_session_kernel.py
│   │   │   │   └── sandbox_runner.py
│   │   │   ├── quant_sandbox
│   │   │   │   ├── __init__.py
│   │   │   │   └── rpc_server.py
│   │   │   ├── __init__.py
│   │   │   ├── base_handler.py
│   │   │   ├── composite_tools.py
│   │   │   ├── executor.py
│   │   │   ├── file_patch_engine.py
│   │   │   ├── loop_guard.py
│   │   │   ├── registry.py
│   │   │   ├── terminal_process_engine.py
│   │   │   ├── tool_catalog.py
│   │   │   ├── tool_executor.py
│   │   │   ├── tool_guardrails.py
│   │   │   ├── tool_plugin.py
│   │   │   ├── tool_registry.py
│   │   │   ├── tool_result_storage.py
│   │   │   ├── tool_search_engine.py
│   │   │   ├── tool_selector.py
│   │   │   ├── tool_spill.py
│   │   │   ├── tools_definitions.py
│   │   │   └── unified_registry.py
│   │   ├── validators
│   │   │   ├── __init__.py
│   │   │   ├── adjudication_verifier.py
│   │   │   ├── adversarial_check.py
│   │   │   ├── confluence_verifier.py
│   │   │   ├── core_data_validator.py
│   │   │   ├── cross_timeframe_gate.py
│   │   │   ├── float_coercion.py
│   │   │   ├── fundamental_verifier.py
│   │   │   ├── in_harness_grounding.py
│   │   │   ├── market_snapshot.py
│   │   │   ├── output_verifier.py
│   │   │   └── precommit_gate.py
│   │   ├── event_broadcaster.py
│   │   ├── macro_pipeline_plugin.py
│   │   ├── pipeline_plugin.py
│   │   ├── prompt_sections.py
│   │   ├── scenario_tree.py
│   │   ├── subagent_blackboard.py
│   │   └── subagent_spawner.py
│   ├── backtest
│   │   ├── __init__.py
│   │   ├── alpha_validation.py
│   │   ├── batch_scenario_runner.py
│   │   ├── benchmark_tracker.py
│   │   ├── decision_memory.py
│   │   ├── isolated_strategy_harness.py
│   │   ├── monte_carlo_engine.py
│   │   ├── offline_signal_engine.py
│   │   ├── outcome_evaluator.py
│   │   ├── point_in_time_engine.py
│   │   ├── report_generator.py
│   │   ├── statistical_tests.py
│   │   ├── time_machine.py
│   │   └── walk_forward_engine.py
│   ├── benchmark
│   │   ├── fixtures
│   │   ├── results
│   │   ├── __init__.py
│   │   ├── alpha_arena.py
│   │   ├── config.py
│   │   ├── db_access.py
│   │   ├── db_models.py
│   │   ├── deterministic.py
│   │   ├── fixture_loader.py
│   │   ├── invoker.py
│   │   ├── judge.py
│   │   ├── model_registry.py
│   │   ├── paired_evaluator.py
│   │   ├── pricing.py
│   │   ├── prompt_evolution.py
│   │   ├── report.py
│   │   ├── runner.py
│   │   ├── system_one_scorer.py
│   │   ├── task_specs.py
│   │   ├── token_drift_tracker.py
│   │   └── trade_trajectory_logger.py
│   ├── cli
│   │   ├── chat
│   │   │   ├── __init__.py
│   │   │   ├── commands.py
│   │   │   ├── completer.py
│   │   │   ├── prompt.py
│   │   │   ├── renderer.py
│   │   │   ├── session.py
│   │   │   └── theme.py
│   │   ├── overlays
│   │   │   ├── __init__.py
│   │   │   ├── approval_modal.py
│   │   │   └── plugin_install_modal.py
│   │   ├── subcommands
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── daemon.py
│   │   │   ├── mcp.py
│   │   │   ├── simulation.py
│   │   │   └── trading.py
│   │   ├── __init__.py
│   │   ├── analysis_tree.py
│   │   ├── busy_input.py
│   │   ├── doctor.py
│   │   ├── main.py
│   │   ├── onboarding_trader.py
│   │   ├── platform_compat.py
│   │   ├── plugins.py
│   │   ├── profile_manager.py
│   │   ├── setup_wizard.py
│   │   ├── sparklines.py
│   │   ├── theme.py
│   │   ├── tui.py
│   │   ├── tui_chat.py
│   │   └── width_budget.py
│   ├── config
│   │   ├── plugins
│   │   │   └── discord_alert.yaml
│   │   ├── __init__.py
│   │   ├── atomic_writer.py
│   │   ├── config_manager.py
│   │   ├── config_migrations.py
│   │   ├── historical_macro_milestones.json
│   │   ├── hot_reload.py
│   │   ├── key_validator.py
│   │   ├── MACRO_REALITY.md
│   │   ├── migrations.py
│   │   ├── plugin_catalog.yaml
│   │   ├── schemas.py
│   │   ├── security.py
│   │   ├── settings.py
│   │   ├── settings.yaml
│   │   └── TRADING_SOUL.md
│   ├── data
│   │   └── .gitkeep
│   ├── data_sources
│   │   ├── __init__.py
│   │   ├── academic_search.py
│   │   ├── bond_yields_fetcher.py
│   │   ├── bond_yields_yfinance.py
│   │   ├── central_bank_watch.py
│   │   ├── cftc_cot.py
│   │   ├── circuit_breaker.py
│   │   ├── coinglass_funding.py
│   │   ├── dxy_yfinance.py
│   │   ├── eia_oil_inventory.py
│   │   ├── fear_greed.py
│   │   ├── fred_treasury_yield.py
│   │   ├── validators.py
│   │   ├── vix_yfinance.py
│   │   ├── web_reader.py
│   │   └── web_search.py
│   ├── database
│   │   ├── domain_models
│   │   │   ├── __init__.py
│   │   │   ├── analysis.py
│   │   │   ├── base.py
│   │   │   ├── market.py
│   │   │   ├── memory.py
│   │   │   ├── news.py
│   │   │   ├── system.py
│   │   │   └── trading.py
│   │   ├── migrations
│   │   │   ├── versions
│   │   │   ├── __init__.py
│   │   │   ├── env.py
│   │   │   ├── README
│   │   │   └── script.py.mako
│   │   ├── __init__.py
│   │   ├── adapters.py
│   │   ├── async_db.py
│   │   ├── cleanup.py
│   │   ├── db.py
│   │   ├── event_store.py
│   │   ├── fts5_cjk.py
│   │   ├── models.py
│   │   ├── repair_ledger.py
│   │   ├── safe_ops.py
│   │   ├── session_db_wal.py
│   │   └── session_lifecycle.py
│   ├── evals
│   │   ├── fixtures
│   │   ├── oracles
│   │   │   ├── __init__.py
│   │   │   ├── macro_regime_oracle.py
│   │   │   ├── risk_compliance_oracle.py
│   │   │   ├── smc_geometry_oracle.py
│   │   │   ├── tool_safety_oracle.py
│   │   │   └── trade_discipline_oracle.py
│   │   ├── __init__.py
│   │   ├── eval_metrics.py
│   │   ├── eval_runner.py
│   │   ├── hostile_market_probe.py
│   │   ├── runner.py
│   │   └── simulation_clock.py
│   ├── execution
│   │   ├── backends
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── docker_backend.py
│   │   │   └── local_backend.py
│   │   ├── ea_bridge
│   │   │   ├── __init__.py
│   │   │   ├── AIAgent_EA.mq5
│   │   │   ├── heartbeat_writer.py
│   │   │   └── watchdog.py
│   │   ├── service
│   │   │   ├── __init__.py
│   │   │   ├── audit_logger.py
│   │   │   ├── base.py
│   │   │   ├── emergency_manager.py
│   │   │   ├── order_creator.py
│   │   │   ├── order_executor.py
│   │   │   ├── position_synchronizer.py
│   │   │   ├── reconciliation.py
│   │   │   ├── risk_evaluator.py
│   │   │   ├── self_healing_executor.py
│   │   │   ├── sizing_calculator.py
│   │   │   ├── state_machine.py
│   │   │   └── trade_confirm.py
│   │   ├── __init__.py
│   │   ├── broker_adapter.py
│   │   ├── broker_plugin.py
│   │   ├── broker_registry.py
│   │   ├── effect_gate.py
│   │   ├── execution_service.py
│   │   ├── health_check.py
│   │   ├── idempotency_guard.py
│   │   ├── mt5_client.py
│   │   ├── mt5_compat.py
│   │   ├── order_emulator.py
│   │   ├── paper_tracker.py
│   │   ├── rate_throttler.py
│   │   └── verification_engine.py
│   ├── gateway
│   │   ├── platforms
│   │   │   ├── __init__.py
│   │   │   ├── discord_adapter.py
│   │   │   ├── slack_adapter.py
│   │   │   ├── telegram_adapter.py
│   │   │   └── webhook_adapter.py
│   │   ├── __init__.py
│   │   ├── acp_server.py
│   │   ├── api_server.py
│   │   ├── bot_loop_guard.py
│   │   ├── channel_router.py
│   │   ├── delivery_ledger.py
│   │   ├── omnichannel_router.py
│   │   ├── pairing.py
│   │   ├── platform_base.py
│   │   ├── stream_consumer.py
│   │   ├── turn_lease.py
│   │   └── webhook_ingress.py
│   ├── graph
│   │   ├── checkpointers
│   │   │   ├── __init__.py
│   │   │   ├── dual_checkpointer.py
│   │   │   └── sqlite_checkpointer.py
│   │   ├── nodes
│   │   │   ├── debate
│   │   │   │   ├── __init__.py
│   │   │   │   ├── bear_dissent_node.py
│   │   │   │   ├── bull_advocate_node.py
│   │   │   │   ├── debate_judge_node.py
│   │   │   │   ├── helpers.py
│   │   │   │   ├── rebuttal_node.py
│   │   │   │   ├── risk_evaluator_node.py
│   │   │   │   ├── round_robin_risk_nodes.py
│   │   │   │   └── subgraph.py
│   │   │   ├── __init__.py
│   │   │   ├── data_node.py
│   │   │   ├── debate_node.py
│   │   │   ├── execution_node.py
│   │   │   ├── fundamental_node.py
│   │   │   ├── per_asset_node.py
│   │   │   ├── plan_refinement_node.py
│   │   │   ├── reflection_node.py
│   │   │   ├── risk_gate_node.py
│   │   │   └── state_pruner.py
│   │   ├── __init__.py
│   │   ├── reactive_graph.py
│   │   ├── state.py
│   │   └── workflow.py
│   ├── harness
│   │   ├── adapters
│   │   │   ├── __init__.py
│   │   │   └── functional_adapter.py
│   │   ├── __init__.py
│   │   ├── context.py
│   │   ├── contract.py
│   │   ├── engine.py
│   │   ├── installer.py
│   │   └── lifecycle.py
│   ├── indicators
│   │   ├── pattern_similarity
│   │   │   ├── __init__.py
│   │   │   ├── context_scorer.py
│   │   │   ├── context_verifier.py
│   │   │   ├── engine.py
│   │   │   ├── feature_extractor.py
│   │   │   ├── models.py
│   │   │   ├── normalizer.py
│   │   │   ├── outcome_analyzer.py
│   │   │   └── scanner.py
│   │   ├── __init__.py
│   │   ├── microstructure.py
│   │   ├── order_flow.py
│   │   ├── regime_detector.py
│   │   ├── structure.py
│   │   ├── technical.py
│   │   └── timesfm_engine.py
│   ├── logging_observability
│   │   ├── dashboard
│   │   │   ├── frontend
│   │   │   │   ├── public
│   │   │   │   │   ├── favicon.svg
│   │   │   │   │   ├── icons.svg
│   │   │   │   │   └── mobius-master.svg
│   │   │   │   ├── src
│   │   │   │   │   ├── assets
│   │   │   │   │   │   ├── hero.png
│   │   │   │   │   │   ├── react.svg
│   │   │   │   │   │   └── vite.svg
│   │   │   │   │   ├── components
│   │   │   │   │   │   ├── charts
│   │   │   │   │   │   │   ├── DecisionDistribution.tsx
│   │   │   │   │   │   │   ├── EquityChart.tsx
│   │   │   │   │   │   │   ├── FactorHeatmap.tsx
│   │   │   │   │   │   │   ├── VixSparkline.tsx
│   │   │   │   │   │   │   └── WinRateGauge.tsx
│   │   │   │   │   │   ├── layout
│   │   │   │   │   │   │   ├── BreadcrumbBar.tsx
│   │   │   │   │   │   │   ├── GlobalStatusBar.tsx
│   │   │   │   │   │   │   ├── Header.tsx
│   │   │   │   │   │   │   ├── MobileNavDrawer.tsx
│   │   │   │   │   │   │   ├── navigation.ts
│   │   │   │   │   │   │   └── Sidebar.tsx
│   │   │   │   │   │   ├── panels
│   │   │   │   │   │   │   ├── config
│   │   │   │   │   │   │   │   ├── ConfigDiffModal.tsx
│   │   │   │   │   │   │   │   └── ConfigSection.tsx
│   │   │   │   │   │   │   ├── graph
│   │   │   │   │   │   │   │   ├── GraphControls.tsx
│   │   │   │   │   │   │   │   ├── GraphEdge.tsx
│   │   │   │   │   │   │   │   ├── GraphInspector.tsx
│   │   │   │   │   │   │   │   ├── GraphNode.tsx
│   │   │   │   │   │   │   │   └── graphUtils.ts
│   │   │   │   │   │   │   ├── tokens
│   │   │   │   │   │   │   │   ├── TokenCharts.tsx
│   │   │   │   │   │   │   │   └── TokenRoleTable.tsx
│   │   │   │   │   │   │   ├── ActivityFeed.tsx
│   │   │   │   │   │   │   ├── AgentChatPanel.tsx
│   │   │   │   │   │   │   ├── AnalysisGrid.tsx
│   │   │   │   │   │   │   ├── BacktestPanel.tsx
│   │   │   │   │   │   │   ├── BenchmarkPanel.tsx
│   │   │   │   │   │   │   ├── CockpitBar.tsx
│   │   │   │   │   │   │   ├── ConfigEditorPanel.tsx
│   │   │   │   │   │   │   ├── DebateOutcomesPanel.tsx
│   │   │   │   │   │   │   ├── EdgeMetricsPanel.tsx
│   │   │   │   │   │   │   ├── GraphVisualizerPanel.tsx
│   │   │   │   │   │   │   ├── MarketDataPanel.tsx
│   │   │   │   │   │   │   ├── MemoryBrowserPanel.tsx
│   │   │   │   │   │   │   ├── ObservabilityPanel.tsx
│   │   │   │   │   │   │   ├── PerformancePanel.tsx
│   │   │   │   │   │   │   ├── PluginManagerPanel.tsx
│   │   │   │   │   │   │   ├── PositionsTable.tsx
│   │   │   │   │   │   │   ├── RiskPanel.tsx
│   │   │   │   │   │   │   ├── SessionBrowserPanel.tsx
│   │   │   │   │   │   │   ├── SignalsTriggersPanel.tsx
│   │   │   │   │   │   │   ├── SkillManagerPanel.tsx
│   │   │   │   │   │   │   ├── SystemPanel.tsx
│   │   │   │   │   │   │   └── TokenAuditPanel.tsx
│   │   │   │   │   │   └── ui
│   │   │   │   │   │       ├── AnalogDial.tsx
│   │   │   │   │   │       ├── ApprovalModal.tsx
│   │   │   │   │   │       ├── Badge.tsx
│   │   │   │   │   │       ├── BootSequence.tsx
│   │   │   │   │   │       ├── Card.tsx
│   │   │   │   │   │       ├── ConfirmModal.tsx
│   │   │   │   │   │       ├── EmptyState.tsx
│   │   │   │   │   │       ├── ErrorBoundary.tsx
│   │   │   │   │   │       ├── Icons.tsx
│   │   │   │   │   │       ├── KeyboardShortcutsPanel.tsx
│   │   │   │   │   │       ├── LedgerTable.tsx
│   │   │   │   │   │       ├── MetricCard.tsx
│   │   │   │   │   │       ├── MonikaInfiniteIcon.tsx
│   │   │   │   │   │       ├── SegmentedProgressBar.tsx
│   │   │   │   │   │       ├── Skeleton.tsx
│   │   │   │   │   │       ├── StatusIndicator.tsx
│   │   │   │   │   │       ├── ThemeToggle.tsx
│   │   │   │   │   │       ├── TickerTape.tsx
│   │   │   │   │   │       ├── TypewriterButton.tsx
│   │   │   │   │   │       ├── VuMeter.tsx
│   │   │   │   │   │       ├── WeekendGapBanner.tsx
│   │   │   │   │   │       └── WindowFrame.tsx
│   │   │   │   │   ├── hooks
│   │   │   │   │   │   ├── useAgentChatWs.ts
│   │   │   │   │   │   ├── usePolling.ts
│   │   │   │   │   │   └── useWebSocket.ts
│   │   │   │   │   ├── lib
│   │   │   │   │   │   ├── api.ts
│   │   │   │   │   │   ├── formatters.ts
│   │   │   │   │   │   └── soundEffects.ts
│   │   │   │   │   ├── store
│   │   │   │   │   │   └── dashboardStore.ts
│   │   │   │   │   ├── theme
│   │   │   │   │   │   └── tokens.ts
│   │   │   │   │   ├── types
│   │   │   │   │   │   └── api.ts
│   │   │   │   │   ├── App.css
│   │   │   │   │   ├── App.tsx
│   │   │   │   │   ├── index.css
│   │   │   │   │   └── main.tsx
│   │   │   │   ├── .gitignore
│   │   │   │   ├── .oxlintrc.json
│   │   │   │   ├── index.html
│   │   │   │   ├── package-lock.json
│   │   │   │   ├── package.json
│   │   │   │   ├── README.md
│   │   │   │   ├── tsconfig.app.json
│   │   │   │   ├── tsconfig.json
│   │   │   │   ├── tsconfig.node.json
│   │   │   │   └── vite.config.ts
│   │   │   ├── routes
│   │   │   │   ├── __init__.py
│   │   │   │   ├── backtest.py
│   │   │   │   ├── benchmark.py
│   │   │   │   ├── common.py
│   │   │   │   ├── config.py
│   │   │   │   ├── intelligence.py
│   │   │   │   ├── mcp_server.py
│   │   │   │   ├── memory.py
│   │   │   │   ├── observability.py
│   │   │   │   ├── plugins.py
│   │   │   │   ├── system.py
│   │   │   │   ├── tokens.py
│   │   │   │   ├── trace_search.py
│   │   │   │   ├── trading.py
│   │   │   │   └── websocket.py
│   │   │   ├── __init__.py
│   │   │   ├── api.py
│   │   │   ├── log_streamer.py
│   │   │   ├── pty_bridge.py
│   │   │   ├── rbac.py
│   │   │   └── ws_ticket.py
│   │   ├── reporting
│   │   │   ├── __init__.py
│   │   │   └── tearsheet_generator.py
│   │   ├── tracing
│   │   │   ├── __init__.py
│   │   │   ├── context.py
│   │   │   ├── exporters.py
│   │   │   ├── otlp_exporter.py
│   │   │   ├── spans.py
│   │   │   └── tracer.py
│   │   ├── __init__.py
│   │   ├── activity_logger.py
│   │   ├── delegation_live_log.py
│   │   ├── metrics_exporter.py
│   │   ├── operator_feedback.py
│   │   ├── report_writer.py
│   │   ├── token_budgeter.py
│   │   └── trading_cycle_event_log.py
│   ├── plugin_kernel
│   │   └── __init__.py
│   ├── plugins
│   │   ├── alerts
│   │   │   └── discord_alert
│   │   │       ├── discord_alert.py
│   │   │       └── plugin.yaml
│   │   ├── analysis_pipelines
│   │   │   ├── macro_to_asset
│   │   │   │   ├── macro_to_asset_pipeline.py
│   │   │   │   └── plugin.yaml
│   │   │   └── technical_scalping
│   │   │       ├── plugin.yaml
│   │   │       └── scalping_pipeline.py
│   │   ├── brokers
│   │   │   ├── mt5_local
│   │   │   │   ├── mt5_plugin.py
│   │   │   │   └── plugin.yaml
│   │   │   └── paper_trading
│   │   │       ├── paper_plugin.py
│   │   │       └── plugin.yaml
│   │   ├── indicators
│   │   │   └── custom_indicator
│   │   │       ├── custom_indicator.py
│   │   │       └── plugin.yaml
│   │   ├── scrapers
│   │   │   └── example_scraper
│   │   │       ├── example_scraper.py
│   │   │       └── plugin.yaml
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── manifest.py
│   ├── provider
│   │   ├── __init__.py
│   │   ├── credential_pool.py
│   │   └── error_taxonomy.py
│   ├── risk
│   │   ├── invariants
│   │   │   ├── __init__.py
│   │   │   ├── position_count_invariant.py
│   │   │   ├── registry.py
│   │   │   ├── risk_gate_invariant.py
│   │   │   └── state_immutability_invariant.py
│   │   ├── __init__.py
│   │   ├── approval_hub.py
│   │   ├── approval_transport.py
│   │   ├── correlation_matrix.py
│   │   ├── execution_simulator.py
│   │   ├── portfolio_correlation_gate.py
│   │   ├── position_sizing.py
│   │   ├── risk_gate.py
│   │   ├── risk_rule_plugin.py
│   │   └── trade_proposal.py
│   ├── scheduler
│   │   ├── __init__.py
│   │   ├── active_calendar_poller.py
│   │   ├── alpha_discovery_scheduler.py
│   │   ├── cron_nlp_parser.py
│   │   ├── cycle_scheduler.py
│   │   ├── detached_cron_worker.py
│   │   ├── digest_slice_scheduler.py
│   │   ├── edge_strategy_runner.py
│   │   ├── flash_crash_detector.py
│   │   ├── graph_cycle_scheduler.py
│   │   ├── macro_data_scheduler.py
│   │   ├── market_data_scheduler.py
│   │   ├── news_watcher.py
│   │   ├── order_reconciler.py
│   │   ├── playbook_curator.py
│   │   ├── position_exit_reviewer.py
│   │   ├── position_guardian.py
│   │   ├── position_supervisor.py
│   │   ├── post_release_analyzer.py
│   │   ├── scraper_runner.py
│   │   ├── strategy_synthesis_scheduler.py
│   │   ├── task_plugin.py
│   │   ├── trailing_stop_manager.py
│   │   ├── trigger_checker.py
│   │   ├── unified_cron_engine.py
│   │   └── universal_cron_scheduler.py
│   ├── scrapers
│   │   ├── calendar
│   │   │   ├── __init__.py
│   │   │   ├── calendar_finnhub.py
│   │   │   ├── calendar_forexfactory.py
│   │   │   └── calendar_investing.py
│   │   ├── macro
│   │   │   ├── __init__.py
│   │   │   └── cme_fedwatch.py
│   │   ├── news
│   │   │   ├── __init__.py
│   │   │   ├── kitco_news.py
│   │   │   ├── rss_base.py
│   │   │   ├── rss_bloomberg.py
│   │   │   ├── rss_boe.py
│   │   │   ├── rss_boj.py
│   │   │   ├── rss_cnbc.py
│   │   │   ├── rss_coindesk.py
│   │   │   ├── rss_dow_jones.py
│   │   │   ├── rss_ecb.py
│   │   │   ├── rss_fed.py
│   │   │   ├── rss_forexlive.py
│   │   │   ├── rss_ft.py
│   │   │   ├── rss_fxstreet.py
│   │   │   ├── rss_investing.py
│   │   │   ├── rss_marketwatch.py
│   │   │   ├── rss_rba.py
│   │   │   ├── rss_reuters.py
│   │   │   ├── rss_wsj.py
│   │   │   └── tradingview_news.py
│   │   ├── sentiment
│   │   │   ├── __init__.py
│   │   │   ├── binance_sentiment.py
│   │   │   ├── fxssi_sentiment.py
│   │   │   └── myfxbook_sentiment.py
│   │   ├── social
│   │   │   ├── __init__.py
│   │   │   └── twitter_watch.py
│   │   ├── __init__.py
│   │   ├── base_scraper.py
│   │   └── models.py
│   ├── scripts
│   │   ├── check_scrapers
│   │   │   ├── __init__.py
│   │   │   ├── check_calendar.py
│   │   │   ├── check_cme.py
│   │   │   ├── check_news.py
│   │   │   ├── check_sentiment.py
│   │   │   └── check_twitter.py
│   │   ├── audit_token_usage.py
│   │   └── heal_kill_switch_state.py
│   ├── security
│   │   ├── __init__.py
│   │   ├── credential_vault.py
│   │   └── terminal_guard.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── market_data_service.py
│   │   ├── portfolio_service.py
│   │   └── system_status_service.py
│   ├── skills
│   │   ├── crystallized
│   │   │   └── eurusd_trend.md
│   │   ├── general
│   │   │   ├── academic-literature
│   │   │   │   └── SKILL.md
│   │   │   ├── code-optimization
│   │   │   │   └── SKILL.md
│   │   │   ├── codebase-inspection
│   │   │   │   └── SKILL.md
│   │   │   ├── data-science-modeling
│   │   │   │   └── SKILL.md
│   │   │   ├── devops-automation
│   │   │   │   └── SKILL.md
│   │   │   ├── financial-research
│   │   │   │   └── SKILL.md
│   │   │   ├── research-analysis
│   │   │   │   └── SKILL.md
│   │   │   ├── software-development
│   │   │   │   └── SKILL.md
│   │   │   └── systematic-debugging
│   │   │       └── SKILL.md
│   │   ├── operator
│   │   │   └── USER.md
│   │   ├── trading
│   │   │   ├── adjudication-framework
│   │   │   │   └── SKILL.md
│   │   │   ├── caveman-mode
│   │   │   │   └── SKILL.md
│   │   │   ├── central-banks-framework
│   │   │   │   └── SKILL.md
│   │   │   ├── commodity-analysis
│   │   │   │   └── SKILL.md
│   │   │   ├── cross-asset-regime-model
│   │   │   │   └── SKILL.md
│   │   │   ├── crypto-analysis
│   │   │   │   └── SKILL.md
│   │   │   ├── event-probability-playbook
│   │   │   │   └── SKILL.md
│   │   │   ├── fundamental-performance-notes
│   │   │   │   └── SKILL.md
│   │   │   ├── lessons-learned
│   │   │   │   └── SKILL.md
│   │   │   ├── liquidity-and-macro-edge
│   │   │   │   └── SKILL.md
│   │   │   ├── macro-analysis-framework
│   │   │   │   └── SKILL.md
│   │   │   ├── market-dynamics-framework
│   │   │   │   └── SKILL.md
│   │   │   ├── orderbook-liquidity-microstructure
│   │   │   │   └── SKILL.md
│   │   │   ├── performance-notes
│   │   │   │   └── SKILL.md
│   │   │   ├── risk-management-principles
│   │   │   │   └── SKILL.md
│   │   │   ├── session-timing-rules
│   │   │   │   └── SKILL.md
│   │   │   ├── smc-ict-playbook
│   │   │   │   └── SKILL.md
│   │   │   └── telegram-persona
│   │   │       └── SKILL.md
│   │   ├── __init__.py
│   │   ├── continuous_learning.py
│   │   ├── curator.py
│   │   ├── loader.py
│   │   ├── skill_manager.py
│   │   ├── skills_guard.py
│   │   ├── skills_hub.py
│   │   ├── trading_skill_linter.py
│   │   ├── unified_runtime.py
│   │   └── usage_tracker.py
│   ├── systemd
│   │   └── tradeagent.service
│   ├── telegram_bot
│   │   ├── __init__.py
│   │   ├── bot.py
│   │   ├── chat_agent.py
│   │   ├── chat_compaction.py
│   │   ├── chat_tool_router.py
│   │   ├── command_router.py
│   │   ├── fuzzy_router.py
│   │   ├── message_formatter.py
│   │   ├── sanitizer.py
│   │   ├── topic_manager.py
│   │   ├── voice_handler.py
│   │   └── voice_safety_gate.py
│   ├── tests
│   ├── utils
│   │   ├── analytics
│   │   │   ├── __init__.py
│   │   │   ├── adversarial_outcome_tracker.py
│   │   │   ├── agent_performance_monitor.py
│   │   │   ├── analysis_tracker.py
│   │   │   ├── cds_outcome_tracker.py
│   │   │   ├── cost_tracker.py
│   │   │   ├── edge_tracker.py
│   │   │   ├── models_dev_sync.py
│   │   │   ├── news_classification_tracker.py
│   │   │   ├── paper_tracker.py
│   │   │   ├── performance_reviewer.py
│   │   │   ├── pricing.py
│   │   │   ├── specialist_tracker.py
│   │   │   ├── strategy_edge_tracker.py
│   │   │   ├── token_auditor.py
│   │   │   └── trade_autopsy.py
│   │   ├── api
│   │   │   ├── __init__.py
│   │   │   ├── claude_rate_limiter.py
│   │   │   ├── credential_pool.py
│   │   │   ├── credit_balance_tracker.py
│   │   │   ├── gemini_rate_limiter.py
│   │   │   ├── groq_rate_limiter.py
│   │   │   ├── http_retry.py
│   │   │   ├── openrouter_rate_limiter.py
│   │   │   └── streaming.py
│   │   ├── calibration
│   │   │   ├── __init__.py
│   │   │   ├── cds_threshold_calibrator.py
│   │   │   ├── confidence_calibrator.py
│   │   │   ├── cot_thresholds.py
│   │   │   └── prescreen_calibrator.py
│   │   ├── infra
│   │   │   ├── __init__.py
│   │   │   ├── audit_settings_keys.py
│   │   │   ├── container.py
│   │   │   ├── db_backup.py
│   │   │   ├── env_file_manager.py
│   │   │   ├── event_loop.py
│   │   │   ├── log_redactor.py
│   │   │   ├── notifier.py
│   │   │   ├── platform_compat.py
│   │   │   └── worktree_manager.py
│   │   ├── llm
│   │   │   ├── __init__.py
│   │   │   ├── adaptive_thinking.py
│   │   │   ├── cache_breakpoint_manager.py
│   │   │   ├── cache_miss_detector.py
│   │   │   ├── caveman_compressor.py
│   │   │   ├── constrained_sampling.py
│   │   │   ├── context_compaction.py
│   │   │   ├── context_tracker.py
│   │   │   ├── credential_pool.py
│   │   │   ├── cycle_budget_guard.py
│   │   │   ├── data_dedup.py
│   │   │   ├── deferred_dispatcher.py
│   │   │   ├── embedding.py
│   │   │   ├── llmlingua_compressor.py
│   │   │   ├── memory_compressor.py
│   │   │   ├── model_capabilities.py
│   │   │   ├── model_discipline.py
│   │   │   ├── prompt_ab_test.py
│   │   │   ├── prompt_assembler.py
│   │   │   ├── prompt_caching.py
│   │   │   ├── prompt_compressor.py
│   │   │   ├── prompt_disciplines.py
│   │   │   ├── prompt_tiering.py
│   │   │   ├── prompt_tiers.py
│   │   │   ├── semantic_cache.py
│   │   │   ├── spill_subsystem.py
│   │   │   └── tool_condenser.py
│   │   ├── market
│   │   │   ├── __init__.py
│   │   │   ├── bias_utils.py
│   │   │   ├── brent_yfinance.py
│   │   │   ├── currency_utils.py
│   │   │   ├── direction.py
│   │   │   ├── dynamic_correlation.py
│   │   │   ├── instrument_identity.py
│   │   │   ├── news_impact_keywords.py
│   │   │   ├── session_info.py
│   │   │   ├── swap_estimator.py
│   │   │   └── usd_strength_proxy.py
│   │   ├── plugins
│   │   │   ├── __init__.py
│   │   │   ├── extension_loader.py
│   │   │   └── manager.py
│   │   ├── protocol
│   │   │   ├── __init__.py
│   │   │   ├── brief_contamination_guard.py
│   │   │   ├── coherence_flag_tracker.py
│   │   │   ├── context_coherence.py
│   │   │   ├── context_snapshot.py
│   │   │   ├── cross_agent_sync.py
│   │   │   ├── enhanced_cds.py
│   │   │   ├── event_bus.py
│   │   │   └── ssvp_coordinator.py
│   │   ├── scheduling
│   │   │   ├── __init__.py
│   │   │   └── wall_clock.py
│   │   ├── security
│   │   │   ├── nt_guard.py
│   │   │   ├── supply_chain_quarantine.py
│   │   │   ├── threat_detector.py
│   │   │   └── threat_scanner.py
│   │   ├── storage
│   │   │   └── spill_store.py
│   │   ├── streaming
│   │   │   ├── __init__.py
│   │   │   ├── stream_scrubber.py
│   │   │   └── streaming_lease.py
│   │   ├── typesafe
│   │   │   ├── __init__.py
│   │   │   └── jev_primitives.py
│   │   ├── validation
│   │   │   ├── __init__.py
│   │   │   ├── data_temporal_validator.py
│   │   │   ├── data_validator.py
│   │   │   ├── indicator_sanitizer.py
│   │   │   └── tool_response_validator.py
│   │   ├── __init__.py
│   │   ├── chart_generator.py
│   │   ├── clock.py
│   │   ├── constants.py
│   │   ├── content_distiller.py
│   │   ├── retry_decorator.py
│   │   ├── turn_marker.py
│   │   └── worktree.py
│   ├── .env.example
│   ├── __init__.py
│   ├── alembic.ini
│   ├── bootstrap.py
│   ├── docker-compose.linux.yml
│   ├── main.py
│   ├── PRD.md
│   ├── requirements.txt
│   ├── run_benchmark.py
│   ├── start_agent.bat
│   ├── start_agent.sh
│   ├── startup_agent.vbs
│   └── stop_agent.bat
├── .dockerignore
├── .env.example
├── .geminiignore
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── contoh_pertanyaan.md
├── CONTRIBUTING.md
├── DESIGN.md
├── docker-compose.yml
├── Dockerfile
├── GEMINI.md
├── INDEX.md
├── LICENSE
├── Makefile
├── PRD.md
├── prompt_benchmark.md
├── pyproject.toml
├── pyrightconfig.json
├── pytest.ini
├── README.md
├── SECURITY.md
├── setup.bat
├── setup.sh
├── skills-lock.json
└── STRUCTURE.md
