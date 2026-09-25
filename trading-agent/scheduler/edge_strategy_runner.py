import asyncio, json, logging, time
from typing import Optional
from datetime import timedelta
from sqlalchemy import select
from database.db import get_session
from database.models import AssetAnalysis, Position, PaperTradeRecord, SystemConfig, TradeTrigger, PriceOHLCV
from analysis.strategies.base_strategy import EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from analysis.strategies.pretrade_gate import evaluate_pretrade_gate
from analysis.strategies.decay_monitor import get_strategy_decay_monitor
import utils.clock as clock
from utils.validation.data_validator import validate_data_freshness
from datetime import timezone

logger = logging.getLogger('TradingAgent.EdgeStrategyRunner')


class EdgeStrategyRunner:

    def __init__(
        self,
        settings: dict,
        execution_service=None,
        poll_seconds: int = 60,
        market_data_scheduler=None,
        recovery_event: Optional[asyncio.Event] = None,
    ):
        self.settings = settings
        self.execution_service = execution_service
        self.poll_seconds = poll_seconds
        self.market_data_scheduler = market_data_scheduler
        self.recovery_event = recovery_event
        self._running = False
        self._last_stale_warn_time = 0.0
        self._signal_cooldowns: dict[tuple[str, str], float] = {}
        self._gate_rejection_log_time: dict[tuple[str, str, str], float] = {}
        self.cooldown_seconds = float(
            self.settings.get('trading', {}).get('edge_strategy', {}).get('signal_cooldown_seconds', 3600)
        )

    async def start(self):
        self._running = True
        logger.info('EdgeStrategyRunner started')
        
        # Tunggu recovery selesai sebelum siklus pertama
        if self.recovery_event:
            try:
                await asyncio.wait_for(self.recovery_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                logger.debug("EdgeStrategyRunner: Recovery wait timed out (60s), proceeding.")
        try:
            async with get_session() as session:
                await self.reload_strategies_from_db(session)
        except Exception as db_err:
            logger.debug(f"[EdgeStrategyRunner] Initial DB reload non-fatal: {db_err}")

        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f'EdgeStrategyRunner cycle error: {e}')
            await asyncio.sleep(self.poll_seconds)

    def stop(self):
        self._running = False

    def hot_reload_strategy(self, strategy_id: str, parameters: dict, symbol: Optional[str] = None) -> None:
        """Dynamically hot-reloads strategy parameters without restarting the runner."""
        if not isinstance(parameters, dict):
            return
        edge_cfg = self.settings.setdefault('trading', {}).setdefault('edge_strategy', {})
        if symbol:
            sym_key = f"{strategy_id}_{symbol.upper()}"
            edge_cfg.setdefault(sym_key, {}).update(parameters)
        edge_cfg.setdefault(strategy_id, {}).update(parameters)
        try:
            from analysis.strategies.registry import StrategyRegistry
            StrategyRegistry.hot_reload(strategy_id, parameters, symbol=symbol)
        except Exception as e:
            logger.debug(f"StrategyRegistry hot_reload non-fatal: {e}")
        target = f"'{strategy_id}' ({symbol.upper()})" if symbol else f"'{strategy_id}'"
        logger.info(f"[EdgeStrategyRunner] Hot-reloaded parameters for strategy {target}: {parameters}")

    async def reload_strategies_from_db(self, session) -> dict[str, dict]:
        """Loads all dynamic strategy parameter configurations and candidate alphas from DB."""
        try:
            from analysis.strategies.registry import StrategyRegistry
            loaded = await StrategyRegistry.load_dynamic_parameters(session)
            edge_cfg = self.settings.setdefault('trading', {}).setdefault('edge_strategy', {})
            for strat_id, params in loaded.items():
                edge_cfg.setdefault(strat_id, {}).update(params)
            logger.info(f"[EdgeStrategyRunner] Reloaded {len(loaded)} strategy parameters from DB SystemConfig.")
            return loaded
        except Exception as e:
            logger.warning(f"[EdgeStrategyRunner] Failed to reload strategies from DB: {e}")
            return {}

    async def _is_in_cooldown(self, session, strategy_id: str, symbol: str, now_ts: float) -> bool:
        """Cek cooldown sinyal menggunakan in-memory cache dengan fallback persistent ke database."""
        last_sig_time = self._signal_cooldowns.get((strategy_id, symbol), 0.0)
        if now_ts - last_sig_time < self.cooldown_seconds:
            return True

        # Fallback ke database jika in-memory cache kosong (mis. setelah restart)
        cutoff = clock.now() - timedelta(seconds=self.cooldown_seconds)
        recent_analysis = (await session.execute(
            select(AssetAnalysis.generated_at)
            .where(
                AssetAnalysis.symbol == symbol,
                AssetAnalysis.source_strategy_id == strategy_id,
                AssetAnalysis.generated_at >= cutoff
            )
            .order_by(AssetAnalysis.generated_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if recent_analysis:
            if recent_analysis.tzinfo is None:
                recent_analysis = recent_analysis.replace(tzinfo=timezone.utc)
            self._signal_cooldowns[(strategy_id, symbol)] = recent_analysis.timestamp()
            return True

        return False

    async def run_once(self):
        universe = self.settings.get('trading', {}).get('asset_universe', [])
        data_quality_cfg = self.settings.get('data_quality', {})
        max_ohlcv = data_quality_cfg.get('max_ohlcv_age_hours', {'H4': 8.0})
        async with get_session() as session:
            freshness = await validate_data_freshness(
                session, symbols=universe, timeframes=['H4'],
                max_ohlcv_age_hours=max_ohlcv,
                log_warning=False,
            )
            stale_symbols = set()
            for err in freshness.get('errors', []):
                for u in universe:
                    if u in err:
                        stale_symbols.add(u)
            
            valid_symbols = [s for s in universe if s not in stale_symbols]
            if not valid_symbols:
                # Trigger on-demand sync jika semua data stale
                if self.market_data_scheduler and hasattr(self.market_data_scheduler, 'sync_now'):
                    asyncio.create_task(self.market_data_scheduler.sync_now())

                now_ts = time.time()
                if now_ts - self._last_stale_warn_time >= 3600:
                    self._last_stale_warn_time = now_ts
                    logger.warning(f"EdgeStrategyRunner: all symbols stale, skipping cycle: {freshness.get('errors')}")
                else:
                    logger.debug(f"EdgeStrategyRunner: all symbols stale, skipping cycle: {freshness.get('errors')}")
                return
            elif stale_symbols:
                logger.debug(f"EdgeStrategyRunner: skipping stale symbols {stale_symbols}, evaluating valid {valid_symbols}")

            for symbol in valid_symbols:
                # 1. Pre-check: Jangan evaluasi jika posisi live atau paper trade untuk simbol ini sudah aktif
                open_pos_id = (await session.execute(
                    select(Position.id).where(Position.symbol == symbol, Position.status == 'open').limit(1)
                )).scalar_one_or_none()

                open_paper_id = (await session.execute(
                    select(PaperTradeRecord.id).where(
                        PaperTradeRecord.symbol == symbol,
                        PaperTradeRecord.status.in_(['open', 'pending'])
                    ).limit(1)
                )).scalar_one_or_none()

                if open_pos_id or open_paper_id:
                    logger.debug(
                        f"Active position exists for {symbol} "
                        f"(pos_id={open_pos_id}, paper_id={open_paper_id}), skipping edge signal."
                    )
                    continue

                # 2. Ambil Regime Info terkini untuk filter kompatibilitas rezim di StrategyRegistry
                regime_dict = None
                current_regime = None
                try:
                    from analysis.calculators.regime_classifier import classify_market_regime
                    regime_dict = await classify_market_regime(session, symbol, self.settings)
                    current_regime = regime_dict.get('regime') if regime_dict else None
                except Exception as reg_err:
                    logger.debug(f"classify_market_regime failed for {symbol}: {reg_err}")

                try:
                    signals = await StrategyRegistry.evaluate_all(
                        session, symbol, self.settings, current_regime=current_regime
                    )
                except Exception as e:
                    logger.error(f'evaluate_all failed for {symbol}: {e}')
                    await session.rollback()
                    continue

                # 3. Kumpulkan kandidat sinyal yang lolos gate dasar dan cooldown
                now_ts = time.time()
                candidates = []
                for sig in signals:
                    try:
                        if not sig.direction:
                            continue
                        if await self._is_disabled(session, sig.strategy_id, symbol):
                            continue

                        # Check StrategyDecayMonitor
                        decay_mon = get_strategy_decay_monitor()
                        if not decay_mon.is_tradeable(sig.strategy_id):
                            logger.debug(
                                f"[{sig.strategy_id}] Suppressed by StrategyDecayMonitor (state={decay_mon.get_health(sig.strategy_id).state.value})"
                            )
                            continue

                        # Cooldown check: Cegah materialisasi sinyal berulang dalam interval cooldown
                        if await self._is_in_cooldown(session, sig.strategy_id, symbol, now_ts):
                            logger.debug(
                                f"[{sig.strategy_id}] Signal for {symbol} in cooldown, skipping."
                            )
                            continue

                        strat_type = ('mean_reversion' if 'mean_reversion' in sig.tags
                                      else 'trend' if 'trend' in sig.tags else None)
                        if strat_type:
                            allowed, reason = await evaluate_pretrade_gate(session, symbol, self.settings, strat_type)
                            if not allowed:
                                gate_key = (sig.strategy_id, symbol, str(reason))
                                last_rej = self._gate_rejection_log_time.get(gate_key, 0.0)
                                if now_ts - last_rej >= self.cooldown_seconds:
                                    self._gate_rejection_log_time[gate_key] = now_ts
                                    logger.info(f'[{sig.strategy_id}/{symbol}] pretrade gate: {reason} (throttled {self.cooldown_seconds:.0f}s)')
                                else:
                                    logger.debug(f'[{sig.strategy_id}/{symbol}] pretrade gate: {reason}')
                                continue

                        candidates.append(sig)
                    except Exception as e:
                        logger.error(f'[{sig.strategy_id}] candidate filtering failed for {symbol}: {e}')

                if not candidates:
                    continue

                # 4. Per-Symbol Signal De-duplicator & Quantitative Weighted Conviction Arbiter
                directions = {c.direction.lower() for c in candidates}
                if 'buy' in directions and 'sell' in directions:
                    # Separate candidate directions
                    buy_candidates = [c for c in candidates if c.direction.lower() == 'buy']
                    sell_candidates = [c for c in candidates if c.direction.lower() == 'sell']

                    decay_mon = get_strategy_decay_monitor()
                    def _get_strat_weight(s: EdgeSignal) -> float:
                        health = decay_mon.get_health(s.strategy_id)
                        state_val = getattr(health.state, "value", "healthy").lower()
                        multiplier = 1.0
                        if state_val == "incubating":
                            multiplier = 0.8
                        elif state_val == "degraded":
                            multiplier = 0.5
                        return float(s.confidence or 0.5) * multiplier

                    w_buy = sum(_get_strat_weight(c) for c in buy_candidates)
                    w_sell = sum(_get_strat_weight(c) for c in sell_candidates)
                    total_w = w_buy + w_sell

                    # Supermajority conviction threshold (>= 70% dominance and significant net difference)
                    buy_ratio = w_buy / total_w if total_w > 0 else 0.5
                    sell_ratio = w_sell / total_w if total_w > 0 else 0.5

                    if buy_ratio >= 0.70 and (w_buy - w_sell) >= 0.35:
                        candidates = buy_candidates
                        logger.info(
                            f"[Ensemble] BUY conviction supermajority ({buy_ratio:.1%}, weight={w_buy:.2f} vs {w_sell:.2f}) "
                            f"overrode dissenting sell signal(s) on {symbol}."
                        )
                    elif sell_ratio >= 0.70 and (w_sell - w_buy) >= 0.35:
                        candidates = sell_candidates
                        logger.info(
                            f"[Ensemble] SELL conviction supermajority ({sell_ratio:.1%}, weight={w_sell:.2f} vs {w_buy:.2f}) "
                            f"overrode dissenting buy signal(s) on {symbol}."
                        )
                    else:
                        conflict_ids = [c.strategy_id for c in candidates]
                        logger.warning(
                            f"[Ensemble] Conflicting buy & sell signals on {symbol} across strategies {conflict_ids} "
                            f"without supermajority (BUY={buy_ratio:.1%}, SELL={sell_ratio:.1%}). "
                            f"Suppressing all to prevent market churn/whip."
                        )
                        continue


                if len(candidates) == 1:
                    chosen_signal = candidates[0]
                else:
                    # Multi-signal concordance: Rank by (confidence, sharpe) descending
                    ranked = sorted(
                        candidates,
                        key=lambda s: (
                            float(getattr(s, 'confidence', 0.0) or 0.0),
                            float(getattr(s, 'sharpe', 0.0) or s.meta.get('sharpe', 0.0) or 0.0)
                        ),
                        reverse=True
                    )
                    chosen_signal = ranked[0]
                    # Multi-strategy ensemble confirmation boost
                    base_conf = float(chosen_signal.confidence or 0.5)
                    boosted_conf = min(base_conf + 0.05, 0.95)
                    chosen_signal.confidence = boosted_conf
                    all_ids = [c.strategy_id for c in candidates]
                    chosen_signal.meta['ensemble_confirmed'] = True
                    chosen_signal.meta['ensemble_strategies'] = all_ids
                    logger.info(
                        f"[Ensemble] Multi-strategy concordance on {symbol} ({all_ids}). "
                        f"Selected {chosen_signal.strategy_id} with boosted confidence {boosted_conf:.2f}."
                    )

                # Record cooldown for all agreeing strategies on this symbol
                for c in candidates:
                    self._signal_cooldowns[(c.strategy_id, symbol)] = now_ts

                # 5. Route chosen signal
                try:
                    await self._materialize_and_route(session, chosen_signal, regime_dict=regime_dict)
                except Exception as e:
                    logger.error(f'[{chosen_signal.strategy_id}] routing failed for {symbol}: {e}')
                    await session.rollback()

    async def _is_disabled(self, session, strategy_id: str, symbol: str) -> bool:
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == f'strategy_disabled_{strategy_id}_{symbol}')
        )).scalar_one_or_none()
        return bool(cfg and cfg.value == 'true')

    async def _resolve_reference_price(self, session, sig) -> float | None:
        if sig.strategy_id == 'liquidity_sweep' and sig.meta.get('sweep_price'):
            return float(sig.meta['sweep_price'])
        last_bar = (await session.execute(
            select(PriceOHLCV).where(PriceOHLCV.symbol == sig.symbol)
            .where(PriceOHLCV.timeframe == 'H4')
            .order_by(PriceOHLCV.timestamp.desc()).limit(1)
        )).scalar_one_or_none()
        return float(last_bar.close) if last_bar else None

    async def _materialize_and_route(self, session, sig, regime_dict: Optional[dict] = None) -> None:
        if sig.entry_price is None:
            sig.entry_price = await self._resolve_reference_price(session, sig)
            if sig.entry_price is None:
                logger.error(f'[{sig.strategy_id}] No reference price for {sig.symbol}, cannot route.')
                return

        if sig.stop_loss is None or sig.take_profit is None:
            exit_style = getattr(sig, 'exit_style', 'intraday_adr')
            
            if exit_style == 'intraday_adr':
                from analysis.calculators.intraday_level_optimizer import compute_optimal_levels
                levels = await compute_optimal_levels(
                    session,
                    sig.symbol,
                    sig.direction,
                    sig.entry_price,
                    self.settings,
                    existing_sl=sig.stop_loss,
                    existing_tp=sig.take_profit,
                )
                if 'error' in levels:
                    logger.error(f"[{sig.strategy_id}] compute_optimal_levels failed for {sig.symbol}: {levels['error']}")
                    return
                if not levels.get('entry_allowed', True):
                    reason = levels.get('rejection_reason', 'ADR room exhausted this cycle')
                    logger.info(f"[{sig.strategy_id}] {sig.symbol}: Entry not allowed by level optimizer ({reason}), skipping.")
                    return
                tp_candidates = levels.get('top_tp_candidates') or []
                sl_candidates = levels.get('top_sl_candidates') or []
                if sig.take_profit is None:
                    if not tp_candidates:
                        logger.error(f'[{sig.strategy_id}] No TP candidate for {sig.symbol}.')
                        return
                    sig.take_profit = float(tp_candidates[0]['price'])
                if sig.stop_loss is None:
                    if not sl_candidates:
                        logger.error(f'[{sig.strategy_id}] No SL candidate for {sig.symbol}.')
                        return
                    sig.stop_loss = float(sl_candidates[0]['price'])
            
            elif exit_style == 'trend_trailing':
                from analysis.calculators.intraday_level_optimizer import _get_atr
                atr = await _get_atr(session, sig.symbol)
                if atr <= 0:
                    logger.error(f"[{sig.strategy_id}] Invalid ATR for {sig.symbol}, cannot compute trend SL.")
                    return
                
                trend_cfg = (self.settings.get('trading', {}).get('edge_strategy', {}).get('trend_trailing') or {})
                risk_cfg = self.settings.get('trading', {}).get('risk', {})
                min_rr = float(risk_cfg.get('min_rr_ratio', 1.3))
                mult_map = risk_cfg.get('min_sl_atr_multiplier_by_symbol', {})
                default_sl_mult = trend_cfg.get('sl_atr_multiplier', 1.5)
                mult = mult_map.get(sig.symbol, mult_map.get('default', default_sl_mult))
                
                sl_dist = atr * max(mult, 1.0)
                tp_mult = float(trend_cfg.get('tp_sl_multiplier', 2.5))
                tp_dist = sl_dist * max(tp_mult, min_rr)

                # Optional ADR-based upper bound
                if trend_cfg.get('use_adr_cap', True):
                    try:
                        from analysis.calculators.daily_range_calculator import compute_daily_range_context
                        adr_ctx = await compute_daily_range_context(session, sig.symbol, self.settings)
                        if 'error' not in adr_ctx and adr_ctx.get('adr'):
                            max_tp_adr = adr_ctx['adr'] * float(trend_cfg.get('max_tp_adr_multiple', 1.5))
                            if tp_dist > max_tp_adr and max_tp_adr >= sl_dist * min_rr:
                                tp_dist = max_tp_adr
                    except Exception as e:
                        logger.debug(f"ADR cap calculation failed for {sig.symbol} (non-fatal): {e}")
                
                if sig.direction == 'buy':
                    sig.stop_loss = sig.stop_loss or (sig.entry_price - sl_dist)
                    sig.take_profit = sig.take_profit or (sig.entry_price + tp_dist)
                else:
                    sig.stop_loss = sig.stop_loss or (sig.entry_price + sl_dist)
                    sig.take_profit = sig.take_profit or (sig.entry_price - tp_dist)

        if not sig.entry_price or not sig.stop_loss or not sig.take_profit:
            logger.error(f'[{sig.strategy_id}] Failed to fully resolve entry/SL/TP for {sig.symbol}.')
            return

        # Upstream R:R pre-filter check
        risk_cfg = (self.settings or {}).get('trading', {}).get('risk', {})
        min_rr = float(risk_cfg.get('min_rr_ratio', 1.3))
        sl_dist = abs(sig.entry_price - sig.stop_loss)
        tp_dist = abs(sig.take_profit - sig.entry_price)
        if sl_dist <= 0:
            logger.error(f"[{sig.strategy_id}] Invalid zero SL distance for {sig.symbol}. Aborting route.")
            return
        actual_rr = tp_dist / sl_dist
        if actual_rr < min_rr:
            logger.info(
                f"[{sig.strategy_id}] {sig.symbol} suppressed: R:R ratio {actual_rr:.2f} < minimum {min_rr:.2f} "
                f"(Entry={sig.entry_price}, SL={sig.stop_loss}, TP={sig.take_profit})"
            )
            return

        exempt = set(self.settings.get('trading', {}).get('edge_strategy', {})
                     .get('macro_gate_exempt_strategies', ['gap_fade']))
        if sig.strategy_id not in exempt:
            from analysis.calculators.macro_bias_filter import evaluate_macro_alignment
            macro = await evaluate_macro_alignment(session, sig.symbol, sig.direction, self.settings)
            if macro.get('strong_conflict'):
                logger.info(f"[{sig.strategy_id}] {sig.symbol} {sig.direction} blocked by macro gate: {macro['reasons']}")
                return

        # Arbitrase dengan sinyal LLM terkini via SignalArbitrator
        from analysis.arbitration.signal_arbitrator import SignalArbitrator
        from database.models import VIXData
        from sqlalchemy import or_

        arbitrator = SignalArbitrator(self.settings)

        # 1. Ambil VIX level terkini
        vix_val = 15.0
        try:
            vix_row = (await session.execute(
                select(VIXData).order_by(VIXData.date.desc()).limit(1)
            )).scalar_one_or_none()
            if vix_row and vix_row.close:
                vix_val = float(vix_row.close)
        except Exception:
            pass

        # 2. Ambil Regime Info terkini jika belum tersedia
        if regime_dict is None:
            regime_dict = {}
            try:
                from analysis.calculators.regime_classifier import classify_market_regime
                regime_dict = await classify_market_regime(session, sig.symbol, self.settings)
            except Exception:
                pass

        # 3. Query sinyal LLM terkini
        recent_llm = None
        try:
            res = await session.execute(
                select(AssetAnalysis)
                .where(AssetAnalysis.symbol == sig.symbol)
                .where(
                    or_(
                        AssetAnalysis.decision_source.in_(["llm_debate", "llm_stage2", "langgraph_stage2"]),
                        AssetAnalysis.decision_source.like("%gemini%"),
                        AssetAnalysis.decision_source.like("%claude%"),
                        AssetAnalysis.source_strategy_id.is_(None)
                    )
                )
                .order_by(AssetAnalysis.generated_at.desc())
                .limit(1)
            )
            if hasattr(res, "scalar_one_or_none"):
                recent_llm = res.scalar_one_or_none()
        except Exception as e:
            logger.debug(f"Could not query recent LLM decision for arbitration (non-fatal): {e}")

        llm_dict = None
        if isinstance(recent_llm, AssetAnalysis) and recent_llm.generated_at:
            gen_at = recent_llm.generated_at.replace(tzinfo=timezone.utc) if recent_llm.generated_at.tzinfo is None else recent_llm.generated_at
            if (clock.now() - gen_at).total_seconds() < 21600:  # 6 jam siklus
                ez = {}
                try:
                    ez = json.loads(recent_llm.entry_zone) if recent_llm.entry_zone else {}
                except Exception:
                    pass
                llm_dict = {
                    "decision": recent_llm.decision,
                    "confidence": recent_llm.confidence,
                    "risk_multiplier": recent_llm.risk_multiplier,
                    "entry_price": ez.get("price"),
                    "stop_loss": recent_llm.stop_loss,
                    "take_profit": recent_llm.take_profit,
                    "rationale": recent_llm.rationale,
                    "decision_source": recent_llm.decision_source,
                }

        arb_res = await arbitrator.arbitrate(
            session=session,
            symbol=sig.symbol,
            quant_signal=sig,
            llm_decision=llm_dict,
            vix_level=vix_val,
            regime_info=regime_dict,
        )

        if arb_res.decision in ("avoid", "wait"):
            logger.info(f"[{sig.strategy_id}] {sig.symbol} suppressed by SignalArbitrator: {arb_res.arbitration_reason}")
            return

        sig.confidence = arb_res.confidence
        sig.meta["size_multiplier"] = arb_res.risk_multiplier
        sig.rationale = f"{sig.rationale} | [Arbitrator: {arb_res.selected_source}]"

        import uuid
        pair_group_id = None
        if sig.paired_leg:
            pair_group_id = str(uuid.uuid4())

        async def _materialize_leg(leg: EdgeSignal, is_hedge: bool = False):
            analysis = AssetAnalysis(
                symbol=leg.symbol, generated_at=clock.now(), decision=leg.direction, confidence=leg.confidence,
                entry_zone=json.dumps({'type': 'market', 'price': leg.entry_price}),
                price_at_analysis=leg.entry_price,
                stop_loss=leg.stop_loss, take_profit=leg.take_profit,
                invalidation=f'Strategy exit: {leg.strategy_id}', rationale=leg.rationale,
                decision_source='edge_registry',
                risk_multiplier=float(leg.meta.get('size_multiplier', 1.0)),
            )
            analysis.source_strategy_id = leg.strategy_id
            if pair_group_id:
                analysis.pair_group_id = pair_group_id
            session.add(analysis)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f'[{leg.strategy_id}] Failed to persist analysis for {leg.symbol}: {e}')
                return None
            await session.refresh(analysis)

            max_hold = getattr(leg, 'max_hold_minutes', None)
            if max_hold is not None and max_hold > 0:
                fire_at = (clock.now() + timedelta(minutes=float(max_hold))).isoformat()
                session.add(TradeTrigger(
                    asset_analysis_id=analysis.id, trigger_type='force_close',
                    condition_json=json.dumps({
                        'fire_at': fire_at, 'symbol': leg.symbol,
                        'reason': f"{leg.strategy_id} max_hold_minutes={max_hold} reached "
                                  f"(force_session_close={getattr(leg, 'force_session_close', False)})",
                    }),
                    status='pending',
                ))
                await session.commit()

            ttl_mins = getattr(leg, 'ttl_minutes', None)
            if ttl_mins is not None and ttl_mins > 0:
                expire_at = (clock.now() + timedelta(minutes=float(ttl_mins))).isoformat()
                session.add(TradeTrigger(
                    asset_analysis_id=analysis.id, trigger_type='cancel_pending',
                    condition_json=json.dumps({
                        'fire_at': expire_at, 'symbol': leg.symbol,
                        'reason': f"{leg.strategy_id} ttl_minutes={ttl_mins} reached (order validity expired)",
                    }),
                    status='pending',
                ))
                await session.commit()

            return analysis

        primary_analysis = await _materialize_leg(sig)
        if not primary_analysis:
            return

        analyses_to_execute = [primary_analysis]
        if sig.paired_leg:
            hedge_analysis = await _materialize_leg(sig.paired_leg, is_hedge=True)
            if not hedge_analysis:
                logger.error(f"[{sig.strategy_id}] Failed to materialize hedge leg for {sig.symbol}. Aborting pair.")
                primary_analysis.execution_status = 'cancelled'
                primary_analysis.execution_notes = 'Aborted: hedge leg failed to materialize'
                try:
                    await session.commit()
                except Exception:
                    pass
                return
            analyses_to_execute.append(hedge_analysis)

        # LangGraph Reactive Entry Point (CRITICAL-01)
        try:
            from graph.reactive_graph import get_reactive_graph
            reactive_graph = get_reactive_graph()
            actionable_legs = [
                (a.symbol, {
                    "analysis_id": a.id,
                    "decision": a.decision.lower(),
                    "confidence": a.confidence,
                    "stop_loss": a.stop_loss,
                    "take_profit": a.take_profit,
                    "source_strategy_id": a.source_strategy_id,
                    "pair_group_id": pair_group_id,
                    "arbitrated_by": f"edge_strategy_runner:{sig.strategy_id}",
                }) for a in analyses_to_execute
            ]
            regime_name = (regime_dict.get("regime", "normal") if regime_dict else "normal").lower()
            reactive_state = {
                "symbols": [a.symbol for a in analyses_to_execute],
                "actionable_trades": actionable_legs,
                "event_type": "edge_signal",
                "extra_context": f"Edge strategy execution: {sig.strategy_id}",
                "event_data": {
                    "strategy_id": sig.strategy_id,
                    "analyses": analyses_to_execute,
                    "pair_group_id": pair_group_id,
                    "session": session,
                    "regime_dict": regime_dict,
                },
                "market_regime": regime_name,
                "summary": {},
                "errors": [],
                "should_pause": False,
            }
            config = {"configurable": {"scheduler": self}}
            logger.info(f"[{sig.strategy_id}] Routing edge signal through LangGraph ReactiveStateGraph...")
            await reactive_graph.ainvoke(reactive_state, config=config)
        except Exception as e:
            await session.rollback()
            logger.error(f'[{sig.strategy_id}] Reactive graph execution failed for {sig.symbol}: {e}', exc_info=True)

