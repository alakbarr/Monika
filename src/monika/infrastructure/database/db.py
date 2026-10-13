# ==============================================================================
# File: database/db.py
# ==============================================================================

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Union

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from monika.infrastructure.database.models import Base

# Setup logger
logger = logging.getLogger(__name__)

# Search candidate .env locations (trading-agent/.env or repo root .env)
_cur_dir = Path(__file__).resolve().parent
for _cand in [Path.cwd() / ".env", _cur_dir.parent.parent / ".env", _cur_dir.parent / ".env", _cur_dir / ".env"]:
    if _cand.exists():
        load_dotenv(dotenv_path=_cand, override=False)


def get_database_url() -> str:
    """
    Retrieve configured database connection URL lazily.
    Checks:
    1. settings.database.url (from central settings)
    2. DATABASE_URL environment variable
    3. Fallback: sqlite+aiosqlite:///monika.db
    """
    try:
        from monika.core.config.settings import load_settings

        settings = load_settings()
        cfg_url = (settings.get("database") or {}).get("url")
        if cfg_url and isinstance(cfg_url, str) and cfg_url.strip():
            return cfg_url.strip()
    except Exception:
        pass

    env_url = os.getenv("DATABASE_URL")
    if env_url and env_url.strip():
        return env_url.strip()

    return "sqlite+aiosqlite:///monika.db"


if TYPE_CHECKING:
    DATABASE_URL: str


def __getattr__(name: str) -> Any:
    if name == "DATABASE_URL":
        return get_database_url()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


engine = None
_async_session_factory = None
_engine_lock = threading.Lock()


class _AsyncSessionLocalProxy:
    """
    Callable proxy ensuring AsyncSessionLocal can be imported and called at any time,
    even before or after get_sessionmaker()/close_db().
    """

    def __call__(self, *args, **kwargs):
        import sys

        mod = sys.modules.get("monika.infrastructure.database.db") or sys.modules.get("database.db")
        if mod is not None:
            current = getattr(mod, "AsyncSessionLocal", None)
            if current is not None and current is not self:
                return current(*args, **kwargs)
        factory = _async_session_factory if _async_session_factory is not None else get_sessionmaker()
        return factory(*args, **kwargs)

    def __getattr__(self, name):
        import sys

        mod = sys.modules.get("monika.infrastructure.database.db") or sys.modules.get("database.db")
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
    """Detect configured tier via canonical settings resolver with fallback to trial."""
    try:
        from monika.core.config.settings import get_installation_tier

        return get_installation_tier()
    except Exception:
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


def get_canonical_db_path() -> Path:
    """Return absolute canonical database file path for Monika SQLite database."""
    base_data_dir = _cur_dir.parent / "data"
    base_data_dir.mkdir(parents=True, exist_ok=True)
    return (base_data_dir / "monika.db").resolve()


def get_engine():
    """Lazy engine factory with connection pooling (thread-safe)."""
    global engine
    if engine is None:
        with _engine_lock:
            if engine is None:
                tier = get_tier()
                env_url = os.getenv("DATABASE_URL")
                if is_running_under_test_suite() and env_url:
                    db_url = env_url
                elif tier == "trial":
                    db_path = get_canonical_db_path()
                    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
                    os.environ["DATABASE_URL"] = db_url
                    os.environ["MONIKA_TIER"] = "trial"
                    os.environ["PAPER_TRADING_MODE"] = "true"
                else:
                    db_url = env_url or get_database_url()
                if db_url.startswith("sqlite://") and not db_url.startswith("sqlite+"):
                    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
                elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
                    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

                # Normalize relative SQLite paths to canonical absolute path unless test/in-memory
                if "sqlite" in db_url and ":memory:" not in db_url and not is_running_under_test_suite():
                    for prefix in [
                        "sqlite+aiosqlite:///data/monika.db",
                        "sqlite+aiosqlite:///monika.db",
                        "sqlite+aiosqlite:///./data/monika.db",
                        "sqlite+aiosqlite:///./monika.db",
                    ]:
                        if db_url == prefix:
                            db_url = f"sqlite+aiosqlite:///{get_canonical_db_path().as_posix()}"
                            break

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
                elif "sqlite" in db_url:
                    if ":memory:" in db_url:
                        from sqlalchemy.pool import StaticPool

                        engine_kwargs.update(
                            {
                                "poolclass": StaticPool,
                                "connect_args": {
                                    "check_same_thread": False,
                                },
                            }
                        )
                    else:
                        engine_kwargs.update(
                            {
                                "pool_size": 20,
                                "max_overflow": 30,
                                "pool_timeout": 60.0,
                                "pool_pre_ping": True,
                                "pool_recycle": 1800,
                                "connect_args": {
                                    "timeout": 60.0,
                                },
                            }
                        )
                new_engine = create_async_engine(db_url, **engine_kwargs)
                if "sqlite" in db_url:
                    from sqlalchemy import event

                    @event.listens_for(new_engine.sync_engine, "connect")
                    def _set_sqlite_pragma(dbapi_connection, connection_record):
                        try:
                            dbapi_connection.isolation_level = None
                        except Exception:
                            pass
                        cursor = dbapi_connection.cursor()
                        cursor.execute("PRAGMA journal_mode=WAL")
                        cursor.execute("PRAGMA busy_timeout=60000")
                        cursor.execute("PRAGMA synchronous=NORMAL")
                        cursor.execute("PRAGMA cache_size=-64000")
                        cursor.execute("PRAGMA journal_size_limit=67108864")
                        cursor.close()

                    @event.listens_for(new_engine.sync_engine, "begin")
                    def _sqlite_begin_immediate(conn):
                        conn.exec_driver_sql("BEGIN IMMEDIATE")

                engine = new_engine

    return engine


def get_sessionmaker():
    """Lazy sessionmaker factory bound to engine (thread-safe)."""
    global _async_session_factory
    if _async_session_factory is None:
        with _engine_lock:
            if _async_session_factory is None:
                _async_session_factory = async_sessionmaker(
                    bind=get_engine(),
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
    return _async_session_factory


async def init_db() -> None:
    """Initialize database schema via Alembic migrations, falling back to create_all if offline/testing."""
    logger.info("Initializing database schema...")
    if not is_running_under_test_suite():
        try:
            from alembic import command
            from alembic.config import Config

            from monika.infrastructure.infra.paths import get_repo_root

            alembic_ini = get_repo_root() / "alembic.ini"
            if not alembic_ini.exists():
                alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
            if alembic_ini.exists():
                alembic_cfg = Config(str(alembic_ini))
                eng = engine if engine is not None else get_engine()
                db_url = str(eng.url)
                alembic_cfg.set_main_option("sqlalchemy.url", db_url)
                await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
                logger.info("Database schema synchronized to Alembic head successfully.")
                return
            else:
                raise FileNotFoundError(f"Alembic configuration file not found at {alembic_ini}")
        except Exception as e:
            logger.critical(f"Alembic migration failed in operational environment: {e}")
            raise RuntimeError(f"Database schema migration failed in operational environment: {e}") from e

    try:
        eng = engine if engine is not None else get_engine()
        get_sessionmaker()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified via metadata.create_all.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield database session for FastAPI dependency injection."""
    sm = (
        AsyncSessionLocal
        if (AsyncSessionLocal is not None and not isinstance(AsyncSessionLocal, _AsyncSessionLocalProxy))
        else get_sessionmaker()
    )
    async with sm() as session:
        yield session


_SQLITE_WRITE_LOCKS: dict[Any, asyncio.Lock] = {}


def _get_write_lock() -> asyncio.Lock:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop not in _SQLITE_WRITE_LOCKS:
        _SQLITE_WRITE_LOCKS[loop] = asyncio.Lock()
    return _SQLITE_WRITE_LOCKS[loop]


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session as an asynchronous context manager (optimistic / non-blocking)."""
    sm = (
        AsyncSessionLocal
        if (AsyncSessionLocal is not None and not isinstance(AsyncSessionLocal, _AsyncSessionLocalProxy))
        else get_sessionmaker()
    )
    async with sm() as session:
        try:
            yield session
        except (Exception, asyncio.CancelledError) as e:
            if isinstance(e, asyncio.CancelledError):
                logger.debug("Session cancelled, rolling back...")
            else:
                logger.error(f"Session error: {e}", exc_info=True)
            try:
                await asyncio.shield(session.rollback())
            except Exception as rb_err:
                logger.warning(f"Session rollback failed (original error preserved): {rb_err}")
            raise


@asynccontextmanager
async def get_write_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async session serialized for write operations.
    On SQLite, acquires an in-process async mutex to guarantee single-writer determinism.
    On PostgreSQL, proceeds with standard connection concurrency.
    Automatically commits on normal exit, or rolls back cleanly on exception.
    """
    eng = engine if engine is not None else get_engine()
    dialect_name = getattr(getattr(eng, "dialect", None), "name", "").lower()
    is_sqlite = "sqlite" in dialect_name

    if is_sqlite:
        async with _get_write_lock():
            async with get_session() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    try:
                        await asyncio.shield(session.rollback())
                    except Exception:
                        pass
                    raise
    else:
        async with get_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                try:
                    await asyncio.shield(session.rollback())
                except Exception:
                    pass
                raise


_IN_MEMORY_EXECUTION_LOCKS: dict[int, asyncio.Lock] = {}


@asynccontextmanager
async def transactional_advisory_lock(
    session: AsyncSession, lock_key: Union[int, str] = 778899
) -> AsyncGenerator[bool, None]:
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
        (int.from_bytes(hashlib.sha256(lock_key.encode("utf-8")).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF)
        if isinstance(lock_key, str)
        else int(lock_key)
    )

    if dialect_name == "postgresql":
        acquired = False
        try:
            res = await session.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": numeric_key})
            acquired = bool(res.scalar())
            if not acquired:
                logger.warning(
                    f"[DB] Could not acquire PostgreSQL transaction advisory lock {numeric_key} (concurrent transaction active)."
                )
        except Exception as e:
            logger.critical(
                f"[DB] PostgreSQL transaction advisory lock failed with error: {e}. BLOCKING execution (Fail-Closed)."
            )
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
    _SQLITE_WRITE_LOCKS.clear()
    _IN_MEMORY_EXECUTION_LOCKS.clear()
    if engine is not None:
        logger.info("Disposing database engine...")
        await engine.dispose()
        engine = None
        _async_session_factory = None
        logger.info("Database engine disposed.")
