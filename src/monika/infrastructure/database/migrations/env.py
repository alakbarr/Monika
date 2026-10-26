# ==============================================================================
# File: database/migrations/env.py
# ==============================================================================

import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import monika.application.benchmark.db_models
from monika.infrastructure.database.models import Base

target_metadata = Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# Preserve application loggers when running in-process inside the trading agent.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    if not logging.getLogger("TradingAgent").handlers:
        fileConfig(config.config_file_name, disable_existing_loggers=False)

custom_url = config.attributes.get("sqlalchemy_url") or config.get_main_option("custom_sqlalchemy_url")
test_db_url = os.getenv("TEST_DATABASE_URL")
if custom_url:
    url = custom_url
elif test_db_url:
    url = test_db_url
else:
    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    DATABASE_URL = os.getenv("DATABASE_URL")
    url = DATABASE_URL or config.get_main_option("sqlalchemy.url") or ""

if url.startswith("postgresql://") and "+asyncpg" not in url:
    url = url.replace("postgresql://", "postgresql+asyncpg://")
elif url.startswith("sqlite://") and "+aiosqlite" not in url:
    url = url.replace("sqlite://", "sqlite+aiosqlite://")

config.set_main_option("sqlalchemy.url", url)


def include_object(object, name, type_, reflected, compare_to):
    # Ignore tables managed outside Alembic (e.g. LangGraph checkpointer, raw partition tables)
    if type_ == "table":
        if name in {
            "checkpoints",
            "wal_entries",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
            "price_ohlcv_partitioned",
        } or (name.startswith("price_ohlcv_") and name != "price_ohlcv_rejected"):
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import sys

    if sys.platform == "win32":
        asyncio.run(run_async_migrations(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
