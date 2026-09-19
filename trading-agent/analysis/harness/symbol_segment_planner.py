"""
Symbol Concurrency Segment Planner for Trading Agent Harness.
Partitions batches of tool calls into parallel and sequential execution segments
based on asset symbol conflicts to prevent race conditions on MT5 terminal bindings.
"""

from typing import List, Dict, Any, Tuple, Set
import logging

logger = logging.getLogger("TradingAgent.Harness.SymbolSegmentPlanner")


class SymbolSegmentPlanner:
    """
    Plans tool execution batches into segments:
    - Independent symbols (e.g. EURUSD vs XAUUSD vs macro news) -> parallel execution.
    - Conflicting operations on the same symbol (e.g. order mutation vs tick fetch) -> sequential execution.
    """

    # Tools that mutate account or position state on a symbol (must be serialized per symbol)
    MUTATING_TOOLS: Set[str] = {
        "execute_trade",
        "place_order",
        "modify_order",
        "close_position",
        "cancel_order",
        "submit_asset_analysis",
    }

    @staticmethod
    def extract_symbol(tool_call: Dict[str, Any]) -> str:
        """Extracts normalized uppercase asset symbol from tool call arguments, or 'GLOBAL'."""
        inp = tool_call.get("input", {})
        if isinstance(inp, dict):
            sym = inp.get("symbol") or inp.get("ticker") or inp.get("asset")
            if sym:
                return str(sym).strip().upper()
        return "GLOBAL"

    @classmethod
    def plan_segments(cls, tool_calls: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
        """
        Partitions tool calls into execution segments: ('parallel', [...]) or ('sequential', [...]).
        
        Rules:
        1. If all calls touch distinct symbols (or are read-only non-conflicting), run in parallel.
        2. If multiple calls touch the same symbol and at least one is a MUTATING_TOOL,
           separate the conflicting calls into sequential segments.
        3. Single tool calls are run as 'parallel' with size 1.
        """
        if not tool_calls:
            return []
        if len(tool_calls) == 1:
            return [("parallel", tool_calls)]

        symbol_counts: Dict[str, int] = {}
        has_mutation: Dict[str, bool] = {}

        for call in tool_calls:
            sym = cls.extract_symbol(call)
            name = call.get("name", "")
            symbol_counts[sym] = symbol_counts.get(sym, 0) + 1
            if name in cls.MUTATING_TOOLS:
                has_mutation[sym] = True

        # Check for conflict: multiple calls for same non-GLOBAL symbol where at least one mutates
        has_conflict = False
        for sym, count in symbol_counts.items():
            if sym != "GLOBAL" and count > 1 and has_mutation.get(sym, False):
                has_conflict = True
                break

        if not has_conflict:
            # No conflict: all independent
            return [("parallel", tool_calls)]

        # Partition into sequential and parallel segments
        segments: List[Tuple[str, List[Dict[str, Any]]]] = []
        seen_symbols: Set[str] = set()
        current_parallel_batch: List[Dict[str, Any]] = []

        for call in tool_calls:
            sym = cls.extract_symbol(call)
            name = call.get("name", "")
            is_mutation = name in cls.MUTATING_TOOLS

            if sym != "GLOBAL" and (sym in seen_symbols or is_mutation):
                # Flush existing parallel batch if any
                if current_parallel_batch:
                    segments.append(("parallel", current_parallel_batch))
                    current_parallel_batch = []
                # Add this conflicting call as sequential
                segments.append(("sequential", [call]))
            else:
                current_parallel_batch.append(call)
                if sym != "GLOBAL":
                    seen_symbols.add(sym)

        if current_parallel_batch:
            segments.append(("parallel", current_parallel_batch))

        return segments
