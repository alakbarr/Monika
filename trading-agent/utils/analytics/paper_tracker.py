# ==============================================================================
# File: utils/paper_tracker.py
# ==============================================================================

"""
Paper Tracker — Melacak estimasi PnL (profit and loss) untuk mode dry_run.
Secara otomatis mencatat posisi setelah analisis disetujui (buy/sell), 
dan mensimulasikan hasil jika harga mengenai SL atau TP.
"""
import logging
from datetime import datetime, timezone, timedelta
import utils.clock as clock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
from database.models import AssetAnalysis, PriceOHLCV, PaperTradeRecord, Position
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

import asyncio
logger = logging.getLogger("TradingAgent.PaperTracker")

_PAPER_TRACKER_LOCK = asyncio.Lock()

class PaperTracker:
    """
    Memantau posisi paper trade terbuka & melikuidasi saat menyentuh SL/TP.
    Dipanggil setiap siklus oleh CycleScheduler.
    """
    
    def __init__(self, settings: Optional[dict] = None):
        if settings is None:
            try:
                import os, yaml
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                with open(os.path.join(base_dir, 'config', 'settings.yaml'), 'r') as f:
                    self.settings = yaml.safe_load(f)
            except Exception:
                self.settings = {}
        else:
            self.settings = settings

    async def update_paper_trade_sl(self, session: AsyncSession, analysis_id: int, new_sl: float) -> None:
        """Update Stop Loss for an open paper trade (used by TrailingStopManager)."""
        trade = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.analysis_id == analysis_id)
            .where(PaperTradeRecord.status == 'open')
        )).scalar_one_or_none()
        
        if trade:
            trade.stop_loss = new_sl
            logger.debug(f"[PAPER] Updated SL for analysis_id {analysis_id} to {new_sl}")

    async def _close_linked_position(self, session: AsyncSession, trade: PaperTradeRecord) -> None:
        """Mirror PaperTradeRecord closure into the Position table.
        Without this, paper Position rows stay status='open' forever and
        permanently deadlock RiskGate._check_max_positions / _check_no_duplicate.
        """
        if not trade.analysis_id:
            return
        pos = (await session.execute(
            select(Position)
            .where(Position.analysis_id == trade.analysis_id)
            .where(Position.status == 'open')
            .where(Position.is_paper == True)
        )).scalar_one_or_none()
        if pos:
            pos.status = 'closed'
            pos.closed_at = trade.closed_at or datetime.now(timezone.utc)
            logger.debug(f"[PAPER] Linked Position id={pos.id} closed with PaperTradeRecord {trade.id}")

    # -------------------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------------------

    def _get_realistic_spread(self, symbol: str) -> float:
        """Calculate realistic spread utilizing multipliers based on settings.yaml and base spreads."""
        base_spreads = {
            'XAUUSD': 0.15,
            'EURUSD': 0.00008,
            'GBPUSD': 0.00012,
            'USDJPY': 0.012,
            'AUDUSD': 0.00008,
            'XTIUSD': 0.03,
            'XBRUSD': 0.04,
            'BTCUSD': 15.0
        }
        spread = base_spreads.get(symbol, 0.0003)
        
        multipliers = self.settings.get('paper_trading', {}).get('spread_multipliers', {})
        multiplier = multipliers.get(symbol, multipliers.get('default', 1.5))
        spread *= multiplier
        return spread

    async def open_paper_trade(self, session: AsyncSession, analysis: AssetAnalysis, risk_pct: float = 0.75) -> None:
        """Open a paper trade respecting the entry condition type."""
        import json
        
        if not analysis.stop_loss or not analysis.take_profit:
            logger.debug(f'[PAPER] Skipping {analysis.symbol}: missing SL or TP')
            return
        
        # Parse entry condition from analysis
        entry_cond = {}
        if analysis.entry_zone:
            try:
                entry_cond = json.loads(analysis.entry_zone)
            except Exception:
                pass
        
        entry_type = entry_cond.get('type', 'market')
        stated_price = entry_cond.get('price')
        
        # Get current market price from last H4 bar
        last_bar = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == analysis.symbol)
            .where(PriceOHLCV.timeframe == 'H4')
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        if not last_bar:
            logger.warning(f'[PAPER] No H4 bar for {analysis.symbol}, cannot open paper trade')
            return
        
        current_price = last_bar.close
        
        # Dynamic spread
        spread = self._get_realistic_spread(analysis.symbol)
        
        if entry_type == 'market' or stated_price is None:
            # Market order: execute at current price + half spread (for buy) or - half spread (for sell)
            if analysis.decision == 'buy':
                actual_entry = current_price + spread / 2  # Pay the ask
            else:
                actual_entry = current_price - spread / 2  # Hit the bid
            is_pending = False
            
        elif entry_type == 'limit':
            # Limit order: do NOT open immediately
            # Will be filled when price reaches stated_price in check_and_close_trades
            actual_entry = stated_price if stated_price else current_price
            is_pending = True
            logger.info(f'[PAPER] PENDING limit order for {analysis.symbol} {analysis.decision} @ {stated_price} (current: {current_price})')
            
        elif entry_type == 'trigger':
            # Treat trigger as limit at stated price
            actual_entry = stated_price if stated_price else current_price
            is_pending = True
            
        else:
            actual_entry = current_price
            is_pending = False
        
        trade = PaperTradeRecord(
            analysis_id=analysis.id,
            symbol=analysis.symbol,
            direction=analysis.decision,
            entry_price=actual_entry,           # Stated/actual fill price
            stop_loss=analysis.stop_loss,
            take_profit=analysis.take_profit,
            opened_at=clock.now(),
            status='open',
            risk_pct=risk_pct,
            entry_condition_type=entry_type,
            stated_entry_price=stated_price,
            is_pending_fill=is_pending,
            decision_source=getattr(analysis, 'decision_source', None),
            was_debate_modified=bool(getattr(analysis, 'was_debate_modified', False)),
        )
        session.add(trade)
        await session.commit()
        
        if is_pending:
            logger.info(f'[PAPER] PENDING {analysis.symbol} {analysis.decision} @ {actual_entry} (awaiting fill, current={current_price})')
        else:
            logger.info(f'[PAPER] Opened {analysis.symbol} {analysis.decision} @ {actual_entry:.5f} (risk={risk_pct}%)')
    
    async def _get_bars_since_open(self, session: AsyncSession, trade: PaperTradeRecord, timeframe: str):
        """Ambil bars sejak posisi dibuka, termasuk bar yang sedang aktif."""
        start_time = trade.filled_at or trade.opened_at
        age_hours = (clock.now() - start_time).total_seconds() / 3600
        
        # Dynamic limit based on timeframe and age
        if timeframe == 'M15':
            limit = int(age_hours * 4) + 10
        elif timeframe == 'H1':
            limit = int(age_hours) + 10
        else:
            limit = int(age_hours / 4) + 10
            
        limit = min(5000, max(50, limit))

        return list((await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == trade.symbol)
            .where(PriceOHLCV.timeframe == timeframe)
            .where(PriceOHLCV.timestamp >= start_time - timedelta(hours=4))
            .where(PriceOHLCV.timestamp <= clock.now())
            .order_by(PriceOHLCV.timestamp.asc())
            .limit(limit)
        )).scalars().all())

    async def _is_news_environment(self, session: AsyncSession, trade: PaperTradeRecord, bar_timestamp) -> bool:
        """Gunakan database EconomicCalendar untuk deteksi rilis berita High impact."""
        if bar_timestamp is None:
            return False
        try:
            from database.models import EconomicCalendar
            from sqlalchemy import select
            from datetime import timedelta
            # Extract base currency from symbol (e.g. EURUSD -> EUR, XAUUSD -> XAU)
            base_ccy = trade.symbol[:3] if len(trade.symbol) >= 6 else None
            quote_ccy = trade.symbol[3:6] if len(trade.symbol) >= 6 else None
            currencies = [c for c in (base_ccy, quote_ccy, 'USD') if c]
            events = (await session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.currency.in_(currencies))
                .where(EconomicCalendar.impact == 'high')
                .where(EconomicCalendar.event_time >= bar_timestamp - timedelta(minutes=30))
                .where(EconomicCalendar.event_time <= bar_timestamp + timedelta(minutes=30))
                .limit(1)
            )).scalar_one_or_none()
            return events is not None
        except Exception as e:
            logger.debug(f'_is_news_environment check failed (non-fatal, assuming normal): {e}')
            return False

    async def _check_sl_tp(self, session: AsyncSession, trade: PaperTradeRecord, bars, timeframe: str = 'H4') -> Optional[dict]:
        SLIPPAGE_MODEL = {
            'XAUUSD': {'normal': 0.3, 'news': 4.0, 'weekend_open': 8.0, 'off_peak': 1.0},
            'EURUSD': {'normal': 0.00012, 'news': 0.0010, 'weekend_open': 0.0020, 'off_peak': 0.0003},
            'GBPUSD': {'normal': 0.00018, 'news': 0.0015, 'weekend_open': 0.0025, 'off_peak': 0.0005},
            'USDJPY': {'normal': 0.06, 'news': 0.30, 'weekend_open': 0.50, 'off_peak': 0.12},
            'AUDUSD': {'normal': 0.00012, 'news': 0.0008, 'weekend_open': 0.0015, 'off_peak': 0.0003},
            'XTIUSD': {'normal': 0.15, 'news': 1.20, 'weekend_open': 2.50, 'off_peak': 0.40},
            'BTCUSD': {'normal': 50.0, 'news': 300.0, 'weekend_open': 500.0, 'off_peak': 150.0}
        }
        # FIX (P0): pakai model spread realistis per-simbol yang SAMA dengan
        # yang dipakai saat entry (self._get_realistic_spread). Implementasi
        # lama membaca settings.assets.symbols.<SYMBOL>.spread_tolerance --
        # path config yang tidak pernah ada di settings.yaml -- sehingga
        # selalu jatuh ke default generik 0.0003 untuk SEMUA simbol,
        # termasuk XAUUSD/BTCUSD di mana 0.0003 nyaris nol relatif terhadap
        # harga. Ini membuat biaya exit tidak konsisten dengan biaya entry.
        spread = self._get_realistic_spread(trade.symbol)
        try:
            default_risk = float(self.settings.get('trading', {}).get('risk', {}).get('risk_percent_per_trade', 0.5))
            tp_method = self.settings.get('paper_trading', {}).get('tp_detection_method', 'close_price')
            sl_conflict = self.settings.get('paper_trading', {}).get('realistic_sl_tp_conflict', 'sl_wins')
        except Exception:
            default_risk = 0.5
            tp_method = 'close_price'
            sl_conflict = 'sl_wins'

        # Get risk_pct - use stored value or default from settings
        risk_pct = getattr(trade, 'risk_pct', None) or default_risk
        def _get_slip_key(bar_timestamp, is_news):
            if is_news:
                return 'news'
            if bar_timestamp:
                hour = bar_timestamp.hour
                if 21 <= hour <= 23 or 0 <= hour < 2:
                    return 'off_peak'
            return 'normal'

        for bar in bars:
            is_news = await self._is_news_environment(session, trade, bar.timestamp)
            slip_key = _get_slip_key(bar.timestamp, is_news)
            
            is_weekend_open = (
                bar.timestamp and 
                bar.timestamp.weekday() == 6 and  # Sunday
                20 <= bar.timestamp.hour <= 22
            )
            if is_weekend_open:
                slip_key = 'weekend_open'
                
            slippage = SLIPPAGE_MODEL.get(trade.symbol, {}).get(slip_key, spread)
            sl_hit = False
            tp_hit = False

            # ============================================================
            # Symmetrical touch detection for long and short directions
            # Standard MT5 FX OHLCV bars represent BID prices.
            # BUY: closed with SELL -> receives BID price
            # SELL: closed with BUY -> pays ASK = BID + spread
            # ============================================================
            if trade.direction == 'buy':
                # SL hit: BID drops to or below stop loss
                sl_hit = bar.low <= trade.stop_loss
                # TP hit: BID rises to or above take profit
                if tp_method == 'close_price':
                    tp_hit = bar.close >= trade.take_profit
                else:
                    tp_hit = bar.high >= trade.take_profit
            else:  # sell
                # SL hit: BID rises to or above stop loss (close BUY, pays ASK = SL + spread)
                sl_hit = bar.high >= trade.stop_loss
                # TP hit: BID drops to or below take profit (close BUY, pays ASK = TP + spread)
                if tp_method == 'close_price':
                    tp_hit = bar.close <= trade.take_profit
                else:
                    tp_hit = bar.low <= trade.take_profit
            
            # If the same bar touches both boundaries, prioritize SL (conservative risk accounting)
            if sl_hit and tp_hit:
                if sl_conflict == 'sl_wins':
                    tp_hit = False
            
            if not sl_hit and not tp_hit:
                continue
            
            # ============================================================
            # Symmetrical exit price calculation (accounting for half-spread & slippage)
            # ============================================================
            gap_multiplier = 2.0 if is_news else 1.5
            actual_slippage = slippage * gap_multiplier
            # Apply half-spread symmetrically on exit legs for both long and short positions.
            if sl_hit:
                exit_reason = 'sl_hit'
                if trade.direction == 'buy':
                    exit_price = trade.stop_loss - spread / 2 - actual_slippage
                else:
                    exit_price = trade.stop_loss + spread / 2 + actual_slippage
            else:
                exit_reason = 'tp_hit'
                if trade.direction == 'buy':
                    exit_price = trade.take_profit - spread / 2 - slippage * 0.5
                else:
                    exit_price = trade.take_profit + spread / 2 + slippage * 0.5
            
            # Kalkulasi P&L
            if trade.entry_price and trade.stop_loss and exit_price:
                sl_distance = abs(trade.entry_price - trade.stop_loss)
                if trade.direction == 'buy':
                    actual_move = exit_price - trade.entry_price
                else:
                    actual_move = trade.entry_price - exit_price
                
                if sl_distance > 0:
                    rr_achieved = actual_move / sl_distance
                    pnl_pct = risk_pct * rr_achieved
                else:
                    rr_achieved = None
                    pnl_pct = risk_pct if exit_reason == 'tp_hit' else -risk_pct
            else:
                rr_achieved = None
                pnl_pct = risk_pct if exit_reason == 'tp_hit' else -risk_pct

            if trade.opened_at and bar.timestamp:
                holding_hours = (bar.timestamp - trade.opened_at).total_seconds() / 3600.0
            else:
                holding_hours = 0.0
            trade.holding_hours = holding_hours

            if holding_hours > 24:
                swap_enabled = self.settings.get('trading', {}).get('edge_strategy', {}).get('swap_modeling_enabled', True)
                if swap_enabled:
                    from utils.market.swap_estimator import estimate_swap_cost
                    swap_abs = await estimate_swap_cost(trade.symbol, trade.direction, 1.0, holding_hours)
                    init_bal = float(self.settings.get('paper_trading', {}).get('initial_balance', 10000.0) or 10000.0)
                    pnl_pct += (swap_abs / max(1.0, init_bal) * 100)

            trade.status = 'closed'
            trade.closed_at = bar.timestamp
            trade.slippage_applied = slippage if exit_reason == 'sl_hit' else 0.0
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason[:100]
            trade.detection_method = f'{tp_method}_tp_{sl_conflict}_sl'[:100]
            trade.pnl_pct = round(pnl_pct, 4)

            return {
                'symbol': trade.symbol,
                'direction': trade.direction,
                'entry': trade.entry_price,
                'exit': trade.exit_price,
                'pnl_pct': trade.pnl_pct,
                'exit_reason': trade.exit_reason,
                'holding_hours': trade.holding_hours,
                'rr_achieved': rr_achieved,
                'detection_tf': timeframe
            }
        return None

    async def check_and_close_trades(self, session: AsyncSession) -> list[dict]:
        """Check and close paper trades using M15 data for accuracy."""
        async with _PAPER_TRACKER_LOCK:
            closed = []
            open_trades = (await session.execute(
                select(PaperTradeRecord).where(PaperTradeRecord.status == 'open')
            )).scalars().all()
            
            now = clock.now()
            MAX_TRADE_AGE_HOURS = float(self.settings.get('paper_trading', {}).get('max_paper_trade_holding_hours', 48))
            
            for trade in open_trades:
                result = None
                try:
                    # NEW: Force close sangat tua trades yang mungkin stuck karena data issue
                    if trade.opened_at:
                        age_hours = (now - trade.opened_at).total_seconds() / 3600
                        if age_hours > MAX_TRADE_AGE_HOURS:
                            # Coba dapatkan current price untuk estimate P&L
                            last_bar = (await session.execute(
                                select(PriceOHLCV)
                                .where(PriceOHLCV.symbol == trade.symbol)
                                .where(PriceOHLCV.timeframe == 'H4')
                                .order_by(PriceOHLCV.timestamp.desc())
                                .limit(1)
                            )).scalar_one_or_none()
                            
                            if last_bar:
                                exit_price = last_bar.close
                                if trade.entry_price:
                                    move = exit_price - trade.entry_price
                                    if trade.direction == 'sell':
                                        move = -move
                                    sl_dist = abs(trade.entry_price - trade.stop_loss) if trade.stop_loss else 1
                                    pnl_pct = (move / sl_dist) * (trade.risk_pct or 0.75) if sl_dist > 0 else 0
                                else:
                                    pnl_pct = 0
                            else:
                                exit_price = trade.entry_price
                                pnl_pct = 0
                            
                            trade.status = 'closed'
                            trade.closed_at = now
                            trade.exit_price = exit_price
                            trade.exit_reason = 'max_holding_time'
                            trade.pnl_pct = round(pnl_pct, 4)
                            trade.holding_hours = age_hours
                            await self._close_linked_position(session, trade)
                            logger.warning(f'[PAPER] Force-closed {trade.symbol} after {age_hours:.0f}h (max holding time)')
                            closed.append({'symbol': trade.symbol, 'exit_reason': 'max_holding_time', 'pnl_pct': pnl_pct})
                            try:
                                await self._record_factor_outcomes(session, trade)
                            except Exception as e:
                                logger.debug(f'Factor outcome recording failed (non-fatal): {e}')
                            continue
                    
                    # Step 1: Handle pending limit orders - check if price reached entry level
                    if getattr(trade, 'is_pending_fill', False) and trade.stated_entry_price:
                        was_filled = await self._try_fill_pending_order(session, trade)
                        if not was_filled:
                            # Check if order has expired (pending for more than 48h)
                            age_hours = (clock.now() - trade.opened_at).total_seconds() / 3600
                            if age_hours > 48:
                                trade.status = 'closed'
                                trade.closed_at = clock.now()
                                trade.exit_reason = 'expired_limit'
                                trade.pnl_pct = 0.0
                                trade.exit_price = trade.entry_price
                                await self._close_linked_position(session, trade)
                                logger.info(f'[PAPER] EXPIRED limit order {trade.symbol} {trade.direction} (never filled after 48h)')
                                try:
                                    await self._record_factor_outcomes(session, trade)
                                except Exception as e:
                                    logger.debug(f'Factor outcome recording failed (non-fatal): {e}')
                            continue  # Skip SL/TP check if still pending
                    
                    # Step 2: Try to detect SL/TP - adaptive TF based on trade age
                    result = None
                    trade_age_h = (clock.now() - trade.opened_at).total_seconds() / 3600
                    tfs_to_check = ['M15', 'H1'] if trade_age_h < 24 else ['H1', 'H4']
                    
                    for timeframe in tfs_to_check:
                        bars = await self._get_bars_since_open(session, trade, timeframe)
                        if bars:
                            result = await self._check_sl_tp(session, trade, bars, timeframe)
                            if result:
                                break
                    
                    if result:
                        closed.append(result)
                        await self._close_linked_position(session, trade)
                        logger.info(
                            f"[PAPER] Closed {trade.symbol} {trade.direction}: "
                            f"{result['exit_reason']}, P&L={result['pnl_pct']:.2f}%, "
                            f"detected_on={result.get('detection_tf', 'unknown')}"
                        )
                        
                        # IMP-11: Record individual factor outcomes for attribution analysis
                        try:
                            await self._record_factor_outcomes(session, trade)
                        except Exception as e:
                            logger.debug(f'Factor outcome recording failed (non-fatal): {e}')
                            
                        # Task 1.1: Improved Post-Trade Closed-Loop Analysis
                        try:
                            from utils.analytics.trade_autopsy import run_trade_autopsy
                            await run_trade_autopsy(session, trade)
                        except Exception as e:
                            logger.debug(f'Trade autopsy failed (non-fatal): {e}')
                            
                        if trade.analysis_id:
                            try:
                                from analysis.memory.outcome_linker import OutcomeLinker
                                await OutcomeLinker(self.settings).process_closed_position(
                                    session, 
                                    analysis_id=trade.analysis_id, 
                                    pnl=trade.pnl_pct or 0.0, 
                                    holding_hours=trade.holding_hours or 0.0, 
                                    exit_reason=trade.exit_reason or "unknown"
                                )
                            except Exception as e:
                                logger.debug(f'OutcomeLinker failed (non-fatal): {e}')
                except Exception as e:
                    logger.error(f'[PAPER] Trade {trade.id} ({trade.symbol}) check failed, skipping this cycle: {e}')
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    # If this trade had partially appended a result before failing, remove it
                    if result and result in closed:
                        closed.remove(result)
                    continue
            
            if closed or any(t.status == 'closed' and t.exit_reason == 'expired_limit' for t in open_trades):
                await session.commit()
                await self.check_recent_streak(session)
            
            return closed

    async def _record_factor_outcomes(self, session: AsyncSession, trade: PaperTradeRecord) -> None:
        """IMP-11: Record individual confluence factor outcomes after a trade closes."""
        import json as _json
        from database.models import AssetAnalysis, ConfluenceFactorOutcome

        if not trade.analysis_id:
            return

        try:
            analysis = (await session.execute(
                select(AssetAnalysis).where(AssetAnalysis.id == trade.analysis_id)
            )).scalar_one_or_none()

            if not analysis or not analysis.confluence_factors_json:
                return

            factors_raw = _json.loads(analysis.confluence_factors_json)
            # Normalize: factors may be list or dict
            if isinstance(factors_raw, list):
                active_factors = set(factors_raw)
            elif isinstance(factors_raw, dict):
                active_factors = {k for k, v in factors_raw.items() if v}
            else:
                active_factors = set()

            ALL_POSSIBLE_FACTORS = [
                'fundamental_bias', 'dxy_confirms', 'd1_trend', 'rsi_neutral',
                'near_fvg', 'near_order_block', 'in_ote_zone', 'near_sr_zone',
                'cot_aligned', 'vix_ok', 'post_event_entry', 'session_prime',
            ]

            for factor in ALL_POSSIBLE_FACTORS:
                outcome_row = ConfluenceFactorOutcome(
                    paper_trade_id=trade.id,
                    analysis_id=trade.analysis_id,
                    symbol=trade.symbol,
                    factor_name=factor,
                    was_present=factor in active_factors,
                    trade_outcome=trade.exit_reason,
                    pnl_pct=trade.pnl_pct,
                )
                session.add(outcome_row)
            # Commit handled by caller
        except Exception as e:
            logger.debug(f'_record_factor_outcomes inner error: {e}')

    async def _try_fill_pending_order(self, session: AsyncSession, trade: PaperTradeRecord) -> bool:
        """Check if a pending limit order has been filled. Returns True if filled."""
        bars = await self._get_bars_since_open(session, trade, 'M15')
        if not bars:
            bars = await self._get_bars_since_open(session, trade, 'H1')
        if not bars:
            bars = await self._get_bars_since_open(session, trade, 'H4')
        if not bars:
            return False
        
        stated_entry = trade.stated_entry_price
        if stated_entry is None:
            return False
        
        for bar in bars:
            # For BUY limit: price must drop to or below the limit price
            if trade.direction == 'buy' and bar.low <= stated_entry:
                # Filled at stated entry price (limit order)
                trade.entry_price = stated_entry
                trade.is_pending_fill = False
                trade.filled_at = bar.timestamp
                logger.info(f'[PAPER] BUY LIMIT FILLED {trade.symbol} @ {stated_entry:.5f}')
                await session.commit()
                return True
            
            # For SELL limit: price must rise to or above the limit price
            elif trade.direction == 'sell' and bar.high >= stated_entry:
                trade.entry_price = stated_entry
                trade.is_pending_fill = False
                trade.filled_at = bar.timestamp
                logger.info(f'[PAPER] SELL LIMIT FILLED {trade.symbol} @ {stated_entry:.5f}')
                await session.commit()
                return True
        
        return False
    async def get_suspended_symbols(self, session: AsyncSession) -> list[str]:
        """Return list of symbols currently suspended due to poor performance"""
        from database.models import SystemConfig
        from sqlalchemy import select
        
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'suspended_symbols')
        )).scalar_one_or_none()
        
        if not cfg or not cfg.value:
            return []
        
        try:
            import json
            data = json.loads(cfg.value)
            now = clock.now()
            # Filter out suspensions that have expired
            active = [
                s for s in data 
                if datetime.fromisoformat(s['until']) > now
            ]
            return [s['symbol'] for s in active]
        except Exception:
            return []

    async def check_and_suspend_poor_performers(
        self, 
        session: AsyncSession,
        settings: dict
    ) -> list[str]:
        """
        Auto-suspend symbols with consecutive losses.
        Returns list of newly suspended symbols.
        Respects trading.paper_trading.streak_loss_policy and prevents infinite re-suspension loop.
        """
        from database.models import PaperTradeRecord, SystemConfig
        from sqlalchemy import select
        import json
        
        paper_cfg = settings.get('trading', {}).get('paper_trading', {})
        streak_policy = paper_cfg.get('streak_loss_policy', 'warn_and_scale')
        is_auto_execute = settings.get('trading', {}).get('auto_execute', False)

        # Jika paper exploration mode (disabled / warn_and_scale) dan bukan live trading:
        if not is_auto_execute and streak_policy in ('disabled', 'warn_and_scale'):
            logger.debug(f"[PaperTracker] Skipping auto-suspension (streak_loss_policy: '{streak_policy}')")
            return []

        newly_suspended = []
        max_consecutive_losses = settings.get('trading', {}).get('risk', {}).get(
            'max_consecutive_losses_per_symbol', 3
        )
        suspension_hours = paper_cfg.get('suspension_hours', settings.get('trading', {}).get('risk', {}).get(
            'suspension_hours_after_consecutive_losses', 12
        ))
        
        asset_universe = settings.get('trading', {}).get('asset_universe', [])
        
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'suspended_symbols')
        )).scalar_one_or_none()
        
        current = []
        if cfg and cfg.value:
            try:
                current = json.loads(cfg.value)
            except Exception:
                current = []
                
        now = clock.now()
        
        for symbol in asset_universe:
            # FIX INFINITE LOOP: Cek apakah simbol ini sebelumnya pernah di-suspend
            prev_entry = next((s for s in current if s.get('symbol') == symbol), None)
            last_suspended_until = None
            if prev_entry and 'until' in prev_entry:
                try:
                    last_suspended_until = datetime.fromisoformat(prev_entry['until'])
                except Exception:
                    last_suspended_until = None

            query = (
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.status == 'closed')
                .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
            )
            # Jika suspensi sebelumnya telah expired, HANYA hitung trade yang ditutup SETELAH masa suspensi berakhir
            if last_suspended_until and last_suspended_until <= now:
                query = query.where(PaperTradeRecord.closed_at > last_suspended_until)

            recent = (await session.execute(
                query.order_by(PaperTradeRecord.closed_at.desc()).limit(max_consecutive_losses + 1)
            )).scalars().all()
            
            consecutive_losses = 0
            for trade in recent:
                if trade.exit_reason == 'sl_hit':
                    consecutive_losses += 1
                else:
                    break
            
            if consecutive_losses >= max_consecutive_losses:
                # Suspend this symbol
                until = (now + timedelta(hours=suspension_hours)).isoformat()
                
                # Remove old entry for this symbol if exists
                current = [s for s in current if s.get('symbol') != symbol]
                current.append({
                    'symbol': symbol,
                    'suspended_at': now.isoformat(),
                    'until': until,
                    'reason': f'{consecutive_losses} consecutive losses'
                })
                
                newly_suspended.append(symbol)
                logger.warning(f'AUTO-SUSPENDED {symbol}: {consecutive_losses} consecutive SL hits. Suspended for {suspension_hours}h.')
                
                try:
                    from utils.infra.notifier import AgentNotifier
                    await AgentNotifier().send_warning(
                        f'⏸️ <b>{symbol} Auto-Suspended</b>\n'
                        f'{consecutive_losses} consecutive losses detected.\n'
                        f'Suspended for {suspension_hours}h until {until[:16]} UTC.\n'
                        f'Review recent analyses to identify systematic issue.'
                    )
                except Exception:
                    pass
        
        if newly_suspended:
            if cfg:
                cfg.value = json.dumps(current)
            else:
                session.add(SystemConfig(key='suspended_symbols', value=json.dumps(current)))
            await session.commit()
            
        return newly_suspended

    async def unsuspend_symbol(self, session: AsyncSession, symbol: str) -> bool:
        """Buka suspensi untuk simbol tertentu."""
        from database.models import SystemConfig
        from sqlalchemy import select
        import json

        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'suspended_symbols')
        )).scalar_one_or_none()
        if not cfg or not cfg.value:
            return False
        try:
            current = json.loads(cfg.value)
            new_list = [s for s in current if s.get('symbol', '').upper() != symbol.upper()]
            if len(new_list) != len(current):
                cfg.value = json.dumps(new_list)
                await session.commit()
                logger.info(f"[PaperTracker] Symbol {symbol} unsuspended successfully.")
                return True
        except Exception as e:
            logger.error(f"Failed to unsuspend {symbol}: {e}")
        return False

    async def unsuspend_all(self, session: AsyncSession) -> list[str]:
        """Buka suspensi untuk semua simbol."""
        from database.models import SystemConfig
        from sqlalchemy import select
        import json

        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == 'suspended_symbols')
        )).scalar_one_or_none()
        if not cfg or not cfg.value:
            return []
        try:
            current = json.loads(cfg.value)
            cleared_symbols = [s.get('symbol') for s in current if s.get('symbol')]
            cfg.value = json.dumps([])
            await session.commit()
            logger.info(f"[PaperTracker] All symbols unsuspended: {cleared_symbols}")
            return cleared_symbols
        except Exception as e:
            logger.error(f"Failed to unsuspend all: {e}")
            return []

    async def get_streak_status(self, session: AsyncSession, symbol: str) -> dict:
        """Mengambil status streak loss dan suspensi untuk simbol tertentu."""
        from database.models import PaperTradeRecord
        from sqlalchemy import select
        
        recent = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == symbol)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(5)
        )).scalars().all()
        
        consecutive_losses = 0
        for trade in recent:
            if trade.exit_reason == 'sl_hit':
                consecutive_losses += 1
            else:
                break
                
        suspended_list = await self.get_suspended_symbols(session)
        is_suspended = symbol in suspended_list
        
        paper_cfg = self.settings.get('trading', {}).get('paper_trading', {}) if hasattr(self, 'settings') and self.settings else {}
        streak_policy = paper_cfg.get('streak_loss_policy', 'warn_and_scale')
        
        return {
            'symbol': symbol,
            'consecutive_losses': consecutive_losses,
            'is_suspended': is_suspended,
            'streak_policy': streak_policy,
        }

    
    async def get_statistics(self, session: AsyncSession, days_back: Optional[int] = None, symbol: Optional[str] = None) -> dict:
        """Hitung win rate dan statistik performa komprehensif."""
        from sqlalchemy import select
        from datetime import datetime, timezone, timedelta
        
        query = (
            select(PaperTradeRecord, AssetAnalysis)
            .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
            .where(PaperTradeRecord.status == 'closed')
        )
        if days_back is not None:
            since = clock.now() - timedelta(days=days_back)
            query = query.where(PaperTradeRecord.closed_at >= since)
        if symbol is not None:
            query = query.where(PaperTradeRecord.symbol == symbol)
            
            
        results = (await session.execute(query)).all()
        
        if not results:
            return {
                "total_trades": 0,
                "market_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_market_pct": 0.0,
                "win_rate_operational_pct": 0.0,
                "win_rate_pct": 0.0,
                "avg_pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "avg_rr_achieved": 0.0,
                "expectancy_per_trade_pct": 0.0,
                "expectancy_per_trade_R": 0.0,
                "has_positive_edge": False,
                "edge_alert": False,
                "by_confluence": {},
                "by_priced_in": {},
                "session_buckets": {
                    'tokyo_00_08': {'label': 'Tokyo (00:00-08:00 UTC)', 'wins': 0, 'total': 0},
                    'london_08_13': {'label': 'London Pre-Overlap (08:00-13:00 UTC)', 'wins': 0, 'total': 0},
                    'overlap_13_16': {'label': 'NY-London Overlap (13:00-16:00 UTC)', 'wins': 0, 'total': 0},
                    'ny_16_21': {'label': 'NY Post-London (16:00-21:00 UTC)', 'wins': 0, 'total': 0},
                    'offpeak_21_00': {'label': 'Off-Peak (21:00-00:00 UTC)', 'wins': 0, 'total': 0},
                },
                "avg_win_hold_hours": 0.0,
                "avg_loss_hold_hours": 0.0,
                "by_symbol": {},
                "by_symbol_direction": {},
                "recent_20": [],
            }
            
        # Pisahkan list paper trades (r) dan list tuples untuk iterasi
        records = [r for r, a in results]
        
        tp_hits = [r for r in records if r.exit_reason == "tp_hit"]
        sl_hits = [r for r in records if r.exit_reason == "sl_hit"]
        pnl_values = [r.pnl_pct or 0 for r in records]
        
        market_records = [r for r in records if r.exit_reason in MARKET_OUTCOME_EXIT_REASONS]
        
        avg_win_pct = sum(r.pnl_pct or 0 for r in tp_hits) / len(tp_hits) if tp_hits else 0
        avg_loss_pct = abs(sum(r.pnl_pct or 0 for r in sl_hits) / len(sl_hits)) if sl_hits else 0
        
        market_total = len(market_records)
        win_rate_market = len(tp_hits) / market_total if market_total > 0 else 0
        loss_rate_market = 1 - win_rate_market if market_total > 0 else 0
        
        win_rate_operational = len(tp_hits) / len(records) if records else 0
        
        # Expectancy per trade
        expectancy = (win_rate_market * avg_win_pct) - (loss_rate_market * avg_loss_pct)
        avg_rr = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 0
        expectancy_r = (win_rate_market * avg_rr) - loss_rate_market

        # Compute extended metrics (Confluence, Priced In, Sessions, Durations)
        by_confluence = {}
        by_priced_in = {}
        session_buckets = {
            'tokyo_00_08': {'label': 'Tokyo (00:00-08:00 UTC)', 'wins': 0, 'total': 0},
            'london_08_13': {'label': 'London Pre-Overlap (08:00-13:00 UTC)', 'wins': 0, 'total': 0},
            'overlap_13_16': {'label': 'NY-London Overlap (13:00-16:00 UTC)', 'wins': 0, 'total': 0},
            'ny_16_21': {'label': 'NY Post-London (16:00-21:00 UTC)', 'wins': 0, 'total': 0},
            'offpeak_21_00': {'label': 'Off-Peak (21:00-00:00 UTC)', 'wins': 0, 'total': 0},
        }
        
        win_durations = []
        loss_durations = []
        
        for r, a in results:
            is_win = (r.pnl_pct or 0) > 0
            
            # Confluence
            if a and a.confluence_score is not None:
                cs = a.confluence_score
                cb = f"{cs}"
                if cb not in by_confluence:
                    by_confluence[cb] = {"wins": 0, "total": 0}
                by_confluence[cb]["total"] += 1
                if is_win:
                    by_confluence[cb]["wins"] += 1
                    
            # Priced In
            if a and a.priced_in_score is not None:
                ps = a.priced_in_score
                pb = f"pi_{ps}"
                if pb not in by_priced_in:
                    by_priced_in[pb] = {"score": ps, "wins": 0, "total": 0}
                by_priced_in[pb]["total"] += 1
                if is_win:
                    by_priced_in[pb]["wins"] += 1
                    
            # Sessions
            if r.opened_at:
                h = r.opened_at.hour
                if 0 <= h < 8: key = 'tokyo_00_08'
                elif 8 <= h < 13: key = 'london_08_13'
                elif 13 <= h < 16: key = 'overlap_13_16'
                elif 16 <= h < 21: key = 'ny_16_21'
                else: key = 'offpeak_21_00'
                session_buckets[key]['total'] += 1
                if is_win:
                    session_buckets[key]['wins'] += 1
                    
            # Durations
            if r.holding_hours:
                if is_win:
                    win_durations.append(r.holding_hours)
                else:
                    loss_durations.append(r.holding_hours)

        history = []
        for record in records:
            history.append({
                'symbol': record.symbol,
                'direction': record.direction,
                'exit_reason': record.exit_reason,
                'pnl_pct': record.pnl_pct or 0,
                'opened_at': record.opened_at.isoformat() if record.opened_at else None,
                'closed_at': record.closed_at.isoformat() if record.closed_at else None,
            })

        return {
            "total_trades": len(records),
            "market_trades": market_total,
            "wins": len(tp_hits),
            "losses": len(sl_hits),
            "win_rate_market_pct": round(win_rate_market * 100, 1),
            "win_rate_operational_pct": round(win_rate_operational * 100, 1),
            "win_rate_pct": round(win_rate_market * 100, 1),
            "avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 4) if len(pnl_values) > 0 else 0,
            "total_pnl_pct": round(sum(pnl_values), 4),
            "avg_win_pct": round(avg_win_pct, 3),
            "avg_loss_pct": round(avg_loss_pct, 3),
            "avg_rr_achieved": round(avg_rr, 2),
            "expectancy_per_trade_pct": round(expectancy, 4),
            "expectancy_per_trade_R": round(expectancy_r, 3),
            "has_positive_edge": expectancy > 0,
            "edge_alert": expectancy < -0.1,
            "by_confluence": by_confluence,
            "by_priced_in": by_priced_in,
            "session_buckets": session_buckets,
            "avg_win_hold_hours": sum(win_durations) / len(win_durations) if win_durations else 0,
            "avg_loss_hold_hours": sum(loss_durations) / len(loss_durations) if loss_durations else 0,
            "by_symbol": _group_by_symbol(history),
            "by_symbol_direction": _group_by_symbol_direction(history),
            "recent_20": [{'symbol': h['symbol'], 'exit_reason': h['exit_reason'], 'pnl_pct': h['pnl_pct']} for h in history[-20:]],
        }

    async def check_and_alert_winrate(self, session: AsyncSession, settings: dict, min_trades: int = 10) -> None:
        """
        Kirim alert jika win rate jatuh di bawah batas minimum (breakeven).
        Berjalan setiap kali paper trade selesai (closed).
        """
        stats = await self.get_statistics(session)
        total = stats.get("total_trades", 0)
        
        if total < min_trades:  # Butuh minimal trades untuk statistik yang valid
            return
        
        win_rate = stats.get("win_rate_pct", 0)
        
        # Ambang batas lebih dinamis berdasarkan R:R minimal
        risk_cfg = settings.get("trading", {}).get("risk", {})
        min_rr = risk_cfg.get("min_rr_ratio", 1.3)
        
        # Breakeven WR% = 100 / (1 + RR)
        breakeven_wr = 100 / (1 + min_rr)
        # Alert threshold = breakeven_wr + 5% (buffer)
        alert_threshold = breakeven_wr + 5
        
        if win_rate < alert_threshold:
            # Generate insight
            by_symbol = stats.get("by_symbol", {})
            worst_symbol = ""
            worst_pnl = 0
            for sym, s_stats in by_symbol.items():
                sym_pnl = s_stats.get("total_pnl_pct", s_stats.get("pnl_pct", 0))
                if sym_pnl < worst_pnl:
                    worst_pnl = sym_pnl
                    worst_symbol = sym
                    
            msg = (
                f"🚨 <b>Win Rate Alert</b>\n"
                f"Paper trading win rate: {win_rate:.1f}% ({total} trades)\n"
                f"Below minimum threshold: {alert_threshold:.1f}% (Breakeven: {breakeven_wr:.1f}%)\n\n"
                f"System may NOT have statistical edge.\n"
            )
            if worst_symbol:
                msg += f"⚠️ Worst performing asset: {worst_symbol} ({worst_pnl:.2f}% PnL)\n"
                
            msg += (
                f"\nAction needed:\n"
                f"• Wait for next Performance Notes generation\n"
                f"• Increase confluence threshold\n"
                f"• Disable {worst_symbol} if bleeding continues"
            )
            
            logger.warning(f"Win rate alert: {win_rate:.1f}% < {alert_threshold:.1f}%")
            try:
                from utils.infra.notifier import AgentNotifier
                await AgentNotifier().send_critical(msg)
            except Exception:
                pass

    async def should_regenerate_performance_notes(self, session: AsyncSession) -> tuple[bool, str]:
        """
        Returns (should_regenerate: bool, reason: str).
        Triggers on: win rate < 40% after 10+ trades, or 10+ new trades since last generation.
        """
        from database.models import SystemConfig
        from sqlalchemy import select
        
        stats = await self.get_statistics(session)
        total = stats.get("total_trades", 0)
        win_rate = stats.get("win_rate_pct", 50)
        
        MIN_TRADES_FOR_INITIAL = 15
        if total < MIN_TRADES_FOR_INITIAL:
            return False, f"insufficient_data ({total}/{MIN_TRADES_FOR_INITIAL} trades)"
            
        # Check autopsy patterns yang mengindikasikan systematic issue
        autopsy_keys = (await session.execute(
            select(SystemConfig.key)
            .where(SystemConfig.key.like('autopsy_%'))
            .where(SystemConfig.value.like('%"severity": "high"%'))
        )).scalars().all()

        if len(autopsy_keys) >= 3:
            # Ada 3+ high-severity patterns dari autopsy → regenerate
            return (True, f'high_severity_autopsy_patterns_detected ({len(autopsy_keys)} patterns)')
        
        # Check last generation time
        last_gen_key = "performance_notes_last_gen"
        last_gen_cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == last_gen_key)
        )).scalar_one_or_none()
        
        if not last_gen_cfg or not last_gen_cfg.value:
            return True, "first_generation"
        
        import json
        last_gen_data = {}
        try:
            last_gen_data = json.loads(last_gen_cfg.value)
        except Exception:
            return True, "corrupted_state"
        
        last_gen_total = last_gen_data.get("total_trades", 0)
        last_gen_time_str = last_gen_data.get("timestamp", "2020-01-01")
        # Handle cases where timestamp might not have timezone info or is invalid
        try:
            last_gen_time = datetime.fromisoformat(last_gen_time_str)
            if last_gen_time.tzinfo is None:
                last_gen_time = last_gen_time.replace(tzinfo=timezone.utc)
        except ValueError:
            last_gen_time = clock.now() - timedelta(days=8)
            
        hours_since = (clock.now() - last_gen_time).total_seconds() / 3600
        
        # Trigger conditions:
        # Require minimum 20 trades before triggering critical status.
        # Win rate of 35% over 10-12 trades is within normal statistical variance
        # for a profitable system and should not trigger system-wide throttling.
        MIN_TRADES_FOR_CRITICAL = 20
        MIN_TRADES_FOR_POOR = 15

        if win_rate < 35 and hours_since >= 6 and total >= MIN_TRADES_FOR_CRITICAL:
            return True, f'critical_win_rate_{win_rate:.0f}pct_over_{total}_trades'

        if win_rate < 40 and hours_since >= 12 and total >= MIN_TRADES_FOR_POOR:
            return True, f'poor_win_rate_{win_rate:.0f}pct_over_{total}_trades'
        
        if total - last_gen_total >= 5:  # 5 new trades since last gen
            return True, f"5_new_trades_since_last_gen"
            
        # TAMBAHKAN: Trigger on consecutive losses (losing streak detection)
        recent = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(4)
        )).scalars().all()
        if len(recent) >= 4 and all(r.exit_reason == "sl_hit" for r in recent):
            return True, "4_consecutive_losses_detected"
        
        if hours_since >= 24 * 7:  # Weekly regardless (existing Monday behavior)
            return True, "weekly_scheduled"
        
        return False, "no_trigger"

    async def check_recent_streak(self, session: AsyncSession, lookback: int = 5) -> dict:
        """
        Deteksi losing streak mendadak (misal: 5 kerugian beruntun memicu alarm).
        Lebih sensitif mendeteksi kelemahan dibanding metrik all-time win rate.
        """
        recent = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.exit_reason.in_(["sl_hit", "tp_hit"]))
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(lookback)
        )).scalars().all()
        
        if len(recent) < lookback:
            return {"streak_data": "insufficient", "count": len(recent)}
        
        losses = [r for r in recent if r.exit_reason == "sl_hit"]
        wins = [r for r in recent if r.exit_reason == "tp_hit"]
        recent_wr = len(wins) / len(recent) * 100
        
        result = {
            "lookback": lookback,
            "recent_win_rate": recent_wr,
            "recent_wins": len(wins),
            "recent_losses": len(losses),
            "alert_triggered": len(losses) >= lookback - 1  # 4 dari 5 terakhir loss
        }
        
        if result["alert_triggered"]:
            msg = (
                f"🔴 <b>LOSING STREAK DETECTED</b>\n"
                f"Last {lookback} trades: {len(losses)} losses, {len(wins)} wins\n"
                f"Recent win rate: {recent_wr:.0f}%\n"
                f"Consider pausing and reviewing recent analyses."
            )
            try:
                from utils.infra.notifier import AgentNotifier
                await AgentNotifier().send_critical(msg)
            except Exception:
                pass
        
        return result

    async def simulate_equity_curve(self, session: AsyncSession, starting_equity: float = 10000.0) -> dict:
        """
        Simulasikan kurva ekuitas (equity curve) untuk hitung max drawdown & growth.
        Menggunakan % risiko per trade dari konfigurasi.
        """
        records = (await session.execute(
            select(PaperTradeRecord)
            .where(PaperTradeRecord.status == 'closed')
            .order_by(PaperTradeRecord.opened_at.asc())
        )).scalars().all()
        
        if not records:
            return {}
        
        equity = starting_equity
        peak_equity = starting_equity
        max_drawdown = 0.0
        equity_history = [{"date": records[0].opened_at.isoformat() if records[0].opened_at else None, "equity": equity}]
        
        RISK_PCT = 1.5 / 100  # Default 1.5% risk per trade
        
        for record in records:
            if record.pnl_pct is not None:
                trade_pnl = equity * (record.pnl_pct / 100.0)
            else:
                trade_pnl = 0.0
            
            equity += trade_pnl
            peak_equity = max(peak_equity, equity)
            drawdown = (peak_equity - equity) / peak_equity * 100
            max_drawdown = max(max_drawdown, drawdown)
            
            equity_history.append({
                "date": record.closed_at.isoformat() if record.closed_at else None,
                "equity": round(equity, 2),
                "trade_pnl": round(trade_pnl, 2),
                "symbol": record.symbol,
                "direction": record.direction,
            })
        
        return {
            "starting_equity": starting_equity,
            "final_equity": round(equity, 2),
            "total_return_pct": round((equity - starting_equity) / starting_equity * 100, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "equity_history": equity_history[-50:],
        }

def _group_by_symbol(history):
    by_sym = {}
    from utils.constants import MARKET_OUTCOME_EXIT_REASONS
    for t in history:
        sym = t.get("symbol")
        if not sym:
            continue
        if sym not in by_sym:
            by_sym[sym] = {
                "trades": 0,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
            }
        
        # Only count trades for win_rate if they are market exits
        if t.get("exit_reason") in MARKET_OUTCOME_EXIT_REASONS:
            by_sym[sym]["trades"] += 1
            by_sym[sym]["total"] += 1
            if t.get("exit_reason") == "tp_hit" or (t.get("pnl_pct") or 0) > 0:
                by_sym[sym]["wins"] += 1
            else:
                by_sym[sym]["losses"] += 1
                
        pnl = t.get("pnl_pct", 0) or 0.0
        by_sym[sym]["pnl_pct"] = round(by_sym[sym]["pnl_pct"] + pnl, 4)
        by_sym[sym]["total_pnl_pct"] = by_sym[sym]["pnl_pct"]
        by_sym[sym]["win_rate"] = (
            round(by_sym[sym]["wins"] / by_sym[sym]["trades"] * 100, 1)
            if by_sym[sym]["trades"] > 0
            else 0.0
        )
    return by_sym


def _group_by_symbol_direction(history):
    by_sym_dir = {}
    from utils.constants import MARKET_OUTCOME_EXIT_REASONS
    for t in history:
        sym = t.get("symbol")
        direction = t.get("direction")
        if not sym or not direction:
            continue
        key = f"{sym}_{str(direction).lower()}"
        if key not in by_sym_dir:
            by_sym_dir[key] = {
                "trades": 0,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "pnl_pct": 0.0,
                "total_pnl_pct": 0.0,
                "win_rate": 0.0,
            }
        
        if t.get("exit_reason") in MARKET_OUTCOME_EXIT_REASONS:
            by_sym_dir[key]["trades"] += 1
            by_sym_dir[key]["total"] += 1
            if t.get("exit_reason") == "tp_hit" or (t.get("pnl_pct") or 0) > 0:
                by_sym_dir[key]["wins"] += 1
            else:
                by_sym_dir[key]["losses"] += 1
                
        pnl = t.get("pnl_pct", 0) or 0.0
        by_sym_dir[key]["pnl_pct"] = round(by_sym_dir[key]["pnl_pct"] + pnl, 4)
        by_sym_dir[key]["total_pnl_pct"] = by_sym_dir[key]["pnl_pct"]
        by_sym_dir[key]["win_rate"] = (
            round(by_sym_dir[key]["wins"] / by_sym_dir[key]["trades"] * 100, 1)
            if by_sym_dir[key]["trades"] > 0
            else 0.0
        )
    return by_sym_dir

