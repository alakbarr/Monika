"""
SignalArbitrator: Arbitrase Sinyal Terpusat antara Quant Strategies dan LLM Debate.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import utils.clock as clock

logger = logging.getLogger("TradingAgent.SignalArbitrator")


@dataclass
class ArbitrationResult:
    symbol: str
    decision: str                     # buy | sell | avoid | wait
    confidence: float
    risk_multiplier: float
    selected_source: str              # quant | llm | concordant | defensive_override | conflict_suppression
    arbitration_reason: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class SignalArbitrator:
    """
    Arbitrator terpusat untuk menengahi proposal sinyal dari Quant Strategies
    dan keputusan LLM Debate demi mencegah double-execution dan tabrakan arah.
    """

    def __init__(self, settings: Optional[dict] = None, arbitration_cfg: Optional[dict] = None):
        self.settings = settings or {}
        self.arbitration_cfg = arbitration_cfg or self.settings.get("trading", {}).get("signal_arbitration", {})

    async def arbitrate(
        self,
        session,
        symbol: str,
        quant_signal: Optional[Any] = None,
        llm_decision: Optional[Dict[str, Any]] = None,
        vix_level: float = 15.0,
        regime_info: Optional[Any] = None,
        **kwargs,
    ) -> ArbitrationResult:
        res = await self._do_arbitrate(
            session=session,
            symbol=symbol,
            quant_signal=quant_signal,
            llm_decision=llm_decision,
            vix_level=vix_level,
            regime_info=regime_info,
            **kwargs,
        )
        if session is not None:
            try:
                from database.event_store import TradingEventStore
                await TradingEventStore.emit(
                    session=session,
                    event_type="analysis.arbitration.result",
                    payload={
                        "symbol": symbol,
                        "decision": res.decision,
                        "selected_source": res.selected_source,
                        "confidence": res.confidence,
                        "risk_multiplier": res.risk_multiplier,
                        "reason": res.arbitration_reason,
                    },
                    correlation_id=str(kwargs.get("cycle_id", f"arb_{symbol}")),
                    actor="signal_arbitrator",
                )
            except Exception:
                pass
        return res

    async def _do_arbitrate(
        self,
        session,
        symbol: str,
        quant_signal: Optional[Any] = None,
        llm_decision: Optional[Dict[str, Any]] = None,
        vix_level: float = 15.0,
        regime_info: Optional[Any] = None,
        **kwargs,
    ) -> ArbitrationResult:
        """
        Mengevaluasi sinyal kuantitatif dan keputusan LLM secara terintegrasi.
        """
        now = clock.now()
        market_regime = "ranging"
        if isinstance(regime_info, dict):
            market_regime = (regime_info.get("regime", "ranging") or "ranging").lower()
        elif isinstance(regime_info, str):
            market_regime = regime_info.lower()
        elif "market_regime" in kwargs:
            market_regime = str(kwargs["market_regime"]).lower()

        def _get_q(field: str, default: Any = None) -> Any:
            if quant_signal is None:
                return default
            if isinstance(quant_signal, dict):
                return quant_signal.get(field, default)
            return getattr(quant_signal, field, default)

        quant_dir = str(_get_q("direction", "") or "").lower()
        quant_strat_id = str(_get_q("strategy_id", "unknown") or "unknown")
        quant_is_valid = bool(
            quant_signal is not None
            and _get_q("valid", True)
            and quant_dir in ("buy", "sell")
        )

        # 1. Hanya sinyal Quant yang valid tersedia
        if quant_is_valid and llm_decision is None:
            direction = quant_dir
            
            # High VIX defense
            risk_mult = float((_get_q("meta", {}) or {}).get("size_multiplier", 1.0) or 1.0)
            if vix_level > 25.0:
                risk_mult *= 0.5
                reason = f"Quant {quant_strat_id} single signal approved (high VIX {vix_level:.1f} penalty applied: 0.5x)"
            else:
                reason = f"Quant {quant_strat_id} single signal approved"

            return ArbitrationResult(
                symbol=symbol,
                decision=direction,
                confidence=float(_get_q("confidence", 0.7) or 0.7),
                risk_multiplier=round(risk_mult, 2),
                selected_source="quant",
                arbitration_reason=reason,
                entry_price=_get_q("entry_price"),
                stop_loss=_get_q("stop_loss"),
                take_profit=_get_q("take_profit"),
                meta={"strategy_id": quant_strat_id}
            )

        # 1b. Sinyal Quant non-direksional/invalid tanpa keputusan LLM
        if quant_signal is not None and not quant_is_valid and llm_decision is None:
            return ArbitrationResult(
                symbol=symbol,
                decision="avoid",
                confidence=0.0,
                risk_multiplier=0.0,
                selected_source="quant",
                arbitration_reason="Quant signal non-directional or invalid"
            )

        # 2. Hanya keputusan LLM yang tersedia (atau sinyal Quant tidak valid)
        if llm_decision is not None and not quant_is_valid:
            direction = str(llm_decision.get("decision", "avoid")).lower()
            conf = float(llm_decision.get("confidence", 0.7) or 0.7)
            risk_mult = float(llm_decision.get("risk_multiplier", 1.0) or 1.0)
            
            return ArbitrationResult(
                symbol=symbol,
                decision=direction,
                confidence=conf,
                risk_multiplier=risk_mult,
                selected_source="llm",
                arbitration_reason=f"LLM decision single signal approved: {llm_decision.get('rationale', '')[:100]}",
                entry_price=llm_decision.get("entry_price"),
                stop_loss=llm_decision.get("stop_loss"),
                take_profit=llm_decision.get("take_profit"),
                meta={"llm_source": llm_decision.get("decision_source", "llm_debate")}
            )

        # 3. Keduanya tersedia: Periksa keselarasan (Concordance vs Conflict)
        if quant_is_valid and llm_decision is not None:
            q_dir = quant_dir
            l_dir = str(llm_decision.get("decision", "avoid")).lower()

            q_conf = float(_get_q("confidence", 0.7) or 0.7)
            l_conf = float(llm_decision.get("confidence", 0.7) or 0.7)

            boost_conf = float(self.arbitration_cfg.get("concordant_boost_conf", self.arbitration_cfg.get("concordant_boost_confidence", 0.05)))
            concordant_risk_mult = float(self.arbitration_cfg.get("concordant_risk_multiplier", 1.15))
            max_risk_mult = float(self.arbitration_cfg.get("max_risk_multiplier", 1.25))
            quant_priority_risk_mult = float(self.arbitration_cfg.get("quant_priority_risk_multiplier", 0.70))
            min_q_trend_override = float(self.arbitration_cfg.get("min_quant_confidence_for_trend_override", 0.75))
            vix_defensive_thresh = float(self.arbitration_cfg.get("vix_defensive_override_threshold", 25.0))
            use_bayesian = bool(self.arbitration_cfg.get("empirical_joint_pooling", True))

            # Skenario A: Sinyal Searah (Concordant Agreement)
            if q_dir in ("buy", "sell") and q_dir == l_dir:
                from utils.calibration.confidence_calibrator import get_calibrated_confidence
                
                # Kalibrasi kepercayaan LLM sebelum pooling dengan probabilitas quant
                l_calibrated = await get_calibrated_confidence(session, l_conf) if session else l_conf

                # Dynamically scale boost_conf based on empirical concordance quality if enabled
                use_dynamic_boost = bool(self.arbitration_cfg.get("dynamic_bayesian_boost", False))
                dynamic_boost = boost_conf
                if use_dynamic_boost and session:
                    try:
                        if l_calibrated >= 0.70 and q_conf >= 0.70:
                            dynamic_boost = min(0.08, dynamic_boost + 0.02)
                        elif l_calibrated < 0.55:
                            dynamic_boost = max(0.02, dynamic_boost - 0.02)
                    except Exception:
                        pass
                boost_conf = dynamic_boost

                if use_bayesian:
                    # Calibrated Linear Opinion Pool with Dynamic Empirical Brier Weights
                    def_wq = float(self.arbitration_cfg.get("quant_weight", 0.45))
                    def_wl = float(self.arbitration_cfg.get("llm_weight", 0.55))
                    use_dynamic = bool(self.arbitration_cfg.get("dynamic_brier_weighting", True))
                    
                    if use_dynamic and session:
                        w_q, w_l = await compute_empirical_arbitrator_weights(session, def_wq, def_wl)
                    else:
                        w_q, w_l = def_wq, def_wl
                        
                    w_sum = w_q + w_l
                    combined_p = ((w_q * q_conf) + (w_l * l_calibrated)) / max(1e-4, w_sum)
                    combined_conf = min(0.90, round(combined_p + boost_conf, 2))
                else:
                    raw_mean_conf = (q_conf + l_calibrated) / 2.0
                    combined_conf = min(0.90, round(raw_mean_conf + boost_conf, 2))

                # Turnover / Reversal Friction Penalty (Enhancement 11)
                turnover_penalty = 0.0
                ctx = kwargs.get("context")
                open_positions = kwargs.get("open_positions") or (ctx.get("open_positions", []) if isinstance(ctx, dict) else [])
                if isinstance(open_positions, list):
                    for p in open_positions:
                        if isinstance(p, dict) and p.get("symbol") == symbol:
                            pos_dir = str(p.get("direction", "")).lower()
                            if pos_dir and pos_dir != q_dir:
                                turnover_penalty = max(turnover_penalty, 0.04)
                if turnover_penalty > 0:
                    combined_conf = max(0.40, round(combined_conf - turnover_penalty, 2))
                
                use_dynamic_mult = bool(self.arbitration_cfg.get("dynamic_concordant_multiplier", True))
                if use_dynamic_mult and session:
                    concordant_risk_mult = await self._get_empirical_concordant_multiplier(
                        session, default_mult=concordant_risk_mult, max_mult=max_risk_mult
                    )

                boosted_risk = min(max_risk_mult, round(float(llm_decision.get("risk_multiplier", 1.0)) * concordant_risk_mult, 2))
                
                # ATR Gap Guard & Optimal Risk:Reward Level Selection (AX1-08)
                llm_entry = float(llm_decision.get("entry_price") or 0.0)
                llm_sl = float(llm_decision.get("adjusted_sl") or llm_decision.get("stop_loss") or 0.0)
                llm_tp = float(llm_decision.get("adjusted_tp") or llm_decision.get("take_profit") or 0.0)

                quant_entry = float(_get_q("entry_price", 0.0) or 0.0)
                quant_sl = float(_get_q("stop_loss", 0.0) or 0.0)
                quant_tp = float(_get_q("take_profit", 0.0) or 0.0)

                quant_meta = _get_q("meta", {}) or {}
                atr_val = float(quant_meta.get("atr") or llm_decision.get("atr") or 0.0)
                if atr_val <= 0 and quant_entry > 0 and quant_sl > 0:
                    atr_val = abs(quant_entry - quant_sl) / 1.5

                entry_p, sl_p, tp_p = llm_entry or quant_entry, llm_sl or quant_sl, llm_tp or quant_tp
                level_source = "llm"

                if llm_entry > 0 and quant_entry > 0:
                    entry_gap = abs(llm_entry - quant_entry)
                    gap_threshold = (0.5 * atr_val) if atr_val > 0 else (0.005 * quant_entry)

                    if entry_gap > gap_threshold:
                        llm_risk = abs(llm_entry - llm_sl) if (llm_entry and llm_sl) else 0.0
                        llm_reward = abs(llm_tp - llm_entry) if (llm_entry and llm_tp) else 0.0
                        llm_rr = (llm_reward / llm_risk) if llm_risk > 0 else 0.0

                        quant_risk = abs(quant_entry - quant_sl) if (quant_entry and quant_sl) else 0.0
                        quant_reward = abs(quant_tp - quant_entry) if (quant_entry and quant_tp) else 0.0
                        quant_rr = (quant_reward / quant_risk) if quant_risk > 0 else 0.0

                        if quant_rr >= llm_rr or entry_gap > (gap_threshold * 2.0):
                            entry_p, sl_p, tp_p = quant_entry, quant_sl, quant_tp
                            level_source = "quant"
                            logger.info(
                                f"[{symbol}] Concordant ATR gap guard: gap={entry_gap:.5f} > {gap_threshold:.5f}. "
                                f"Selected Quant levels with optimal R:R ({quant_rr:.2f} vs LLM {llm_rr:.2f})."
                            )
                        else:
                            entry_p, sl_p, tp_p = llm_entry, llm_sl, llm_tp
                            level_source = "llm"

                return ArbitrationResult(
                    symbol=symbol,
                    decision=q_dir,
                    confidence=combined_conf,
                    risk_multiplier=boosted_risk,
                    selected_source="concordant",
                    arbitration_reason=f"Concordant agreement: Quant {quant_strat_id} & LLM both signal {q_dir.upper()} (Linear pool={combined_conf:.0%}, levels={level_source}).",
                    entry_price=entry_p,
                    stop_loss=sl_p,
                    take_profit=tp_p,
                    meta={
                        "quant_strategy": quant_strat_id,
                        "llm_concordance": True,
                        "calibrated_conf": l_calibrated,
                        "level_source": level_source,
                        "dynamic_boost": boost_conf
                    }
                )

            # Skenario B: Konflik Arah (Misal: Quant BUY vs LLM SELL / AVOID)
            logger.warning(f"[{symbol}] Signal conflict detected: Quant={q_dir.upper()} ({quant_strat_id}) vs LLM={l_dir.upper()}")

            # 1. High VIX / Defensive Override (only on extreme VIX or explicit avoid)
            if vix_level >= 35.0 or (vix_level > vix_defensive_thresh and l_dir == "avoid"):
                return ArbitrationResult(
                    symbol=symbol,
                    decision="avoid",
                    confidence=0.0,
                    risk_multiplier=0.0,
                    selected_source="defensive_override",
                    arbitration_reason=f"Arbitrator suppressed signal: Defensive stance during elevated uncertainty (VIX={vix_level:.1f}, LLM={l_dir}).",
                    meta={"quant_signal": q_dir, "llm_signal": l_dir}
                )

            # 2. Multi-Regime Strategy Precedence
            is_trending_regime = market_regime in ("strong_trend", "trend", "trending_bullish", "trending_bearish", "breakout_expansion")
            is_ranging_regime = market_regime in ("ranging", "mean_reverting", "choppy")
            strat_id = quant_strat_id.lower()
            
            is_trend_strat = any(k in strat_id for k in ["donchian", "trend", "breakout", "momentum", "expansion"])
            is_mean_rev_strat = any(k in strat_id for k in ["reversion", "bollinger", "range", "oscillator", "rsi"])

            # A. Strong Trend / Breakout Regime -> Trend Quant strategy precedence
            if is_trending_regime and q_conf >= min_q_trend_override and (is_trend_strat or not is_mean_rev_strat):
                return ArbitrationResult(
                    symbol=symbol,
                    decision=q_dir,
                    confidence=q_conf,
                    risk_multiplier=quant_priority_risk_mult,  # Caution scaling
                    selected_source="quant",
                    arbitration_reason=f"Quant strategy {quant_strat_id} prioritized over LLM during verified {market_regime} regime.",
                    entry_price=_get_q("entry_price"),
                    stop_loss=_get_q("stop_loss"),
                    take_profit=_get_q("take_profit"),
                    meta={"quant_precedence": True, "overridden_llm_decision": l_dir, "market_regime": market_regime}
                )

            # B. Ranging / Mean-Reverting Regime -> Mean Reversion Quant strategy precedence
            if is_ranging_regime and q_conf >= 0.70 and is_mean_rev_strat and l_dir in ("avoid", "wait"):
                return ArbitrationResult(
                    symbol=symbol,
                    decision=q_dir,
                    confidence=q_conf,
                    risk_multiplier=round(quant_priority_risk_mult * 0.9, 2),
                    selected_source="quant",
                    arbitration_reason=f"Mean-reversion strategy {quant_strat_id} executed in ranging regime while LLM is neutral.",
                    entry_price=_get_q("entry_price"),
                    stop_loss=_get_q("stop_loss"),
                    take_profit=_get_q("take_profit"),
                    meta={"quant_precedence": True, "overridden_llm_decision": l_dir, "market_regime": market_regime}
                )

            # 3. Volatile Chop Protection: If market is in volatile chop, block quant signal when LLM is waiting/avoiding
            chop_block = bool(regime_info.get("volatility_chop", {}).get("chop_block", False)) if isinstance(regime_info, dict) else False
            is_volatile_chop = market_regime in ("volatile_chop", "chop", "turbulent_chop") or chop_block
            if is_volatile_chop:
                return ArbitrationResult(
                    symbol=symbol,
                    decision="avoid",
                    confidence=0.0,
                    risk_multiplier=0.0,
                    selected_source="chop_block_suppression",
                    arbitration_reason=f"Arbitrator suppressed signal: Volatile chop regime detected ({market_regime}). Quant execution blocked while LLM is in {l_dir} stance.",
                    meta={"quant_signal": q_dir, "llm_signal": l_dir, "market_regime": market_regime}
                )

            # TimesFM 3.0 Statistical Arbiter Check
            tfm_skew = 0.0
            if session:
                try:
                    from indicators.timesfm_engine import TimesFMEngine
                    tfm_engine = TimesFMEngine(self.settings)
                    tfm_fc = await tfm_engine.get_latest_forecast(session, symbol, timeframe='H1', max_age_hours=8.0)
                    if tfm_fc:
                        tfm_skew = float(tfm_fc.get('quantile_skew', 0.0))
                except Exception as tfm_err:
                    logger.debug(f"[{symbol}] TimesFM lookup in arbitrator failed (non-fatal): {tfm_err}")

            # 4. If LLM is waiting/avoiding and Quant has active valid signal:
            if l_dir in ("avoid", "wait") and q_dir in ("buy", "sell"):
                # If TimesFM strongly opposes Quant, suppress to avoid false breakout
                if (q_dir == "buy" and tfm_skew < -0.30) or (q_dir == "sell" and tfm_skew > 0.30):
                    return ArbitrationResult(
                        symbol=symbol,
                        decision="avoid",
                        confidence=0.0,
                        risk_multiplier=0.0,
                        selected_source="statistical_suppression",
                        arbitration_reason=f"Arbitrator suppressed signal: Quant {q_dir.upper()} contradicted by TimesFM statistical skew ({tfm_skew:.2f}) and LLM {l_dir}.",
                        meta={"quant_signal": q_dir, "llm_signal": l_dir, "timesfm_skew": tfm_skew}
                    )

                # If TimesFM confirms Quant, boost caution multiplier
                effective_mult = quant_priority_risk_mult
                if (q_dir == "buy" and tfm_skew >= 0.20) or (q_dir == "sell" and tfm_skew <= -0.20):
                    effective_mult = min(0.90, quant_priority_risk_mult + 0.15)

                return ArbitrationResult(
                    symbol=symbol,
                    decision=q_dir,
                    confidence=q_conf,
                    risk_multiplier=effective_mult,
                    selected_source="quant",
                    arbitration_reason=f"Quant signal {quant_strat_id} executed while LLM is in {l_dir} (TimesFM skew={tfm_skew:+.2f}).",
                    entry_price=_get_q("entry_price"),
                    stop_loss=_get_q("stop_loss"),
                    take_profit=_get_q("take_profit"),
                    meta={"quant_precedence": True, "overridden_llm_decision": l_dir, "timesfm_skew": tfm_skew}
                )

            # 5. Direct conflict in ranging / mixed market -> Mutual Suppression unless TimesFM breaks tie
            if abs(tfm_skew) >= 0.35:
                tfm_favors = "buy" if tfm_skew > 0 else "sell"
                favored_source = "quant" if q_dir == tfm_favors else ("llm" if l_dir == tfm_favors else None)
                if favored_source:
                    fav_entry = _get_q("entry_price") if favored_source == "quant" else llm_decision.get("entry_price")
                    fav_sl = _get_q("stop_loss") if favored_source == "quant" else llm_decision.get("stop_loss")
                    fav_tp = _get_q("take_profit") if favored_source == "quant" else llm_decision.get("take_profit")
                    return ArbitrationResult(
                        symbol=symbol,
                        decision=tfm_favors,
                        confidence=0.75,
                        risk_multiplier=round(quant_priority_risk_mult * 0.85, 2),
                        selected_source=f"timesfm_tie_break_{favored_source}",
                        arbitration_reason=f"TimesFM 3.0 statistical skew ({tfm_skew:+.2f}) resolved conflict in favor of {favored_source.upper()} {tfm_favors.upper()}.",
                        entry_price=fav_entry,
                        stop_loss=fav_sl,
                        take_profit=fav_tp,
                        meta={"conflict_resolved": True, "timesfm_skew": tfm_skew}
                    )

            return ArbitrationResult(
                symbol=symbol,
                decision="avoid",
                confidence=0.0,
                risk_multiplier=0.0,
                selected_source="conflict_suppression",
                arbitration_reason=f"Direct direction conflict ({q_dir.upper()} vs {l_dir.upper()}) in {market_regime} market. Trade avoided to preserve capital.",
                meta={"quant_signal": q_dir, "llm_signal": l_dir, "market_regime": market_regime, "timesfm_skew": tfm_skew}
            )

        # 4. Tidak ada sinyal
        return ArbitrationResult(
            symbol=symbol,
            decision="avoid",
            confidence=0.0,
            risk_multiplier=0.0,
            selected_source="none",
            arbitration_reason="No signals provided for arbitration."
        )

    async def _get_empirical_concordant_multiplier(
        self,
        session,
        default_mult: float = 1.15,
        max_mult: float = 1.25
    ) -> float:
        """
        Dynamically scale concordant risk multiplier based on rolling win rate of past concordant trades.
        If empirical edge is strong (win rate >= 65%, N >= 15), scale up to max_mult (1.25x).
        If empirical edge is weak (< 50%), dampen to 1.0x (no extra leverage boost).
        """
        if session is None:
            return default_mult

        try:
            from database.models import PaperTradeRecord, TradeOutcome
            from sqlalchemy import select

            # Query up to 30 recent concordant closed trades
            stmt = (
                select(PaperTradeRecord)
                .where(PaperTradeRecord.status == 'closed')
                .where(PaperTradeRecord.decision_source == 'concordant')
                .order_by(PaperTradeRecord.closed_at.desc())
                .limit(30)
            )
            records = (await session.execute(stmt)).scalars().all()
            if len(records) < 15:
                stmt_live = (
                    select(TradeOutcome)
                    .where(TradeOutcome.decision_source == 'concordant')
                    .order_by(TradeOutcome.closed_at.desc())
                    .limit(30)
                )
                live_records = (await session.execute(stmt_live)).scalars().all()
                all_records = list(records) + list(live_records)
            else:
                all_records = list(records)

            if len(all_records) < 15:
                return default_mult

            wins = sum(
                1 for r in all_records
                if getattr(r, "exit_reason", "") == "tp_hit"
                or (getattr(r, "pnl_pct", None) is not None and r.pnl_pct > 0)
                or getattr(r, "was_profitable", False)
            )
            win_rate = wins / len(all_records)

            if win_rate >= 0.65:
                return min(max_mult, round(1.0 + (win_rate * 0.38), 2))
            elif win_rate >= 0.50:
                return default_mult
            else:
                # Dampen risk multiplier when concordant win rate is poor
                return 1.00
        except Exception as e:
            logger.debug(f"Error computing empirical concordant multiplier: {e}")
            return default_mult


async def compute_empirical_arbitrator_weights(
    session,
    default_quant: float = 0.45,
    default_llm: float = 0.55,
    lookback_limit: int = 30
) -> tuple[float, float]:
    """
    Menghitung bobot empiris dinamis untuk Quant vs LLM berbasis inverse Brier Score (1 - Brier)
    dari trade historis tertutup.
    Clamps bobot pada rentang aman [0.20, 0.80].
    Fallback ke (default_quant, default_llm) jika sampel < 15.
    """
    if not session:
        return default_quant, default_llm
    try:
        from database.models import PaperTradeRecord, AssetAnalysis
        from sqlalchemy import select
        
        stmt = (
            select(PaperTradeRecord, AssetAnalysis)
            .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(lookback_limit)
        )
        exec_res = await session.execute(stmt)
        records = exec_res.all() if hasattr(exec_res, 'all') else []
        if len(records) < 10:
            return default_quant, default_llm
            
        brier_llm_list = []
        brier_quant_list = []
        
        for rec, ana in records:
            is_win = 1.0 if (getattr(rec, 'exit_reason', None) == 'tp_hit' or (getattr(rec, 'pnl_pct', None) and rec.pnl_pct > 0)) else 0.0
            
            # LLM Brier extraction
            if ana and getattr(ana, 'confidence', None) is not None:
                try:
                    conf_l = float(ana.confidence)
                    brier_llm_list.append((conf_l - is_win) ** 2)
                except (ValueError, TypeError):
                    pass
                
            # Quant Brier extraction (from quant signals, strategy runners, or concordant executions)
            rec_src = getattr(rec, 'decision_source', '') or ''
            has_quant_src = rec_src in ("quant", "strategy_runner", "concordant") or (ana and getattr(ana, "source_strategy_id", None) is not None)
            if has_quant_src:
                q_conf = 0.60
                if ana and getattr(ana, "strategy_confidence", None) is not None:
                    try:
                        q_conf = float(ana.strategy_confidence)
                    except (ValueError, TypeError):
                        q_conf = 0.60
                brier_quant_list.append((q_conf - is_win) ** 2)
                
        mean_brier_llm = sum(brier_llm_list) / len(brier_llm_list) if len(brier_llm_list) >= 8 else 0.25
        mean_brier_quant = sum(brier_quant_list) / len(brier_quant_list) if len(brier_quant_list) >= 8 else 0.25
        
        acc_q = max(0.01, 1.0 - mean_brier_quant)
        acc_l = max(0.01, 1.0 - mean_brier_llm)
        
        total_acc = acc_q + acc_l
        raw_w_q = acc_q / max(1e-6, total_acc)
        
        clamped_w_q = max(0.20, min(0.80, raw_w_q))
        clamped_w_l = round(1.0 - clamped_w_q, 4)
        return round(clamped_w_q, 4), clamped_w_l
    except Exception as e:
        logger.debug(f"Dynamic arbitrator weight computation fallback: {e}")
        return default_quant, default_llm
