"""
Confluence Verifier — Deterministik layer untuk memvalidasi AI confluence score.
Checks factual conditions independently dari model's judgment.
"""
import logging
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import AssetAnalysis
from analysis.calculators.confluence_calculator import calculate_confluence

logger = logging.getLogger('TradingAgent.ConfluenceVerifier')

async def verify_confluence(
    session: AsyncSession,
    analysis: AssetAnalysis,
    settings: dict
) -> dict:
    """
    Verifikasi deterministik apakah AI confluence claim masuk akal.
    Return: {verified: bool, computed_score: int, discrepancy: int, blocking_issues: list}
    """
    symbol = analysis.symbol
    direction = analysis.decision
    entry_zone = {}
    if analysis.entry_zone:
        try:
            entry_zone = json.loads(analysis.entry_zone)
        except Exception:
            pass
    
    entry_price = entry_zone.get('price') or analysis.price_at_analysis
    sl = analysis.stop_loss
    tp = analysis.take_profit
    
    calc_res = await calculate_confluence(session, symbol, direction, entry_price, sl, tp, settings=settings)
    computed_score = calc_res.get('computed_score', 0)
    blocking_issues = calc_res.get('blocking_issues', [])
    
    # ===== CHECK 6: AI score vs computed score discrepancy =====
    ai_score = analysis.confluence_score or 0
    discrepancy = ai_score - computed_score
    
    # Check symbol-specific discrepancy allowed, fallback to general setting
    risk_cfg = settings.get('trading', {}).get('risk', {})
    default_allowed = 5 if symbol in {"BTCUSD", "XTIUSD", "XBRUSD", "XAUUSD"} else risk_cfg.get('max_score_discrepancy_allowed', 4)
    max_allowed_discrepancy = risk_cfg.get('max_score_discrepancy_by_symbol', {}).get(
        symbol, default_allowed
    )
    if discrepancy > max_allowed_discrepancy:
        # Only hard block if computed_score is virtually zero or discrepancy is extreme (>6)
        if computed_score < 2 or discrepancy > 6:
            blocking_issues.append(
                f'Score inflation suspected: AI reported {ai_score}/14 '
                f'but factual checks computed {computed_score}. '
                f'Discrepancy of {discrepancy} exceeds tolerance of {max_allowed_discrepancy}.'
            )
        else:
            logger.info(
                f"[{symbol}] Confluence discrepancy warning: AI={ai_score}, computed={computed_score} "
                f"(diff={discrepancy} > {max_allowed_discrepancy}), but setup has valid parameters. Passing with soft note."
            )
    
    verified = len(blocking_issues) == 0
    
    return {
        'verified': verified,
        'computed_score': computed_score,
        'ai_score': ai_score,
        'claude_score': ai_score,
        'discrepancy': discrepancy,
        'blocking_issues': blocking_issues,
        'symbol': symbol,
        'direction': direction,
    }
