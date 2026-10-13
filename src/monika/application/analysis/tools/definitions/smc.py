# ==============================================================================
# File: application/analysis/tools/definitions/smc.py
# ==============================================================================

"""
Smart Money Concepts (SMC), FVG, Order Blocks, and Liquidity tool definitions.
"""

from __future__ import annotations

from monika.application.analysis.tools.definitions.base import _tool

GET_SWING_POINTS = _tool(
    name="get_swing_points",
    description=(
        "Fetch detected swing high and swing low points for a symbol and timeframe. "
        "Use these to identify market structure: higher highs/lows (uptrend), "
        "lower highs/lows (downtrend), or ranges."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "limit": {"type": "integer", "description": "Number of most recent swing points per type. Default: 10."},
    },
    required=["symbol", "timeframe"],
)


GET_SR_ZONES = _tool(
    name="get_sr_zones",
    description=(
        "Fetch Support & Resistance zones for a symbol and timeframe. "
        "Zones are clustered swing points with multiple touches — stronger zones have higher strength values. "
        "Use these as potential entry, target, or invalidation levels."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "min_strength": {"type": "integer", "description": "Minimum number of touches to include. Default: 2."},
    },
    required=["symbol", "timeframe"],
)


GET_LIQUIDITY_ZONES = _tool(
    name="get_liquidity_zones",
    description=(
        "Fetch liquidity zones — areas above swing highs (buy-stop clusters) and "
        "below swing lows (sell-stop clusters) where retail stop-losses are likely concentrated. "
        "In SMC/ICT analysis, price often sweeps these zones before reversing. "
        "Use to identify likely sweep targets and potential reversal zones."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
    },
    required=["symbol", "timeframe"],
)


GET_FVG_ZONES = _tool(
    name="get_fvg_zones",
    description=(
        "Fetch Fair Value Gap (FVG) zones — price imbalances where candle N-2 and candle N "
        "did not overlap (3-candle pattern). Unfilled FVGs often act as magnets for price. "
        "Bullish FVG = potential support. Bearish FVG = potential resistance."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "filled": {
            "type": "boolean",
            "description": "If false (default), only return unfilled FVGs. If true, include filled ones.",
        },
    },
    required=["symbol", "timeframe"],
)


GET_ORDER_BLOCKS = _tool(
    name="get_order_blocks",
    description=(
        "Fetch unmitigated Order Blocks (OB) for a symbol and timeframe. "
        "Order blocks are the last opposite candle before a strong impulsive move. "
        "Unmitigated OBs often act as strong support/resistance where institutional orders are placed."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "days": {"type": "integer", "description": "Maximum age of order blocks in days (default: 14)."},
        "limit": {"type": "integer", "description": "Maximum number of blocks to return (default: 10)."},
    },
    required=["symbol", "timeframe"],
)


GET_SMC_ZONES = _tool(
    name="get_smc_zones",
    description=(
        "Composite SMC/ICT analysis tool — returns Order Blocks, FVG Zones, "
        "Liquidity Zones, and S/R Zones in a single call. "
        "Use this instead of calling get_order_blocks + get_fvg_zones + "
        "get_liquidity_zones + get_sr_zones separately — saves 3 round-trips. "
        "Order Blocks: unmitigated institutional entry zones. "
        "FVG Zones: price imbalances (unfilled by default). "
        "Liquidity Zones: stop-loss clusters above highs / below lows. "
        "S/R Zones: clustered swing points with multiple touches."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["H1", "H4", "D1"]},
        "include_filled_fvg": {
            "type": "boolean",
            "description": "If true, include already-filled FVGs. Default: false.",
        },
        "min_sr_strength": {
            "type": "integer",
            "description": "Minimum touch count for S/R zones. Default: 2.",
        },
    },
    required=["symbol", "timeframe"],
)


GET_STRUCTURE_BREAKS = _tool(
    name="get_structure_breaks",
    description=(
        "Fetch recent Break of Structure (BOS) and Change of Character (ChoCH) events. "
        "BOS indicates trend continuation, while ChoCH indicates a potential trend reversal."
    ),
    properties={
        "symbol": {"type": "string"},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
    },
    required=["symbol", "timeframe"],
)


GET_INDUCEMENTS = _tool(
    name="get_inducements",
    description=(
        "Detect Inducement (IDM) price level and validation status based on SMC rules. "
        "In bullish trend, IDM is the first internal swing low after a new high. "
        "When price sweeps IDM, the high is confirmed and valid order blocks below can be safely traded."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"],
            "description": "Timeframe to evaluate (default: 'M15').",
        },
        "trend": {"type": "string", "enum": ["bullish", "bearish"], "description": "Current directional trend bias."},
    },
    required=["symbol"],
)


GET_BREAKER_BLOCKS = _tool(
    name="get_breaker_blocks",
    description=(
        "Detect Breaker Blocks: failed order blocks that were aggressively broken through with strong momentum, "
        "inverting their polarity (failed bullish OB becomes resistance; failed bearish OB becomes support)."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
    },
    required=["symbol", "timeframe"],
)


GET_INVERTED_FVG = _tool(
    name="get_inverted_fvg",
    description=(
        "Detect Inverted Fair Value Gaps (IFVG): Fair Value Gaps that were violated and closed through with displacement, "
        "inverting their institutional polarity (broken bullish FVG becomes resistance; broken bearish FVG becomes support)."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"],
            "description": "Timeframe (default: 'H1').",
        },
        "lookback": {"type": "integer", "description": "Lookback bars (default: 150)."},
    },
    required=["symbol"],
)


GET_JUDAS_SWING = _tool(
    name="get_judas_swing",
    description=(
        "Detect London Open (08:00 UTC) Judas Swing false breakout trap. "
        "Identifies false expansions that engineer liquidity above/below Asian range extremes before aggressive reversal."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol (e.g. 'GBPUSD', 'EURUSD', 'XAUUSD')."},
        "timeframe": {
            "type": "string",
            "enum": ["M1", "M5", "M15", "H1"],
            "description": "Timeframe for microstructure (default: 'M15').",
        },
    },
    required=["symbol"],
)


GET_EQUAL_HIGHS_LOWS = _tool(
    name="get_equal_highs_lows",
    description=(
        "Detect engineered liquidity pools formed by Equal Highs (EQH / Buy-Side Liquidity) "
        "or Equal Lows (EQL / Sell-Side Liquidity) within tight tolerance pips."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]},
        "tolerance_pips": {"type": "number", "description": "Price clustering tolerance in pips (default: 3.0)."},
    },
    required=["symbol", "timeframe"],
)


GET_WICK_TO_WICK_FVG = _tool(
    name="get_wick_to_wick_fvg",
    description=("Detect shadow / wick-to-wick Fair Value Gaps where long overlapping wicks form an imbalance on HTF."),
    properties={
        "symbol": {"type": "string", "description": "Trading symbol."},
        "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"]},
    },
    required=["symbol", "timeframe"],
)


GET_LIQUIDITY_SWEEP_CONTEXT = _tool(
    name="get_liquidity_sweep_context",
    description="Detects an Asian-session (00:00-08:00 UTC) liquidity sweep (wick beyond session high/low, closes back inside) confirmed by a post-sweep ChoCH/BOS, Order Block, or FVG. Only use 'liquidity_sweep_confirmed' in confluence_factors if structure_confirmed=True AND valid_for_direction matches your decision — verified server-side.",
    properties={"symbol": {"type": "string"}},
    required=["symbol"],
)


SCAN_SMC_SETUPS_TOOL = _tool(
    name="scan_smc_setups",
    description="Parallel live screener scanning all pairs for active unmitigated Order Blocks, FVGs, and Liquidity Sweeps (Q060).",
    properties={
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of symbols to screen (default: all universe).",
        },
        "timeframe": {
            "type": "string",
            "enum": ["M15", "H1", "H4", "D1"],
            "description": "Timeframe to scan (default: 'H4').",
        },
    },
    required=[],
)


__all__ = [
    "GET_SWING_POINTS",
    "GET_SR_ZONES",
    "GET_LIQUIDITY_ZONES",
    "GET_FVG_ZONES",
    "GET_ORDER_BLOCKS",
    "GET_SMC_ZONES",
    "GET_STRUCTURE_BREAKS",
    "GET_INDUCEMENTS",
    "GET_BREAKER_BLOCKS",
    "GET_INVERTED_FVG",
    "GET_JUDAS_SWING",
    "GET_EQUAL_HIGHS_LOWS",
    "GET_WICK_TO_WICK_FVG",
    "GET_LIQUIDITY_SWEEP_CONTEXT",
    "SCAN_SMC_SETUPS_TOOL",
]
