from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import logging
import math
from sqlalchemy.ext.asyncio import AsyncSession
from monika.domain.market.dynamic_correlation import get_rolling_correlation, _static_fallback

logger = logging.getLogger('TradingAgent.PortfolioCorrelationGate')

async def compute_portfolio_correlation_matrix(
    session: AsyncSession,
    symbols: List[str],
    as_of: Optional[datetime] = None
) -> Dict[str, Dict[str, float]]:
    """Menghitung matriks korelasi penuh N x N antar instrumen portofolio aktif."""
    matrix: Dict[str, Dict[str, float]] = {s: {} for s in symbols}
    for i, s1 in enumerate(symbols):
        matrix[s1][s1] = 1.0
        for s2 in symbols[i + 1:]:
            corr, _ = await get_rolling_correlation(session, s1, s2, as_of=as_of)
            matrix[s1][s2] = round(corr, 4)
            matrix[s2][s1] = round(corr, 4)
    return matrix


GROUP_POSITION_LIMITS: Dict[str, int] = {
    "USD_MAJORS": 3,
    "METALS": 2,
    "ENERGY": 1,
    "CRYPTO": 1,
}


def _get_usd_directional_delta(symbol: str, direction: str) -> int:
    """
    Menghitung arah eksposur USD:
    +1 = Long USD (misal Buy USDJPY, Sell EURUSD, Sell GBPUSD, Sell XAUUSD)
    -1 = Short USD (misal Sell USDJPY, Buy EURUSD, Buy GBPUSD, Buy XAUUSD)
     0 = Non-USD or Neutral
    """
    sym = symbol.upper()
    dir_lower = direction.lower()
    if dir_lower not in ("buy", "sell"):
        return 0

    if sym.startswith("USD"):
        return 1 if dir_lower == "buy" else -1
    elif sym.endswith("USD"):
        return -1 if dir_lower == "buy" else 1
    return 0


async def filter_correlated_proposals(
    session: Optional[AsyncSession],
    actionable_trades: list,
    threshold: float = 0.65,
    max_usd_exposure: int = 3,
    as_of: Optional[datetime] = None
) -> tuple[list, list]:
    """
    Menyaring proposal trade yang berkorelasi tinggi atau menumpuk risiko sistemik USD agregat,
    dengan memperhitungkan posisi terbuka yang sudah ada di database.
    """
    if not actionable_trades:
        return ([], [])
    
    # 0. Query existing open positions to enforce true portfolio risk
    open_positions: List[Any] = []
    if session is not None:
        try:
            from monika.domain.risk.ports import get_default_risk_data_provider
            repo = get_default_risk_data_provider(session=session)
            if repo is not None:
                open_positions = await repo.get_open_positions(is_paper=False, session=session)
        except Exception as e:
            logger.warning(f"Correlation Gate: Failed to query open positions from repository: {e}")

    # Calculate starting net USD exposure and sector counts from existing open positions
    from monika.domain.risk.portfolio_optimizer import DEFAULT_GROUP_MAP
    GROUP_POSITION_LIMITS = {
        "USD_MAJORS": 3,
        "METALS": 2,
        "ENERGY": 1,
        "CRYPTO": 1,
        "OTHER": 2,
    }

    net_usd_exposure = 0
    group_counts: Dict[str, int] = {k: 0 for k in GROUP_POSITION_LIMITS}
    for pos in open_positions:
        p_dir = str(getattr(pos, "direction", None) or (pos.get("direction") if isinstance(pos, dict) else "") or "").lower()
        p_sym = str(getattr(pos, "symbol", None) or (pos.get("symbol") if isinstance(pos, dict) else "") or "")
        net_usd_exposure += _get_usd_directional_delta(p_sym, p_dir)
        grp = DEFAULT_GROUP_MAP.get(p_sym.upper(), "OTHER")
        group_counts[grp] = group_counts.get(grp, 0) + 1

    sorted_trades = sorted(actionable_trades, key=lambda x: x[1].get('confidence') or 0.0, reverse=True)
    kept_trades = []
    rejected_trades = []
    
    for sym, r in sorted_trades:
        direction = r.get('decision', 'wait').lower()
        if direction not in ('buy', 'sell'):
            continue
            
        usd_delta = _get_usd_directional_delta(sym, direction)
        grp = DEFAULT_GROUP_MAP.get(sym.upper(), "OTHER")
        max_grp_limit = GROUP_POSITION_LIMITS.get(grp, 2)
        
        # 1. Systemic Net USD Concentration Check (including open positions)
        if abs(net_usd_exposure + usd_delta) > max_usd_exposure:
            bias_str = "Long-USD" if (net_usd_exposure + usd_delta) > 0 else "Short-USD"
            reason = f"Systemic concentration cap: aggregate net {bias_str} positions would exceed {max_usd_exposure}."
            logger.info(f"Correlation Gate: Rejected {sym} {direction}. {reason}")
            rejected_trades.append((sym, r, reason))
            continue

        # 2. Sector Concentration Check
        if group_counts.get(grp, 0) + 1 > max_grp_limit:
            reason = f"Sector concentration cap: {grp} positions ({group_counts.get(grp, 0) + 1}) would exceed limit of {max_grp_limit}."
            logger.info(f"Correlation Gate: Rejected {sym} {direction}. {reason}")
            rejected_trades.append((sym, r, reason))
            continue

        # 2. Pairwise Dynamic Correlation Check against existing open positions
        conflict_found = False
        conflict_reason = ''
        
        for pos in open_positions:
            pos_sym = str(getattr(pos, "symbol", None) or (pos.get("symbol") if isinstance(pos, dict) else "") or "")
            pos_dir = str(getattr(pos, "direction", None) or (pos.get("direction") if isinstance(pos, dict) else "") or "").lower()
            if pos_sym.upper() == sym.upper():
                continue
            if session is not None:
                corr, source = await get_rolling_correlation(session, sym, pos_sym, as_of=as_of)
            else:
                corr, source = _static_fallback(sym, pos_sym), "static_fallback"
            if corr is None or (isinstance(corr, float) and math.isnan(corr)):
                corr = 0.0
                source = "neutral_fallback"
            same_dir = (direction == pos_dir)
            effective_corr = corr if same_dir else -corr
            if effective_corr >= threshold:
                conflict_found = True
                conflict_reason = f"Correlated with open position {pos_sym} (effective_corr={effective_corr:.2f}, raw={corr:.2f} [{source}])"
                break

        if conflict_found:
            logger.info(f"Correlation Gate: Rejected {sym} {direction}. {conflict_reason}")
            rejected_trades.append((sym, r, conflict_reason))
            continue

        # 3. Pairwise Dynamic Correlation Check against kept candidates in current batch
        conflict_found = False
        conflict_reason = ''
        
        for kept_sym, kept_r in kept_trades:
            kept_direction = kept_r.get('decision', 'wait').lower()
            if session is not None:
                corr, source = await get_rolling_correlation(session, sym, kept_sym, as_of=as_of)
            else:
                corr, source = _static_fallback(sym, kept_sym), "static_fallback"
            
            if corr is None or (isinstance(corr, float) and math.isnan(corr)):
                logger.info(f"Correlation Gate: Correlation data unavailable for {sym}-{kept_sym}. Defaulting to neutral 0.0 fallback.")
                corr = 0.0
                source = "neutral_fallback"
                
            same_dir = (direction == kept_direction)
            effective_corr = corr if same_dir else -corr
            if effective_corr >= threshold:
                conflict_found = True
                rel_desc = f"both {direction}" if same_dir else f"{direction} vs {kept_direction} with negative correlation"
                conflict_reason = f'Correlated with {kept_sym} (effective_corr={effective_corr:.2f}, raw={corr:.2f} [{source}], {rel_desc})'
                break
                
        if conflict_found:
            logger.info(f'Correlation Gate: Rejected {sym} {direction}. {conflict_reason}')
            rejected_trades.append((sym, r, conflict_reason))
        else:
            kept_trades.append((sym, r))
            net_usd_exposure += usd_delta
            group_counts[grp] = group_counts.get(grp, 0) + 1
            
    return (kept_trades, rejected_trades)
