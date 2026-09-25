"""
Composite Tools — Multi-tool execution in a single call.
Reduces tool round-trips from 14 to 5, and shrinks schema footprint.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TradingAgent.CompositeTools")


async def _run_tasks_gather(tasks: Dict[str, Any]) -> Dict[str, Any]:
    keys = list(tasks.keys())
    raw_res = await asyncio.gather(*tasks.values(), return_exceptions=True)
    results = {}
    for key, res in zip(keys, raw_res):
        if isinstance(res, Exception):
            logger.debug(f"Composite item {key} error: {res}")
            results[key] = {"error": str(res)}
        else:
            results[key] = res
    return results


async def execute_market_context(executor, symbol: str) -> Dict[str, Any]:
    """
    Executes: market_session, DXY, VIX, fundamental_brief, open_positions, risk_state.
    """
    tasks = {
        "market_session": executor.execute("get_market_session", {}),
        "dxy": executor.execute("get_dxy", {"days_back": 5}),
        "vix": executor.execute("get_vix", {"days_back": 5}),
        "fundamental_brief": executor.execute("get_fundamental_brief", {}),
        "open_positions": executor.execute("get_open_positions", {}),
        "risk_state": executor.execute("get_risk_state", {}),
    }
    return await _run_tasks_gather(tasks)


async def execute_technical_analysis(executor, symbol: str, timeframes: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Multi-timeframe technical analysis in a single call.
    Returns: indicators + structure_breaks + swing_points + smc_zones per timeframe.
    """
    if not timeframes:
        timeframes = ["D1", "H4"]
        
    results = {}
    for tf in timeframes:
        tf_data = {}
        tf_tasks = {
            "technical_indicators": executor.execute("get_technical_indicators", {"symbol": symbol, "timeframe": tf}),
            "structure_breaks": executor.execute("get_structure_breaks", {"symbol": symbol, "timeframe": tf}),
            "swing_points": executor.execute("get_swing_points", {"symbol": symbol, "timeframe": tf, "limit": 6}),
        }
        if tf == "H4":
            tf_tasks["smc_zones"] = executor.execute("get_smc_zones", {"symbol": symbol, "timeframe": "H4"})
            tf_tasks["fibonacci_levels"] = executor.execute("get_fibonacci_levels", {"symbol": symbol, "timeframe": "H4"})

        results[tf] = await _run_tasks_gather(tf_tasks)
        
    return results


async def execute_price_data(executor, symbol: str, direction: Optional[str] = None, entry_price: Optional[float] = None) -> Dict[str, Any]:
    """
    Fetches price history (OHLCV), ATR, and optimal intraday structural levels.
    """
    tasks = {
        "price_history": executor.execute("get_price_history", {"symbol": symbol, "timeframe": "H4", "limit": 30}),
        "atr": executor.execute("get_atr", {"symbol": symbol, "timeframe": "H4"}),
    }
    if direction and entry_price:
        tasks["optimal_levels"] = executor.execute(
            "get_optimal_intraday_levels",
            {"symbol": symbol, "direction": direction, "entry_price": entry_price}
        )

    return await _run_tasks_gather(tasks)


async def execute_institutional_data(executor, symbol: str, cot_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches COT report and sentiment indicators (retail/crypto/oil).
    """
    tasks = {
        "cot_signals": executor.execute("get_precomputed_cot_signals", {}),
    }
    if cot_code:
        tasks["cot_report"] = executor.execute("get_cot_report", {"market_codes": [cot_code]})
        
    if symbol == "BTCUSD":
        tasks["fear_greed"] = executor.execute("get_fear_greed_index", {})
        tasks["funding_rate"] = executor.execute("get_funding_rate", {})
    elif symbol in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY"):
        tasks["retail_sentiment"] = executor.execute("get_retail_sentiment", {"symbol": symbol})

    return await _run_tasks_gather(tasks)
