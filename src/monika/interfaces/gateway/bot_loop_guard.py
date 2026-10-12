# ==============================================================================
# File: gateway/bot_loop_guard.py
# ==============================================================================

"""
Omnichannel Bot Ping-Pong Loop Guard & Message Echo Breaker.
Prevents infinite feedback loops between Monika and automated bots,
webhook responders, or echoed channel messages.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger("TradingAgent.Gateway.BotLoopGuard")

MAX_MESSAGES_WINDOW = 5
WINDOW_SECONDS = 4.0
SIMILARITY_THRESHOLD = 0.85


@dataclass
class MessageFingerprint:
    hash_str: str
    timestamp: float
    text_preview: str


class BotLoopGuard:
    """
    Monitors incoming message cadence and similarity to detect and break infinite bot loops.
    """

    def __init__(
        self,
        window_seconds: float = WINDOW_SECONDS,
        max_messages: int = MAX_MESSAGES_WINDOW,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ):
        self.window_seconds = window_seconds
        self.max_messages = max_messages
        self.similarity_threshold = similarity_threshold
        # Key: "platform:chat_id" -> Deque of MessageFingerprint
        self._history: Dict[str, Deque[MessageFingerprint]] = {}

    def check_and_record(
        self,
        platform: str,
        chat_id: str,
        sender_id: str,
        text: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether an incoming message is part of an automated loop.
        Returns (is_allowed, block_reason).
        """
        if not text or not text.strip():
            return True, None

        key = f"{platform.lower()}:{chat_id}"
        now = time.time()
        text_clean = text.strip().lower()
        msg_hash = hashlib.md5(text_clean.encode("utf-8")).hexdigest()

        if key not in self._history:
            self._history[key] = deque(maxlen=self.max_messages * 2)

        history = self._history[key]

        # 1. Clean entries older than window
        while history and (now - history[0].timestamp) > self.window_seconds:
            history.popleft()

        # 2. Check for rapid repeated identical messages
        identical_count = sum(1 for item in history if item.hash_str == msg_hash)
        if identical_count >= 2:
            reason = f"Bot loop detected: {identical_count + 1} identical messages within {self.window_seconds}s."
            logger.warning(f"[BotLoopGuard] Blocked message from '{sender_id}' on '{key}': {reason}")
            return False, reason

        # 3. Check for high message burst velocity with high similarity
        if len(history) >= self.max_messages:
            similar_count = 0
            for item in history:
                ratio = difflib.SequenceMatcher(None, text_clean, item.text_preview).ratio()
                if ratio >= self.similarity_threshold:
                    similar_count += 1

            if similar_count >= 3:
                reason = f"Bot ping-pong storm detected: {similar_count} highly similar messages in {self.window_seconds}s."
                logger.warning(f"[BotLoopGuard] Blocked message from '{sender_id}' on '{key}': {reason}")
                return False, reason

        # 4. Check for automated echo headers
        lower_raw = text.lower()
        if "[monika_echo]" in lower_raw or "x-bot-loop-prevent: true" in lower_raw:
            return False, "Bot echo header detected in message body."

        # Record message
        history.append(
            MessageFingerprint(
                hash_str=msg_hash,
                timestamp=now,
                text_preview=text_clean[:120],
            )
        )
        return True, None
