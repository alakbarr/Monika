# ==============================================================================
# File: graph/nodes/debate/helpers.py
# ==============================================================================

import sys
import re
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import utils.clock as clock
from database.db import get_session
from database.models import AssetAnalysis, RiskState, Position, SystemConfig
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.Graph.Debate.Helpers")


async def _get_recent_sl_streak(session, symbol: str) -> int:
    from database.models import PaperTradeRecord
    from sqlalchemy import select
    recent = (await session.execute(
        select(PaperTradeRecord).where(PaperTradeRecord.symbol == symbol)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
        .order_by(PaperTradeRecord.closed_at.desc()).limit(5)
    )).scalars().all()
    streak = 0
    for r in recent:
        if r.exit_reason == 'sl_hit':
            streak += 1
        else:
            break
    return streak


async def _get_correlated_exposure_summary(session, symbol: str) -> List[str]:
    from database.models import Position
    from utils.market.dynamic_correlation import get_rolling_correlation
    from sqlalchemy import select
    open_positions = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
    summary = []
    for pos in open_positions:
        if pos.symbol == symbol:
            continue
        try:
            corr, source = await get_rolling_correlation(session, symbol, pos.symbol)
            if abs(corr) > 0.5:
                summary.append(f"{pos.symbol} {pos.direction} (corr={corr:.2f}[{source}])")
        except Exception:
            pass
    return summary


def _is_grounded(claim_dict: dict, current_price: float) -> bool:
    if not claim_dict:
        return False
    text = str(claim_dict)
    raw_nums = re.findall(r'\b\d+(?:\.\d+)?\b', text)
    if not raw_nums:
        return False
    if current_price > 0:
        nums = [float(x) for x in raw_nums]
        has_plausible_price = any(abs(n - current_price) / current_price <= 0.20 for n in nums)
        return has_plausible_price or len(nums) >= 2
    return len(raw_nums) >= 2


def _apply_deterministic_risk_clamp(pm_decision: dict, risk_stances: dict, actual_risk_state: dict | None) -> dict:
    veto_count = sum(1 for stance in ('conservative', 'aggressive', 'neutral') if risk_stances.get(stance, {}).get('veto_trade'))
    multiplier = float(pm_decision.get('recommended_risk_multiplier', 1.0) or 0.0)
    approval = bool(pm_decision.get('approval', False))
    reasons = []
    if veto_count >= 3:
        multiplier = 0.0
        approval = False
        reasons.append(f'deterministic_veto_consensus({veto_count}/3)')
    elif veto_count >= 2:
        multiplier = min(multiplier, 0.50)
        reasons.append(f'persona_veto_dampened({veto_count}/3, 0.50 cap)')
    elif veto_count >= 1:
        multiplier = min(multiplier, 0.75)
        reasons.append(f'persona_veto_dampened({veto_count}/3, 0.75 cap)')
    if actual_risk_state:
        daily_pnl_pct = actual_risk_state.get('daily_pnl_pct', 0.0)
        heat_pct = actual_risk_state.get('portfolio_heat_pct', 0.0)
        if daily_pnl_pct is not None and daily_pnl_pct < -2.0 and multiplier > 0.5:
            multiplier = 0.5
            reasons.append(f'daily_pnl_{daily_pnl_pct:.2f}pct_cap')
        if heat_pct is not None and heat_pct > 3.0 and multiplier > 0.5:
            multiplier = 0.5
            reasons.append(f'portfolio_heat_{heat_pct:.1f}pct_cap')
    multiplier = max(0.0, min(1.5, multiplier))
    if multiplier <= 0.0:
        approval = False
    pm_decision['recommended_risk_multiplier'] = round(multiplier, 3)
    pm_decision['approval'] = approval
    if reasons:
        pm_decision['deterministic_overrides'] = reasons
        logger.warning(f"[PortfolioManager][{'/'.join(reasons)}] clamp applied -> multiplier={multiplier}, approval={approval}")
    return pm_decision


async def compute_actual_risk_state(session, settings: dict, mt5_client=None) -> Dict[str, Any]:
    """Menghitung actual_risk_state (equity, daily_pnl_pct, portfolio_heat_pct)."""
    from sqlalchemy import select
    today_start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    risk_state_obj = (await session.execute(
        select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
    )).scalar_one_or_none()
    open_pos_rows = (await session.execute(select(Position).where(Position.status == 'open'))).scalars().all()
    open_pos = len(open_pos_rows)

    equity = 10000.0
    if mt5_client:
        try:
            account_info = await mt5_client.get_account_info()
            if account_info and account_info.get('equity', 0) > 0:
                equity = float(account_info['equity'])
        except Exception as e:
            logger.debug(f'[DebateHelpers] Gagal ambil equity live, pakai fallback {equity}: {e}')

    daily_pnl_pct = round((risk_state_obj.daily_pnl / equity) * 100, 3) if risk_state_obj and equity > 0 else 0.0

    portfolio_heat_pct = 0.0
    try:
        from risk.position_sizing import PositionSizer
        sizer = PositionSizer(settings, mt5_client=mt5_client)
        heat_usd = 0.0
        for pos in open_pos_rows:
            if pos.entry_price and pos.sl:
                sl_distance = abs(pos.entry_price - pos.sl)
                spec = await sizer._get_instrument_spec_dynamic(session, pos.symbol)
                if spec and spec.pip_size > 0 and spec.pip_value_per_lot > 0:
                    sl_distance_pips = sl_distance / spec.pip_size
                    heat_usd += sl_distance_pips * spec.pip_value_per_lot * pos.volume
        portfolio_heat_pct = round((heat_usd / equity) * 100, 2) if equity > 0 else 0.0
    except Exception as e:
        logger.debug(f'[DebateHelpers] Perhitungan heat riil gagal, fallback estimasi: {e}')
        portfolio_heat_pct = float(open_pos) * 1.5

    return {
        'daily_pnl_pct': daily_pnl_pct,
        'open_positions': open_pos,
        'portfolio_heat_pct': portfolio_heat_pct,
        'risk_budget_remaining_pct': max(0.0, 100.0 - float(risk_state_obj.current_drawdown) / 50.0 * 100) if risk_state_obj else 100.0,
    }


async def inject_coherence_and_intel(session, sym: str, bull_thesis: str, user_market_intel: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """Menginjeksi CDS Context Divergence Score alert & user operator market intel ke thesis."""
    # 1. CDS Alert
    try:
        mon_key = f'context_drift_{sym}'
        from sqlalchemy import select
        drift_cfgs = (await session.execute(
            select(SystemConfig)
            .where(SystemConfig.key.like(f'{mon_key}%'))
            .order_by(SystemConfig.updated_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if drift_cfgs and drift_cfgs.value:
            drift_data = json.loads(drift_cfgs.value)
            drift_ts = datetime.fromisoformat(drift_data.get('timestamp'))
            if drift_ts.tzinfo is None:
                drift_ts = drift_ts.replace(tzinfo=timezone.utc)
            if (clock.now() - drift_ts).total_seconds() < 7200:
                cds_score = drift_data.get('cds_score', 0)
                if cds_score >= 0.35:
                    alert_msg = (
                        f"\n\n[CRITICAL MACRO CONTEXT ALERT]: "
                        f"The Stage 1 macro brief has a Context Divergence Score of {cds_score:.2f} "
                        f"against recent price action for {sym}. "
                        f"The Bear Analyst MUST aggressively challenge the Bull Thesis on "
                        f"macro grounds if the Bull relies on outdated Stage 1 narrative."
                    )
                    bull_thesis += alert_msg
                    logger.info(f'[{sym}] Debate Node injected CDS alert (Score: {cds_score:.2f})')
    except Exception as _coh_err:
        logger.debug(f'[{sym}] Failed to inject coherence alert in debate: {_coh_err}')

    # 2. Operator Intel
    rel_intel = []
    sym_clean = sym.upper().replace('/', '')
    for item in (user_market_intel or []):
        raw_aff = item.get("affected_symbols") or []
        if isinstance(raw_aff, str):
            aff_list = [s.strip() for s in raw_aff.split(",") if s.strip()]
        else:
            aff_list = list(raw_aff)
        aff = [s.upper().replace('/', '') for s in aff_list]
        if not aff or "ALL" in aff or sym_clean in aff:
            rel_intel.append(item)
    if rel_intel:
        intel_block = ["\n\n[OPERATOR MARKET INTELLIGENCE & DIRECTIVES]"]
        for it in rel_intel:
            intel_block.append(f"- ID #{it.get('id')} [{it.get('intel_type', '').upper()}]: {it.get('title')}")
            intel_block.append(f"  Directive: {it.get('directive', 'neutral')} | Target Cycle: {it.get('target_cycle', 'continuous')}")
            intel_block.append(f"  Summary: {it.get('summary')}")
        bull_thesis += "\n".join(intel_block)

    return bull_thesis, rel_intel


async def inject_telemetry_reliability_into_fact_sheet(session, fact_sheet: dict) -> dict:
    """
    Injects specialist trust weights and news classification accuracy into the debate FactSheet.
    Allows the Investment Judge to dynamically discount arguments originating from unreliable specialists.
    """
    if not isinstance(fact_sheet, dict):
        return fact_sheet

    # 1. Specialist Reliability & Trust Weights
    try:
        from utils.analytics.specialist_tracker import compute_specialist_reliability
        rel = await compute_specialist_reliability(session, days_back=45)
        specialists = rel.get("specialists", {})
        if specialists:
            fact_sheet["specialist_reliability"] = {
                spec: {
                    "accuracy_pct": d.get("accuracy_pct"),
                    "trust_weight": d.get("trust_weight"),
                    "chronically_unreliable": d.get("chronically_unreliable", False),
                    "total_samples": d.get("total", 0),
                }
                for spec, d in specialists.items()
            }
    except Exception as e:
        logger.debug(f"Failed to fetch specialist reliability for FactSheet: {e}")

    # 2. News Classification Directives & Accuracy
    try:
        from database.models import SystemConfig
        from sqlalchemy import select
        cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "news_tier_calibration_directives")
        )).scalar_one_or_none()
        if cfg and cfg.value:
            data = json.loads(cfg.value)
            fact_sheet["news_calibration_directives"] = data.get("directives", [])
    except Exception as e:
        logger.debug(f"Failed to fetch news calibration directives for FactSheet: {e}")

    return fact_sheet


def sync_facade_patches():
    """Propagate any monkey-patched module attributes from debate_node facade to sub-agent modules."""
    curr_mod = sys.modules.get("graph.nodes.debate_node")
    if not curr_mod:
        return
    mod_names = [
        "graph.nodes.debate.bull_advocate_node",
        "graph.nodes.debate.bear_dissent_node",
        "graph.nodes.debate.rebuttal_node",
        "graph.nodes.debate.debate_judge_node",
        "graph.nodes.debate.risk_evaluator_node",
        "graph.nodes.debate.helpers",
    ]
    mods = [sys.modules[m] for m in mod_names if m in sys.modules]
    props = [
        "get_session", "get_client_for_task", "generate_bull_advocacy", "generate_bull_rebuttal",
        "generate_bear_dissent", "evaluate_debate", "build_fact_sheet", "validate_and_apply_judge_adjustments",
        "analyze_risk_conservative", "analyze_risk_aggressive", "analyze_risk_neutral",
        "make_portfolio_decision_deterministic", "analyze_risk_conservative_llm",
        "analyze_risk_aggressive_llm", "analyze_risk_neutral_llm", "make_portfolio_decision"
    ]
    try:
        from unittest.mock import Base as MockBase
    except ImportError:
        MockBase = tuple()

    for p in props:
        if hasattr(curr_mod, p):
            val = getattr(curr_mod, p)
            if isinstance(val, MockBase) or type(val).__name__ in ('MagicMock', 'AsyncMock', 'Mock'):
                for m in mods:
                    setattr(m, p, val)
