# ==============================================================================
# File: domain/risk/evaluators/intelligence_checks.py
# ==============================================================================

"""
TimesFM expectancy, analysis quality scores, evidence gate, and mandate checks for RiskGate.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone, UTC
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from monika.domain.risk.evaluators.base import _RiskGateMixinBase, resolve_model
from monika.domain.risk.position_sizing import SizingResult

Position: Any = resolve_model("Position")
AssetAnalysis: Any = resolve_model("AssetAnalysis")
SystemConfig: Any = resolve_model("SystemConfig")
TimesFMForecast: Any = resolve_model("TimesFMForecast")

logger = logging.getLogger("TradingAgent.RiskGate")


def _fmt_quantile_price(val: float, ref_price: float) -> str:
    """Format quantile price with appropriate decimal places based on reference price magnitude."""
    abs_ref = abs(ref_price)
    if abs_ref < 10.0:
        return f"{val:.5f}"
    elif abs_ref < 500.0:
        return f"{val:.3f}"
    else:
        return f"{val:.2f}"


class RiskIntelligenceChecksMixin(_RiskGateMixinBase):
    """Model intelligence, forecast expectancy, and evidence gate validation mixin."""

    async def _check_timesfm_expectancy(
        self,
        session: Any,
        symbol: str,
        direction: str,
        sizing: SizingResult,
        is_backtest: bool = False,
        proposal: Any | None = None,
    ) -> tuple[bool, str]:
        """Validasi ekspektansi probabilistik menggunakan kuantil TimesFM 3.0 tanpa dependensi ML engine."""
        tfm_cfg = self.settings.get("timesfm", {})
        if not tfm_cfg.get("enabled", True) or not tfm_cfg.get("expectancy_gate", {}).get("enabled", True):
            return True, "TimesFM expectancy gate disabled"

        try:
            q: dict[str, Any] | None = None
            if proposal and hasattr(proposal, "metadata") and isinstance(proposal.metadata, dict):
                q = proposal.metadata.get("timesfm_quantiles") or proposal.metadata.get("timesfm_forecast", {}).get(
                    "quantiles"
                )

            if not q:
                # Lightweight database query without loading TimesFMEngine or PyTorch
                import json
                from datetime import datetime, timedelta, timezone

                from sqlalchemy import desc, select

                max_age = float(tfm_cfg.get("cache_ttl_hours", 8.0))
                cutoff = datetime.now(UTC) - timedelta(hours=max_age)
                stmt = (
                    select(TimesFMForecast)
                    .where(TimesFMForecast.symbol == symbol, TimesFMForecast.timeframe == "H1")
                    .where(TimesFMForecast.generated_at >= cutoff)
                    .order_by(desc(TimesFMForecast.generated_at))
                    .limit(1)
                )
                record = (await session.execute(stmt)).scalar_one_or_none()
                if record and record.quantiles_json:
                    q = json.loads(record.quantiles_json)

            if not q:
                return True, "No fresh TimesFM forecast available — gate bypassed"

            entry = sizing.entry_price
            tp = sizing.take_profit
            sl = sizing.stop_loss

            if not tp or not sl or entry <= 0:
                return True, "Missing TP/SL levels for expectancy calculation"

            # Determine dynamic evaluation step based on trade holding horizon
            exp_gate_cfg = tfm_cfg.get("expectancy_gate", {})
            noise_buffer_ratio = float(exp_gate_cfg.get("noise_cone_buffer_ratio", 0.2))

            # Dynamically select step index corresponding to the trade's expected horizon
            horizon_hours: float | None = None
            if proposal is not None:
                meta = getattr(proposal, "metadata", None)
                if isinstance(meta, dict):
                    horizon_hours = meta.get("horizon_hours") or meta.get("expected_holding_hours")
                    if horizon_hours is None and meta.get("holding_period"):
                        hp = str(meta["holding_period"]).lower()
                        if "scalp" in hp:
                            horizon_hours = 2.0
                        elif "intraday" in hp or "day" in hp:
                            horizon_hours = 6.0
                        elif "swing" in hp:
                            horizon_hours = 24.0

                if horizon_hours is None:
                    hp_attr = getattr(proposal, "holding_period", None)
                    if hp_attr:
                        hp_str = str(hp_attr).lower()
                        if "scalp" in hp_str:
                            horizon_hours = 2.0
                        elif "intraday" in hp_str or "day" in hp_str:
                            horizon_hours = 6.0
                        elif "swing" in hp_str:
                            horizon_hours = 24.0

                if horizon_hours is None:
                    reval = getattr(proposal, "reevaluation_trigger", None)
                    if isinstance(reval, str) and reval.strip():
                        try:
                            import json

                            reval_dict = json.loads(reval)
                            if isinstance(reval_dict, dict) and "bars" in reval_dict:
                                horizon_hours = float(reval_dict["bars"])
                        except Exception:
                            pass

                if horizon_hours is None:
                    adr_tp = getattr(proposal, "adr_tp_pct_used", None)
                    if adr_tp is not None and 0.0 < float(adr_tp) <= 0.6:
                        horizon_hours = 6.0

            def _get_step_val(q_list: list[Any]) -> float:
                if not q_list:
                    return 0.0
                if horizon_hours is not None:
                    idx = max(0, min(int(round(horizon_hours)) - 1, len(q_list) - 1))
                    return float(q_list[idx])
                default_intraday = int(exp_gate_cfg.get("default_horizon_steps", 6))
                idx = max(0, min(default_intraday - 1, len(q_list) - 1))
                return float(q_list[idx])

            # Check reachability in horizon envelope
            if direction.lower() == "buy":
                if "q90" in q and q["q90"]:
                    q90 = float(q["q90"][-1])
                    if tp > (q90 * 1.02):
                        return (
                            False,
                            f"Proposed TP ({tp}) exceeds TimesFM Q90 ceiling ({_fmt_quantile_price(q90, tp)}) by >2%. Mathematical expectancy negative.",
                        )
                if "q30" in q and q["q30"] and "q10" in q and q["q10"]:
                    q30 = _get_step_val(q["q30"])
                    q10 = _get_step_val(q["q10"])
                    if sl > q30 and (entry - sl) < max(0.0, entry - q10) * noise_buffer_ratio:
                        return (
                            False,
                            f"Proposed SL ({sl}) is inside high-probability noise cone (> Q30 {_fmt_quantile_price(q30, sl)}).",
                        )
            elif direction.lower() == "sell":
                if "q10" in q and q["q10"]:
                    q10 = float(q["q10"][-1])
                    if tp < (q10 * 0.98):
                        return (
                            False,
                            f"Proposed TP ({tp}) falls below TimesFM Q10 floor ({_fmt_quantile_price(q10, tp)}) by >2%. Mathematical expectancy negative.",
                        )
                if "q70" in q and q["q70"] and "q90" in q and q["q90"]:
                    q70 = _get_step_val(q["q70"])
                    q90 = _get_step_val(q["q90"])
                    if sl < q70 and (sl - entry) < max(0.0, q90 - entry) * noise_buffer_ratio:
                        return (
                            False,
                            f"Proposed SL ({sl}) is inside high-probability noise cone (< Q70 {_fmt_quantile_price(q70, sl)}).",
                        )

            return True, "TimesFM expectancy passed (target within Q10-Q90 cone)"
        except Exception as e:
            logger.error(f"[{symbol}] TimesFM expectancy check error (fail-closed): {e}")
            return False, f"TimesFM expectancy check failed (fail-closed): {e}"

    async def _check_analysis_quality_scores(self, analysis: Any, session: Any | None = None) -> tuple[bool, str]:
        """Validate that analysis has required quality scores before execution."""
        if analysis is None:
            return (False, "No analysis object provided")

        decision_source = str(getattr(analysis, "decision_source", "") or "")
        if (
            decision_source == "edge_registry"
            or decision_source.startswith("quant_")
            or bool(getattr(analysis, "source_strategy_id", None))
        ):
            if analysis.confidence is None or float(analysis.confidence) < 0.3:
                return False, f"{decision_source or 'quantitative'} signal confidence too low ({analysis.confidence})"
            return True, f"{decision_source or 'quantitative'}_quantitative_signal_passed"

        if analysis.confluence_score is None:
            return (
                False,
                f"confluence_score is None for {analysis.symbol}. "
                f"Model did not fill required scorecard. Blocking execution.",
            )

        if analysis.priced_in_score is None:
            return (
                False,
                f"priced_in_score is None for {analysis.symbol}. "
                f"Priced-in assessment not completed. Blocking execution.",
            )

        if analysis.priced_in_score >= 8:
            return (
                False,
                f"priced_in_score={analysis.priced_in_score} >= 8 for {analysis.symbol}. "
                f"Event fully priced in (score >= 8) — high sell-the-news reversal risk.",
            )

        min_confluence = self.settings.get("trading", {}).get("auto_execute_min_confluence", 7)
        if session and getattr(analysis, "symbol", None):
            try:
                from monika.domain.risk.ports import get_default_adaptive_risk_policy

                policy = get_default_adaptive_risk_policy(self.settings)
                if policy is not None:
                    eff_thresh, reason = await policy.get_effective_threshold(session, analysis.symbol)
                    min_confluence = eff_thresh
                    logger.debug(f"[{analysis.symbol}] RiskGate adaptive threshold: {eff_thresh} ({reason})")
            except Exception as e:
                logger.debug(f"AdaptiveRiskPolicy lookup in RiskGate non-fatal: {e}")

        if analysis.confluence_score < min_confluence:
            return (
                False,
                f"confluence_score={analysis.confluence_score} < {min_confluence} (adaptive policy threshold).",
            )

        return (
            True,
            f"quality_scores_ok(confluence={analysis.confluence_score}, priced_in={analysis.priced_in_score}, threshold={min_confluence})",
        )

    async def _check_edge_status_not_paused(self, session: Any, is_backtest: bool = False) -> tuple[bool, str]:
        if is_backtest:
            return (True, "ok")

        from sqlalchemy import select

        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == "trading_paused"))
        ).scalar_one_or_none()
        if cfg and cfg.value and cfg.value.split(":", 1)[0].strip().lower() == "true":
            reason = (
                cfg.value.split(":", 1)[1]
                if ":" in cfg.value
                else "No statistical edge detected (EdgeTracker auto-pause)"
            )
            return (False, f"EdgeTracker auto-pause active: {reason}")
        return (True, "ok")

    async def _check_evidence_gate(
        self,
        session: Any,
        symbol: str,
        analysis: Any | None = None,
        is_backtest: bool = False,
    ) -> tuple[bool, str]:
        """
        Subsystem 5: Strategy Evidence Store Gate.
        Verifies that the proposing strategy has non-negative empirical expectancy
        in the current regime before permitting execution.
        """
        if is_backtest or analysis is None:
            return True, "Evidence gate skipped for backtest or missing analysis"

        try:
            from monika.domain.risk.ports import get_default_evidence_store

            strat_id = getattr(analysis, "strategy_id", None) or "general"
            regime = getattr(analysis, "market_regime", "UNKNOWN") or "UNKNOWN"

            ev_store = get_default_evidence_store()
            if ev_store is not None:
                is_valid, reason = ev_store.validate_strategy_for_trade(strat_id, regime)
                if not is_valid:
                    return False, f"EvidenceStore rejected trade: {reason}"
        except Exception as e:
            logger.warning(f"[{symbol}] Evidence gate check failed: {e}")
            return False, f"evidence_gate_check_failed: {e}"

        return True, "Strategy passed regime evidence verification"

    async def _check_bounded_mandate(
        self,
        session: Any,
        symbol: str,
        sizing: Any,
        as_of: Any | None = None,
        simulated_positions: list[Any] | None = None,
    ) -> tuple[bool, str]:
        """
        Subsystem 7: Bounded Mandate Contract Gate.
        Enforces 30-day operator authorization TTL, authorized symbol coverage,
        and maximum risk / position boundaries.
        """
        from monika.domain.risk.approval_hub import get_approval_hub

        hub = get_approval_hub()

        if not hub._mandates and hub._active_mandate_id is None:
            return True, "No operator mandate registered; mandate enforcement dormant"

        open_count = len(simulated_positions) if simulated_positions is not None else 0
        if simulated_positions is None and session:
            try:
                from sqlalchemy import func, select

                stmt = select(func.count(Position.id)).where(Position.status == "open")
                res = await session.execute(stmt)
                scalar_val = res.scalar() if hasattr(res, "scalar") else 0
                if asyncio.iscoroutine(scalar_val):
                    scalar_val = await scalar_val
                open_count = int(scalar_val or 0)
            except Exception:
                open_count = 0

        risk_pct = getattr(sizing, "risk_percent", 1.0)
        check_ts = None
        if as_of is not None:
            check_ts = as_of.timestamp() if hasattr(as_of, "timestamp") else float(as_of)

        return hub.validate_mandate(
            symbol=symbol,
            risk_pct=risk_pct,
            current_positions=open_count,
            as_of=check_ts,
        )


__all__ = ["RiskIntelligenceChecksMixin"]
