# Project Structure & Directory Layout

> **Auto-Generated File**: Generated via `python scripts/generate_ast_docs.py`.
> Do not edit manually.

```text
Monika/
│   └── monika/
│       ├── application/
│       │   ├── agent/
│       │   │   ├── chat/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── action_execution.py
│       │   │   │   ├── action_state.py
│       │   │   │   ├── base.py
│       │   │   │   ├── constants.py
│       │   │   │   ├── coordinator.py
│       │   │   │   ├── history.py
│       │   │   │   ├── pending_actions.py
│       │   │   │   ├── prompt_builder.py
│       │   │   │   ├── streaming.py
│       │   │   │   └── tiers.py
│       │   │   ├── harness/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── agent_harness.py
│       │   │   │   ├── anti_slop_gate.py
│       │   │   │   ├── context_compressor.py
│       │   │   │   ├── error_classifier.py
│       │   │   │   ├── general_tool_pruner.py
│       │   │   │   ├── harness_state.py
│       │   │   │   ├── interactive_todo.py
│       │   │   │   ├── message_repair.py
│       │   │   │   ├── physical_deliverable_gate.py
│       │   │   │   ├── repetition_guard.py
│       │   │   │   ├── stall_guard.py
│       │   │   │   ├── structured_output.py
│       │   │   │   ├── symbol_segment_planner.py
│       │   │   │   ├── tool_batch_planner.py
│       │   │   │   ├── tool_repair.py
│       │   │   │   ├── trade_stop_gates.py
│       │   │   │   ├── turn_failure_diagnostics.py
│       │   │   │   └── verification_evidence_ledger.py
│       │   │   ├── monitors/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── db_health.py
│       │   │   │   ├── drawdown_monitor.py
│       │   │   │   ├── margin_monitor.py
│       │   │   │   ├── paper_trade_monitor.py
│       │   │   │   ├── process_guardian.py
│       │   │   │   ├── scraper_loop.py
│       │   │   │   └── startup_watchdog.py
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
│       │   │   ├── moa_alternation.py
│       │   │   ├── moa_loop.py
│       │   │   ├── moa_trace.py
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
│       │   ├── analysis/
│       │   │   ├── arbitration/
│       │   │   │   ├── __init__.py
│       │   │   │   └── signal_arbitrator.py
│       │   │   ├── calculators/
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
│       │   │   │   ├── technical_regime_calculator.py
│       │   │   │   ├── timesfm_alpha.py
│       │   │   │   ├── timesfm_residual_validator.py
│       │   │   │   ├── unified_threshold_calculator.py
│       │   │   │   ├── universal_cb_differ.py
│       │   │   │   ├── universal_liquidity_analyzer.py
│       │   │   │   ├── universal_macro_analyzer.py
│       │   │   │   └── volume_profile.py
│       │   │   ├── debate/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adjustment_validator.py
│       │   │   │   ├── aggressive_risk_llm.py
│       │   │   │   ├── bear_analyst.py
│       │   │   │   ├── blackboard.py
│       │   │   │   ├── bull_analyst.py
│       │   │   │   ├── conservative_risk_llm.py
│       │   │   │   ├── debate_orchestrator.py
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
│       │   │   ├── evaluation/
│       │   │   │   ├── __init__.py
│       │   │   │   └── decision_quality.py
│       │   │   ├── grounding/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── declared_figures.py
│       │   │   │   ├── market_grounding.py
│       │   │   │   ├── provenance_tagger.py
│       │   │   │   └── surgical_redaction.py
│       │   │   ├── journal/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── attribution_engine.py
│       │   │   │   ├── behavioral_diagnostics.py
│       │   │   │   ├── journal_parser.py
│       │   │   │   └── shadow_extractor.py
│       │   │   ├── memory/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── alpha_calculator.py
│       │   │   │   ├── background_review.py
│       │   │   │   ├── background_review_fork.py
│       │   │   │   ├── chronicle_curator.py
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
│       │   │   ├── prefetch/
│       │   │   │   ├── news_digest/
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
│       │   │   │   ├── __init__.py
│       │   │   │   ├── digest_slice_generator.py
│       │   │   │   ├── macro_preprocessor.py
│       │   │   │   ├── news_digest.py
│       │   │   │   ├── pipeline.py
│       │   │   │   ├── sentiment_aggregator.py
│       │   │   │   ├── stage1_prefetcher.py
│       │   │   │   └── stage2_prefetcher.py
│       │   │   ├── prompt/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── prompt_assembler.py
│       │   │   │   └── risk_contract.py
│       │   │   ├── recursive_harness/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── composer.py
│       │   │   │   ├── library.py
│       │   │   │   ├── prober.py
│       │   │   │   ├── proposer.py
│       │   │   │   ├── selector.py
│       │   │   │   ├── service.py
│       │   │   │   ├── surface.py
│       │   │   │   └── tree.py
│       │   │   ├── research/
│       │   │   │   ├── __init__.py
│       │   │   │   └── macro_playbook_runner.py
│       │   │   ├── schemas/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── pydantic_schemas.py
│       │   │   │   └── schemas.py
│       │   │   ├── stages/
│       │   │   │   ├── per_asset/
│       │   │   │   │   ├── runner_mixins/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── base.py
│       │   │   │   │   │   ├── batch_orchestrator.py
│       │   │   │   │   │   ├── post_verifications.py
│       │   │   │   │   │   ├── prescreen.py
│       │   │   │   │   │   ├── recovery.py
│       │   │   │   │   │   ├── single_asset.py
│       │   │   │   │   │   └── single_asset_helpers.py
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── context_builder.py
│       │   │   │   │   ├── runner.py
│       │   │   │   │   ├── specialist_council.py
│       │   │   │   │   ├── specialist_pipeline.py
│       │   │   │   │   └── verifiers.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── fundamental_stage.py
│       │   │   │   ├── fundamental_stage_recovery.py
│       │   │   │   ├── per_asset_stage.py
│       │   │   │   └── preflight_gate.py
│       │   │   ├── strategies/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── asian_range_fade.py
│       │   │   │   ├── base_strategy.py
│       │   │   │   ├── bb_volume_profile.py
│       │   │   │   ├── bollinger_reversion.py
│       │   │   │   ├── btc_donchian_breakout.py
│       │   │   │   ├── btc_us_momentum.py
│       │   │   │   ├── btcusd_dynamic_donchian.py
│       │   │   │   ├── crude_london_breakout.py
│       │   │   │   ├── decay_monitor.py
│       │   │   │   ├── evidence_store.py
│       │   │   │   ├── gap_fade.py
│       │   │   │   ├── gbpusd_trend_breakout.py
│       │   │   │   ├── hypothesis_registry.py
│       │   │   │   ├── liquidity_sweep_edge.py
│       │   │   │   ├── london_gold_breakout.py
│       │   │   │   ├── london_trend_breakout.py
│       │   │   │   ├── pretrade_gate.py
│       │   │   │   ├── registry.py
│       │   │   │   ├── smc_fvg.py
│       │   │   │   ├── smt_divergence.py
│       │   │   │   ├── strategy_plugin.py
│       │   │   │   ├── tokyo_range_fade.py
│       │   │   │   ├── tokyo_sweep.py
│       │   │   │   ├── tri_convergent_alpha.py
│       │   │   │   ├── tsm_momentum.py
│       │   │   │   ├── usdjpy_atr_exhaustion.py
│       │   │   │   ├── vwap_reversion.py
│       │   │   │   ├── xau_trend_engine.py
│       │   │   │   ├── xauusd_atr_exhaustion.py
│       │   │   │   ├── xti_pairs_readiness.py
│       │   │   │   └── xtiusd_atr_exhaustion.py
│       │   │   ├── subagent/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adhoc_manager.py
│       │   │   │   └── isolated_harness.py
│       │   │   ├── tools/
│       │   │   │   ├── core/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── coercion.py
│       │   │   │   │   ├── decorator.py
│       │   │   │   │   ├── definition.py
│       │   │   │   │   ├── dispatcher.py
│       │   │   │   │   └── toolset_registry.py
│       │   │   │   ├── definitions/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── base.py
│       │   │   │   │   ├── files.py
│       │   │   │   │   ├── groups.py
│       │   │   │   │   ├── intelligence.py
│       │   │   │   │   ├── macro.py
│       │   │   │   │   ├── market.py
│       │   │   │   │   ├── smc.py
│       │   │   │   │   ├── system.py
│       │   │   │   │   └── trading.py
│       │   │   │   ├── domain/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── browser_tool.py
│       │   │   │   │   ├── clarify_tool.py
│       │   │   │   │   ├── code_execution_tool.py
│       │   │   │   │   ├── code_search_tool.py
│       │   │   │   │   ├── computer_use_tool.py
│       │   │   │   │   ├── cron_tool.py
│       │   │   │   │   ├── delegate_tool.py
│       │   │   │   │   ├── execution_handlers.py
│       │   │   │   │   ├── file_tools.py
│       │   │   │   │   ├── kanban_tools.py
│       │   │   │   │   ├── macro_handlers.py
│       │   │   │   │   ├── multimodal_tools.py
│       │   │   │   │   ├── position_handlers.py
│       │   │   │   │   ├── sentiment_handlers.py
│       │   │   │   │   ├── skill_tools.py
│       │   │   │   │   ├── spill_reader_tool.py
│       │   │   │   │   ├── technical_handlers.py
│       │   │   │   │   ├── terminal_tools.py
│       │   │   │   │   ├── todo_tool.py
│       │   │   │   │   ├── tool_search_tools.py
│       │   │   │   │   └── web_tools.py
│       │   │   │   ├── environments/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── base_environment.py
│       │   │   │   │   ├── pty_query_responder.py
│       │   │   │   │   ├── tier1_inprocess.py
│       │   │   │   │   ├── tier2_kernel.py
│       │   │   │   │   └── tier3_docker.py
│       │   │   │   ├── handlers/
│       │   │   │   │   ├── macro/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── base.py
│       │   │   │   │   │   ├── calendar.py
│       │   │   │   │   │   ├── central_banks.py
│       │   │   │   │   │   ├── fixed_income.py
│       │   │   │   │   │   ├── regime.py
│       │   │   │   │   │   ├── registration.py
│       │   │   │   │   │   └── sentiment_commodities.py
│       │   │   │   │   ├── market_data_handlers/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── base.py
│       │   │   │   │   │   ├── charts.py
│       │   │   │   │   │   ├── quotes_prices.py
│       │   │   │   │   │   ├── registration.py
│       │   │   │   │   │   ├── structures_smc.py
│       │   │   │   │   │   └── technicals.py
│       │   │   │   │   ├── trade_intel/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── base.py
│       │   │   │   │   │   ├── debate.py
│       │   │   │   │   │   ├── operations.py
│       │   │   │   │   │   ├── performance.py
│       │   │   │   │   │   ├── registry.py
│       │   │   │   │   │   ├── reporting.py
│       │   │   │   │   │   └── simulation.py
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── advanced_quant_tools.py
│       │   │   │   │   ├── analysis_submit.py
│       │   │   │   │   ├── analytical_query_builder.py
│       │   │   │   │   ├── behavioral_alert_tool.py
│       │   │   │   │   ├── broker_profile_tool.py
│       │   │   │   │   ├── category_loader.py
│       │   │   │   │   ├── chart_bridge_tools.py
│       │   │   │   │   ├── db_tools.py
│       │   │   │   │   ├── execution_handlers.py
│       │   │   │   │   ├── intelligence.py
│       │   │   │   │   ├── macro_data.py
│       │   │   │   │   ├── macro_tools.py
│       │   │   │   │   ├── market_data.py
│       │   │   │   │   ├── market_data_tools.py
│       │   │   │   │   ├── news_tools.py
│       │   │   │   │   ├── pattern_similarity_tools.py
│       │   │   │   │   ├── phase_transition.py
│       │   │   │   │   ├── position_mgmt.py
│       │   │   │   │   ├── ptc_handler.py
│       │   │   │   │   ├── scratchpad.py
│       │   │   │   │   ├── sentiment_data.py
│       │   │   │   │   ├── sentiment_tools.py
│       │   │   │   │   ├── skills_tools.py
│       │   │   │   │   ├── smc_tools.py
│       │   │   │   │   ├── system_info.py
│       │   │   │   │   ├── timesfm.py
│       │   │   │   │   ├── trade_intel.py
│       │   │   │   │   ├── trading_tools.py
│       │   │   │   │   └── verified_snapshot.py
│       │   │   │   ├── kernel/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── code_execution_rpc.py
│       │   │   │   │   ├── env_sanitizer.py
│       │   │   │   │   ├── output_spiller.py
│       │   │   │   │   ├── persistent_kernel.py
│       │   │   │   │   ├── persistent_session_kernel.py
│       │   │   │   │   └── sandbox_runner.py
│       │   │   │   ├── mixins/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── analysis_submission.py
│       │   │   │   │   ├── analysis_validation.py
│       │   │   │   │   ├── base.py
│       │   │   │   │   ├── brief_submission.py
│       │   │   │   │   └── system_tools.py
│       │   │   │   ├── quant_sandbox/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   └── rpc_server.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base_handler.py
│       │   │   │   ├── composite_tools.py
│       │   │   │   ├── executor.py
│       │   │   │   ├── file_patch_engine.py
│       │   │   │   ├── loop_guard.py
│       │   │   │   ├── registry.py
│       │   │   │   ├── terminal_process_engine.py
│       │   │   │   ├── tool_catalog.py
│       │   │   │   ├── tool_executor.py
│       │   │   │   ├── tool_guardrails.py
│       │   │   │   ├── tool_plugin.py
│       │   │   │   ├── tool_registry.py
│       │   │   │   ├── tool_result_storage.py
│       │   │   │   ├── tool_search_engine.py
│       │   │   │   ├── tool_selector.py
│       │   │   │   ├── tool_spill.py
│       │   │   │   ├── tools_definitions.py
│       │   │   │   └── unified_registry.py
│       │   │   ├── validators/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── adjudication_verifier.py
│       │   │   │   ├── adversarial_check.py
│       │   │   │   ├── confluence_verifier.py
│       │   │   │   ├── core_data_validator.py
│       │   │   │   ├── cross_timeframe_gate.py
│       │   │   │   ├── float_coercion.py
│       │   │   │   ├── fundamental_verifier.py
│       │   │   │   ├── in_harness_grounding.py
│       │   │   │   ├── market_snapshot.py
│       │   │   │   ├── output_verifier.py
│       │   │   │   └── precommit_gate.py
│       │   │   ├── __init__.py
│       │   │   ├── event_broadcaster.py
│       │   │   ├── macro_pipeline_plugin.py
│       │   │   ├── pipeline_plugin.py
│       │   │   ├── prompt_sections.py
│       │   │   ├── scenario_tree.py
│       │   │   ├── subagent_blackboard.py
│       │   │   └── subagent_spawner.py
│       │   ├── backtest/
│       │   │   ├── engines/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── crypto_engine.py
│       │   │   │   ├── equity_engine.py
│       │   │   │   ├── forex_engine.py
│       │   │   │   └── futures_engine.py
│       │   │   ├── __init__.py
│       │   │   ├── alpha_validation.py
│       │   │   ├── batch_scenario_runner.py
│       │   │   ├── benchmark_tracker.py
│       │   │   ├── decision_memory.py
│       │   │   ├── isolated_strategy_harness.py
│       │   │   ├── matrix_alignment.py
│       │   │   ├── monte_carlo_engine.py
│       │   │   ├── offline_signal_engine.py
│       │   │   ├── outcome_evaluator.py
│       │   │   ├── performance_metrics.py
│       │   │   ├── point_in_time_engine.py
│       │   │   ├── price_series.py
│       │   │   ├── report_generator.py
│       │   │   ├── run_card.py
│       │   │   ├── statistical_tests.py
│       │   │   ├── time_machine.py
│       │   │   └── walk_forward_engine.py
│       │   ├── benchmark/
│       │   │   ├── fixtures/
│       │   │   │   ├── debate/
│       │   │   │   │   ├── eurusd_dialectical_clash.json
│       │   │   │   │   ├── jev_debate_micro_clash.json
│       │   │   │   │   └── stage2_adjudication_conflict.json
│       │   │   │   ├── macro/
│       │   │   │   │   ├── cot_institutional_report.json
│       │   │   │   │   ├── economic_calendar_week.json
│       │   │   │   │   ├── escalation_geopolitical_crisis.json
│       │   │   │   │   ├── fomc_press_conference_transcript.txt
│       │   │   │   │   ├── full_production_stage1_bundle.json
│       │   │   │   │   ├── golden_macro_stage1_20261001.json
│       │   │   │   │   ├── raw_unfiltered_transcript_12p.txt
│       │   │   │   │   ├── session_reports_multi_asset.json
│       │   │   │   │   └── shadow_check_audit_case.json
│       │   │   │   ├── news/
│       │   │   │   │   ├── breaking_news_escalation.json
│       │   │   │   │   ├── production_curated_news_digest.json
│       │   │   │   │   ├── production_news_1000_daily.json
│       │   │   │   │   └── raw_news_batch_25.json
│       │   │   │   ├── omnichannel/
│       │   │   │   │   ├── interactive_reasoning_prompts.json
│       │   │   │   │   ├── telegram_conversations.json
│       │   │   │   │   └── voice_transcripts_id_en.json
│       │   │   │   ├── per_asset/
│       │   │   │   │   ├── btcusd_golden_bundle.json
│       │   │   │   │   ├── eurusd_golden_bundle.json
│       │   │   │   │   ├── full_production_stage2_bundles.json
│       │   │   │   │   ├── gbpusd_golden_bundle.json
│       │   │   │   │   ├── prescreen_multi_asset_matrix.json
│       │   │   │   │   ├── usdjpy_golden_bundle.json
│       │   │   │   │   ├── xauusd_golden_bundle.json
│       │   │   │   │   └── xtiusd_golden_bundle.json
│       │   │   │   ├── risk/
│       │   │   │   │   ├── adversarial_liquidity_trap.json
│       │   │   │   │   ├── curated_decision_reflections.json
│       │   │   │   │   ├── multi_asset_concurrent_orders.json
│       │   │   │   │   ├── risk_gate_defensive_drawdown.json
│       │   │   │   │   ├── risk_gate_production_state.json
│       │   │   │   │   └── trade_reflection_postmortem.json
│       │   │   │   ├── specialists/
│       │   │   │   │   ├── pattern_historical_match_case.json
│       │   │   │   │   ├── sentiment_cot_retail_matrix.json
│       │   │   │   │   └── technical_multi_tf_indicators.json
│       │   │   │   ├── system1_jev/
│       │   │   │   │   ├── jev_confluence_gate_state.json
│       │   │   │   │   ├── jev_reflex_suite.json
│       │   │   │   │   └── jev_session_timing_state.json
│       │   │   │   ├── _market_snapshot_2026_09.json
│       │   │   │   ├── macro_dxy_eur_divergence.json
│       │   │   │   ├── macro_fomc_blackout.json
│       │   │   │   ├── metadata.json
│       │   │   │   ├── news_hormuz_escalation.json
│       │   │   │   ├── news_nfp_release.json
│       │   │   │   ├── production_macro_snapshot.json
│       │   │   │   ├── production_news_snapshot.json
│       │   │   │   ├── production_smc_snapshot_btcusd.json
│       │   │   │   ├── production_smc_snapshot_eurusd.json
│       │   │   │   ├── production_smc_snapshot_gbpusd.json
│       │   │   │   ├── production_smc_snapshot_usdjpy.json
│       │   │   │   ├── production_smc_snapshot_xauusd.json
│       │   │   │   ├── production_smc_snapshot_xtiusd.json
│       │   │   │   ├── risk_eurusd_daily_drawdown.json
│       │   │   │   ├── risk_eurusd_spread_spike.json
│       │   │   │   ├── risk_portfolio_max_heat.json
│       │   │   │   ├── risk_xauusd_high_vix_defensive.json
│       │   │   │   ├── s1_exit_prescreen_gbpusd.json
│       │   │   │   ├── s1_news_breaking_iran.json
│       │   │   │   ├── s1_position_guard_xauusd.json
│       │   │   │   ├── s1_stage2_prescreen_eurusd.json
│       │   │   │   ├── s1_trigger_stale_eurusd.json
│       │   │   │   ├── smc_eurusd_h1_bull_displacement.json
│       │   │   │   ├── smc_gbpusd_h1_choppy_trap.json
│       │   │   │   └── smc_xauusd_m15_bear_sweep.json
│       │   │   ├── results/
│       │   │   │   ├── benchmark_leaderboard.json
│       │   │   │   ├── benchmark_leaderboard.md
│       │   │   │   ├── benchmark_stage1_fundamental_openrouter.md
│       │   │   │   ├── benchmark_stage1_results.json
│       │   │   │   ├── benchmark_stage2_per_asset_openrouter.md
│       │   │   │   ├── benchmark_stage2_results.json
│       │   │   │   ├── model_all.csv
│       │   │   │   ├── model_cheap_efficient.csv
│       │   │   │   ├── model_cheap_smart.csv
│       │   │   │   ├── model_high_intelligence.csv
│       │   │   │   └── model_quadrant_analysis.html
│       │   │   ├── task_specs/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py
│       │   │   │   ├── chat_cases.py
│       │   │   │   ├── debate_cases.py
│       │   │   │   ├── macro_cases.py
│       │   │   │   ├── news_cases.py
│       │   │   │   ├── reflex_cases.py
│       │   │   │   ├── registry.py
│       │   │   │   ├── risk_cases.py
│       │   │   │   ├── specialist_cases.py
│       │   │   │   └── stage2_cases.py
│       │   │   ├── __init__.py
│       │   │   ├── alpha_arena.py
│       │   │   ├── benchmark_scorer.py
│       │   │   ├── config.py
│       │   │   ├── db_access.py
│       │   │   ├── db_models.py
│       │   │   ├── deterministic.py
│       │   │   ├── fixture_loader.py
│       │   │   ├── invoker.py
│       │   │   ├── judge.py
│       │   │   ├── model_registry.py
│       │   │   ├── paired_evaluator.py
│       │   │   ├── pricing.py
│       │   │   ├── prompt_evolution.py
│       │   │   ├── report.py
│       │   │   ├── run_benchmark.py
│       │   │   ├── runner.py
│       │   │   ├── system_one_scorer.py
│       │   │   ├── task_specs.py
│       │   │   ├── token_drift_tracker.py
│       │   │   └── trade_trajectory_logger.py
│       │   ├── evals/
│       │   │   ├── fixtures/
│       │   │   │   ├── risk_trap_daily_dd.json
│       │   │   │   ├── risk_trap_spread_spike.json
│       │   │   │   ├── smc_bear_sweep.json
│       │   │   │   ├── smc_bull_displacement.json
│       │   │   │   ├── smc_choppy_trap.json
│       │   │   │   └── tool_jailbreak_trap.json
│       │   │   ├── oracles/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── macro_regime_oracle.py
│       │   │   │   ├── risk_compliance_oracle.py
│       │   │   │   ├── smc_geometry_oracle.py
│       │   │   │   ├── tool_safety_oracle.py
│       │   │   │   └── trade_discipline_oracle.py
│       │   │   ├── __init__.py
│       │   │   ├── eval_metrics.py
│       │   │   ├── eval_runner.py
│       │   │   ├── harness_audit.py
│       │   │   ├── hostile_market_probe.py
│       │   │   ├── llm_replay.py
│       │   │   ├── runner.py
│       │   │   └── simulation_clock.py
│       │   ├── execution/
│       │   │   ├── service/
│       │   │   │   ├── executors/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── analysis_executor.py
│       │   │   │   │   ├── analysis_preflight.py
│       │   │   │   │   ├── analysis_submission.py
│       │   │   │   │   ├── base.py
│       │   │   │   │   ├── paired_executor.py
│       │   │   │   │   ├── preplanned_executor.py
│       │   │   │   │   ├── proposal_executor.py
│       │   │   │   │   └── tranche_executor.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py
│       │   │   │   ├── emergency_manager.py
│       │   │   │   ├── multi_account_adapter.py
│       │   │   │   ├── order_executor.py
│       │   │   │   ├── order_lifecycle_service.py
│       │   │   │   ├── position_synchronizer.py
│       │   │   │   ├── reconciliation.py
│       │   │   │   ├── risk_evaluator.py
│       │   │   │   ├── self_healing_executor.py
│       │   │   │   └── trade_confirm.py
│       │   │   ├── __init__.py
│       │   │   ├── broker_registry.py
│       │   │   ├── effect_gate.py
│       │   │   ├── execution_service.py
│       │   │   └── health_check.py
│       │   ├── governance/
│       │   │   ├── __init__.py
│       │   │   └── run_manifest.py
│       │   ├── graph/
│       │   │   ├── nodes/
│       │   │   │   ├── debate/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── bear_dissent_node.py
│       │   │   │   │   ├── bull_advocate_node.py
│       │   │   │   │   ├── debate_judge_node.py
│       │   │   │   │   ├── helpers.py
│       │   │   │   │   ├── rebuttal_node.py
│       │   │   │   │   ├── risk_evaluator_node.py
│       │   │   │   │   ├── round_robin_risk_nodes.py
│       │   │   │   │   └── subgraph.py
│       │   │   │   ├── risk/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── level_synthesizer.py
│       │   │   │   │   ├── portfolio_synthesis.py
│       │   │   │   │   ├── proposal_notifier.py
│       │   │   │   │   ├── quant_arbitration.py
│       │   │   │   │   └── rejection_auditor.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── data_node.py
│       │   │   │   ├── debate_node.py
│       │   │   │   ├── execution_node.py
│       │   │   │   ├── fundamental_node.py
│       │   │   │   ├── per_asset_node.py
│       │   │   │   ├── plan_refinement_node.py
│       │   │   │   ├── reflection_node.py
│       │   │   │   ├── risk_gate_node.py
│       │   │   │   └── state_pruner.py
│       │   │   ├── presets/
│       │   │   │   ├── crypto_trading_desk.yaml
│       │   │   │   ├── gold_commodity_desk.yaml
│       │   │   │   ├── investment_committee.yaml
│       │   │   │   └── macro_rates_fx_desk.yaml
│       │   │   ├── __init__.py
│       │   │   ├── grounding.py
│       │   │   ├── reactive_graph.py
│       │   │   ├── state.py
│       │   │   ├── team_compiler.py
│       │   │   └── workflow.py
│       │   ├── orchestrator/
│       │   │   ├── __init__.py
│       │   │   ├── agent.py
│       │   │   ├── builder.py
│       │   │   ├── entrypoints.py
│       │   │   ├── lifecycle.py
│       │   │   ├── monitors.py
│       │   │   └── recovery.py
│       │   ├── planning/
│       │   │   └── session_plan.py
│       │   ├── plugins/
│       │   │   ├── alerts/
│       │   │   │   └── discord_alert/
│       │   │   │       ├── __init__.py
│       │   │   │       ├── discord_alert.py
│       │   │   │       └── plugin.yaml
│       │   │   ├── analysis_pipelines/
│       │   │   │   ├── macro_to_asset/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── macro_to_asset_pipeline.py
│       │   │   │   │   └── plugin.yaml
│       │   │   │   └── technical_scalping/
│       │   │   │       ├── __init__.py
│       │   │   │       ├── plugin.yaml
│       │   │   │       └── scalping_pipeline.py
│       │   │   ├── brokers/
│       │   │   │   ├── mt5_local/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── mt5_plugin.py
│       │   │   │   │   └── plugin.yaml
│       │   │   │   └── paper_trading/
│       │   │   │       ├── __init__.py
│       │   │   │       ├── paper_plugin.py
│       │   │   │       └── plugin.yaml
│       │   │   ├── engine/
│       │   │   │   ├── adapters/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   └── functional_adapter.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── context.py
│       │   │   │   ├── contract.py
│       │   │   │   ├── engine.py
│       │   │   │   ├── installer.py
│       │   │   │   └── lifecycle.py
│       │   │   ├── indicators/
│       │   │   │   └── custom_indicator/
│       │   │   │       ├── __init__.py
│       │   │   │       ├── custom_indicator.py
│       │   │   │       └── plugin.yaml
│       │   │   ├── manager/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── extension_loader.py
│       │   │   │   └── manager.py
│       │   │   ├── scrapers/
│       │   │   │   └── example_scraper/
│       │   │   │       ├── __init__.py
│       │   │   │       ├── example_scraper.py
│       │   │   │       └── plugin.yaml
│       │   │   ├── __init__.py
│       │   │   ├── kernel.py
│       │   │   ├── loader.py
│       │   │   └── manifest.py
│       │   ├── protocol/
│       │   │   ├── __init__.py
│       │   │   ├── brief_contamination_guard.py
│       │   │   ├── coherence_flag_tracker.py
│       │   │   ├── context_coherence.py
│       │   │   ├── context_snapshot.py
│       │   │   ├── cross_agent_sync.py
│       │   │   ├── enhanced_cds.py
│       │   │   └── ssvp_coordinator.py
│       │   ├── scheduler/
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
│       │   │   ├── universal_cron_scheduler.py
│       │   │   └── wall_clock.py
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   ├── general_harness_service.py
│       │   │   ├── market_data_service.py
│       │   │   ├── market_intel_service.py
│       │   │   ├── market_structure_service.py
│       │   │   ├── order_flow_service.py
│       │   │   ├── portfolio_service.py
│       │   │   ├── system_status_service.py
│       │   │   ├── technical_indicator_service.py
│       │   │   └── trading_service.py
│       │   ├── skills/
│       │   │   ├── __init__.py
│       │   │   ├── continuous_learning.py
│       │   │   ├── curator.py
│       │   │   ├── loader.py
│       │   │   ├── skill_manager.py
│       │   │   ├── skills_guard.py
│       │   │   ├── skills_hub.py
│       │   │   ├── trading_skill_linter.py
│       │   │   ├── unified_runtime.py
│       │   │   └── usage_tracker.py
│       │   ├── __init__.py
│       │   ├── bootstrap.py
│       │   └── main.py
│       ├── core/
│       │   ├── analytics/
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
│       │   ├── calibration/
│       │   │   ├── __init__.py
│       │   │   ├── cds_threshold_calibrator.py
│       │   │   ├── confidence_calibrator.py
│       │   │   ├── cot_thresholds.py
│       │   │   └── prescreen_calibrator.py
│       │   ├── config/
│       │   │   ├── __init__.py
│       │   │   ├── atomic_writer.py
│       │   │   ├── audit_settings_keys.py
│       │   │   ├── config_manager.py
│       │   │   ├── config_migrations.py
│       │   │   ├── env_file_manager.py
│       │   │   ├── hot_reload.py
│       │   │   ├── key_validator.py
│       │   │   ├── migrations.py
│       │   │   ├── profile_applicator.py
│       │   │   ├── protocols.py
│       │   │   ├── risk_defaults.py
│       │   │   ├── schemas.py
│       │   │   ├── security.py
│       │   │   └── settings.py
│       │   ├── contracts/
│       │   │   ├── __init__.py
│       │   │   └── plugin.py
│       │   ├── primitives/
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
│       │   ├── risk/
│       │   │   ├── __init__.py
│       │   │   └── quant_scorecard.py
│       │   ├── security/
│       │   │   ├── __init__.py
│       │   │   ├── credential_vault.py
│       │   │   ├── env_sanitizer.py
│       │   │   ├── log_redactor.py
│       │   │   ├── nt_guard.py
│       │   │   ├── prompt_injection_scanner.py
│       │   │   ├── ssrf_guard.py
│       │   │   ├── supply_chain_quarantine.py
│       │   │   ├── terminal_guard.py
│       │   │   ├── threat_detector.py
│       │   │   └── threat_scanner.py
│       │   ├── streaming/
│       │   │   ├── __init__.py
│       │   │   ├── sanitizer.py
│       │   │   ├── stream_scrubber.py
│       │   │   └── streaming_lease.py
│       │   ├── telemetry/
│       │   │   ├── reporting/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── docx_report_generator.py
│       │   │   │   ├── pdf_report_generator.py
│       │   │   │   ├── pptx_deck_generator.py
│       │   │   │   └── tearsheet_generator.py
│       │   │   ├── tracing/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── context.py
│       │   │   │   ├── exporters.py
│       │   │   │   ├── otlp_exporter.py
│       │   │   │   ├── spans.py
│       │   │   │   └── tracer.py
│       │   │   ├── __init__.py
│       │   │   ├── activity_logger.py
│       │   │   ├── delegation_live_log.py
│       │   │   ├── doctor.py
│       │   │   ├── metrics_exporter.py
│       │   │   ├── operator_feedback.py
│       │   │   ├── report_writer.py
│       │   │   ├── run_card.py
│       │   │   ├── sinks.py
│       │   │   ├── token_budgeter.py
│       │   │   └── trading_cycle_event_log.py
│       │   ├── validation/
│       │   │   ├── __init__.py
│       │   │   ├── data_temporal_validator.py
│       │   │   ├── data_validator.py
│       │   │   ├── indicator_sanitizer.py
│       │   │   └── tool_response_validator.py
│       │   ├── __init__.py
│       │   ├── container.py
│       │   ├── exceptions.py
│       │   ├── paths.py
│       │   └── platform.py
│       ├── domain/
│       │   ├── entities/
│       │   │   ├── __init__.py
│       │   │   ├── order.py
│       │   │   ├── order_status.py
│       │   │   ├── position.py
│       │   │   ├── snapshots.py
│       │   │   └── trade_trigger.py
│       │   ├── execution/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── bracket_optimizer.py
│       │   │   ├── broker_plugin.py
│       │   │   ├── order_creator.py
│       │   │   ├── order_emulator.py
│       │   │   ├── sizing_calculator.py
│       │   │   ├── state_machine.py
│       │   │   └── verification_engine.py
│       │   ├── harness/
│       │   │   ├── __init__.py
│       │   │   └── models.py
│       │   ├── indicators/
│       │   │   ├── alpha_zoo/
│       │   │   │   ├── catalog/
│       │   │   │   │   ├── factors.json
│       │   │   │   │   └── synthesized_strategies.json
│       │   │   │   ├── factors/
│       │   │   │   │   ├── academic/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── amihud_illiquidity.py
│       │   │   │   │   │   ├── betting_against_beta.py
│       │   │   │   │   │   ├── carhart_momentum.py
│       │   │   │   │   │   ├── conservative_minus_aggressive.py
│       │   │   │   │   │   ├── correlation_rewiring.py
│       │   │   │   │   │   ├── high_minus_low_value.py
│       │   │   │   │   │   ├── idiosyncratic_volatility.py
│       │   │   │   │   │   ├── market_excess_return.py
│       │   │   │   │   │   ├── proximity_52_week_high.py
│       │   │   │   │   │   ├── return_skewness.py
│       │   │   │   │   │   ├── robust_minus_weak_profitability.py
│       │   │   │   │   │   ├── short_term_reversal.py
│       │   │   │   │   │   └── small_minus_big_size.py
│       │   │   │   │   ├── fundamental/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── asset_growth.py
│       │   │   │   │   │   ├── earnings_yield.py
│       │   │   │   │   │   ├── gross_profitability.py
│       │   │   │   │   │   └── return_on_equity.py
│       │   │   │   │   ├── guotai_junan_191/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── gtja_alpha_001.py
│       │   │   │   │   │   ├── gtja_alpha_002.py
│       │   │   │   │   │   ├── gtja_alpha_003.py
│       │   │   │   │   │   ├── gtja_alpha_004.py
│       │   │   │   │   │   ├── gtja_alpha_005.py
│       │   │   │   │   │   ├── gtja_alpha_006.py
│       │   │   │   │   │   ├── gtja_alpha_007.py
│       │   │   │   │   │   ├── gtja_alpha_008.py
│       │   │   │   │   │   ├── gtja_alpha_009.py
│       │   │   │   │   │   ├── gtja_alpha_010.py
│       │   │   │   │   │   ├── gtja_alpha_011.py
│       │   │   │   │   │   ├── gtja_alpha_012.py
│       │   │   │   │   │   ├── gtja_alpha_013.py
│       │   │   │   │   │   ├── gtja_alpha_014.py
│       │   │   │   │   │   ├── gtja_alpha_015.py
│       │   │   │   │   │   ├── gtja_alpha_016.py
│       │   │   │   │   │   ├── gtja_alpha_017.py
│       │   │   │   │   │   ├── gtja_alpha_018.py
│       │   │   │   │   │   ├── gtja_alpha_019.py
│       │   │   │   │   │   ├── gtja_alpha_020.py
│       │   │   │   │   │   ├── gtja_alpha_021.py
│       │   │   │   │   │   ├── gtja_alpha_022.py
│       │   │   │   │   │   ├── gtja_alpha_023.py
│       │   │   │   │   │   ├── gtja_alpha_024.py
│       │   │   │   │   │   ├── gtja_alpha_025.py
│       │   │   │   │   │   ├── gtja_alpha_026.py
│       │   │   │   │   │   ├── gtja_alpha_027.py
│       │   │   │   │   │   ├── gtja_alpha_028.py
│       │   │   │   │   │   ├── gtja_alpha_029.py
│       │   │   │   │   │   ├── gtja_alpha_030.py
│       │   │   │   │   │   ├── gtja_alpha_031.py
│       │   │   │   │   │   ├── gtja_alpha_032.py
│       │   │   │   │   │   ├── gtja_alpha_033.py
│       │   │   │   │   │   ├── gtja_alpha_034.py
│       │   │   │   │   │   ├── gtja_alpha_035.py
│       │   │   │   │   │   ├── gtja_alpha_036.py
│       │   │   │   │   │   ├── gtja_alpha_037.py
│       │   │   │   │   │   ├── gtja_alpha_038.py
│       │   │   │   │   │   ├── gtja_alpha_039.py
│       │   │   │   │   │   ├── gtja_alpha_040.py
│       │   │   │   │   │   ├── gtja_alpha_041.py
│       │   │   │   │   │   ├── gtja_alpha_042.py
│       │   │   │   │   │   ├── gtja_alpha_043.py
│       │   │   │   │   │   ├── gtja_alpha_044.py
│       │   │   │   │   │   ├── gtja_alpha_045.py
│       │   │   │   │   │   ├── gtja_alpha_046.py
│       │   │   │   │   │   ├── gtja_alpha_047.py
│       │   │   │   │   │   ├── gtja_alpha_048.py
│       │   │   │   │   │   ├── gtja_alpha_049.py
│       │   │   │   │   │   ├── gtja_alpha_050.py
│       │   │   │   │   │   ├── gtja_alpha_051.py
│       │   │   │   │   │   ├── gtja_alpha_052.py
│       │   │   │   │   │   ├── gtja_alpha_053.py
│       │   │   │   │   │   ├── gtja_alpha_054.py
│       │   │   │   │   │   ├── gtja_alpha_055.py
│       │   │   │   │   │   ├── gtja_alpha_056.py
│       │   │   │   │   │   ├── gtja_alpha_057.py
│       │   │   │   │   │   ├── gtja_alpha_058.py
│       │   │   │   │   │   ├── gtja_alpha_059.py
│       │   │   │   │   │   ├── gtja_alpha_060.py
│       │   │   │   │   │   ├── gtja_alpha_061.py
│       │   │   │   │   │   ├── gtja_alpha_062.py
│       │   │   │   │   │   ├── gtja_alpha_063.py
│       │   │   │   │   │   ├── gtja_alpha_064.py
│       │   │   │   │   │   ├── gtja_alpha_065.py
│       │   │   │   │   │   ├── gtja_alpha_066.py
│       │   │   │   │   │   ├── gtja_alpha_067.py
│       │   │   │   │   │   ├── gtja_alpha_068.py
│       │   │   │   │   │   ├── gtja_alpha_069.py
│       │   │   │   │   │   ├── gtja_alpha_070.py
│       │   │   │   │   │   ├── gtja_alpha_071.py
│       │   │   │   │   │   ├── gtja_alpha_072.py
│       │   │   │   │   │   ├── gtja_alpha_073.py
│       │   │   │   │   │   ├── gtja_alpha_074.py
│       │   │   │   │   │   ├── gtja_alpha_075.py
│       │   │   │   │   │   ├── gtja_alpha_076.py
│       │   │   │   │   │   ├── gtja_alpha_077.py
│       │   │   │   │   │   ├── gtja_alpha_078.py
│       │   │   │   │   │   ├── gtja_alpha_079.py
│       │   │   │   │   │   ├── gtja_alpha_080.py
│       │   │   │   │   │   ├── gtja_alpha_081.py
│       │   │   │   │   │   ├── gtja_alpha_082.py
│       │   │   │   │   │   ├── gtja_alpha_083.py
│       │   │   │   │   │   ├── gtja_alpha_084.py
│       │   │   │   │   │   ├── gtja_alpha_085.py
│       │   │   │   │   │   ├── gtja_alpha_086.py
│       │   │   │   │   │   ├── gtja_alpha_087.py
│       │   │   │   │   │   ├── gtja_alpha_088.py
│       │   │   │   │   │   ├── gtja_alpha_089.py
│       │   │   │   │   │   ├── gtja_alpha_090.py
│       │   │   │   │   │   ├── gtja_alpha_091.py
│       │   │   │   │   │   ├── gtja_alpha_092.py
│       │   │   │   │   │   ├── gtja_alpha_093.py
│       │   │   │   │   │   ├── gtja_alpha_094.py
│       │   │   │   │   │   ├── gtja_alpha_095.py
│       │   │   │   │   │   ├── gtja_alpha_096.py
│       │   │   │   │   │   ├── gtja_alpha_097.py
│       │   │   │   │   │   ├── gtja_alpha_098.py
│       │   │   │   │   │   ├── gtja_alpha_099.py
│       │   │   │   │   │   ├── gtja_alpha_100.py
│       │   │   │   │   │   ├── gtja_alpha_101.py
│       │   │   │   │   │   ├── gtja_alpha_102.py
│       │   │   │   │   │   ├── gtja_alpha_103.py
│       │   │   │   │   │   ├── gtja_alpha_104.py
│       │   │   │   │   │   ├── gtja_alpha_105.py
│       │   │   │   │   │   ├── gtja_alpha_106.py
│       │   │   │   │   │   ├── gtja_alpha_107.py
│       │   │   │   │   │   ├── gtja_alpha_108.py
│       │   │   │   │   │   ├── gtja_alpha_109.py
│       │   │   │   │   │   ├── gtja_alpha_110.py
│       │   │   │   │   │   ├── gtja_alpha_111.py
│       │   │   │   │   │   ├── gtja_alpha_112.py
│       │   │   │   │   │   ├── gtja_alpha_113.py
│       │   │   │   │   │   ├── gtja_alpha_114.py
│       │   │   │   │   │   ├── gtja_alpha_115.py
│       │   │   │   │   │   ├── gtja_alpha_116.py
│       │   │   │   │   │   ├── gtja_alpha_117.py
│       │   │   │   │   │   ├── gtja_alpha_118.py
│       │   │   │   │   │   ├── gtja_alpha_119.py
│       │   │   │   │   │   ├── gtja_alpha_120.py
│       │   │   │   │   │   ├── gtja_alpha_121.py
│       │   │   │   │   │   ├── gtja_alpha_122.py
│       │   │   │   │   │   ├── gtja_alpha_123.py
│       │   │   │   │   │   ├── gtja_alpha_124.py
│       │   │   │   │   │   ├── gtja_alpha_125.py
│       │   │   │   │   │   ├── gtja_alpha_126.py
│       │   │   │   │   │   ├── gtja_alpha_127.py
│       │   │   │   │   │   ├── gtja_alpha_128.py
│       │   │   │   │   │   ├── gtja_alpha_129.py
│       │   │   │   │   │   ├── gtja_alpha_130.py
│       │   │   │   │   │   ├── gtja_alpha_131.py
│       │   │   │   │   │   ├── gtja_alpha_132.py
│       │   │   │   │   │   ├── gtja_alpha_133.py
│       │   │   │   │   │   ├── gtja_alpha_134.py
│       │   │   │   │   │   ├── gtja_alpha_135.py
│       │   │   │   │   │   ├── gtja_alpha_136.py
│       │   │   │   │   │   ├── gtja_alpha_137.py
│       │   │   │   │   │   ├── gtja_alpha_138.py
│       │   │   │   │   │   ├── gtja_alpha_139.py
│       │   │   │   │   │   ├── gtja_alpha_140.py
│       │   │   │   │   │   ├── gtja_alpha_141.py
│       │   │   │   │   │   ├── gtja_alpha_142.py
│       │   │   │   │   │   ├── gtja_alpha_143.py
│       │   │   │   │   │   ├── gtja_alpha_144.py
│       │   │   │   │   │   ├── gtja_alpha_145.py
│       │   │   │   │   │   ├── gtja_alpha_146.py
│       │   │   │   │   │   ├── gtja_alpha_147.py
│       │   │   │   │   │   ├── gtja_alpha_148.py
│       │   │   │   │   │   ├── gtja_alpha_149.py
│       │   │   │   │   │   ├── gtja_alpha_150.py
│       │   │   │   │   │   ├── gtja_alpha_151.py
│       │   │   │   │   │   ├── gtja_alpha_152.py
│       │   │   │   │   │   ├── gtja_alpha_153.py
│       │   │   │   │   │   ├── gtja_alpha_154.py
│       │   │   │   │   │   ├── gtja_alpha_155.py
│       │   │   │   │   │   ├── gtja_alpha_156.py
│       │   │   │   │   │   ├── gtja_alpha_157.py
│       │   │   │   │   │   ├── gtja_alpha_158.py
│       │   │   │   │   │   ├── gtja_alpha_159.py
│       │   │   │   │   │   ├── gtja_alpha_160.py
│       │   │   │   │   │   ├── gtja_alpha_161.py
│       │   │   │   │   │   ├── gtja_alpha_162.py
│       │   │   │   │   │   ├── gtja_alpha_163.py
│       │   │   │   │   │   ├── gtja_alpha_164.py
│       │   │   │   │   │   ├── gtja_alpha_165.py
│       │   │   │   │   │   ├── gtja_alpha_166.py
│       │   │   │   │   │   ├── gtja_alpha_167.py
│       │   │   │   │   │   ├── gtja_alpha_168.py
│       │   │   │   │   │   ├── gtja_alpha_169.py
│       │   │   │   │   │   ├── gtja_alpha_170.py
│       │   │   │   │   │   ├── gtja_alpha_171.py
│       │   │   │   │   │   ├── gtja_alpha_172.py
│       │   │   │   │   │   ├── gtja_alpha_173.py
│       │   │   │   │   │   ├── gtja_alpha_174.py
│       │   │   │   │   │   ├── gtja_alpha_175.py
│       │   │   │   │   │   ├── gtja_alpha_176.py
│       │   │   │   │   │   ├── gtja_alpha_177.py
│       │   │   │   │   │   ├── gtja_alpha_178.py
│       │   │   │   │   │   ├── gtja_alpha_179.py
│       │   │   │   │   │   ├── gtja_alpha_180.py
│       │   │   │   │   │   ├── gtja_alpha_181.py
│       │   │   │   │   │   ├── gtja_alpha_182.py
│       │   │   │   │   │   ├── gtja_alpha_183.py
│       │   │   │   │   │   ├── gtja_alpha_184.py
│       │   │   │   │   │   ├── gtja_alpha_185.py
│       │   │   │   │   │   ├── gtja_alpha_186.py
│       │   │   │   │   │   ├── gtja_alpha_187.py
│       │   │   │   │   │   ├── gtja_alpha_188.py
│       │   │   │   │   │   ├── gtja_alpha_189.py
│       │   │   │   │   │   ├── gtja_alpha_190.py
│       │   │   │   │   │   └── gtja_alpha_191.py
│       │   │   │   │   ├── microsoft_qlib_158/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── candlestick_body_magnitude.py
│       │   │   │   │   │   ├── candlestick_body_ratio.py
│       │   │   │   │   │   ├── candlestick_body_shift.py
│       │   │   │   │   │   ├── candlestick_body_shift_ratio.py
│       │   │   │   │   │   ├── candlestick_length.py
│       │   │   │   │   │   ├── candlestick_lower_shadow.py
│       │   │   │   │   │   ├── candlestick_lower_shadow_ratio.py
│       │   │   │   │   │   ├── candlestick_upper_shadow.py
│       │   │   │   │   │   ├── candlestick_upper_shadow_ratio.py
│       │   │   │   │   │   ├── close_open_dispersion_10.py
│       │   │   │   │   │   ├── close_open_dispersion_20.py
│       │   │   │   │   │   ├── close_open_dispersion_30.py
│       │   │   │   │   │   ├── close_open_dispersion_5.py
│       │   │   │   │   │   ├── close_open_dispersion_60.py
│       │   │   │   │   │   ├── count_down_ratio_10.py
│       │   │   │   │   │   ├── count_down_ratio_20.py
│       │   │   │   │   │   ├── count_down_ratio_30.py
│       │   │   │   │   │   ├── count_down_ratio_5.py
│       │   │   │   │   │   ├── count_down_ratio_60.py
│       │   │   │   │   │   ├── count_negative_returns_10.py
│       │   │   │   │   │   ├── count_negative_returns_20.py
│       │   │   │   │   │   ├── count_negative_returns_30.py
│       │   │   │   │   │   ├── count_negative_returns_5.py
│       │   │   │   │   │   ├── count_negative_returns_60.py
│       │   │   │   │   │   ├── count_positive_returns_10.py
│       │   │   │   │   │   ├── count_positive_returns_20.py
│       │   │   │   │   │   ├── count_positive_returns_30.py
│       │   │   │   │   │   ├── count_positive_returns_5.py
│       │   │   │   │   │   ├── count_positive_returns_60.py
│       │   │   │   │   │   ├── index_max_high_10.py
│       │   │   │   │   │   ├── index_max_high_20.py
│       │   │   │   │   │   ├── index_max_high_30.py
│       │   │   │   │   │   ├── index_max_high_5.py
│       │   │   │   │   │   ├── index_max_high_60.py
│       │   │   │   │   │   ├── index_max_min_difference_10.py
│       │   │   │   │   │   ├── index_max_min_difference_20.py
│       │   │   │   │   │   ├── index_max_min_difference_30.py
│       │   │   │   │   │   ├── index_max_min_difference_5.py
│       │   │   │   │   │   ├── index_max_min_difference_60.py
│       │   │   │   │   │   ├── index_min_low_10.py
│       │   │   │   │   │   ├── index_min_low_20.py
│       │   │   │   │   │   ├── index_min_low_30.py
│       │   │   │   │   │   ├── index_min_low_5.py
│       │   │   │   │   │   ├── index_min_low_60.py
│       │   │   │   │   │   ├── market_beta_10.py
│       │   │   │   │   │   ├── market_beta_20.py
│       │   │   │   │   │   ├── market_beta_30.py
│       │   │   │   │   │   ├── market_beta_5.py
│       │   │   │   │   │   ├── market_beta_60.py
│       │   │   │   │   │   ├── moving_average_10.py
│       │   │   │   │   │   ├── moving_average_20.py
│       │   │   │   │   │   ├── moving_average_30.py
│       │   │   │   │   │   ├── moving_average_5.py
│       │   │   │   │   │   ├── moving_average_60.py
│       │   │   │   │   │   ├── moving_average_x10.py
│       │   │   │   │   │   ├── moving_average_x20.py
│       │   │   │   │   │   ├── moving_average_x30.py
│       │   │   │   │   │   ├── moving_average_x5.py
│       │   │   │   │   │   ├── moving_average_x60.py
│       │   │   │   │   │   ├── percentile_price_rank_10.py
│       │   │   │   │   │   ├── percentile_price_rank_20.py
│       │   │   │   │   │   ├── percentile_price_rank_30.py
│       │   │   │   │   │   ├── percentile_price_rank_5.py
│       │   │   │   │   │   ├── percentile_price_rank_60.py
│       │   │   │   │   │   ├── price_volume_correlation_10.py
│       │   │   │   │   │   ├── price_volume_correlation_20.py
│       │   │   │   │   │   ├── price_volume_correlation_30.py
│       │   │   │   │   │   ├── price_volume_correlation_5.py
│       │   │   │   │   │   ├── price_volume_correlation_60.py
│       │   │   │   │   │   ├── quantile_down_ratio_10.py
│       │   │   │   │   │   ├── quantile_down_ratio_20.py
│       │   │   │   │   │   ├── quantile_down_ratio_30.py
│       │   │   │   │   │   ├── quantile_down_ratio_5.py
│       │   │   │   │   │   ├── quantile_down_ratio_60.py
│       │   │   │   │   │   ├── quantile_up_ratio_10.py
│       │   │   │   │   │   ├── quantile_up_ratio_20.py
│       │   │   │   │   │   ├── quantile_up_ratio_30.py
│       │   │   │   │   │   ├── quantile_up_ratio_5.py
│       │   │   │   │   │   ├── quantile_up_ratio_60.py
│       │   │   │   │   │   ├── rate_of_change_10.py
│       │   │   │   │   │   ├── rate_of_change_20.py
│       │   │   │   │   │   ├── rate_of_change_30.py
│       │   │   │   │   │   ├── rate_of_change_5.py
│       │   │   │   │   │   ├── rate_of_change_60.py
│       │   │   │   │   │   ├── raw_stochastic_value_10.py
│       │   │   │   │   │   ├── raw_stochastic_value_20.py
│       │   │   │   │   │   ├── raw_stochastic_value_30.py
│       │   │   │   │   │   ├── raw_stochastic_value_5.py
│       │   │   │   │   │   ├── raw_stochastic_value_60.py
│       │   │   │   │   │   ├── regression_r_squared_10.py
│       │   │   │   │   │   ├── regression_r_squared_20.py
│       │   │   │   │   │   ├── regression_r_squared_30.py
│       │   │   │   │   │   ├── regression_r_squared_5.py
│       │   │   │   │   │   ├── regression_r_squared_60.py
│       │   │   │   │   │   ├── regression_residual_10.py
│       │   │   │   │   │   ├── regression_residual_20.py
│       │   │   │   │   │   ├── regression_residual_30.py
│       │   │   │   │   │   ├── regression_residual_5.py
│       │   │   │   │   │   ├── regression_residual_60.py
│       │   │   │   │   │   ├── rolling_min_10.py
│       │   │   │   │   │   ├── rolling_min_20.py
│       │   │   │   │   │   ├── rolling_min_30.py
│       │   │   │   │   │   ├── rolling_min_5.py
│       │   │   │   │   │   ├── rolling_min_60.py
│       │   │   │   │   │   ├── rolling_volatility_10.py
│       │   │   │   │   │   ├── rolling_volatility_20.py
│       │   │   │   │   │   ├── rolling_volatility_30.py
│       │   │   │   │   │   ├── rolling_volatility_5.py
│       │   │   │   │   │   ├── rolling_volatility_60.py
│       │   │   │   │   │   ├── sum_negative_returns_10.py
│       │   │   │   │   │   ├── sum_negative_returns_20.py
│       │   │   │   │   │   ├── sum_negative_returns_30.py
│       │   │   │   │   │   ├── sum_negative_returns_5.py
│       │   │   │   │   │   ├── sum_negative_returns_60.py
│       │   │   │   │   │   ├── sum_positive_returns_10.py
│       │   │   │   │   │   ├── sum_positive_returns_20.py
│       │   │   │   │   │   ├── sum_positive_returns_30.py
│       │   │   │   │   │   ├── sum_positive_returns_5.py
│       │   │   │   │   │   ├── sum_positive_returns_60.py
│       │   │   │   │   │   ├── sum_price_drops_10.py
│       │   │   │   │   │   ├── sum_price_drops_20.py
│       │   │   │   │   │   ├── sum_price_drops_30.py
│       │   │   │   │   │   ├── sum_price_drops_5.py
│       │   │   │   │   │   ├── sum_price_drops_60.py
│       │   │   │   │   │   ├── volume_moving_average_10.py
│       │   │   │   │   │   ├── volume_moving_average_20.py
│       │   │   │   │   │   ├── volume_moving_average_30.py
│       │   │   │   │   │   ├── volume_moving_average_5.py
│       │   │   │   │   │   ├── volume_moving_average_60.py
│       │   │   │   │   │   ├── volume_sum_drops_10.py
│       │   │   │   │   │   ├── volume_sum_drops_20.py
│       │   │   │   │   │   ├── volume_sum_drops_30.py
│       │   │   │   │   │   ├── volume_sum_drops_5.py
│       │   │   │   │   │   ├── volume_sum_drops_60.py
│       │   │   │   │   │   ├── volume_sum_negative_10.py
│       │   │   │   │   │   ├── volume_sum_negative_20.py
│       │   │   │   │   │   ├── volume_sum_negative_30.py
│       │   │   │   │   │   ├── volume_sum_negative_5.py
│       │   │   │   │   │   ├── volume_sum_negative_60.py
│       │   │   │   │   │   ├── volume_sum_positive_10.py
│       │   │   │   │   │   ├── volume_sum_positive_20.py
│       │   │   │   │   │   ├── volume_sum_positive_30.py
│       │   │   │   │   │   ├── volume_sum_positive_5.py
│       │   │   │   │   │   ├── volume_sum_positive_60.py
│       │   │   │   │   │   ├── volume_volatility_10.py
│       │   │   │   │   │   ├── volume_volatility_20.py
│       │   │   │   │   │   ├── volume_volatility_30.py
│       │   │   │   │   │   ├── volume_volatility_5.py
│       │   │   │   │   │   ├── volume_volatility_60.py
│       │   │   │   │   │   ├── volume_weighted_volatility_10.py
│       │   │   │   │   │   ├── volume_weighted_volatility_20.py
│       │   │   │   │   │   ├── volume_weighted_volatility_30.py
│       │   │   │   │   │   ├── volume_weighted_volatility_5.py
│       │   │   │   │   │   └── volume_weighted_volatility_60.py
│       │   │   │   │   ├── microstructure/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── range_dispersion.py
│       │   │   │   │   │   ├── shadow_asymmetry.py
│       │   │   │   │   │   ├── volume_price_rank_divergence.py
│       │   │   │   │   │   └── volume_weighted_momentum.py
│       │   │   │   │   ├── worldquant_101/
│       │   │   │   │   │   ├── __init__.py
│       │   │   │   │   │   ├── wq_alpha_001.py
│       │   │   │   │   │   ├── wq_alpha_002.py
│       │   │   │   │   │   ├── wq_alpha_003.py
│       │   │   │   │   │   ├── wq_alpha_004.py
│       │   │   │   │   │   ├── wq_alpha_005.py
│       │   │   │   │   │   ├── wq_alpha_006.py
│       │   │   │   │   │   ├── wq_alpha_007.py
│       │   │   │   │   │   ├── wq_alpha_008.py
│       │   │   │   │   │   ├── wq_alpha_009.py
│       │   │   │   │   │   ├── wq_alpha_010.py
│       │   │   │   │   │   ├── wq_alpha_011.py
│       │   │   │   │   │   ├── wq_alpha_012.py
│       │   │   │   │   │   ├── wq_alpha_013.py
│       │   │   │   │   │   ├── wq_alpha_014.py
│       │   │   │   │   │   ├── wq_alpha_015.py
│       │   │   │   │   │   ├── wq_alpha_016.py
│       │   │   │   │   │   ├── wq_alpha_017.py
│       │   │   │   │   │   ├── wq_alpha_018.py
│       │   │   │   │   │   ├── wq_alpha_019.py
│       │   │   │   │   │   ├── wq_alpha_020.py
│       │   │   │   │   │   ├── wq_alpha_021.py
│       │   │   │   │   │   ├── wq_alpha_022.py
│       │   │   │   │   │   ├── wq_alpha_023.py
│       │   │   │   │   │   ├── wq_alpha_024.py
│       │   │   │   │   │   ├── wq_alpha_025.py
│       │   │   │   │   │   ├── wq_alpha_026.py
│       │   │   │   │   │   ├── wq_alpha_027.py
│       │   │   │   │   │   ├── wq_alpha_028.py
│       │   │   │   │   │   ├── wq_alpha_029.py
│       │   │   │   │   │   ├── wq_alpha_030.py
│       │   │   │   │   │   ├── wq_alpha_031.py
│       │   │   │   │   │   ├── wq_alpha_032.py
│       │   │   │   │   │   ├── wq_alpha_033.py
│       │   │   │   │   │   ├── wq_alpha_034.py
│       │   │   │   │   │   ├── wq_alpha_035.py
│       │   │   │   │   │   ├── wq_alpha_036.py
│       │   │   │   │   │   ├── wq_alpha_037.py
│       │   │   │   │   │   ├── wq_alpha_038.py
│       │   │   │   │   │   ├── wq_alpha_039.py
│       │   │   │   │   │   ├── wq_alpha_040.py
│       │   │   │   │   │   ├── wq_alpha_041.py
│       │   │   │   │   │   ├── wq_alpha_042.py
│       │   │   │   │   │   ├── wq_alpha_043.py
│       │   │   │   │   │   ├── wq_alpha_044.py
│       │   │   │   │   │   ├── wq_alpha_045.py
│       │   │   │   │   │   ├── wq_alpha_046.py
│       │   │   │   │   │   ├── wq_alpha_047.py
│       │   │   │   │   │   ├── wq_alpha_048.py
│       │   │   │   │   │   ├── wq_alpha_049.py
│       │   │   │   │   │   ├── wq_alpha_050.py
│       │   │   │   │   │   ├── wq_alpha_051.py
│       │   │   │   │   │   ├── wq_alpha_052.py
│       │   │   │   │   │   ├── wq_alpha_053.py
│       │   │   │   │   │   ├── wq_alpha_054.py
│       │   │   │   │   │   ├── wq_alpha_055.py
│       │   │   │   │   │   ├── wq_alpha_056.py
│       │   │   │   │   │   ├── wq_alpha_057.py
│       │   │   │   │   │   ├── wq_alpha_058.py
│       │   │   │   │   │   ├── wq_alpha_059.py
│       │   │   │   │   │   ├── wq_alpha_060.py
│       │   │   │   │   │   ├── wq_alpha_061.py
│       │   │   │   │   │   ├── wq_alpha_062.py
│       │   │   │   │   │   ├── wq_alpha_063.py
│       │   │   │   │   │   ├── wq_alpha_064.py
│       │   │   │   │   │   ├── wq_alpha_065.py
│       │   │   │   │   │   ├── wq_alpha_066.py
│       │   │   │   │   │   ├── wq_alpha_067.py
│       │   │   │   │   │   ├── wq_alpha_068.py
│       │   │   │   │   │   ├── wq_alpha_069.py
│       │   │   │   │   │   ├── wq_alpha_070.py
│       │   │   │   │   │   ├── wq_alpha_071.py
│       │   │   │   │   │   ├── wq_alpha_072.py
│       │   │   │   │   │   ├── wq_alpha_073.py
│       │   │   │   │   │   ├── wq_alpha_074.py
│       │   │   │   │   │   ├── wq_alpha_075.py
│       │   │   │   │   │   ├── wq_alpha_076.py
│       │   │   │   │   │   ├── wq_alpha_077.py
│       │   │   │   │   │   ├── wq_alpha_078.py
│       │   │   │   │   │   ├── wq_alpha_079.py
│       │   │   │   │   │   ├── wq_alpha_080.py
│       │   │   │   │   │   ├── wq_alpha_081.py
│       │   │   │   │   │   ├── wq_alpha_082.py
│       │   │   │   │   │   ├── wq_alpha_083.py
│       │   │   │   │   │   ├── wq_alpha_084.py
│       │   │   │   │   │   ├── wq_alpha_085.py
│       │   │   │   │   │   ├── wq_alpha_086.py
│       │   │   │   │   │   ├── wq_alpha_087.py
│       │   │   │   │   │   ├── wq_alpha_088.py
│       │   │   │   │   │   ├── wq_alpha_089.py
│       │   │   │   │   │   ├── wq_alpha_090.py
│       │   │   │   │   │   ├── wq_alpha_091.py
│       │   │   │   │   │   ├── wq_alpha_092.py
│       │   │   │   │   │   ├── wq_alpha_093.py
│       │   │   │   │   │   ├── wq_alpha_094.py
│       │   │   │   │   │   ├── wq_alpha_095.py
│       │   │   │   │   │   ├── wq_alpha_096.py
│       │   │   │   │   │   ├── wq_alpha_097.py
│       │   │   │   │   │   ├── wq_alpha_098.py
│       │   │   │   │   │   ├── wq_alpha_099.py
│       │   │   │   │   │   ├── wq_alpha_100.py
│       │   │   │   │   │   └── wq_alpha_101.py
│       │   │   │   │   └── __init__.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── academic_factors.py
│       │   │   │   ├── alpha101.py
│       │   │   │   ├── fundamental_factors.py
│       │   │   │   ├── meta.py
│       │   │   │   ├── microstructure_factors.py
│       │   │   │   ├── qlib158.py
│       │   │   │   ├── registry.py
│       │   │   │   └── vector_factor_engine.py
│       │   │   ├── pattern_similarity/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── context_scorer.py
│       │   │   │   ├── context_verifier.py
│       │   │   │   ├── engine.py
│       │   │   │   ├── feature_extractor.py
│       │   │   │   ├── models.py
│       │   │   │   ├── normalizer.py
│       │   │   │   ├── outcome_analyzer.py
│       │   │   │   └── scanner.py
│       │   │   ├── __init__.py
│       │   │   ├── candlestick_patterns.py
│       │   │   ├── chart_patterns.py
│       │   │   ├── factor_primitives.py
│       │   │   ├── micro_alpha_zoo.py
│       │   │   ├── microstructure.py
│       │   │   ├── order_flow.py
│       │   │   ├── regime_detector.py
│       │   │   ├── smc_advanced.py
│       │   │   ├── structure.py
│       │   │   └── technical.py
│       │   ├── macro/
│       │   │   ├── __init__.py
│       │   │   └── regime_classifier.py
│       │   ├── market/
│       │   │   ├── __init__.py
│       │   │   ├── bias_utils.py
│       │   │   ├── currency_utils.py
│       │   │   ├── direction.py
│       │   │   ├── dynamic_correlation.py
│       │   │   ├── instrument_identity.py
│       │   │   ├── news_impact_keywords.py
│       │   │   ├── playbook_screener.py
│       │   │   ├── session_info.py
│       │   │   ├── swap_estimator.py
│       │   │   └── usd_strength_proxy.py
│       │   ├── ports/
│       │   │   ├── __init__.py
│       │   │   ├── event_publisher.py
│       │   │   ├── execution.py
│       │   │   ├── llm.py
│       │   │   ├── market_data.py
│       │   │   ├── notifier.py
│       │   │   ├── repository.py
│       │   │   └── unit_of_work.py
│       │   ├── risk/
│       │   │   ├── evaluators/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py
│       │   │   │   ├── execution_checks.py
│       │   │   │   ├── intelligence_checks.py
│       │   │   │   ├── market_checks.py
│       │   │   │   └── portfolio_checks.py
│       │   │   ├── instruments/
│       │   │   │   ├── __init__.py
│       │   │   │   └── instruments.py
│       │   │   ├── invariants/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── position_count_invariant.py
│       │   │   │   ├── registry.py
│       │   │   │   ├── risk_gate_invariant.py
│       │   │   │   └── state_immutability_invariant.py
│       │   │   ├── __init__.py
│       │   │   ├── approval_hub.py
│       │   │   ├── approval_transport.py
│       │   │   ├── correlation_matrix.py
│       │   │   ├── crypto_audit_ledger.py
│       │   │   ├── execution_simulator.py
│       │   │   ├── pending_action.py
│       │   │   ├── portfolio_correlation_gate.py
│       │   │   ├── portfolio_optimizer.py
│       │   │   ├── ports.py
│       │   │   ├── position_math.py
│       │   │   ├── position_sizing.py
│       │   │   ├── risk_gate.py
│       │   │   ├── risk_rule_plugin.py
│       │   │   └── trade_proposal.py
│       │   ├── __init__.py
│       │   └── models_resolver.py
│       ├── infrastructure/
│       │   ├── api/
│       │   │   ├── __init__.py
│       │   │   ├── claude_rate_limiter.py
│       │   │   ├── credential_pool.py
│       │   │   ├── credit_balance_tracker.py
│       │   │   ├── gemini_rate_limiter.py
│       │   │   ├── groq_rate_limiter.py
│       │   │   ├── http_retry.py
│       │   │   ├── openrouter_rate_limiter.py
│       │   │   └── streaming.py
│       │   ├── auth/
│       │   │   ├── __init__.py
│       │   │   ├── antigravity_bridge.py
│       │   │   ├── claude_oauth.py
│       │   │   ├── codex_device_flow.py
│       │   │   └── oauth_store.py
│       │   ├── brokers/
│       │   │   ├── ea_bridge/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── AIAgent_EA.mq5
│       │   │   │   ├── heartbeat_writer.py
│       │   │   │   └── watchdog.py
│       │   │   ├── mt5/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py
│       │   │   │   ├── broker_time.py
│       │   │   │   ├── client.py
│       │   │   │   ├── connection.py
│       │   │   │   ├── constants.py
│       │   │   │   ├── execution.py
│       │   │   │   ├── market_data.py
│       │   │   │   ├── order_ops.py
│       │   │   │   └── primitives.py
│       │   │   ├── __init__.py
│       │   │   ├── approval_transport.py
│       │   │   ├── audit_logger.py
│       │   │   ├── broker_adapter.py
│       │   │   ├── ibkr_adapter.py
│       │   │   ├── idempotency_guard.py
│       │   │   ├── mt5_client.py
│       │   │   ├── mt5_compat.py
│       │   │   ├── paper_tracker.py
│       │   │   └── rate_throttler.py
│       │   ├── credentials/
│       │   │   ├── __init__.py
│       │   │   ├── credential_pool.py
│       │   │   └── error_taxonomy.py
│       │   ├── data_ingestion/
│       │   │   ├── data/
│       │   │   │   └── sessions/
│       │   │   │       └── twitter_quarantined.json
│       │   │   ├── scrapers/
│       │   │   │   ├── calendar/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── calendar_finnhub.py
│       │   │   │   │   ├── calendar_forexfactory.py
│       │   │   │   │   └── calendar_investing.py
│       │   │   │   ├── macro/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── bank_indonesia.py
│       │   │   │   │   ├── central_bank_doc_scraper.py
│       │   │   │   │   ├── cme_fedwatch.py
│       │   │   │   │   ├── generic_gov_stats_fetcher.py
│       │   │   │   │   └── macro_trigger_router.py
│       │   │   │   ├── news/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── kitco_news.py
│       │   │   │   │   ├── rss_base.py
│       │   │   │   │   ├── rss_bloomberg.py
│       │   │   │   │   ├── rss_boe.py
│       │   │   │   │   ├── rss_boj.py
│       │   │   │   │   ├── rss_cnbc.py
│       │   │   │   │   ├── rss_coindesk.py
│       │   │   │   │   ├── rss_dow_jones.py
│       │   │   │   │   ├── rss_ecb.py
│       │   │   │   │   ├── rss_fed.py
│       │   │   │   │   ├── rss_forexlive.py
│       │   │   │   │   ├── rss_ft.py
│       │   │   │   │   ├── rss_fxstreet.py
│       │   │   │   │   ├── rss_investing.py
│       │   │   │   │   ├── rss_marketwatch.py
│       │   │   │   │   ├── rss_rba.py
│       │   │   │   │   ├── rss_reuters.py
│       │   │   │   │   ├── rss_wsj.py
│       │   │   │   │   └── tradingview_news.py
│       │   │   │   ├── sentiment/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── binance_sentiment.py
│       │   │   │   │   ├── fxssi_sentiment.py
│       │   │   │   │   └── myfxbook_sentiment.py
│       │   │   │   ├── social/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   └── twitter_watch.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base_scraper.py
│       │   │   │   └── models.py
│       │   │   ├── sources/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── academic_search.py
│       │   │   │   ├── bond_yields_fetcher.py
│       │   │   │   ├── bond_yields_yfinance.py
│       │   │   │   ├── bps_stats.py
│       │   │   │   ├── brent_yfinance.py
│       │   │   │   ├── central_bank_watch.py
│       │   │   │   ├── cftc_cot.py
│       │   │   │   ├── circuit_breaker.py
│       │   │   │   ├── coinglass_funding.py
│       │   │   │   ├── crypto_orderbook_depth.py
│       │   │   │   ├── dxy_yfinance.py
│       │   │   │   ├── eia_oil_inventory.py
│       │   │   │   ├── fear_greed.py
│       │   │   │   ├── fed_liquidity_h41_fetcher.py
│       │   │   │   ├── fred_treasury_yield.py
│       │   │   │   ├── gold_physical_radar.py
│       │   │   │   ├── leading_survey_fetcher.py
│       │   │   │   ├── market_stress_auction_fetcher.py
│       │   │   │   ├── prediction_market.py
│       │   │   │   ├── sovereign_yield_spreads.py
│       │   │   │   ├── validators.py
│       │   │   │   ├── vix_yfinance.py
│       │   │   │   ├── web_reader.py
│       │   │   │   └── web_search.py
│       │   │   └── __init__.py
│       │   ├── database/
│       │   │   ├── domain_models/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── analysis.py
│       │   │   │   ├── base.py
│       │   │   │   ├── market.py
│       │   │   │   ├── memory.py
│       │   │   │   ├── news.py
│       │   │   │   ├── system.py
│       │   │   │   └── trading.py
│       │   │   ├── migrations/
│       │   │   │   ├── versions/
│       │   │   │   │   ├── 0001_initial_schema.py
│       │   │   │   │   ├── 0002_user_prefs_and_journal.py
│       │   │   │   │   ├── 0003_add_benchmark_tables_and_cache_cost_columns.py
│       │   │   │   │   ├── 0004_fk_cascade_integrity.py
│       │   │   │   │   ├── 0005_sync_missing_indexes_and_constraints.py
│       │   │   │   │   ├── 0006_consolidate_and_numeric.py
│       │   │   │   │   ├── 0007_sync_queue_indexes_and_nullability.py
│       │   │   │   │   ├── 0008_create_debate_transcripts.py
│       │   │   │   │   ├── 0009_price_ohlcv_canonical_ts.py
│       │   │   │   │   ├── 0010_paper_trade_initial_risk.py
│       │   │   │   │   ├── 0011_sync_indexes_constraints.py
│       │   │   │   │   ├── 0012_sync_indexes_and_constraints.py
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   └── c83c5e451412_sync_schema_indexes_types_and_.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── env.py
│       │   │   │   ├── README
│       │   │   │   └── script.py.mako
│       │   │   ├── repositories/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── activity_log_repository.py
│       │   │   │   ├── asset_analysis_repository.py
│       │   │   │   ├── market_data_repository.py
│       │   │   │   ├── paper_trade_repository.py
│       │   │   │   ├── position_repository.py
│       │   │   │   ├── risk_repository.py
│       │   │   │   ├── system_config_repository.py
│       │   │   │   ├── trade_proposal_repository.py
│       │   │   │   └── unit_of_work.py
│       │   │   ├── __init__.py
│       │   │   ├── adapters.py
│       │   │   ├── backup.py
│       │   │   ├── cleanup.py
│       │   │   ├── db.py
│       │   │   ├── event_store.py
│       │   │   ├── fts5_cjk.py
│       │   │   ├── models.py
│       │   │   ├── repair_ledger.py
│       │   │   ├── safe_ops.py
│       │   │   ├── session_db_wal.py
│       │   │   └── session_lifecycle.py
│       │   ├── graph/
│       │   │   ├── checkpointers/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── dual_checkpointer.py
│       │   │   │   └── sqlite_checkpointer.py
│       │   │   └── __init__.py
│       │   ├── llm/
│       │   │   ├── rate_limiting/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── claude_rate_limiter.py
│       │   │   │   ├── credential_pool.py
│       │   │   │   ├── credit_balance_tracker.py
│       │   │   │   ├── gemini_rate_limiter.py
│       │   │   │   ├── groq_rate_limiter.py
│       │   │   │   ├── http_retry.py
│       │   │   │   ├── openrouter_rate_limiter.py
│       │   │   │   └── streaming.py
│       │   │   ├── __init__.py
│       │   │   ├── adaptive_thinking.py
│       │   │   ├── cache_breakpoint_manager.py
│       │   │   ├── cache_miss_detector.py
│       │   │   ├── cache_warmer.py
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
│       │   │   ├── instruction_budgeter.py
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
│       │   ├── mcp/
│       │   │   ├── servers/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── excel_server.py
│       │   │   │   ├── fetch_server.py
│       │   │   │   ├── filesystem_server.py
│       │   │   │   ├── google_sheets_server.py
│       │   │   │   └── sqlite_server.py
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── dispatcher.py
│       │   │   ├── event_bridge.py
│       │   │   ├── mcp_death_supervisor.py
│       │   │   ├── mcp_schema_cache.py
│       │   │   ├── mcp_serve.py
│       │   │   ├── oauth_handler.py
│       │   │   ├── protocol.py
│       │   │   └── server.py
│       │   ├── ml/
│       │   │   ├── __init__.py
│       │   │   └── timesfm_engine.py
│       │   ├── notifications/
│       │   │   ├── __init__.py
│       │   │   ├── discord_notifier.py
│       │   │   └── telegram_notifier.py
│       │   ├── providers/
│       │   │   ├── __init__.py
│       │   │   ├── anthropic_provider.py
│       │   │   ├── backend_identity.py
│       │   │   ├── base_provider.py
│       │   │   ├── capabilities.py
│       │   │   ├── codex_provider.py
│       │   │   ├── deepseek_provider.py
│       │   │   ├── error_classifier.py
│       │   │   ├── gemini_provider.py
│       │   │   ├── groq_provider.py
│       │   │   ├── llm_factory.py
│       │   │   ├── nine_router_provider.py
│       │   │   ├── ollama_provider.py
│       │   │   ├── openai_provider.py
│       │   │   ├── opencode_provider.py
│       │   │   ├── openrouter_provider.py
│       │   │   ├── pricing_catalog.py
│       │   │   ├── provider_failover_classifier.py
│       │   │   ├── provider_profile.py
│       │   │   ├── provider_registry.py
│       │   │   ├── runtime_model_registry.py
│       │   │   ├── schema_normalizer.py
│       │   │   ├── streaming_think_scrubber.py
│       │   │   ├── structured_fallback.py
│       │   │   ├── trajectory_compressor.py
│       │   │   ├── typesafe_provider.py
│       │   │   └── zai_provider.py
│       │   ├── sandboxes/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── docker_backend.py
│       │   │   ├── local_backend.py
│       │   │   ├── pty_bridge.py
│       │   │   ├── pty_query_responder.py
│       │   │   └── worktree_manager.py
│       │   ├── storage/
│       │   │   ├── __init__.py
│       │   │   ├── journal_helper.py
│       │   │   ├── playbook_catalog_repository.py
│       │   │   └── spill_store.py
│       │   └── __init__.py
│       ├── interfaces/
│       │   ├── cli/
│       │   │   ├── chat/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── commands.py
│       │   │   │   ├── completer.py
│       │   │   │   ├── prompt.py
│       │   │   │   ├── renderer.py
│       │   │   │   ├── session.py
│       │   │   │   └── theme.py
│       │   │   ├── commands/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── analysis_ctrl.py
│       │   │   │   ├── auth_ctrl.py
│       │   │   │   ├── benchmark_ctrl.py
│       │   │   │   ├── config_ctrl.py
│       │   │   │   ├── daemon_ctrl.py
│       │   │   │   ├── inspect_ctrl.py
│       │   │   │   └── parser.py
│       │   │   ├── overlays/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── approval_modal.py
│       │   │   │   └── plugin_install_modal.py
│       │   │   ├── subcommands/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py
│       │   │   │   ├── daemon.py
│       │   │   │   ├── desks.py
│       │   │   │   ├── mcp.py
│       │   │   │   ├── runcard.py
│       │   │   │   ├── simulation.py
│       │   │   │   ├── trading.py
│       │   │   │   └── upgrade.py
│       │   │   ├── tui_app/
│       │   │   │   ├── mixins/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── actions.py
│       │   │   │   │   ├── data_sync.py
│       │   │   │   │   ├── navigation.py
│       │   │   │   │   ├── plugins_benchmark.py
│       │   │   │   │   └── websocket.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py
│       │   │   │   ├── constants.py
│       │   │   │   ├── dashboard.py
│       │   │   │   ├── entrypoints.py
│       │   │   │   └── widgets.py
│       │   │   ├── __init__.py
│       │   │   ├── analysis_tree.py
│       │   │   ├── busy_input.py
│       │   │   ├── context.py
│       │   │   ├── doctor.py
│       │   │   ├── harness_audit.py
│       │   │   ├── main.py
│       │   │   ├── onboarding_trader.py
│       │   │   ├── platform_compat.py
│       │   │   ├── plugins.py
│       │   │   ├── profile_manager.py
│       │   │   ├── setup_wizard.py
│       │   │   ├── sparklines.py
│       │   │   ├── theme.py
│       │   │   ├── tui.py
│       │   │   ├── tui_chat.py
│       │   │   └── width_budget.py
│       │   ├── dashboard/
│       │   │   ├── routes/
│       │   │   │   ├── trading_endpoints/
│       │   │   │   │   ├── __init__.py
│       │   │   │   │   ├── actions.py
│       │   │   │   │   ├── analysis.py
│       │   │   │   │   ├── market_data.py
│       │   │   │   │   ├── orders.py
│       │   │   │   │   ├── overview.py
│       │   │   │   │   ├── positions.py
│       │   │   │   │   └── risk.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── backtest.py
│       │   │   │   ├── benchmark.py
│       │   │   │   ├── common.py
│       │   │   │   ├── config.py
│       │   │   │   ├── intelligence.py
│       │   │   │   ├── mcp_server.py
│       │   │   │   ├── memory.py
│       │   │   │   ├── observability.py
│       │   │   │   ├── plugins.py
│       │   │   │   ├── system.py
│       │   │   │   ├── tokens.py
│       │   │   │   ├── trace_search.py
│       │   │   │   ├── trading.py
│       │   │   │   └── websocket.py
│       │   │   ├── __init__.py
│       │   │   ├── api.py
│       │   │   ├── log_streamer.py
│       │   │   ├── pty_bridge.py
│       │   │   ├── rbac.py
│       │   │   ├── schemas.py
│       │   │   └── ws_ticket.py
│       │   ├── gateway/
│       │   │   ├── platforms/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── discord_adapter.py
│       │   │   │   ├── slack_adapter.py
│       │   │   │   ├── telegram_adapter.py
│       │   │   │   └── webhook_adapter.py
│       │   │   ├── __init__.py
│       │   │   ├── acp_server.py
│       │   │   ├── api_server.py
│       │   │   ├── bot_loop_guard.py
│       │   │   ├── channel_router.py
│       │   │   ├── delivery_ledger.py
│       │   │   ├── omnichannel_router.py
│       │   │   ├── omnichannel_streamer.py
│       │   │   ├── pairing.py
│       │   │   ├── platform_base.py
│       │   │   ├── stream_consumer.py
│       │   │   ├── turn_lease.py
│       │   │   └── webhook_ingress.py
│       │   ├── telegram/
│       │   │   ├── formatters/
│       │   │   │   ├── __init__.py
│       │   │   │   └── text_builders.py
│       │   │   ├── handlers/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── admin_commands.py
│       │   │   │   ├── callback_handler.py
│       │   │   │   ├── market_commands.py
│       │   │   │   ├── media_handlers.py
│       │   │   │   ├── system_commands.py
│       │   │   │   └── trading_commands.py
│       │   │   ├── routers/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── admin_router.py
│       │   │   │   ├── market_router.py
│       │   │   │   ├── quant_router.py
│       │   │   │   ├── risk_router.py
│       │   │   │   └── trading_router.py
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── bot.py
│       │   │   ├── chat_agent.py
│       │   │   ├── chat_compaction.py
│       │   │   ├── chat_tool_router.py
│       │   │   ├── command_router.py
│       │   │   ├── fuzzy_router.py
│       │   │   ├── message_formatter.py
│       │   │   ├── sanitizer.py
│       │   │   ├── topic_manager.py
│       │   │   ├── voice_handler.py
│       │   │   └── voice_safety_gate.py
│       │   └── __init__.py
│       └── __init__.py
│   ├── public/
│   │   ├── favicon.svg
│   │   ├── icons.svg
│   │   └── mobius-master.svg
│   ├── src/
│   │   ├── assets/
│   │   │   ├── react.svg
│   │   │   └── vite.svg
│   │   ├── components/
│   │   │   ├── charts/
│   │   │   │   ├── CandlestickChart.tsx
│   │   │   │   ├── DecisionDistribution.tsx
│   │   │   │   ├── EquityChart.tsx
│   │   │   │   ├── FactorHeatmap.tsx
│   │   │   │   ├── VixSparkline.tsx
│   │   │   │   └── WinRateGauge.tsx
│   │   │   ├── layout/
│   │   │   │   ├── BreadcrumbBar.tsx
│   │   │   │   ├── GlobalStatusBar.tsx
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── MobileNavDrawer.tsx
│   │   │   │   ├── navigation.ts
│   │   │   │   └── Sidebar.tsx
│   │   │   ├── panels/
│   │   │   │   ├── config/
│   │   │   │   │   ├── ConfigDiffModal.tsx
│   │   │   │   │   └── ConfigSection.tsx
│   │   │   │   ├── graph/
│   │   │   │   │   ├── GraphControls.tsx
│   │   │   │   │   ├── GraphEdge.tsx
│   │   │   │   │   ├── GraphInspector.tsx
│   │   │   │   │   ├── GraphNode.tsx
│   │   │   │   │   └── graphUtils.ts
│   │   │   │   ├── tokens/
│   │   │   │   │   ├── TokenCharts.tsx
│   │   │   │   │   └── TokenRoleTable.tsx
│   │   │   │   ├── ActivityFeed.tsx
│   │   │   │   ├── AgentChatPanel.tsx
│   │   │   │   ├── AnalysisGrid.tsx
│   │   │   │   ├── BacktestPanel.tsx
│   │   │   │   ├── BenchmarkPanel.tsx
│   │   │   │   ├── CockpitBar.tsx
│   │   │   │   ├── ConfigEditorPanel.tsx
│   │   │   │   ├── DebateOutcomesPanel.tsx
│   │   │   │   ├── DecisionDossierModal.tsx
│   │   │   │   ├── EdgeMetricsPanel.tsx
│   │   │   │   ├── GraphVisualizerPanel.tsx
│   │   │   │   ├── MarketDataPanel.tsx
│   │   │   │   ├── MemoryBrowserPanel.tsx
│   │   │   │   ├── ObservabilityPanel.tsx
│   │   │   │   ├── PerformancePanel.tsx
│   │   │   │   ├── PluginManagerPanel.tsx
│   │   │   │   ├── PositionsTable.tsx
│   │   │   │   ├── RiskPanel.tsx
│   │   │   │   ├── SessionBrowserPanel.tsx
│   │   │   │   ├── SignalsTriggersPanel.tsx
│   │   │   │   ├── SkillManagerPanel.tsx
│   │   │   │   ├── SystemPanel.tsx
│   │   │   │   ├── TerminalPanel.tsx
│   │   │   │   └── TokenAuditPanel.tsx
│   │   │   └── ui/
│   │   │       ├── AnalogDial.tsx
│   │   │       ├── ApprovalModal.tsx
│   │   │       ├── AuthModal.tsx
│   │   │       ├── Badge.tsx
│   │   │       ├── BootSequence.tsx
│   │   │       ├── Card.tsx
│   │   │       ├── CommandPalette.tsx
│   │   │       ├── ConfirmModal.tsx
│   │   │       ├── EmptyState.tsx
│   │   │       ├── ErrorBoundary.tsx
│   │   │       ├── Icons.tsx
│   │   │       ├── KeyboardShortcutsPanel.tsx
│   │   │       ├── LedgerTable.tsx
│   │   │       ├── ManualOrderDrawer.tsx
│   │   │       ├── MarkdownRenderer.tsx
│   │   │       ├── MetricCard.tsx
│   │   │       ├── MonikaInfiniteIcon.tsx
│   │   │       ├── SegmentedProgressBar.tsx
│   │   │       ├── Skeleton.tsx
│   │   │       ├── StatusIndicator.tsx
│   │   │       ├── ThemeToggle.tsx
│   │   │       ├── TickerTape.tsx
│   │   │       ├── TypewriterButton.tsx
│   │   │       ├── VuMeter.tsx
│   │   │       ├── WeekendGapBanner.tsx
│   │   │       └── WindowFrame.tsx
│   │   ├── hooks/
│   │   │   ├── useAgentChatWs.ts
│   │   │   ├── usePolling.ts
│   │   │   └── useWebSocket.ts
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── formatters.ts
│   │   │   └── soundEffects.ts
│   │   ├── store/
│   │   │   └── dashboardStore.ts
│   │   ├── theme/
│   │   │   └── tokens.ts
│   │   ├── types/
│   │   │   ├── api.ts
│   │   │   ├── openapi.json
│   │   │   └── openapi.ts
│   │   ├── App.css
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── .gitignore
│   ├── .oxlintrc.json
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── README.md
│   ├── tsconfig.app.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
│   ├── agent/
│   │   ├── test_agent_loop.py
│   │   ├── test_chat_memory_budget.py
│   │   ├── test_core_and_error_taxonomy.py
│   │   ├── test_file_write_approval.py
│   │   ├── test_harness_effort_recovery_and_antislop.py
│   │   ├── test_mcp_write_approval.py
│   │   ├── test_memory_skills_and_traps.py
│   │   ├── test_moa_loop.py
│   │   ├── test_multiagent_and_delegation.py
│   │   ├── test_p0_safety_and_invariants.py
│   │   ├── test_pgvector_startup_check.py
│   │   ├── test_runtime_enhancements.py
│   │   ├── test_runtime_lifecycle.py
│   │   ├── test_startup_watchdog.py
│   │   ├── test_startup_watchdog_enhancement.py
│   │   ├── test_task_registry.py
│   │   ├── test_turn_hardening_and_guards.py
│   │   ├── test_turn_lease_manager.py
│   │   └── test_turn_liveness_and_recovery.py
│   ├── analysis/
│   │   ├── arbitration/
│   │   │   ├── test_degridlock_and_portfolio_invariants.py
│   │   │   ├── test_fase12_hardening.py
│   │   │   └── test_recency_brier_weighting.py
│   │   ├── calculators/
│   │   │   └── test_quant_plateau_optimizer.py
│   │   ├── debate/
│   │   │   └── test_market_aware_judge.py
│   │   ├── evaluation/
│   │   │   └── test_decision_quality.py
│   │   ├── grounding/
│   │   │   ├── test_extended_grounding.py
│   │   │   └── test_market_grounding_live.py
│   │   ├── mcp/
│   │   │   ├── test_mcp.py
│   │   │   ├── test_mcp_and_integrations.py
│   │   │   ├── test_mcp_client_manager.py
│   │   │   └── test_mcp_dispatcher_and_routes.py
│   │   ├── memory/
│   │   │   ├── test_counterfactual_simulator.py
│   │   │   ├── test_failure_taxonomy.py
│   │   │   ├── test_fase_8_hardening.py
│   │   │   ├── test_negative_constraint_generator.py
│   │   │   ├── test_playbook_ledger.py
│   │   │   ├── test_playbook_lifecycle.py
│   │   │   ├── test_skill_curator.py
│   │   │   └── test_specialist_and_playbook.py
│   │   ├── prompt/
│   │   │   └── test_unified_risk_contract_and_gates.py
│   │   ├── providers/
│   │   │   ├── test_capabilities.py
│   │   │   ├── test_credential_pool_routing.py
│   │   │   ├── test_failover_expanded.py
│   │   │   ├── test_fallback_wrapper_cooldown.py
│   │   │   ├── test_llm_and_streaming.py
│   │   │   ├── test_nine_router_provider.py
│   │   │   ├── test_prompt_caching_enhancements.py
│   │   │   ├── test_providers_and_cost_engine.py
│   │   │   ├── test_structured_fallback.py
│   │   │   └── test_typesafe_provider.py
│   │   ├── recursive_harness/
│   │   │   ├── test_advanced_harness_enhancements.py
│   │   │   ├── test_agent_harness.py
│   │   │   ├── test_capabilities_and_structured.py
│   │   │   ├── test_context_compressor.py
│   │   │   ├── test_critical_harness.py
│   │   │   ├── test_error_classifier.py
│   │   │   ├── test_harness_enhancements.py
│   │   │   ├── test_harness_routes.py
│   │   │   ├── test_library.py
│   │   │   ├── test_prompt_cache_architecture.py
│   │   │   ├── test_prompt_tiers_and_state.py
│   │   │   ├── test_propose_probe_compose.py
│   │   │   ├── test_recursive_harness_integration.py
│   │   │   ├── test_runtime_wiring.py
│   │   │   ├── test_structured_context_engine.py
│   │   │   ├── test_surface.py
│   │   │   ├── test_tool_batch_and_repair.py
│   │   │   ├── test_trade_stop_and_segment_planner.py
│   │   │   └── test_tree.py
│   │   ├── strategies/
│   │   │   ├── test_evidence_significance.py
│   │   │   ├── test_evidence_store_aging.py
│   │   │   ├── test_gbpusd_trend_breakout.py
│   │   │   ├── test_new_empirical_strategies.py
│   │   │   ├── test_phase15_remediation.py
│   │   │   ├── test_promoted_empirical_strategies.py
│   │   │   ├── test_promotion_evidence_source.py
│   │   │   ├── test_quant_discovery_pipeline.py
│   │   │   ├── test_strategy_governance_and_brackets.py
│   │   │   ├── test_strategy_registry_summary.py
│   │   │   ├── test_synthesized_strategy_resilience.py
│   │   │   └── test_xti_pairs_readiness.py
│   │   ├── tools/
│   │   │   ├── test_domain_handlers.py
│   │   │   ├── test_domain_universal_tools.py
│   │   │   ├── test_file_tool_catalog_integration.py
│   │   │   ├── test_handlers_regression.py
│   │   │   ├── test_loop_guard.py
│   │   │   ├── test_market_quote_tool.py
│   │   │   ├── test_news_tools.py
│   │   │   ├── test_ptc_and_sandboxes.py
│   │   │   ├── test_ptc_execution.py
│   │   │   ├── test_registry.py
│   │   │   ├── test_registry_and_handlers.py
│   │   │   ├── test_sandbox_and_delegation.py
│   │   │   ├── test_security_interceptors.py
│   │   │   ├── test_security_remediation_phase7.py
│   │   │   ├── test_skills_tools.py
│   │   │   ├── test_spill_reader_tool.py
│   │   │   ├── test_tool_catalog_and_spill.py
│   │   │   ├── test_tool_deadlines_and_availability.py
│   │   │   ├── test_tool_engine_and_patching.py
│   │   │   ├── test_tool_executor_timesfm.py
│   │   │   ├── test_tool_guardrails.py
│   │   │   ├── test_tooling_and_sandbox.py
│   │   │   ├── test_unified_registry.py
│   │   │   ├── test_unified_tool_registry_and_search.py
│   │   │   ├── test_unified_tooling.py
│   │   │   └── test_universal_tools.py
│   │   ├── __init__.py
│   │   ├── test_adhoc_and_quant_sandbox.py
│   │   ├── test_adjudication_and_risk.py
│   │   ├── test_adjudication_framework.py
│   │   ├── test_adjustment_validator.py
│   │   ├── test_advanced_quant_tools.py
│   │   ├── test_adversarial_dialectic_debate.py
│   │   ├── test_agent_harness_steering_truncation.py
│   │   ├── test_arbitrator_borderline_guard.py
│   │   ├── test_audit_sota_enhancements.py
│   │   ├── test_candidate_lessons_shadow_validation.py
│   │   ├── test_central_bank_rates.py
│   │   ├── test_chronicle_curator.py
│   │   ├── test_chronicle_writer.py
│   │   ├── test_closed_loop_memory.py
│   │   ├── test_composite_tools.py
│   │   ├── test_concurrent_macro_analysts.py
│   │   ├── test_confluence_verifier.py
│   │   ├── test_consecutive_sl_query_fix.py
│   │   ├── test_context_compressor_hardening.py
│   │   ├── test_copula_tail_risk.py
│   │   ├── test_core_data_validator.py
│   │   ├── test_cross_timeframe_gate.py
│   │   ├── test_daily_range_calculator.py
│   │   ├── test_daily_range_timesfm.py
│   │   ├── test_debate_orchestrator_and_transcript_persistence.py
│   │   ├── test_debate_risk_and_pm.py
│   │   ├── test_decay_monitor.py
│   │   ├── test_decay_monitor_incubation.py
│   │   ├── test_deliberation_and_redaction.py
│   │   ├── test_denial_breaker_guard.py
│   │   ├── test_digest_slice_generator.py
│   │   ├── test_domain_handlers.py
│   │   ├── test_economic_surprise.py
│   │   ├── test_error_classifier.py
│   │   ├── test_event_broadcaster.py
│   │   ├── test_exact_decimal_math.py
│   │   ├── test_fallback_restore.py
│   │   ├── test_float_coercion.py
│   │   ├── test_frozen_memory_snapshot.py
│   │   ├── test_fundamental_prefetch_compliance.py
│   │   ├── test_fundamental_stage.py
│   │   ├── test_funding_rate_and_fedwatch_fixes.py
│   │   ├── test_gemini_and_news_fixes.py
│   │   ├── test_gemini_schema_normalization.py
│   │   ├── test_gemini_token_governance.py
│   │   ├── test_groq_provider.py
│   │   ├── test_hierarchical_risk_parity.py
│   │   ├── test_hmm_regime.py
│   │   ├── test_hypothesis_and_evidence.py
│   │   ├── test_in_harness_grounding.py
│   │   ├── test_invariant_calculator.py
│   │   ├── test_isolated_harness.py
│   │   ├── test_jev_news_classifier.py
│   │   ├── test_jev_verifiers_and_builders.py
│   │   ├── test_layered_memory.py
│   │   ├── test_level_optimizer_rr_pairing.py
│   │   ├── test_llm_factory.py
│   │   ├── test_llm_memory_cache_enhancements.py
│   │   ├── test_macro_debate.py
│   │   ├── test_macro_playbook_runner.py
│   │   ├── test_macro_preprocessor.py
│   │   ├── test_macro_priced_in_calculator.py
│   │   ├── test_market_intelligence_tools.py
│   │   ├── test_market_snapshot.py
│   │   ├── test_mechanical_risk_gate.py
│   │   ├── test_memory_subagent_copula_remediation.py
│   │   ├── test_multi_timeframe_tool.py
│   │   ├── test_news_digest.py
│   │   ├── test_openai_provider.py
│   │   ├── test_openrouter_provider.py
│   │   ├── test_output_verifier.py
│   │   ├── test_paper_incubation_loop.py
│   │   ├── test_per_asset_stage.py
│   │   ├── test_per_asset_stage_recovery.py
│   │   ├── test_pipeline_defensive_bias_fixes.py
│   │   ├── test_pipeline_plugins.py
│   │   ├── test_playbook_rule_attribution.py
│   │   ├── test_portfolio_synthesis_key_safety.py
│   │   ├── test_precommit_gate.py
│   │   ├── test_prefetch_and_anti_fabrication.py
│   │   ├── test_preflight_gate.py
│   │   ├── test_pricing_audit.py
│   │   ├── test_progressive_tools.py
│   │   ├── test_prompt_cache_stability.py
│   │   ├── test_prompt_quality_gates.py
│   │   ├── test_provenance_tagger.py
│   │   ├── test_provider_failover_classifier.py
│   │   ├── test_provider_registry.py
│   │   ├── test_providers.py
│   │   ├── test_providers_streaming.py
│   │   ├── test_regime_and_factor_parity.py
│   │   ├── test_regime_b_confluence_verification.py
│   │   ├── test_sandbox_runner.py
│   │   ├── test_scenario_tree.py
│   │   ├── test_session_search.py
│   │   ├── test_signal_arbitrator_bayesian_pooling.py
│   │   ├── test_signal_arbitrator_confirmation.py
│   │   ├── test_signal_arbitrator_runtime_integration.py
│   │   ├── test_signal_arbitrator_timesfm.py
│   │   ├── test_signal_arbitrator_volatile_chop.py
│   │   ├── test_skill_crystallizer.py
│   │   ├── test_skill_crystallizer_curation.py
│   │   ├── test_skill_evolution.py
│   │   ├── test_sota_harness_integration.py
│   │   ├── test_stage1_priced_in.py
│   │   ├── test_stage2_bundle_truncation.py
│   │   ├── test_stage2_prefetcher.py
│   │   ├── test_stage2_structural_fixes.py
│   │   ├── test_stall_guard.py
│   │   ├── test_streaming.py
│   │   ├── test_structured_output_degradation.py
│   │   ├── test_subagent_blackboard.py
│   │   ├── test_submission_structural_limit.py
│   │   ├── test_summary_fallback.py
│   │   ├── test_system_config_upsert.py
│   │   ├── test_technical_analysis_improvements.py
│   │   ├── test_telegram_tools_integration.py
│   │   ├── test_token_logging.py
│   │   ├── test_tool_executor.py
│   │   ├── test_tool_executor_concurrency.py
│   │   ├── test_tool_registry.py
│   │   ├── test_tools_definitions.py
│   │   ├── test_unified_threshold_calculator.py
│   │   ├── test_universal_cache_telemetry.py
│   │   └── test_working_scratchpad.py
│   ├── application/
│   │   ├── services/
│   │   │   └── test_general_harness_integration.py
│   │   ├── test_empirical_promoted_strategies.py
│   │   ├── test_profitability_structural_fixes.py
│   │   └── test_signal_arbitrator_refinement.py
│   ├── architecture/
│   │   ├── test_docs_parity.py
│   │   ├── test_domain_ports_compliance.py
│   │   └── test_layer_contracts.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── test_antigravity_bridge.py
│   │   ├── test_antigravity_pool.py
│   │   ├── test_claude_oauth.py
│   │   ├── test_codex_device_flow.py
│   │   └── test_oauth_store.py
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── test_alpha_validation.py
│   │   ├── test_benchmark_tracker.py
│   │   ├── test_canonical_price_loader.py
│   │   ├── test_empirical_portfolio_monte_carlo.py
│   │   ├── test_fase7_lookahead_and_kelly.py
│   │   ├── test_isolated_harness_fidelity.py
│   │   ├── test_langgraph_backtest_parity.py
│   │   ├── test_monte_carlo_block_bootstrap.py
│   │   ├── test_offline_signal_engine_no_lookahead.py
│   │   ├── test_outcome_evaluator.py
│   │   ├── test_outcome_evaluator_dynamic_friction.py
│   │   ├── test_outcome_evaluator_realism.py
│   │   ├── test_performance_metrics.py
│   │   ├── test_point_in_time_engine.py
│   │   ├── test_point_in_time_full_mode.py
│   │   ├── test_purged_wfe_and_pbo.py
│   │   ├── test_report_generator_daily_sharpe_sortino.py
│   │   ├── test_statistical_tests.py
│   │   ├── test_time_machine.py
│   │   └── test_walk_forward_purged.py
│   ├── benchmark/
│   │   ├── test_alpha_arena.py
│   │   ├── test_benchmark_engine_and_integration.py
│   │   ├── test_gepa_full.py
│   │   ├── test_judge_ensemble_integration.py
│   │   ├── test_paired_evaluator.py
│   │   ├── test_prompt_evolution.py
│   │   └── test_trade_trajectory.py
│   ├── cli/
│   │   ├── test_analysis_tree.py
│   │   ├── test_approval_modal.py
│   │   ├── test_auth_ctrl.py
│   │   ├── test_busy_input.py
│   │   ├── test_chat_suite.py
│   │   ├── test_doctor_and_profile.py
│   │   ├── test_platform_compat.py
│   │   ├── test_plugin_cli.py
│   │   ├── test_setup_and_doctor.py
│   │   ├── test_sparklines.py
│   │   ├── test_theme_packs.py
│   │   ├── test_tui_components.py
│   │   └── test_tui_ergonomics.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── test_atomic_writer.py
│   │   ├── test_audit_settings_keys.py
│   │   ├── test_config_manager.py
│   │   ├── test_config_migrations.py
│   │   ├── test_config_schemas.py
│   │   ├── test_hot_reload.py
│   │   ├── test_key_validator.py
│   │   ├── test_migrations.py
│   │   ├── test_modular_config.py
│   │   ├── test_risk_contract_sync.py
│   │   ├── test_settings.py
│   │   ├── test_settings_llm.py
│   │   ├── test_settings_task_roles.py
│   │   └── test_skill_risk_contract_sync.py
│   ├── data_sources/
│   │   ├── __init__.py
│   │   ├── test_bond_yields.py
│   │   ├── test_central_bank_watch.py
│   │   ├── test_cftc_cot.py
│   │   ├── test_circuit_breaker.py
│   │   ├── test_dxy_yfinance.py
│   │   ├── test_fred_treasury_yield.py
│   │   ├── test_macro_fail_closed.py
│   │   ├── test_prediction_market.py
│   │   ├── test_validators.py
│   │   ├── test_vix_yfinance.py
│   │   ├── test_web_and_search.py
│   │   ├── test_web_reader.py
│   │   └── test_web_search.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── test_adapters.py
│   │   ├── test_cleanup.py
│   │   ├── test_core_runtime_and_memory.py
│   │   ├── test_db.py
│   │   ├── test_domain_models_and_subagent.py
│   │   ├── test_event_store.py
│   │   ├── test_foreign_key_and_test_hygiene.py
│   │   ├── test_hybrid_state.py
│   │   ├── test_migration_0010_downgrade.py
│   │   ├── test_models.py
│   │   ├── test_repositories.py
│   │   ├── test_schema_completeness_and_migrations.py
│   │   ├── test_session_fts_and_rewind.py
│   │   ├── test_sqlite_concurrency_fix.py
│   │   ├── test_unified_state_and_compression.py
│   │   └── test_user_market_intel.py
│   ├── deploy/
│   │   └── test_deployment_configs.py
│   ├── domain/
│   │   ├── execution/
│   │   │   └── test_bracket_optimizer.py
│   │   ├── test_bracket_optimizer_buffers.py
│   │   ├── test_macro_regime_classifier.py
│   │   └── test_risk_gate_macro_regime.py
│   ├── evals/
│   │   ├── __init__.py
│   │   ├── test_eval_metrics_and_ab_runner.py
│   │   ├── test_eval_reliability.py
│   │   ├── test_evals_and_observability.py
│   │   ├── test_harness_audit.py
│   │   ├── test_llm_replay.py
│   │   ├── test_offline_evals.py
│   │   ├── test_offline_oracles.py
│   │   └── test_simulation_and_oracles.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── test_application_execution_full_coverage.py
│   │   ├── test_audit_execution_path_remediation.py
│   │   ├── test_broker_plugins.py
│   │   ├── test_broker_registry.py
│   │   ├── test_ea_bridge.py
│   │   ├── test_ea_watchdog.py
│   │   ├── test_effect_gate.py
│   │   ├── test_execution_broker_routing.py
│   │   ├── test_execution_concurrency.py
│   │   ├── test_execution_orchestration.py
│   │   ├── test_execution_order_invariants.py
│   │   ├── test_execution_safety_guards.py
│   │   ├── test_execution_service.py
│   │   ├── test_fase14_execution_invariants.py
│   │   ├── test_fase5_mt5_watchdog_scrapers.py
│   │   ├── test_flake_tolerant_health.py
│   │   ├── test_heartbeat_writer.py
│   │   ├── test_idempotency_guard.py
│   │   ├── test_inflight_reconciliation.py
│   │   ├── test_modular_execution_service.py
│   │   ├── test_mt5_broker_time.py
│   │   ├── test_mt5_chunked_fetch.py
│   │   ├── test_mt5_client.py
│   │   ├── test_mt5_compat.py
│   │   ├── test_mt5_ohlcv_sync.py
│   │   ├── test_mt5_priority_queue.py
│   │   ├── test_mt5_profile_and_commit.py
│   │   ├── test_mt5_tick_poller.py
│   │   ├── test_order_emulator.py
│   │   ├── test_order_reconciliation.py
│   │   ├── test_paired_execution.py
│   │   ├── test_partial_fill_and_slippage.py
│   │   ├── test_rate_throttler.py
│   │   ├── test_real_concurrency_locking.py
│   │   ├── test_self_healing_executor.py
│   │   ├── test_service_base.py
│   │   ├── test_staged_order_execution.py
│   │   ├── test_tranche_execution.py
│   │   └── test_verification_engine.py
│   ├── gateway/
│   │   ├── test_gateway_and_api_server.py
│   │   ├── test_gateways_and_approvals.py
│   │   ├── test_omnichannel_and_hitl.py
│   │   ├── test_omnichannel_stream.py
│   │   ├── test_omnichannel_streamer.py
│   │   ├── test_telegram_adapter_and_webhook_safety.py
│   │   └── test_universal_ecosystem.py
│   ├── graph/
│   │   ├── test_context_hygiene.py
│   │   ├── test_debate_convergence.py
│   │   ├── test_debate_subgraph.py
│   │   ├── test_dual_checkpointer.py
│   │   ├── test_duplicate_entry_guard.py
│   │   ├── test_reactive_graph.py
│   │   ├── test_risk_gate_node_levels.py
│   │   ├── test_state_pruner_and_checkpointer.py
│   │   ├── test_team_compiler_live.py
│   │   └── test_workflow_authoritative_checkpointer.py
│   ├── harness/
│   │   ├── test_domain_plugins_integration.py
│   │   ├── test_functional_compatibility.py
│   │   ├── test_installer_service.py
│   │   ├── test_message_repair.py
│   │   ├── test_plugin_engine.py
│   │   ├── test_plugin_kernel_namespace.py
│   │   ├── test_repetition_and_candidate.py
│   │   ├── test_threat_scanner.py
│   │   ├── test_trading_agent_harness_integration.py
│   │   └── test_unified_plugin_engine.py
│   ├── indicators/
│   │   ├── __init__.py
│   │   ├── test_advanced_volatility.py
│   │   ├── test_factor_primitives.py
│   │   ├── test_micro_alpha_zoo.py
│   │   ├── test_microstructure.py
│   │   ├── test_pattern_similarity.py
│   │   ├── test_phase10_regression.py
│   │   ├── test_qlib_and_wq_factors.py
│   │   ├── test_regime_detector.py
│   │   ├── test_structure.py
│   │   ├── test_technical.py
│   │   └── test_timesfm_engine.py
│   ├── logging_observability/
│   │   ├── __init__.py
│   │   ├── test_activity_logger.py
│   │   ├── test_cost_tracking_dashboard.py
│   │   ├── test_cycle_event_log_and_feedback.py
│   │   ├── test_dashboard_api.py
│   │   ├── test_dashboard_backtest_routes.py
│   │   ├── test_dashboard_memory_routes.py
│   │   ├── test_dashboard_observability.py
│   │   ├── test_dashboard_observability_endpoints.py
│   │   ├── test_dashboard_plugins_routes.py
│   │   ├── test_intelligence_routes.py
│   │   ├── test_log_streamer.py
│   │   ├── test_modular_routes.py
│   │   ├── test_otlp_exporter.py
│   │   ├── test_report_writer.py
│   │   ├── test_tearsheet_generator.py
│   │   ├── test_token_budgeter.py
│   │   ├── test_trace_search.py
│   │   ├── test_tracing.py
│   │   └── test_websocket_stream_scrubber.py
│   ├── mcp/
│   │   └── test_bidirectional_mcp.py
│   ├── memory/
│   │   ├── test_adaptive_context_engine.py
│   │   ├── test_background_review_async.py
│   │   ├── test_learning_loop_and_ledger.py
│   │   └── test_trajectory_exporter.py
│   ├── perf/
│   │   ├── test_memory_budget.py
│   │   └── test_microstructure_perf.py
│   ├── planning/
│   │   ├── test_session_integration.py
│   │   └── test_session_plan.py
│   ├── plugins/
│   │   ├── test_plugin_lifecycle.py
│   │   ├── test_plugin_manifest_and_loader.py
│   │   └── test_reference_plugins.py
│   ├── prompt_eval/
│   │   ├── fixtures/
│   │   │   └── smc_ict_fixtures.json
│   │   ├── __init__.py
│   │   └── test_prompt_eval.py
│   ├── provider/
│   │   ├── __init__.py
│   │   ├── test_codex_provider.py
│   │   ├── test_credential_pool.py
│   │   ├── test_error_taxonomy.py
│   │   ├── test_multitier_subscription_routing.py
│   │   ├── test_opencode_provider.py
│   │   ├── test_role_fallback_chain.py
│   │   ├── test_universal_provider.py
│   │   └── test_zai_provider.py
│   ├── providers/
│   │   └── test_tool_schema_normalizer.py
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── test_approval_hub.py
│   │   ├── test_bounded_mandate_and_runcard.py
│   │   ├── test_calendar_freshness.py
│   │   ├── test_daily_rollover_ny_close.py
│   │   ├── test_domain_risk_full_coverage.py
│   │   ├── test_evidence_gate_fail_closed.py
│   │   ├── test_execution_simulator.py
│   │   ├── test_flash_crash_risk_gate.py
│   │   ├── test_fortress_invariants.py
│   │   ├── test_invariant_registry.py
│   │   ├── test_invariants_and_replay.py
│   │   ├── test_pending_action.py
│   │   ├── test_portfolio_correlation_gate.py
│   │   ├── test_position_sizing.py
│   │   ├── test_property_sizing_hypothesis.py
│   │   ├── test_quant_scorecard_gate.py
│   │   ├── test_risk_gate.py
│   │   ├── test_risk_gate_expectancy.py
│   │   ├── test_risk_rule_pipeline.py
│   │   ├── test_safety_audit.py
│   │   ├── test_subsystem5_risk_and_dom.py
│   │   ├── test_timesfm_decoupled_risk_gate.py
│   │   ├── test_trade_proposal.py
│   │   └── test_weekly_drawdown_source.py
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── test_active_calendar_poller.py
│   │   ├── test_alpha_discovery_closed_loop.py
│   │   ├── test_alpha_discovery_overhaul.py
│   │   ├── test_cron_nlp_and_worker.py
│   │   ├── test_cycle_scheduler.py
│   │   ├── test_cycle_scheduler_demo_gate.py
│   │   ├── test_digest_slice_scheduler.py
│   │   ├── test_edge_strategy_runner.py
│   │   ├── test_edge_strategy_runner_admission.py
│   │   ├── test_flash_crash_detector.py
│   │   ├── test_friday_gap_protection.py
│   │   ├── test_macro_data_scheduler.py
│   │   ├── test_market_data_scheduler.py
│   │   ├── test_multi_stage_trade_plan.py
│   │   ├── test_news_watcher.py
│   │   ├── test_news_watcher_turn_lease.py
│   │   ├── test_playbook_curator.py
│   │   ├── test_position_exit_reviewer.py
│   │   ├── test_post_release_analyzer.py
│   │   ├── test_report_and_safehaven.py
│   │   ├── test_scraper_runner.py
│   │   ├── test_strategy_synthesis_historical_sandbox.py
│   │   ├── test_strategy_synthesis_scheduler.py
│   │   ├── test_synthesis_hypothesis_lineage.py
│   │   ├── test_task_plugin_lifecycle.py
│   │   ├── test_trailing_stop_manager.py
│   │   ├── test_trigger_checker.py
│   │   ├── test_unified_cron_and_security.py
│   │   ├── test_unified_cron_outbox.py
│   │   ├── test_universal_cron.py
│   │   └── test_user_intel_cycle_injection.py
│   ├── scrapers/
│   │   ├── calendar/
│   │   │   ├── __init__.py
│   │   │   ├── test_calendar_finnhub.py
│   │   │   ├── test_calendar_forexfactory.py
│   │   │   └── test_calendar_investing.py
│   │   ├── macro/
│   │   │   ├── __init__.py
│   │   │   └── test_cme_fedwatch.py
│   │   ├── news/
│   │   │   ├── __init__.py
│   │   │   ├── test_kitco_news.py
│   │   │   ├── test_rss_base.py
│   │   │   ├── test_rss_bloomberg.py
│   │   │   ├── test_rss_cnbc.py
│   │   │   ├── test_rss_coindesk.py
│   │   │   ├── test_rss_dow_jones.py
│   │   │   ├── test_rss_forexlive.py
│   │   │   ├── test_rss_ft.py
│   │   │   ├── test_rss_fxstreet.py
│   │   │   ├── test_rss_investing.py
│   │   │   ├── test_rss_marketwatch.py
│   │   │   ├── test_rss_reuters.py
│   │   │   ├── test_rss_wsj.py
│   │   │   └── test_tradingview_news.py
│   │   ├── sentiment/
│   │   │   └── test_sentiment_scrapers.py
│   │   ├── social/
│   │   │   ├── __init__.py
│   │   │   └── test_twitter_watch.py
│   │   ├── __init__.py
│   │   ├── test_base_scraper.py
│   │   ├── test_scraper_language_isolation.py
│   │   └── test_scraper_models.py
│   ├── security/
│   │   ├── test_credential_vault.py
│   │   ├── test_fase3_security_hardening.py
│   │   ├── test_fase4_central_config_and_security.py
│   │   ├── test_security_guards.py
│   │   └── test_supply_chain_and_win32.py
│   ├── services/
│   │   ├── test_portfolio_service.py
│   │   ├── test_system_status_service.py
│   │   └── test_trading_service.py
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── test_central_banks_framework.py
│   │   ├── test_event_probability_playbook.py
│   │   ├── test_event_probability_stress.py
│   │   ├── test_loader.py
│   │   ├── test_playbook_screener.py
│   │   ├── test_playbook_stress_challenge.py
│   │   ├── test_progressive_playbook_disclosure.py
│   │   ├── test_skill_curator.py
│   │   ├── test_skill_engine.py
│   │   ├── test_skills_and_continuous_learning.py
│   │   ├── test_trading_skill_linter.py
│   │   ├── test_trading_skills_format.py
│   │   └── test_unified_skills.py
│   ├── strategies/
│   │   ├── test_gap_fade.py
│   │   ├── test_liquidity_sweep_edge.py
│   │   ├── test_pretrade_gate.py
│   │   ├── test_strategy_edge_tracker.py
│   │   └── test_tsm_momentum.py
│   ├── support/
│   │   ├── __init__.py
│   │   └── replay_provider.py
│   ├── telegram_bot/
│   │   ├── __init__.py
│   │   ├── test_backtest_command.py
│   │   ├── test_bot.py
│   │   ├── test_chat_agent.py
│   │   ├── test_chat_agent_deep_research.py
│   │   ├── test_chat_agent_deep_research_stress.py
│   │   ├── test_chat_agent_stress_challenge.py
│   │   ├── test_chat_agent_tool_understanding.py
│   │   ├── test_chat_compaction_and_control.py
│   │   ├── test_chat_database_access.py
│   │   ├── test_chat_tool_router.py
│   │   ├── test_chat_tool_router_semantic.py
│   │   ├── test_chat_tool_router_stress.py
│   │   ├── test_command_handlers_descriptors.py
│   │   ├── test_command_router.py
│   │   ├── test_fase6_outbound_queue_and_sync.py
│   │   ├── test_fuzzy_and_confirm.py
│   │   ├── test_plugins_telegram.py
│   │   ├── test_progressive_tools.py
│   │   ├── test_proposal_notifier.py
│   │   ├── test_sanitizer.py
│   │   ├── test_session_approval.py
│   │   ├── test_telegram_enhancements.py
│   │   ├── test_telegram_pairing.py
│   │   ├── test_telegram_streaming_tools.py
│   │   └── test_voice_handler.py
│   ├── unit/
│   │   ├── application/
│   │   │   ├── agent/
│   │   │   │   └── test_replay_envelope_and_recovery.py
│   │   │   └── analysis/
│   │   │       ├── test_forked_subagent_cache.py
│   │   │       └── test_spill_and_ptc_parallel.py
│   │   └── infrastructure/
│   │       └── llm/
│   │           └── test_kv_cache_invariance.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── test_analysis_tracker.py
│   │   ├── test_analytics_trackers.py
│   │   ├── test_brief_contamination_guard.py
│   │   ├── test_cache_breakpoint.py
│   │   ├── test_cache_immutability_and_replay.py
│   │   ├── test_cache_miss_detector.py
│   │   ├── test_caveman_compressor.py
│   │   ├── test_cds_outcome_tracker.py
│   │   ├── test_chart_generator.py
│   │   ├── test_confidence_calibrator.py
│   │   ├── test_constrained_sampling.py
│   │   ├── test_container_hierarchical.py
│   │   ├── test_context_coherence.py
│   │   ├── test_context_compaction.py
│   │   ├── test_context_tracker.py
│   │   ├── test_cost_tracker.py
│   │   ├── test_cot_thresholds.py
│   │   ├── test_credit_balance_tracker.py
│   │   ├── test_cross_agent_sync.py
│   │   ├── test_currency_utils.py
│   │   ├── test_cycle_budget_guard.py
│   │   ├── test_data_dedup.py
│   │   ├── test_data_freshness_macro_expansion.py
│   │   ├── test_data_validator.py
│   │   ├── test_db_backup.py
│   │   ├── test_deferred_dispatcher.py
│   │   ├── test_edge_tracker.py
│   │   ├── test_embedding.py
│   │   ├── test_enhanced_cds.py
│   │   ├── test_env_file_manager.py
│   │   ├── test_event_bus.py
│   │   ├── test_event_bus_enhancements.py
│   │   ├── test_event_loop.py
│   │   ├── test_http_retry.py
│   │   ├── test_instrument_identity.py
│   │   ├── test_lfsp_compression.py
│   │   ├── test_log_redactor_and_container.py
│   │   ├── test_lossless_condensation_integrity.py
│   │   ├── test_notifier.py
│   │   ├── test_paper_trade_detection_method_fix.py
│   │   ├── test_paper_trading_streak_policy.py
│   │   ├── test_platt_isotonic_calibration.py
│   │   ├── test_plugins.py
│   │   ├── test_plugins_extended.py
│   │   ├── test_pricing_tier.py
│   │   ├── test_prompt_ab_test.py
│   │   ├── test_prompt_assembler.py
│   │   ├── test_prompt_caching.py
│   │   ├── test_prompt_compressor.py
│   │   ├── test_prompt_tiering.py
│   │   ├── test_quantized_thinking.py
│   │   ├── test_retry_decorator.py
│   │   ├── test_sota_harness_alpha.py
│   │   ├── test_sota_harness_beta.py
│   │   ├── test_sota_harness_gamma.py
│   │   ├── test_spill_store.py
│   │   ├── test_ssvp.py
│   │   ├── test_ssvp_coordinator.py
│   │   ├── test_stream_scrubber.py
│   │   ├── test_threat_detector.py
│   │   ├── test_token_auditor.py
│   │   ├── test_token_efficiency_and_anti_loop.py
│   │   ├── test_tool_condenser.py
│   │   ├── test_utility_upgrades.py
│   │   └── test_wall_clock.py
│   ├── __init__.py
│   ├── conftest.py
│   ├── golden_news_classification.py
│   ├── test_alpha_calculator.py
│   ├── test_alpha_discovery_scheduler.py
│   ├── test_alpha_observability_partitioning.py
│   ├── test_analytical_query.py
│   ├── test_analytics_advanced.py
│   ├── test_api_frontend_contract.py
│   ├── test_architecture_parity.py
│   ├── test_audit_remediation_consolidated.py
│   ├── test_audit_round1_core_invariants.py
│   ├── test_audit_round1_execution_invariants.py
│   ├── test_audit_round2_core_invariants.py
│   ├── test_audit_round2_execution_invariants.py
│   ├── test_audit_round2_remediation.py
│   ├── test_audit_round3_core_invariants.py
│   ├── test_audit_round3_institutional.py
│   ├── test_audit_round3_remediation.py
│   ├── test_audit_round4_core_invariants.py
│   ├── test_audit_round4_execution_invariants.py
│   ├── test_audit_round4_remediation.py
│   ├── test_bootstrap_composition_root.py
│   ├── test_bulkhead_isolation.py
│   ├── test_bulletproof_harness.py
│   ├── test_capability_gaps.py
│   ├── test_cds_threshold_calibrator.py
│   ├── test_chat_tool_router.py
│   ├── test_cli.py
│   ├── test_cli_theme.py
│   ├── test_codebase_hygiene_and_consolidation.py
│   ├── test_consolidation_audit.py
│   ├── test_conversational_gaps_fixes.py
│   ├── test_core_engine_safety.py
│   ├── test_core_exceptions.py
│   ├── test_core_remediation_invariants.py
│   ├── test_critical_fixes_verification.py
│   ├── test_dashboard_action_endpoints.py
│   ├── test_database_concurrency.py
│   ├── test_debate_concurrency.py
│   ├── test_debate_node.py
│   ├── test_debate_node_smoke.py
│   ├── test_domain_layer_audit_hardening.py
│   ├── test_econometric_models.py
│   ├── test_engine_critical_fixes.py
│   ├── test_enhancements_verification.py
│   ├── test_env_example_parity.py
│   ├── test_event_driven_harness.py
│   ├── test_event_loop_and_shutdown.py
│   ├── test_event_probability_flow.py
│   ├── test_execution_invariants.py
│   ├── test_execution_remediation_invariants.py
│   ├── test_extended_polish_invariants.py
│   ├── test_fedwatch_comparison.py
│   ├── test_gap_analysis_remediation.py
│   ├── test_god_object_decomposition_audit.py
│   ├── test_graph_workflow.py
│   ├── test_installation_tiers.py
│   ├── test_interfaces_and_observability_verification.py
│   ├── test_issue_investigation_reproduction.py
│   ├── test_live_macro_fetching.py
│   ├── test_log_issues_and_paper_trade_fixes.py
│   ├── test_m2_empirical_stress.py
│   ├── test_main.py
│   ├── test_margin_monitor.py
│   ├── test_memory_constructors.py
│   ├── test_model_quadrant_analysis_html.py
│   ├── test_model_quadrant_generator.py
│   ├── test_model_routing_config.py
│   ├── test_module_import_integrity.py
│   ├── test_monika_capability_expansion.py
│   ├── test_order_flow_engine.py
│   ├── test_order_state_machine_parity.py
│   ├── test_outcome_linker_pips.py
│   ├── test_paper_tracker_accounting.py
│   ├── test_paper_tracker_fix.py
│   ├── test_paths.py
│   ├── test_phase19_remediation.py
│   ├── test_phase20_remediation.py
│   ├── test_phase_2_remediation.py
│   ├── test_platform_compat.py
│   ├── test_process_guardian.py
│   ├── test_provider_and_tools_verification.py
│   ├── test_provider_signatures.py
│   ├── test_pydantic_schemas.py
│   ├── test_real_functional_verification.py
│   ├── test_reflector_alpha.py
│   ├── test_remediation_fixes.py
│   ├── test_rolling_correlation.py
│   ├── test_scraper_check_scripts.py
│   ├── test_sentiment_aggregator.py
│   ├── test_smc_advanced.py
│   ├── test_sota_frontier_upgrade.py
│   ├── test_stage1_prefetcher.py
│   ├── test_stategraph_and_safety_verification.py
│   ├── test_strategies_smc_bb.py
│   ├── test_subagent_spawner.py
│   ├── test_system_hotfixes_verification.py
│   ├── test_system_polish_invariants.py
│   ├── test_system_wiring_audit.py
│   ├── test_telegram_message_formatter.py
│   ├── test_token_efficiency_architectural.py
│   ├── test_toolsets_and_terminal_guard.py
│   ├── test_trade_lifecycle_immutability.py
│   ├── test_universal_macro_and_capability_remediation.py
│   ├── test_vector_factor_engine.py
│   └── test_workspace_mcp_integration.py
│   ├── check_scrapers/
│   │   ├── __init__.py
│   │   ├── check_calendar.py
│   │   ├── check_cme.py
│   │   ├── check_news.py
│   │   ├── check_sentiment.py
│   │   ├── check_twitter.py
│   │   └── verify_all_scrapers.py
│   ├── empirical_alpha/
│   │   ├── __init__.py
│   │   ├── asset_pool_signals.py
│   │   ├── baseline_signals.py
│   │   ├── evaluator.py
│   │   ├── metadata.py
│   │   ├── multi_indicator_signals.py
│   │   ├── omni_signals.py
│   │   ├── session_signals.py
│   │   ├── signals.py
│   │   ├── targeted_signals.py
│   │   └── ultra_signals.py
│   ├── audit_settings_keys.py
│   ├── audit_token_usage.py
│   ├── benchmark_debate_openrouter.py
│   ├── benchmark_news_classification_openrouter.py
│   ├── benchmark_stage1_openrouter.py
│   ├── benchmark_stage2_openrouter.py
│   ├── bootstrap_strategy_evidence.py
│   ├── build_curated_benchmark_fixtures.py
│   ├── build_empirical_playbooks.py
│   ├── capture_dashboard_screenshots.js
│   ├── capture_tui_screenshots.py
│   ├── check_env_keys.py
│   ├── cleanup_fvg_duplicates.py
│   ├── compile_alphas_to_catalog.py
│   ├── consolidate_sqlite_dbs.py
│   ├── convert_tui_svg_to_png.js
│   ├── download_timesfm_weights.py
│   ├── evaluate_gate_filter_pnl.py
│   ├── generate_ast_docs.py
│   ├── generate_benchmark_leaderboard.py
│   ├── generate_model_quadrant.py
│   ├── generate_openapi_types.py
│   ├── heal_kill_switch_state.py
│   ├── migrate_runtime_home.py
│   ├── migrate_sqlite_to_canonical.py
│   ├── repair_price_ohlcv.py
│   ├── replay_llm_analysis.py
│   ├── report_execution_funnel.py
│   ├── reset_paper_trades.py
│   ├── run_tests.bat
│   ├── run_tests.sh
│   ├── test_m15_playbooks.py
│   ├── test_strict_edge.py
│   ├── update_economic_calendar.py
│   ├── update_index_toc.py
│   ├── ux_audit_baseline_scan.py
│   └── weekly_evaluation.py
│   ├── docker-compose.vps.yml
│   ├── Dockerfile.mt5-wine
│   ├── entrypoint_mt5.sh
│   ├── install_vps.bat
│   ├── install_vps.ps1
│   ├── install_vps.sh
│   ├── monika.service
│   ├── tradeagent.service
│   └── vps_deployment_guide.md
│   ├── adr/
│   │   ├── ADR-001-clean-architecture-layer-boundaries.md
│   │   ├── ADR-002-mechanical-fortress-and-riskgate-invariants.md
│   │   ├── ADR-003-independent-guardian-watchdog-process.md
│   │   ├── ADR-004-canonical-sqlite-and-state-directory.md
│   │   └── ADR-005-unified-api-v1-and-openapi-contract-sync.md
│   ├── architecture/
│   │   └── OVERVIEW.md
│   ├── images/
│   │   ├── dashboard/
│   │   │   ├── 01_tui_overview_dark.svg
│   │   │   ├── 01_tui_overview_light.svg
│   │   │   ├── 02_tui_analysis_dark.svg
│   │   │   ├── 02_tui_analysis_light.svg
│   │   │   ├── 03_tui_signals_dark.svg
│   │   │   ├── 03_tui_signals_light.svg
│   │   │   ├── 04_tui_risk_dark.svg
│   │   │   ├── 04_tui_risk_light.svg
│   │   │   ├── 05_tui_performance_dark.svg
│   │   │   ├── 05_tui_performance_light.svg
│   │   │   ├── 06_tui_market_dark.svg
│   │   │   ├── 06_tui_market_light.svg
│   │   │   ├── 07_tui_plugins_dark.svg
│   │   │   ├── 07_tui_plugins_light.svg
│   │   │   ├── 08_tui_benchmark_dark.svg
│   │   │   ├── 08_tui_benchmark_light.svg
│   │   │   ├── 09_tui_chat_dark.svg
│   │   │   ├── 09_tui_chat_light.svg
│   │   │   ├── 10_tui_modal_kill_dark.svg
│   │   │   └── 10_tui_modal_kill_light.svg
│   │   └── 10_terminal_ui_tui.svg
│   ├── quality/
│   │   └── baseline.json
│   ├── ux-audit/
│   │   ├── evidence/
│   │   │   ├── collect_evidence.py
│   │   │   ├── g1-tokens-and-forbidden-effects.txt
│   │   │   ├── g11-tui-audit.txt
│   │   │   ├── g2-contrast-scan.txt
│   │   │   ├── g3-type-floor-scan.txt
│   │   │   └── g4-target-and-controls-scan.txt
│   │   ├── iterations/
│   │   │   ├── 01/
│   │   │   │   └── summary.md
│   │   │   ├── 02/
│   │   │   │   └── summary.md
│   │   │   └── 03/
│   │   │       └── summary.md
│   │   ├── surfaces/
│   │   │   ├── TUI-DASH-OVERVIEW.md
│   │   │   ├── WEB-DLG-DOSSIER.md
│   │   │   ├── WEB-SHELL-HEADER.md
│   │   │   ├── WEB-SHELL-STATUSBAR.md
│   │   │   ├── WEB-TRD-OVERVIEW.md
│   │   │   ├── WEB-TRD-POSITIONS.md
│   │   │   └── WEB-TRD-SIGNALS.md
│   │   ├── AUDIT.md
│   │   ├── COVERAGE.md
│   │   ├── DECISIONS.md
│   │   ├── FINDINGS.md
│   │   ├── PLAN.md
│   │   ├── STATE.md
│   │   ├── SURFACES.md
│   │   └── SYSTEM-MAP.md
│   ├── design_system.html
│   ├── ROADMAP_SRC_MONIKA.md
│   └── SETUP_GUIDE.md
│   ├── google_credentials.json.example
│   ├── historical_macro_milestones.json
│   ├── MACRO_REALITY.md
│   ├── plugin_catalog.yaml
│   ├── settings.example.yaml
│   └── TRADING_SOUL.md
├── alembic.ini
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── DESIGN.md
├── docker-compose.yml
├── Dockerfile
├── INDEX.md
├── LICENSE
├── Makefile
├── monika.bat
├── PRD.md
├── pyproject.toml
├── pyrightconfig.json
├── pytest.ini
├── README.md
├── requirements-timesfm.txt
├── requirements.txt
├── SECURITY.md
├── skills-lock.json
├── start_monika.bat
├── start_monika.sh
├── STRUCTURE.md
```

**Total Tracked Directories**: 265 | **Total Tracked Files**: 2802
