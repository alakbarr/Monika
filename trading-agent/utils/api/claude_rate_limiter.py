import asyncio
import time
import logging
from typing import ClassVar

logger = logging.getLogger('TradingAgent.ClaudeRateLimiter')

class ClaudeRateLimiter:
    """Simple sliding window rate limiter for Claude API calls."""
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _call_times: ClassVar[list] = []
    
    # Conservative limits: 50 calls/minute max (Sonnet tier has higher limits)
    MAX_CALLS_PER_MINUTE: ClassVar[int] = 50
    MAX_TOKENS_PER_MINUTE: ClassVar[int] = 100_000
    MIN_DELAY_BETWEEN_SESSIONS: ClassVar[float] = 2.0  # seconds between new sessions
    _last_session_start: ClassVar[float] = 0.0
    _token_history: ClassVar[list] = []
    
    @classmethod
    async def acquire_session_slot(cls, model_name: str = '', estimated_tokens: int = 0) -> None:
        """Wait until it's safe to start a new Claude session (checks RPM and TPM)."""
        async with cls._lock:
            now = time.time()
            
            # Clean old entries (> 60 seconds)
            cls._call_times = [t for t in cls._call_times if now - t < 60]
            cls._token_history = [item for item in cls._token_history if now - item[0] < 60]
            
            # Check if we're at RPM limit
            if len(cls._call_times) >= cls.MAX_CALLS_PER_MINUTE:
                oldest = cls._call_times[0]
                wait_time = 60 - (now - oldest) + 0.1
                if wait_time > 0:
                    logger.warning(f'Claude RPM rate limit: waiting {wait_time:.1f}s')
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    cls._call_times = [t for t in cls._call_times if now - t < 60]
                    cls._token_history = [item for item in cls._token_history if now - item[0] < 60]

            # Check if we're at TPM limit
            if estimated_tokens > 0:
                current_tokens = sum(tokens for _, tokens in cls._token_history)
                if current_tokens + estimated_tokens > cls.MAX_TOKENS_PER_MINUTE:
                    oldest_item = cls._token_history[0] if cls._token_history else (now, 0)
                    wait_time = 60 - (now - oldest_item[0]) + 0.1
                    if wait_time > 0:
                        logger.warning(f'Claude TPM rate limit ({current_tokens} + {estimated_tokens} > {cls.MAX_TOKENS_PER_MINUTE}): waiting {wait_time:.1f}s')
                        await asyncio.sleep(wait_time)
                        now = time.time()
                        cls._call_times = [t for t in cls._call_times if now - t < 60]
                        cls._token_history = [item for item in cls._token_history if now - item[0] < 60]
            
            # Enforce minimum delay between sessions
            time_since_last = now - cls._last_session_start
            if time_since_last < cls.MIN_DELAY_BETWEEN_SESSIONS:
                wait = cls.MIN_DELAY_BETWEEN_SESSIONS - time_since_last
                await asyncio.sleep(wait)
            
            ts = time.time()
            cls._call_times.append(ts)
            if estimated_tokens > 0:
                cls._token_history.append((ts, estimated_tokens))
            cls._last_session_start = ts
    
    @classmethod
    def get_current_rpm(cls) -> int:
        now = time.time()
        return len([t for t in cls._call_times if now - t < 60])

    @classmethod
    def get_current_tpm(cls) -> int:
        now = time.time()
        return sum(tokens for t, tokens in cls._token_history if now - t < 60)
