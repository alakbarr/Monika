import asyncio
import logging
import os
import sqlite3
from typing import Any, Dict, Optional, Sequence
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, ChannelVersions
from langgraph.checkpoint.memory import InMemorySaver

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

logger = logging.getLogger("TradingAgent.SqliteCheckpointer")


class SqliteCheckpointSaver(InMemorySaver):
    """Local SQLite checkpointer providing crash-safe state persistence across restarts.
    
    Serves as an autonomous tier between PostgreSQL and volatile MemorySaver (M-5).
    """

    def __init__(self, db_path: str = ".agent_state/checkpoints.sqlite"):
        super().__init__()
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a hardened SQLite connection with WAL mode and high-concurrency pragmas."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA journal_size_limit = 67108864")  # 64MB journal limit
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = self._get_connection()
        try:
            # Self-healing integrity check
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()
            if integrity and integrity[0] != "ok":
                logger.error(f"[SqliteCheckpointer] DB integrity failure: {integrity[0]}. Running self-healing REINDEX.")
                conn.execute("REINDEX")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT,
                    checkpoint_ns TEXT,
                    checkpoint_id TEXT,
                    parent_checkpoint_id TEXT,
                    checkpoint_type TEXT,
                    checkpoint_blob BLOB,
                    metadata_type TEXT,
                    metadata_blob BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS writes (
                    thread_id TEXT,
                    checkpoint_ns TEXT,
                    checkpoint_id TEXT,
                    task_id TEXT,
                    idx INTEGER,
                    channel TEXT,
                    value_type TEXT,
                    value_blob BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                )
            """)
            conn.commit()
        finally:
            conn.close()
        self._load_from_sqlite()

    def _load_from_sqlite(self):
        """Restore previous checkpoints and writes into memory state."""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_blob, metadata_type, metadata_blob FROM checkpoints")
                rows = cursor.fetchall()
                for t_id, ns, c_id, p_id, c_type, c_blob, m_type, m_blob in rows:
                    if t_id not in self.storage:
                        self.storage[t_id] = {}
                    if ns not in self.storage[t_id]:
                        self.storage[t_id][ns] = {}

                    self.storage[t_id][ns][c_id] = (
                        (str(c_type), bytes(c_blob)),
                        (str(m_type), bytes(m_blob)),
                        str(p_id) if p_id is not None else None,
                    )
                logger.debug(f"[SqliteCheckpointer] Loaded {len(rows)} persistent checkpoints from {self.db_path}")

                cursor.execute("SELECT thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, value_type, value_blob FROM writes")
                write_rows = cursor.fetchall()
                for t_id, ns, c_id, task_id, idx, channel, v_type, v_blob in write_rows:
                    outer_key = (t_id, ns, c_id)
                    inner_key = (task_id, idx)
                    self.writes[outer_key][inner_key] = (
                        task_id,
                        channel,
                        (str(v_type), bytes(v_blob)),
                        "",
                    )
                if write_rows:
                    logger.debug(f"[SqliteCheckpointer] Loaded {len(write_rows)} persistent writes from {self.db_path}")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[SqliteCheckpointer] Failed loading checkpoints from SQLite: {e}")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[ChannelVersions] = None,
    ) -> RunnableConfig:
        versions: ChannelVersions = new_versions or {}
        res = super().put(config, checkpoint, metadata, new_versions=versions)
        try:
            cfg: Dict[str, Any] = getattr(config, "get", lambda k, d=None: {})("configurable", {}) or {}
            thread_id = cfg.get("thread_id", "")
            checkpoint_ns = cfg.get("checkpoint_ns", "")
            checkpoint_id = checkpoint["id"]
            parent_checkpoint_id = cfg.get("checkpoint_id")

            serde: Any = getattr(self, "serde", None)
            if hasattr(serde, "dumps_typed"):
                type_chk, c_blob = serde.dumps_typed(checkpoint)
                type_meta, m_blob = serde.dumps_typed(metadata)
            elif hasattr(serde, "dumps"):
                type_chk, c_blob = ("json", serde.dumps(checkpoint))
                type_meta, m_blob = ("json", serde.dumps(metadata))
            else:
                type_chk, c_blob = ("json", b"")
                type_meta, m_blob = ("json", b"")

            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO checkpoints 
                    (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_blob, metadata_type, metadata_blob)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type_chk, c_blob, type_meta, m_blob),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[SqliteCheckpointer] Failed to persist checkpoint to SQLite: {e}")
        return res

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[ChannelVersions] = None,
    ) -> RunnableConfig:
        versions: ChannelVersions = new_versions or {}
        res = super().put(config, checkpoint, metadata, new_versions=versions)
        try:
            cfg: Dict[str, Any] = getattr(config, "get", lambda k, d=None: {})("configurable", {}) or {}
            thread_id = cfg.get("thread_id", "")
            checkpoint_ns = cfg.get("checkpoint_ns", "")
            checkpoint_id = checkpoint["id"]
            parent_checkpoint_id = cfg.get("checkpoint_id")

            serde: Any = getattr(self, "serde", None)
            if hasattr(serde, "dumps_typed"):
                type_chk, c_blob = serde.dumps_typed(checkpoint)
                type_meta, m_blob = serde.dumps_typed(metadata)
            elif hasattr(serde, "dumps"):
                type_chk, c_blob = ("json", serde.dumps(checkpoint))
                type_meta, m_blob = ("json", serde.dumps(metadata))
            else:
                type_chk, c_blob = ("json", b"")
                type_meta, m_blob = ("json", b"")

            if aiosqlite is not None:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.execute(
                        """
                        INSERT OR REPLACE INTO checkpoints 
                        (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_blob, metadata_type, metadata_blob)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type_chk, c_blob, type_meta, m_blob),
                    )
                    await conn.commit()
            else:
                await asyncio.to_thread(
                    self._persist_checkpoint_sync,
                    thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type_chk, c_blob, type_meta, m_blob
                )
        except Exception as e:
            logger.warning(f"[SqliteCheckpointer] Failed to persist checkpoint asynchronously: {e}")
        return res

    def _persist_checkpoint_sync(self, thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type_chk, c_blob, type_meta, m_blob):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints 
                (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint_type, checkpoint_blob, metadata_type, metadata_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type_chk, c_blob, type_meta, m_blob),
            )
            conn.commit()
        finally:
            conn.close()

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path=task_path)
        try:
            cfg = getattr(config, "get", lambda k, d=None: {})("configurable", {}) or {}
            thread_id = str(cfg.get("thread_id", ""))
            checkpoint_ns = str(cfg.get("checkpoint_ns", ""))
            checkpoint_id = str(cfg.get("checkpoint_id", ""))
            serde: Any = getattr(self, "serde", None)

            rows = []
            for idx, (channel, value) in enumerate(writes):
                if hasattr(serde, "dumps_typed"):
                    v_type, v_blob = serde.dumps_typed(value)
                elif hasattr(serde, "dumps"):
                    v_type, v_blob = ("json", serde.dumps(value))
                else:
                    v_type, v_blob = ("json", b"")
                rows.append((thread_id, checkpoint_ns, checkpoint_id, task_id, idx, str(channel), str(v_type), bytes(v_blob)))

            conn = sqlite3.connect(self.db_path)
            try:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO writes
                    (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, value_type, value_blob)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[SqliteCheckpointer] Failed to persist writes to SQLite: {e}")

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path=task_path)
        try:
            cfg = getattr(config, "get", lambda k, d=None: {})("configurable", {}) or {}
            thread_id = str(cfg.get("thread_id", ""))
            checkpoint_ns = str(cfg.get("checkpoint_ns", ""))
            checkpoint_id = str(cfg.get("checkpoint_id", ""))
            serde: Any = getattr(self, "serde", None)

            rows = []
            for idx, (channel, value) in enumerate(writes):
                if hasattr(serde, "dumps_typed"):
                    v_type, v_blob = serde.dumps_typed(value)
                elif hasattr(serde, "dumps"):
                    v_type, v_blob = ("json", serde.dumps(value))
                else:
                    v_type, v_blob = ("json", b"")
                rows.append((thread_id, checkpoint_ns, checkpoint_id, task_id, idx, str(channel), str(v_type), bytes(v_blob)))

            if aiosqlite is not None:
                async with aiosqlite.connect(self.db_path) as conn:
                    await conn.executemany(
                        """
                        INSERT OR REPLACE INTO writes
                        (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, value_type, value_blob)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                    await conn.commit()
            else:
                await asyncio.to_thread(self._persist_writes_sync, rows)
        except Exception as e:
            logger.warning(f"[SqliteCheckpointer] Failed to persist writes asynchronously: {e}")

    def _persist_writes_sync(self, rows):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                """
                INSERT OR REPLACE INTO writes
                (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, value_type, value_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()

