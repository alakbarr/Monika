"""
State Immutability Invariant Listener (Phase 5.6).
Verifies that graph state and context snapshots cannot be corrupted by in-place mutations.
"""

import hashlib
import json
import logging
from typing import Any, Dict
from .risk_gate_invariant import InvariantViolationError

logger = logging.getLogger("TradingAgent.StateInvariants")


def compute_state_digest(state: Dict[str, Any], protected_keys: tuple = ("symbol", "cycle_id", "macro_brief")) -> str:
    """Computes a deterministic hash of protected state keys."""
    sub_dict = {k: state.get(k) for k in protected_keys if k in state}
    try:
        raw = json.dumps(sub_dict, sort_keys=True, default=str)
    except Exception:
        raw = str(sorted(sub_dict.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class StateFreezeGuard:
    """Context manager capturing pre-node state hash and asserting immutability on exit."""

    def __init__(self, state: Dict[str, Any], protected_keys: tuple = ("symbol", "cycle_id", "macro_brief"), node_name: str = "node"):
        self.state = state
        self.protected_keys = protected_keys
        self.node_name = node_name
        self.initial_digest: str = ""

    def __enter__(self) -> "StateFreezeGuard":
        self.initial_digest = compute_state_digest(self.state, self.protected_keys)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            return  # Propagate original exception
        current_digest = compute_state_digest(self.state, self.protected_keys)
        if current_digest != self.initial_digest:
            raise InvariantViolationError(
                f"State immutability breach in '{self.node_name}': Protected keys {self.protected_keys} "
                f"were mutated in-place during node execution."
            )


def assert_state_immutability(initial_state: Dict[str, Any], current_state: Dict[str, Any], protected_keys: tuple = ("symbol", "cycle_id")) -> None:
    """Asserts that protected keys in current_state match initial_state."""
    d1 = compute_state_digest(initial_state, protected_keys)
    d2 = compute_state_digest(current_state, protected_keys)
    if d1 != d2:
        raise InvariantViolationError(
            f"State immutability breach: protected fields {protected_keys} differ between snapshots."
        )
