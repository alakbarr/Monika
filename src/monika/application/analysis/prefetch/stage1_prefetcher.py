import asyncio
import json
import logging
from typing import Any, Dict, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.tools.tool_executor import ToolExecutor
from monika.infrastructure.llm.caveman_compressor import compress_tool_payload

logger = logging.getLogger("TradingAgent.Stage1Prefetcher")

PREFETCH_KEY_TO_TOOL: dict[str, str] = {
    "economic_calendar": "get_economic_calendar",
    "news_digest": "get_news_digest",
    "dxy": "get_dxy",
    "treasury_yields": "get_treasury_yields",
    "interest_rates": "get_interest_rates",
    "fedwatch": "get_fedwatch_probabilities",
    "vix": "get_vix",
    "fear_greed": "get_fear_greed_index",
    "cot_signals": "get_precomputed_cot_signals",
    "surprise_summary": "get_surprise_summary",
    "eurusd_momentum": "get_price_momentum",
    "market_session": "get_market_session",
    "funding_rate": "get_funding_rate",
    "bond_yield_spreads": "get_bond_yield_spreads",
    "central_bank_expectations": "get_central_bank_expectations",
    "prediction_market": "get_prediction_market_odds",
    "fed_net_liquidity_and_stress": "get_fed_net_liquidity_and_stress",
    "treasury_auction_results": "get_treasury_auction_results",
    "macro_cross_report_synthesis": "get_macro_cross_report_synthesis",
    "g10_macro_divergence": "get_g10_macro_divergence",
}

CORE_STAGE1_PREFETCH_TOOLS: frozenset[str] = frozenset(
    {
        "get_economic_calendar",
        "get_treasury_yields",
        "get_vix",
        "get_dxy",
        "get_fedwatch_probabilities",
        "get_news_digest",
    }
)


def prune_stage1_tools(
    base_tools: list[dict[str, Any]],
    satisfied_tools: Union[set[str], frozenset[str]],
    mandatory_conclusion_tool: str = "submit_fundamental_brief",
) -> list[dict[str, Any]]:
    """
    Health-Aware Conditional Tool Pruning for Stage 1 Fundamental Analysis.

    When prefetch data has already been injected into prompt context:
    1. If prefetch is complete (all core indicators satisfied), prunes all read
       tools to force direct synthesis and eliminate turn exhaustion, leaving
       only mandatory_conclusion_tool ('submit_fundamental_brief').
    2. If any core indicator failed during prefetch (e.g. FRED API down), that specific
       tool is preserved alongside mandatory_conclusion_tool so the agent retains
       an operational fallback path.
    3. If satisfied_tools is empty (prefetch failure), returns base_tools unchanged.
    """
    if not satisfied_tools:
        return list(base_tools)

    if CORE_STAGE1_PREFETCH_TOOLS.issubset(satisfied_tools):
        # 100% healthy prefetch: prune all read tools, leaving only mandatory conclusion tool
        return [
            tool
            for tool in base_tools
            if (tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "")) == mandatory_conclusion_tool
        ]

    # Partial prefetch: keep mandatory conclusion tool and any unsatisfied tools
    pruned: list[dict[str, Any]] = []
    for tool in base_tools:
        name = str(tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", ""))
        if name == mandatory_conclusion_tool or name not in satisfied_tools:
            pruned.append(tool)

    return pruned


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
            "economic_calendar": self.executor.execute(
                "get_economic_calendar", {"hours_ahead": 48, "hours_behind": 24}
            ),
            "news_digest": self.executor.execute("get_news_digest", {"hours_back": 12}),
            "dxy": self.executor.execute("get_dxy", {}),
            "treasury_yields": self.executor.execute("get_treasury_yields", {"days_back": 5}),
            "interest_rates": self.executor.execute("get_interest_rates", {}),
            "fedwatch": self.executor.execute("get_fedwatch_probabilities", {}),
            "vix": self.executor.execute("get_vix", {}),
            "fear_greed": self.executor.execute("get_fear_greed_index", {}),
            "cot_signals": self.executor.execute("get_precomputed_cot_signals", {}),
            "surprise_summary": self.executor.execute("get_surprise_summary", {}),
            "eurusd_momentum": self.executor.execute(
                "get_price_momentum", {"symbol": "EURUSD", "timeframe": "H4", "period": 20}
            ),
            "market_session": self.executor.execute("get_market_session", {}),
            "funding_rate": self.executor.execute("get_funding_rate", {}),
            "bond_yield_spreads": self.executor.execute("get_bond_yield_spreads", {}),
            "central_bank_expectations": self.executor.execute("get_central_bank_expectations", {}),
            "prediction_market": self.executor.execute("get_prediction_market_odds", {}),
            "fed_net_liquidity_and_stress": self.executor.execute("get_fed_net_liquidity_and_stress", {}),
            "treasury_auction_results": self.executor.execute("get_treasury_auction_results", {"tenor": "10Y"}),
            "macro_cross_report_synthesis": self.executor.execute("get_macro_cross_report_synthesis", {}),
            "g10_macro_divergence": self.executor.execute("get_g10_macro_divergence", {"pair": "EURUSD"}),
        }

        # Extra parallel zero-browser real-time feeds
        async def _fetch_crypto_depth():
            from monika.infrastructure.data_ingestion.sources.crypto_orderbook_depth import CryptoOrderbookDepth

            snap = await CryptoOrderbookDepth.fetch_snapshot("BTCUSD")
            return (
                {
                    "exchange": snap.exchange,
                    "spread_bps": snap.spread_bps,
                    "imbalance_score": snap.imbalance_score,
                    "bid_liq_usd": snap.bid_liquidity_usd,
                    "ask_liq_usd": snap.ask_liquidity_usd,
                    "slippage": snap.slippage_estimates,
                }
                if snap
                else {"error": "L2 depth unavailable"}
            )

        async def _fetch_sovereign_spreads():
            from monika.infrastructure.data_ingestion.sources.sovereign_yield_spreads import SovereignYieldSpreads

            return await SovereignYieldSpreads.get_spreads(session=self.session)

        async def _fetch_gold_radar():
            from monika.infrastructure.data_ingestion.sources.gold_physical_radar import GoldPhysicalRadar

            radar = await GoldPhysicalRadar.fetch_radar()
            return {
                "is_available": radar.is_available,
                "flow_bias": radar.institutional_flow_bias,
                "gld_change_pct": radar.gld_1d_change_pct,
                "conviction": radar.xau_sentiment_conviction,
                "summary": radar.summary,
            }

        async def _fetch_brent_crude():
            from monika.infrastructure.data_ingestion.sources.brent_yfinance import get_brent_price

            price = await get_brent_price()
            return {"brent_price": price, "is_available": price is not None}

        tasks["crypto_l2_depth"] = _fetch_crypto_depth()
        tasks["sovereign_yield_spreads"] = _fetch_sovereign_spreads()
        tasks["gold_physical_radar"] = _fetch_gold_radar()
        tasks["brent_crude"] = _fetch_brent_crude()

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

                import monika.core.primitives.clock as clock

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
                        all_event_shifts.append(
                            {
                                "event_time": t_str,
                                "events": names or "USD Release",
                                "meeting_date": c.get("meeting_date"),
                                "shift_summary": c.get("shift_summary"),
                                "deltas_pct": c.get("deltas_pct"),
                                "prior_probabilities": c.get("prior_probabilities"),
                                "current_probabilities": c.get("current_probabilities"),
                                "pre_snapshot_time": c.get("pre_snapshot_time"),
                                "post_snapshot_time": c.get("post_snapshot_time"),
                            }
                        )
            else:
                # Fallback: pergeseran temporal 24 jam jika tidak ada event kalender spesifik
                fw_comp = await self.executor.execute("get_fedwatch_probabilities", {"compare_hours_ago": 24})
                if isinstance(fw_comp, dict) and fw_comp.get("comparisons"):
                    c = fw_comp["comparisons"][0]
                    all_event_shifts.append(
                        {
                            "event_time": None,
                            "events": "24h Temporal Shift",
                            "meeting_date": c.get("meeting_date"),
                            "shift_summary": c.get("shift_summary"),
                            "deltas_pct": c.get("deltas_pct"),
                            "prior_probabilities": c.get("prior_probabilities"),
                            "current_probabilities": c.get("current_probabilities"),
                            "pre_snapshot_time": c.get("pre_snapshot_time"),
                            "post_snapshot_time": c.get("post_snapshot_time"),
                        }
                    )

            if all_event_shifts:
                latest_shift = all_event_shifts[-1]
                multi_summary = " | ".join([f"[{s['events']}]: {s['shift_summary']}" for s in all_event_shifts])

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
                        from monika.infrastructure.database.models import TreasuryYield

                        stmt = (
                            select(TreasuryYield.yield_percent)
                            .where(TreasuryYield.tenor.in_(["10Y_INFLATION", "T10YIE"]))
                            .order_by(TreasuryYield.date.desc())
                            .limit(30)
                        )
                        recent_vals = (await self.session.execute(stmt)).scalars().all()
                        if recent_vals and len(recent_vals) > 0:
                            import statistics

                            est_breakeven = round(float(statistics.median(recent_vals)), 2)
                        else:
                            est_breakeven = None
                            is_breakeven_fallback = True
                    except Exception:
                        est_breakeven = None
                        is_breakeven_fallback = True

                if real_10y is not None:
                    real_10y = round(float(real_10y), 2)
                elif nom_10y is not None and est_breakeven is not None:
                    real_10y = round(nom_10y - est_breakeven, 2)
                else:
                    real_10y = None

                gold_bias = (
                    "BEARISH_HEADWIND"
                    if real_10y is not None and real_10y > 2.0
                    else ("BULLISH_TAILWIND" if real_10y is not None and real_10y < 1.0 else "NEUTRAL_RANGE")
                )
                bundled_data["real_yield_context"] = {
                    "nominal_us10y_pct": nom_10y,
                    "estimated_breakeven_inflation_pct": est_breakeven,
                    "real_us10y_yield_pct": real_10y,
                    "is_breakeven_fallback": is_breakeven_fallback,
                    "gold_macro_bias": gold_bias,
                    "interpretation": (
                        f"Real 10Y Yield at {real_10y}%. Real yields > 2.0% create strong headwind for Gold (XAUUSD); < 1.0% provides fuel for Gold breakout."
                        if real_10y is not None
                        else "Real 10Y Yield data currently unavailable."
                    ),
                }
        except Exception as e:
            logger.debug(f"Real yield precomputation non-fatal error: {e}")

        # Compute unified multi-source aggregated sentiment across traded symbols
        try:
            from monika.application.analysis.prefetch.sentiment_aggregator import SentimentAggregator
            from monika.infrastructure.database.models import SystemConfig

            aggregator = SentimentAggregator(self.settings)
            cot_signals = bundled_data.get("cot_signals", {})
            vix_data = bundled_data.get("vix", {})
            funding_data = bundled_data.get("funding_rate", {})

            # Extract latest retail positioning from SystemConfig
            retail_sentiment_map = {}
            try:
                cfg_rows = (
                    (
                        await self.session.execute(
                            select(SystemConfig).where(
                                SystemConfig.key.in_(
                                    [
                                        "myfxbook_sentiment_latest",
                                        "fxssi_sentiment_latest",
                                        "binance_sentiment_latest",
                                    ]
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for row in cfg_rows:
                    if row.value:
                        try:
                            val_dict = json.loads(row.value)
                            if isinstance(val_dict, dict):
                                ratios = val_dict.get("ratios") or val_dict.get("positions") or {}
                                if isinstance(ratios, dict):
                                    for s_key, r_info in ratios.items():
                                        s_clean = s_key.upper().replace("/", "").strip()
                                        if s_clean not in retail_sentiment_map and isinstance(r_info, dict):
                                            retail_sentiment_map[s_clean] = r_info
                        except Exception:
                            pass
            except Exception as ret_cfg_err:
                logger.debug(f"Prefetch retail sentiment query non-fatal: {ret_cfg_err}")

            symbols_to_aggregate = (
                self.settings.get("trading", {}).get("asset_universe")
                or self.settings.get("trading", {}).get("symbols")
                or ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XTIUSD", "BTCUSD", "XBRUSD"]
            )
            aggregated_sentiment_map = {}
            for sym in symbols_to_aggregate:
                try:
                    sent_schema = aggregator.aggregate_sentiment(
                        cot_data=cot_signals,
                        retail_data=retail_sentiment_map.get(sym, {}),
                        risk_data=vix_data,
                        symbol=sym,
                        funding_data=funding_data if "BTC" in sym.upper() else None,
                    )
                    aggregated_sentiment_map[sym] = sent_schema.model_dump()
                except Exception as agg_sym_err:
                    logger.debug(f"Aggregated sentiment failure for {sym}: {agg_sym_err}")

            if aggregated_sentiment_map:
                bundled_data["aggregated_sentiment"] = aggregated_sentiment_map
        except Exception as sent_err:
            logger.debug(f"Aggregated sentiment computation non-fatal error: {sent_err}")

        # Validate macro & market data freshness
        try:
            from monika.core.validation.data_validator import validate_data_freshness

            symbols = (
                self.settings.get("trading", {}).get("asset_universe")
                or self.settings.get("trading", {}).get("symbols")
                or ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XTIUSD", "BTCUSD", "XBRUSD"]
            )
            freshness = await validate_data_freshness(self.session, symbols, ["H1", "H4", "D1"])
            bundled_data["data_freshness_status"] = freshness
            if not freshness.get("ready"):
                notices = (freshness.get("errors") or []) + (freshness.get("warnings") or [])
                logger.warning(f"Stage 1 data freshness validation notices: {notices}")
        except Exception as e:
            logger.debug(f"Data freshness prefetch check non-fatal error: {e}")

        # Update DataFeedCircuitBreaker heartbeats and evaluate critical feeds
        try:
            from monika.infrastructure.data_ingestion.sources.circuit_breaker import get_data_feed_circuit_breaker

            breaker = get_data_feed_circuit_breaker()
            ec_data = bundled_data.get("economic_calendar")
            if ec_data and isinstance(ec_data, dict) and "error" not in ec_data and ec_data.get("events"):
                breaker.record_feed_heartbeat("economic_calendar")
            ty_data = bundled_data.get("treasury_yields")
            if ty_data and isinstance(ty_data, dict) and "error" not in ty_data:
                breaker.record_feed_heartbeat("fred")
            nd_data = bundled_data.get("news_digest")
            if (
                nd_data
                and isinstance(nd_data, dict)
                and "error" not in nd_data
                and (nd_data.get("items") or nd_data.get("digest"))
            ):
                breaker.record_feed_heartbeat("finnhub")

            eval_res = breaker.evaluate_all_feeds(auto_trip=False)
            bundled_data["circuit_breaker_status"] = eval_res
            if breaker.is_tripped():
                logger.warning(
                    f"[Stage1DataBundler] Data feed circuit breaker is TRIPPED: {breaker.get_tripped_feeds()}"
                )
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
        terminal_dashboard = self._synthesize_tier1_terminal(bundled_data)
        bundled_data = {"_tier1_executive_macro_terminal": terminal_dashboard, **bundled_data}
        compressed_json = self._compress_json(bundled_data)
        return compressed_json, satisfied_tools, bundled_data

    def _synthesize_tier1_terminal(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesizes high-saliency Tier 1 Executive Macro Terminal Dashboard."""
        terminal: Dict[str, Any] = {}

        # 1. Treasuries & Yield Curve
        y_info = data.get("treasury_yields", {})
        y_dict = y_info.get("yields_by_tenor", {}) if isinstance(y_info, dict) else {}
        us02y = y_dict.get("2Y", [{}])[0].get("yield_pct") if "2Y" in y_dict and y_dict["2Y"] else None
        us10y = y_dict.get("10Y", [{}])[0].get("yield_pct") if "10Y" in y_dict and y_dict["10Y"] else None
        us30y = y_dict.get("30Y", [{}])[0].get("yield_pct") if "30Y" in y_dict and y_dict["30Y"] else None

        spread_str = "N/A"
        if us10y is not None and us02y is not None:
            spread_bps = round((float(us10y) - float(us02y)) * 100, 1)
            slope_regime = "Bull/Bear Steepener" if spread_bps > 0 else "Inverted/Flattener"
            spread_str = f"{spread_bps:+.1f} bps ({slope_regime})"

        terminal["treasury_curve_2s10s"] = (
            f"2Y={us02y or 'N/A'}% | 10Y={us10y or 'N/A'}% | 30Y={us30y or 'N/A'}% | Spread={spread_str}"
        )

        ry_ctx = data.get("real_yield_context", {})
        if isinstance(ry_ctx, dict) and ry_ctx.get("real_10y_yield_pct") is not None:
            terminal["real_rates_context"] = (
                f"10Y TIPS Real Yield={ry_ctx.get('real_10y_yield_pct')}% | Breakeven={ry_ctx.get('estimated_breakeven_inflation_pct', 'N/A')}%"
            )

        # 2. DXY & VIX
        dxy_data = data.get("dxy", {})
        dxy_val = dxy_data.get("value") if isinstance(dxy_data, dict) else None
        vix_data = data.get("vix", {})
        vix_val = vix_data.get("value") if isinstance(vix_data, dict) else None
        terminal["market_volatility_dxy_vix"] = f"DXY={dxy_val or 'N/A'} | VIX={vix_val or 'N/A'}"

        # 3. FedWatch Trajectory
        fw_comp = data.get("fedwatch_comparison", {})
        if isinstance(fw_comp, dict) and fw_comp.get("shift_summary"):
            terminal["fedwatch_shift"] = fw_comp.get("shift_summary")

        # 4. Central Bank Rates
        cb_rates = data.get("interest_rates", data.get("central_bank_rates", {}))
        if isinstance(cb_rates, dict) and "rates" in cb_rates:
            rates_obj = cb_rates["rates"]
            if isinstance(rates_obj, dict):
                terminal["central_bank_policy_rates"] = {
                    k: v.get("rate") or v.get("rate_pct")
                    for k, v in rates_obj.items()
                    if isinstance(v, dict) and (v.get("rate") is not None or v.get("rate_pct") is not None)
                }
            elif isinstance(rates_obj, list):
                terminal["central_bank_policy_rates"] = {
                    item.get("bank"): item.get("rate_pct") or item.get("rate")
                    for item in rates_obj
                    if isinstance(item, dict)
                    and item.get("bank")
                    and (item.get("rate_pct") is not None or item.get("rate") is not None)
                }

        # 5. Crypto Funding Rate (if present)
        f_rate = data.get("funding_rate", {})
        if isinstance(f_rate, dict):
            fr_val = f_rate.get("funding_rate") or f_rate.get("average_funding_rate")
            if fr_val is not None:
                terminal["crypto_perp_funding_rate"] = f"{fr_val}%"

        return terminal

    def _compress_json(self, data: Dict[str, Any]) -> str:
        """Compress data to save tokens using caveman logic and context compressor."""
        compressed = compress_tool_payload(data)
        if isinstance(compressed, (str, dict)):
            try:
                from monika.infrastructure.llm.prompt_compressor import PromptBundleCompressor as ContextCompressor

                compressor = ContextCompressor(self.settings)
                return compressor.compress_stage1_bundle(compressed, max_tokens=6000)
            except Exception:
                pass
        return json.dumps(compressed, default=str)
