# ==============================================================================
# File: logging_observability/dashboard/ws_ticket.py
# ==============================================================================

"""
Single-Use Ephemeral WebSocket Ticket Authentication Manager.
Institutional-grade dashboard observability and transport architecture.

Eliminates API key exposure in WebSocket query parameters and access logs.
Generates cryptographically random, short-lived (TTL 30s) single-use tickets
that are immediately invalidated upon initial WebSocket handshake.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.Dashboard.WsTicket")

DEFAULT_TICKET_TTL_SECONDS = 30.0


@dataclass
class TicketPayload:
    user_id: str
    role: str
    created_at: float
    expires_at: float


class WsTicketManager:
    """Manages ephemeral, single-use tickets for secure WebSocket handshakes."""

    def __init__(self, default_ttl: float = DEFAULT_TICKET_TTL_SECONDS):
        self.default_ttl = default_ttl
        self._tickets: Dict[str, TicketPayload] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        self._tickets = {t: p for t, p in self._tickets.items() if p.expires_at > now}

    def create_ticket(
        self,
        user_id: str = "operator",
        role: str = "admin",
        ttl_seconds: Optional[float] = None,
    ) -> str:
        """Issues a single-use ticket string."""
        self._purge_expired()
        ticket_id = secrets.token_urlsafe(32)
        ttl = ttl_seconds or self.default_ttl
        now = time.time()

        self._tickets[ticket_id] = TicketPayload(
            user_id=user_id,
            role=role,
            created_at=now,
            expires_at=now + ttl,
        )
        logger.debug(f"[WsTicketManager] Created single-use ticket for user '{user_id}' [{role}] (TTL {ttl}s)")
        return ticket_id

    def validate_and_consume(self, ticket_id: str) -> Optional[TicketPayload]:
        """
        Validates and immediately consumes the ticket.
        Returns TicketPayload if valid and unexpired, None otherwise.
        """
        self._purge_expired()
        if not ticket_id or ticket_id not in self._tickets:
            return None

        # Atomically pop to enforce single-use invariant
        payload = self._tickets.pop(ticket_id)
        if time.time() > payload.expires_at:
            return None

        logger.debug(f"[WsTicketManager] Consumed valid ticket for user '{payload.user_id}'")
        return payload

    def active_ticket_count(self) -> int:
        self._purge_expired()
        return len(self._tickets)


_GLOBAL_TICKET_MANAGER = WsTicketManager()


def get_ws_ticket_manager() -> WsTicketManager:
    return _GLOBAL_TICKET_MANAGER
