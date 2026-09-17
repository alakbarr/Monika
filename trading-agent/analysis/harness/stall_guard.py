import hashlib
import json
import logging
from collections import deque
from typing import Any, Optional, Tuple, Set

logger = logging.getLogger("TradingAgent.Harness.StallGuard")

# Set of tools considered read-only / idempotent
READ_ONLY_TOOLS: Set[str] = {
    "get_price_history", "get_technical_indicators", "get_atr",
    "get_swing_points", "get_structure_breaks", "get_smc_zones",
    "get_fibonacci_levels", "get_optimal_intraday_levels", "get_daily_range_context",
    "get_news_items", "get_news_digest", "get_retail_sentiment",
    "get_funding_rate", "get_fear_greed_index", "get_forex_sentiment",
    "get_fxssi_sentiment", "get_structured_sentiment", "get_dxy", "get_vix",
    "get_fedwatch_probabilities", "get_yield_data", "get_cot_report",
    "get_economic_calendar", "get_account_info", "get_open_positions", "get_trade_history",
    "get_active_triggers", "get_system_health", "get_paper_trading_performance",
    "get_verified_market_snapshot", "get_market_quote", "get_ohlcv", "get_rate",
    "get_tick", "get_candles", "search_tools", "describe_tool",
    "execute_analysis_code",
}

STATE_ADVANCING_TOOLS: Set[str] = {
    "submit_asset_analysis", "submit_fundamental_brief", "propose_action",
    "place_order", "modify_position", "close_position",
}


class StallGuard:
    """
    State-Aware Stall Guard (H-8).
    Monitors consecutive read-only tool loops and stalled iterations.
    Injects stall warnings when loop threshold is reached and triggers forced termination
    if agent fails to advance state after warnings.
    """

    def __init__(self, warning_threshold: int = 4, force_terminate_threshold: int = 7):
        self.warning_threshold = warning_threshold
        self.force_terminate_threshold = force_terminate_threshold
        self.consecutive_read_count = 0
        self.warning_issued = False
        self.warning_turns_count = 0
        self.seen_content_hashes: deque[str] = deque(maxlen=10)

    def is_read_only(self, tool_name: str) -> bool:
        if tool_name in STATE_ADVANCING_TOOLS:
            return False
        if tool_name in READ_ONLY_TOOLS:
            return True
        return tool_name.startswith(("get_", "read_", "query_", "fetch_", "search_", "load_"))

    def record_call(self, tool_name: str, tool_result: Any = None) -> None:
        """Record execution of a tool and update stall counters."""
        if self.is_read_only(tool_name):
            self.consecutive_read_count += 1
            if self.warning_issued:
                self.warning_turns_count += 1
        else:
            # Mutating / state-advancing tool breaks the stall
            self.reset()
            return

        # Track result hash to catch identical query loops
        if tool_result is not None:
            try:
                res_str = json.dumps(tool_result, sort_keys=True, default=str)
                h = hashlib.md5(res_str.encode("utf-8")).hexdigest()
                self.seen_content_hashes.append(h)
            except Exception:
                pass

    def check_stall(self) -> Tuple[bool, bool, Optional[str]]:
        """
        Evaluate current execution state for stall conditions.
        Returns:
            (is_stall_warning, is_force_terminate, message)
        """
        # 1. Check for identical result looping (>= 3 times exact same result)
        content_repeat_count = 0
        if self.seen_content_hashes:
            latest = self.seen_content_hashes[-1]
            content_repeat_count = self.seen_content_hashes.count(latest)

        # 2. Check for force termination condition
        if (
            self.consecutive_read_count >= self.force_terminate_threshold
            or (self.warning_issued and self.warning_turns_count >= 2)
            or content_repeat_count >= 4
        ):
            msg = (
                f"[STALL GUARD CRITICAL]: Execution stalled across {self.consecutive_read_count} "
                f"consecutive read-only tool calls without state advancement. "
                f"Halting tool execution. You MUST synthesize and output your final conclusion now."
            )
            logger.warning(f"[StallGuard] Force terminate triggered: {msg}")
            return (False, True, msg)

        # 3. Check for warning condition
        if (
            self.consecutive_read_count >= self.warning_threshold
            or content_repeat_count >= 3
        ):
            self.warning_issued = True
            msg = (
                f"[STALL GUARD WARNING]: You have executed {self.consecutive_read_count} consecutive "
                f"read-only tool calls. Do not make further redundant data requests. "
                f"Synthesize your collected findings and conclude your analysis."
            )
            logger.info(f"[StallGuard] Warning triggered: {msg}")
            return (True, False, msg)

        return (False, False, None)

    def reset(self) -> None:
        """Reset stall counters upon state-advancing actions."""
        self.consecutive_read_count = 0
        self.warning_issued = False
        self.warning_turns_count = 0
        self.seen_content_hashes.clear()
