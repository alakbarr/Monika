import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Callable, AsyncGenerator
from database.db import get_session
from database.models import ActivityLog
from analysis.stages.fundamental_stage import FundamentalStage
from analysis.stages.per_asset_stage import PerAssetStage
logger = logging.getLogger('TradingAgent.CycleScheduler')

class CycleScheduler:

    def __init__(
        self,
        settings: dict,
        mt5_client: Optional[Any] = None,
        fundamental_stage: Optional[Any] = None,
        per_asset_stage: Optional[Any] = None,
        dry_run: bool = False,
        macro_data_scheduler: Optional[Any] = None,
    ) -> None:
        self.settings = settings
        self._mt5 = mt5_client
        self.dry_run = dry_run
        self.macro_data_scheduler = macro_data_scheduler
        self._fundamental = fundamental_stage or FundamentalStage(settings)
        self._per_asset = per_asset_stage or PerAssetStage(settings)
        sched_cfg = settings.get('trading', {}).get('schedule', {})
        self.cycle_hours: float = sched_cfg.get('analysis_cycle_hours', 8.0)
        self.timezone_name: str = sched_cfg.get('timezone', 'Asia/Jakarta')
        self.cycle_times_local: list[str] = (
            sched_cfg.get('cycle_times_local') or self._default_times_from_interval(self.cycle_hours)
        )
        self.daily_report_time_local: str = sched_cfg.get('daily_report_time_local', '08:00')
        self.weekly_report_day: int = sched_cfg.get('weekly_report_weekday', 5)
        self.run_immediately_on_first_start: bool = sched_cfg.get('run_immediately_on_first_start', False)
        self.catch_up_missed_cycles: bool = sched_cfg.get('catch_up_missed_cycles', True)
        self.catch_up_overdue_multiplier: float = sched_cfg.get('catch_up_overdue_multiplier', 1.5)
        self._reports_running: bool = False
        asset_cfg = settings.get('trading', {})
        self.asset_universe: list[str] = asset_cfg.get('asset_universe', ['XAUUSD', 'EURUSD'])
        self.mt5_timeframes: list[str] = asset_cfg.get('mt5', {}).get('timeframes', ['H1', 'H4', 'D1'])
        from scheduler.scraper_runner import ScraperRunner
        self._scraper_runner = ScraperRunner(settings)
        self._stage1_consecutive_failures = 0
        self._max_stage1_failures_before_alert = 2
        from utils.analytics.paper_tracker import PaperTracker
        self._paper_tracker = PaperTracker(settings)
        self._execution_service: Optional[Any] = None
        self._risk_gate: Optional[Any] = None
        self._activity_log: Optional[Any] = None
        self._running = False
        self._stop_event = asyncio.Event()

    @staticmethod
    def _default_times_from_interval(cycle_hours: float) -> list[str]:
        """
        Fallback: kalau user tidak mengonfigurasi `cycle_times_local` secara
        eksplisit, auto-generate jam-jam tetap harian yang merata mulai
        00:00 waktu lokal berdasarkan `analysis_cycle_hours`, sehingga
        cadence lama tetap dipertahankan tapi sekarang berupa jam tetap,
        bukan "jalan lalu tidur N jam".
        """
        try:
            ch = float(cycle_hours) if cycle_hours is not None else 8.0
        except (ValueError, TypeError):
            ch = 8.0
        if ch <= 0 or ch == 8.0:
            return ["07:00", "15:00", "20:00"]
        n = max(1, int(round(24 / cycle_hours)))
        times = []
        for i in range(n):
            total_minutes = int(round(i * cycle_hours * 60)) % (24 * 60)
            hh, mm = divmod(total_minutes, 60)
            times.append(f'{hh:02d}:{mm:02d}')
        return times

    async def _pre_cycle_setup(self, forced: bool=False) -> dict:
        result = {'should_skip': False, 'skip_reason': None, 'weekend_symbols_override': None, 'effective_auto_execute': self.settings.get('trading', {}).get('auto_execute', False)}
        try:
            from utils.analytics.cost_tracker import CostTracker
            async with get_session() as budget_check:
                try:
                    from analysis.tools.tool_executor import ToolExecutor
                    executor = ToolExecutor(budget_check, self.settings)
                    await executor._cleanup_stale_caches()
                except Exception as e:
                    logger.debug(f'Cache cleanup failed (non-fatal): {e}')
                if await CostTracker.is_budget_paused(budget_check, settings=self.settings, force_recheck=True):
                    if not forced:
                        logger.warning("[PreCycleSetup] Cycle SKIPPED: API budget is currently paused (limit reached). Adjust settings or clear pause.")
                        result.update({'should_skip': True, 'skip_reason': 'budget_paused'})
                        return result
                    else:
                        logger.warning("[PreCycleSetup] API budget is paused, but cycle is FORCED (forced=True). Proceeding anyway...")
                rolling = await CostTracker.get_rolling_7day_cost(budget_check)
                from config.settings import DEFAULT_MONTHLY_BUDGET_USD
                budget = self.settings.get('cost_tracking', {}).get('monthly_budget_usd', DEFAULT_MONTHLY_BUDGET_USD)
                if rolling['projected_monthly'] > budget * 0.95 and (not forced):
                    logger.warning(f"[PreCycleSetup] Cycle SKIPPED: Projected monthly cost ${rolling['projected_monthly']:.2f} > 95% of budget ${budget:.2f}.")
                    result.update({'should_skip': True, 'skip_reason': 'near_budget_limit'})
                    return result
        except Exception as e:
            logger.debug(f'Pre-cycle budget check failed (non-fatal): {e}')
        if not forced:
            from utils.validation.data_validator import validate_data_freshness
            async with get_session() as session:
                proxy = self.asset_universe[0:1] if self.asset_universe else ['EURUSD']
                data_quality_cfg = self.settings.get('data_quality', {})
                max_ohlcv = data_quality_cfg.get('max_ohlcv_age_hours', {'H4': 8.0})
                freshness = await validate_data_freshness(session, proxy, ['H4'], max_ohlcv_age_hours=max_ohlcv)
                if not freshness['ready']:
                    msg = f"Data freshness validation failed: {freshness['errors']}. Will attempt to fetch in data_gathering node."
                    logger.warning(msg)
        paper_trades = 0
        paper_wr = 0.0
        min_paper_trades = self.settings.get('trading', {}).get('min_paper_trades_before_live', 40)
        min_paper_wr = self.settings.get('trading', {}).get('min_paper_win_rate_pct', 45.0)
        try:
            from utils.analytics.paper_tracker import PaperTracker
            from database.models import SystemConfig
            from sqlalchemy import select
            async with get_session() as perf_session:
                tracker = PaperTracker()
                stats = await tracker.get_statistics(perf_session)
                paper_trades = stats.get('total_trades', 0)
                paper_wr = stats.get('win_rate_pct', 0)
                blocked_cfg = (await perf_session.execute(select(SystemConfig).where(SystemConfig.key == 'auto_execute_paper_blocked'))).scalar_one_or_none()
                is_blocked = blocked_cfg and blocked_cfg.value == 'true'
                if paper_trades < min_paper_trades:
                    logger.info(f'[PaperGate] Accumulation phase: {paper_trades}/{min_paper_trades} trades. auto_execute allowed to accumulate paper trade data. Ensure --dry-run flag is active.')
                    if is_blocked and blocked_cfg:
                        blocked_cfg.value = 'false'
                        await perf_session.commit()
                    import sys
                    is_dry_run = '--dry-run' in sys.argv or getattr(self, 'dry_run', False)
                    if not is_dry_run and self.settings.get('trading', {}).get('auto_execute', False):
                        logger.critical(f'[SAFETY WARNING] auto_execute=True and paper_trades={paper_trades} < {min_paper_trades}. No performance validation yet. Run with --dry-run until min trades are accumulated!')
                elif paper_trades >= min_paper_trades and paper_wr < min_paper_wr:
                    if not is_blocked:
                        if blocked_cfg:
                            blocked_cfg.value = 'true'
                        else:
                            perf_session.add(SystemConfig(key='auto_execute_paper_blocked', value='true'))
                        await perf_session.commit()
                    result['effective_auto_execute'] = False
                    if self.settings.get('trading', {}).get('auto_execute', False):
                        logger.warning(f'AUTO-EXECUTE SUPPRESSED: Performance gate failed. Trades: {paper_trades}/{min_paper_trades}, WR: {paper_wr:.1f}%/{min_paper_wr}%.')
                elif is_blocked and paper_wr >= min_paper_wr and (paper_trades >= min_paper_trades):
                    if blocked_cfg:
                        blocked_cfg.value = 'false'
                        await perf_session.commit()
                        logger.info('Paper performance recovered. Unblocking auto-execute.')
                    result['effective_auto_execute'] = self.settings.get('trading', {}).get('auto_execute', False)
                if paper_trades >= min_paper_trades:
                    try:
                        from utils.analytics.edge_tracker import compute_edge_status
                        async with get_session() as edge_session:
                            edge_status = await compute_edge_status(edge_session)
                        if edge_status.get('status') == 'no_edge' and edge_status.get('total_trades', 0) >= 50:
                            result['effective_auto_execute'] = False
                            logger.critical(f"[EdgeGate] Statistical edge NOT confirmed after {edge_status['total_trades']} trades. Win rate: {edge_status['win_rate']}% (CI: {edge_status['ci_lower']}-{edge_status['ci_upper']}%). Auto-execute suppressed.")
                    except Exception as e:
                        logger.debug(f'Edge status check failed (non-fatal): {e}')
        except Exception as e:
            logger.debug(f'Paper performance gate check failed (non-fatal): {e}')
        if not forced:
            start = datetime.now(timezone.utc)
            weekday = start.weekday()
            hour = start.hour
            is_weekend_close = weekday == 4 and hour >= 21 or weekday == 5 or (weekday == 6 and hour < 21)
            if is_weekend_close:
                always_open = set(self.settings.get('trading', {}).get('24_7_assets', ['BTCUSD']))
                active = [a for a in self.asset_universe if a in always_open]
                if not active:
                    logger.info('Market closed (weekend). No 24/7 assets. Skipping cycle.')
                    result.update({'should_skip': True, 'skip_reason': 'market_closed_weekend'})
                    return result
                logger.info(f'Weekend: running analysis for 24/7 assets only: {active}')
                result['weekend_symbols_override'] = active

        # TimesFM 3.0 Universe Batch Forecast Generation
        if not result.get('should_skip', False):
            try:
                from indicators.timesfm_engine import TimesFMEngine
                tfm_engine = TimesFMEngine(self.settings)
                if tfm_engine.enabled:
                    target_syms = result.get('weekend_symbols_override') or self.asset_universe
                    async with get_session() as tfm_sess:
                        await tfm_engine.generate_and_store_universe_forecasts(tfm_sess, target_syms, timeframe='H1', horizon_steps=24)
            except Exception as tfm_setup_err:
                logger.warning(f"[PreCycleSetup] TimesFM universe forecast batch error (non-fatal): {tfm_setup_err}")

        logger.info(f"[PreCycleSetup] effective_auto_execute={result['effective_auto_execute']}, paper_trades={paper_trades}/{min_paper_trades}, win_rate={paper_wr:.1f}%/{min_paper_wr}%, should_skip={result['should_skip']}")
        return result

    async def run_once(self, forced: bool=False) -> dict:
        raise NotImplementedError('Use GraphCycleScheduler.run_once()')

    async def _get_symbol_paper_stats(self, session: Any, symbol: str) -> dict:
        try:
            from database.models import PaperTradeRecord
            from sqlalchemy import select
            stmt = (
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.status == 'closed')
                .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
                .order_by(PaperTradeRecord.closed_at.desc().nullslast(), PaperTradeRecord.id.desc())
                .limit(20)
            )
            records = (await session.execute(stmt)).scalars().all()
            if len(records) < 5:
                return {'sufficient': False, 'trades': len(records)}
            wins = [r for r in records if r.exit_reason == 'tp_hit']
            win_rate = len(wins) / len(records) * 100
            return {'sufficient': True, 'trades': len(records), 'win_rate': win_rate, 'blocked': win_rate < 35.0 and len(records) >= 8}
        except Exception as e:
            logger.debug(f'Symbol stats check failed: {e}')
            return {'sufficient': False, 'trades': 0}

    async def _should_skip_full_cycle(self) -> tuple[bool, str]:
        async with get_session() as session:
            from database.models import VIXData, TechnicalIndicator
            from sqlalchemy import select
            vix = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
            if vix and vix.close > 35:
                logger.warning(f'VIX={vix.close:.1f} > 35 (extreme fear). Running analysis anyway — position protection critical during extreme volatility.')
            ranging_count = 0
            for symbol in self.asset_universe:
                adx_row = (await session.execute(select(TechnicalIndicator).where(TechnicalIndicator.symbol == symbol).where(TechnicalIndicator.timeframe == 'D1').where(TechnicalIndicator.indicator_name == 'ADX_14').order_by(TechnicalIndicator.timestamp.desc()).limit(1))).scalar_one_or_none()
                if adx_row:
                    import json
                    adx_data = json.loads(adx_row.value_json or '{}')
                    adx = adx_data.get('adx', 25) if isinstance(adx_data, dict) else float(adx_data)
                    if adx < 12:
                        ranging_count += 1
        return (False, '')

    # =====================================================================
    # NOTE: _deterministic_portfolio_filter and _portfolio_synthesis
    # have been REMOVED (Phase 2).
    # Portfolio synthesis logic is now fully handled by:
    # 1. risk/portfolio_correlation_gate.py
    # 2. graph/nodes/risk_gate_node.py (_ai_portfolio_synthesis)
    # =====================================================================

    async def _handle_weekend_positions(self) -> dict:
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        hour = now.hour
        if weekday != 4 or not 16 <= hour <= 20:
            return {}
        weekend_cfg = self.settings.get('trading', {}).get('weekend_management', {})
        if not weekend_cfg.get('enabled', True):
            return {}
        strategy = weekend_cfg.get('strategy', 'alert_only')
        exempted_symbols = set(weekend_cfg.get('exempted_symbols', ['BTCUSD']))
        from database.db import get_session
        from database.models import Position
        from sqlalchemy import select
        async with get_session() as session:
            open_positions = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
            positions_at_risk = [p for p in open_positions if p.symbol not in exempted_symbols]
            if not positions_at_risk:
                return {'positions_checked': 0}
            msg_lines = [f'🌙 <b>Weekend Gap Alert — Friday {hour}:00 UTC</b>\n', f'Open positions exposed to weekend gap risk:\n']
            for p in positions_at_risk:
                msg_lines.append(f'• {p.symbol} {p.direction.upper()} {p.volume}L @ {p.entry_price} | ticket={p.mt5_ticket}')
            if strategy == 'close_positions':
                msg_lines.append(f'\n<b>AUTO-CLOSING non-exempt positions before weekend.</b>')
                from execution.execution_service import ExecutionService
                exec_svc = ExecutionService(self.settings, self._mt5, dry_run=self.dry_run) if not hasattr(self, '_execution_service') else self._execution_service
                for p in positions_at_risk:
                    if p.mt5_ticket and exec_svc:
                        try:
                            await exec_svc.close_position_by_ticket(p.mt5_ticket, requested_by='weekend_guardian', reason='Weekend gap protection')
                        except Exception as e:
                            logger.error(f'Weekend close failed for {p.symbol}: {e}')
            elif strategy == 'close_if_profitable':
                msg_lines.append(f'\n<b>Applying close_if_profitable strategy.</b>')
                threshold = weekend_cfg.get('profit_threshold_pct', 0.5)
                from execution.execution_service import ExecutionService
                exec_svc = ExecutionService(self.settings, self._mt5, dry_run=self.dry_run) if not hasattr(self, '_execution_service') else self._execution_service
                for p in positions_at_risk:
                    if p.mt5_ticket and exec_svc and self._mt5:
                        unrealized_pnl = 0.0
                        try:
                            mt5_pos = await self._mt5.get_open_positions()
                            for mp in mt5_pos or []:
                                if mp['ticket'] == p.mt5_ticket:
                                    curr = mp['price_current']
                                    if p.entry_price and curr:
                                        if p.direction == 'buy':
                                            unrealized_pnl = (curr - p.entry_price) / p.entry_price * 100
                                        else:
                                            unrealized_pnl = (p.entry_price - curr) / p.entry_price * 100
                                    break
                        except Exception as e:
                            logger.warning(f'Could not calc pnl for {p.symbol}: {e}')
                        if unrealized_pnl and unrealized_pnl > threshold:
                            msg_lines.append(f'  → Closing {p.symbol} (profit {unrealized_pnl:.2f}% > {threshold}%)')
                            try:
                                await exec_svc.close_position_by_ticket(p.mt5_ticket, requested_by='weekend_guardian', reason=f'Weekend profit lock ({unrealized_pnl:.2f}%)')
                            except Exception as e:
                                logger.error(f'Weekend close failed for {p.symbol}: {e}')
                        elif p.entry_price and p.sl and (unrealized_pnl > 0.1):
                            msg_lines.append(f'  → Moving SL to breakeven for {p.symbol} (profit {unrealized_pnl:.2f}%)')
                            try:
                                await exec_svc.modify_position_sl_tp(p.mt5_ticket, sl=p.entry_price, tp=p.tp, requested_by='weekend_guardian')
                            except Exception as e:
                                logger.error(f'Weekend breakeven SL failed for {p.symbol}: {e}')
                        else:
                            msg_lines.append(f'  → Leaving {p.symbol} open (loss/small profit {unrealized_pnl:.2f}%)')
            else:
                msg_lines.append(f'\nConsider closing positions manually before Forex market close (~21:00 UTC).')
            try:
                from utils.infra.notifier import AgentNotifier
                await AgentNotifier().send_warning('\n'.join(msg_lines))
            except Exception as e:
                logger.warning(f'Weekend alert failed: {e}')
            return {'positions_alerted': len(positions_at_risk), 'strategy': strategy}

    async def start(self) -> None:
        self._running = True
        from utils.scheduling.wall_clock import parse_time_list, sleep_until_next

        logger.info(
            f'Cycle scheduler starting. Scheduled run times ({self.timezone_name}): '
            f'{self.cycle_times_local} | Assets: {self.asset_universe}'
        )
        logger.info(
            'Catatan: siklus TIDAK dijalankan langsung saat startup. Ini disengaja '
            'agar restart selama development tidak memboroskan API budget. Gunakan '
            'perintah Telegram /run untuk memicu siklus manual kapan saja.'
        )

        if self.run_immediately_on_first_start:
            logger.warning(
                'trading.schedule.run_immediately_on_first_start=true — menjalankan '
                'satu siklus analisis SEKARANG saat startup (ini AKAN memakan token API).'
            )
            await self._safe_run_once()

        while self._running:
            times = parse_time_list(self.cycle_times_local)
            target = await sleep_until_next(times, self.timezone_name, label='CycleScheduler', shutdown_event=self._stop_event)
            if not self._running:
                break
            logger.info(
                f"Jadwal terjadwal tercapai ({target.strftime('%Y-%m-%d %H:%M UTC')}). "
                f"Menjalankan siklus analisis..."
            )
            await self._safe_run_once()

    async def run_scheduled_reports_loop(self) -> None:
        """
        Menjalankan laporan harian + kalibrasi pada jam lokal tetap setiap
        hari, dan weekly edge assessment pada hari tertentu. Dipisahkan dari
        loop siklus analisis utama agar waktunya presisi, tidak lagi
        tergantung kapan loop siklus utama kebetulan bangun dari sleep.
        """
        from utils.scheduling.wall_clock import parse_time_list, sleep_until_next, get_tzinfo

        self._reports_running = True
        logger.info(
            f'Scheduled reports loop starting. Daily report time: '
            f'{self.daily_report_time_local} {self.timezone_name}'
        )
        while self._reports_running:
            try:
                from config.settings import load_settings
                fresh_settings = load_settings()
                sched_cfg = fresh_settings.get('trading', {}).get('schedule', {})
                self.timezone_name = sched_cfg.get('timezone', self.timezone_name)
                self.daily_report_time_local = sched_cfg.get('daily_report_time_local', self.daily_report_time_local)
                self.weekly_report_day = sched_cfg.get('weekly_report_weekday', self.weekly_report_day)
            except Exception as e:
                logger.debug(f'Reports loop settings reload failed (non-fatal): {e}')

            times = parse_time_list([self.daily_report_time_local])
            target = await sleep_until_next(times, self.timezone_name, label='DailyReport', shutdown_event=self._stop_event)
            if not self._reports_running:
                break

            try:
                await self._send_daily_report()
            except Exception as e:
                logger.error(f'Daily report failed: {e}')
            try:
                await self._run_daily_calibrations()
            except Exception as e:
                logger.error(f'Daily calibrations failed: {e}')

            local_dt = target.astimezone(get_tzinfo(self.timezone_name))
            if local_dt.weekday() == self.weekly_report_day:
                try:
                    await self._send_weekly_edge_assessment()
                except Exception as e:
                    logger.error(f'Weekly edge assessment failed: {e}')

    def stop(self) -> None:
        self._running = False
        self._reports_running = False
        self._stop_event.set()
        logger.info('Cycle scheduler stop requested.')

    async def _run_daily_calibrations(self) -> None:
        try:
            from database.db import get_session
            from database.models import SystemConfig
            from sqlalchemy import select
            
            async with get_session() as session:
                logger.info("Running daily background calibrations...")
                
                # 0. Strategy Edge tracker
                try:
                    from utils.analytics.strategy_edge_tracker import apply_disable_flags
                    disabled = await apply_disable_flags(session, self.settings)
                    if disabled:
                        logger.info(f"EdgeStrategyRunner disabled underperforming strategies: {disabled}")
                except Exception as e:
                    logger.error(f"Strategy edge tracking failed: {e}")

                # 1. CDS Threshold Calibration
                try:
                    from utils.calibration.cds_threshold_calibrator import run_calibration_if_due
                    cds_result = await run_calibration_if_due(session, self.settings)
                    if cds_result.get('status') == 'calibrated' and cds_result.get('recommendations'):
                        logger.info(f"CDS thresholds auto-calibrated: {cds_result['recommendations']}")
                except Exception as e:
                    logger.error(f"CDS threshold calibration failed: {e}")
                
                try:
                    from utils.analytics.cds_outcome_tracker import auto_calibrate_cds_threshold
                    new_thresh, reason = await auto_calibrate_cds_threshold(session)
                    logger.info(f"CDS Outcome auto-calibration: {new_thresh} ({reason})")
                except Exception as e:
                    logger.debug(f"CDS outcome auto-calibration failed: {e}")
                
                # 2. Adversarial Correlation Check
                try:
                    from utils.analytics.adversarial_outcome_tracker import compute_adversarial_check_correlation
                    adv_result = await compute_adversarial_check_correlation(session)
                    if adv_result.get('status') == 'analyzed':
                        logger.info(f"Adversarial logic analyzed: {adv_result.get('recommendation')}")
                        key = 'adversarial_alert_on_extreme_only_override'
                        should_widen = (not adv_result.get('is_predictive', True)
                                         and adv_result.get('flagged_total', 0) >= 10)
                        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                        val = 'false' if should_widen else 'true'
                        if cfg:
                            cfg.value = val
                        else:
                            session.add(SystemConfig(key=key, value=val))
                        await session.commit()
                        if should_widen:
                            logger.warning('[AdversarialCalib] Flagged trades tidak terbukti lebih buruk dari clean '
                                            'trades -> memperluas alert scope (alert_on_extreme_only=false)')
                except Exception as e:
                    logger.error(f"Adversarial correlation check failed: {e}")

                # IMP-2: News classification calibration
                try:
                    from utils.analytics.news_classification_tracker import compute_news_classification_calibration
                    news_calib = await compute_news_classification_calibration(session)
                    if news_calib.get('over_classification_suspected'):
                        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'news_auto_tighten'))).scalar_one_or_none()
                        if cfg:
                            cfg.value = '1'
                        else:
                            session.add(SystemConfig(key='news_auto_tighten', value='1'))
                        await session.commit()
                        logger.warning(f"[NewsCalib] Outcome-based over-classification detected: {news_calib['by_impact']}")
                except Exception as e:
                    logger.error(f'News classification calibration failed: {e}')

                # IMP-9: Confidence calibration
                try:
                    from utils.calibration.confidence_calibrator import apply_calibration_correction
                    await apply_calibration_correction(session, self.settings)
                except (ImportError, AttributeError) as e:
                    logger.warning(f"Calibration correction not yet implemented: {e}")
                except Exception as e:
                    logger.debug(f'Confidence calibration correction failed: {e}')

                # IMP-7: Consolidate lessons
                try:
                    from analysis.memory.lesson_consolidator import consolidate_lessons_to_playbook
                    key = 'lesson_consolidation_last_run'
                    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
                    should_run = True
                    if cfg and cfg.value:
                        last_run = datetime.fromisoformat(cfg.value)
                        if last_run.tzinfo is None:
                            last_run = last_run.replace(tzinfo=timezone.utc)
                        should_run = (datetime.now(timezone.utc) - last_run).total_seconds() > 7 * 86400
                    if should_run:
                        content = await consolidate_lessons_to_playbook(session, self.settings)
                        if content:
                            logger.info('Lessons Learned playbook consolidated and updated.')
                            now_iso = datetime.now(timezone.utc).isoformat()
                            if cfg:
                                cfg.value = now_iso
                            else:
                                session.add(SystemConfig(key=key, value=now_iso))
                            await session.commit()
                except Exception as e:
                    logger.error(f'Lesson consolidation failed: {e}')

        except Exception as e:
            logger.error(f'Failed to run daily calibrations: {e}')

    async def _send_weekly_edge_assessment(self) -> None:
        try:
            from utils.analytics.analysis_tracker import get_direction_accuracy_report, compute_factor_effectiveness, analyze_debate_impact
            from utils.analytics.edge_tracker import compute_edge_status
            from utils.llm.memory_compressor import compress_agent_memory
            from utils.protocol.coherence_flag_tracker import compute_coherence_override_impact
            from database.db import get_session
            from sqlalchemy import select
            async with get_session() as session:
                dir_acc = await get_direction_accuracy_report(session, 14)
                factors = await compute_factor_effectiveness(session, 30)
                stats = await self._paper_tracker.get_statistics(session)
                edge_data = await compute_edge_status(session)
                debate_impact = await analyze_debate_impact(session, 30)
                coherence_impact = await compute_coherence_override_impact(session, 30)
                
                # Compress agent memory weekly
                await compress_agent_memory(session, self.settings)
                
                # IMP-10: Cek kualitas model specialist
                from utils.analytics.specialist_tracker import check_specialist_model_quality
                spec_qual = await check_specialist_model_quality(session, self.settings)

                from database.models import PaperTradeRecord
                try:
                    res = await session.execute(
                        select(PaperTradeRecord).where(PaperTradeRecord.status == 'closed')
                    )
                    sc = res.scalars() if hasattr(res, "scalars") else None
                    if asyncio.iscoroutine(sc):
                        sc = await sc
                    all_paper = sc.all() if (sc is not None and hasattr(sc, "all")) else []
                    if asyncio.iscoroutine(all_paper):
                        all_paper = await all_paper
                    if not isinstance(all_paper, list):
                        all_paper = list(all_paper) if hasattr(all_paper, "__iter__") else []
                except Exception as paper_err:
                    logger.debug(f"Could not load closed paper trades for weekly tearsheet: {paper_err}")
                    all_paper = []
                
            msg = '📊 *WEEKLY EDGE ASSESSMENT*\n\n'
            msg += f"• *Win Rate (Paper):* {stats.get('win_rate_pct', 0)}% (Total: {stats.get('total_trades', 0)})\n"
            try:
                from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator
                if all_paper:
                    ts_res = QuantTearsheetGenerator.generate_from_trades(all_paper)
                    msg += f"• *Quant Tearsheet (All-Time):* Sharpe: `{ts_res.annualized_sharpe:.2f}` | Sortino: `{ts_res.annualized_sortino:.2f}` | Calmar: `{ts_res.calmar_ratio:.2f}`\n"
                    msg += f"• *Drawdown & Risk:* Max DD: `{ts_res.max_drawdown_pct:.2f}%` ({ts_res.max_drawdown_duration_days:.1f}d) | Vol: `{ts_res.daily_std_pct:.2f}%`\n"
                    msg += f"• *Expectancy Profile:* PF: `{ts_res.profit_factor:.2f}` | Payoff: `{ts_res.payoff_ratio:.2f}` | Expectancy: `{ts_res.expectancy_r:+.2f}R`\n"
            except Exception as e:
                logger.debug(f"Weekly tearsheet generation failed: {e}")

            if 'direction_accuracy_4h' in dir_acc:
                msg += f"• *Direction Accuracy (4H):* {dir_acc['direction_accuracy_4h']}%\n"
            if debate_impact:
                msg += f"• *Debate Alignment (Judge)*: {debate_impact.get('judge_alignment_pct', 0)}% match with outcome\n"
            if coherence_impact and not coherence_impact.get('insufficient_data'):
                msg += f"• *Coherence Override Impact*: {coherence_impact.get('recommendation', '')}\n"
            msg += "\n"
            if edge_data['status'] != 'insufficient_data':
                status_emoji = {'positive_edge': '🟢', 'uncertain': '🟡', 'no_edge': '🔴'}.get(edge_data['status'], '⚪')
                msg += f'*Edge Analysis ({status_emoji})*\n'
                msg += f"Z-Score: {edge_data['z_score']} (CI: {edge_data['ci_lower']}-{edge_data['ci_upper']}%)\n"
                msg += f"{edge_data['action']}\n\n"
            msg += '*Top Edge Factors:*\n'
            top_factors = sorted(factors.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True)[:3]
            for factor, data in top_factors:
                msg += f"- {factor.upper()}: {data.get('win_rate', 0)}% WR\n"
            if spec_qual.get('alerts'):
                msg += '\n\n🚨 *SPECIALIST ALERTS*\n'
                for alert in spec_qual['alerts']:
                    msg += f"- {alert}\n"
            
            # LLM Executive Synthesis for Weekly Edge Assessment
            try:
                from analysis.providers.llm_factory import get_client_for_task
                client = get_client_for_task("report_synthesizer", self.settings)
                prompt = (
                    "Synthesize the following weekly edge assessment metrics into a concise executive narrative "
                    "(2-3 sentences covering edge health, top factor drivers, and operational takeaways for risk posture):\n\n"
                    f"{msg}"
                )
                summary = await client.generate_text(prompt, system_prompt="You are the Chief Risk Officer for an institutional trading desk.")
                if summary and summary.strip():
                    msg = f"📊 *WEEKLY EDGE ASSESSMENT*\n\n*Executive Synthesis:*\n{summary.strip()}\n\n" + msg[len("📊 *WEEKLY EDGE ASSESSMENT*\n\n"):]
            except Exception as llm_err:
                logger.debug(f"LLM weekly edge assessment synthesis fallback to raw: {llm_err}")

            from utils.infra.notifier import AgentNotifier
            await AgentNotifier().send_markdown(msg)
        except Exception as e:
            logger.error(f'Failed to send weekly edge assessment: {e}')

    async def _send_daily_report(self) -> None:
        try:
            from database.db import get_session
            from database.models import TradeOutcome, Position, EconomicCalendar, VIXData
            from sqlalchemy import select, func
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            yesterday = now - timedelta(days=1)
            async with get_session() as session:
                closed_today = (await session.execute(select(TradeOutcome).where(TradeOutcome.closed_at >= yesterday))).scalars().all()
                total_pnl = sum((t.pnl_usd or 0 for t in closed_today))
                wins = [t for t in closed_today if (t.pnl_usd or 0) > 0]
                open_pos = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
                next_24h = now + timedelta(hours=24)
                events = (await session.execute(select(EconomicCalendar).where(EconomicCalendar.event_time >= now).where(EconomicCalendar.event_time <= next_24h).where(EconomicCalendar.impact == 'high').order_by(EconomicCalendar.event_time.asc()))).scalars().all()
                vix = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
                
                paper_stats = {}
                try:
                    from utils.analytics.paper_tracker import PaperTracker
                    tracker = PaperTracker()
                    paper_stats = await tracker.get_statistics(session)
                except Exception as e:
                    logger.debug(f'Paper stats in report failed: {e}')
                
                health_score = 10
                if not getattr(self, '_mt5', None):
                    health_score -= 3
                try:
                    from utils.analytics.cost_tracker import CostTracker
                    rolling = await CostTracker.get_rolling_7day_cost(session)
                    from config.settings import DEFAULT_MONTHLY_BUDGET_USD
                    budget = self.settings.get('cost_tracking', {}).get('monthly_budget_usd', DEFAULT_MONTHLY_BUDGET_USD)
                    if rolling.get('projected_monthly', 0) > budget:
                        health_score -= 2
                except Exception:
                    pass
                
                last_7d = now - timedelta(days=7)
                from database.models import PaperTradeRecord, AssetAnalysis, CyclePerformance
                paper_7d = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == 'closed', PaperTradeRecord.closed_at >= last_7d))).scalars().all()
                wins_7d = sum((1 for p in paper_7d if p.exit_reason == 'tp_hit' or (p.pnl_pct and p.pnl_pct > 0)))
                wr_7d = wins_7d / len(paper_7d) * 100 if paper_7d else 0.0
                cycles_24h = (await session.execute(select(CyclePerformance).where(CyclePerformance.cycle_at >= yesterday))).scalars().all()
                total_assets = sum(((c.assets_analyzed or 0) + (c.assets_skipped or 0) for c in cycles_24h))
                skip_rate = sum((c.assets_skipped or 0 for c in cycles_24h)) / total_assets * 100 if total_assets > 0 else 0.0
                recent_analyses = (await session.execute(select(AssetAnalysis).where(AssetAnalysis.decision.in_(['buy', 'sell'])).order_by(AssetAnalysis.generated_at.desc()).limit(3))).scalars().all()
                
                lines = [f"📊 <b>Daily Report — {now.strftime('%d %b %Y %H:%M UTC')}</b>\n", f'<b>❤️ System Health: {health_score}/10</b>', f'<b>📈 Trending WR (7d): {wr_7d:.1f}%</b> ({len(paper_7d)} trades)', f'<b>⏭️ Haiku Skip Rate: {skip_rate:.1f}%</b>\n', f"<b>Yesterday's Live Trades ({len(closed_today)} closed):</b>", f"  P&L: ${total_pnl:+.2f}", f'  Win rate: {len(wins)}/{max(len(closed_today), 1)} ({len(wins) / max(len(closed_today), 1) * 100:.0f}%)\n', f'<b>Top 3 Recent Setups:</b>']
                for a in recent_analyses:
                    lines.append(f"  • {a.symbol}: {a.decision.upper()} (Conf: {getattr(a, 'confidence', 0):.0%})")
                if not recent_analyses:
                    lines.append('  • None recently')
                lines.append(f'\n<b>Open Positions ({len(open_pos)}):</b>')
                
                try:
                    from utils.analytics.analysis_tracker import get_confluence_calibration_status
                    calib = await get_confluence_calibration_status(session)
                    if not calib.get('insufficient_data'):
                        rec = calib.get('recommendation', 'MAINTAIN')
                        if rec != 'MAINTAIN':
                            lines.insert(1, f"⚠️ <b>Calibration Alert:</b> threshold {calib['current_threshold']} → {calib['optimal_threshold_from_data']} ({rec})\n")
                except Exception:
                    pass
                
                for pos in open_pos:
                    lines.append(f'  • {pos.symbol} {pos.direction.upper()} {pos.volume}L @ {pos.entry_price} | SL: {pos.sl}')
                if events:
                    lines.append('')
                    lines.append("<b>Today's High-Impact Events:</b>")
                    for ev in events[:5]:
                        ts = ev.event_time.strftime('%H:%M UTC') if ev.event_time else '?'
                        lines.append(f'  • {ts} {ev.currency}: {ev.event_name}')
                if vix:
                    risk_cfg = self.settings.get('trading', {}).get('risk', {})
                    vix_thresholds = risk_cfg.get('vix_thresholds', {})
                    vix_pause = vix_thresholds.get('pause', 30)
                    vix_defensive = vix_thresholds.get('defensive', 25)
                    if vix.close >= vix_pause:
                        vix_status = f'🔴 {vix.close:.2f} — TRADING BLOCKED (>{vix_pause})'
                    elif vix.close >= vix_defensive:
                        vix_status = f'🟡 {vix.close:.2f} — Defensive mode (>{vix_defensive}, 50% risk)'
                    else:
                        vix_status = f'🟢 {vix.close:.2f} — Normal'
                    lines.append(f'\n<b>VIX:</b> {vix_status}')
                
                try:
                    stats = paper_stats
                    if stats.get('total_trades', 0) >= 3:
                        wr = stats.get('win_rate_pct', 0)
                        wr_emoji = '🔴' if wr < 35 else '🟡' if wr < 50 else '🟢'
                        lines.append(f"\n<b>📊 Paper Trading (All-Time {stats['total_trades']} trades):</b>\n  Win rate: {wr_emoji} {wr:.1f}% | Avg P&L: {stats.get('avg_pnl_pct', 0):.3f}%\n  Total PnL: {stats.get('total_pnl_pct', 0):+.3f}%")
                        by_sym = stats.get('by_symbol', {})
                        worst_symbols = sorted([(s, d) for s, d in by_sym.items() if d.get('trades', 0) >= 3], key=lambda x: x[1].get('win_rate', 50))[:3]
                        if worst_symbols:
                            lines.append('  Worst performers:')
                            for sym, data in worst_symbols:
                                lines.append(f"    • {sym}: {data.get('win_rate', 0):.0f}% WR ({data.get('trades', 0)} trades)")
                except Exception as e:
                    logger.warning(f'Paper stats in report failed: {e}')

                try:
                    from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator
                    if paper_7d and len(paper_7d) >= 3:
                        ts_res = QuantTearsheetGenerator.generate_from_trades(paper_7d)
                        lines.append(
                            f"\n<b>📈 Quant Tearsheet (7d):</b>\n"
                            f"  Sharpe: <code>{ts_res.annualized_sharpe:.2f}</code> | Sortino: <code>{ts_res.annualized_sortino:.2f}</code>\n"
                            f"  Max DD: <code>{ts_res.max_drawdown_pct:.2f}%</code> | Profit Factor: <code>{ts_res.profit_factor:.2f}</code>\n"
                            f"  Expectancy: <code>{ts_res.expectancy_r:+.2f}R</code> (${ts_res.expectancy_usd:+.2f})"
                        )
                except Exception as e:
                    logger.debug(f"Quant tearsheet in daily report failed: {e}")
                
                try:
                    from utils.analytics.analysis_tracker import compute_analysis_quality_report
                    quality_report = await compute_analysis_quality_report(session, days_back=30)
                    if quality_report.get('total_outcomes', 0) >= 5:
                        lines.append(f"\n<b>Analysis Quality (30d, {quality_report['total_outcomes']} trades):</b>")
                        lines.append(f"  Overall win rate: {quality_report.get('overall_win_rate', 0)}%")
                        for sym, data in quality_report.get('by_symbol', {}).items():
                            sym_total = data.get('total', data.get('trades', 0))
                            sym_wr = data.get('win_rate', 100)
                            if sym_total >= 3 and sym_wr < 35:
                                lines.append(f"  ⚠️ {sym}: {sym_wr:.0f}% WR — below breakeven!")
                except Exception as e:
                    logger.warning(f'Analysis quality report failed: {e}')
                
                try:
                    from utils.calibration.prescreen_calibrator import compute_prescreen_skip_quality
                    skip_qual = await compute_prescreen_skip_quality(session)
                    if not skip_qual.get("insufficient_data"):
                        false_skip_rate = skip_qual.get("false_skip_rate", 0)
                        lines.append(f"\n<b>Prescreen Skip Quality (7d):</b>")
                        lines.append(f"  False Skip Rate: {false_skip_rate:.1f}%")
                        if false_skip_rate > 35:
                            lines.append(f"  ⚠️ HIGH FALSE SKIP RATE detected! Local ADX/VIX gates will be auto-disabled to prevent missing good setups.")
                except Exception as e:
                    logger.warning(f'Prescreen skip quality check failed: {e}')
                
                try:
                    from utils.analytics.analysis_tracker import detect_score_inflation
                    inflation_data = await detect_score_inflation(session, days_back=30)
                    if not inflation_data.get('insufficient_data') and inflation_data.get('alert'):
                        direction = inflation_data.get('direction', 'UNKNOWN')
                        drift = inflation_data.get('drift', 0)
                        first_avg = inflation_data.get('first_half_avg_score', 0)
                        second_avg = inflation_data.get('second_half_avg_score', 0)
                        lines.append(f'\n<b>⚠️ Score Drift Detected:</b>')
                        lines.append(f'  Confluence scores: {first_avg:.1f} (first half) → {second_avg:.1f} (second half)')
                        if direction == 'INFLATING':
                            lines.append(f'  📈 INFLATING +{drift:.2f}: Model may be lowering standards. Review recent BUY/SELL rationale quality. Consider raising auto_execute_min_confluence by 1-2 temporarily.')
                        elif direction == 'DEFLATING':
                            lines.append(f'  📉 DEFLATING {drift:.2f}: Model may be overly conservative. Review whether valid setups are being skipped.')
                        
                        if direction == 'INFLATING' and drift > 2.0:
                            from database.models import SystemConfig
                            correction_threshold = min(int(second_avg) - 1, 12)
                            cfg_key = 'score_inflation_correction_threshold'
                            cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))).scalar_one_or_none()
                            import json as _j
                            correction_data = _j.dumps({'threshold': correction_threshold, 'set_at': datetime.now(timezone.utc).isoformat(), 'drift': round(drift, 2), 'expires_days': 7})
                            if cfg:
                                cfg.value = correction_data
                            else:
                                session.add(SystemConfig(key=cfg_key, value=correction_data))
                            await session.commit()
                            logger.warning(f'Score inflation correction applied: effective threshold raised to {correction_threshold} (drift={drift:.1f} points). Auto-expires in 7 days.')
                except Exception as e:
                    logger.debug(f'Score inflation check in daily report failed (non-fatal): {e}')
                
                lines.append(f"\n<b>🖥️ System Health:</b>")
                try:
                    from utils.scheduling.wall_clock import parse_time_list, next_occurrence
                    times = parse_time_list(self.cycle_times_local)
                    next_dt = next_occurrence(times, self.timezone_name, now)
                    diff_h = max(0.0, (next_dt - now).total_seconds() / 3600)
                    lines.append(f"  Next cycle: ~{diff_h:.1f}h from now")
                except Exception:
                    lines.append(f"  Next cycle: ~{self.cycle_hours}h from now")
                lines.append(f"  Asset universe: {', '.join(self.asset_universe)}")
                
                try:
                    from database.models import PriceOHLCV
                    paper_m15_count = (await session.execute(select(func.count(PriceOHLCV.id)).where(PriceOHLCV.timeframe == 'M15').where(PriceOHLCV.timestamp >= now - timedelta(hours=24)))).scalar_one_or_none() or 0
                    if paper_m15_count == 0:
                        lines.append('  ⚠️ M15: No data (paper trade detection using H4 fallback)')
                    else:
                        lines.append(f'  ✅ M15: {paper_m15_count} bars (last 24h) - accurate paper trade detection active')
                except Exception as e:
                    logger.debug(f'Failed to check M15 data freshness: {e}')
                
                try:
                    from utils.api.gemini_rate_limiter import GeminiRateLimiter
                    limiter = GeminiRateLimiter(session)
                    await GeminiRateLimiter._ensure_initialized(session)
                    flash_usage = await limiter.get_usage('flash')
                    lite_usage = await limiter.get_usage('flash_lite')
                    lines.append(f"  Gemini Flash: {flash_usage['used']}/{flash_usage['max_rpd']} RPD\n  Gemini Lite: {lite_usage['used']}/{lite_usage['max_rpd']} RPD")
                except Exception:
                    pass
                
                # Phase 5.1: Agent Performance Metrics (Stage 1 Bias Accuracy)
                try:
                    from utils.analytics.agent_performance_monitor import compute_agent_accuracy_report
                    agent_report = await compute_agent_accuracy_report(session, days_back=7)
                    stage1_acc = agent_report.get('stage1_bias_accuracy', {})
                    if stage1_acc.get('total_checked', 0) >= 10:
                        lines.append(f"\n<b>Stage 1 Bias Accuracy (7d):</b>")
                        lines.append(f"  Overall: {stage1_acc.get('overall', 0):.1f}% ({stage1_acc.get('total_checked', 0)} checks)")
                        lines.append(f"  Status: {stage1_acc.get('interpretation', 'N/A')}")
                        for currency, data in stage1_acc.get('by_currency', {}).items():
                            flag = '⚠️' if data['accuracy'] < 50 else '✅'
                            lines.append(f"  {flag} {currency}: {data['accuracy']:.0f}% ({data['total']} checks)")
                except Exception as e:
                    logger.debug(f'Agent performance report failed: {e}')
                
                # Phase 5.2: Model Source Performance
                try:
                    from utils.analytics.analysis_tracker import compute_model_source_performance
                    model_perf = await compute_model_source_performance(session, days_back=7)
                    if model_perf.get('by_source'):
                        lines.append(f"\n<b>Model Source Performance (7d):</b>")
                        for source, data in model_perf['by_source'].items():
                            win_rate = data.get('win_rate', 0)
                            flag = '⚠️' if win_rate < 35 else '🟢' if win_rate >= 50 else '🟡'
                            lines.append(f"  {flag} {source}: {win_rate:.0f}% WR ({data['wins']}/{data['total_closed']} closed)")
                except Exception as e:
                    logger.debug(f'Model source performance report failed: {e}')
                
                # Phase 6: Active Calibration Directives & Confidence Ceilings
                try:
                    from database.models import SystemConfig
                    import json as _json
                    from utils.analytics.agent_performance_monitor import get_currency_confidence_ceiling
                    
                    cal_cfg = (await session.execute(
                        select(SystemConfig).where(SystemConfig.key == "news_tier_calibration_directives")
                    )).scalar_one_or_none()
                    
                    lines.append(f"\n<b>System Calibration States:</b>")
                    if cal_cfg and cal_cfg.value:
                        cal_data = _json.loads(cal_cfg.value)
                        if cal_data:
                            lines.append("  News Directives:")
                            for k, v in cal_data.items():
                                lines.append(f"   - {k}: {v}")
                            
                    ceilings = await get_currency_confidence_ceiling(session, days_back=30)
                    if ceilings:
                        lines.append("  Confidence Ceilings:")
                        for cur, cap in ceilings.items():
                            lines.append(f"   - {cur}: Max {cap}")
                except Exception as e:
                    logger.debug(f'Calibration states report failed: {e}')
                
                # LLM Executive Synthesis for Daily Report
                try:
                    from analysis.providers.llm_factory import get_client_for_task
                    client = get_client_for_task("report_synthesizer", self.settings)
                    raw_report = "\n".join(lines)
                    prompt = (
                        "Summarize the following daily trading agent metrics into a concise executive narrative brief "
                        "(2-3 short bullet points highlighting key risks, P&L/health status, and recommended posture for the next 24h):\n\n"
                        f"{raw_report}"
                    )
                    summary = await client.generate_text(prompt, system_prompt="You are the Executive Trading Desk Lead.")
                    if summary and summary.strip():
                        lines.insert(1, f"\n<b>Executive Summary:</b>\n{summary.strip()}\n")
                except Exception as llm_err:
                    logger.debug(f"LLM daily report synthesis fallback to raw: {llm_err}")

                from utils.infra.notifier import AgentNotifier
                await AgentNotifier().send_info("\n".join(lines))
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}")

    async def _refresh_data_sources(self) -> dict:
        macro_sched = getattr(self, "macro_data_scheduler", None)
        if macro_sched is not None:
            return await macro_sched.refresh_macro_data()
        from scheduler.macro_data_scheduler import MacroDataScheduler
        scheduler = MacroDataScheduler(self.settings)
        return await scheduler.refresh_macro_data()

    async def _update_analysis_ground_truth(self) -> None:
        from database.models import AssetAnalysis, PriceOHLCV, PaperTradeRecord
        from datetime import timedelta
        from sqlalchemy import select, func
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            pending = (await session.execute(select(AssetAnalysis).where(AssetAnalysis.decision.in_(['buy', 'sell'])).where(AssetAnalysis.price_at_analysis.is_not(None)).where(AssetAnalysis.direction_correct_4h.is_(None)).where(AssetAnalysis.generated_at < now - timedelta(hours=4)))).scalars().all()
            for analysis in pending:
                target_time_4h = analysis.generated_at + timedelta(hours=4)
                price_4h_bar = (await session.execute(select(PriceOHLCV).where(PriceOHLCV.symbol == analysis.symbol).where(PriceOHLCV.timeframe == 'H4').where(PriceOHLCV.timestamp >= target_time_4h - timedelta(hours=2)).where(PriceOHLCV.timestamp <= target_time_4h + timedelta(hours=2)).order_by(func.abs(func.extract('epoch', PriceOHLCV.timestamp) - target_time_4h.timestamp())).limit(1))).scalar_one_or_none()
                if price_4h_bar and analysis.price_at_analysis:
                    price_change = price_4h_bar.close - analysis.price_at_analysis
                    direction_correct = analysis.decision == 'buy' and price_change > 0 or (analysis.decision == 'sell' and price_change < 0)
                    analysis.price_4h_after = price_4h_bar.close
                    analysis.direction_correct_4h = direction_correct
            await session.commit()
            closed_papers_no_price = (await session.execute(select(PaperTradeRecord, AssetAnalysis).outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id).where(PaperTradeRecord.status == 'closed').where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit'])).where(AssetAnalysis.direction_correct_4h.is_(None)).where(AssetAnalysis.price_at_analysis.is_(None)))).all()
            for paper, analysis in closed_papers_no_price:
                if analysis:
                    analysis.direction_correct_4h = paper.exit_reason == 'tp_hit'
                    analysis.price_4h_after = paper.exit_price
            await session.commit()
        logger.info(f'Ground truth updated for {len(pending)} analyses')

    async def _safe_run_once(self) -> None:
        try:
            from config.settings import load_settings
            self.settings = load_settings()
            asset_cfg = self.settings.get('trading', {})
            new_universe = asset_cfg.get('asset_universe', self.asset_universe)
            new_cycle_hours = self.settings.get('trading', {}).get('schedule', {}).get('analysis_cycle_hours', self.cycle_hours)
            if new_universe != self.asset_universe:
                logger.info(f'Asset universe updated: {self.asset_universe} → {new_universe}')
                self.asset_universe = new_universe
            if new_cycle_hours != self.cycle_hours:
                logger.info(f'Cycle hours updated: {self.cycle_hours} → {new_cycle_hours}')
                self.cycle_hours = new_cycle_hours
            sched_cfg_reload = self.settings.get('trading', {}).get('schedule', {})
            new_timezone = sched_cfg_reload.get('timezone', self.timezone_name)
            new_cycle_times = sched_cfg_reload.get(
                'cycle_times_local', self._default_times_from_interval(new_cycle_hours)
            )
            new_daily_report_time = sched_cfg_reload.get('daily_report_time_local', self.daily_report_time_local)
            new_weekly_report_day = sched_cfg_reload.get('weekly_report_weekday', self.weekly_report_day)
            if new_timezone != self.timezone_name:
                logger.info(f'Schedule timezone updated: {self.timezone_name} → {new_timezone}')
                self.timezone_name = new_timezone
            if new_cycle_times != self.cycle_times_local:
                logger.info(f'Schedule cycle_times_local updated: {self.cycle_times_local} → {new_cycle_times}')
                self.cycle_times_local = new_cycle_times
            if new_daily_report_time != self.daily_report_time_local:
                self.daily_report_time_local = new_daily_report_time
            if new_weekly_report_day != self.weekly_report_day:
                self.weekly_report_day = new_weekly_report_day
            if hasattr(self, '_fundamental') and self._fundamental:
                self._fundamental.settings = self.settings
            if hasattr(self, '_per_asset') and self._per_asset:
                self._per_asset.settings = self.settings
                self._per_asset.asset_universe = self.asset_universe
            if hasattr(self, '_scraper_runner') and self._scraper_runner:
                self._scraper_runner.settings = self.settings
            if hasattr(self, '_execution_service') and self._execution_service:
                self._execution_service.settings = self.settings
            if hasattr(self, '_risk_gate') and self._risk_gate:
                self._risk_gate.settings = self.settings
            try:
                from utils.infra.db_backup import create_backup
                backup_cfg = self.settings.get('database', {}).get('backup', {})
                if backup_cfg.get('enabled', False):
                    now = datetime.now(timezone.utc)
                    if not hasattr(self, '_last_backup') or (now - self._last_backup).total_seconds() > 86400:
                        backup_result = await create_backup(self.settings)
                        self._last_backup = now
                        if backup_result.get('success'):
                            logger.info(f"Daily backup created: {backup_result.get('backup_file')}")
            except Exception as e:
                logger.warning(f'Backup failed (non-fatal): {e}')
            await self.run_once()
            import asyncio
            asyncio.create_task(self._update_analysis_ground_truth())
        except Exception as e:
            logger.exception(f'Unhandled exception in analysis cycle: {e}')
            async with get_session() as session:
                await self._log(session, f'CYCLE CRASHED: {e}', category='error')

    async def _log(self, session: Any, description: str, category: str='analysis') -> None:
        try:
            if not session.is_active:
                session.add(ActivityLog(category='system', description=description, actor='cycle_scheduler'))
            else:
                session.add(ActivityLog(category='system', description=description, actor='cycle_scheduler'))
            await session.commit()
        except Exception as e:
            logger.debug(f'Log write failed (non-fatal): {e}')

    async def _log_summary(self, summary: dict) -> None:
        import json
        async with get_session() as session:
            await self._log(session, f'Cycle summary: {json.dumps(summary, default=str)[:500]}', category='system')
