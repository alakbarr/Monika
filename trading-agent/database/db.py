# ==============================================================================
# File: database/db.py
# ==============================================================================

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Union

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.models import Base

from pathlib import Path

# Setup logger
logger = logging.getLogger(__name__)

# Search candidate .env locations (trading-agent/.env or repo root .env)
_cur_dir = Path(__file__).resolve().parent
for _cand in [Path.cwd() / ".env", _cur_dir.parent / ".env", _cur_dir / ".env"]:
    if _cand.exists():
        load_dotenv(dotenv_path=_cand, override=False)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///monika.db")

engine = None
_async_session_factory = None


class _AsyncSessionLocalProxy:
    """
    Callable proxy ensuring AsyncSessionLocal can be imported and called at any time,
    even before or after get_sessionmaker()/close_db().
    """

    def __call__(self, *args, **kwargs):
        import sys
        mod = sys.modules.get("database.db")
        if mod is not None:
            current = getattr(mod, "AsyncSessionLocal", None)
            if current is not None and current is not self:
                return current(*args, **kwargs)
        factory = _async_session_factory if _async_session_factory is not None else get_sessionmaker()
        return factory(*args, **kwargs)

    def __getattr__(self, name):
        import sys
        mod = sys.modules.get("database.db")
        if mod is not None:
            current = getattr(mod, "AsyncSessionLocal", None)
            if current is not None and current is not self:
                return getattr(current, name)
        factory = _async_session_factory if _async_session_factory is not None else get_sessionmaker()
        return getattr(factory, name)

    def __bool__(self):
        return True

    def __repr__(self):
        return f"<AsyncSessionLocalProxy target={_async_session_factory}>"


AsyncSessionLocal = _AsyncSessionLocalProxy()


def is_running_under_test_suite() -> bool:
    """Check if process or any ancestor in process tree is a test runner (e.g. pytest)."""
    import sys
    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
        return True
    try:
        import psutil
        curr = psutil.Process()
        for p in curr.parents():
            name = p.name().lower()
            if "pytest" in name:
                return True
    except Exception:
        pass
    return False


def verify_safe_database_url(url: str) -> None:
    """Ensure test runner doesn't accidentally connect to production database."""
    if is_running_under_test_suite():
        lower_url = url.lower()
        if "prod" in lower_url and not os.environ.get("MONIKA_ALLOW_PROD_DB_IN_TEST"):
            raise RuntimeError(
                f"SAFETY GUARD: Test process detected trying to connect to production database ({url}). Aborting."
            )


def get_tier() -> str:
    """Detect configured tier with fallback to trial."""
    tier = os.getenv("MONIKA_TIER")
    if tier:
        return tier.strip().lower()
    from pathlib import Path
    _cur = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / ".monika_tier",
        Path.cwd().parent / ".monika_tier",
        _cur.parent / ".monika_tier",
        _cur.parent.parent / ".monika_tier",
        _cur / ".monika_tier",
    ]
    for cand in candidates:
        if cand.exists():
            try:
                t = cand.read_text(encoding="utf-8").strip().lower()
                if t:
                    return t
            except Exception:
                pass
    return "trial"


def get_engine():
    """Lazy engine factory with connection pooling."""
    global engine
    if engine is None:
        tier = get_tier()
        if tier == "trial":
            from pathlib import Path
            data_dir = Path.cwd() / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = (data_dir / "monika.db").resolve()
            db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
            os.environ["DATABASE_URL"] = db_url
            os.environ["MONIKA_TIER"] = "trial"
            os.environ["PAPER_TRADING_MODE"] = "true"
        else:
            db_url = os.getenv("DATABASE_URL", DATABASE_URL)
        if db_url.startswith("sqlite://") and not db_url.startswith("sqlite+"):
            db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        verify_safe_database_url(db_url)
        engine_kwargs: dict[str, Any] = {"echo": False}
        if "postgresql" in db_url:
            engine_kwargs.update(
                {
                    "pool_size": 25,
                    "max_overflow": 35,
                    "pool_timeout": 60.0,
                    "pool_pre_ping": True,
                    "pool_recycle": 1800,
                    "connect_args": {
                        "timeout": 30.0,
                    },
                }
            )
        engine = create_async_engine(db_url, **engine_kwargs)
        if "sqlite" in db_url:
            from sqlalchemy import event

            @event.listens_for(engine.sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
    return engine


def get_sessionmaker():
    """Lazy sessionmaker factory bound to engine."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def init_db() -> None:
    """Initialize database schema and create all tables."""
    logger.info("Initializing database tables...")
    try:
        eng = engine if engine is not None else get_engine()
        get_sessionmaker()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield database session for FastAPI dependency injection."""
    sm = AsyncSessionLocal if (AsyncSessionLocal is not None and not isinstance(AsyncSessionLocal, _AsyncSessionLocalProxy)) else get_sessionmaker()
    async with sm() as session:
        yield session

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session as an asynchronous context manager."""
    sm = AsyncSessionLocal if (AsyncSessionLocal is not None and not isinstance(AsyncSessionLocal, _AsyncSessionLocalProxy)) else get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except (Exception, asyncio.CancelledError) as e:
            if isinstance(e, asyncio.CancelledError):
                logger.debug("Session cancelled, rolling back...")
            else:
                logger.error(f"Session error: {e}", exc_info=True)
            try:
                await session.rollback()
            except Exception as rb_err:
                logger.warning(f"Session rollback failed (original error preserved): {rb_err}")
            raise

_IN_MEMORY_EXECUTION_LOCKS: dict[int, asyncio.Lock] = {}

@asynccontextmanager
async def transactional_advisory_lock(session: AsyncSession, lock_key: Union[int, str] = 778899) -> AsyncGenerator[bool, None]:
    """
    Acquires a PostgreSQL transaction-level advisory lock (pg_try_advisory_xact_lock).
    Automatically releases when transaction commits/rolls back.
    Supports dynamic per-symbol or integer lock keys.
    Falls back gracefully to in-memory per-key asyncio.Lock for SQLite/mock test environments.
    """
    import hashlib
    from sqlalchemy import text
    bind = session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    
    # M-3: 64-bit positive signed integer key to prevent hash collision in pg_try_advisory_xact_lock
    numeric_key = (
        (int.from_bytes(hashlib.sha256(lock_key.encode('utf-8')).digest()[:8], 'big') & 0x7FFFFFFFFFFFFFFF)
        if isinstance(lock_key, str)
        else int(lock_key)
    )

    if dialect_name == "postgresql":
        acquired = False
        try:
            res = await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": numeric_key}
            )
            acquired = bool(res.scalar())
            if not acquired:
                logger.warning(f"[DB] Could not acquire PostgreSQL transaction advisory lock {numeric_key} (concurrent transaction active).")
        except Exception as e:
            logger.critical(f"[DB] PostgreSQL transaction advisory lock failed with error: {e}. BLOCKING execution (Fail-Closed).")
            acquired = False

        if not acquired:
            yield False
            return

        yield True
    else:
        lock = _IN_MEMORY_EXECUTION_LOCKS.setdefault(numeric_key, asyncio.Lock())
        async with lock:
            yield True

async def close_db() -> None:
    """Tutup koneksi database dengan aman."""
    global engine, _async_session_factory
    if engine is not None:
        logger.info("Disposing database engine...")
        await engine.dispose()
        engine = None
        _async_session_factory = None
        logger.info("Database engine disposed.")


