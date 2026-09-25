import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
import json

from database.models import AssetAnalysis, TechnicalIndicator, FVGZone, OrderBlock, DXYData, FundamentalBrief

logger = logging.getLogger("TradingAgent.FactSheet")

async def build_fact_sheet(session: AsyncSession, analysis_id: Any) -> Dict[str, Any]:
    """
    Build a deterministically verified fact sheet for the debate node.
    This prevents AI hallucination during debates by providing an exact ground-truth reference.
    """
    if isinstance(analysis_id, AssetAnalysis):
        analysis = analysis_id
    else:
        analysis = (await session.execute(
            select(AssetAnalysis).where(AssetAnalysis.id == analysis_id)
        )).scalar_one_or_none()
    
    if not analysis:
        raise ValueError(f"Analysis {analysis_id} not found for fact sheet")
        
    entry_zone = {}
    if analysis.entry_zone:
        try:
            entry_zone = json.loads(analysis.entry_zone)
        except Exception:
            pass
            
    entry_price = entry_zone.get('price') or analysis.price_at_analysis or 0
    sl = analysis.stop_loss or 0
    tp = analysis.take_profit or 0
    sl_dist = abs(entry_price - sl) if sl != 0 else 0
    tp_dist = abs(entry_price - tp) if tp != 0 else 0
    rr_calculated = tp_dist / sl_dist if sl_dist > 0 else 0
    
    # Fetch ATR
    atr_row = (await session.execute(
        select(TechnicalIndicator)
        .where(TechnicalIndicator.symbol == analysis.symbol)
        .where(TechnicalIndicator.timeframe == 'H4')
        .where(TechnicalIndicator.indicator_name == 'ATR_14')
        .order_by(TechnicalIndicator.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()
    
    atr = 0
    if atr_row:
        try:
            raw = json.loads(atr_row.value_json)
            atr = float(raw.get('atr', 0) if isinstance(raw, dict) else raw)
        except Exception:
            pass
            
    # Check FVG proximity
    nearest_fvg = "NONE"
    fvg_distance = float('inf')
    if entry_price:
        fvgs = (await session.execute(
            select(FVGZone)
            .where(FVGZone.symbol == analysis.symbol)
            .where(FVGZone.timeframe == 'H4')
            .where(FVGZone.filled_at.is_(None))
            .order_by(FVGZone.formed_at.desc())
            .limit(5)
        )).scalars().all()
        
        for fvg in fvgs:
            mid = (fvg.gap_high + fvg.gap_low) / 2
            dist = abs(entry_price - mid)
            if dist < fvg_distance:
                fvg_distance = dist
                nearest_fvg = f"FVG {fvg.direction}: {fvg.gap_low:.5f}-{fvg.gap_high:.5f}"
                
    # Check OB proximity
    nearest_ob = "NONE"
    ob_distance = float('inf')
    if entry_price:
        obs = (await session.execute(
            select(OrderBlock)
            .where(OrderBlock.symbol == analysis.symbol)
            .where(OrderBlock.timeframe == 'H4')
            .where(OrderBlock.mitigated_at.is_(None))
            .order_by(OrderBlock.formed_at.desc())
            .limit(5)
        )).scalars().all()
        
        for ob in obs:
            mid = (ob.price_high + ob.price_low) / 2
            dist = abs(entry_price - mid)
            if dist < ob_distance:
                ob_distance = dist
                nearest_ob = f"OB {ob.direction}: {ob.price_low:.5f}-{ob.price_high:.5f}"
                
    # Fetch currency bias and DXY
    brief = (await session.execute(
        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
    )).scalar_one_or_none()
    
    currency_bias_str = 'N/A'
    if brief and brief.structured_json:
        try:
            b_data = json.loads(brief.structured_json)
            currency_bias_str = b_data.get('currency_bias') or 'N/A'
        except Exception:
            pass
            
    dxy_rows = (await session.execute(
        select(DXYData).order_by(DXYData.date.desc()).limit(5)
    )).scalars().all()
    dxy_trend = 'unknown'
    if len(dxy_rows) >= 3:
        dxy_trend = 'strengthening' if dxy_rows[0].close > dxy_rows[-1].close else 'weakening'
        
    confluence_factors = []
    if analysis.confluence_factors_json:
        try:
            confluence_factors = json.loads(analysis.confluence_factors_json)
        except Exception:
            pass

    # Fetch historical win rate for this symbol
    from database.models import Position, PaperTradeRecord
    historical_positions = (await session.execute(
        select(Position)
        .where(Position.symbol == analysis.symbol)
        .where(Position.status == 'closed')
    )).scalars().all()
    
    win_rate = 0.0
    total_trades = len(historical_positions)
    if total_trades > 0:
        winning_trades = sum(1 for p in historical_positions if p.pnl and p.pnl > 0)
        win_rate = winning_trades / total_trades
    else:
        try:
            paper_trades = (await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == analysis.symbol)
                .where(PaperTradeRecord.status == 'closed')
            )).scalars().all()
            total_trades = len(paper_trades)
            if total_trades > 0:
                winning_trades = sum(1 for p in paper_trades if (getattr(p, 'virtual_pnl', None) or 0) > 0 or (getattr(p, 'pnl', None) or 0) > 0)
                win_rate = winning_trades / total_trades
        except Exception:
            pass

    core_mem_str = None
    try:
        from analysis.memory.layered_memory import LayeredMemoryManager
        mem_mgr = LayeredMemoryManager({})
        core_mem_str = await mem_mgr.get_core_memory(session)
    except Exception:
        pass

    vix_val = None
    try:
        from database.models import VIXData
        vix_row = (await session.execute(
            select(VIXData).order_by(VIXData.date.desc()).limit(1)
        )).scalar_one_or_none()
        if vix_row:
            vix_val = round(vix_row.close, 1)
    except Exception:
        pass

    chronicle_str = None
    try:
        from analysis.memory.chronicle_writer import ChronicleWriter
        from config.settings import load_all_config
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
        from indicators.order_flow import fetch_latest_order_flow
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
        "atr_14_h4": atr,
        "nearest_fvg": nearest_fvg,
        "fvg_distance": fvg_distance,
        "nearest_ob": nearest_ob,
        "ob_distance": ob_distance,
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
        from graph.nodes.debate.helpers import inject_telemetry_reliability_into_fact_sheet
        fact_sheet = await inject_telemetry_reliability_into_fact_sheet(session, fact_sheet)
    except Exception as t_err:
        logger.debug(f"FactSheet telemetry injection error: {t_err}")

    return fact_sheet

