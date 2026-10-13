# ==============================================================================
# File: graph/nodes/risk/portfolio_synthesis.py
# Monika AI Portfolio Synthesis & Heat Reduction Sub-Node
# ==============================================================================

"""
Executes LLM-based portfolio-level cross-asset synthesis and dynamic correlation
heat reduction when multiple trades are proposed simultaneously.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from monika.application.graph.nodes.risk.rejection_auditor import audit_trade_rejection

logger = logging.getLogger("TradingAgent.Graph.Risk.PortfolioSynthesis")


async def ai_portfolio_synthesis(
    actionable: List[Tuple[str, Dict[str, Any]]],
    session: Any,
    settings: Dict[str, Any],
    market_regime: str = "normal",
    as_of: Optional[datetime] = None,
    user_market_intel: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executes AI portfolio-level synthesis when multiple trades are proposed simultaneously.
    """
    from sqlalchemy import select

    from monika.domain.market.dynamic_correlation import get_rolling_correlation
    from monika.infrastructure.database.models import FundamentalBrief, VIXData
    from monika.infrastructure.providers.llm_factory import get_client_for_task

    trade_summaries = []
    proposed_trades = []
    for sym, r in actionable:
        trade_summaries.append(
            f"- {sym} {r.get('decision', '?').upper()}: "
            f"confidence={r.get('confidence', 0):.0%}, "
            f"analysis_id={r.get('analysis_id', '?')}"
        )
        proposed_trades.append({"symbol": sym, "decision": r.get("decision", "unknown")})

    corr_context = []
    for i in range(len(proposed_trades)):
        for j in range(i + 1, len(proposed_trades)):
            sym1, sym2 = proposed_trades[i]["symbol"], proposed_trades[j]["symbol"]
            try:
                corr, source = await get_rolling_correlation(session, sym1, sym2)
                d1, d2 = proposed_trades[i]["decision"], proposed_trades[j]["decision"]
                aligned = (d1 == d2 and corr > 0) or (d1 != d2 and corr < 0)
                if abs(corr) >= 0.3:
                    corr_context.append(
                        f"{sym1}({d1}) & {sym2}({d2}): Correlation={corr:.2f}[{source}] -> "
                        f"{'MULTIPLYING RISK' if aligned else 'HEDGING'}"
                    )
            except Exception:
                pass

    intel_context = []
    if user_market_intel:
        for item in user_market_intel:
            raw_syms = item.get("affected_symbols")
            syms = ", ".join(raw_syms) if isinstance(raw_syms, list) else str(raw_syms or "ALL")
            intel_context.append(
                f"- ID #{item.get('id')} [{item.get('intel_type', '').upper()}]: {item.get('title')}\n"
                f"  Directive: {item.get('directive', 'neutral')} | Scope: {syms} | Target Cycle: {item.get('target_cycle', 'continuous')}\n"
                f"  Summary: {item.get('summary')}"
            )

    brief_stmt = select(FundamentalBrief)
    if as_of:
        brief_stmt = brief_stmt.where(FundamentalBrief.generated_at <= as_of)
    brief = (
        await session.execute(brief_stmt.order_by(FundamentalBrief.generated_at.desc()).limit(1))
    ).scalar_one_or_none()

    vix_stmt = select(VIXData)
    if as_of:
        vix_stmt = vix_stmt.where(VIXData.date <= as_of)
    vix = (await session.execute(vix_stmt.order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()

    prompt = f"""Portfolio Review: {len(actionable)} trades proposed simultaneously.

Proposed Trades:
{chr(10).join(trade_summaries)}

Macro Context:
- Market Regime (from early cycle check): {market_regime}
- Risk sentiment: {brief.risk_sentiment if brief else "unknown"}
- Brief confidence: {brief.confidence if brief else "unknown"}
- VIX: {vix.close if vix else "unknown"}

Operator Market Intelligence & Directives:
{chr(10).join(intel_context) if intel_context else "- (No active operator directives)"}

Pairwise Correlation Assessment:
{chr(10).join(corr_context) if corr_context else "- (No relevant pairs found or only 1 trade)"}

Question: Should we execute ALL these trades simultaneously, or REDUCE the portfolio?

Consider:
1. Correlation between assets
2. Overall portfolio risk
3. Macro conditions and Operator directives (e.g. avoid_trade, favor_buy/sell)
4. Prefer reducing position size via "size_adjustments" (multiplier 0.1-1.0, e.g. 0.5) over completely dropping a trade when setups are valid but moderately correlated.

Respond in JSON:
{{
  "recommendation": "execute_all" or "reduce",
  "keep": ["SYMBOL1", "SYMBOL2"],
  "size_adjustments": {{"SYMBOL1": 0.5}},
  "reasoning": "brief explanation"
}}
"""
    PORTFOLIO_SYNTHESIS_SCHEMA = {
        "type": "object",
        "properties": {
            "recommendation": {"type": "string", "enum": ["execute_all", "reduce"]},
            "keep": {"type": "array", "items": {"type": "string"}},
            "size_adjustments": {
                "type": "object",
                "description": "Optional per-symbol risk multiplier (0.1-1.0) as an alternative "
                "to fully dropping a trade — prefer this over hard exclusion when "
                "the correlation risk is moderate rather than severe.",
                "additionalProperties": {"type": "number"},
            },
            "reasoning": {"type": "string"},
        },
        "required": ["recommendation", "keep", "reasoning"],
    }

    client = get_client_for_task("portfolio_synthesis", settings)
    result = await client.classify_json(prompt=prompt, schema=PORTFOLIO_SYNTHESIS_SCHEMA, temperature=0.0)
    return result or {
        "recommendation": "execute_all",
        "keep": [t["symbol"] for t in proposed_trades],
        "size_adjustments": {},
        "reasoning": "fallback: synthesis call failed",
    }


async def apply_portfolio_synthesis_reduction(
    actionable: List[Tuple[str, Dict[str, Any]]],
    scheduler: Any,
    state: Mapping[str, Any],
) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    Invokes AI portfolio synthesis when >= 3 trades are proposed, applies size adjustments,
    and records paper what-ifs for trimmed positions.
    """
    from monika.infrastructure.database.db import get_session
    from monika.infrastructure.database.models import AssetAnalysis

    if len(actionable) < 3:
        return actionable, []

    newly_rejected: List[Dict[str, Any]] = []

    try:
        async with get_session() as session:
            portfolio_summary = await ai_portfolio_synthesis(
                actionable,
                session,
                scheduler.settings,
                market_regime=state.get("market_regime", "normal"),
                user_market_intel=state.get("user_market_intel"),
            )

        if portfolio_summary.get("recommendation") == "reduce":
            size_adj = portfolio_summary.get("size_adjustments", {})
            keep_symbols = portfolio_summary.get("keep", [sym for sym, _ in actionable])

            if size_adj:
                async with get_session() as adj_session:
                    for sym, r in actionable:
                        if sym in size_adj and sym in keep_symbols:
                            try:
                                mult = max(0.1, min(1.0, float(size_adj[sym])))
                            except TypeError, ValueError:
                                continue
                            ana = await adj_session.get(AssetAnalysis, r["analysis_id"])
                            if ana:
                                new_mult = round((ana.risk_multiplier or 1.0) * mult, 3)
                                ana.risk_multiplier = new_mult
                                r["risk_multiplier"] = new_mult
                                logger.info(f"[PortfolioSynthesis] {sym} risk_multiplier -> {new_mult} (persisted)")
                    await adj_session.commit()

            removed_trades = [(sym, r) for sym, r in actionable if sym not in keep_symbols]
            if removed_trades:
                async with get_session() as reject_session:
                    for sym, r in removed_trades:
                        reasons = ["portfolio_synthesis: heat reduced"]
                        newly_rejected.append({"symbol": sym, "trade": r, "reasons": reasons})
                        await audit_trade_rejection(
                            reject_session,
                            symbol=sym,
                            trade_data=r,
                            reasons=reasons,
                            stage="portfolio_synthesis",
                        )

            actionable = [(sym, r) for sym, r in actionable if sym in keep_symbols]
            logger.info(f"[PortfolioSynthesis] Reduced trades to: {[s for s, _ in actionable]}")
    except Exception as e:
        logger.debug(f"[PortfolioSynthesis] Synthesis failed non-fatal: {e}")

    return actionable, newly_rejected
