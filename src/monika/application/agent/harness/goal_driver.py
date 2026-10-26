"""Goal driver service managing goal lifecycle and grounded wrap-up prompts.

Provides:
- Optimistic concurrency control via revision-checked GoalRef.
- Circuit breaker rejecting premature goal blocked transitions before minimum round threshold.
- Grounded completion and blocked wrap-up prompt builders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GoalStatus = Literal["pending", "active", "completed", "blocked", "abandoned"]


@dataclass(frozen=True, slots=True)
class GoalRef:
    """Optimistic concurrency token for goal state transitions."""

    id: str
    revision: int


@dataclass(frozen=True, slots=True)
class GoalSnapshot:
    """Immutable state snapshot for a tracked goal."""

    id: str
    revision: int
    status: GoalStatus
    description: str
    consecutive_rounds: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class GoalStateService:
    """State service governing goal lifecycle with optimistic concurrency and premature block protection."""

    def __init__(self, blocked_after_consecutive_rounds: int = 3) -> None:
        self.blocked_after_consecutive_rounds = blocked_after_consecutive_rounds
        self._goals: dict[str, GoalSnapshot] = {}

    def create_goal(
        self,
        goal_id: str,
        description: str,
        status: GoalStatus = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> GoalSnapshot:
        if goal_id in self._goals:
            raise ValueError(f"Goal '{goal_id}' already exists.")

        snapshot = GoalSnapshot(
            id=goal_id,
            revision=1,
            status=status,
            description=description,
            consecutive_rounds=0,
            metadata=dict(metadata) if metadata is not None else {},
        )
        self._goals[goal_id] = snapshot
        return snapshot

    def get_goal(self, goal_id: str) -> GoalSnapshot | None:
        return self._goals.get(goal_id)

    def update_goal(
        self,
        ref: GoalRef,
        action: str = "noop",
        new_status: GoalStatus | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GoalSnapshot:
        current = self._goals.get(ref.id)
        if current is None:
            raise ValueError(f"Goal '{ref.id}' does not exist.")

        if current.revision != ref.revision:
            raise ValueError(
                f"Revision mismatch for goal '{ref.id}': expected {ref.revision}, found {current.revision}."
            )

        updated_rounds = current.consecutive_rounds
        if action == "increment_round":
            updated_rounds += 1
        elif action == "reset_round":
            updated_rounds = 0

        target_status = new_status if new_status is not None else current.status
        if target_status == "blocked" and updated_rounds < self.blocked_after_consecutive_rounds:
            raise ValueError(
                f"Cannot transition goal '{ref.id}' to 'blocked' before {self.blocked_after_consecutive_rounds} "
                f"consecutive rounds of attempts (current: {updated_rounds})."
            )

        merged_meta = dict(current.metadata)
        if reason is not None:
            merged_meta["last_reason"] = reason
        if metadata is not None:
            merged_meta.update(metadata)

        updated_snapshot = GoalSnapshot(
            id=ref.id,
            revision=ref.revision + 1,
            status=target_status,
            description=current.description,
            consecutive_rounds=updated_rounds,
            metadata=merged_meta,
        )
        self._goals[ref.id] = updated_snapshot
        return updated_snapshot

    def build_goal_complete_prompt(self, goal: GoalSnapshot, evidence_summary: str) -> str:
        """Build grounded wrap-up prompt for completed goal."""
        return (
            f"<goal_complete>\n"
            f"<id>{goal.id}</id>\n"
            f"<description>{goal.description}</description>\n"
            f"<evidence>\n{evidence_summary.strip()}\n</evidence>\n"
            f"</goal_complete>"
        )

    def build_goal_blocked_prompt(self, goal: GoalSnapshot, block_reason: str) -> str:
        """Build grounded wrap-up prompt for blocked goal."""
        return (
            f"<goal_blocked>\n"
            f"<id>{goal.id}</id>\n"
            f"<description>{goal.description}</description>\n"
            f"<reason>\n{block_reason.strip()}\n</reason>\n"
            f"<rounds>{goal.consecutive_rounds}</rounds>\n"
            f"</goal_blocked>"
        )
