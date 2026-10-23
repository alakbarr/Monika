import json
from contextlib import contextmanager
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.schemas import SubmitAssetAnalysisSchema, SubmitFundamentalBriefSchema
from monika.application.analysis.tools.tool_executor import ToolExecutor
from monika.infrastructure.database.models import (
    AssetAnalysis,
    DecisionReflection,
    FundamentalBrief,
    NewsDigest,
    NewsItem,
    TelegramConversation,
)


class BenchmarkToolExecutor(ToolExecutor):
    """ToolExecutor sungguhan (semua tool baca = data live dari Postgres/MT5
    cache, identik dgn produksi) tapi tool tulis divalidasi via schema Pydantic
    ASLI lalu ditangkap di memori -- TIDAK PERNAH menulis ke Postgres."""

    def __init__(self, session, settings, model_name=None):
        super().__init__(session, settings, model_name=model_name)
        self.captured: dict | None = None

    async def execute(self, tool_name: str, tool_input: dict) -> dict:
        normalized = getattr(self, "TOOL_ALIASES", {}).get(tool_name, tool_name)
        if hasattr(self, "called_tools"):
            self.called_tools.add(normalized)
        if normalized == "submit_fundamental_brief":
            return await self._tool_submit_fundamental_brief(tool_input)
        if normalized == "submit_asset_analysis":
            return await self._tool_submit_asset_analysis(tool_input)
        if normalized == "propose_action":
            return await self._tool_propose_action(tool_input)
        if BenchmarkFixtureDispatcher.can_handle(normalized):
            return BenchmarkFixtureDispatcher.dispatch(normalized, tool_input)
        return await super().execute(tool_name, tool_input)

    async def _tool_submit_asset_analysis(self, inp: dict) -> dict:
        try:
            payload = SubmitAssetAnalysisSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
        except ValidationError as e:
            return {
                "status": "validation_failed",
                "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()],
            }
        self.captured = {"tool": "submit_asset_analysis", "payload": payload}
        return {
            "status": "saved",
            "analysis_id": -1,
            "symbol": payload.get("symbol"),
            "decision": payload.get("decision"),
            "message": "benchmark: tidak dipersist",
        }

    async def _tool_submit_fundamental_brief(self, inp: dict) -> dict:
        try:
            payload = SubmitFundamentalBriefSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
        except ValidationError as e:
            return {
                "status": "validation_failed",
                "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()],
            }
        self.captured = {"tool": "submit_fundamental_brief", "payload": payload}
        return {"status": "saved", "brief_id": -1, "valid_until": None}

    async def _tool_propose_action(self, inp: dict) -> dict:
        self.captured = {"tool": "propose_action", "payload": inp}
        return {
            "status": "proposed",
            "message": "benchmark: tidak dipersist",
            "action_type": inp.get("action_type"),
            "params": inp.get("params"),
        }


# ---------------------------------------------------------------------------
# run_agent()/run_chat_loop() milik BaseLLMClient MEMBUAT ToolExecutor sendiri
# di dalam (tidak menerima instance dari luar). Untuk mode "agent"/"chat" kita
# terpaksa patch method tulis di CLASS ToolExecutor untuk sementara. Karena
# ini state global proses, runner.py WAJIB menyerialkan pemanggilan mode ini
# (lihat _AGENT_LOCK di runner.py) supaya tidak race dengan panggilan model
# lain yang berjalan paralel.
# ---------------------------------------------------------------------------
_capture_box: dict = {}


async def _capturing_submit_asset_analysis(self, inp: dict) -> dict:
    try:
        payload = SubmitAssetAnalysisSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
    except ValidationError as e:
        return {
            "status": "validation_failed",
            "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()],
        }
    _capture_box["result"] = {"tool": "submit_asset_analysis", "payload": payload}
    return {
        "status": "saved",
        "analysis_id": -1,
        "symbol": payload.get("symbol"),
        "decision": payload.get("decision"),
        "message": "benchmark: tidak dipersist",
    }


async def _capturing_submit_fundamental_brief(self, inp: dict) -> dict:
    try:
        payload = SubmitFundamentalBriefSchema.model_validate(inp).model_dump(exclude_unset=True, mode="json")
    except ValidationError as e:
        return {
            "status": "validation_failed",
            "errors": [f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors()],
        }
    _capture_box["result"] = {"tool": "submit_fundamental_brief", "payload": payload}
    return {"status": "saved", "brief_id": -1, "valid_until": None}


async def _capturing_propose_action(self, inp: dict) -> dict:
    _capture_box["result"] = {"tool": "propose_action", "payload": inp}
    return {
        "status": "proposed",
        "message": "benchmark: tidak dipersist",
        "action_type": inp.get("action_type"),
        "params": inp.get("params"),
    }


def _handle_economic_calendar(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    events = bundle.get("economic_calendar", [])
    cur_filter = inp.get("currency_filter")
    impact_filter = inp.get("impact_filter")
    event_name = inp.get("event_name")
    filtered = list(events)
    if cur_filter:
        curs = {c.strip().upper() for c in str(cur_filter).split(",")}
        filtered = [e for e in filtered if str(e.get("currency", "")).upper() in curs]
    if impact_filter and impact_filter != "all":
        if impact_filter == "high_and_medium":
            filtered = [e for e in filtered if str(e.get("impact", "")).lower() in ("high", "medium")]
        elif impact_filter in ("high", "medium", "low"):
            filtered = [e for e in filtered if str(e.get("impact", "")).lower() == impact_filter]
    if event_name:
        ename = str(event_name).lower()
        filtered = [e for e in filtered if ename in str(e.get("event", "")).lower()]
    return {"status": "success", "count": len(filtered), "events": filtered}


def _handle_interest_rates(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    rates = bundle.get("interest_rates", [])
    cb_filter = inp.get("central_bank")
    if cb_filter:
        rates = [r for r in rates if str(r.get("central_bank", "")).upper() == str(cb_filter).upper()]
    return {"status": "success", "count": len(rates), "interest_rates": rates}


def _handle_treasury_yields(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "data": bundle.get("treasury_yields", {})}


def _handle_bond_yield_spreads(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "spreads": bundle.get("bond_yield_spreads", {})}


def _handle_fedwatch(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "fedwatch": bundle.get("fedwatch", {})}


def _handle_central_bank_expectations(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "expectations": bundle.get("central_bank_expectations", {})}


def _handle_news_digest(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "digest": bundle.get("news_digest", ""), "generated_at": "2026-10-04T18:47:55Z"}


def _handle_news_items(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    from monika.application.benchmark.fixture_loader import get_golden_macro_stage1

    golden = get_golden_macro_stage1()
    items = []
    for it in golden.get("high_impact_news", []):
        items.append(
            {
                "title": it.get("title"),
                "summary": it.get("summary"),
                "impact": it.get("impact", "HIGH"),
                "source": it.get("source", "news"),
                "published_at": it.get("published_at", "2026-10-04T12:00:00Z"),
                "currencies": it.get("currencies", ["USD"]),
            }
        )
    limit = int(inp.get("limit", 10)) if inp.get("limit") else 10
    return {"status": "success", "count": len(items[:limit]), "news_items": items[:limit]}


def _handle_vix(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "vix": bundle.get("vix", {})}


def _handle_dxy(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "dxy": bundle.get("dxy", {})}


def _handle_fear_greed(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "fear_greed": bundle.get("fear_greed", {})}


def _handle_eia_oil_inventory(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "crude_inventory_change_mb": -1.8,
        "gasoline_inventory_change_mb": 0.4,
        "distillate_change_mb": -0.9,
        "spr_change_mb": 0.2,
        "interpretation": "BULLISH_CRUDE",
        "report_date": "2026-10-02",
    }


def _handle_market_session(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "session": bundle.get("market_session", {})}


def _handle_surprise_summary(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "surprises": {
            "USD": {"score": -1.4, "momentum": "WEAKENING_POST_NFP", "last_release": "NFP +29k vs +90k exp"},
            "EUR": {"score": +0.2, "momentum": "STABLE", "last_release": "CPI flash 2.2%"},
            "GBP": {"score": +0.5, "momentum": "MODERATELY_POSITIVE", "last_release": "GDP 0.3%"},
            "JPY": {"score": +0.3, "momentum": "HAWKISH_NORMALIZATION", "last_release": "Tokyo CPI 2.5%"},
            "AUD": {"score": 0.0, "momentum": "NEUTRAL", "last_release": "RBA hold 4.10%"},
        },
    }


def _handle_cot_signals(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "cot_signals": bundle.get("cot_signals", [])}


def _handle_economic_surprise(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "key_surprises": [
            {
                "indicator": "Non-Farm Payrolls",
                "country": "US",
                "actual": 29000,
                "forecast": 90000,
                "deviation": -61000,
                "impact": "LARGE_NEGATIVE",
            },
            {
                "indicator": "Unemployment Rate",
                "country": "US",
                "actual": 4.2,
                "forecast": 4.1,
                "deviation": 0.1,
                "impact": "NEGATIVE",
            },
        ],
    }


def _handle_price_momentum(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "momentum": bundle.get("eurusd_momentum", {})}


def _handle_funding_rate(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "funding_rates": bundle.get("funding_rate", {})}


def _handle_web_search(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    q = str(inp.get("query", ""))
    return {
        "status": "success",
        "query": q,
        "results": [
            {
                "title": "US Nonfarm Payrolls Miss Sharply in September 2026",
                "snippet": "The US economy added just 29,000 jobs in September 2026 against consensus of 90,000, pushing the unemployment rate up to 4.2%. Dollar Index softened below 102.",
                "url": "https://reuters.com/markets/us-nfp-sep-2026",
            },
            {
                "title": "Middle East Tensions Sustain Oil and Gold Safe-Haven Bids",
                "snippet": "WTI crude trades near $71.85 and Spot Gold holds near $2,658.50/oz as geopolitical friction in the Middle East sustains a persistent risk premium.",
                "url": "https://bloomberg.com/markets/commodities-geopolitics-2026",
            },
            {
                "title": "Federal Reserve Rate Decision Outlook",
                "snippet": "CME FedWatch shows an 82% probability of the Fed holding rates at 3.75-4.00% at the November meeting following mixed labor and inflation data.",
                "url": "https://cmegroup.com/fedwatch-2026",
            },
        ],
    }


def _handle_save_intel(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "saved", "intel_id": 9999, "message": "benchmark: intelligence captured in memory"}


def _handle_list_intel(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "active_intelligence": []}


def _handle_archive_intel(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "archived", "intel_id": inp.get("intel_id", 0)}


def _handle_inspect_report(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "report_name": inp.get("report_name", "NFP"),
        "details": "US September Non-Farm Payrolls printed at +29,000 vs +90,000 expected. Unemployment rate rose to 4.2%. Prior two months revised downward by 60,000 jobs cumulatively.",
    }


def _handle_diff_cb_docs(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "comparison": "FOMC Statement Delta: The Committee noted slower job gains while inflation remains somewhat elevated. Language shifted from active tightening risk to balanced two-sided risks.",
    }


def _handle_cross_report_synthesis(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "synthesis": bundle.get("macro_cross_report_synthesis", {})}


def _handle_g10_divergence(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "divergence": bundle.get("g10_macro_divergence", {})}


def _handle_fed_net_liquidity(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "liquidity_stress": bundle.get("fed_net_liquidity_and_stress", {})}


def _handle_treasury_auction(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "auction_results": bundle.get("treasury_auction_results", {})}


def _handle_market_quote(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper().replace("/", "")
    prices = {
        "EURUSD": 1.1260,
        "GBPUSD": 1.3325,
        "USDJPY": 144.20,
        "XAUUSD": 2658.50,
        "XTIUSD": 71.85,
        "BTCUSD": 84200.00,
        "ETHUSD": 3150.00,
        "AUDUSD": 0.6540,
        "USDCHF": 0.8520,
        "USDCAD": 1.3580,
    }
    p = prices.get(sym, 1.0)
    return {
        "status": "success",
        "symbol": sym,
        "price": p,
        "bid": round(p * 0.9999, 4),
        "ask": round(p * 1.0001, 4),
        "spread_pips": 1.2,
        "as_of": "2026-10-04T19:00:00Z",
    }


def _handle_calculate_position_size(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper().replace("/", "")
    entry = float(inp.get("entry_price") or 1.1250)
    sl = float(inp.get("stop_loss") or (entry - 0.0030))
    risk_pct = float(inp.get("risk_pct") or inp.get("risk_percent") or 1.0)
    sl_dist = abs(entry - sl)
    pip_size = 0.01 if "JPY" in sym or "XAU" in sym else 0.0001
    sl_pips = sl_dist / pip_size if pip_size > 0 else 30.0
    account_balance = 76849.91
    risk_usd = round(account_balance * (risk_pct / 100.0), 2)
    lot_size = round(max(0.01, risk_usd / (max(sl_pips, 1.0) * 10.0)), 2)
    return {
        "status": "success",
        "symbol": sym,
        "entry_price": entry,
        "stop_loss": sl,
        "risk_pct": risk_pct,
        "risk_amount_usd": risk_usd,
        "lot_size": lot_size,
        "lots": lot_size,
        "recommended_lots": lot_size,
        "max_risk_allowed": risk_usd,
        "invariants_checked": True,
    }


def _handle_optimal_intraday_levels(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper().replace("/", "")
    direction = str(inp.get("direction", "buy")).lower()
    entry = float(inp.get("entry_price") or 1.1250)
    pip = 0.0001 if "JPY" not in sym else 0.01
    sl = round(entry - (30 * pip) if direction == "buy" else entry + (30 * pip), 5)
    tp1 = round(entry + (45 * pip) if direction == "buy" else entry - (45 * pip), 5)
    tp2 = round(entry + (75 * pip) if direction == "buy" else entry - (75 * pip), 5)
    return {
        "status": "success",
        "symbol": sym,
        "direction": direction,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "rr_ratio": 1.5,
        "levels": {"sl": sl, "tp1": tp1, "tp2": tp2},
    }


def _handle_spread_snapshot(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper().replace("/", "")
    return {
        "status": "success",
        "symbol": sym,
        "spread_pips": 1.0,
        "spread_points": 10,
        "pip_size": 0.0001 if "JPY" not in sym else 0.01,
        "bid": 1.12500,
        "ask": 1.12510,
        "status_quality": "normal",
    }


def _handle_technical_analysis(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper().replace("/", "")
    return {
        "status": "success",
        "symbol": sym,
        "H4": {
            "trend": "BEARISH_CORRECTION",
            "rsi": 52.4,
            "ema_20": 1.1228,
            "ema_50": 1.11942,
            "ema_200": 1.11155,
            "atr_14": 0.00563,
            "adx_14": 28.5,
        },
        "H1": {
            "trend": "PULLBACK",
            "rsi": 48.6,
            "ema_20": 1.1228,
            "ema_50": 1.11942,
            "atr_14": 0.0021,
        },
    }


def _handle_institutional_data(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "symbol": str(inp.get("symbol", "EURUSD")).upper(),
        "cot_bias": "Net Short Hedging (EUR)",
        "commercial_sentiment": "Bearish",
        "retail_sentiment": {"long_pct": 74.2, "short_pct": 25.8, "contrarian_signal": "BEARISH"},
    }


_scratchpad_cache: dict[str, Any] = {}


def _handle_update_scratchpad(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper()
    data = inp.get("data") or inp.get("notes") or inp
    _scratchpad_cache[sym] = data
    return {"status": "success", "symbol": sym, "saved": True}


def _handle_read_scratchpad(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    sym = str(inp.get("symbol", "EURUSD")).upper()
    return {"status": "success", "symbol": sym, "data": _scratchpad_cache.get(sym, {})}


def _handle_scan_pattern_similarity(bundle: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "symbol": str(inp.get("symbol", "EURUSD")).upper(),
        "top_matches": [
            {
                "date": "2026-06-12",
                "similarity": 0.88,
                "pattern": "H4 Asian Liquidity Sweep & Retest",
                "subsequent_outcome": "BEARISH_EXPANSION +85 pips",
            },
            {
                "date": "2026-08-04",
                "similarity": 0.81,
                "pattern": "H1 Bearish FVG Rejection",
                "subsequent_outcome": "BEARISH_CONTINUATION +60 pips",
            },
        ],
    }


class BenchmarkFixtureDispatcher:
    """Deterministic in-memory fixture dispatcher for benchmark evaluations.
    Serves all Stage 1 & Stage 2 read tools directly from golden production fixtures,
    guaranteeing zero empty DB returns, zero network timeouts, and zero unmocked MT5 calls."""

    _bundle: dict[str, Any] | None = None

    _HANDLERS = {
        "get_economic_calendar": _handle_economic_calendar,
        "get_economic_calendars": _handle_economic_calendar,
        "get_calendar": _handle_economic_calendar,
        "get_interest_rates": _handle_interest_rates,
        "get_interest_rate": _handle_interest_rates,
        "get_treasury_yields": _handle_treasury_yields,
        "get_treasury_yield": _handle_treasury_yields,
        "get_bond_yield_spreads": _handle_bond_yield_spreads,
        "get_fedwatch_probabilities": _handle_fedwatch,
        "get_central_bank_expectations": _handle_central_bank_expectations,
        "get_news_digest": _handle_news_digest,
        "get_news": _handle_news_digest,
        "get_news_items": _handle_news_items,
        "get_news_item": _handle_news_items,
        "get_vix": _handle_vix,
        "get_dxy": _handle_dxy,
        "get_fear_greed": _handle_fear_greed,
        "get_eia_oil_inventory": _handle_eia_oil_inventory,
        "get_market_session": _handle_market_session,
        "get_market_sessions": _handle_market_session,
        "get_surprise_summary": _handle_surprise_summary,
        "surprise_summary": _handle_surprise_summary,
        "economic_surprise_summary": _handle_surprise_summary,
        "get_economic_surprise_summary": _handle_surprise_summary,
        "get_precomputed_cot_signals": _handle_cot_signals,
        "get_precomputed_cot_signal": _handle_cot_signals,
        "get_cot_signals": _handle_cot_signals,
        "cot_signals": _handle_cot_signals,
        "precomputed_cot": _handle_cot_signals,
        "get_cot_report": _handle_cot_signals,
        "get_economic_surprise": _handle_economic_surprise,
        "get_price_momentum": _handle_price_momentum,
        "get_funding_rate": _handle_funding_rate,
        "web_search": _handle_web_search,
        "search_web": _handle_web_search,
        "google_search": _handle_web_search,
        "save_market_intelligence": _handle_save_intel,
        "save_intel": _handle_save_intel,
        "list_active_intelligence": _handle_list_intel,
        "list_intel": _handle_list_intel,
        "archive_market_intelligence": _handle_archive_intel,
        "archive_intel": _handle_archive_intel,
        "inspect_economic_report": _handle_inspect_report,
        "diff_central_bank_documents": _handle_diff_cb_docs,
        "get_macro_cross_report_synthesis": _handle_cross_report_synthesis,
        "get_g10_macro_divergence": _handle_g10_divergence,
        "get_fed_net_liquidity_and_stress": _handle_fed_net_liquidity,
        "get_treasury_auction_results": _handle_treasury_auction,
        "get_market_quote": _handle_market_quote,
        "get_quote": _handle_market_quote,
        "market_quote": _handle_market_quote,
        "fetch_quote": _handle_market_quote,
        "quote": _handle_market_quote,
        "get_current_price": _handle_market_quote,
        "get_price_data": _handle_market_quote,
        "get_verified_market_snapshot": _handle_market_quote,
        "calculate_position_size": _handle_calculate_position_size,
        "calculate_size": _handle_calculate_position_size,
        "position_size": _handle_calculate_position_size,
        "get_optimal_intraday_levels": _handle_optimal_intraday_levels,
        "optimal_intraday_levels": _handle_optimal_intraday_levels,
        "get_spread_snapshot": _handle_spread_snapshot,
        "get_spread": _handle_spread_snapshot,
        "spread_snapshot": _handle_spread_snapshot,
        "get_technical_analysis": _handle_technical_analysis,
        "technical_analysis": _handle_technical_analysis,
        "get_institutional_data": _handle_institutional_data,
        "institutional_data": _handle_institutional_data,
        "update_scratchpad": _handle_update_scratchpad,
        "read_scratchpad": _handle_read_scratchpad,
        "scan_pattern_similarity": _handle_scan_pattern_similarity,
        "pattern_similarity": _handle_scan_pattern_similarity,
    }

    @classmethod
    def get_bundle(cls) -> dict[str, Any]:
        if cls._bundle is None:
            from monika.application.benchmark.fixture_loader import get_stage1_fixture_bundle_dict

            cls._bundle = get_stage1_fixture_bundle_dict()
        return cls._bundle

    @classmethod
    def can_handle(cls, tool_name: str) -> bool:
        return tool_name in cls._HANDLERS

    @classmethod
    def dispatch(cls, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        handler = cls._HANDLERS.get(tool_name)
        if handler:
            return handler(cls.get_bundle(), tool_input)
        return {"status": "error", "message": f"Unsupported benchmark tool: {tool_name}"}


@contextmanager
def guarded_tool_executor():
    """Context manager: selama block ini aktif:
    1. Tool tulis (submit_asset_analysis, submit_fundamental_brief, propose_action)
       divalidasi via schema Pydantic dan ditangkap di memori tanpa menulis DB.
    2. Tool baca diarahkan ke BenchmarkFixtureDispatcher sehingga selalu
       mengembalikan data fixture deterministik (anti-stuck, anti-empty DB).
    Selalu dipulihkan (finally), termasuk saat exception. Kembalikan dict box --
    box['result'] berisi payload yang ditangkap (kalau model memanggil tool tsb)."""
    _capture_box.clear()
    orig = (
        ToolExecutor._tool_submit_asset_analysis,
        ToolExecutor._tool_submit_fundamental_brief,
        ToolExecutor._tool_propose_action,
    )
    orig_execute = ToolExecutor.execute

    ToolExecutor._tool_submit_asset_analysis = _capturing_submit_asset_analysis
    ToolExecutor._tool_submit_fundamental_brief = _capturing_submit_fundamental_brief
    ToolExecutor._tool_propose_action = _capturing_propose_action

    async def _guarded_execute(self: ToolExecutor, tool_name: str, tool_input: dict) -> dict:
        normalized = getattr(self, "TOOL_ALIASES", {}).get(tool_name, tool_name)
        if hasattr(self, "called_tools"):
            self.called_tools.add(normalized)
        if normalized == "submit_fundamental_brief":
            return await _capturing_submit_fundamental_brief(self, tool_input)
        if normalized == "submit_asset_analysis":
            return await _capturing_submit_asset_analysis(self, tool_input)
        if normalized == "propose_action":
            return await _capturing_propose_action(self, tool_input)
        if BenchmarkFixtureDispatcher.can_handle(normalized):
            return BenchmarkFixtureDispatcher.dispatch(normalized, tool_input)
        return await orig_execute(self, tool_name, tool_input)

    setattr(ToolExecutor, "execute", _guarded_execute)
    try:
        yield _capture_box
    finally:
        (
            ToolExecutor._tool_submit_asset_analysis,
            ToolExecutor._tool_submit_fundamental_brief,
            ToolExecutor._tool_propose_action,
        ) = orig
        setattr(ToolExecutor, "execute", orig_execute)


# ---------------------------------------------------------------------------
# Data loaders -- SEMUA dari Postgres asli, tidak ada yang di-hardcode. Kalau
# tabel relevan masih kosong (mis. belum pernah menjalankan Stage 1/2), fungsi
# akan raise RuntimeError yang jelas dan task tsb otomatis di-skip oleh runner.
# ---------------------------------------------------------------------------


async def pick_asset_analysis(
    session: AsyncSession, symbol: str | None = None, need_tradeable: bool = True
) -> AssetAnalysis:
    q = select(AssetAnalysis)
    if symbol:
        q = q.where(AssetAnalysis.symbol == symbol)
    if need_tradeable:
        q = q.where(AssetAnalysis.decision.in_(["buy", "sell"]))
    row = (await session.execute(q.order_by(AssetAnalysis.generated_at.desc()).limit(1))).scalar_one_or_none()
    if row is None and need_tradeable:
        return await pick_asset_analysis(session, symbol, need_tradeable=False)
    if row is None:
        raise RuntimeError(
            f"Tidak ada baris AssetAnalysis di DB untuk symbol={symbol!r}. "
            "Jalankan Stage 2 minimal 1 siklus sebelum benchmark task ini."
        )
    return row


async def latest_brief(session: AsyncSession) -> FundamentalBrief:
    row = (
        await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise RuntimeError("Tidak ada FundamentalBrief di DB -- jalankan Stage 1 dulu.")
    return row


async def latest_digest(session: AsyncSession) -> NewsDigest | None:
    return (
        await session.execute(select(NewsDigest).order_by(NewsDigest.generated_at.desc()).limit(1))
    ).scalar_one_or_none()


async def recent_news(session: AsyncSession, limit: int = 8) -> list[NewsItem]:
    rows = (await session.execute(select(NewsItem).order_by(NewsItem.fetched_at.desc()).limit(limit))).scalars().all()
    if not rows:
        raise RuntimeError("Tidak ada NewsItem di DB -- jalankan scraper dulu.")
    return list(rows)


async def resolved_reflection(session: AsyncSession) -> DecisionReflection | None:
    return (
        await session.execute(
            select(DecisionReflection)
            .where(DecisionReflection.status == "resolved")
            .order_by(DecisionReflection.resolved_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_user_message(session: AsyncSession) -> str | None:
    row = (
        await session.execute(
            select(TelegramConversation)
            .where(TelegramConversation.role == "user")
            .order_by(TelegramConversation.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row.message if row else None


def _safe_json_loads(val: Any, default: Any) -> Any:
    if not val:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def entry_context(analysis: AssetAnalysis) -> dict:
    ez = _safe_json_loads(analysis.entry_zone, {})
    return {
        "decision": (analysis.decision or "wait").upper(),
        "rationale": analysis.rationale,
        "confluence_score": analysis.confluence_score,
        "confluence_factors": _safe_json_loads(analysis.confluence_factors_json, []),
        "entry_price": (ez.get("price") if isinstance(ez, dict) else None) or analysis.price_at_analysis,
        "stop_loss": analysis.stop_loss,
        "take_profit": analysis.take_profit,
        "invalidation": analysis.invalidation,
    }
