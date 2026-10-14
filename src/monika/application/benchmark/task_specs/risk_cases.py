# ==============================================================================
# File: application/benchmark/task_specs/risk_cases.py
# ==============================================================================

"""
Risk gate, portfolio management, adversarial check, and risk audit task specs.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from monika.application.analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from monika.application.analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from monika.application.analysis.debate.deterministic_risk import (
    analyze_risk_aggressive,
    analyze_risk_conservative,
    analyze_risk_neutral,
)
from monika.application.analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from monika.application.analysis.debate.portfolio_manager import make_portfolio_decision

from ..db_access import entry_context, latest_brief, pick_asset_analysis
from ..fixture_loader import (
    get_golden_adversarial_case,
    get_golden_concurrent_orders,
    get_golden_risk_state,
    get_synthetic_risk_context,
)
from .base import BenchmarkCase, _sym


async def _build_strict_risk_context(
    session: Any, settings: dict[str, Any], ex: Any, symbol: str
) -> tuple[dict[str, Any], Any]:
    use_fixtures = settings.get("_use_fixtures", False)
    if not use_fixtures and session:
        try:
            analysis = await pick_asset_analysis(session, symbol)
            ctx = entry_context(analysis)
            risk_state = await ex.execute("get_risk_state", {}) if ex else {}
            open_pos = await ex.execute("get_open_positions", {}) if ex else {}
            entry_price = ctx.get("entry_price")
            rr = None
            if entry_price and analysis.stop_loss and analysis.take_profit:
                sl_d, tp_d = abs(entry_price - analysis.stop_loss), abs(entry_price - analysis.take_profit)
                rr = (tp_d / sl_d) if sl_d else None
            strict_context = {
                "symbol": symbol,
                "decision": ctx["decision"],
                "confluence_score": analysis.confluence_score,
                "priced_in_score": analysis.priced_in_score,
                "rr_ratio": rr,
                "sl_beyond_structure": True,
                "actual_risk_state": {
                    "daily_pnl_pct": risk_state.get("daily_pnl_pct", 0.0),
                    "open_positions": open_pos.get("count", 0),
                    "portfolio_heat_pct": 0.0,
                },
            }
            return strict_context, analysis
        except Exception:
            pass
    strict_context = get_synthetic_risk_context(symbol)
    return strict_context, None


async def _case_risk_gate(session: Any, settings: dict[str, Any], ex: Any, fn: Callable[..., Any]) -> BenchmarkCase:
    symbol = _sym(settings)
    strict_context, _ = await _build_strict_risk_context(session, settings, ex, symbol)
    return BenchmarkCase(
        symbol,
        "risk",
        custom_fn=fn,
        custom_args=(symbol, strict_context),
        role_kwargs=dict(max_tokens=500, thinking="low"),
        context_summary=json.dumps(strict_context, default=str),
    )


async def _case_risk_gate_conservative(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _case_risk_gate(session, settings, ex, analyze_risk_conservative_llm)


async def _case_risk_gate_aggressive(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _case_risk_gate(session, settings, ex, analyze_risk_aggressive_llm)


async def _case_risk_gate_neutral(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _case_risk_gate(session, settings, ex, analyze_risk_neutral_llm)


async def _case_portfolio_manager_per_trade(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    strict_context, _ = await _build_strict_risk_context(session, settings, ex, symbol)
    min_rr = settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)
    risk_debate_states = {
        "conservative": analyze_risk_conservative(strict_context),
        "aggressive": analyze_risk_aggressive(strict_context, min_rr_ratio=min_rr),
        "neutral": analyze_risk_neutral(strict_context, min_rr_ratio=min_rr),
    }
    return BenchmarkCase(
        symbol,
        "risk",
        custom_fn=make_portfolio_decision,
        custom_args=(symbol, risk_debate_states, strict_context["actual_risk_state"]),
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=json.dumps(
            {"risk_debate_states": risk_debate_states, "actual_risk_state": strict_context["actual_risk_state"]},
            default=str,
        ),
    )


_PORTFOLIO_SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string", "enum": ["execute_all", "reduce"]},
        "keep": {"type": "array", "items": {"type": "string"}},
        "size_adjustments": {"type": "object"},
        "reasoning": {"type": "string"},
    },
    "required": ["recommendation", "keep", "reasoning"],
}


async def _case_portfolio_synthesis(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    rows = []
    if not use_fixtures and session:
        try:
            from sqlalchemy import select as _sel

            from monika.infrastructure.database.models import AssetAnalysis as _AA

            rows = (
                (
                    await session.execute(
                        _sel(_AA).where(_AA.decision.in_(["buy", "sell"])).order_by(_AA.generated_at.desc()).limit(3)
                    )
                )
                .scalars()
                .all()
            )
        except Exception:
            rows = []
    if use_fixtures or len(rows) < 2:
        concurrent = get_golden_concurrent_orders()
        proposals = concurrent.get("simultaneous_order_proposals", [])
        if proposals:
            summaries = [
                f"- {p['symbol']} {p['decision']}: confidence={int(p.get('confidence', 0.8) * 100)}% "
                f"(Entry {p.get('entry_price')}, SL {p.get('stop_loss')}, TP {p.get('take_profit')}, "
                f"Risk ${p.get('risk_amount_usd', 400)} / {p.get('risk_pct', 0.5)}%, Confluence {p.get('confluence_score', 10)}/14)"
                for p in proposals
            ]
        else:
            summaries = [
                "- EURUSD BUY: confidence=82% (Entry 1.1065, SL 1.1035, TP 1.1135, R:R 2.33)",
                "- GBPUSD WAIT: confidence=60% (Entry 1.3020, range bound chop)",
                "- USDJPY SELL: confidence=78% (Entry 143.80, SL 144.60, TP 142.20, R:R 2.10)",
                "- XAUUSD BUY: confidence=85% (Entry 2658.50, SL 2642.00, TP 2695.00, R:R 2.45)",
                "- XTIUSD BUY: confidence=80% (Entry 71.85, SL 70.40, TP 74.50, R:R 2.00)",
            ]
        brief_sentiment = concurrent.get("market_regime", "selective_risk_off")
        brief_confidence = 0.82
        vix_val = 16.70
    else:
        summaries = [f"- {r.symbol} {r.decision.upper()}: confidence={r.confidence:.0%}" for r in rows]
        try:
            brief = await latest_brief(session)
            brief_sentiment = brief.risk_sentiment
            brief_confidence = brief.confidence
        except Exception:
            brief_sentiment = "neutral"
            brief_confidence = 0.70
        try:
            vix = await ex.execute("get_vix", {}) if ex else {}
            vix_val = (vix.get("latest") or {}).get("close", 16.70)
        except Exception:
            vix_val = 16.70
    prompt = (
        f"Portfolio Review: Multiple proposed trades across asset universe.\n\nProposed Trades:\n"
        + "\n".join(summaries)
        + f"\n\nRisk sentiment: {brief_sentiment}\nBrief confidence: {brief_confidence}\n"
        f"VIX: {vix_val}\n\n"
        "Execute ALL of these trades, or REDUCE portfolio exposure due to correlation/risk clustering? Respond with "
        "recommendation, keep[], optional size_adjustments{symbol:multiplier}, and reasoning."
    )
    return BenchmarkCase(
        "portfolio",
        "risk",
        "",
        prompt,
        schema=_PORTFOLIO_SYNTHESIS_SCHEMA,
        role_kwargs=dict(max_tokens=800, thinking="high"),
        context_summary=prompt,
    )


_ADVERSARIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean"},
        "overall_quality": {"type": "string", "enum": ["high", "medium", "low"]},
        "strongest_counter_argument": {"type": "string"},
        "hard_block": {"type": "boolean"},
        "hard_block_reason": {"type": "string"},
        "recommend_block": {"type": "boolean"},
        "block_reason": {"type": "string"},
    },
    "required": ["approve", "overall_quality", "strongest_counter_argument", "hard_block", "recommend_block"],
}


async def _case_adversarial_check(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    if use_fixtures:
        adv = get_golden_adversarial_case()
        symbol = adv.get("symbol", symbol)
        decision = "BUY"
        confluence = 11
        priced_in = 3
        invalidation = "Break below 1.1030"
        entry_zone = "1.1055 - 1.1070"
        sl, tp = 1.1035, 1.1135
        traps = "\n".join(f"- {t}" for t in adv.get("hidden_traps", []))
        rationale = f"{adv.get('setup_appearance')}\nContext Hazards:\n{traps}"
    else:
        decision = "BUY"
        confluence = 11
        priced_in = 3
        invalidation = "Break below 1.1030"
        entry_zone = "1.1055 - 1.1070"
        sl, tp = 1.1035, 1.1135
        rationale = "H1 BOS bullish after liquidity sweep below London low. Risk-reward is 2.33."
        if session:
            try:
                analysis = await pick_asset_analysis(session, symbol)
                decision = (analysis.decision or "BUY").upper()
                confluence = analysis.confluence_score
                priced_in = analysis.priced_in_score
                invalidation = analysis.invalidation or invalidation
                entry_zone = str(analysis.entry_zone)
                sl = analysis.stop_loss or sl
                tp = analysis.take_profit or tp
                rationale = analysis.rationale or rationale
            except Exception:
                pass
    prompt = (
        f"Symbol: {symbol}\nDirection: {decision}\n"
        f"Confluence Score: {confluence}/14\nPriced-In Score: {priced_in}/10\n"
        f"Invalidation: {invalidation}\nEntry context: {entry_zone}\n"
        f"SL: {sl}  TP: {tp}\n\n"
        f"Full Rationale:\n{rationale[:3500]}\n\n"
        "Find the STRONGEST argument against this specific trade. hard_block=true only for objective "
        "defects (mathematical error, self-contradiction, missing invalidation). recommend_block=true "
        "for significant non-fatal risk."
    )
    return BenchmarkCase(
        symbol,
        "risk",
        "You are a skeptical risk-desk reviewer conducting a final pre-trade challenge.",
        prompt,
        schema=_ADVERSARIAL_SCHEMA,
        role_kwargs=dict(max_tokens=1200, thinking="medium"),
        context_summary=prompt,
    )


async def _case_risk_gate_task(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    risk_state = get_golden_risk_state("baseline")
    acct = risk_state.get("account_state", {})
    prop = risk_state.get("proposed_trade", {})
    prompt = (
        f"Subagent Risk Gate Compliance Audit:\n"
        f"Account Equity: ${acct.get('equity', 76849.91):,.2f} | Free Margin: ${acct.get('margin_free', 75200.0):,.2f}\n"
        f"Daily Realized PnL: ${acct.get('daily_realized_pnl', -350.0):,.2f} | Daily Drawdown: {acct.get('daily_drawdown_pct', 1.2)}%\n"
        f"Open Positions: {acct.get('open_positions_count', 2)} | Max Daily Loss Limit: ${acct.get('max_daily_loss_limit_usd', 1500.0):,.2f}\n\n"
        f"Proposed Order:\n"
        f"Symbol: {prop.get('symbol', 'EURUSD')} {prop.get('direction', 'BUY')} | Lots: {prop.get('calculated_lots', 1.5)}\n"
        f"Entry: {prop.get('entry_price', 1.1065)} | SL: {prop.get('stop_loss', 1.1035)} | TP: {prop.get('take_profit', 1.1135)}\n"
        f"Risk Amount: ${prop.get('risk_amount_usd', 450.0):,.2f} | R:R: {prop.get('risk_reward_ratio', 2.33)}\n\n"
        "Evaluate compliance with portfolio risk gates, capital preservation rules, and maximum loss limits."
    )
    return BenchmarkCase(
        "risk_gate",
        "risk",
        system_prompt="You are a Subagent Risk Gate Auditor.",
        user_prompt=prompt,
        schema={
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "veto_reason": {"type": "string"},
                "multiplier": {"type": "number"},
            },
            "required": ["approved", "multiplier"],
        },
        role_kwargs=dict(max_tokens=1024, thinking="medium"),
        context_summary=prompt,
    )
