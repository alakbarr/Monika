import asyncio
import sys
import warnings
import pytest

# Suppress pytest-asyncio event_loop_policy deprecation warning during transition
warnings.filterwarnings("ignore", category=pytest.PytestDeprecationWarning, message=".*event_loop_policy.*")


@pytest.hookimpl
def pytest_asyncio_loop_factories(config, item):
    """Customize pytest-asyncio event loop factory on Windows to use SelectorEventLoop."""
    if sys.platform == "win32":
        return {"default": asyncio.SelectorEventLoop}
    return None


@pytest.fixture(scope="session")
def event_loop_policy():
    """Fallback fixture to force SelectorEventLoop on Windows for psycopg and async compatibility."""
    if sys.platform == "win32":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=DeprecationWarning)
            return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


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

