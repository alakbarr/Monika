"""
Position Count Invariant.
Asserts that open position count does not breach maximum account limits.
"""

from typing import Any, Dict, List, Optional

from .registry import (
    InvariantRegistry,
    InvariantResult,
    InvariantStatus,
    InvariantViolationError,
)


def assert_position_count_invariant(
    open_positions: list[Any],
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


def check_position_count_invariant(context: dict[str, Any]) -> InvariantResult:
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

    # If currently evaluating a new trade proposal and already at maximum limit, fail
    if count == max_positions:
        if "proposal" in context or context.get("is_new_trade"):
            return InvariantResult(
                name="position_count",
                status=InvariantStatus.FAIL,
                message=f"Open positions ({count}) have reached maximum capacity ({max_positions}). New trade prohibited.",
                details={"current_count": count, "max_limit": max_positions},
                package_name="risk.invariants.position_count",
            )
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


InvariantRegistry.register_default_provider(
    lambda reg: reg.register("position_count_ceiling", check_position_count_invariant)
)
