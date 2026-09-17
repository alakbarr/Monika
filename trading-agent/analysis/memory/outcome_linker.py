import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from database.models import DecisionReflection, AssetAnalysis, PaperTradeRecord
from analysis.memory.reflector import TradeReflector
from analysis.memory.alpha_calculator import AlphaCalculator

logger = logging.getLogger(__name__)

class OutcomeLinker:
    """Menghubungkan outcome (real/hypothetical) dengan keputusan awal, lalu memicu refleksi."""
    
    def __init__(self, settings: Optional[dict] = None):
        self.reflector = TradeReflector(settings)

    async def process_closed_position(self, session: AsyncSession, analysis_id: int, pnl: float, holding_hours: float, exit_reason: str, entry_time: Optional[datetime] = None, exit_time: Optional[datetime] = None, asset_return_pct: Optional[float] = None):
        """Dipanggil saat trade benar-benar ditutup (Real/Paper Trade yang dieksekusi)."""
        try:
            # Cari log pending berdasarkan analysis_id
            if not analysis_id:
                return

            stmt = select(DecisionReflection).where(
                DecisionReflection.analysis_id == analysis_id,
                DecisionReflection.status == 'pending',
                DecisionReflection.is_paper_whatif == False
            )
            reflection = (await session.execute(stmt)).scalar_one_or_none()

            if reflection:
                prev_pnl = reflection.outcome_pnl_usd or 0.0
                total_pnl = prev_pnl + (pnl or 0.0)
                reflection.outcome_pnl_usd = total_pnl
                reflection.holding_hours = holding_hours
                reflection.exit_reason = exit_reason
                reflection.was_profitable = True if total_pnl > 0.0 else (False if total_pnl < 0.0 else None)

                # P0-8 Debate-based reflection logic
                analysis = await session.get(AssetAnalysis, analysis_id)
                if analysis and analysis.debate_verdict:
                    # Bila verdict disagree dengan exit_reason (e.g. avoid tapi tp_hit, buy tapi sl_hit)
                    if analysis.debate_verdict == 'avoid' and reflection.was_profitable:
                        reflection.debate_verdict = 'rejected_but_won'
                    elif analysis.debate_verdict in ('buy', 'sell') and not reflection.was_profitable:
                        reflection.debate_verdict = 'approved_but_lost'
                    else:
                        reflection.debate_verdict = analysis.debate_verdict
                    
                    reflection.debate_summary = analysis.debate_reason

                if entry_time and exit_time and asset_return_pct is not None:
                    calculator = AlphaCalculator(session)
                    alpha_data = await calculator.calculate_alpha(
                        symbol=reflection.symbol,
                        direction=reflection.decision,
                        entry_time=entry_time,
                        exit_time=exit_time,
                        asset_return_pct=asset_return_pct
                    )
                    reflection.benchmark_name = alpha_data['benchmark_name']
                    reflection.benchmark_return = alpha_data['benchmark_return']
                    reflection.alpha_return = alpha_data['alpha_return']

                from database.safe_ops import safe_commit
                if exit_reason != "partial_tp":
                    reflection.status = "resolved"
                    reflection.resolved_at = datetime.now(timezone.utc)
                    await safe_commit(session, label="outcome_linker_closed")
                    
                    # Picu refleksi AI
                    await self.reflector.reflect_on_trade(session, reflection.id)
                else:
                    await safe_commit(session, label="outcome_linker_partial")

        except Exception as e:
            logger.error(f"Error di process_closed_position: {e}")
            await session.rollback()

    async def process_paper_whatifs(self, session: AsyncSession):
        """
        Job background/scheduler untuk me-resolve what-ifs yang sudah > 24 jam.
        Mencari status='pending_whatif', membandingkan harga 24h, lalu memicu refleksi.
        """
        try:
            now = datetime.now(timezone.utc)
            # Cari pending_whatif yang analysis-nya sudah > 24h
            stmt = select(DecisionReflection, AssetAnalysis).join(
                AssetAnalysis, DecisionReflection.analysis_id == AssetAnalysis.id
            ).where(
                DecisionReflection.status == 'pending_whatif',
                AssetAnalysis.generated_at <= now - timedelta(hours=24)
            )
            
            results = (await session.execute(stmt)).all()
            
            for reflection, analysis in results:
                try:
                    price_now = analysis.price_24h_after if hasattr(analysis, 'price_24h_after') and analysis.price_24h_after else None
                    if price_now is None:
                        from database.models import PriceOHLCV
                        target_time = analysis.generated_at + timedelta(hours=24)
                        bar = (await session.execute(
                            select(PriceOHLCV)
                            .where(PriceOHLCV.symbol == reflection.symbol)
                            .where(PriceOHLCV.timeframe == 'H1')
                            .where(PriceOHLCV.timestamp >= target_time - timedelta(hours=2))
                            .where(PriceOHLCV.timestamp <= target_time + timedelta(hours=4))
                            .order_by(PriceOHLCV.timestamp.asc())
                            .limit(1)
                        )).scalar_one_or_none()
                        if not bar:
                            bar = (await session.execute(
                                select(PriceOHLCV)
                                .where(PriceOHLCV.symbol == reflection.symbol)
                                .where(PriceOHLCV.timeframe == 'H1')
                                .order_by(PriceOHLCV.timestamp.desc())
                                .limit(1)
                            )).scalar_one_or_none()
                        if bar:
                            price_now = bar.close
                            if hasattr(analysis, 'price_24h_after'):
                                analysis.price_24h_after = price_now

                    entry_price = reflection.whatif_entry_price
                    
                    if entry_price and price_now:
                        from risk.position_sizing import get_instrument_spec
                        spec = get_instrument_spec(reflection.symbol)
                        pip_size = spec.pip_size if spec and spec.pip_size > 0 else 0.0001

                        diff = price_now - entry_price
                        direction = 1 if reflection.decision.lower() == 'buy' else -1
                        
                        reflection.whatif_price_24h = price_now
                        diff_pips = (diff / pip_size) * direction
                        reflection.whatif_hypothetical_pnl_pips = round(diff_pips, 2)
                        
                        reflection.whatif_direction_correct = (diff_pips > 0)
                        
                        # Evaluate path-dependent price action using proposed SL/TP from AssetAnalysis
                        proposed_sl = analysis.stop_loss
                        proposed_tp = analysis.take_profit
                        
                        sl_hit, tp_hit = await self._check_path_dependent_outcome(
                            session=session,
                            symbol=reflection.symbol,
                            start_time=analysis.generated_at,
                            end_time=now,
                            entry_price=entry_price,
                            proposed_sl=proposed_sl,
                            proposed_tp=proposed_tp,
                            direction=direction,
                            pip_size=pip_size
                        )
                        reflection.whatif_sl_would_hit = sl_hit
                        reflection.whatif_tp_would_hit = tp_hit


                        asset_return_pct = ((price_now - entry_price) / entry_price) * 100.0 * direction if entry_price > 0 else 0.0

                        calculator = AlphaCalculator(session)
                        alpha_data = await calculator.calculate_alpha(
                            symbol=reflection.symbol,
                            direction=reflection.decision,
                            entry_time=analysis.generated_at,
                            exit_time=now,
                            asset_return_pct=asset_return_pct
                        )
                        reflection.benchmark_name = alpha_data['benchmark_name']
                        reflection.benchmark_return = alpha_data['benchmark_return']
                        reflection.alpha_return = alpha_data['alpha_return']
                        
                        reflection.resolved_at = now
                        await session.commit()
                        
                        # Picu refleksi
                        await self.reflector.reflect_on_trade(session, reflection.id)
                except Exception as inner_e:
                    logger.error(f"Error memproses whatif untuk reflection {reflection.id}: {inner_e}")
                    await session.rollback()
                    try:
                        # Cegah item ini memblokir batch run selamanya jika error terus berulang sebelum reflector dipanggil
                        ref_obj = await session.get(DecisionReflection, reflection.id)
                        if ref_obj and ref_obj.status == 'pending_whatif':
                            ref_obj.status = 'error'
                            await session.commit()
                    except Exception as rb_err:
                        logger.error(f"Failed to record error status for reflection {reflection.id}: {rb_err}")
                        await session.rollback()
                    
        except Exception as e:
            logger.error(f"Error di process_paper_whatifs: {e}")
            await session.rollback()

    async def _check_path_dependent_outcome(
        self,
        session: AsyncSession,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        entry_price: float,
        proposed_sl: Optional[float],
        proposed_tp: Optional[float],
        direction: int,
        pip_size: float = 0.0001
    ) -> tuple[bool, bool]:
        """
        Evaluasi apakah bar harga historis antara start_time dan end_time
        menyentuh SL atau TP terlebih dahulu (path-dependent evaluation).
        Returns: (sl_would_hit, tp_would_hit)
        """
        from database.models import PriceOHLCV
        from sqlalchemy import select

        # Fallback sl/tp jika tidak ditentukan atau bernilai non-positif dalam AssetAnalysis
        if proposed_sl is None or proposed_sl <= 0:
            proposed_sl = entry_price - (50 * pip_size * direction)
        if proposed_tp is None or proposed_tp <= 0:
            proposed_tp = entry_price + (100 * pip_size * direction)

        # Validasi konsistensi arah stop loss dan take profit relatif terhadap entry
        if direction == 1:  # BUY: SL harus di bawah entry, TP harus di atas entry
            if proposed_sl >= entry_price:
                proposed_sl = entry_price - (50 * pip_size)
            if proposed_tp <= entry_price:
                proposed_tp = entry_price + (100 * pip_size)
        else:  # SELL: SL harus di atas entry, TP harus di bawah entry
            if proposed_sl <= entry_price:
                proposed_sl = entry_price + (50 * pip_size)
            if proposed_tp >= entry_price:
                proposed_tp = entry_price - (100 * pip_size)

        try:
            stmt = (
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == 'H1')
                .where(PriceOHLCV.timestamp >= start_time)
                .where(PriceOHLCV.timestamp <= end_time)
                .order_by(PriceOHLCV.timestamp.asc())
            )
            bars = (await session.execute(stmt)).scalars().all()

            if not bars:
                return False, False

            for bar in bars:
                high = float(bar.high)
                low = float(bar.low)

                if direction == 1:  # BUY
                    hit_sl = low <= proposed_sl
                    hit_tp = high >= proposed_tp
                else:  # SELL
                    hit_sl = high >= proposed_sl
                    hit_tp = low <= proposed_tp

                if hit_sl and hit_tp:
                    # Konservatif: jika keduanya tersentuh pada bar yang sama, anggap SL tersentuh lebih dulu
                    return True, False
                elif hit_sl:
                    return True, False
                elif hit_tp:
                    return False, True

            return False, False
        except Exception as e:
            logger.debug(f"Path dependent check error for {symbol}: {e}")
            return False, False

