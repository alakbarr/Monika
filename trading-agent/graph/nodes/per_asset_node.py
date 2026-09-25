import logging
import utils.clock as clock
from typing import Dict, Any, Optional
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session

logger = logging.getLogger("TradingAgent.Graph.PerAssetNode")

async def per_asset_analysis_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node untuk menjalankan analisis teknikal dan sentimen per aset (Stage 2).
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    summary = state.get("summary", {})
    stale_assets = state.get("stale_assets", [])
    weekend_symbols_override = state.get("weekend_symbols_override")

    if scheduler is None:
        logger.error("Scheduler not found in config")
        return {"summary": summary, "asset_analyses": {}, "actionable_trades": []}
    
    logger.info("[Step 7/7] Running Per-Asset Stage (Stage 2 — Per-Asset Analysis)...")
    
    async with get_session() as session:
        await scheduler._paper_tracker.check_and_suspend_poor_performers(session, scheduler.settings)
        suspended_symbols = await scheduler._paper_tracker.get_suspended_symbols(session)

    now = clock.now()
    hour = now.hour
    weekday = now.weekday()
    
    trading_cfg = scheduler.settings.get('trading', {})
    start_hr = trading_cfg.get('auto_execute_active_hours_utc_start', 6)
    end_hr = trading_cfg.get('auto_execute_active_hours_utc_end', 22)
    auto_execute = trading_cfg.get('auto_execute', False)
    
    is_outside_active_hours = not (start_hr <= hour < end_hr)
    is_weekday = weekday < 5
    
    symbols_override = weekend_symbols_override or scheduler.asset_universe
    
    if auto_execute and is_outside_active_hours and is_weekday:
        from database.db import get_session as _gs_pos
        from database.models import Position
        from sqlalchemy import select, func
        async with _gs_pos() as session:
            open_count = (await session.execute(
                select(func.count(Position.id)).where(Position.status == 'open')
            )).scalar_one_or_none() or 0
        
        # Check Asian session assets (Tokyo 00:00 - 09:00 UTC) and 24/7 crypto
        ASIA_SESSION_SYMBOLS = {"USDJPY", "AUDUSD", "NZDUSD", "AUDJPY", "BTCUSD", "ETHUSD"}
        is_asian_session = (0 <= hour < 9)
        asian_crypto_eligible = [
            s for s in symbols_override 
            if (s in ASIA_SESSION_SYMBOLS and (is_asian_session or "BTC" in s or "ETH" in s))
        ]
        
        if asian_crypto_eligible:
            open_symbols = []
            if open_count > 0:
                async with _gs_pos() as session:
                    open_symbols = list(set([p.symbol for p in (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()]))
            symbols_override = list(set(asian_crypto_eligible + open_symbols))
            logger.info(f'[PerAsset] Active hours gate: Asian/Crypto session assets eligible ({symbols_override}). Proceeding with analysis.')
        elif open_count == 0:
            logger.info(f'[PerAsset] Skipping full Stage 2: outside active hours ({hour}:00 UTC, window={start_hr}-{end_hr}) and no open positions. Token saved: ~7 AI calls.')
            summary['per_asset'] = {'skipped': True, 'reason': 'outside_active_hours_no_positions', 'next_active_hour': start_hr}
            return {'summary': summary, 'asset_analyses': {}, 'actionable_trades': []}
        else:
            logger.info(f'[PerAsset] Outside active hours but {open_count} open positions. Running limited analysis for position management only.')
            async with _gs_pos() as session:
                open_symbols = list(set([p.symbol for p in (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()]))
            symbols_override = [s for s in symbols_override if s in open_symbols]

    symbols_to_analyze_fresh = [s for s in symbols_override if s not in stale_assets]
    paper_cfg = scheduler.settings.get('trading', {}).get('paper_trading', {})
    streak_policy = paper_cfg.get('streak_loss_policy', 'warn_and_scale')
    is_auto_execute = scheduler.settings.get('trading', {}).get('auto_execute', False)

    if not is_auto_execute and streak_policy in ('disabled', 'warn_and_scale'):
        symbols_to_analyze = symbols_to_analyze_fresh
        if suspended_symbols:
            logger.info(f"[PerAsset] Symbols currently marked suspended: {suspended_symbols}, but analyzing anyway due to streak_loss_policy='{streak_policy}'.")
    else:
        symbols_to_analyze = [s for s in symbols_to_analyze_fresh if s not in suspended_symbols]
        if suspended_symbols:
            logger.warning(f"Skipping suspended symbols in Stage 2: {suspended_symbols}")
        
    from database.db import get_session as _gs
    
    per_symbol_contexts = state.get('ssvp_per_symbol_contexts', {})
    ssvp_context = state.get('ssvp_reconciliation_context', '')
    if ssvp_context or per_symbol_contexts:
        logger.info(f"[SSVP] Injecting reconciliation context into {len(symbols_to_analyze)} Stage 2 analyses")

    pa_results = await scheduler._per_asset.run_all(
        session_factory=_gs,
        symbols=symbols_to_analyze,
        extra_context=f"Market Regime: {state.get('market_regime', 'normal')}",
        per_symbol_contexts=per_symbol_contexts,
        user_market_intel=state.get('user_market_intel'),
    )
    
    # ============================================================
    # SSVP: CROSS-AGENT SELECTIVE SYNCHRONIZATION
    # Detects contradictions and suppresses ONLY the lower-confidence
    # agent, rather than broadcasting a "winner's" belief (anti-contamination).
    # ============================================================
    try:
        from utils.protocol.ssvp_coordinator import SSVPCoordinator
        ssvp = SSVPCoordinator(settings=scheduler.settings)
        async with get_session() as ssvp_session:
            updated_pa_results, suppressed_symbols = await ssvp.compute_post_stage2_sync(
                ssvp_session, pa_results
            )
            
            if suppressed_symbols:
                logger.warning(f'[SSVP] Applied selective suppression to: {suppressed_symbols}')
                summary['ssvp_suppressed_symbols'] = suppressed_symbols
                summary['contradiction_filter_applied'] = True
                
            pa_results = updated_pa_results
    except Exception as ssvp_sync_err:
        logger.debug(f'SSVP Cross-agent sync failed (non-fatal): {ssvp_sync_err}')
    # ============================================================

    # Ingest Ad-Hoc Investigation Verdicts from sidecar subagents
    try:
        from analysis.subagent.adhoc_manager import get_adhoc_manager
        adhoc_mgr = get_adhoc_manager(settings=scheduler.settings)
        adhoc_verdicts = {}
        for sym, r in pa_results.items():
            verdict = adhoc_mgr.get_latest_verdict(sym)
            if verdict:
                adhoc_verdicts[sym] = verdict.to_dict()
                r["adhoc_investigation"] = verdict.to_dict()
                if verdict.anomaly_detected:
                    logger.warning(f"[PerAsset] Ad-hoc anomaly detected for {sym}: {verdict.findings} (rec={verdict.recommendation})")
                    if verdict.recommendation in ("halt", "avoid"):
                        r["decision"] = "skip"
                        r["rationale"] = f"[AdHoc Anomaly Halt] {verdict.findings}"
                    elif verdict.recommendation == "reduce_risk":
                        r["risk_multiplier"] = min(float(r.get("risk_multiplier", 1.0) or 1.0), 0.5)
        if adhoc_verdicts:
            summary["adhoc_verdicts"] = adhoc_verdicts
    except Exception as adhoc_err:
        logger.debug(f"[PerAsset] Ad-hoc verdict ingestion note: {adhoc_err}")

    # TAMBAHKAN: Track dan notifikasi untuk failed analyses
    failed_symbols = []
    error_symbols = []
    
    for sym, r in pa_results.items():
        if r.get('decision') == 'error' or not r.get('success', True):
            error_symbols.append({
                'symbol': sym,
                'error': r.get('error', 'unknown'),
                'elapsed': r.get('elapsed_seconds', 0)
            })
        elif r.get('decision') == 'skip' and not r.get('skipped_by_cooldown'):
            # Skipped bukan karena cooldown (unexpected)
            failed_symbols.append(sym)
    
    if error_symbols:
        error_detail = ', '.join([f"{e['symbol']}({e['error'][:30]})" for e in error_symbols])
        logger.error(f'Stage 2 errors for: {error_detail}')
        summary['per_asset_errors'] = error_symbols
        
        # Notifikasi jika ada error yang tidak expected
        unexpected_errors = [e for e in error_symbols 
                           if 'timeout' not in e.get('error', '').lower()]
        if unexpected_errors and len(unexpected_errors) >= 2:
            try:
                from utils.infra.notifier import AgentNotifier
                await AgentNotifier().send_warning(
                    f'⚠️ <b>Analysis Errors</b>\n'
                    f'{len(unexpected_errors)} symbols had unexpected errors:\n'
                    + '\n'.join([f"• {e['symbol']}: {e['error'][:80]}" 
                                for e in unexpected_errors[:3]])
                )
            except Exception:
                pass
    
    # Store failed analyses untuk potential retry next cycle
    if error_symbols:
        try:
            from database.db import get_session as _gs2
            from database.models import SystemConfig
            from sqlalchemy import select
            import json as _j
            async with _gs2() as cfg_session:
                failed_key = 'last_cycle_failed_analyses'
                failed_data = _j.dumps({
                    'cycle_at': clock.now().isoformat(),
                    'failed': error_symbols
                })
                cfg = (await cfg_session.execute(
                    select(SystemConfig).where(SystemConfig.key == failed_key)
                )).scalar_one_or_none()
                if cfg:
                    cfg.value = failed_data
                else:
                    cfg_session.add(SystemConfig(key=failed_key, value=failed_data))
                await cfg_session.commit()
        except Exception:
            pass
    
    summary["per_asset"] = {
        sym: {
            "decision": r.get("decision"),
            "confidence": r.get("confidence"),
            "analysis_id": r.get("analysis_id"),
            "elapsed_s": r.get("elapsed_seconds"),
            "input_tokens": r.get("input_tokens", 0),
            "output_tokens": r.get("output_tokens", 0),
            "skipped_by_cooldown": r.get("skipped_by_cooldown", False),
            "skipped_by_prescreen": r.get("skipped_by_prescreen", False),
            "skipped_by_data_quality": r.get("skipped_by_data_quality", False),
            "skipped_by_weekend_guard": r.get("skipped_by_weekend_guard", False),
            "skipped_by_brief_staleness": r.get("skipped_by_brief_staleness", False),
            "skipped_no_brief": r.get("skipped_no_brief", False),
            "error": r.get("error"),
            "rationale": r.get("rationale"),
        }
        for sym, r in pa_results.items()
    }
    
    actionable = [
        (sym, r) for sym, r in pa_results.items()
        if r.get("decision") in ("buy", "sell") and r.get("analysis_id")
    ]
    
    # Context Version Split Detection (P1-B)
    try:
        from utils.protocol.context_snapshot import detect_context_version_split
        from datetime import timedelta
        # P3-2: Use actual elapsed time from state if available, fallback to 1h
        elapsed_s = float(state.get('summary', {}).get('elapsed_total_s') or 3600.0)
        cycle_start = clock.now() - timedelta(seconds=elapsed_s)
        
        from database.db import get_session as _gs_snap
        async with _gs_snap() as snap_session:
            split_warning = await detect_context_version_split(snap_session, cycle_start)
        
        if split_warning:
            logger.warning(f'[ContextSplit] {split_warning}')
            summary['context_version_split_detected'] = True
            summary['context_version_split_detail'] = split_warning
            
            # Add warning to all actionable trades from this cycle
            if actionable:
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_warning(
                        f'⚠️ <b>Context Version Split</b>\n{split_warning}\n'
                        f'Actionable trades this cycle: {[sym for sym, _ in actionable]}\n'
                        f'Recommend manual review before execution.'
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f'Context split detection failed (non-fatal): {e}')

    return {
        "summary": summary,
        "asset_analyses": pa_results,
        "actionable_trades": actionable
    }
