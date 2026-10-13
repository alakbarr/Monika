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
    from monika.domain.entities.order_status import OrderStatus
    from monika.domain.entities.order import OrderEntity as Order
    from monika.domain.entities.position import PositionEntity as Position
    from monika.domain.risk.position_sizing import PositionSizer, SizingResult
    from monika.domain.risk.risk_gate import RiskGate
    from monika.domain.execution.verification_engine import EvidenceFirstVerifier
    from monika.application.benchmark.trade_trajectory_logger import TradeTrajectoryLogger
    from monika.application.execution.effect_gate import EffectGate

    AssetAnalysis = Any
    MT5Client = Any
    BrokerAdapter = Any
    RateThrottler = Any


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


__all__ = ["_ExecutionServiceMixinBase"]
