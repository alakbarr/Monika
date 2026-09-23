"""
File: trading-agent/utils/protocol/event_bus.py

Typed Asynchronous Event Bus for High-Performance Decoupled Architecture.
Supports:
1. Strongly typed dataclass events (TickPriceEvent, BarClosedEvent, OrderStateChangedEvent,
   RiskBreachEvent, CircuitBreakerEvent).
2. Asynchronous pub-sub with prioritization and full exception isolation.
3. Queue-based buffered delivery for high-throughput market tick streaming.
4. Polymorphic event hierarchy dispatch.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Type, TypeVar, Union
import inspect

logger = logging.getLogger("TradingAgent.EventBus")

E = TypeVar("E", bound="AppEvent")


# ==============================================================================
# 1. Event Type Definitions
# ==============================================================================

@dataclass(frozen=True)
class AppEvent:
    """Base class for all application domain events."""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class TickPriceEvent(AppEvent):
    """Real-time market quote tick event."""
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    spread: float = 0.0


@dataclass(frozen=True)
class BarClosedEvent(AppEvent):
    """Completed OHLCV candle bar event."""
    symbol: str = ""
    timeframe: str = ""
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0


@dataclass(frozen=True)
class OrderStateChangedEvent(AppEvent):
    """Order state transition event."""
    order_id: str = ""
    symbol: str = ""
    old_state: str = ""
    new_state: str = ""
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RiskBreachEvent(AppEvent):
    """Risk gate or drawndown threshold breach event."""
    breach_type: str = ""
    symbol: Optional[str] = None
    details: dict = field(default_factory=dict)
    severity: str = "warning"  # 'warning', 'critical', 'fatal'


@dataclass(frozen=True)
class CircuitBreakerEvent(AppEvent):
    """Circuit breaker state change event (e.g., FlashCrash, Margin, MaxLoss)."""
    component: str = ""
    reason: str = ""
    is_active: bool = True
    cooldown_seconds: int = 0


@dataclass(frozen=True)
class PreRiskGateEvent(AppEvent):
    """Domain hook triggered prior to RiskGate evaluation."""
    symbol: str = ""
    direction: str = ""
    proposal: Any = None
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PreOrderEvent(AppEvent):
    """Domain hook triggered immediately before order dispatch to broker."""
    symbol: str = ""
    order_request: Any = None
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PostFillEvent(AppEvent):
    """Domain hook triggered immediately after order fill confirmation."""
    ticket: Optional[int] = None
    symbol: str = ""
    volume: float = 0.0
    price: float = 0.0
    fill_time: Optional[datetime] = None
    context: dict = field(default_factory=dict)


# ==============================================================================
# 2. Subscription Metadata
# ==============================================================================

@dataclass
class Subscription:
    """Handler subscription record with priority ordering."""
    event_type: Type[AppEvent]
    handler: Callable[[Any], Union[Coroutine[Any, Any, None], Any]]
    priority: int = 0  # Higher integer = earlier execution


# ==============================================================================
# 3. Asynchronous Event Bus Implementation
# ==============================================================================

class EventBus:
    """
    Central Asynchronous Event Bus.
    Supports:
    - Instance & Singleton usage
    - Priority-based subscriber ordering
    - Polymorphic subscription (subscribing to AppEvent receives all events)
    - Exception isolation (one failing subscriber never fails others or publisher)
    - Queue-based buffered streaming
    """

    _default_instance: Optional["EventBus"] = None

    def __init__(self):
        self._subscribers: Dict[Type[AppEvent], List[Subscription]] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._queue_stats: Dict[str, Dict[str, int]] = {}
        self._worker_tasks: Dict[str, asyncio.Task] = {}
        self._running: bool = True

    # --------------------------------------------------------------------------
    # Subscription Management
    # --------------------------------------------------------------------------

    def subscribe(
        self,
        event_type: Type[E],
        handler: Callable[[E], Union[Coroutine[Any, Any, None], Any]],
        priority: int = 0,
    ) -> Callable[[E], Union[Coroutine[Any, Any, None], Any]]:
        """
        Register a subscriber for a specific event type or base class.
        
        Args:
            event_type: The event class to subscribe to.
            handler: Async coroutine function or sync callable taking the event as argument.
            priority: Execution priority (higher executes first, default 0).
            
        Returns:
            The handler function for convenience.
        """
        if not (isinstance(event_type, type) and issubclass(event_type, AppEvent)):
            raise TypeError(f"event_type must be a subclass of AppEvent, got {event_type}")

        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        sub = Subscription(event_type=event_type, handler=handler, priority=priority)
        self._subscribers[event_type].append(sub)
        # Sort descending by priority so high priority runs first
        self._subscribers[event_type].sort(key=lambda s: s.priority, reverse=True)
        logger.debug(
            f"[EventBus] Subscribed {getattr(handler, '__name__', str(handler))} "
            f"to {event_type.__name__} (priority={priority})"
        )
        return handler

    def unsubscribe(
        self,
        event_type: Type[E],
        handler: Callable[[E], Union[Coroutine[Any, Any, None], Any]],
    ) -> bool:
        """
        Unsubscribe a handler from an event type.
        
        Returns:
            True if handler was found and removed, False otherwise.
        """
        if event_type not in self._subscribers:
            return False

        initial_len = len(self._subscribers[event_type])
        self._subscribers[event_type] = [
            s for s in self._subscribers[event_type] if s.handler != handler
        ]
        removed = len(self._subscribers[event_type]) < initial_len
        if removed:
            logger.debug(
                f"[EventBus] Unsubscribed {getattr(handler, '__name__', str(handler))} "
                f"from {event_type.__name__}"
            )
        return removed

    def get_subscribers(self, event_type: Type[AppEvent]) -> List[Subscription]:
        """Get all subscriptions matching the event type, including polymorphic bases."""
        matching: List[Subscription] = []
        for registered_type, subs in self._subscribers.items():
            if issubclass(event_type, registered_type):
                matching.extend(subs)
        # Sort all matching by priority descending
        matching.sort(key=lambda s: s.priority, reverse=True)
        # Deduplicate by handler preserving highest registered priority
        seen_handlers = set()
        deduped: List[Subscription] = []
        for s in matching:
            if s.handler not in seen_handlers:
                seen_handlers.add(s.handler)
                deduped.append(s)
        return deduped

    # --------------------------------------------------------------------------
    # Publishing & Dispatch
    # --------------------------------------------------------------------------

    async def publish(self, event: AppEvent) -> List[Any]:
        """
        Publish an event to all matching subscribers with full exception isolation.
        
        Subscribers are invoked in priority groups; subscribers with identical priority
        are executed concurrently via asyncio.gather(return_exceptions=True).
        
        Args:
            event: The AppEvent instance to publish.
            
        Returns:
            List of results or exceptions returned by handlers.
        """
        if not isinstance(event, AppEvent):
            raise TypeError(f"Expected AppEvent instance, got {type(event).__name__}")

        subscriptions = self.get_subscribers(type(event))
        if not subscriptions:
            return []

        # Group by priority to respect order while allowing parallel execution within same priority
        priority_groups: Dict[int, List[Subscription]] = {}
        for sub in subscriptions:
            priority_groups.setdefault(sub.priority, []).append(sub)

        # Priorities descending
        sorted_priorities = sorted(priority_groups.keys(), reverse=True)
        all_results: List[Any] = []

        for p in sorted_priorities:
            group = priority_groups[p]

            async def _invoke_safe(sub: Subscription) -> Any:
                try:
                    if inspect.iscoroutinefunction(sub.handler):
                        return await sub.handler(event)
                    else:
                        res = sub.handler(event)
                        if inspect.isawaitable(res):
                            return await res
                        return res
                except Exception as exc:
                    handler_name = getattr(sub.handler, "__name__", str(sub.handler))
                    logger.error(
                        f"[EventBus] Handler '{handler_name}' raised error processing "
                        f"{event.__class__.__name__}: {exc}",
                        exc_info=True,
                    )
                    return exc

            results = await asyncio.gather(*(_invoke_safe(s) for s in group), return_exceptions=True)
            all_results.extend(results)

        return all_results

    def publish_nowait(self, event: AppEvent) -> Optional[asyncio.Task]:
        """
        Non-blocking fire-and-forget publish scheduled on the active asyncio event loop.
        Attaches a done callback to capture and log any unhandled task exceptions.
        
        Returns:
            asyncio.Task if event loop is running, None otherwise.
        """
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.publish(event))

            def _handle_done(t: asyncio.Task):
                if not t.cancelled():
                    exc = t.exception()
                    if exc:
                        logger.error(f"[EventBus] publish_nowait task failed with exception: {exc}")

            task.add_done_callback(_handle_done)
            return task
        except RuntimeError:
            logger.warning("[EventBus] publish_nowait called without running event loop.")
            return None

    def publish_threadsafe(self, event: AppEvent, loop: Optional[asyncio.AbstractEventLoop] = None) -> Any:
        """
        Thread-safe publish for external background threads (MT5 COM worker, EA bridge).
        Dispatches coroutine safely to the main asyncio loop.
        """
        target_loop = loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        if target_loop and target_loop.is_running():
            return asyncio.run_coroutine_threadsafe(self.publish(event), target_loop)
        else:
            logger.warning("[EventBus] publish_threadsafe called with no running event loop.")
            return None

    async def publish_waterfall(self, event: AppEvent, initial_payload: Any = None) -> Any:
        """
        Waterfall dispatch mode: invokes subscribers sequentially in priority order.
        Each handler receives (event, current_payload) and its returned result is passed as
        the payload to the next handler.
        """
        if not isinstance(event, AppEvent):
            raise TypeError(f"Expected AppEvent instance, got {type(event).__name__}")

        subscriptions = self.get_subscribers(type(event))
        current_val = initial_payload

        for sub in subscriptions:
            try:
                sig = inspect.signature(sub.handler)
                takes_payload = len(sig.parameters) >= 2
                if inspect.iscoroutinefunction(sub.handler):
                    if takes_payload:
                        current_val = await sub.handler(event, current_val)
                    else:
                        current_val = await sub.handler(event)
                else:
                    if takes_payload:
                        res = sub.handler(event, current_val)
                    else:
                        res = sub.handler(event)
                    if inspect.isawaitable(res):
                        current_val = await res
                    else:
                        current_val = res
            except Exception as exc:
                handler_name = getattr(sub.handler, "__name__", str(sub.handler))
                logger.error(
                    f"[EventBus.waterfall] Error in {handler_name} processing {event.__class__.__name__}: {exc}",
                    exc_info=True,
                )
        return current_val

    async def publish_bail(self, event: AppEvent) -> Optional[Any]:
        """
        Bail dispatch mode: invokes subscribers sequentially in priority order,
        stopping and returning immediately upon the first truthy / non-None result.
        Useful for pre-trade interceptors, gating decisions, and permission checks.
        """
        if not isinstance(event, AppEvent):
            raise TypeError(f"Expected AppEvent instance, got {type(event).__name__}")

        subscriptions = self.get_subscribers(type(event))

        for sub in subscriptions:
            try:
                if inspect.iscoroutinefunction(sub.handler):
                    res = await sub.handler(event)
                else:
                    res = sub.handler(event)
                    if inspect.isawaitable(res):
                        res = await res
                if res:
                    return res
            except Exception as exc:
                handler_name = getattr(sub.handler, "__name__", str(sub.handler))
                logger.error(
                    f"[EventBus.bail] Error in {handler_name} processing {event.__class__.__name__}: {exc}",
                    exc_info=True,
                )
        return None

    # --------------------------------------------------------------------------
    # Buffered Queue Delivery (for decoupling high-frequency streams)
    # --------------------------------------------------------------------------

    def get_or_create_queue(self, queue_name: str = "default", maxsize: int = 2000) -> asyncio.Queue:
        """Get or create a named event buffer queue."""
        if queue_name not in self._queues:
            self._queues[queue_name] = asyncio.Queue(maxsize=maxsize)
        if queue_name not in self._queue_stats:
            self._queue_stats[queue_name] = {
                "queued_count": 0,
                "dropped_count": 0,
                "high_watermark": 0,
            }
        return self._queues[queue_name]

    def get_queue_stats(self, queue_name: str = "default") -> Dict[str, Any]:
        """Returns statistics for a named queue (current size, maxsize, dropped count, high watermark)."""
        queue = self._queues.get(queue_name)
        stats = self._queue_stats.get(queue_name, {"queued_count": 0, "dropped_count": 0, "high_watermark": 0})
        return {
            "queue_name": queue_name,
            "current_size": queue.qsize() if queue else 0,
            "maxsize": queue.maxsize if queue else 0,
            "queued_count": stats["queued_count"],
            "dropped_count": stats["dropped_count"],
            "high_watermark": stats["high_watermark"],
        }

    async def publish_buffered(
        self,
        event: AppEvent,
        queue_name: str = "default",
        backpressure_mode: str = "drop_oldest",
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Put event into buffered queue with backpressure policies.
        Supported backpressure modes:
        - 'drop_oldest': Drops oldest item if queue is full (streaming priority).
        - 'block': Awaits space in queue with optional timeout.
        - 'raise': Raises asyncio.QueueFull if queue is full.
        
        Returns:
            True if queued, False if discarded/timed out.
        """
        queue = self.get_or_create_queue(queue_name)
        stats = self._queue_stats[queue_name]

        if backpressure_mode == "drop_oldest":
            if queue.full():
                try:
                    _ = queue.get_nowait()
                    queue.task_done()
                    stats["dropped_count"] += 1
                    logger.warning(f"[EventBus] Queue '{queue_name}' full, dropped oldest event (backpressure=drop_oldest).")
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
                stats["queued_count"] += 1
                stats["high_watermark"] = max(stats["high_watermark"], queue.qsize())
                return True
            except asyncio.QueueFull:
                stats["dropped_count"] += 1
                logger.error(f"[EventBus] Failed to queue event into '{queue_name}'.")
                return False

        elif backpressure_mode == "block":
            try:
                if timeout is not None:
                    await asyncio.wait_for(queue.put(event), timeout=timeout)
                else:
                    await queue.put(event)
                stats["queued_count"] += 1
                stats["high_watermark"] = max(stats["high_watermark"], queue.qsize())
                return True
            except asyncio.TimeoutError:
                stats["dropped_count"] += 1
                logger.warning(f"[EventBus] Timeout waiting to put event into full queue '{queue_name}'.")
                return False

        elif backpressure_mode == "raise":
            queue.put_nowait(event)
            stats["queued_count"] += 1
            stats["high_watermark"] = max(stats["high_watermark"], queue.qsize())
            return True

        else:
            raise ValueError(f"Unknown backpressure_mode: '{backpressure_mode}'")


    def start_queue_worker(self, queue_name: str = "default") -> asyncio.Task:
        """Start a background worker task that consumes from queue and publishes to subscribers."""
        self._running = True  # Ensure running flag is active even if stop_workers was previously called

        if queue_name in self._worker_tasks and not self._worker_tasks[queue_name].done():
            return self._worker_tasks[queue_name]

        queue = self.get_or_create_queue(queue_name)

        async def _worker():
            logger.info(f"[EventBus] Queue worker started for '{queue_name}'")
            while self._running:
                try:
                    event = await queue.get()
                    await self.publish(event)
                    queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[EventBus] Worker error in '{queue_name}': {e}")
            logger.info(f"[EventBus] Queue worker stopped for '{queue_name}'")

        loop = asyncio.get_running_loop()
        task = loop.create_task(_worker(), name=f"event_bus_worker_{queue_name}")
        self._worker_tasks[queue_name] = task
        return task

    def stop_workers(self) -> None:
        """Stop all background queue worker tasks."""
        self._running = False
        for name, task in list(self._worker_tasks.items()):
            if not task.done():
                task.cancel()
        self._worker_tasks.clear()

    # --------------------------------------------------------------------------
    # Lifecycle & Cleanup
    # --------------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all subscribers, queues, and worker tasks (useful for testing)."""
        self.stop_workers()
        self._subscribers.clear()
        self._queues.clear()
        self._running = True

    # --------------------------------------------------------------------------
    # Class-Level Convenience Proxies
    # --------------------------------------------------------------------------

    @classmethod
    def get_default_bus(cls) -> "EventBus":
        """Get or initialize singleton default EventBus instance."""
        if cls._default_instance is None:
            cls._default_instance = EventBus()
        return cls._default_instance

    @classmethod
    def subscribe_default(
        cls,
        event_type: Type[E],
        handler: Callable[[E], Union[Coroutine[Any, Any, None], Any]],
        priority: int = 0,
    ) -> Callable[[E], Union[Coroutine[Any, Any, None], Any]]:
        return cls.get_default_bus().subscribe(event_type, handler, priority=priority)

    @classmethod
    def unsubscribe_default(
        cls,
        event_type: Type[E],
        handler: Callable[[E], Union[Coroutine[Any, Any, None], Any]],
    ) -> bool:
        return cls.get_default_bus().unsubscribe(event_type, handler)

    @classmethod
    async def publish_default(cls, event: AppEvent) -> List[Any]:
        return await cls.get_default_bus().publish(event)


def get_event_bus() -> EventBus:
    """Retrieve global default EventBus instance."""
    return EventBus.get_default_bus()


def reset_event_bus() -> EventBus:
    """Reset and clear global default EventBus instance."""
    bus = EventBus.get_default_bus()
    bus.clear()
    EventBus._default_instance = EventBus()
    return EventBus._default_instance


class ServicePredicate:
    """
    Service availability registry and predicate checker (Phase 5).
    Provides Service.check() mechanism for conditional dispatch and graceful degradation.
    """
    _predicates: Dict[str, Callable[[], bool]] = {}

    @classmethod
    def register(cls, service_name: str, check_fn: Callable[[], bool]) -> None:
        """Register an availability predicate for a service name."""
        cls._predicates[service_name.lower().strip()] = check_fn

    @classmethod
    def check(cls, service_name: str) -> bool:
        """Evaluate availability predicate for a service. Defaults to True if unconstrained."""
        fn = cls._predicates.get(service_name.lower().strip())
        if fn is None:
            return True
        try:
            return bool(fn())
        except Exception as e:
            logger.debug(f"[ServicePredicate] Check failed for {service_name}: {e}")
            return False

    @classmethod
    def check_all(cls) -> Dict[str, bool]:
        """Return status mapping for all registered service predicates."""
        return {name: cls.check(name) for name in cls._predicates}

    @classmethod
    def reset(cls) -> None:
        """Reset registered predicates."""
        cls._predicates.clear()
