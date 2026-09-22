"""
Runtime Invariant Registry Framework.
Coordinates runtime checks, guarantees failure attribution, and enforces non-negotiable safety rules.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from .risk_gate_invariant import InvariantViolationError

logger = logging.getLogger("TradingAgent.RiskInvariants.Registry")


class InvariantStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


@dataclass
class InvariantResult:
    name: str
    status: InvariantStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    package_name: str = "risk.invariants"

    @property
    def passed(self) -> bool:
        return self.status == InvariantStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status == InvariantStatus.FAIL


class InvariantRegistry:
    """Registry coordinating non-negotiable quantitative and runtime invariants."""

    _instance: Optional["InvariantRegistry"] = None

    def __init__(self):
        self._invariants: Dict[str, Callable[[Dict[str, Any]], InvariantResult]] = {}

    @classmethod
    def get_instance(cls) -> "InvariantRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (primarily for testing)."""
        cls._instance = None

    def register(
        self,
        name: str,
        check_fn: Callable[[Dict[str, Any]], InvariantResult],
    ) -> None:
        """Register an invariant evaluation callable."""
        self._invariants[name] = check_fn
        logger.debug(f"[InvariantRegistry] Registered invariant: '{name}'")

    def unregister(self, name: str) -> None:
        """Remove a registered invariant."""
        self._invariants.pop(name, None)

    def list_invariants(self) -> List[str]:
        """Return list of registered invariant names."""
        return list(self._invariants.keys())

    def run_all(
        self,
        context: Dict[str, Any],
        fail_fast: bool = False,
    ) -> List[InvariantResult]:
        """
        Execute all registered invariants against provided runtime context.
        
        Args:
            context: Dictionary containing state to validate (e.g. proposal, positions, drawdown).
            fail_fast: If True, immediately raises InvariantViolationError on first failure.
        """
        results: List[InvariantResult] = []

        for name, fn in self._invariants.items():
            try:
                res = fn(context)
                results.append(res)
                if res.failed:
                    logger.warning(f"[InvariantRegistry] Invariant '{name}' FAILED: {res.message}")
                    if fail_fast:
                        raise InvariantViolationError(
                            f"Invariant failure in '{name}' [{res.package_name}]: {res.message}"
                        )
            except InvariantViolationError:
                raise
            except Exception as e:
                logger.error(f"[InvariantRegistry] Exception during '{name}' evaluation: {e}", exc_info=True)
                err_res = InvariantResult(
                    name=name,
                    status=InvariantStatus.FAIL,
                    message=f"Evaluation error: {str(e)}",
                    details={"exception": str(e)},
                )
                results.append(err_res)
                if fail_fast:
                    raise InvariantViolationError(f"Invariant '{name}' crashed: {e}") from e

        return results

    def assert_all(self, context: Dict[str, Any]) -> None:
        """Runs all invariants and raises InvariantViolationError if any fail."""
        results = self.run_all(context, fail_fast=False)
        failures = [r for r in results if r.failed]
        if failures:
            summary = "; ".join(f"[{f.name}]: {f.message}" for f in failures)
            raise InvariantViolationError(f"Runtime invariant assertion failed: {summary}")


def get_global_invariant_registry() -> InvariantRegistry:
    """Return the singleton InvariantRegistry instance."""
    return InvariantRegistry.get_instance()


def reset_global_invariant_registry() -> None:
    """Reset the singleton InvariantRegistry instance."""
    InvariantRegistry.reset_instance()
