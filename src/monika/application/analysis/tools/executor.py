# ==============================================================================
# File: analysis/tools/executor.py
# ==============================================================================

"""
Core Tool Executor: Primary engine for routing and executing AI Agent tools.
Integrates decorator-based ToolRegistry, domain handlers, dynamic tool dispatch,
monotonic guards, LFSP condensation, and OpenTelemetry tracing.
"""

import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

from pydantic import ValidationError
from sqlalchemy import and_, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.application.analysis.tools.handlers  # Auto-registers all modular tool handlers
import monika.core.primitives.clock as clock
from monika.application.analysis.schemas.schemas import SubmitAssetAnalysisSchema, SubmitFundamentalBriefSchema
from monika.application.analysis.tools.registry import ToolRegistry, default_tool_registry
from monika.infrastructure.database.models import (
    ActivityLog,
    AssetAnalysis,
    BondYieldData,
    COTReport,
    DXYData,
    EconomicCalendar,
    FedWatchProbability,
    FundamentalBrief,
    FVGZone,
    InterestRate,
    LiquidityZone,
    MarketChronicle,
    NewsDigest,
    NewsItem,
    OrderBlock,
    PaperTradeRecord,
    Position,
    PriceOHLCV,
    RiskState,
    SRZone,
    StructureBreak,
    SwingPoint,
    SystemConfig,
    TechnicalIndicator,
    TelegramConversation,
    TradeTrigger,
    TreasuryYield,
    UserMarketIntel,
    VIXData,
)

logger = logging.getLogger("TradingAgent.ToolExecutor")

FACTOR_POINT_MAP = {
    "fundamental_bias": 2,
    "dxy_confirms": 1,
    "d1_trend": 2,
    "rsi_neutral": 1,
    "near_fvg": 2,
    "near_order_block": 2,
    "in_ote_zone": 1,
    "near_sr_zone": 1,
    "cot_aligned": 1,
    "vix_ok": 1,
    "liquidity_sweep_confirmed": 2,
    "microstructure_ok": 1,
    "microstructure_confirmed": 1,
    "historical_pattern_consensus": 1,
    "pattern_consensus": 1,
    "session_prime": 1,  # modifier tambahan, bukan bagian base-14
    "post_event_entry": 0,  # informational tag, tidak menambah skor
}
FACTOR_CONSISTENCY_TOLERANCE = 1
FACTORS_WITH_VARIABLE_WEIGHT = {"cot_aligned"}


def get_default_registry() -> ToolRegistry:
    return default_tool_registry


from monika.application.analysis.tools.mixins import (
    AssetAnalysisSubmissionMixin,
    AssetAnalysisValidationMixin,
    FundamentalBriefMixin,
    SystemToolsMixin,
    _ToolExecutorMixinBase,
)


class ToolExecutor(
    FundamentalBriefMixin,
    AssetAnalysisValidationMixin,
    AssetAnalysisSubmissionMixin,
    SystemToolsMixin,
    _ToolExecutorMixinBase,
):
    """Engine utama untuk merutekan dan mengeksekusi pemanggilan tool."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Optional[dict] = None,
        model_name: Optional[str] = None,
        prefetch_satisfied_tools: Optional[set] = None,
        symbol: Optional[str] = None,
        registry: Optional[Any] = None,
    ):
        import asyncio

        self.session = session
        self.submit_attempts = 0
        self.called_tools = set()
        self.prefetch_satisfied_tools = set(prefetch_satisfied_tools or set())
        self.monotonic_restrictions = set()
        self.model_name = model_name
        self.symbol = symbol.strip().upper().replace("/", "") if symbol and isinstance(symbol, str) else None
        self._submitted_analysis_id: Optional[int] = None
        self._submitted_brief_id: Optional[int] = None
        self._pending_charts: dict[str, Any] = {}
        self._pending_files: list[dict] = []
        self.verification_ledger: Optional[Any] = None
        self.is_admin: bool = False
        try:
            from monika.infrastructure.llm.data_dedup import DataFetchDeduplicator

            self.deduplicator = DataFetchDeduplicator()
        except Exception:
            self.deduplicator = None
        if session is not None:
            lock = getattr(session, "_session_lock", None)
            if lock is None:
                lock = asyncio.Lock()
                setattr(session, "_session_lock", lock)
            self._session_lock = lock
        else:
            self._session_lock = asyncio.Lock()
        if registry is not None:
            self.registry = registry
        else:
            try:
                from monika.application.analysis.tools.registry import default_tool_registry

                self.registry = default_tool_registry
            except Exception:
                self.registry = None
        if settings is None:
            try:
                from monika.core.config.settings import load_settings

                self.settings = load_settings() or {}
            except Exception:
                self.settings = {}
        else:
            self.settings = settings

        from monika.application.analysis.tools.domain.execution_handlers import ExecutionToolHandlers
        from monika.application.analysis.tools.domain.macro_handlers import MacroToolHandlers
        from monika.application.analysis.tools.domain.position_handlers import PositionToolHandlers
        from monika.application.analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
        from monika.application.analysis.tools.domain.technical_handlers import TechnicalToolHandlers

        self.execution_handlers = ExecutionToolHandlers(self.settings)
        self.position_handlers = PositionToolHandlers(self.settings)
        self.macro_handlers = MacroToolHandlers(self.settings)
        self.sentiment_handlers = SentimentToolHandlers(self.settings)
        self.technical_handlers = TechnicalToolHandlers(self.settings)

    def _resolve_symbol(self, inp: dict) -> str | None:
        """Extract, resolve alias, or fallback to current bound symbol, and normalize."""
        if not isinstance(inp, dict):
            return self.symbol

        sym = inp.get("symbol")
        if not sym:
            for alias in ("asset", "pair", "ticker", "instrument", "symbol_name", "target_asset", "currency_pair"):
                if inp.get(alias):
                    sym = inp[alias]
                    break

        if not sym:
            sym = self.symbol

        if sym and isinstance(sym, str):
            try:
                from monika.domain.market.instrument_identity import resolve_instrument_identity

                clean_sym = resolve_instrument_identity(sym).canonical_symbol
            except Exception:
                clean_sym = sym.strip().upper().replace("/", "")
            inp["symbol"] = clean_sym
            return clean_sym
        return None

    def add_pending_file(
        self, file_path: str, filename: Optional[str] = None, data: Optional[Any] = None, caption: Optional[str] = None
    ) -> None:
        """Queue a file (document/excel/pdf) to be delivered to the user interface."""
        import io
        import os

        if isinstance(filename, (bytes, io.BytesIO)) and data is None:
            data = filename
            filename = os.path.basename(file_path)
        self._pending_files.append(
            {
                "filepath": file_path,
                "filename": filename or os.path.basename(file_path),
                "data": data,
                "caption": caption,
            }
        )

    def pop_pending_files(self) -> list[tuple[str, Any]]:
        """Menguras dan mengembalikan antrean file dokumen sebagai tuple (filename, BytesIO) untuk Telegram delivery."""
        import io
        import os

        result = []
        for item in list(self._pending_files):
            fn = item.get("filename") or os.path.basename(item.get("filepath", "report.dat"))
            raw_bytes = item.get("data")
            if raw_bytes is not None and hasattr(raw_bytes, "getvalue"):
                raw_bytes = getattr(raw_bytes, "getvalue")()
            if not raw_bytes and item.get("filepath") and os.path.exists(item["filepath"]):
                try:
                    with open(item["filepath"], "rb") as f:
                        raw_bytes = f.read()
                except Exception as e:
                    logger.warning(f"Gagal membaca file pending {item['filepath']}: {e}")
                    continue
            if raw_bytes:
                buf = io.BytesIO(raw_bytes)
                buf.name = fn
                result.append((fn, buf))
        self._pending_files.clear()
        return result

    @property
    def effective_called_tools(self) -> set:
        """Union of tools genuinely called this turn AND tools satisfied via prefetch bundle.
        MUST be used instead of self.called_tools for any completeness/compliance validation,
        because a compliant model is explicitly instructed NOT to re-call prefetched tools."""
        return self.called_tools | self.prefetch_satisfied_tools

    async def _get_effective_factor_point_map(self) -> dict:
        """Base FACTOR_POINT_MAP + dynamic overrides dari performance data (clamped >= 0)."""
        effective = dict(FACTOR_POINT_MAP)
        try:
            import json

            cfg = (
                await self.session.execute(
                    select(SystemConfig).where(SystemConfig.key == "dynamic_factor_point_overrides")
                )
            ).scalar_one_or_none()
            if cfg and cfg.value:
                overrides = json.loads(cfg.value).get("overrides", {})
                for factor, delta in overrides.items():
                    if factor in effective:
                        effective[factor] = max(0, effective[factor] + delta)
        except Exception as e:
            logger.debug(f"Effective factor point map load failed (non-fatal, using static): {e}")
        return effective

    async def _get_cached_tool_result(self, tool_name: str, tool_input: dict, cache_hours: int = 4) -> dict | None:
        import json
        from datetime import datetime, timezone

        TOOL_CACHE_HOURS = {
            "get_treasury_yields": 6,
            "get_bond_yield_spreads": 6,
            "get_interest_rates": 24,
            "get_vix": 1,
            "get_dxy": 0.5,
            "get_fedwatch_probabilities": 2,
            "get_cot_report": 12,
            "get_fear_greed_index": 1,
        }
        actual_cache_hours = TOOL_CACHE_HOURS.get(tool_name, cache_hours)

        if not self.session or self.settings.get("_benchmark_mode"):
            return None
        try:
            # Include input in cache key to ensure we don't return wrong filtered results
            cache_key = f"cache_tool_{tool_name}_{json.dumps(tool_input, sort_keys=True)}"
            cfg = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == cache_key))
            ).scalar_one_or_none()

            if cfg and cfg.value:
                try:
                    data = json.loads(cfg.value)
                    from monika.infrastructure.data_ingestion.sources.validators import is_intraday_cache_expired

                    ttl_sec = actual_cache_hours * 3600
                    if not is_intraday_cache_expired(data["timestamp"], ttl_seconds=ttl_sec, now=clock.now()):
                        return data["result"]
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Tool cache lookup failed (non-fatal): {e}")
        return None

    async def _save_tool_cache(self, tool_name: str, tool_input: dict, result: dict):
        if not self.session or self.settings.get("_benchmark_mode"):
            return
        import json
        from datetime import datetime, timezone

        try:
            cache_key = f"cache_tool_{tool_name}_{json.dumps(tool_input, sort_keys=True)}"
            cfg = (
                await self.session.execute(select(SystemConfig).where(SystemConfig.key == cache_key))
            ).scalar_one_or_none()

            data_str = json.dumps({"timestamp": clock.now().isoformat(), "result": result})

            if cfg:
                cfg.value = data_str
            else:
                self.session.add(SystemConfig(key=cache_key, value=data_str))
            await self.session.commit()
        except Exception as e:
            logger.debug(f"Tool cache save failed (non-fatal): {e}")

    def _title_tokens(self, title: str) -> frozenset:
        words = title.lower().split()
        return frozenset(words)

    def _is_similar(self, title: str, seen_sets: list[frozenset], threshold=0.7) -> bool:
        tokens = self._title_tokens(title)
        if not tokens:
            return False
        for seen in seen_sets:
            if not seen:
                continue
            intersection = len(tokens & seen)
            union = len(tokens | seen)
            if union > 0 and intersection / union > threshold:
                return True
        return False

    async def _cleanup_stale_caches(self):
        """Hapus cache entries yang expired."""
        import json

        from sqlalchemy import delete

        now = clock.now()
        cache_rows = (
            (await self.session.execute(select(SystemConfig).where(SystemConfig.key.like("cache_tool_%"))))
            .scalars()
            .all()
        )

        deleted = 0
        for row in cache_rows:
            try:
                if not row.value:
                    await self.session.delete(row)
                    deleted += 1
                    continue
                data = json.loads(row.value)
                cached_time = datetime.fromisoformat(data["timestamp"])
                # Hapus cache yang lebih dari 24 jam
                if (now - cached_time).total_seconds() > 86400:
                    await self.session.delete(row)
                    deleted += 1
            except Exception:
                await self.session.delete(row)
                deleted += 1

        if deleted:
            await self.session.commit()
            logger.debug(f"Cleaned up {deleted} stale tool cache entries")

    TOOL_ALIASES = {
        "submit_fundamental": "submit_fundamental_brief",
        "submit_fundamental_analysis": "submit_fundamental_brief",
        "submit_fundamental_brief_schema": "submit_fundamental_brief",
        "submit_asset": "submit_asset_analysis",
        "submit_trade_analysis": "submit_asset_analysis",
        "submit_asset_analysis_schema": "submit_asset_analysis",
        "get_economic_calendars": "get_economic_calendar",
        "get_calendar": "get_economic_calendar",
        "get_open_position": "get_open_positions",
        "get_positions": "get_open_positions",
        "get_treasury_yield": "get_treasury_yields",
        "get_interest_rate": "get_interest_rates",
        "get_technical_indicator": "get_technical_indicators",
        "get_market_sessions": "get_market_session",
        "get_precomputed_cot_signal": "get_precomputed_cot_signals",
        "get_cot_signals": "get_precomputed_cot_signals",
        "cot_signals": "get_precomputed_cot_signals",
        "precomputed_cot": "get_precomputed_cot_signals",
        "surprise_summary": "get_surprise_summary",
        "economic_surprise_summary": "get_surprise_summary",
        "get_economic_surprise_summary": "get_surprise_summary",
        "get_news_item": "get_news_items",
        "get_news": "get_news_digest",
        "search_web": "web_search",
        "google_search": "web_search",
        "academic_search": "search_academic",
        "arxiv_search": "search_academic",
        "fetch_url": "read_url",
        "url_reader": "read_url",
        "save_intelligence": "save_market_intelligence",
        "save_intel": "save_market_intelligence",
        "list_intelligence": "list_active_intelligence",
        "list_intel": "list_active_intelligence",
        "archive_intel": "archive_market_intelligence",
        "get_quote": "get_market_quote",
        "market_quote": "get_market_quote",
        "fetch_quote": "get_market_quote",
        "quote": "get_market_quote",
        "analytical_query": "run_analytical_query",
        "query_analytics": "run_analytical_query",
        "get_inducement": "get_inducements",
        "inducements": "get_inducements",
        "get_breaker_block": "get_breaker_blocks",
        "breaker_blocks": "get_breaker_blocks",
        "get_equal_highs": "get_equal_highs_lows",
        "get_equal_lows": "get_equal_highs_lows",
        "equal_highs_lows": "get_equal_highs_lows",
        "judas_swing": "get_judas_swing",
        "wick_fvg": "get_wick_to_wick_fvg",
        "wick_to_wick_fvg": "get_wick_to_wick_fvg",
    }

    def _normalize_tool_name(self, raw_name: str) -> str:
        """
        Normalisasi nama tool untuk menangani halusinasi LLM seperti:
        - Duplikasi prefix: submit_submit_fundamental_brief -> submit_fundamental_brief
        - Namespace: tools.get_dxy, functions.get_vix -> get_dxy, get_vix
        - Trailing parentheses: submit_fundamental_brief() -> submit_fundamental_brief
        - Tool aliases / plurals / singulars
        """
        if not raw_name or not isinstance(raw_name, str):
            return ""

        clean = raw_name.strip()
        clean = clean.strip("\"'` ")
        if clean.endswith("()"):
            clean = clean[:-2].strip()

        for ns in ("tools.", "functions.", "tool.", "fn.", "default.", "modules."):
            if clean.startswith(ns):
                clean = clean[len(ns) :].strip()

        for pfx in ("submit_", "get_", "load_", "calculate_"):
            double_pfx = pfx + pfx
            while clean.startswith(double_pfx):
                clean = clean[len(pfx) :]

        if clean.startswith("tool_") and not hasattr(self, f"_tool_{clean}"):
            candidate = clean[5:]
            if hasattr(self, f"_tool_{candidate}"):
                clean = candidate

        if clean in self.TOOL_ALIASES:
            clean = self.TOOL_ALIASES[clean]

        return clean

    def get_tool_schema(self, tool_name: str) -> Optional[dict]:
        """Return tool definition schema for validation (M5)."""
        from monika.application.analysis.tools.tools_definitions import ALL_TOOLS

        normalized = self._normalize_tool_name(tool_name) or tool_name
        for tool in ALL_TOOLS:
            if tool.get("name") in (tool_name, normalized):
                return tool
        return None

    async def execute(self, tool_name: str, tool_input: dict) -> Any:
        """Mendelegasikan nama tool ke fungsi handler spesifik dan mengembalikan dictionary JSON."""
        normalized_name = self._normalize_tool_name(tool_name) or tool_name

        # H2: Programmatic Tool Calling (PTC) execution
        if normalized_name == "execute_analysis_code":
            from monika.application.analysis.tools.handlers.ptc_handler import PTCHandler

            ptc = PTCHandler(tool_executor=self, settings=self.settings)
            code_str = tool_input.get("code", "") if isinstance(tool_input, dict) else str(tool_input)
            return await ptc.execute(code=code_str)

        # Progressive Tool Disclosure Dispatch
        if normalized_name == "search_tools":
            from monika.application.analysis.tools.tool_registry import default_registry

            query = tool_input.get("query", "") if isinstance(tool_input, dict) else str(tool_input)
            limit = int(tool_input.get("limit", 5)) if isinstance(tool_input, dict) else 5
            matches = default_registry.search_tools(query, limit=limit)
            return {"status": "success", "query": query, "matches": matches}

        if normalized_name == "describe_tool":
            from monika.application.analysis.tools.tool_registry import default_registry

            name_to_desc = tool_input.get("tool_name", "") if isinstance(tool_input, dict) else str(tool_input)
            schema = default_registry.describe_tool(name_to_desc)
            if schema:
                return {"status": "success", "tool": schema}
            return {"status": "error", "message": f"Tool '{name_to_desc}' not found in registry."}

        if normalized_name == "load_tool_category":
            from monika.application.analysis.tools.tool_registry import default_registry

            category = tool_input.get("category", "") if isinstance(tool_input, dict) else str(tool_input)
            schemas = default_registry.load_category(category)
            return {
                "status": "success",
                "category": category,
                "loaded_count": len(schemas),
                "tools": [s.get("name") for s in schemas],
                "schemas": schemas,
            }

        # Prefetch Deduplication Check: Return lightweight stub if data was already in prefetch bundle
        if (
            normalized_name in self.prefetch_satisfied_tools
            and isinstance(tool_input, dict)
            and not tool_input.get("force_refresh")
        ):
            logger.info(
                f"[{self.symbol or 'global'}][ToolExecutor] Tool '{normalized_name}' already satisfied in prefetch bundle. Returning lightweight dedup notice."
            )
            self.called_tools.add(normalized_name)
            return {
                "status": "success",
                "tool": normalized_name,
                "message": f"[PREFETCH DEDUP] Tool '{normalized_name}' data was already provided in the pre-fetched bundle. Refer to pre-fetched context.",
            }

        # 1. Monotonic Risk Invariant:
        # Once risk gate denies within a cycle, execution tools cannot override or escalate
        if "risk_denied" in self.monotonic_restrictions and normalized_name in (
            "execute_order_guard",
            "modify_position",
            "execute_market_order",
        ):
            logger.warning(f"Monotonic guard blocked execution of '{normalized_name}' due to prior risk denial.")
            return {
                "error": "MONOTONIC GUARD ENFORCEMENT: Risk denial is monotonic and irrevocable within this cycle. Downstream execution is locked.",
                "status": "denied",
                "risk_denied": True,
            }

        # 2. Read-Before-Act Invariant & Mandatory Tool Enforcement:
        if normalized_name == "submit_asset_analysis":
            DATA_READING_TOOLS = {
                "get_price_history",
                "get_technical_indicators",
                "get_price_momentum",
                "execute_price_data",
                "execute_technical_analysis",
                "get_multi_timeframe_summary",
                "get_verified_market_snapshot",
                "get_price_data",
                "get_technical_analysis",
                "get_market_quote",
            }
            if not (self.effective_called_tools & DATA_READING_TOOLS):
                return {
                    "error": (
                        "MONOTONIC GUARD ENFORCEMENT: Read-before-act policy violated. "
                        "You must read market price/technical data (e.g. via 'get_price_history' or 'get_technical_indicators') "
                        "before submitting asset analysis."
                    ),
                    "status": "blocked",
                    "error_type": "ReadBeforeActViolation",
                }

            # Mandatory tool use: No mental math for position sizing
            decision = str(tool_input.get("decision", "")).lower() if isinstance(tool_input, dict) else ""
            if decision in ("buy", "sell"):
                if "calculate_position_size" not in self.effective_called_tools:
                    return {
                        "error": (
                            "MANDATORY TOOL ENFORCEMENT (<mandatory_tool_use>): Mental calculation of lot size/risk is strictly forbidden. "
                            "You must call 'calculate_position_size' to compute verified lot sizing and risk metrics before submitting buy/sell analysis."
                        ),
                        "status": "blocked",
                        "error_type": "MandatoryToolViolation",
                    }

        self.called_tools.add(normalized_name)

        # 1. Primary dispatch via UnifiedToolRegistry (Single Source of Truth)
        handler = None
        try:
            from monika.application.analysis.tools.unified_registry import unified_tool_registry

            u_entry = unified_tool_registry.get_tool(normalized_name)
            if u_entry is not None:

                async def _unified_wrapper(inp_dict: dict, _ue=u_entry):
                    params = dict(inp_dict) if isinstance(inp_dict, dict) else {}
                    res = await unified_tool_registry.execute_tool(
                        _ue.name, params, session=self.session, executor=self
                    )
                    if isinstance(res, str):
                        try:
                            res = json.loads(res)
                        except Exception:
                            pass
                    return res

                handler = _unified_wrapper
        except Exception as _unif_err:
            logger.debug(f"UnifiedToolRegistry dispatch error for '{normalized_name}': {_unif_err}")

        # 2. Dispatch to modular domain handlers
        if handler is None:
            domain_candidates = [
                self.execution_handlers,
                self.position_handlers,
                self.macro_handlers,
                self.sentiment_handlers,
                self.technical_handlers,
            ]
            for dh in domain_candidates:
                if hasattr(dh, normalized_name):
                    target_func = getattr(dh, normalized_name)

                    async def _delegated_wrapper(inp_dict: dict, _fn=target_func):
                        params = dict(inp_dict) if isinstance(inp_dict, dict) else {}
                        if "session" not in params:
                            params["session"] = self.session
                        return await _fn(**params)

                    handler = _delegated_wrapper
                    break

        # 3. Fallback to internal ToolExecutor methods (lifecycle, scratchpad, submission)
        # Avoid triggering __getattr__ infinite recursion for nonexistent tools
        if handler is None:
            if f"_tool_{normalized_name}" in self.__dict__:
                handler = self.__dict__[f"_tool_{normalized_name}"]
            elif hasattr(self.__class__, f"_tool_{normalized_name}"):
                handler = getattr(self, f"_tool_{normalized_name}")

        # 4. Fallback to modular ToolRegistry auto-discovery
        if handler is None:
            try:
                from monika.application.analysis.tools.registry import default_tool_registry

                reg = getattr(self, "registry", None) or default_tool_registry
                reg_handler = reg.get(normalized_name, settings=self.settings)
                if reg_handler is not None:

                    async def _reg_wrapper(inp_dict: dict, _rh=reg_handler):
                        if hasattr(_rh, "execute"):
                            res = await _rh.execute(inp_dict, self.session, executor=self)
                        elif hasattr(_rh, "handler"):
                            if inspect.iscoroutinefunction(_rh.handler):
                                res = await _rh.handler(**inp_dict)
                            else:
                                res = _rh.handler(**inp_dict)
                        elif callable(_rh):
                            res = _rh(inp_dict)
                        else:
                            res = str(_rh)
                        if isinstance(res, str):
                            try:
                                res = json.loads(res)
                            except Exception:
                                pass
                        return res

                    handler = _reg_wrapper
            except Exception as _reg_err:
                logger.debug(f"Registry dispatch error for '{normalized_name}': {_reg_err}")

        if handler is None:
            logger.warning(f"Unknown tool called: '{tool_name}' (normalized: '{normalized_name}')")
            return {
                "error": f"Unknown tool: '{tool_name}'. Please call one of the valid registered tools.",
                "tool": tool_name,
                "error_type": "UnknownToolError",
                "suggested_action": "Verify tool name and invoke a valid registered tool.",
            }

        if isinstance(tool_input, dict):
            self._resolve_symbol(tool_input)

        cacheable_tools = ["get_treasury_yields", "get_bond_yield_spreads", "get_interest_rates"]

        if normalized_name in cacheable_tools:
            try:
                cached_result = await self._get_cached_tool_result(normalized_name, tool_input)
                if cached_result is not None:
                    logger.debug(f"Tool {normalized_name} returned from cache")
                    return cached_result
            except Exception as ce:
                logger.debug(f"Tool cache lookup non-fatal exception: {ce}")

        session_lock = getattr(self.session, "_session_lock", None) or getattr(self, "_session_lock", None)
        if session_lock is None:
            import asyncio

            session_lock = asyncio.Lock()
            self._session_lock = session_lock
            if self.session is not None:
                setattr(self.session, "_session_lock", session_lock)

        result = None
        max_db_attempts = 2
        import asyncio as _asyncio

        _cur_task = _asyncio.current_task()
        for db_attempt in range(max_db_attempts):
            try:
                if getattr(session_lock, "_owner_task", None) is _cur_task:
                    # Reentrant: current task already holds the lock (nested execute).
                    result = await handler(tool_input)
                else:
                    async with session_lock:
                        setattr(session_lock, "_owner_task", _cur_task)
                        try:
                            result = await handler(tool_input)
                        finally:
                            setattr(session_lock, "_owner_task", None)
                break
            except Exception as e:
                err_text = str(e).lower()
                is_concurrency_error = (
                    "another operation is in progress" in err_text or "cannot perform operation" in err_text
                )
                if is_concurrency_error and db_attempt < max_db_attempts - 1:
                    logger.warning(
                        f"Session contention on tool '{normalized_name}' (attempt {db_attempt + 1}/{max_db_attempts}): {e}. "
                        f"Rolling back and retrying in 50ms..."
                    )
                    if self.session is not None:
                        try:
                            await self.session.rollback()
                        except Exception as rb_err:
                            logger.debug(f"Rollback during retry non-fatal: {rb_err}")
                    import asyncio

                    await asyncio.sleep(0.05)
                    continue

                if self.session is not None:
                    try:
                        await self.session.rollback()
                    except Exception as rb_err:
                        logger.debug(f"Rollback on failure non-fatal: {rb_err}")

                logger.error(f"Tool {normalized_name} failed with {type(e).__name__}: {str(e)[:300]}", exc_info=True)
                return {"error": str(e), "tool": normalized_name, "error_type": type(e).__name__}

        try:
            # Monotonic state update
            if isinstance(result, dict) and (result.get("risk_denied") or result.get("kill_switch_active")):
                self.monotonic_restrictions.add("risk_denied")

            # Write-Then-Readback Verification:
            if normalized_name in ("modify_position", "close_position", "execute_order_guard") and isinstance(
                result, dict
            ):
                if result.get("retcode") == 10009 or result.get("status") in ("success", "executed"):
                    try:
                        readback = await self._tool_get_open_positions({})
                        result["_readback_verified"] = True
                        result["_post_execution_positions"] = readback
                    except Exception as rb_err:
                        logger.debug(f"Write-then-readback check non-fatal error: {rb_err}")

            if self.settings.get("trading", {}).get("caveman_mode", False):
                from monika.infrastructure.llm.caveman_compressor import compress_tool_payload

                result = compress_tool_payload(result)

            if normalized_name in cacheable_tools and isinstance(result, dict) and "error" not in result:
                try:
                    await self._save_tool_cache(normalized_name, tool_input, result)
                except Exception as ce:
                    logger.debug(f"Tool cache save non-fatal exception: {ce}")

            # Tool Observation Condensation & Lossless Financial Structural Projection (LFSP)
            if normalized_name not in ("submit_asset_analysis", "submit_fundamental_brief") and isinstance(
                result, (dict, list)
            ):
                try:
                    from monika.infrastructure.llm.tool_condenser import ToolObservationCondenser

                    condenser = ToolObservationCondenser(self.settings)
                    condensed_str = await condenser.condense_observation(
                        tool_name=normalized_name, tool_output=result, session=self.session, symbol=self.symbol
                    )
                    if isinstance(condensed_str, str) and condensed_str.strip().startswith(("{", "[")):
                        try:
                            result = json.loads(condensed_str)
                        except Exception:
                            result = condensed_str
                    else:
                        result = condensed_str
                except Exception as cond_err:
                    logger.debug(f"Tool observation condenser non-fatal error: {cond_err}")

            if self.deduplicator and result is not None:
                try:
                    res_text = json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)
                    dedup_notice = self.deduplicator.check_and_record(
                        normalized_name, tool_input if isinstance(tool_input, dict) else {}, res_text
                    )
                    if dedup_notice:
                        logger.info(
                            f"[{self.symbol or 'global'}][ToolExecutor] Tool '{normalized_name}' returned duplicate data — deduplicating response."
                        )
                        return {"status": "success", "tool": normalized_name, "message": dedup_notice}
                except Exception as d_err:
                    logger.debug(f"Data deduplicator check non-fatal error: {d_err}")

            logger.debug(f"Tool {normalized_name} executed successfully")
            return result
        except Exception as post_err:
            logger.error(f"Post-processing for tool {normalized_name} failed: {post_err}", exc_info=True)
            return result if result is not None else {"error": str(post_err), "tool": normalized_name}

    # ------------------------------------------------------------------
    # Domain & Execution Tool handlers
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Dynamic dispatch for _tool_* methods to handlers or execute()."""
        if name.startswith("_tool_"):
            raw_name = name[6:]
            tool_name = self._normalize_tool_name(raw_name) or raw_name

            async def _dynamic_tool_caller(*args, **kwargs) -> Any:
                params = {}
                if args and isinstance(args[0], dict):
                    params.update(args[0])
                params.update(kwargs)
                return await self.execute(tool_name, params)

            return _dynamic_tool_caller
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
