import logging
import asyncio
from typing import Dict, Any, Optional
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session

logger = logging.getLogger("TradingAgent.Graph.FundamentalNode")

async def fundamental_analysis_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node untuk menjalankan analisis fundamental (Stage 1).
    Memanggil LLM client untuk membuat narasi makro.
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    forced = configurable.get("forced", False) if isinstance(configurable, dict) else False
    summary = state.get("summary", {})

    if scheduler is None:
        logger.error("Scheduler not found in config")
        return {"summary": summary, "should_pause": True}
    
    # Cek Smart Skip
    should_skip, skip_reason = await scheduler._should_skip_full_cycle()
    if should_skip:
        logger.info(f"[Optimization] Full cycle skipped: {skip_reason}")
        summary["skipped_reason"] = skip_reason
        async with get_session() as session:
            await scheduler._log(session, f"Smart skip: {skip_reason}")
        return {"summary": summary, "should_pause": True}
        
    weekend_symbols_override = state.get("weekend_symbols_override")
    is_weekend_restricted = (weekend_symbols_override is not None and len(weekend_symbols_override) > 0)
    
    fund_result = None
    last_error = None
    max_attempts = 1
    
    if is_weekend_restricted:
        logger.info("[Step 6/7] Weekend mode: running abbreviated Stage 1 (crypto-focused)...")
    else:
        logger.info("[Step 6/7] Running Fundamental Stage (Stage 1 — Fundamental Analysis)...")
        
    for attempt in range(max_attempts):
        if attempt > 0:
            # Exponential backoff: 30s, 60s
            wait_time = 30 * attempt
            logger.warning(f'Stage 1 attempt {attempt + 1}/{max_attempts}, waiting {wait_time}s...')
            await asyncio.sleep(wait_time)
        
        try:
            async with get_session() as session:
                fund_result = await scheduler._fundamental.run(
                    session, forced=forced, 
                    weekend_btc_only_mode=is_weekend_restricted,
                    user_market_intel=state.get("user_market_intel"),
                )
        except Exception as e:
            last_error = str(e)
            logger.error(f'Stage 1 attempt {attempt + 1} exception: {e}')
            
            # Classify error - permanent errors tidak perlu retry
            PERMANENT_PATTERNS = ['AuthenticationError', 'invalid_api_key', 'API key', 
                                   'Invalid model', 'model_not_found']
            if any(p in str(e) for p in PERMANENT_PATTERNS):
                logger.critical(f'Permanent error in Stage 1, stopping retry: {e}')
                fund_result = {'success': False, 'error': str(e), '_permanent': True}
                break
            continue
        
        if fund_result and fund_result.get('success'):
            break
            
    fund_result = fund_result or {}
                
    summary["fundamental"] = {
        "success": fund_result.get("success", False),
        "brief_id": fund_result.get("brief_id"),
        "tool_calls": fund_result.get("tool_calls_made", 0),
        "elapsed_s": fund_result.get("elapsed_seconds", 0.0),
        "input_tokens": fund_result.get("input_tokens", 0),
        "output_tokens": fund_result.get("output_tokens", 0),
    }

    if not fund_result.get("success"):
        scheduler._stage1_consecutive_failures += 1
        logger.error(f"Fundamental Stage failed — skipping per-asset stage (failures: {scheduler._stage1_consecutive_failures})")
        if scheduler._stage1_consecutive_failures >= scheduler._max_stage1_failures_before_alert:
            try:
                from utils.infra.notifier import AgentNotifier
                await AgentNotifier().send_critical(
                    f"🔴 <b>Stage 1 Consecutive Failures: {scheduler._stage1_consecutive_failures}</b>\n"
                    f"Last error: {fund_result.get('error', 'unknown')[:200]}"
                )
            except Exception as notif_err:
                logger.error(f"Failed to send Stage 1 critical alert: {notif_err}")
        
        summary["per_asset"] = {"skipped": True, "reason": "fundamental_failed"}
        
        try:
            from utils.analytics.cost_tracker import CostTracker
            cycle_id_val = state.get("cycle_id")
            s1_in = int(summary.get("fundamental", {}).get("input_tokens", 0) or 0)
            s1_out = int(summary.get("fundamental", {}).get("output_tokens", 0) or 0)
            async with get_session() as session:
                cost_usd = await CostTracker.log_cycle_cost(
                    session, s1_in, s1_out,
                    0, 0, settings=scheduler.settings, cycle_id=cycle_id_val,
                )
                summary["api_cost_usd"] = cost_usd
        except Exception as e:
            logger.error(f"Failed to log cycle cost on stage 1 fail: {e}")
            
        retry_count = state.get("fundamental_retry_count", 0) + 1
        
        if fund_result and fund_result.get('_permanent'):
            return {
                'summary': summary,
                'node_errors': {'fundamental': fund_result.get('error', 'permanent_error')},
                'should_pause': True,
                'fundamental_retry_count': 99  # Prevent any further retry
            }
            
        return {
            "summary": summary,
            "node_errors": {"fundamental": fund_result.get("error", "unknown") if fund_result else last_error},
            "should_pause": True,
            "fundamental_retry_count": retry_count
        }
    else:
        scheduler._stage1_consecutive_failures = 0
        
        # --- FUNDAMENTAL NARRATIVE SHIFT DETECTION ---
        try:
            from database.models import FundamentalBrief, Position
            from sqlalchemy import select
            import json
            
            async with get_session() as session:
                new_brief = (await session.execute(
                    select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                )).scalar_one_or_none()
                
                prev_brief = (await session.execute(
                    select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).offset(1).limit(1)
                )).scalar_one_or_none()
                
                if new_brief and prev_brief and new_brief.structured_json and prev_brief.structured_json:
                    new_bias = json.loads(new_brief.structured_json).get('currency_bias', {})
                    prev_bias = json.loads(prev_brief.structured_json).get('currency_bias', {})
                    
                    reversals = {}
                    for currency in ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'XAU', 'XTI', 'XBR', 'BTC']:
                        raw_new = new_bias.get(currency)
                        if raw_new is None and currency in ('XTI', 'XBR'):
                            raw_new = new_bias.get('OIL')
                        raw_prev = prev_bias.get(currency)
                        if raw_prev is None and currency in ('XTI', 'XBR'):
                            raw_prev = prev_bias.get('OIL')
                        new_b = normalize_bias(raw_new or 'neutral')
                        prev_b = normalize_bias(raw_prev or 'neutral')
                        if (new_b == 'bullish' and prev_b == 'bearish') or (new_b == 'bearish' and prev_b == 'bullish'):
                            reversals[currency] = {'from': prev_b, 'to': new_b}
                    
                    if reversals:
                        POSITION_CURRENCIES = {
                            'EURUSD': ['EUR', 'USD'], 'GBPUSD': ['GBP', 'USD'],
                            'USDJPY': ['USD', 'JPY'], 'AUDUSD': ['AUD', 'USD'],
                            'XAUUSD': ['XAU', 'USD'], 'XTIUSD': ['XTI', 'USD'],
                            'XBRUSD': ['XBR', 'USD'], 'BTCUSD': ['BTC', 'USD']
                        }
                        
                        open_positions = (await session.execute(
                            select(Position).where(Position.status == 'open')
                        )).scalars().all()
                        
                        affected_positions = []
                        for pos in open_positions:
                            currencies = POSITION_CURRENCIES.get(pos.symbol, [])
                            for curr in currencies:
                                if curr in reversals:
                                    reversal = reversals[curr]
                                    is_problematic = False
                                    if pos.direction == 'buy':
                                        base, quote = (currencies[0], currencies[1]) if len(currencies) == 2 else (None, None)
                                        if base == curr and reversal['to'] == 'bearish': is_problematic = True
                                        elif quote == curr and reversal['to'] == 'bullish': is_problematic = True
                                    elif pos.direction == 'sell':
                                        base, quote = (currencies[0], currencies[1]) if len(currencies) == 2 else (None, None)
                                        if base == curr and reversal['to'] == 'bullish': is_problematic = True
                                        elif quote == curr and reversal['to'] == 'bearish': is_problematic = True
                                    
                                    if is_problematic:
                                        affected_positions.append({
                                            'symbol': pos.symbol, 'direction': pos.direction,
                                            'ticket': pos.mt5_ticket,
                                            'reason': f'{curr} bias reversed: {reversal["from"]} → {reversal["to"]}'
                                        })
                                        break
                        
                        if affected_positions:
                            summary['fundamental_shift_alert'] = {'reversals': reversals, 'affected_positions': affected_positions}
                            alert_lines = ['⚠️ <b>FUNDAMENTAL NARRATIVE SHIFT DETECTED</b>\n']
                            for curr, rev in reversals.items():
                                alert_lines.append(f'• {curr}: {rev["from"]} → <b>{rev["to"]}</b>')
                            alert_lines.append('\n<b>Positions at risk:</b>')
                            for pos in affected_positions:
                                alert_lines.append(f'• {pos["symbol"]} {pos["direction"].upper()} (ticket {pos["ticket"]}): {pos["reason"]}')
                            alert_lines.append('\nConsider reviewing these positions manually.')
                            from utils.infra.notifier import AgentNotifier
                            await AgentNotifier().send_warning('\n'.join(alert_lines))
                            logger.warning(f'Fundamental shift detected affecting {len(affected_positions)} positions')
        except Exception as e:
            logger.debug(f'Fundamental shift detection failed (non-fatal): {e}')
        
        # SSVP: Verify context coherence after Stage 1 completes
        from utils.protocol.ssvp_coordinator import SSVPCoordinator
        from database.models import FundamentalBrief
        from sqlalchemy import select
        
        ssvp = SSVPCoordinator(settings=scheduler.settings)
        async with get_session() as ssvp_session:
            should_proceed, cds_score, ssvp_msg = await ssvp.check_pre_stage2_sync(
                ssvp_session, scheduler.settings
            )
            
            # Hitung per-symbol context dan ekstrak regime/vix/confidence untuk downstream nodes
            brief = (await ssvp_session.execute(
                select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
            )).scalar_one_or_none()
            
            per_symbol_contexts = {}
            market_regime = "unknown"
            vix_level = None
            brief_confidence = None
            if brief:
                brief_confidence = brief.confidence
                if brief.risk_sentiment:
                    market_regime = brief.risk_sentiment
                if brief.structured_json:
                    try:
                        import json
                        brief_data = json.loads(brief.structured_json)
                        market_regime = brief_data.get("macro_regime") or brief_data.get("risk_sentiment") or market_regime
                        vix_level = brief_data.get("vix_level") or (brief_data.get("key_data_points_used") or {}).get("vix_close")
                        if brief_confidence is None:
                            brief_confidence = brief_data.get("confidence")
                        per_symbol_contexts = await ssvp.compute_per_symbol_contexts(
                            ssvp_session, brief_data, scheduler.asset_universe
                        )
                    except Exception as e:
                        logger.debug(f'Per-symbol context computation failed (non-fatal): {e}')
        
        summary['ssvp_cds_score'] = cds_score
        summary['ssvp_message'] = ssvp_msg
        
        if not should_proceed and state.get('ssvp_retry_count', 0) < 1:
            # CDS terlalu tinggi setelah Stage 1 fresh run — tanda masalah data bukan brief
            logger.error(f"[SSVP] CDS={cds_score:.2f} masih tinggi setelah Stage 1 fresh. Market data mungkin inconsistent.")
            # Proceed dengan warning, jangan loop infinite
            summary['ssvp_warning'] = f"CDS high post-fresh-brief: {ssvp_msg}"
        
        # Store reconciliation context untuk Stage 2
        ssvp_context = ''
        summary['ssvp_reconciliation_context'] = ssvp_context
        
        return {
            'summary': summary,
            'market_regime': str(market_regime),
            'vix_level': vix_level,
            'brief_confidence': brief_confidence,
            'ssvp_per_symbol_contexts': per_symbol_contexts,
            'ssvp_blocked': (not should_proceed) and state.get('ssvp_retry_count', 0) < 1,
            'ssvp_retry_count': state.get('ssvp_retry_count', 0) + 1,
            'ssvp_cds_score': cds_score,
            'ssvp_reconciliation_context': ssvp_context,
            'should_pause': False,
            'fundamental_retry_count': 0
        }
