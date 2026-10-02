import os
os.environ.setdefault("PTB_TIMEDELTA", "1")
import asyncio
import sys
import warnings
import pytest
import pytest_asyncio

try:
    import asyncpg.connection

    def _safe_clean_tasks(self):
        if hasattr(self, "_cancellations") and self._cancellations:
            for fut in list(self._cancellations):
                if not fut.done():
                    fut.cancel()
                    coro = getattr(fut, "get_coro", lambda: None)()
                    if coro is not None:
                        try:
                            coro.close()
                        except Exception:
                            pass
            self._cancellations.clear()

    asyncpg.connection.Connection._clean_tasks = _safe_clean_tasks

    _orig_conn_del = getattr(asyncpg.connection.Connection, "__del__", None)
    def _safe_conn_del(self):
        try:
            _safe_clean_tasks(self)
        except Exception:
            pass
        if _orig_conn_del:
            try:
                _orig_conn_del(self)
            except Exception:
                pass
    asyncpg.connection.Connection.__del__ = _safe_conn_del

    _orig_cancel_cmd = getattr(asyncpg.connection.Connection, "_cancel_current_command", None)
    if _orig_cancel_cmd is not None:
        def _safe_cancel_current_command(self, waiter):
            if hasattr(self, "_loop") and (self._loop.is_closed() or not self._loop.is_running()):
                coro = self._cancel(waiter)
                if coro:
                    try:
                        coro.close()
                    except Exception:
                        pass
                return
            return _orig_cancel_cmd(self, waiter)
        asyncpg.connection.Connection._cancel_current_command = _safe_cancel_current_command
except Exception:
    pass


@pytest.hookimpl
def pytest_asyncio_loop_factories(config, item):
    """Customize pytest-asyncio event loop factory on Windows to use SelectorEventLoop except for MCP/subprocess."""
    if sys.platform == "win32":
        if "mcp" in item.nodeid or "subprocess" in item.nodeid or "terminal" in item.nodeid:
            return {"default": asyncio.ProactorEventLoop}
        return {"default": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}


@pytest.fixture(autouse=True)
def protect_live_db_from_test_activity_logs(monkeypatch):
    """
    Mencegah seluruh unit test memanggil database live untuk ActivityLog saat session=None.
    Jika test membutuhkan pengujian save ActivityLog, test tersebut harus menyediakan db_session / mock_session.
    """
    try:
        from analysis.harness.agent_harness import AgentHarness
        orig_log = AgentHarness._log_tool_call

        async def guarded_log(self, session, *args, **kwargs):
            if session is None:
                return None
            return await orig_log(self, session, *args, **kwargs)

        monkeypatch.setattr(AgentHarness, "_log_tool_call", guarded_log)
    except Exception:
        pass

    try:
        from unittest.mock import Mock
        import database.db
        from analysis.providers.base_provider import BaseLLMClient
        orig_llm_log = BaseLLMClient._log_tool_call

        async def guarded_llm_log(self, session, *args, **kwargs):
            if not isinstance(database.db.get_session, Mock):
                return None
            return await orig_llm_log(self, session, *args, **kwargs)

        monkeypatch.setattr(BaseLLMClient, "_log_tool_call", guarded_llm_log)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def protect_live_db_from_test_token_logs(monkeypatch):
    """
    Mencegah seluruh unit test menulis record token_usage_log ke database live.
    Jika test membutuhkan pengujian save_token_usage, test tersebut harus menyediakan mock_session.
    """
    try:
        from analysis.providers.base_provider import BaseLLMClient
        orig_save = BaseLLMClient._save_token_usage

        async def guarded_save(self, *args, **kwargs):
            if "session" not in kwargs or kwargs.get("session") is None:
                return None
            return await orig_save(self, *args, **kwargs)

        monkeypatch.setattr(BaseLLMClient, "_save_token_usage", guarded_save)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def protect_live_telegram_in_tests(monkeypatch, request):
    """
    Mencegah seluruh unit test memicu socket / HTTP request / transport leak ke live Telegram API.
    Kecuali test_bot.py yang secara eksplisit menguji TelegramBot integration/mocking.
    """
    if "test_bot.py" in request.node.nodeid or "test_notifier.py" in request.node.nodeid:
        return
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "")


@pytest.fixture(autouse=True)
def protect_llm_provider_network_and_pools(monkeypatch):
    """
    Mencegah provider LLM (OpenRouter, OpenAI, dll.) menginstansiasi AsyncOpenAI transport nyata
    dan membersihkan client pool antar pengujian untuk mencegah kebocoran socket / transport unclosed.
    """
    try:
        from analysis.providers.openrouter_provider import OpenRouterProvider
        OpenRouterProvider._client_pool.clear()
    except Exception:
        pass

    try:
        from unittest.mock import MagicMock, AsyncMock
        def make_mock_async_openai(*args, **kwargs):
            mock_inst = MagicMock()
            mock_inst.base_url = kwargs.get("base_url", "https://api.openai.com/v1")
            mock_inst.default_headers = kwargs.get("default_headers", {})
            mock_inst.chat.completions.create = AsyncMock()
            mock_inst.close = AsyncMock()
            return mock_inst

        monkeypatch.setattr("openai.AsyncOpenAI", MagicMock(side_effect=make_mock_async_openai))
    except Exception:
        pass

    yield

    try:
        from analysis.providers.openrouter_provider import OpenRouterProvider
        OpenRouterProvider._client_pool.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def drain_orphan_async_tasks():
    """Drain any lingering background async tasks before event loop teardown."""
    yield
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        if not loop.is_closed() and not loop.is_running():
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            if pending:
                for t in pending:
                    t.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except (RuntimeError, Exception):
        pass


@pytest.fixture(autouse=True)
def allow_tradingagent_log_propagation():
    """Memastikan log dari hierarki logger TradingAgent merambat ke root logger untuk caplog pytest."""
    import logging
    ta_logger = logging.getLogger("TradingAgent")
    prev_propagate = ta_logger.propagate
    prev_level = ta_logger.level
    ta_logger.propagate = True
    ta_logger.setLevel(logging.DEBUG)
    yield
    ta_logger.propagate = prev_propagate
    ta_logger.setLevel(prev_level)



import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    """Async database session fixture using in-memory SQLite."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from database.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

    await engine.dispose()


from unittest.mock import AsyncMock, MagicMock


def create_mock_async_session():
    """Create a fully compliant AsyncSession mock that avoids unawaited coroutine warnings for sync methods."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()
    mock_session.delete = MagicMock()
    mock_session.expunge = MagicMock()
    mock_session.refresh = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.close = AsyncMock()
    
    mock_nested = AsyncMock()
    mock_nested.__aenter__.return_value = mock_nested
    mock_nested.__aexit__.return_value = None
    mock_session.begin_nested = MagicMock(return_value=mock_nested)
    
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.get_bind = MagicMock(return_value=mock_bind)
    mock_session.bind = mock_bind

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.all.return_value = []
    mock_res.scalars.return_value.first.return_value = None
    mock_res.scalars.return_value.one_or_none.return_value = None
    mock_res.scalar.return_value = None
    mock_res.all.return_value = []
    mock_res.first.return_value = None
    mock_res.mappings.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.scalar = AsyncMock(return_value=None)
    mock_session.scalars = AsyncMock(return_value=mock_res.scalars.return_value)
    mock_session.get = AsyncMock(return_value=None)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


@pytest.fixture
def mock_async_session():
    return create_mock_async_session()


@pytest.fixture(autouse=True)
def protect_live_database_in_tests(monkeypatch, request):
    """
    Mencegah seluruh unit test memicu koneksi socket asyncpg ke live PostgreSQL port 5432
    kecuali jika pengujian secara eksplisit meminta fixture `db_session`.
    """
    if "db_session" in request.fixturenames:
        return

    try:
        import database.db

        def make_mock_session(*args, **kwargs):
            return create_mock_async_session()

        def safe_get_sessionmaker():
            sm = getattr(database.db, "AsyncSessionLocal", None)
            if sm is not None and not isinstance(sm, database.db._AsyncSessionLocalProxy):
                return sm
            return make_mock_session

        monkeypatch.setattr(database.db, "get_sessionmaker", safe_get_sessionmaker)
    except Exception:
        pass


