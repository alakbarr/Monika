import logging
from typing import Dict, Any, Optional
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from datetime import datetime, timezone, timedelta
import utils.clock as clock

logger = logging.getLogger("TradingAgent.Graph.DataNode")

async def fetch_data_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node untuk mengambil dan memvalidasi semua data (Scraping, MT5, Indikator).
    Mereplikasi Step 1-5 dari cycle_scheduler.py
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    summary = state.get("summary", {})
    is_ad_hoc = bool(configurable.get("is_ad_hoc") or summary.get("is_ad_hoc"))

    if scheduler is None:
        if is_ad_hoc:
            logger.info("Scheduler not found in config for ad-hoc pipeline, initializing AdHocSchedulerProxy fallback.")
            from agent.agent_loop import AdHocSchedulerProxy
            scheduler = AdHocSchedulerProxy(
                settings=configurable.get("settings"),
                symbols=list(state.get("symbols") or [s for s, _ in state.get("actionable_trades", [])] or ["XAUUSD"]),
            )
        else:
            logger.error("Scheduler instance not found in config['configurable']['scheduler']")
            return {"summary": summary, "should_pause": True, "stale_assets": []}
    
    # Step 1: Eksekusi scrapers (Scraping berat sekarang dilakukan di latar belakang setiap 1 jam via main.py)
    logger.info("[Step 1/7] Scraping is handled in background loop. Skipping in graph cycle.")
    try:
        scraping_info: Dict[str, Any] = {"status": "moved to background loop"}
        summary["scraping"] = scraping_info
        from analysis.calculators.economic_surprise import compute_surprise_scores
        async with get_session() as session:
            updated = await compute_surprise_scores(session)
            if updated > 0:
                logger.info(f"Computed surprise scores for {updated} economic events")
                scraping_info["economic_surprise_updated"] = updated
                summary["scraping"] = scraping_info
    except Exception as e:
        logger.error(f"Scraper metrics update failed: {e}")
        summary["scraping"] = {"error": str(e)}

    # Cek freshness kalender
    try:
        from sqlalchemy import func, select as _sel
        from database.models import EconomicCalendar, SystemConfig
        async with get_session() as session:
            latest_cal = None
            now_curr = clock.now()
            cfg = (await session.execute(_sel(SystemConfig).where(SystemConfig.key == 'last_calendar_fetch_at'))).scalar_one_or_none()
            if cfg and cfg.value:
                try:
                    dt = datetime.fromisoformat(cfg.value)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    latest_cal = dt
                except Exception:
                    pass
            if latest_cal is None:
                max_fetched = (await session.execute(
                    _sel(func.max(EconomicCalendar.fetched_at)).where(EconomicCalendar.fetched_at <= now_curr)
                )).scalar_one_or_none()
                if max_fetched is not None:
                    latest_cal = max_fetched.replace(tzinfo=timezone.utc) if max_fetched.tzinfo is None else max_fetched

            if latest_cal is None:
                logger.error("CRITICAL: No calendar data in DB. Risk gate will block all trades.")
            else:
                cal_age = (now_curr - latest_cal).total_seconds() / 3600
                future_cov = (await session.execute(
                    _sel(EconomicCalendar.id)
                    .where(EconomicCalendar.event_time >= now_curr - timedelta(hours=1))
                    .where(EconomicCalendar.event_time <= now_curr + timedelta(hours=12))
                    .limit(1)
                )).scalar_one_or_none()

                if cal_age > 8 and future_cov is None:
                    logger.warning(f"Calendar data is {cal_age:.1f}h old with no future coverage — risk gate protection reduced")
                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_warning(
                            f"⚠️ Economic calendar data is {cal_age:.1f}h old with no upcoming events in DB.\n"
                            f"Calendar scrapers may have failed. Risk gate will block trades until calendar is refreshed."
                        )
                    except Exception as notif_err:
                        logger.warning(f"Failed to send calendar warning alert: {notif_err}")
                elif cal_age > 8:
                    logger.info(f"Calendar fetch is {cal_age:.1f}h old, but upcoming event coverage exists in DB.")
    except Exception as e:
        logger.debug(f"Calendar freshness check failed: {e}")

    # Step 1.5: LLM News Digest
    logger.info("[Step 1.5/7] Processing news with LLM...")
    try:
        from analysis.prefetch.news_digest import NewsDigestProcessor
        processor = NewsDigestProcessor(scheduler.settings)
        async with get_session() as session:
            classified = await processor.classify_unscored_news(session, hours_back=8)
            logger.info(f"LLM classified {classified} news items")
        async with get_session() as session:
            digest = await processor.create_news_digest(session, hours_back=12)
            if digest: logger.info("News digest created for Stage 1")

        # Health report and auto-tightening
        async with get_session() as session:
            from analysis.prefetch.news_digest import get_classification_health_report
            from database.models import SystemConfig
            from sqlalchemy import select
            health = await get_classification_health_report(session)
            if health.get('anomaly_alert'):
                logger.warning(f"News anomaly detected! Breaking rate={health.get('breaking_rate_pct')}%. Auto-tightening breaking threshold.")
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'news_auto_tighten'))).scalar_one_or_none()
                if cfg: cfg.value = "1"
                else: session.add(SystemConfig(key='news_auto_tighten', value="1"))
                await session.commit()
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_warning(f"⚠️ <b>News Classification Anomaly</b>\nHigh breaking rate detected: {health.get('breaking_rate_pct')}%. Auto-tightening activated.")
                except Exception as notif_err:
                    logger.warning(f"Failed to send news anomaly alert: {notif_err}")
            else:
                cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'news_auto_tighten'))).scalar_one_or_none()
                if cfg and cfg.value == "1":
                    cfg.value = "0"
                    await session.commit()
    except Exception as e:
        logger.warning(f"News processing failed (non-fatal): {e}")

    # Step 2: External API Refresh
    logger.info("[Step 2/7] Refreshing API data sources...")
    summary["data_refresh"] = await scheduler._refresh_data_sources()

    # Step 3: MT5 price fetch
    logger.info("[Step 3/7] Fetching MT5 price data...")
    if scheduler._mt5:
        try:
            async with get_session() as session:
                result = await scheduler._mt5.fetch_and_save_all(
                    session, symbols=scheduler.asset_universe,
                    timeframes=scheduler.mt5_timeframes, count=500,
                )
                summary["price_fetch"] = result
                
                # TAMBAHAN: Fetch M15 khusus untuk paper trade detection
                m15_result = await scheduler._mt5.fetch_and_save_all(
                    session,
                    symbols=scheduler.asset_universe,
                    timeframes=['M15'],
                    count=100
                )
                summary['price_fetch_m15'] = m15_result
                logger.debug(f'M15 price fetch for paper trade detection: {m15_result}')
            
            logger.debug(f"Price fetch: {result}")
        except Exception as e:
            logger.error(f"MT5 price fetch failed: {e}")
            summary["price_fetch"] = {"error": str(e)}
    else:
        logger.warning("MT5 client not available — skipping price fetch")
        summary["price_fetch"] = {"skipped": "no MT5 client"}

    # Step 4: Technical indicators
    logger.info("[Step 4/7] Computing technical indicators...")
    try:
        from indicators.technical import TechnicalIndicatorCalculator
        async with get_session() as session:
            calc = TechnicalIndicatorCalculator(session, scheduler.settings.get("trading", {}))
            indicator_timeframes = [tf for tf in scheduler.mt5_timeframes if tf != 'M15']
            ind_result = await calc.compute_all_symbols(scheduler.asset_universe, indicator_timeframes)
        summary["indicators"] = ind_result
        logger.debug(f"Indicators computed: {ind_result}")
    except Exception as e:
        logger.error(f"Indicator computation failed: {e}")
        summary["indicators"] = {"error": str(e)}

    # Step 5: Structure analysis
    logger.info("[Step 5/7] Analyzing market structure (swings, SR, FVG)...")
    try:
        from indicators.structure import MarketStructureAnalyzer
        async with get_session() as session:
            analyzer = MarketStructureAnalyzer(session, scheduler.settings)
            indicator_timeframes = [tf for tf in scheduler.mt5_timeframes if tf != 'M15']
            struct_result = await analyzer.analyze_all(scheduler.asset_universe, indicator_timeframes)
        summary["structure"] = {k: sum(v.values()) for k, v in struct_result.items()}
        logger.debug(f"Structure analysis complete: {summary['structure']}")
    except Exception as e:
        logger.error(f"Structure analysis failed: {e}")
        summary["structure"] = {"error": str(e)}

    # Step 5.5: Macro Precomputations
    logger.info("[Step 5.5/7] Running Macro pre-computations...")
    try:
        from analysis.prefetch.macro_preprocessor import MacroPreprocessor
        processor = MacroPreprocessor(settings=scheduler.settings)
        async with get_session() as session:
            await processor.run_all_and_save(session, scheduler.asset_universe, scheduler.mt5_timeframes)
        logger.info("Macro pre-computations completed successfully")
        summary["macro_precompute"] = "success"
    except Exception as e:
        logger.error(f"Macro pre-computations failed: {e}")
        summary["macro_precompute"] = {"error": str(e)}

    # Step 5.6: Regenerate Performance Notes
    logger.info("[Step 5.6/7] Checking if performance notes need regeneration...")
    try:
        async with get_session() as session:
            tracker = getattr(scheduler, "_paper_tracker", None)
            if tracker is not None:
                should_regen, reason = await tracker.should_regenerate_performance_notes(session)
            else:
                should_regen, reason = False, "no_paper_tracker"
            
            from utils.analytics.performance_reviewer import should_regenerate_fundamental_notes, generate_fundamental_performance_review
            should_regen_fund, fund_reason = await should_regenerate_fundamental_notes(session)
            if should_regen_fund and not should_regen:
                fund_content = await generate_fundamental_performance_review(session)
                if fund_content:
                    from database.models import SystemConfig
                    from sqlalchemy import select
                    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'fundamental_notes_last_gen'))).scalar_one_or_none()
                    now_iso = clock.now().isoformat()
                    if cfg: cfg.value = now_iso
                    else: session.add(SystemConfig(key='fundamental_notes_last_gen', value=now_iso))
                    await session.commit()
                    logger.info(f'Fundamental performance notes regenerated independently (Reason: {fund_reason})')
                    
            if should_regen:
                logger.info(f"Regenerating performance notes (Reason: {reason})")
                from utils.analytics.performance_reviewer import generate_weekly_review
                review_content = await generate_weekly_review(session, scheduler.settings)
                
                # Regenerate fundamental performance notes as well
                fund_content = await generate_fundamental_performance_review(session)
                
                if review_content:
                    from database.models import SystemConfig
                    from sqlalchemy import select
                    import json
                    last_gen_key = "performance_notes_last_gen"
                    stats = (await tracker.get_statistics(session)) if tracker is not None else {}
                    gen_data = {"timestamp": clock.now().isoformat(), "total_trades": stats.get("total_trades", 0), "reason": reason}
                    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == last_gen_key))).scalar_one_or_none()
                    if cfg: cfg.value = json.dumps(gen_data)
                    else: session.add(SystemConfig(key=last_gen_key, value=json.dumps(gen_data)))
                    await session.commit()
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_info(f"📊 <b>Performance Notes Regenerated</b>\nReason: {reason}\nUpdated in skills/trading/performance_notes.md and fundamental_performance_notes.md")
                summary["performance_notes"] = {"regenerated": True, "reason": reason}
            else:
                summary["performance_notes"] = {"regenerated": False, "reason": reason}
    except Exception as e:
        logger.error(f"Performance notes check failed: {e}")
        summary["performance_notes"] = {"error": str(e)}

    # Step 5.7: Score Inflation Detection
    logger.info("[Step 5.7/7] Running score inflation drift check (lightweight, every cycle)...")
    try:
        from utils.analytics.analysis_tracker import detect_score_inflation
        from database.models import SystemConfig
        from sqlalchemy import select as _sel_infl
        import json as _json_infl
        async with get_session() as session:
            inflation_data = await detect_score_inflation(session, days_back=14)
            if not inflation_data.get('insufficient_data') and inflation_data.get('alert'):
                direction = inflation_data.get('direction')
                drift = inflation_data.get('drift', 0)
                second_avg = inflation_data.get('second_half_avg_score', 0)
                if direction == 'INFLATING' and drift > 2.0:
                    correction_threshold = min(int(second_avg) - 1, 12)
                    cfg_key = 'score_inflation_correction_threshold'
                    cfg = (await session.execute(_sel_infl(SystemConfig).where(SystemConfig.key == cfg_key))).scalar_one_or_none()
                    correction_data = _json_infl.dumps({'threshold': correction_threshold, 'set_at': clock.now().isoformat(), 'drift': round(drift, 2), 'expires_days': 3})
                    if cfg:
                        cfg.value = correction_data
                    else:
                        session.add(SystemConfig(key=cfg_key, value=correction_data))
                    await session.commit()
                    logger.warning(f'[Step 5.7] Intra-cycle score inflation correction applied: threshold={correction_threshold} (drift={drift:.1f})')
    except Exception as e:
        logger.error(f"Score inflation detection failed: {e}")

    # Step 5.8: Factor Point Override Computation
    logger.info("[Step 5.8/7] Computing factor point overrides...")
    try:
        from utils.analytics.analysis_tracker import compute_and_persist_factor_point_overrides
        async with get_session() as session:
            await compute_and_persist_factor_point_overrides(session)
    except Exception as e:
        logger.error(f'Factor point override computation failed: {e}')

    # Validasi kesegaran data
    from utils.validation.data_validator import validate_data_freshness
    weekend_symbols_override = state.get("weekend_symbols_override")
    target_symbols = weekend_symbols_override if (weekend_symbols_override and len(weekend_symbols_override) > 0) else scheduler.asset_universe
    async with get_session() as session:
        data_quality_cfg = scheduler.settings.get("data_quality", {})
        validation = await validate_data_freshness(
            session, symbols=target_symbols, timeframes=scheduler.mt5_timeframes,
            max_ohlcv_age_hours=data_quality_cfg.get("max_ohlcv_age_hours", {}),
            max_indicator_age_hours=data_quality_cfg.get("max_indicator_age_hours", {}),
            max_macro_age_days=data_quality_cfg.get("max_macro_age_days", {}),
            max_calendar_age_hours=float(data_quality_cfg.get("block_analysis_if_calendar_stale_hours", 14.0)),
            max_news_age_hours=float(data_quality_cfg.get("max_news_age_hours", 24.0)),
            require_macro_data=bool(data_quality_cfg.get("require_macro_data", False)),
        )
        
    stale_assets = set()
    for err in validation.get("errors", []):
        for sym in target_symbols:
            if sym in err: stale_assets.add(sym)

    should_pause = False
    require_macro = bool(data_quality_cfg.get("require_macro_data", False))
    has_global_macro_error = require_macro and any(
        any(k in err.lower() for k in ("macro", "treasury", "cot", "dxy", "fedwatch", "calendar", "vix", "news"))
        for err in validation.get("errors", [])
    )

    if (len(stale_assets) >= len(target_symbols) and len(target_symbols) > 0) or has_global_macro_error:
        reason = "macro_data_stale" if has_global_macro_error else "all_data_stale"
        logger.error(f"Critical data freshness failure ({reason})! Skipping Stage 2. Errors: {validation['errors']}")
        try:
            from utils.infra.notifier import AgentNotifier
            await AgentNotifier().send_critical(
                f"🚨 <b>CRITICAL: Data Freshness Failure ({reason})!</b>\nStage 2 analysis SKIPPED this cycle.\n"
                f"Errors: {', '.join(validation['errors'][:3])}\nCheck MT5 connection and data fetching."
            )
        except Exception: pass
        summary["per_asset"] = {"skipped": True, "reason": reason}
        should_pause = True
        
    if validation["warnings"]:
        logger.warning(f"Data freshness warnings: {validation['warnings']}")
    summary["data_validation"] = validation

    # === VIX SYSTEM HALT CHECK ===
    try:
        from database.models import VIXData
        from sqlalchemy import select as _sel2
        async with get_session() as vix_check_session:
            vix_latest = (await vix_check_session.execute(
                _sel2(VIXData).order_by(VIXData.date.desc()).limit(1)
            )).scalar_one_or_none()
            
            if vix_latest:
                risk_cfg = scheduler.settings.get('trading', {}).get('risk', {})
                vix_pause_threshold = float(risk_cfg.get('vix_thresholds', {}).get('pause', 40.0))
                
                if vix_latest.close >= vix_pause_threshold:
                    logger.critical(
                        f'[VIX HALT] VIX={vix_latest.close:.1f} >= pause threshold {vix_pause_threshold}. '
                        f'Aborting cycle — no analysis will be performed.'
                    )
                    summary['vix_halt'] = {
                        'triggered': True, 
                        'vix': vix_latest.close, 
                        'threshold': vix_pause_threshold
                    }
                    try:
                        from utils.infra.notifier import AgentNotifier
                        await AgentNotifier().send_warning(
                            f'⚠️ <b>VIX System Halt</b>\n'
                            f'VIX={vix_latest.close:.1f} >= {vix_pause_threshold} (pause threshold)\n'
                            f'Full analysis cycle skipped. Trading blocked.\n'
                            f'Will retry next scheduled cycle.'
                        )
                    except Exception:
                        pass
                    return {
                        'summary': summary, 
                        'should_pause': True, 
                        'stale_assets': list(scheduler.asset_universe)
                    }
    except Exception as e:
        logger.error(f'VIX halt check failed (non-fatal, continuing): {e}')

    # === GLOBAL MACRO REGIME ASSESSMENT ===
    macro_regime = 'normal'
    macro_regime_reason = ''
    vix_latest_close = None

    try:
        from database.models import VIXData, DXYData
        from sqlalchemy import select as _sel3
        async with get_session() as session:
            vix_row = (await session.execute(
                _sel3(VIXData).order_by(VIXData.date.desc()).limit(1)
            )).scalar_one_or_none()
            
            if vix_row:
                vix_latest_close = vix_row.close
                if vix_row.close >= 35:
                    macro_regime = 'extreme_risk_off'
                    macro_regime_reason = f'VIX={vix_row.close:.1f} >= 35 (extreme fear)'
                elif vix_row.close >= 28:
                    macro_regime = 'risk_off'
                    macro_regime_reason = f'VIX={vix_row.close:.1f} >= 28 (elevated fear)'
                elif vix_row.close <= 12:
                    macro_regime = 'risk_on_complacent'
                    macro_regime_reason = f'VIX={vix_row.close:.1f} <= 12 (extreme complacency, reversal risk)'
            
            # DXY extreme movement check
            dxy_rows = (await session.execute(
                _sel3(DXYData).order_by(DXYData.date.desc()).limit(5)
            )).scalars().all()
            
            if len(dxy_rows) >= 5:
                dxy_5d_change = (dxy_rows[0].close - dxy_rows[4].close) / dxy_rows[4].close * 100
                if abs(dxy_5d_change) > 2.5:  # DXY moved > 2.5% in 5 days
                    if macro_regime == 'normal':
                        macro_regime = 'dxy_extreme_move'
                        macro_regime_reason = f'DXY moved {dxy_5d_change:+.1f}% in 5 days (unusual)'

        summary['macro_regime'] = {
            'regime': macro_regime,
            'reason': macro_regime_reason,
            'vix': vix_latest_close
        }

    except Exception as e:
        logger.debug(f'Macro regime assessment failed: {e}')

    # Fetch Active User Market Intelligence & Directives
    active_user_intel = []
    try:
        from database.models import UserMarketIntel
        from sqlalchemy import select as _sel_intel, or_ as _or_intel
        async with get_session() as session:
            now_intel = clock.now()
            stmt = (
                _sel_intel(UserMarketIntel)
                .where(
                    UserMarketIntel.is_active == True,
                    _or_intel(UserMarketIntel.expires_at.is_(None), UserMarketIntel.expires_at > now_intel),
                )
                .order_by(UserMarketIntel.created_at.desc())
            )
            intel_rows = (await session.execute(stmt)).scalars().all()
            for r in intel_rows:
                active_user_intel.append({
                    "id": r.id,
                    "intel_type": r.intel_type,
                    "title": r.title,
                    "summary": r.summary,
                    "full_content": r.full_content,
                    "affected_symbols": r.affected_symbols_list if hasattr(r, "affected_symbols_list") else (r.affected_symbols.split(",") if isinstance(r.affected_symbols, str) else (r.affected_symbols or [])),
                    "directive": r.directive,
                    "target_cycle": r.target_cycle,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "metadata": r.metadata_dict if hasattr(r, "metadata_dict") else (r.metadata_json or {}),
                })
        if active_user_intel:
            logger.info(f"Loaded {len(active_user_intel)} active user market intelligence items into cycle state")
    except Exception as intel_err:
        logger.warning(f"Failed to fetch user market intelligence: {intel_err}")

    if macro_regime == 'extreme_risk_off':
        logger.critical(f'MACRO REGIME: {macro_regime_reason}. All trading suspended.')
        return {
            'summary': summary,
            'should_pause': True,
            'stale_assets': list(scheduler.asset_universe),
            'market_regime': macro_regime,
            'user_market_intel': active_user_intel,
        }

    try:
        from database.event_store import TradingEventStore
        async with get_session() as ds_session:
            await TradingEventStore.emit(
                session=ds_session,
                event_type="cycle.data_gathered",
                payload={
                    "market_regime": macro_regime,
                    "stale_assets": list(stale_assets),
                    "should_pause": should_pause,
                },
                correlation_id=state.get("cycle_id", "cycle_unknown"),
                actor="data_node",
            )
    except Exception:
        pass

    return {
        "summary": summary,
        "stale_assets": list(stale_assets),
        "should_pause": should_pause,
        "market_regime": macro_regime,
        "user_market_intel": active_user_intel,
    }
