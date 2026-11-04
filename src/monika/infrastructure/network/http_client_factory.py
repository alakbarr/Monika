# ==============================================================================
# File: infrastructure/network/http_client_factory.py
# Monika Unified Connection-Pooled HTTP Client Factory
# ==============================================================================

"""
High-Performance, Connection-Pooled Asynchronous HTTP Client Factory.

Prevents socket leaks, TLS handshake thrashing, and descriptor exhaustion
by managing long-lived pooled aiohttp.ClientSession instances with:
- DNS resolution caching (300s TTL).
- Keep-Alive connection pooling with configurable limits.
- Automatic recycling on event loop renewal.
- Clean graceful shutdown hooks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger("TradingAgent.Infrastructure.Network")


class HttpClientFactory:
    """
    Singleton connection-pooled aiohttp session factory.
    """

    _instance: Optional[HttpClientFactory] = None
    _lock = asyncio.Lock()

    def __init__(
        self,
        total_limit: int = 100,
        per_host_limit: int = 10,
        dns_cache_ttl: int = 300,
        keepalive_timeout: float = 60.0,
    ):
        self._total_limit = total_limit
        self._per_host_limit = per_host_limit
        self._dns_cache_ttl = dns_cache_ttl
        self._keepalive_timeout = keepalive_timeout

        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    def get_instance(cls) -> HttpClientFactory:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    async def get_session(self) -> aiohttp.ClientSession:
        """
        Retrieves or initializes the active pooled aiohttp ClientSession.
        Ensures the session matches the currently running event loop.
        """
        current_loop = asyncio.get_running_loop()

        if self._session is not None and not self._session.closed and self._loop == current_loop:
            return self._session

        # Needs creation or recreation
        if self._session is not None and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass

        self._loop = current_loop
        self._connector = aiohttp.TCPConnector(
            limit=self._total_limit,
            limit_per_host=self._per_host_limit,
            ttl_dns_cache=self._dns_cache_ttl,
            keepalive_timeout=self._keepalive_timeout,
        )
        default_timeout = aiohttp.ClientTimeout(total=30.0, connect=10.0)
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            timeout=default_timeout,
        )
        logger.debug(
            f"[HttpClientFactory] Initialized shared connection pool (limit={self._total_limit}, "
            f"per_host={self._per_host_limit}, dns_ttl={self._dns_cache_ttl}s)"
        )
        return self._session

    async def close_all(self) -> None:
        """Gracefully closes all open connections and underlying pooled connector."""
        if self._session is not None and not self._session.closed:
            logger.debug("[HttpClientFactory] Closing shared HTTP connection pool...")
            await self._session.close()
            self._session = None
        if self._connector is not None and not self._connector.closed:
            await self._connector.close()
            self._connector = None
        self._loop = None


__all__ = [
    "HttpClientFactory",
]
