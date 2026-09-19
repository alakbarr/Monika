"""
Unit tests for MT5Backend abstraction interface.
"""

import pytest
from execution.backends.base import MT5Backend


def test_mt5_backend_abstract_instantiation_fails():
    with pytest.raises(TypeError):
        MT5Backend()


def test_mt5_backend_concrete_implementation():
    class DummyBackend(MT5Backend):
        async def connect(self) -> bool:
            return True
        async def disconnect(self) -> None:
            pass
        async def get_quote(self, symbol: str):
            return {"symbol": symbol, "bid": 1.0, "ask": 1.0002}
        async def get_positions(self, symbol=None):
            return []
        async def place_order(self, symbol, direction, volume, sl=None, tp=None, comment="", magic=123456):
            return {"status": "success", "ticket": 12345}
        async def close_position(self, ticket: int, volume=None) -> bool:
            return True
        async def modify_position(self, ticket: int, sl=None, tp=None) -> bool:
            return True

    backend = DummyBackend()
    assert backend is not None
