"""
Position Count Invariant.
Asserts that open position count does not breach maximum account limits.
"""

from typing import Any, Dict, List, Optional
from .risk_gate_invariant import InvariantViolationError
from .registry import InvariantResult, InvariantStatus


def assert_position_count_invariant(
    open_positions: List[Any],
    max_concurrent_positions: int = 5,
) -> None:
    """
    Asserts that the number of open positions is strictly within allowed ceiling.
    Raises InvariantViolationError on breach.
    """
    count = len(open_positions)
    if count > max_concurrent_positions:
        raise InvariantViolationError(
            f"Position count breach: {count} open positions exceed maximum limit of {max_concurrent_positions}."
        )


def check_position_count_invariant(context: Dict[str, Any]) -> InvariantResult:
    """
    InvariantRegistry adapter checking position count.
    Expects 'open_positions' (list) and optional 'max_concurrent_positions' (int, default 5) in context.
    """
    open_positions = context.get("open_positions", [])
    max_positions = int(context.get("max_concurrent_positions", 5))

    count = len(open_positions)
    if count > max_positions:
        return InvariantResult(
            name="position_count",
            status=InvariantStatus.FAIL,
            message=f"Open positions ({count}) exceed allowed limit ({max_positions}).",
            details={"current_count": count, "max_limit": max_positions},
            package_name="risk.invariants.position_count",
        )

    # Optional warning if at maximum limit
    if count == max_positions:
        return InvariantResult(
            name="position_count",
            status=InvariantStatus.WARN,
            message=f"Open positions ({count}) is at maximum capacity ({max_positions}).",
            details={"current_count": count, "max_limit": max_positions},
            package_name="risk.invariants.position_count",
        )

    return InvariantResult(
        name="position_count",
        status=InvariantStatus.PASS,
        message=f"Position count valid ({count}/{max_positions}).",
        details={"current_count": count, "max_limit": max_positions},
        package_name="risk.invariants.position_count",
    )
