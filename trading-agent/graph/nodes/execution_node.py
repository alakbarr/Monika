import logging
import utils.clock as clock
from typing import Dict, Any, Optional
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from datetime import datetime, timezone
from sqlalchemy import select

logger = logging.getLogger("TradingAgent.Graph.ExecutionNode")

async def execution_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node untuk mengeksekusi order via ExecutionService (auto_execute).
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    summary = state.get("summary", {})
    actionable = state.get("actionable_trades", [])

    if scheduler is None:
        logger.error("Scheduler not found in config")
        return {"summary": summary}
    
    trading_cfg = scheduler.settings.get("trading", {})
    auto_execute: bool = trading_cfg.get("auto_execute", False)
    
    if auto_execute and scheduler._mt5 and actionable:
        min_confluence = trading_cfg.get("auto_execute_min_confluence", 7)
        min_confidence = trading_cfg.get("auto_execute_min_confidence", 0.60)
        
        # [NEW] Check override
        try:
            from database.models import SystemConfig
            async with get_session() as session:
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'auto_execute_min_confidence_override'))).scalar_one_or_none()
                if cfg and cfg.value:
                    min_confidence = float(cfg.value)
        except Exception:
            pass

        start_hr = trading_cfg.get("auto_execute_active_hours_utc_start", 6)
        end_hr = trading_cfg.get("auto_execute_active_hours_utc_end", 22)
        hour = clock.now().hour

        # Support overnight windows (e.g., start=22, end=6)
        if start_hr <= end_hr:
            is_active = start_hr <= hour < end_hr
        else:
            is_active = hour >= start_hr or hour < end_hr

        if not is_active:
            logger.info(f"[Step 7b] auto_execute skipped: Outside active hours ({hour} UTC not in {start_hr}-{end_hr})")
            summary["execution"] = {"status": "skipped_outside_active_hours"}
        else:
            logger.info(f"[Step 7b] auto_execute=true — sending proposals, executing immediately...")
            
            exec_svc = getattr(scheduler, "execution_service", None)
            if exec_svc is None:
                from execution.execution_service import ExecutionService
                exec_svc = ExecutionService(scheduler.settings, scheduler._mt5, dry_run=getattr(scheduler, 'dry_run', False))
            equity = None
            try:
                account = await scheduler._mt5.get_account_info()
                if account and account.get('equity', 0) > 0:
                    equity = account.get('equity')
                else:
                    logger.error('MT5 returned zero or null equity. Auto-execute BLOCKED this cycle.')
                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_warning('⚠️ <b>Auto-Execute BLOCKED</b>\nMT5 could not verify account equity.')
                    except Exception: pass
                    summary['execution'] = {'status': 'blocked_no_equity_data', 'count': 0}
                    return {"summary": summary}
            except Exception as e:
                logger.error(f'Could not get account equity for auto-execute: {e}.')
                summary['execution'] = {'status': 'blocked_equity_error', 'error': str(e)}
                return {"summary": summary}

            exec_results = {}
            for sym, r in actionable:
                analysis_id = r["analysis_id"]
                raw_conf = r.get("confidence", 0)
                from utils.calibration.confidence_calibrator import get_calibrated_confidence
                async with get_session() as cal_session:
                    calibrated_conf = await get_calibrated_confidence(
                        cal_session, raw_conf, regime=r.get("market_regime") or r.get("regime")
                    )
                effective_min = min_confidence - 0.03
                if calibrated_conf < effective_min:
                    logger.info(f"Execution for {sym} skipped: calibrated confidence {calibrated_conf:.2f} < {effective_min:.2f} (base: {min_confidence:.2f})")
                    exec_results[sym] = "skipped_low_confidence"
                    continue
                    

                async with get_session() as check_session:
                    sym_stats = await scheduler._get_symbol_paper_stats(check_session, sym)
                
                from analysis.memory.decision_log import DecisionLogger
                
                if sym_stats.get('blocked'):
                    logger.warning(f"Auto-execute blocked for {sym}: symbol WR < 35%")
                    exec_results[sym] = f"blocked_symbol_wr_{sym_stats.get('win_rate', 0):.0f}pct"
                    async with get_session() as session:
                        await DecisionLogger.log_paper_whatif(session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0), None, "Blocked by symbol WR", "execution_node_blocked")
                    continue
                    
                max_execute_age_minutes = scheduler.settings.get('execution', {}).get('max_analysis_age_for_execute_minutes', 20)
                
                async with get_session() as session:
                    from database.models import AssetAnalysis
                    ana = (await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))).scalar_one_or_none()
                    
                    if ana:
                        if scheduler.settings.get('adversarial_check', {}).get('enabled', True):
                            from database.models import SystemConfig
                            import json
                            cached = (await session.execute(
                                select(SystemConfig).where(SystemConfig.key == f'adversarial_outcome_{analysis_id}')
                            )).scalar_one_or_none()
                            
                            if cached and cached.value:
                                try:
                                    adversarial_result = json.loads(cached.value)
                                    if adversarial_result.get('hard_block'):
                                        logger.warning(
                                            f"[AdversarialCheck] HARD BLOCK {sym} (cached): {adversarial_result.get('hard_block_reason', 'unknown')}"
                                        )
                                        exec_results[sym] = f"hard_blocked_adversarial_cached"
                                        continue
                                        
                                    alert_on_extreme_cfg = (await session.execute(
                                        select(SystemConfig).where(SystemConfig.key == 'adversarial_alert_on_extreme_only_override')
                                    )).scalar_one_or_none()
                                    alert_on_extreme = (alert_on_extreme_cfg.value == 'true') if alert_on_extreme_cfg else \
                                        scheduler.settings.get('adversarial_check', {}).get('alert_on_extreme_only', True)
                                        
                                    if adversarial_result.get('recommend_block'):
                                        if not alert_on_extreme or adversarial_result.get('quality') == 'low':
                                            logger.warning(f"[AdversarialCheck] Blocking {sym} (cached): {adversarial_result.get('block_reason', 'unknown')}")
                                            exec_results[sym] = f"blocked_adversarial_cached"
                                            continue
                                except Exception as e:
                                    logger.debug(f"Failed to read cached adversarial check: {e}")
                                
                        if ana.execution_status == 'rejected':
                            exec_results[sym] = "rejected_by_admin"
                            await DecisionLogger.log_paper_whatif(
                                session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0),
                                None, "Rejected by admin", "admin_reject",
                                context_snapshot_id=ana.context_snapshot_id, ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                            )
                            continue
                            
                        if ana.generated_at:
                            gen_at = ana.generated_at.replace(tzinfo=timezone.utc) if ana.generated_at.tzinfo is None else ana.generated_at
                            age_minutes = (clock.now() - gen_at).total_seconds() / 60
                            if age_minutes > max_execute_age_minutes:
                                exec_results[sym] = f'skipped_stale_analysis_{age_minutes:.0f}min'
                                await DecisionLogger.log_paper_whatif(
                                    session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0),
                                    None, "Analysis stale", "stale_analysis",
                                    context_snapshot_id=ana.context_snapshot_id, ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                                )
                                continue
                                
                        cs = ana.confluence_score
                        if cs is None:
                            exec_results[sym] = "blocked_missing_confluence_score"
                            await DecisionLogger.log_paper_whatif(
                                session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0),
                                None, "Missing confluence", "no_confluence",
                                context_snapshot_id=ana.context_snapshot_id, ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                            )
                            continue
                        if cs < min_confluence:
                            exec_results[sym] = f"skipped_low_confluence_{cs}"
                            await DecisionLogger.log_paper_whatif(
                                session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0),
                                cs, "Low confluence", "low_confluence",
                                context_snapshot_id=ana.context_snapshot_id, ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                            )
                            continue
                            
                        ps = ana.priced_in_score
                        if ps is not None and ps >= 8:
                            exec_results[sym] = "blocked_priced_in_too_high"
                            await DecisionLogger.log_paper_whatif(
                                session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0),
                                cs, "Priced in too high", "priced_in",
                                context_snapshot_id=ana.context_snapshot_id, ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                            )
                            continue

                        # Phase 7: Pre-Execution Market Replay & Slippage Simulation Sandbox
                        try:
                            from risk.execution_simulator import ExecutionSimulator
                            simulator = ExecutionSimulator(scheduler.settings, mt5_client=scheduler._mt5)
                            entry_p = float(ana.entry_price or ana.price_at_analysis or r.get("entry_price") or 0.0)
                            sl_p = float(ana.stop_loss or r.get("stop_loss") or 0.0)
                            tp_p = float(ana.take_profit or r.get("take_profit") or 0.0)
                            direction_str = str(ana.decision or r.get("decision") or "buy")

                            if entry_p > 0 and sl_p > 0 and tp_p > 0:
                                sim_result = await simulator.simulate_execution(
                                    symbol=sym,
                                    direction=direction_str,
                                    entry_price=entry_p,
                                    stop_loss=sl_p,
                                    take_profit=tp_p,
                                    session=session
                                )

                                if not sim_result.resilient:
                                    logger.warning(
                                        f"[SlippageSandbox] Execution for {sym} blocked: {sim_result.rejection_reason}"
                                    )
                                    exec_results[sym] = "blocked_slippage_drag"
                                    ana.execution_status = "rejected"
                                    ana.execution_notes = sim_result.rejection_reason
                                    await DecisionLogger.log_paper_whatif(
                                        session, analysis_id, sym, r.get("decision", "wait"), r.get("confidence", 0),
                                        cs, f"Slippage drag: {sim_result.rejection_reason}", "slippage_drag",
                                        context_snapshot_id=ana.context_snapshot_id, ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                                    )
                                    await session.commit()
                                    continue
                        except Exception as sim_err:
                            logger.error(f"[SlippageSandbox] Simulation check error for {sym}: {sim_err}")

                        try:
                            result = await exec_svc.execute_analysis(session, ana, equity)
                            exec_results[sym] = result.summary() if hasattr(result, "summary") else str(result)
                            logger.info(f"Execution for {sym}: {exec_results[sym]}")
                            
                            # TAMBAHKAN: Update status di DB agar tidak diulang
                            if hasattr(result, 'executed'):
                                if result.executed:
                                    ana.execution_status = 'executed'
                                elif not getattr(result, 'risk_approved', False):
                                    ana.execution_status = 'rejected'
                                else:
                                    ana.execution_status = 'failed' # MT5 Error
                            else:
                                ana.execution_status = 'failed'
                        except Exception as e:
                            logger.error(f"Execution failed for {sym}: {e}")
                            exec_results[sym] = f"error: {str(e)[:100]}"
                            try:
                                await session.rollback()
                                ana = (await session.execute(
                                    select(AssetAnalysis).where(AssetAnalysis.id == analysis_id)
                                )).scalar_one_or_none()
                                if ana:
                                    ana.execution_status = 'failed'
                            except Exception as rb_err:
                                logger.debug(f"Rollback failed: {rb_err}")
                            
                        await session.commit()
                    else:
                        logger.warning(f"Analysis {analysis_id} not found for execution")
                        
            summary["execution"] = exec_results

    # Hitung API Cost
    try:
        from utils.analytics.cost_tracker import CostTracker
        stage1_in = summary.get("fundamental", {}).get("input_tokens", 0)
        stage1_out = summary.get("fundamental", {}).get("output_tokens", 0)
        stage2_in = sum(r.get("input_tokens", 0) for r in summary.get("per_asset", {}).values() if isinstance(r, dict))
        stage2_out = sum(r.get("output_tokens", 0) for r in summary.get("per_asset", {}).values() if isinstance(r, dict))
        cycle_id_val = state.get("cycle_id")
        
        async with get_session() as session:
            cost_usd = await CostTracker.log_cycle_cost(
                session, stage1_in, stage1_out, stage2_in, stage2_out, settings=scheduler.settings, cycle_id=cycle_id_val
            )
            summary["api_cost_usd"] = cost_usd
    except Exception as e:
        logger.error(f"Failed to calculate cycle cost: {e}")

    return {"summary": summary}
