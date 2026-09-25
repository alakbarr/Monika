from datetime import datetime
from typing import Optional, Dict, List, Tuple
import logging
from utils.market.dynamic_correlation import get_rolling_correlation

logger = logging.getLogger('TradingAgent.PortfolioCorrelationGate')

async def compute_portfolio_correlation_matrix(
    session,
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
    session,
    actionable_trades: list,
    threshold: float = 0.65,
    max_usd_exposure: int = 3,
    as_of: Optional[datetime] = None
) -> tuple[list, list]:
    """
    Menyaring proposal trade yang berkorelasi tinggi atau menumpuk risiko sistemik USD agregat.
    """
    if len(actionable_trades) <= 1:
        return (actionable_trades, [])
    
    sorted_trades = sorted(actionable_trades, key=lambda x: x[1].get('confidence') or 0.0, reverse=True)
    kept_trades = []
    rejected_trades = []
    net_usd_exposure = 0
    
    for sym, r in sorted_trades:
        direction = r.get('decision', 'wait').lower()
        if direction not in ('buy', 'sell'):
            continue
            
        usd_delta = _get_usd_directional_delta(sym, direction)
        
        # 1. Systemic Net USD Concentration Check
        if abs(net_usd_exposure + usd_delta) > max_usd_exposure:
            bias_str = "Long-USD" if (net_usd_exposure + usd_delta) > 0 else "Short-USD"
            reason = f"Systemic concentration cap: aggregate net {bias_str} positions would exceed {max_usd_exposure}."
            logger.info(f"Correlation Gate: Rejected {sym} {direction}. {reason}")
            rejected_trades.append((sym, r, reason))
            continue

        # 2. Pairwise Dynamic Correlation Check
        conflict_found = False
        conflict_reason = ''
        
        for kept_sym, kept_r in kept_trades:
            kept_direction = kept_r.get('decision', 'wait').lower()
            corr, source = await get_rolling_correlation(session, sym, kept_sym, as_of=as_of)
            
            import math
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
            
    return (kept_trades, rejected_trades)
