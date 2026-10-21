# ==============================================================================
# File: application/benchmark/task_specs/stage2_cases.py
# ==============================================================================

"""
Stage 2 per-asset analysis, prescreen, and session trigger benchmark task specs.
"""

from __future__ import annotations

import json
from typing import Any

from monika.application.analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.application.analysis.stages.per_asset_stage import SYMBOL_TO_COT
from monika.application.analysis.tools.tools_definitions import PER_ASSET_ANALYSIS_TOOLS
from monika.application.skills.loader import compose_system_prompt

from ..fixture_loader import (
    get_golden_prescreen_matrix,
    get_synthetic_fundamental_brief,
    get_synthetic_stage2_bundle,
)
from .base import BenchmarkCase, _sym


def _stage2_system_prompt(settings: dict[str, Any], symbol: str, cot_code: str, threshold: int) -> str:
    skills = [
        "smc_ict_playbook",
        "market_dynamics_framework",
        "liquidity_and_macro_edge",
        "risk_management_principles",
        "session_timing_rules",
    ]
    if symbol == "XTIUSD":
        skills.insert(1, "commodity_analysis")
    elif symbol in settings.get("trading", {}).get("24_7_assets", ["BTCUSD"]):
        skills.insert(1, "crypto_analysis")
    if settings.get("trading", {}).get("caveman_mode", False):
        skills.append("caveman_mode")
    body = compose_system_prompt(*skills).replace(
        "{tool_order_guidance}", "Standard data is pre-fetched below; only invoke tools for genuinely missing data."
    )
    static = "You are a professional FX/Gold/commodity/crypto technical analyst using SMC/ICT.\n\n" + body
    dyn = (
        f"\n\n=== CURRENT ANALYSIS TARGET ===\nSymbol: {symbol}\nCOT Code: {cot_code or 'N/A'}\n"
        f"Effective Confluence Threshold: {threshold}/14\n"
        f"Minimum R:R Ratio: {settings.get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.5)}\n"
        "=== END TARGET ===\n"
    )
    return static + dyn


async def _build_stage2_case(session: Any, settings: dict[str, Any], symbol: str, stage_tag: str) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_code = SYMBOL_TO_COT.get(symbol, "")
    threshold = 8
    if not use_fixtures and session:
        try:
            threshold, _ = await compute_unified_confluence_threshold(session, symbol, settings)
        except Exception:
            threshold = 8
    sysp = _stage2_system_prompt(settings, symbol, cot_code, threshold)
    bundle_text = None
    if not use_fixtures and session:
        try:
            from sqlalchemy import select

            from monika.infrastructure.database.models import FundamentalBrief

            b_row = (
                await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
            ).scalar_one_or_none()
            if not b_row:
                import monika.core.primitives.clock as clock

                syn = get_synthetic_fundamental_brief()
                session.add(
                    FundamentalBrief(
                        generated_at=clock.now(),
                        valid_until=clock.now(),
                        content_markdown=syn.get("macro_narrative", ""),
                        structured_json=json.dumps(syn),
                        confidence=0.82,
                        risk_sentiment="selective_risk_off",
                    )
                )
                await session.flush()

            bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
            bundle_text = bundled[0] if isinstance(bundled, tuple) else (bundled or "")
            if "CORE DATA INVALID" in bundle_text or len(bundle_text) < 500:
                bundle_text = None
        except Exception:
            bundle_text = None
    if not bundle_text:
        bundle_text, _ = get_synthetic_stage2_bundle(symbol)
    user_msg = bundle_text + (
        f"\n\nAnalyze {symbol} using pre-fetched data above, then call submit_asset_analysis with your final decision."
    )
    return BenchmarkCase(
        symbol,
        "trade_decision",
        sysp,
        user_msg,
        tools=PER_ASSET_ANALYSIS_TOOLS,
        stage_name=f"benchmark_{stage_tag}_{symbol}",
        role_kwargs=dict(max_tokens=12000, max_tool_turns=10, thinking="high"),
        context_summary=bundle_text[:6000],
    )


async def _case_stage2_primary(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_stage2_case(session, settings, _sym(settings), "stage2_primary")


async def _case_stage2_secondary(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_stage2_case(session, settings, _sym(settings), "stage2_secondary")


async def _case_stage2_session_trigger(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_stage2_case(session, settings, _sym(settings), "stage2_session_trigger")


async def _case_stage2_prescreen(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    vix_val = 16.70
    trading_paused = False
    if use_fixtures:
        matrix = get_golden_prescreen_matrix()
        asset_info = matrix.get(symbol, {})
        if asset_info:
            price_val = asset_info.get("price")
            atr_val = asset_info.get("atr_m15")
            adx_val = asset_info.get("adx_h1")
            spread_val = asset_info.get("spread_points")
            regime = asset_info.get("market_regime")
            prompt = (
                f"Prescreen opportunity evaluation for {symbol}:\n"
                f"Price: {price_val}\n"
                f"ATR(14) M15: {atr_val} | ADX(14) H1: {adx_val}\n"
                f"Spread: {spread_val} points | Regime: {regime}\n"
                f"VIX: {vix_val} | Risk Paused: {trading_paused} | Tier-1 News Next 30m: False\n\n"
                "Evaluate if liquidity, volatility, and market conditions meet requirements for full specialist analysis. "
                "Output YES if viable, NO if risk paused, VIX extreme (>28), or market is dead/illiquid."
            )
            schema = {
                "type": "object",
                "properties": {"decision": {"type": "string", "enum": ["YES", "NO"]}, "reason": {"type": "string"}},
                "required": ["decision", "reason"],
            }
            return BenchmarkCase(
                symbol,
                "trade_decision",
                "",
                prompt,
                schema=schema,
                role_kwargs=dict(max_tokens=256, thinking="none"),
                context_summary=prompt,
            )
    if not use_fixtures and ex:
        try:
            vix = await ex.execute("get_vix", {})
            vix_val = (vix.get("latest") or {}).get("close", 16.70)
            risk_state = await ex.execute("get_risk_state", {})
            trading_paused = risk_state.get("trading_paused", False)
        except Exception:
            pass
    prompt = (
        f"Quick trading opportunity check for {symbol}.\n"
        f"VIX: {vix_val}\nRisk paused: {trading_paused}\n"
        "YES if viable for full analysis, NO if risk is paused / VIX is extreme (>28) / dead market."
    )
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string", "enum": ["YES", "NO"]}, "reason": {"type": "string"}},
        "required": ["decision", "reason"],
    }
    return BenchmarkCase(
        symbol,
        "trade_decision",
        "",
        prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=256, thinking="none"),
        context_summary=prompt,
    )
