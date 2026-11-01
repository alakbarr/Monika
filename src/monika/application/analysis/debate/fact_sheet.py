import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import (
    AssetAnalysis,
    DXYData,
    FundamentalBrief,
    FVGZone,
    OrderBlock,
    TechnicalIndicator,
)

logger = logging.getLogger("TradingAgent.FactSheet")


async def build_fact_sheet(session: AsyncSession, analysis_id: Any) -> Dict[str, Any]:
    """
    Build a deterministically verified fact sheet for the debate node.
    This prevents AI hallucination during debates by providing an exact ground-truth reference.
    """
    if isinstance(analysis_id, AssetAnalysis):
        analysis = analysis_id
    else:
        analysis = (
            await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == analysis_id))
        ).scalar_one_or_none()

    if not analysis:
        raise ValueError(f"Analysis {analysis_id} not found for fact sheet")

    entry_zone = {}
    if analysis.entry_zone:
        try:
            entry_zone = json.loads(analysis.entry_zone)
        except Exception:
            pass

    entry_price = entry_zone.get("price") or analysis.price_at_analysis or 0
    sl = analysis.stop_loss or 0
    tp = analysis.take_profit or 0
    sl_dist = abs(entry_price - sl) if sl != 0 else 0
    tp_dist = abs(entry_price - tp) if tp != 0 else 0
    rr_calculated = tp_dist / sl_dist if sl_dist > 0 else 0

    # Fetch ATR
    atr_row = (
        await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == analysis.symbol)
            .where(TechnicalIndicator.timeframe == "H4")
            .where(TechnicalIndicator.indicator_name == "ATR_14")
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    atr = 0
    if atr_row:
        try:
            raw = json.loads(atr_row.value_json)
            atr = float(raw.get("atr", 0) if isinstance(raw, dict) else raw)
        except Exception:
            pass

    # Check FVG proximity
    nearest_fvg = "NONE"
    fvg_distance = float("inf")
    if entry_price and entry_price > 0:
        fvgs = (
            (
                await session.execute(
                    select(FVGZone)
                    .where(FVGZone.symbol == analysis.symbol)
                    .where(FVGZone.timeframe == "H4")
                    .where(FVGZone.filled_at.is_(None))
                    .order_by(FVGZone.formed_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        for fvg in fvgs:
            mid = (fvg.gap_high + fvg.gap_low) / 2
            dist = abs(entry_price - mid)
            if dist < fvg_distance:
                fvg_distance = dist
                nearest_fvg = f"FVG {fvg.direction}: {fvg.gap_low:.5f}-{fvg.gap_high:.5f}"

    # Check OB proximity
    nearest_ob = "NONE"
    ob_distance = float("inf")
    if entry_price and entry_price > 0:
        obs = (
            (
                await session.execute(
                    select(OrderBlock)
                    .where(OrderBlock.symbol == analysis.symbol)
                    .where(OrderBlock.timeframe == "H4")
                    .where(OrderBlock.mitigated_at.is_(None))
                    .order_by(OrderBlock.formed_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        for ob in obs:
            mid = (ob.price_high + ob.price_low) / 2
            dist = abs(entry_price - mid)
            if dist < ob_distance:
                ob_distance = dist
                nearest_ob = f"OB {ob.direction}: {ob.price_low:.5f}-{ob.price_high:.5f}"

    # Fetch currency bias and DXY
    brief = (
        await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
    ).scalar_one_or_none()

    currency_bias_str = "N/A"
    if brief and brief.structured_json:
        try:
            b_data = json.loads(brief.structured_json)
            currency_bias_str = b_data.get("currency_bias") or "N/A"
        except Exception:
            pass

    dxy_rows = (await session.execute(select(DXYData).order_by(DXYData.date.desc()).limit(5))).scalars().all()
    dxy_trend = "unknown"
    if len(dxy_rows) >= 3:
        dxy_trend = "strengthening" if dxy_rows[0].close > dxy_rows[-1].close else "weakening"

    confluence_factors = []
    if analysis.confluence_factors_json:
        try:
            confluence_factors = json.loads(analysis.confluence_factors_json)
        except Exception:
            pass

    # Fetch historical win rate for this symbol
    from monika.infrastructure.database.models import PaperTradeRecord, Position

    historical_positions = (
        (
            await session.execute(
                select(Position).where(Position.symbol == analysis.symbol).where(Position.status == "closed")
            )
        )
        .scalars()
        .all()
    )

    win_rate = 0.0
    total_trades = len(historical_positions)
    if total_trades > 0:
        winning_trades = sum(1 for p in historical_positions if p.pnl and p.pnl > 0)
        win_rate = winning_trades / total_trades
    else:
        try:
            paper_trades = (
                (
                    await session.execute(
                        select(PaperTradeRecord)
                        .where(PaperTradeRecord.symbol == analysis.symbol)
                        .where(PaperTradeRecord.status == "closed")
                    )
                )
                .scalars()
                .all()
            )
            total_trades = len(paper_trades)
            if total_trades > 0:
                winning_trades = sum(
                    1
                    for p in paper_trades
                    if (getattr(p, "pnl_pct", None) or 0) > 0
                    or (getattr(p, "pnl", None) or 0) > 0
                    or (getattr(p, "realized_pnl", None) or 0) > 0
                )
                win_rate = winning_trades / total_trades
        except Exception:
            pass

    core_mem_str = None
    try:
        from monika.application.analysis.memory.layered_memory import LayeredMemoryManager

        mem_mgr = LayeredMemoryManager({})
        core_mem_str = await mem_mgr.get_core_memory(session)
    except Exception:
        pass

    vix_val = None
    try:
        from monika.infrastructure.database.models import VIXData

        vix_row = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
        if vix_row:
            vix_val = round(vix_row.close, 1)
    except Exception:
        pass

    chronicle_str = None
    sys_cfg: Dict[str, Any] = {}
    try:
        from monika.application.analysis.memory.chronicle_writer import ChronicleWriter
        from monika.core.config.settings import load_all_config

        sys_cfg = load_all_config()
        c_writer = ChronicleWriter(sys_cfg)
        chronicle_str = await c_writer.get_condensed_chronicle_bullets(session, analysis.symbol, days_back=30, limit=4)
        if not chronicle_str:
            chronicle_str = await c_writer.get_chronicle_for_symbol(session, analysis.symbol, days_back=30, limit=3)
    except Exception as c_err:
        logger.debug(f"FactSheet chronicle fetch failed: {c_err}")

    # Order Flow & Liquidity Delta
    order_flow_data = {
        "mode": "SYNTHETIC_TICK_RULE",
        "book_imbalance": 0.0,
        "cvd_session": 0.0,
        "cvd_divergence": "NONE",
    }
    try:
        from monika.application.services.order_flow_service import fetch_latest_order_flow

        of_snap = await fetch_latest_order_flow(session, analysis.symbol)
        if of_snap:
            order_flow_data = {
                "mode": of_snap.mode,
                "book_imbalance": of_snap.order_book_imbalance,
                "cvd_session": of_snap.cvd_session_delta,
                "cvd_divergence": of_snap.cvd_divergence,
            }
    except Exception as of_err:
        logger.debug(f"FactSheet order flow fetch note: {of_err}")

    curr_px = float(entry_price or getattr(analysis, "price_at_analysis", 0) or 0.0)
    atr_val = float(atr or 0.0)
    dealing_range_pos = 0.5
    h4_impulse_atr = 0.0
    try:
        from monika.infrastructure.database.models import PriceOHLCV

        h4_stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == analysis.symbol)
            .where(PriceOHLCV.timeframe == "H4")
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(20)
        )
        h4_rows = list((await session.execute(h4_stmt)).scalars().all())
        if h4_rows:
            h4_rows.reverse()
            highs = [float(r.high) for r in h4_rows if getattr(r, "high", None) is not None]
            lows = [float(r.low) for r in h4_rows if getattr(r, "low", None) is not None]
            closes = [float(r.close) for r in h4_rows if getattr(r, "close", None) is not None]
            ref_px = curr_px if curr_px > 0 else (closes[-1] if closes else 0.0)
            if highs and lows and max(highs) > min(lows) and ref_px > 0:
                raw_pos = (ref_px - min(lows)) / (max(highs) - min(lows))
                dealing_range_pos = round(max(0.0, min(1.0, raw_pos)), 4)
            if atr_val <= 0 and highs and lows and len(highs) == len(lows):
                atr_val = float(sum(h - l for h, l in zip(highs, lows)) / len(highs))
            if len(closes) >= 3 and atr_val > 0 and ref_px > 0:
                h4_impulse_atr = round((ref_px - closes[-3]) / atr_val, 4)
            elif len(closes) >= 2 and atr_val > 0 and ref_px > 0:
                h4_impulse_atr = round((ref_px - closes[0]) / atr_val, 4)
    except Exception as h4_err:
        logger.debug(f"FactSheet H4 dealing range/impulse calculation note: {h4_err}")

    biases_dict: Dict[str, str] = {}
    raw_spec = getattr(analysis, "specialist_biases_json", None)
    if raw_spec:
        try:
            parsed_spec = json.loads(raw_spec) if isinstance(raw_spec, str) else raw_spec
            if isinstance(parsed_spec, dict):
                inner_biases = parsed_spec.get("biases")
                if isinstance(inner_biases, dict):
                    biases_dict = {str(k).lower(): str(v).lower() for k, v in inner_biases.items() if v}
                else:
                    biases_dict = {
                        str(k).lower(): str(v).lower()
                        for k, v in parsed_spec.items()
                        if k in ("technical", "sentiment", "macro") and isinstance(v, str)
                    }
        except Exception:
            pass

    t_b = biases_dict.get("technical", "")
    s_b = biases_dict.get("sentiment", "")
    m_b = biases_dict.get("macro", "")

    if (t_b == "bullish" and s_b == "bullish" and m_b == "bearish") or (
        t_b == "bearish" and s_b == "bearish" and m_b == "bullish"
    ):
        synergy_state = "crowded_tech_sent_trap_vs_macro"
    elif t_b and m_b and t_b != "neutral" and t_b == m_b and s_b != t_b:
        synergy_state = "uncrowded_institutional_synergy"
    elif t_b and m_b and s_b and t_b != "neutral" and t_b == m_b == s_b:
        synergy_state = "crowded_unanimous_exhaustion"
    else:
        synergy_state = "mixed_council"

    if synergy_state == "crowded_tech_sent_trap_vs_macro" and m_b in ("bullish", "bearish"):
        dominant_bias = m_b
    elif t_b in ("bullish", "bearish") and t_b == m_b:
        dominant_bias = t_b
    elif m_b in ("bullish", "bearish"):
        dominant_bias = m_b
    elif t_b in ("bullish", "bearish"):
        dominant_bias = t_b
    else:
        dominant_bias = "neutral"

    specialist_consensus = {
        "biases": biases_dict,
        "synergy_state": synergy_state,
        "dominant_bias": dominant_bias,
    }

    if 0.40 <= dealing_range_pos <= 0.60 and abs(h4_impulse_atr) < 0.25:
        regime_classification = "EQUILIBRIUM_DEAD_ZONE_CHOP"
    elif synergy_state == "crowded_tech_sent_trap_vs_macro":
        regime_classification = "CROWDED_TECH_SENT_TRAP_VS_MACRO"
    elif h4_impulse_atr >= 1.25:
        regime_classification = "BULLISH_IMPULSE_BREAKOUT"
    elif h4_impulse_atr <= -1.25:
        regime_classification = "BEARISH_IMPULSE_BREAKOUT"
    elif dealing_range_pos >= 0.80 and h4_impulse_atr < 1.25:
        regime_classification = "OVEREXTENDED_RANGE_CEILING_PULLBACK_RISK"
    elif dealing_range_pos <= 0.38:
        regime_classification = "DISCOUNT_ACCUMULATION_ZONE"
    elif dealing_range_pos >= 0.60:
        regime_classification = "UPPER_RANGE_TREND_CONTINUATION"
    else:
        regime_classification = "MID_RANGE_DIRECTIONAL_FLOW"

    daily_range_context: Dict[str, Any] = {}
    try:
        from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context

        adr_res = await compute_daily_range_context(
            session, analysis.symbol, sys_cfg or {}, atr_h4=atr_val if atr_val > 0 else None
        )
        if isinstance(adr_res, dict):
            daily_range_context = adr_res
    except Exception as adr_err:
        logger.debug(f"FactSheet daily_range_context note: {adr_err}")

    bracket_options: Dict[str, Any] = {}
    try:
        from monika.application.analysis.calculators.invariant_calculator import generate_concrete_bracket_options

        eff_atr = atr_val if atr_val > 0 else (curr_px * 0.005 if curr_px > 0 else 0.0)
        if curr_px > 0 and eff_atr > 0:
            bracket_options = generate_concrete_bracket_options(
                symbol=analysis.symbol,
                current_price=curr_px,
                atr=eff_atr,
            )
    except Exception as bo_err:
        logger.debug(f"FactSheet bracket_options note: {bo_err}")

    fact_sheet = {
        "symbol": analysis.symbol,
        "proposed_decision": analysis.decision,
        "entry_price": entry_price,
        "stop_loss": sl,
        "take_profit": tp,
        "sl_dist": sl_dist,
        "tp_dist": tp_dist,
        "risk_reward_ratio": round(rr_calculated, 2),
        "confluence_score": analysis.confluence_score,
        "confluence_factors": confluence_factors,
        "rationale": analysis.rationale,
        "atr": round(atr_val, 5),
        "atr_14_h4": round(atr_val, 5),
        "dealing_range_pos": dealing_range_pos,
        "h4_impulse_atr": h4_impulse_atr,
        "specialist_consensus": specialist_consensus,
        "regime_classification": regime_classification,
        "daily_range_context": daily_range_context,
        "bracket_options": bracket_options,
        "nearest_fvg": nearest_fvg,
        "fvg_distance": round(fvg_distance, 5) if fvg_distance != float("inf") else None,
        "nearest_ob": nearest_ob,
        "ob_distance": round(ob_distance, 5) if ob_distance != float("inf") else None,
        "currency_bias": currency_bias_str,
        "dxy_trend": dxy_trend,
        "vix": vix_val,
        "fundamental_brief_confidence": brief.confidence if brief else None,
        "historical_win_rate_pct": round(win_rate * 100, 1),
        "historical_trades_count": total_trades,
        "active_core_regime_and_lessons": core_mem_str[:400] if core_mem_str else None,
        "active_market_chronicle": chronicle_str,
        "order_flow": order_flow_data,
    }

    try:
        from monika.application.graph.nodes.debate.helpers import inject_telemetry_reliability_into_fact_sheet

        fact_sheet = await inject_telemetry_reliability_into_fact_sheet(session, fact_sheet)
    except Exception as t_err:
        logger.debug(f"FactSheet telemetry injection error: {t_err}")

    # Inject empirical OHLCV market grounding table to strictly anchor debate agents
    try:
        from monika.application.analysis.grounding.market_grounding import MarketGroundingEngine

        fact_sheet["empirical_market_grounding"] = await MarketGroundingEngine.build_grounding_table(
            symbol=analysis.symbol, session=session, days_back=30
        )
    except Exception as g_err:
        logger.debug(f"FactSheet grounding injection note: {g_err}")
        fact_sheet["empirical_market_grounding"] = ""

    # Inject user chart workspace summary and telemetry for debate agents (Wave 2)
    try:
        from monika.application.services.technical_indicator_service import TechnicalIndicatorService
        from monika.infrastructure.database.repositories.user_preference_repository import (
            SqlAlchemyUserPreferenceRepository,
        )

        ws_repo = SqlAlchemyUserPreferenceRepository(session)
        workspace_config = await ws_repo.resolve_chart_workspace_config(analysis.symbol)
        tech_svc = TechnicalIndicatorService(session)
        ws_summary = await tech_svc.compute_multi_tf_workspace_summary(analysis.symbol, workspace_config)
        if ws_summary and ws_summary.get("overall_bias") and ws_summary.get("formatted_report"):
            fact_sheet["user_chart_workspace_telemetry"] = (
                f"[USER CHART WORKSPACE TELEMETRY]\n{str(ws_summary['formatted_report']).strip()}"
            )
            fact_sheet["user_chart_workspace_bias"] = ws_summary["overall_bias"]
            fact_sheet["user_chart_workspace_confluence_adj"] = ws_summary.get("confluence_adjustment", 0)
    except Exception as ws_err:
        logger.debug(f"FactSheet user chart workspace fetch note: {ws_err}")

    return fact_sheet
