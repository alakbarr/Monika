import logging
import math
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

class AdaptiveRiskPolicy:
    """
    Single source of truth for effective risk thresholds per symbol.
    Uses Wilson score intervals for statistical significance to adjust thresholds dynamically.
    """
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.base_min_confluence = settings.get('trading', {}).get('auto_execute_min_confluence', 7)
        self.max_score_inflation = settings.get('trading', {}).get('risk', {}).get('max_score_inflation', 2)

    async def get_effective_threshold(self, session: AsyncSession, symbol: str, as_of: Optional[datetime] = None) -> Tuple[int, str]:
        """
        Returns the effective min_confluence score required for a symbol and the reason.
        If the symbol has a statistically significant high win rate, we can lower the threshold.
        If the symbol has a low win rate, we increase the threshold.
        """
        from database.models import PaperTradeRecord
        from sqlalchemy import cast, Integer
        
        from utils.constants import MARKET_OUTCOME_EXIT_REASONS
        
        from datetime import timedelta
        import utils.clock as clock
        
        lookback_days = int(self.settings.get('trading', {}).get('risk', {}).get('adaptive_policy_lookback_days', 60))
        max_trades_cap = int(self.settings.get('trading', {}).get('risk', {}).get('adaptive_policy_max_trades', 100))
        
        ref_time = as_of or clock.now()
        since_time = ref_time - timedelta(days=lookback_days)
        
        # Subquery to bound sample to the most recent max_trades_cap trades within lookback_days
        subq = (
            select(PaperTradeRecord.id, PaperTradeRecord.pnl_pct)
            .where(PaperTradeRecord.symbol == symbol)
            .where(PaperTradeRecord.status == 'closed')
            .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
            .where(PaperTradeRecord.closed_at <= ref_time)
            .where(PaperTradeRecord.closed_at >= since_time)
            .order_by(PaperTradeRecord.closed_at.desc())
            .limit(max_trades_cap)
            .subquery()
        )
        
        stmt = select(
            func.count(subq.c.id).label('total_trades'),
            func.sum(cast(subq.c.pnl_pct > 0, Integer)).label('winning_trades')
        )
        result = (await session.execute(stmt)).first()
        
        n = (result.total_trades if result else 0) or 0
        wins = (result.winning_trades if result else 0) or 0
        
        # If we don't have enough data, use base threshold
        min_trades_required = self.settings.get('trading', {}).get('risk', {}).get('strategy_min_sample_size',
                                self.settings.get('trading', {}).get('min_paper_trades_before_live', 50))
        if n < min_trades_required:
            return self.base_min_confluence, f"Insufficient data ({n}/{min_trades_required}), using base threshold."
            
        # Wilson score interval (lower bound) for 90% confidence
        z = 1.645
        p = wins / n
        denominator = 1 + z**2/n
        centre_adjusted_prob = p + z**2 / (2*n)
        adjusted_standard_deviation = math.sqrt((p*(1 - p) + z**2 / (4*n)) / n)
        
        wilson_lower = (centre_adjusted_prob - z*adjusted_standard_deviation) / denominator
        
        target_win_rate = self.settings.get('trading', {}).get('min_paper_win_rate_pct', 45) / 100.0
        
        # Policy decisions
        if wilson_lower > target_win_rate + 0.1:
            # Strong statistical edge, we can afford to be slightly more aggressive
            effective_threshold = max(self.base_min_confluence - 1, 5)
            reason = f"Strong edge detected (Wilson lower {wilson_lower:.1%} > {target_win_rate+0.1:.1%}). Relaxing threshold to {effective_threshold}."
        elif wilson_lower < target_win_rate - 0.15:
            # Genuinely weak edge — tighten moderately
            effective_threshold = min(self.base_min_confluence + 1, 9)
            reason = f"Weak edge detected (Wilson lower {wilson_lower:.1%} < {target_win_rate-0.15:.1%}). Tightening threshold to {effective_threshold}."
        else:
            effective_threshold = self.base_min_confluence
            reason = f"Average edge (Wilson lower {wilson_lower:.1%}). Using base threshold {effective_threshold}."
            
        return effective_threshold, reason
