# ==============================================================================
# File: tests/scrapers/test_http_client_factory.py
# ==============================================================================

import asyncio
import aiohttp
import pytest

from monika.infrastructure.network.http_client_factory import HttpClientFactory


@pytest.mark.asyncio
async def test_http_client_factory_singleton_and_pool():
    factory = HttpClientFactory.get_instance()
    session_1 = await factory.get_session()
    assert isinstance(session_1, aiohttp.ClientSession)
    assert not session_1.closed

    # Second call returns the exact same pooled session
    session_2 = await factory.get_session()
    assert session_2 is session_1

    # Graceful shutdown closes all connections
    await factory.close_all()
    assert session_1.closed

    # Next call cleanly creates a fresh active pooled session
    session_3 = await factory.get_session()
    assert isinstance(session_3, aiohttp.ClientSession)
    assert not session_3.closed
    assert session_3 is not session_1

    await factory.close_all()
