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
    'bond_yield_spreads': 'get_bond_yield_spreads',
    'central_bank_expectations': 'get_central_bank_expectations',
    'prediction_market': 'get_prediction_market_odds',
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
            "funding_rate": self.executor.execute("get_funding_rate", {}),
            "bond_yield_spreads": self.executor.execute("get_bond_yield_spreads", {}),
            "central_bank_expectations": self.executor.execute("get_central_bank_expectations", {}),
            "prediction_market": self.executor.execute("get_prediction_market_odds", {}),
        }

        # Extra parallel zero-browser real-time feeds
        async def _fetch_crypto_depth():
            from data_sources.crypto_orderbook_depth import CryptoOrderbookDepth
            snap = await CryptoOrderbookDepth.fetch_snapshot("BTCUSD")
            return {
                "exchange": snap.exchange,
                "spread_bps": snap.spread_bps,
                "imbalance_score": snap.imbalance_score,
                "bid_liq_usd": snap.bid_liquidity_usd,
                "ask_liq_usd": snap.ask_liquidity_usd,
                "slippage": snap.slippage_estimates,
            } if snap else {"error": "L2 depth unavailable"}

        async def _fetch_sovereign_spreads():
            from data_sources.sovereign_yield_spreads import SovereignYieldSpreads
            return await SovereignYieldSpreads.get_spreads()

        async def _fetch_gold_radar():
            from data_sources.gold_physical_radar import GoldPhysicalRadar
            radar = await GoldPhysicalRadar.fetch_radar()
            return {
                "flow_bias": radar.institutional_flow_bias,
                "gld_change_pct": radar.gld_1d_change_pct,
                "conviction": radar.xau_sentiment_conviction,
                "summary": radar.summary,
            }

        tasks["crypto_l2_depth"] = _fetch_crypto_depth()
        tasks["sovereign_yield_spreads"] = _fetch_sovereign_spreads()
        tasks["gold_physical_radar"] = _fetch_gold_radar()

        # Execute tasks sequentially to prevent AsyncSession concurrency issues
        bundled_data = {}
        for key, coro in tasks.items():
            try:
                bundled_data[key] = await coro
            except Exception as e:
                logger.error(f"Prefetch error for {key}: {e}")
                bundled_data[key] = {"error": str(e)}

        # CME FedWatch Repricing Correlation (Multi-Event Pre vs Post USD Economic Releases or 24h Shift)
        try:
            ec_data = bundled_data.get("economic_calendar", {})
            events_by_time = {}
            if isinstance(ec_data, dict) and isinstance(ec_data.get("events"), list):
                from datetime import datetime, timezone
                import utils.clock as clock
                now_utc = clock.now()
                usd_past_events = []
                for ev in ec_data["events"]:
                    if not isinstance(ev, dict):
                        continue
                    curr = str(ev.get("currency", "")).upper()
                    impact = str(ev.get("impact", "")).lower()
                    ev_time_str = ev.get("event_time")
                    if curr == "USD" and impact in ("high", "medium") and ev_time_str:
                        try:
                            ev_dt = datetime.fromisoformat(ev_time_str.replace("Z", "+00:00"))
                            if ev_dt.tzinfo is None:
                                ev_dt = ev_dt.replace(tzinfo=timezone.utc)
                            if ev_dt <= now_utc:
                                usd_past_events.append((ev_dt, ev))
                        except Exception:
                            continue

                if usd_past_events:
                    # Urutkan kronologis dari terlama ke terbaru agar membentuk trajektori
                    usd_past_events.sort(key=lambda x: x[0])
                    for ev_dt, ev in usd_past_events:
                        t_str = ev.get("event_time")
                        if t_str not in events_by_time:
                            events_by_time[t_str] = []
                        events_by_time[t_str].append(ev)

            import re
            def _clean(name):
                return re.sub(r"<[^>]+>", "", name or "").strip()

            all_event_shifts = []

            if events_by_time:
                # Ambil hingga 5 slot waktu rilis USD terbaru dalam 24 jam terakhir
                time_keys = list(events_by_time.keys())[-5:]
                for t_str in time_keys:
                    ev_group = events_by_time[t_str]
                    names = ", ".join([_clean(e.get("event_name")) for e in ev_group if _clean(e.get("event_name"))])
                    fw_comp = await self.executor.execute("get_fedwatch_probabilities", {"event_time": t_str})
                    if isinstance(fw_comp, dict) and fw_comp.get("comparisons"):
                        c = fw_comp["comparisons"][0]
                        all_event_shifts.append({
                            "event_time": t_str,
                            "events": names or "USD Release",
                            "meeting_date": c.get("meeting_date"),
                            "shift_summary": c.get("shift_summary"),
                            "deltas_pct": c.get("deltas_pct"),
                            "prior_probabilities": c.get("prior_probabilities"),
                            "current_probabilities": c.get("current_probabilities"),
                            "pre_snapshot_time": c.get("pre_snapshot_time"),
                            "post_snapshot_time": c.get("post_snapshot_time"),
                        })
            else:
                # Fallback: pergeseran temporal 24 jam jika tidak ada event kalender spesifik
                fw_comp = await self.executor.execute("get_fedwatch_probabilities", {"compare_hours_ago": 24})
                if isinstance(fw_comp, dict) and fw_comp.get("comparisons"):
                    c = fw_comp["comparisons"][0]
                    all_event_shifts.append({
                        "event_time": None,
                        "events": "24h Temporal Shift",
                        "meeting_date": c.get("meeting_date"),
                        "shift_summary": c.get("shift_summary"),
                        "deltas_pct": c.get("deltas_pct"),
                        "prior_probabilities": c.get("prior_probabilities"),
                        "current_probabilities": c.get("current_probabilities"),
                        "pre_snapshot_time": c.get("pre_snapshot_time"),
                        "post_snapshot_time": c.get("post_snapshot_time"),
                    })

            if all_event_shifts:
                latest_shift = all_event_shifts[-1]
                multi_summary = " | ".join([
                    f"[{s['events']}]: {s['shift_summary']}"
                    for s in all_event_shifts
                ])

                mode_str = "24h_temporal_shift"
                if events_by_time:
                    mode_str = "multi_event_pre_vs_post" if len(all_event_shifts) > 1 else "pre_vs_post_event"

                bundled_data["fedwatch_comparison"] = {
                    "mode": mode_str,
                    "total_events_tracked": len(all_event_shifts),
                    "trajectory_summary": multi_summary,
                    "referenced_event": latest_shift["events"],
                    "event_time": latest_shift["event_time"],
                    "meeting_date": latest_shift.get("meeting_date"),
                    "shift_summary": latest_shift.get("shift_summary"),
                    "deltas_pct": latest_shift.get("deltas_pct"),
                    "prior_probabilities": latest_shift.get("prior_probabilities"),
                    "current_probabilities": latest_shift.get("current_probabilities"),
                    "all_event_shifts": all_event_shifts,
                }
                existing_fw = bundled_data.get("fedwatch")
                if isinstance(existing_fw, dict) and not existing_fw.get("error"):
                    existing_fw["comparisons"] = all_event_shifts
        except Exception as e:
            logger.debug(f"FedWatch repricing correlation non-fatal error: {e}")

        # Compute Real Yield Context for XAUUSD & Dollar Macro Grounding
        try:
            yields_info = bundled_data.get("treasury_yields", {})
            nom_10y = None
            est_breakeven = None
            real_10y = None

            if isinstance(yields_info, dict):
                by_t = yields_info.get("yields_by_tenor", {})
                if isinstance(by_t, dict):
                    if "10Y" in by_t and by_t["10Y"]:
                        nom_10y = by_t["10Y"][0].get("yield_pct")
                    # Dynamic 10Y Breakeven Inflation (T10YIE / 10Y_INFLATION)
                    for k in ("10Y_INFLATION", "T10YIE"):
                        if k in by_t and by_t[k]:
                            est_breakeven = by_t[k][0].get("yield_pct")
                            break
                    # Dynamic 10Y Real Yield (DFII10 / 10Y_REAL)
                    for k in ("10Y_REAL", "DFII10"):
                        if k in by_t and by_t[k]:
                            real_10y = by_t[k][0].get("yield_pct")
                            break
                if nom_10y is None and "us10y" in yields_info:
                    nom_10y = yields_info.get("us10y")

            if nom_10y is not None:
                nom_10y = float(nom_10y)
                is_breakeven_fallback = False
                # Dynamic breakeven / real yield calculation with graceful fallback
                if est_breakeven is not None:
                    est_breakeven = float(est_breakeven)
                elif real_10y is not None:
                    est_breakeven = round(nom_10y - float(real_10y), 2)
                else:
                    # Attempt dynamic median query from recent treasury yields if available
                    try:
                        from database.models import TreasuryYield
                        stmt = select(TreasuryYield.yield_pct).where(
                            TreasuryYield.tenor.in_(["10Y_INFLATION", "T10YIE"])
                        ).order_by(TreasuryYield.fetched_at.desc()).limit(30)
                        recent_vals = (await self.session.execute(stmt)).scalars().all()
                        if recent_vals and len(recent_vals) > 0:
                            import statistics
                            est_breakeven = round(float(statistics.median(recent_vals)), 2)
                        else:
                            est_breakeven = 2.35
                            is_breakeven_fallback = True
                    except Exception:
                        est_breakeven = 2.35
                        is_breakeven_fallback = True

                if real_10y is not None:
                    real_10y = round(float(real_10y), 2)
                else:
                    real_10y = round(nom_10y - est_breakeven, 2)

                gold_bias = "BEARISH_HEADWIND" if real_10y > 2.0 else ("BULLISH_TAILWIND" if real_10y < 1.0 else "NEUTRAL_RANGE")
                bundled_data["real_yield_context"] = {
                    "nominal_us10y_pct": nom_10y,
                    "estimated_breakeven_inflation_pct": est_breakeven,
                    "real_us10y_yield_pct": real_10y,
                    "is_breakeven_fallback": is_breakeven_fallback,
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
            ec_data = bundled_data.get("economic_calendar")
            if ec_data and isinstance(ec_data, dict) and "error" not in ec_data and ec_data.get("events"):
                breaker.record_feed_heartbeat("economic_calendar")
            ty_data = bundled_data.get("treasury_yields")
            if ty_data and isinstance(ty_data, dict) and "error" not in ty_data:
                breaker.record_feed_heartbeat("fred")
            nd_data = bundled_data.get("news_digest")
            if nd_data and isinstance(nd_data, dict) and "error" not in nd_data and (nd_data.get("items") or nd_data.get("digest")):
                breaker.record_feed_heartbeat("finnhub")

            eval_res = breaker.evaluate_all_feeds(auto_trip=False)
            bundled_data["circuit_breaker_status"] = eval_res
            if breaker.is_tripped():
                logger.warning(f"[Stage1DataBundler] Data feed circuit breaker is TRIPPED: {breaker.get_tripped_feeds()}")
        except Exception as cb_err:
            logger.debug(f"Circuit breaker prefetch check non-fatal error: {cb_err}")

        # Direct in-memory computation of satisfied tools (excluding failed tools)
        satisfied_tools = set()
        for key, val in bundled_data.items():
            if isinstance(val, dict) and "error" in val:
                continue
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
