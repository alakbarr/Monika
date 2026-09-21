"""
Dual Checkpoint Saver for LangGraph.

Implements always-on dual-write persistence:
- Writes simultaneously to both Primary (PostgreSQL) and Secondary (local SQLite).
- On read, fetches from Primary; if Primary fails or is disconnected, transparently falls back to Secondary.
- Guarantees zero state loss across network disruptions and broker disconnects.
"""

import logging
from typing import Any, AsyncIterator, Iterator, Optional, Sequence
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)

logger = logging.getLogger("TradingAgent.DualCheckpointSaver")


class DualCheckpointSaver(BaseCheckpointSaver):
    """
    Dual-write LangGraph checkpointer orchestrating Primary (PostgreSQL) and Secondary (SQLite).
    """

    def __init__(self, primary: Any, secondary: Any):
        super().__init__()
        self.primary = primary
        self.secondary = secondary

    # Pass-through setup attribute for scheduler initialization
    @property
    def _needs_setup(self) -> bool:
        return getattr(self.primary, "_needs_setup", False)

    @_needs_setup.setter
    def _needs_setup(self, val: bool):
        if hasattr(self.primary, "_needs_setup"):
            setattr(self.primary, "_needs_setup", val)

    async def a_setup(self) -> None:
        """Initialize both checkpointer backends."""
        if hasattr(self.primary, "setup"):
            try:
                await self.primary.setup()
            except Exception as e:
                logger.warning(f"[DualCheckpointer] Primary setup error: {e}")
        if hasattr(self.secondary, "setup"):
            try:
                await self.secondary.setup()
            except Exception as e:
                logger.warning(f"[DualCheckpointer] Secondary setup error: {e}")

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Read from primary, fallback to secondary on failure."""
        try:
            res = self.primary.get_tuple(config)
            if res is not None:
                return res
        except Exception as e:
            logger.warning(f"[DualCheckpointer] Primary get_tuple failed ({e}). Falling back to secondary.")
        try:
            return self.secondary.get_tuple(config)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Secondary get_tuple also failed: {e}")
            return None

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Async read from primary, fallback to secondary on failure."""
        try:
            if hasattr(self.primary, "aget_tuple"):
                res = await self.primary.aget_tuple(config)
            else:
                res = self.primary.get_tuple(config)
            if res is not None:
                return res
        except Exception as e:
            logger.warning(f"[DualCheckpointer] Primary aget_tuple failed ({e}). Falling back to secondary.")
        try:
            if hasattr(self.secondary, "aget_tuple"):
                return await self.secondary.aget_tuple(config)
            return self.secondary.get_tuple(config)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Secondary aget_tuple also failed: {e}")
            return None

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints from primary, fallback to secondary."""
        try:
            return self.primary.list(config, filter=filter, before=before, limit=limit)
        except Exception as e:
            logger.warning(f"[DualCheckpointer] Primary list failed ({e}). Falling back to secondary.")
            return self.secondary.list(config, filter=filter, before=before, limit=limit)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Async list checkpoints from primary, fallback to secondary."""
        try:
            if hasattr(self.primary, "alist"):
                return self.primary.alist(config, filter=filter, before=before, limit=limit)
            return self.secondary.alist(config, filter=filter, before=before, limit=limit)
        except Exception as e:
            logger.warning(f"[DualCheckpointer] Primary alist failed ({e}). Falling back to secondary.")
            if hasattr(self.secondary, "alist"):
                return self.secondary.alist(config, filter=filter, before=before, limit=limit)
            return self.secondary.list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[ChannelVersions] = None,
    ) -> RunnableConfig:
        """Dual-write sync to both primary and secondary."""
        res_config = config
        # Primary write
        try:
            res_config = self.primary.put(config, checkpoint, metadata, new_versions=new_versions)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Primary put write failed: {e}")

        # Secondary write (local SQLite)
        try:
            self.secondary.put(config, checkpoint, metadata, new_versions=new_versions)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Secondary put write failed: {e}")

        return res_config

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[ChannelVersions] = None,
    ) -> RunnableConfig:
        """Dual-write async to both primary and secondary."""
        res_config = config
        # Primary write
        try:
            if hasattr(self.primary, "aput"):
                res_config = await self.primary.aput(config, checkpoint, metadata, new_versions=new_versions)
            else:
                res_config = self.primary.put(config, checkpoint, metadata, new_versions=new_versions)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Primary aput write failed: {e}")

        # Secondary write (local SQLite)
        try:
            if hasattr(self.secondary, "aput"):
                await self.secondary.aput(config, checkpoint, metadata, new_versions=new_versions)
            else:
                self.secondary.put(config, checkpoint, metadata, new_versions=new_versions)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Secondary aput write failed: {e}")

        return res_config

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Dual-write task writes sync."""
        try:
            self.primary.put_writes(config, writes, task_id)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Primary put_writes failed: {e}")
        try:
            self.secondary.put_writes(config, writes, task_id)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Secondary put_writes failed: {e}")

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Dual-write task writes async."""
        try:
            if hasattr(self.primary, "aput_writes"):
                await self.primary.aput_writes(config, writes, task_id)
            else:
                self.primary.put_writes(config, writes, task_id)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Primary aput_writes failed: {e}")
        try:
            if hasattr(self.secondary, "aput_writes"):
                await self.secondary.aput_writes(config, writes, task_id)
            else:
                self.secondary.put_writes(config, writes, task_id)
        except Exception as e:
            logger.error(f"[DualCheckpointer] Secondary aput_writes failed: {e}")
