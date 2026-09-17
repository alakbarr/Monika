# ==============================================================================
# File: execution/service/base.py
# ==============================================================================

"""
Base typing infrastructure for modular execution service mixins.
Provides static attribute and cross-mixin method declarations during type-checking
without introducing any runtime overhead or metaclass conflicts.
"""

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    import asyncio
    from database.models import AssetAnalysis, Order, Position, OrderStatus
    from execution.mt5_client import MT5Client
    from execution.broker_adapter import BrokerAdapter
    from risk.position_sizing import PositionSizer, SizingResult
    from risk.risk_gate import RiskGate
    from execution.rate_throttler import RateThrottler
    from execution.verification_engine import EvidenceFirstVerifier
    from benchmark.trade_trajectory_logger import TradeTrajectoryLogger
    from execution.effect_gate import EffectGate


class _ExecutionServiceMixinBase:
    """
    Type-checking base class for ExecutionService mixins.
    Attributes and cross-mixin methods are only declared during static analysis.
    At runtime, this class is an empty lightweight base.
    """

    if TYPE_CHECKING:
        settings: Dict[str, Any]
        mt5: MT5Client
        mt5_client: MT5Client
        sizer: PositionSizer
        gate: RiskGate
        risk_gate: RiskGate
        dry_run: bool
        broker_adapter: BrokerAdapter
        evidence_verifier: EvidenceFirstVerifier
        trajectory_logger: TradeTrajectoryLogger
        rate_throttler: RateThrottler
        effect_gate: EffectGate
        _ticket_locks: Dict[int, Any]
        _kill_lock: Any

        # Cross-mixin methods provided by sibling mixins
        async def _count_open_positions(self, session: Any, symbol: Optional[str] = None) -> int: ...
        async def _get_dynamic_risk_percent(self, session: Any, symbol: str, base_risk_pct: float) -> float: ...
        async def _get_current_price(self, symbol: str, direction: str = "buy") -> Tuple[float, bool, float]: ...
        async def _get_equity(self) -> Optional[float]: ...
        async def _save_position(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _transition_order_state(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _handle_stop_loss_hit(self, *args: Any, **kwargs: Any) -> Any: ...
        async def _close_paper_position(self, *args: Any, **kwargs: Any) -> Any: ...
