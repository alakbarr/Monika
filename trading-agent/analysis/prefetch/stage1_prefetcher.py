import logging
import asyncio
import json
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from analysis.tools.tool_executor import ToolExecutor
from utils.llm.caveman_compressor import compress_tool_payload

logger = logging.getLogger("TradingAgent.Stage1Prefetcher")

PREFETCH_KEY_TO_TOOL: dict[str, str] = {
    'economic_calendar': 'get_economic_calendar',
    'news_digest': 'get_news_digest',
    'dxy': 'get_dxy',
    'treasury_yields': 'get_treasury_yields',
    'interest_rates': 'get_interest_rates',
    'fedwatch': 'get_fedwatch_probabilities',
    'vix': 'get_vix',
    'fear_greed': 'get_fear_greed_index',
    'cot_signals': 'get_precomputed_cot_signals',
    'surprise_summary': 'get_surprise_summary',
    'eurusd_momentum': 'get_price_momentum',
    'market_session': 'get_market_session',
    'funding_rate': 'get_funding_rate',
}

class Stage1DataBundler:
    def __init__(self, session: AsyncSession, settings: dict):
        self.session = session
        self.settings = settings
        self.executor = ToolExecutor(session, settings)

    async def prefetch_all_data(self) -> tuple[str, set[str], Dict[str, Any]]:
        """
        Executes standard Stage 1 tools asynchronously and returns:
        - compressed_json_str: JSON string for LLM prompt
        - satisfied_tools: set of tool names satisfied via prefetch
        - bundled_data: raw dict of all executed tool responses
        """
        logger.info("Prefetching standard Stage 1 data in parallel...")
        
        tasks = {
            "economic_calendar": self.executor.execute("get_economic_calendar", {"hours_ahead": 48, "hours_behind": 24}),
            "news_digest": self.executor.execute("get_news_digest", {"hours_back": 12}),
            "dxy": self.executor.execute("get_dxy", {}),
            "treasury_yields": self.executor.execute("get_treasury_yields", {"days_back": 5}),
            "interest_rates": self.executor.execute("get_interest_rates", {}),
            "fedwatch": self.executor.execute("get_fedwatch_probabilities", {}),
            "vix": self.executor.execute("get_vix", {}),
            "fear_greed": self.executor.execute("get_fear_greed_index", {}),
            "cot_signals": self.executor.execute("get_precomputed_cot_signals", {}),
            "surprise_summary": self.executor.execute("get_surprise_summary", {}),
            "eurusd_momentum": self.executor.execute("get_price_momentum", {"symbol": "EURUSD", "timeframe": "H4", "period": 20}),
            "market_session": self.executor.execute("get_market_session", {}),
            "funding_rate": self.executor.execute("get_funding_rate", {})
        }

        # Execute tasks sequentially to prevent AsyncSession concurrency issues
        bundled_data = {}
        for key, coro in tasks.items():
            try:
                bundled_data[key] = await coro
            except Exception as e:
                logger.error(f"Prefetch error for {key}: {e}")
                bundled_data[key] = {"error": str(e)}

        # Compute Real Yield Context for XAUUSD & Dollar Macro Grounding
        try:
            yields_info = bundled_data.get("treasury_yields", {})
            nom_10y = None
            if isinstance(yields_info, dict):
                by_t = yields_info.get("yields_by_tenor", {})
                if isinstance(by_t, dict) and "10Y" in by_t and by_t["10Y"]:
                    nom_10y = by_t["10Y"][0].get("yield_pct")
                elif "us10y" in yields_info:
                    nom_10y = yields_info.get("us10y")

            if nom_10y is not None:
                nom_10y = float(nom_10y)
                est_breakeven = 2.25
                real_10y = round(nom_10y - est_breakeven, 2)
                gold_bias = "BEARISH_HEADWIND" if real_10y > 2.0 else ("BULLISH_TAILWIND" if real_10y < 1.0 else "NEUTRAL_RANGE")
                bundled_data["real_yield_context"] = {
                    "nominal_us10y_pct": nom_10y,
                    "estimated_breakeven_inflation_pct": est_breakeven,
                    "real_us10y_yield_pct": real_10y,
                    "gold_macro_bias": gold_bias,
                    "interpretation": f"Real 10Y Yield at {real_10y}%. Real yields > 2.0% create strong headwind for Gold (XAUUSD); < 1.0% provides fuel for Gold breakout."
                }
        except Exception as e:
            logger.debug(f"Real yield precomputation non-fatal error: {e}")
                
        # Validate macro & market data freshness
        try:
            from utils.validation.data_validator import validate_data_freshness
            symbols = (
                self.settings.get("trading", {}).get("asset_universe")
                or self.settings.get("trading", {}).get("symbols")
                or ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XTIUSD", "BTCUSD", "XBRUSD"]
            )
            freshness = await validate_data_freshness(self.session, symbols, ["H1", "H4", "D1"])
            bundled_data["data_freshness_status"] = freshness
            if not freshness.get("ready"):
                notices = (freshness.get('errors') or []) + (freshness.get('warnings') or [])
                logger.warning(f"Stage 1 data freshness validation notices: {notices}")
        except Exception as e:
            logger.debug(f"Data freshness prefetch check non-fatal error: {e}")

        # Update DataFeedCircuitBreaker heartbeats and evaluate critical feeds
        try:
            from data_sources.circuit_breaker import get_data_feed_circuit_breaker
            breaker = get_data_feed_circuit_breaker()
            if "error" not in bundled_data.get("economic_calendar", {}):
                breaker.record_feed_heartbeat("economic_calendar")
            if "error" not in bundled_data.get("treasury_yields", {}):
                breaker.record_feed_heartbeat("fred")
            if "error" not in bundled_data.get("news_digest", {}):
                breaker.record_feed_heartbeat("finnhub")

            eval_res = breaker.evaluate_all_feeds(auto_trip=False)
            bundled_data["circuit_breaker_status"] = eval_res
            if breaker.is_tripped():
                logger.warning(f"[Stage1DataBundler] Data feed circuit breaker is TRIPPED: {breaker.get_tripped_feeds()}")
        except Exception as cb_err:
            logger.debug(f"Circuit breaker prefetch check non-fatal error: {cb_err}")

        # Direct in-memory computation of satisfied tools
        satisfied_tools = set()
        for key in bundled_data:
            tool_name = PREFETCH_KEY_TO_TOOL.get(key)
            if tool_name:
                satisfied_tools.add(tool_name)

        logger.info(f"Prefetch complete ({len(satisfied_tools)} tools satisfied). Compressing output for LLM context.")
        compressed_json = self._compress_json(bundled_data)
        return compressed_json, satisfied_tools, bundled_data

    def _compress_json(self, data: Dict[str, Any]) -> str:
        """Compress data to save tokens using caveman logic and context compressor."""
        compressed = compress_tool_payload(data)
        if isinstance(compressed, (str, dict)):
            try:
                from utils.llm.prompt_compressor import ContextCompressor
                compressor = ContextCompressor(self.settings)
                return compressor.compress_stage1_bundle(compressed, max_tokens=6000)
            except Exception:
                pass
        return json.dumps(compressed, default=str)
