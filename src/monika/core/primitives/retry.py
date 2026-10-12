"""
Retry decorator with exponential backoff and jitter for transient failures.
Supports both asynchronous and synchronous function execution.
"""

import asyncio
import functools
import inspect
import logging
import random
import time
from typing import Any, Callable, Optional, Sequence, Tuple, Type, TypeVar, Union

logger = logging.getLogger("TradingAgent.Utils.Retry")

F = TypeVar("F", bound=Callable[..., Any])


def _calculate_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    backoff_factor: float,
    jitter: bool,
) -> float:
    """Calculate exponential backoff delay with optional jitter."""
    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
    if delay <= 0:
        return 0.0
    if jitter:
        # Jitter between 75% and 100% of calculated delay
        delay = delay * (1.0 - random.random() * 0.25)
    return max(0.0, delay)


def retryable(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = (Exception,),
    logger_instance: Optional[logging.Logger] = None,
    on_retry_callback: Optional[Callable[[BaseException, int, float], None]] = None,
) -> Callable[[F], F]:
    """
    Decorator for retrying functions on transient failures with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts before re-raising exception.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay ceiling in seconds.
        backoff_factor: Multiplier applied per attempt (default 2.0).
        jitter: If True, adds random jitter to prevent thundering herd.
        retryable_exceptions: Exception type or tuple of types to catch and retry.
        logger_instance: Custom logger instance (defaults to module logger).
        on_retry_callback: Optional callback invoked on retry (exception, attempt, delay).
    """
    log = logger_instance or logger

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Optional[BaseException] = None
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        last_exc = exc
                        if attempt >= max_retries:
                            log.error(
                                f"[Retry] Max retries ({max_retries}) exhausted for async function '{func.__name__}': {exc}"
                            )
                            raise
                        delay = _calculate_delay(attempt, base_delay, max_delay, backoff_factor, jitter)
                        log.warning(
                            f"[Retry] Transient error in async '{func.__name__}' (attempt {attempt + 1}/{max_retries}): {exc}. Retrying in {delay:.2f}s..."
                        )
                        if on_retry_callback is not None:
                            try:
                                on_retry_callback(exc, attempt + 1, delay)
                            except Exception as cb_err:
                                log.debug(f"[Retry] Callback error: {cb_err}")
                        await asyncio.sleep(delay)
                if last_exc is not None:
                    raise last_exc

            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Optional[BaseException] = None
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except retryable_exceptions as exc:
                        last_exc = exc
                        if attempt >= max_retries:
                            log.error(
                                f"[Retry] Max retries ({max_retries}) exhausted for sync function '{func.__name__}': {exc}"
                            )
                            raise
                        delay = _calculate_delay(attempt, base_delay, max_delay, backoff_factor, jitter)
                        log.warning(
                            f"[Retry] Transient error in sync '{func.__name__}' (attempt {attempt + 1}/{max_retries}): {exc}. Retrying in {delay:.2f}s..."
                        )
                        if on_retry_callback is not None:
                            try:
                                on_retry_callback(exc, attempt + 1, delay)
                            except Exception as cb_err:
                                log.debug(f"[Retry] Callback error: {cb_err}")
                        time.sleep(delay)
                if last_exc is not None:
                    raise last_exc

            return sync_wrapper  # type: ignore[return-value]

    return decorator
