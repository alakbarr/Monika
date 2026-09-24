# ==============================================================================
# File: cli/busy_input.py
# Description: Steer vs Follow-Up Input Buffer for Interactive TUI
# ==============================================================================

"""
Steer and Follow-Up Input Buffering Model for Interactive TUI.

Provides two distinct queues during active agent processing:
- STEER: injected at the next tool boundary mid-stream (e.g. adjust focus, filter symbol).
- FOLLOW_UP: queued until the agent reaches fully IDLE state.
- INTERRUPT: aborts current execution immediately.

Default steer delivery mode is 'one-at-a-time' for trading safety.
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Deque, List, Optional


class InputDelivery(str, Enum):
    STEER = "steer"
    FOLLOW_UP = "follow_up"
    INTERRUPT = "interrupt"


@dataclass
class BusyInputBuffer:
    """
    Manages dual input queues during agent analysis/execution cycles.

    Features:
    - Independent steer and follow-up FIFO queues.
    - Configurable delivery mode: 'one-at-a-time' (default) vs 'all'.
    - Dequeue support: returns pending messages back to editor without discarding.
    - Status formatting for TUI status bar.
    """

    steer_queue: Deque[str] = field(default_factory=deque)
    followup_queue: Deque[str] = field(default_factory=deque)
    default_mode: InputDelivery = InputDelivery.STEER
    delivery_mode: str = "one-at-a-time"  # 'one-at-a-time' (recommended for trading) or 'all'
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def submit(self, text: str, mode: Optional[InputDelivery] = None) -> None:
        """Submit text message into corresponding queue."""
        clean = text.strip()
        if not clean:
            return

        with self._lock:
            target_mode = mode or self.default_mode
            if target_mode == InputDelivery.STEER:
                self.steer_queue.append(clean)
            elif target_mode == InputDelivery.FOLLOW_UP:
                self.followup_queue.append(clean)
            elif target_mode == InputDelivery.INTERRUPT:
                # Immediate interruption signal
                self.steer_queue.appendleft(f"[INTERRUPT] {clean}")

    def pop_steer(self) -> Optional[str]:
        """Pop next steer message for mid-stream delivery at tool/stage boundary."""
        with self._lock:
            return self.steer_queue.popleft() if self.steer_queue else None

    def pop_all_steer(self) -> List[str]:
        """Pop all steer messages if batch delivery requested."""
        with self._lock:
            items = list(self.steer_queue)
            self.steer_queue.clear()
            return items

    def pop_followup(self) -> Optional[str]:
        """Pop next follow-up message for post-completion delivery."""
        with self._lock:
            return self.followup_queue.popleft() if self.followup_queue else None

    def pop_all_followup(self) -> List[str]:
        """Pop all follow-up messages."""
        with self._lock:
            items = list(self.followup_queue)
            self.followup_queue.clear()
            return items

    def dequeue_all(self) -> List[str]:
        """Restore all queued messages (steer + followup) in insertion order."""
        with self._lock:
            msgs = list(self.steer_queue) + list(self.followup_queue)
            self.steer_queue.clear()
            self.followup_queue.clear()
            return msgs

    def clear(self) -> None:
        """Clear both queues."""
        with self._lock:
            self.steer_queue.clear()
            self.followup_queue.clear()

    @property
    def pending_count(self) -> int:
        """Total number of queued messages."""
        with self._lock:
            return len(self.steer_queue) + len(self.followup_queue)

    @property
    def has_pending(self) -> bool:
        """Check if any message is pending."""
        return self.pending_count > 0

    @property
    def status_text(self) -> str:
        """Render human-readable queue status for status bar."""
        with self._lock:
            parts = []
            if self.steer_queue:
                parts.append(f"⟳{len(self.steer_queue)} steer")
            if self.followup_queue:
                parts.append(f"▷{len(self.followup_queue)} queued")
            return " │ ".join(parts) if parts else ""
