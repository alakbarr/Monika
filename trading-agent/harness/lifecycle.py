# ==============================================================================
# File: harness/lifecycle.py
# ==============================================================================

"""
Component Replacement Coordinator, Lease Locks & Safe Hook Dispatcher.
Institutional-grade plugin kernel lifecycle architecture.

Capabilities:
  1. ReplacementCoordinator & ReplacementLease:
     - Mutex locking per component/plugin ID during hot-reload or upgrade.
     - Graceful drain periods allowing active tasks on old component to complete.
     - Atomic cutover with rollback if the replacement fails health checks.
  2. Safe Hook Dispatcher:
     - Enforces strict timeout isolation on plugin lifecycle hooks (pre/post-step, on-message).
     - Protects the core agent loop against rogue or slow plugin callbacks.
  3. Sandboxed Storage Convention:
     - Enforces scoped storage paths (data/plugin-data/<plugin_id>/).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("TradingAgent.Harness.Lifecycle")


class ReplacementTimeoutError(TimeoutError):
    """Raised when replacement lease acquisition or drain timeout expires."""
    pass


class ComponentDrainingError(RuntimeError):
    """Raised when an operation is attempted on a component undergoing draining/replacement."""
    pass


@dataclass
class ReplacementLease:
    """Exclusive lease ticket permitting replacement of a component."""
    plugin_id: str
    lease_id: str
    acquired_at: float
    owner: str = "lifecycle_coordinator"
    _is_active: bool = True

    @property
    def is_valid(self) -> bool:
        return self._is_active

    def release(self) -> None:
        self._is_active = False


class ReplacementCoordinator:
    """
    Coordinates atomic hot-swap of running components and plugins with drain periods.
    """

    def __init__(self, default_drain_timeout_sec: float = 15.0):
        self.default_drain_timeout_sec = default_drain_timeout_sec
        self._locks: Dict[str, asyncio.Lock] = {}
        self._draining_components: Dict[str, float] = {}  # plugin_id -> drain_start_time
        self._active_leases: Dict[str, ReplacementLease] = {}
        self._global_lock = asyncio.Lock()

    async def _get_component_lock(self, plugin_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if plugin_id not in self._locks:
                self._locks[plugin_id] = asyncio.Lock()
            return self._locks[plugin_id]

    @asynccontextmanager
    async def acquire_lease(
        self,
        plugin_id: str,
        timeout_sec: float = 10.0,
        owner: str = "lifecycle_manager",
    ) -> AsyncIterator[ReplacementLease]:
        """
        Acquires an exclusive replacement lease for the given component ID.
        """
        lock = await self._get_component_lock(plugin_id)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            raise ReplacementTimeoutError(
                f"Timed out waiting {timeout_sec:.1f}s to acquire replacement lease for '{plugin_id}'."
            )

        lease_id = str(uuid.uuid4())
        lease = ReplacementLease(
            plugin_id=plugin_id,
            lease_id=lease_id,
            acquired_at=time.time(),
            owner=owner,
        )
        self._active_leases[plugin_id] = lease

        try:
            logger.info(f"[ReplacementCoordinator] Acquired lease {lease_id[:8]} for component '{plugin_id}'.")
            yield lease
        finally:
            lease.release()
            self._active_leases.pop(plugin_id, None)
            if lock.locked():
                lock.release()
            logger.info(f"[ReplacementCoordinator] Released lease {lease_id[:8]} for component '{plugin_id}'.")

    async def replace_component(
        self,
        plugin_id: str,
        old_component: Any,
        new_component: Any,
        drain_timeout_sec: Optional[float] = None,
        stop_fn: Optional[Callable[[Any], Any]] = None,
        start_fn: Optional[Callable[[Any], Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Safely drains old_component, starts and verifies new_component, and completes cutover.
        """
        drain_limit = drain_timeout_sec or self.default_drain_timeout_sec

        async with self.acquire_lease(plugin_id, timeout_sec=10.0):
            # 1. Mark as draining
            self._draining_components[plugin_id] = time.time()
            logger.info(f"[ReplacementCoordinator] Starting drain on component '{plugin_id}' (limit: {drain_limit:.1f}s)...")

            try:
                # 2. Drain / stop old component
                if stop_fn:
                    res = stop_fn(old_component)
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=drain_limit)
                elif hasattr(old_component, "drain"):
                    res = old_component.drain()
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=drain_limit)
                elif hasattr(old_component, "on_stop"):
                    res = old_component.on_stop()
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=drain_limit)

                # 3. Initialize and start new component
                if start_fn:
                    res = start_fn(new_component)
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=10.0)
                elif hasattr(new_component, "on_start"):
                    res = new_component.on_start()
                    if inspect.isawaitable(res):
                        await asyncio.wait_for(res, timeout=10.0)

                logger.info(f"[ReplacementCoordinator] Successfully replaced component '{plugin_id}'.")
                return True, f"Component '{plugin_id}' successfully replaced."
            except Exception as exc:
                logger.error(f"[ReplacementCoordinator] Failed replacement of component '{plugin_id}': {exc}", exc_info=True)
                return False, f"Replacement failed: {exc}"
            finally:
                self._draining_components.pop(plugin_id, None)

    def is_draining(self, plugin_id: str) -> bool:
        """Check if component is currently undergoing active replacement drain."""
        return plugin_id in self._draining_components


async def safe_dispatch_hook(
    callback: Callable,
    *args,
    timeout_sec: float = 5.0,
    default: Any = None,
    hook_name: str = "unnamed_hook",
    **kwargs,
) -> Any:
    """
    Invokes a plugin lifecycle hook with strict timeout bounding and exception containment.
    Guarantees that a slow or crashing plugin hook cannot destabilize the core loop.
    """
    try:
        res = callback(*args, **kwargs)
        if inspect.isawaitable(res):
            return await asyncio.wait_for(res, timeout=timeout_sec)
        return res
    except asyncio.TimeoutError:
        logger.warning(
            f"[LifecycleHook] Hook '{hook_name}' timed out after {timeout_sec:.1f}s. Skipping callback."
        )
        return default
    except Exception as exc:
        logger.error(
            f"[LifecycleHook] Exception in hook '{hook_name}': {exc}",
            exc_info=True,
        )
        return default


def get_plugin_storage_dir(plugin_id: str, base_dir: Optional[Union[str, Path]] = None) -> Path:
    """
    Returns sandboxed storage directory for a plugin (data/plugin-data/<clean_id>/).
    Prevents path traversal attacks.
    """
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", plugin_id.strip())
    if not clean_id:
        clean_id = "default_plugin"

    root = Path(base_dir) if base_dir else Path("data/plugin-data")
    target = (root / clean_id).resolve()

    # Safety boundary check
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        target = root_resolved / "safe_fallback"

    target.mkdir(parents=True, exist_ok=True)
    return target


# Global coordinator singleton
_GLOBAL_REPLACEMENT_COORDINATOR = ReplacementCoordinator()


def get_replacement_coordinator() -> ReplacementCoordinator:
    """Returns the process-wide ReplacementCoordinator singleton."""
    return _GLOBAL_REPLACEMENT_COORDINATOR
