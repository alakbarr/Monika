"""
Composite Tools — Multi-tool execution in a single call.
Reduces tool round-trips from 14 to 5, and shrinks schema footprint.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.CompositeTools")


COMPOSITE_BUNDLE_SUBTOOLS_MAP: dict[str, tuple[str, ...]] = {
    "get_macro_rates": (
        "get_interest_rates",
        "get_treasury_yields",
        "get_bond_yield_spreads",
        "get_central_bank_expectations",
        "get_fedwatch_probabilities",
        "get_dxy",
    ),
    "get_macro_sentiment": (
        "get_vix",
        "get_volatility_regime",
        "get_market_correlations",
        "get_precomputed_cot_signals",
        "get_retail_sentiment",
        "get_fear_greed_index",
    ),
    "get_macro_events": (
        "get_economic_calendar",
        "get_news_digest",
        "get_news_items",
        "get_treasury_auction_results",
    ),
    "get_crypto_context": (
        "get_funding_rate",
        "get_fear_greed_index",
        "get_price_history",
        "get_technical_indicators",
    ),
    "get_portfolio_state": (
        "get_account_info",
        "get_open_positions",
        "get_pending_orders",
        "get_risk_state",
        "get_market_session",
    ),
    "get_market_context": (
        "get_market_session",
        "get_dxy",
        "get_vix",
        "get_fundamental_brief",
        "get_open_positions",
        "get_risk_state",
        "get_market_quote",
        "get_spread_snapshot",
    ),
    "get_technical_analysis": (
        "get_technical_indicators",
        "get_structure_breaks",
        "get_swing_points",
        "get_smc_zones",
        "get_fibonacci_levels",
    ),
    "get_price_data": (
        "get_price_history",
        "get_atr",
        "get_optimal_intraday_levels",
        "get_daily_range_context",
        "get_volatility_regime",
        "get_volume_profile_context",
        "get_liquidity_sweep_context",
        "get_smc_zones",
        "get_structure_breaks",
        "get_swing_points",
    ),
    "get_institutional_data": (
        "get_precomputed_cot_signals",
        "get_cot_report",
        "get_fear_greed_index",
        "get_funding_rate",
        "get_retail_sentiment",
        "get_economic_calendar",
        "get_news_items",
        "get_market_correlations",
    ),
}

COMPOSITE_BUNDLE_TOOLS: frozenset[str] = frozenset(COMPOSITE_BUNDLE_SUBTOOLS_MAP.keys())


def _record_bundle_tools(executor: Any, bundle_name: str) -> None:
    """Records the bundle tool and its constituent sub-tools into executor.called_tools."""
    if executor is None:
        return
    called = getattr(executor, "called_tools", None)
    if isinstance(called, set):
        called.add(bundle_name)
        subtools = COMPOSITE_BUNDLE_SUBTOOLS_MAP.get(bundle_name, ())
        called.update(subtools)


async def _run_tasks_gather(tasks: Dict[str, Any]) -> Dict[str, Any]:
    """Sequential execution inside current task to avoid SQLAlchemy AsyncSession lock deadlocks."""
    results = {}
    for key, coro in tasks.items():
        try:
            results[key] = await coro
        except Exception as e:
            logger.debug(f"Composite item {key} error: {e}")
            results[key] = {"error": str(e)}
    return results


async def execute_macro_rates(executor, currencies: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """
    Executes macro rates suite:
    - official interest rates
    - US treasury yields (2Y, 5Y, 10Y, 30Y)
    - bond yield spreads (US-DE, US-UK, US-JP, US-AU)
    - central bank rate hike/cut expectations
    - FedWatch probabilities
    - US dollar index (DXY)
    """
    tasks = {
        "interest_rates": executor.execute("get_interest_rates", {}),
        "treasury_yields": executor.execute("get_treasury_yields", {"days_back": 5}),
        "bond_yield_spreads": executor.execute("get_bond_yield_spreads", {"days_back": 10}),
        "central_bank_expectations": executor.execute("get_central_bank_expectations", {}),
        "fedwatch_probabilities": executor.execute("get_fedwatch_probabilities", {"limit": 3}),
        "dxy": executor.execute("get_dxy", {"days_back": 5}),
    }
    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_macro_rates")
    return res


async def execute_macro_sentiment(executor, symbols: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """
    Executes macro market sentiment suite:
    - VIX volatility index
    - Volatility regime
    - Cross-asset correlations
    - Precomputed COT institutional positioning signals
    - Retail sentiment
    - Crypto Fear & Greed index
    """
    syms = symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    primary_sym = syms[0] if syms else "EURUSD"
    tasks = {
        "vix": executor.execute("get_vix", {"days_back": 10}),
        "volatility_regime": executor.execute("get_volatility_regime", {"symbol": primary_sym}),
        "market_correlations": executor.execute("get_market_correlations", {"symbols": syms}),
        "cot_signals": executor.execute("get_precomputed_cot_signals", {}),
        "retail_sentiment": executor.execute("get_retail_sentiment", {"symbol": primary_sym}),
        "fear_greed": executor.execute("get_fear_greed_index", {}),
    }
    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_macro_sentiment")
    return res


async def execute_macro_events(executor, days_ahead: int = 3, hours_back: int = 24, **kwargs) -> Dict[str, Any]:
    """
    Executes macro events & news catalyst suite:
    - Economic calendar (high and medium impact)
    - News digest narrative summary
    - Raw news items / breaking news
    - Treasury auction results
    """
    tasks = {
        "economic_calendar": executor.execute(
            "get_economic_calendar",
            {
                "impact_filter": "high_and_medium",
                "hours_ahead": max(int(days_ahead or 3) * 24, 48),
                "hours_behind": int(hours_back or 24),
            },
        ),
        "news_digest": executor.execute("get_news_digest", {"hours_back": int(hours_back or 24)}),
        "news_items": executor.execute("get_news_items", {"hours_back": int(hours_back or 24), "limit": 20}),
        "treasury_auctions": executor.execute("get_treasury_auction_results", {"tenor": "10Y", "limit": 3}),
    }
    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_macro_events")
    return res


async def execute_crypto_context(executor, symbols: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """
    Executes crypto derivatives and sentiment suite:
    - BTC perpetual funding rate
    - Fear & Greed Index
    - BTCUSD H4 price history
    - BTCUSD H4 technical indicators
    """
    syms = symbols or ["BTCUSD"]
    target_sym = syms[0] if syms else "BTCUSD"
    tasks = {
        "funding_rate": executor.execute("get_funding_rate", {}),
        "fear_greed": executor.execute("get_fear_greed_index", {}),
        "price_history": executor.execute(
            "get_price_history", {"symbol": target_sym, "timeframe": "H4", "count": 20, "limit": 20}
        ),
        "technical_indicators": executor.execute("get_technical_indicators", {"symbol": target_sym, "timeframe": "H4"}),
    }
    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_crypto_context")
    return res


async def execute_portfolio_state(executor, symbol: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Executes portfolio and operator account state suite:
    - Account summary (balance, equity, margin, free margin)
    - Open positions
    - Pending orders
    - Risk state & drawdown budget
    - Current market trading session status
    """
    tasks = {
        "account_info": executor.execute("get_account_info", {}),
        "open_positions": executor.execute("get_open_positions", {}),
        "pending_orders": executor.execute("get_pending_orders", {}),
        "risk_state": executor.execute("get_risk_state", {}),
        "market_session": executor.execute("get_market_session", {}),
    }
    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_portfolio_state")
    return res


async def execute_market_context(executor, symbol: str, **kwargs) -> Dict[str, Any]:
    """
    Executes: market_session, DXY, VIX, fundamental_brief, open_positions, risk_state,
    market quote, and spread snapshot.
    """
    tasks = {
        "market_session": executor.execute("get_market_session", {}),
        "dxy": executor.execute("get_dxy", {"days_back": 5}),
        "vix": executor.execute("get_vix", {"days_back": 5}),
        "fundamental_brief": executor.execute("get_fundamental_brief", {}),
        "open_positions": executor.execute("get_open_positions", {}),
        "risk_state": executor.execute("get_risk_state", {}),
        "market_quote": executor.execute("get_market_quote", {"symbol": symbol}),
        "spread_snapshot": executor.execute("get_spread_snapshot", {"symbols": [symbol] if symbol else []}),
    }
    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_market_context")
    return res


async def execute_technical_analysis(
    executor, symbol: str, timeframes: Optional[List[str]] = None, **kwargs
) -> Dict[str, Any]:
    """
    Multi-timeframe technical analysis in a single call.
    Returns: indicators + structure_breaks + swing_points + smc_zones per timeframe.
    """
    if not timeframes:
        timeframes = ["D1", "H4"]

    results = {}
    for tf in timeframes:
        tf_tasks = {
            "technical_indicators": executor.execute("get_technical_indicators", {"symbol": symbol, "timeframe": tf}),
            "structure_breaks": executor.execute("get_structure_breaks", {"symbol": symbol, "timeframe": tf}),
            "swing_points": executor.execute("get_swing_points", {"symbol": symbol, "timeframe": tf, "limit": 6}),
        }
        if tf == "H4":
            tf_tasks["smc_zones"] = executor.execute("get_smc_zones", {"symbol": symbol, "timeframe": "H4"})
            tf_tasks["fibonacci_levels"] = executor.execute(
                "get_fibonacci_levels", {"symbol": symbol, "timeframe": "H4"}
            )

        results[tf] = await _run_tasks_gather(tf_tasks)

    _record_bundle_tools(executor, "get_technical_analysis")
    return results


async def execute_price_data(
    executor, symbol: str, direction: Optional[str] = None, entry_price: Optional[float] = None, **kwargs
) -> Dict[str, Any]:
    """
    Fetches price history (OHLCV), ATR, optimal intraday structural levels,
    SMC zones, structure breaks, swing points, and daily range context.
    """
    tasks = {
        "price_history": executor.execute(
            "get_price_history", {"symbol": symbol, "timeframe": "H4", "count": 30, "limit": 30}
        ),
        "atr": executor.execute("get_atr", {"symbol": symbol, "timeframe": "H4"}),
        "daily_range": executor.execute("get_daily_range_context", {"symbol": symbol}),
        "volatility_regime": executor.execute("get_volatility_regime", {"symbol": symbol}),
        "volume_profile": executor.execute("get_volume_profile_context", {"symbol": symbol}),
        "liquidity_sweep": executor.execute("get_liquidity_sweep_context", {"symbol": symbol}),
        "smc_zones": executor.execute("get_smc_zones", {"symbol": symbol, "timeframe": "H4"}),
        "structure_breaks": executor.execute("get_structure_breaks", {"symbol": symbol, "timeframe": "H4"}),
        "swing_points": executor.execute("get_swing_points", {"symbol": symbol, "timeframe": "H4", "limit": 6}),
    }
    if direction and entry_price:
        tasks["optimal_levels"] = executor.execute(
            "get_optimal_intraday_levels", {"symbol": symbol, "direction": direction, "entry_price": entry_price}
        )

    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_price_data")
    return res


async def execute_institutional_data(executor, symbol: str, cot_code: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """
    Fetches COT report and sentiment indicators (retail/crypto/oil),
    plus pair-filtered economic calendar and news items.
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

    # Pair-filtered calendar, news, and correlations
    curr_filter = f"{symbol[:3]},{symbol[3:]}" if len(symbol) == 6 else symbol
    tasks["economic_calendar"] = executor.execute(
        "get_economic_calendar",
        {"impact_filter": "high_and_medium", "currency_filter": curr_filter, "hours_ahead": 48},
    )
    tasks["news_items"] = executor.execute(
        "get_news_items",
        {"currency_filter": curr_filter, "hours_back": 24, "limit": 10},
    )
    tasks["market_correlations"] = executor.execute("get_market_correlations", {"symbols": [symbol]})

    res = await _run_tasks_gather(tasks)
    _record_bundle_tools(executor, "get_institutional_data")
    return res
