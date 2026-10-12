
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class MockPassStrategy(EdgeStrategy):
    strategy_id: str = "mock_pass"
    applicable_symbols: set = {"EURUSD"}
    compatible_regimes: set = {"TREND"}
    factor_family: str = "trend"

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.8,
            stop_loss=1.09,
            take_profit=1.12
        )
