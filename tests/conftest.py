import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
_src_dir = _repo_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import monika
import monika.infrastructure.database.models
from monika.domain.risk.ports import (
    register_evidence_store_factory,
    register_notifier,
    register_session_factory,
    register_event_publisher,
)
from monika.application.analysis.strategies.evidence_store import EvidenceStore
from monika.infrastructure.notifications.telegram_notifier import AgentNotifier
from monika.infrastructure.database.event_store import TradingEventStore
from monika.infrastructure.database.db import get_session

register_evidence_store_factory(lambda: EvidenceStore())


def _test_notifier_factory():
    from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

    return AgentNotifier()


register_notifier(_test_notifier_factory)
register_event_publisher(TradingEventStore)
register_session_factory(get_session)

from monika.domain.risk.ports import register_data_freshness_validator, register_suspended_symbols_provider
from monika.core.validation.data_validator import validate_data_freshness
from monika.core.analytics.paper_tracker import PaperTracker

register_data_freshness_validator(validate_data_freshness)
register_suspended_symbols_provider(lambda settings=None: PaperTracker(settings))

import os

import tempfile

os.environ.setdefault("PTB_TIMEDELTA", "1")
_cache_dir = os.path.join(tempfile.gettempdir(), "monika_test_cache", "matplotlib")
os.makedirs(_cache_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _cache_dir)

import _thread
import threading
import faulthandler
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
            if callable(_orig_cancel_cmd):
                _orig_cancel_cmd(self, waiter)

        setattr(asyncpg.connection.Connection, "_cancel_current_command", _safe_cancel_current_command)
except Exception:
    pass


# (pytest-asyncio loop factory handled by pytest-asyncio default configuration)

if sys.platform == "win32":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_pipe_del = getattr(_ProactorBasePipeTransport, "__del__", None)
        if _orig_pipe_del is not None:

            def _safe_pipe_del(self):
                if callable(_orig_pipe_del):
                    try:
                        _orig_pipe_del(self)
                    except ValueError, OSError:
                        pass

            _ProactorBasePipeTransport.__del__ = _safe_pipe_del
    except Exception:
        pass


@pytest.fixture(autouse=True)
def test_timeout_watchdog(request):
    """Ensure no test hangs indefinitely; interrupts after 30s with full thread traceback."""
    interrupted = threading.Event()
    test_node = request.node.nodeid

    def on_timeout():
        interrupted.set()
        sys.stderr.write(f"\n[WATCHDOG TIMEOUT] Test exceeded 30s limit: {test_node}\n")
        try:
            faulthandler.dump_traceback(file=sys.stderr)
        except Exception:
            pass
        _thread.interrupt_main()

    timeout_secs = 60.0 if os.environ.get("CI") else 30.0
    timer = threading.Timer(timeout_secs, on_timeout)
    timer.daemon = True
    timer.start()
    try:
        yield
    except KeyboardInterrupt:
        if interrupted.is_set():
            pytest.fail(f"Test exceeded 30s execution limit (stuck/hanging detected): {test_node}")
        raise
    finally:
        timer.cancel()


@pytest.fixture(autouse=True)
def isolate_risk_port_registry():
    """Preserve and restore RiskPortRegistry baseline state to prevent cross-test pollution."""
    from monika.domain.risk.ports import RiskPortRegistry

    snapshot = {k: getattr(RiskPortRegistry, k) for k in dir(RiskPortRegistry) if not k.startswith("_")}
    yield
    for k, v in snapshot.items():
        setattr(RiskPortRegistry, k, v)


@pytest.fixture(autouse=True)
def isolate_llm_circuit_breakers():
    """Ensure in-memory circuit breakers and model blacklists do not leak across tests."""
    try:
        from monika.infrastructure.providers.llm_factory import EndpointBlackhole, ProviderCircuitBreaker

        ProviderCircuitBreaker.reset()
        EndpointBlackhole.reset()
    except Exception:
        pass
    yield
    try:
        from monika.infrastructure.providers.llm_factory import EndpointBlackhole, ProviderCircuitBreaker

        ProviderCircuitBreaker.reset()
        EndpointBlackhole.reset()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def protect_live_db_from_test_activity_logs(monkeypatch):
    """
    Mencegah seluruh unit test memanggil database live untuk ActivityLog saat session=None.
    Jika test membutuhkan pengujian save ActivityLog, test tersebut harus menyediakan db_session / mock_session.
    """
    try:
        from monika.application.agent.harness.agent_harness import AgentHarness

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
        import monika.infrastructure.database.db as database_db
        from monika.infrastructure.providers.base_provider import BaseLLMClient

        orig_llm_log = BaseLLMClient._log_tool_call

        async def guarded_llm_log(self, session, *args, **kwargs):
            if not isinstance(database_db.get_session, Mock):
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
        from monika.infrastructure.providers.base_provider import BaseLLMClient

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

    from monika.domain.risk.ports import register_notifier

    def _isolated_notifier_factory():
        from monika.infrastructure.notifications.telegram_notifier import AgentNotifier

        return AgentNotifier()

    register_notifier(_isolated_notifier_factory)


@pytest.fixture(autouse=True)
def protect_llm_provider_network_and_pools(monkeypatch):
    """
    Mencegah provider LLM (OpenRouter, OpenAI, dll.) menginstansiasi AsyncOpenAI transport nyata
    dan membersihkan client pool antar pengujian untuk mencegah kebocoran socket / transport unclosed.
    """
    try:
        from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

        OpenRouterProvider._client_pool.clear()
    except Exception:
        pass

    try:
        from monika.infrastructure.providers.llm_factory import FallbackClientWrapper

        FallbackClientWrapper._shared_role_slot_cooldowns.clear()
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
        from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

        OpenRouterProvider._client_pool.clear()
    except Exception:
        pass

    try:
        from monika.infrastructure.providers.llm_factory import FallbackClientWrapper

        FallbackClientWrapper._shared_role_slot_cooldowns.clear()
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
    except RuntimeError, Exception:
        pass


@pytest.fixture(autouse=True)
def isolate_environment_mutations():
    """Protect process environment from direct in-place mutations during tests."""
    orig_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(orig_env)


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
    from monika.infrastructure.database.models import Base

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
    if "db_session" in request.fixturenames or "setup_sqlite_concurrency_db" in request.fixturenames:
        return

    try:
        import monika.infrastructure.database.db as database_db

        def make_mock_session(*args, **kwargs):
            return create_mock_async_session()

        def safe_get_sessionmaker():
            sm = getattr(database_db, "AsyncSessionLocal", None)
            if sm is not None and not isinstance(sm, database_db._AsyncSessionLocalProxy):
                return sm
            return make_mock_session

        monkeypatch.setattr(database_db, "get_sessionmaker", safe_get_sessionmaker)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_executed_analysis_ids():
    """Ensure in-memory executed analysis cache is cleanly reset between test runs."""
    yield
    try:
        from monika.application.execution.execution_service import _EXECUTED_ANALYSIS_IDS

        _EXECUTED_ANALYSIS_IDS.clear()
    except Exception:
        pass
