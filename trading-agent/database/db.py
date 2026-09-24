# ==============================================================================
# File: database/db.py
# ==============================================================================

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Union

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from database.models import Base

# Setup logger
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/trading_db")

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


def get_engine():
    """Lazy engine factory with connection pooling."""
    global engine
    if engine is None:
        db_url = os.getenv("DATABASE_URL", DATABASE_URL)
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
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
    """Inisialisasi database (buat semua tabel)."""
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
    """Menghasilkan session database (untuk dependency injection FastAPI/lainnya)."""
    sm = AsyncSessionLocal if (AsyncSessionLocal is not None and not isinstance(AsyncSessionLocal, _AsyncSessionLocalProxy)) else get_sessionmaker()
    async with sm() as session:
        yield session

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Mengembalikan session async dengan context manager."""
    sm = AsyncSessionLocal if (AsyncSessionLocal is not None and not isinstance(AsyncSessionLocal, _AsyncSessionLocalProxy)) else get_sessionmaker()
    async with sm() as session:
        try:
            yield session
        except (Exception, asyncio.CancelledError) as e:
            if isinstance(e, asyncio.CancelledError):
                logger.debug("Session cancelled, rolling back...")
            else:
                logger.error(f"Session error: {e}")
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
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": numeric_key}
            )
            acquired = bool(res.scalar())
            if not acquired:
                logger.warning(f"[DB] Could not acquire PostgreSQL advisory lock {numeric_key} (concurrent transaction active).")
        except Exception as e:
            logger.critical(f"[DB] PostgreSQL advisory lock failed with error: {e}. BLOCKING execution (Fail-Closed).")
            acquired = False

        if not acquired:
            yield False
            return

        try:
            yield True
        finally:
            try:
                if session.in_transaction() and not session.is_active:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                await session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": numeric_key})
            except Exception as e:
                logger.warning(f"[DB] Error releasing advisory lock {numeric_key}: {e}")
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


