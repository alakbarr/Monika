"""
Abstract execution backend for MT5 operations.
Enables transparent switching between local Windows MT5 IPC and future remote server bridges.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MT5Backend(ABC):
    """Abstract interface for MT5 communication and order execution."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establishes connection to the MT5 terminal or remote execution bridge."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Closes connection to terminal."""
        pass

    @abstractmethod
    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves real-time bid, ask, spread, and timestamp for a symbol."""
        pass

    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves list of active open market positions."""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        magic: int = 123456,
    ) -> Dict[str, Any]:
        """Submits a market execution order."""
        pass

    @abstractmethod
    async def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        """Closes an open position by ticket."""
        pass

    @abstractmethod
    async def modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        """Modifies SL or TP of an active position."""
        pass
