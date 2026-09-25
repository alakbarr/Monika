# ==============================================================================
# File: analysis/tools/executor.py
# ==============================================================================

"""
Core Tool Executor: Primary engine for routing and executing AI Agent tools.
Integrates decorator-based ToolRegistry, domain handlers, dynamic tool dispatch,
monotonic guards, LFSP condensation, and OpenTelemetry tracing.
"""

from typing import Any, Dict, Optional, Set
import json
import logging
from pydantic import ValidationError
from analysis.schemas.schemas import SubmitFundamentalBriefSchema, SubmitAssetAnalysisSchema
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, desc, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    NewsItem, EconomicCalendar, TreasuryYield, InterestRate,
    FedWatchProbability, COTReport, VIXData, PriceOHLCV,
    TechnicalIndicator, SwingPoint, SRZone, LiquidityZone, FVGZone,
    FundamentalBrief, AssetAnalysis, TradeTrigger, Position,
    ActivityLog, RiskState, TelegramConversation, OrderBlock, StructureBreak, SystemConfig,
    DXYData, NewsDigest, PaperTradeRecord, BondYieldData,
    UserMarketIntel, MarketChronicle
)

import utils.clock as clock
from analysis.tools.registry import default_tool_registry, ToolRegistry
import analysis.tools.handlers  # Auto-registers all modular tool handlers

logger = logging.getLogger("TradingAgent.ToolExecutor")

FACTOR_POINT_MAP = {
    'fundamental_bias': 2, 'dxy_confirms': 1, 'd1_trend': 2, 'rsi_neutral': 1,
    'near_fvg': 2, 'near_order_block': 2, 'in_ote_zone': 1, 'near_sr_zone': 1,
    'cot_aligned': 1, 'vix_ok': 1, 'liquidity_sweep_confirmed': 2,
    'session_prime': 1,       # modifier tambahan, bukan bagian base-14
    'post_event_entry': 0,    # informational tag, tidak menambah skor
}
FACTOR_CONSISTENCY_TOLERANCE = 1
FACTORS_WITH_VARIABLE_WEIGHT = {'cot_aligned'}


def get_default_registry() -> ToolRegistry:
    return default_tool_registry

class ToolExecutor:
    """Engine utama untuk merutekan dan mengeksekusi pemanggilan tool."""

    def __init__(self, session: AsyncSession, settings: Optional[dict] = None, model_name: Optional[str] = None, prefetch_satisfied_tools: Optional[set] = None, symbol: Optional[str] = None, registry: Optional[Any] = None):
        import asyncio
        self.session = session
        self.submit_attempts = 0
        self.called_tools = set()
        self.prefetch_satisfied_tools = set(prefetch_satisfied_tools or set())
        self.monotonic_restrictions = set()
        self.model_name = model_name
        self.symbol = symbol.strip().upper().replace('/', '') if symbol and isinstance(symbol, str) else None
        self._submitted_analysis_id: Optional[int] = None
        self._submitted_brief_id: Optional[int] = None
        self._pending_charts: dict[str, Any] = {}
        self.verification_ledger: Optional[Any] = None
        self.is_admin: bool = False
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
                from analysis.tools.registry import default_tool_registry
                self.registry = default_tool_registry
            except Exception:
                self.registry = None
        if settings is None:
            import yaml
            import os
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                with open(os.path.join(base_dir, 'config', 'settings.yaml'), 'r') as f:
                    self.settings = yaml.safe_load(f)
            except Exception:
                self.settings = {}
        else:
            self.settings = settings

        from analysis.tools.domain.execution_handlers import ExecutionToolHandlers
        from analysis.tools.domain.position_handlers import PositionToolHandlers
        from analysis.tools.domain.macro_handlers import MacroToolHandlers
        from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
        from analysis.tools.domain.technical_handlers import TechnicalToolHandlers

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
                from utils.market.instrument_identity import resolve_instrument_identity
                clean_sym = resolve_instrument_identity(sym).canonical_symbol
            except Exception:
                clean_sym = sym.strip().upper().replace('/', '')
            inp["symbol"] = clean_sym
            return clean_sym
        return None

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
            cfg = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == 'dynamic_factor_point_overrides')
            )).scalar_one_or_none()
            if cfg and cfg.value:
                overrides = json.loads(cfg.value).get('overrides', {})
                for factor, delta in overrides.items():
                    if factor in effective:
                        effective[factor] = max(0, effective[factor] + delta)
        except Exception as e:
            logger.debug(f'Effective factor point map load failed (non-fatal, using static): {e}')
        return effective

    async def _get_cached_tool_result(self, tool_name: str, tool_input: dict, cache_hours: int = 4) -> dict | None:
        import json
        from datetime import datetime, timezone
        TOOL_CACHE_HOURS = {
            'get_treasury_yields': 6,
            'get_bond_yield_spreads': 6,
            'get_interest_rates': 24,
            'get_vix': 1,
            'get_dxy': 0.5,
            'get_fedwatch_probabilities': 2,
            'get_cot_report': 12,
            'get_fear_greed_index': 1,
        }
        actual_cache_hours = TOOL_CACHE_HOURS.get(tool_name, cache_hours)
        
        # Include input in cache key to ensure we don't return wrong filtered results
        cache_key = f"cache_tool_{tool_name}_{json.dumps(tool_input, sort_keys=True)}"
        cfg = (await self.session.execute(select(SystemConfig).where(SystemConfig.key == cache_key))).scalar_one_or_none()
        
        if cfg and cfg.value:
            try:
                data = json.loads(cfg.value)
                from data_sources.validators import is_intraday_cache_expired
                ttl_sec = actual_cache_hours * 3600
                if not is_intraday_cache_expired(data["timestamp"], ttl_seconds=ttl_sec, now=clock.now()):
                    return data["result"]
            except Exception:
                pass
        return None

    async def _save_tool_cache(self, tool_name: str, tool_input: dict, result: dict):
        import json
        from datetime import datetime, timezone
        cache_key = f"cache_tool_{tool_name}_{json.dumps(tool_input, sort_keys=True)}"
        cfg = (await self.session.execute(select(SystemConfig).where(SystemConfig.key == cache_key))).scalar_one_or_none()
        
        data_str = json.dumps({
            "timestamp": clock.now().isoformat(),
            "result": result
        })
        
        if cfg:
            cfg.value = data_str
        else:
            self.session.add(SystemConfig(key=cache_key, value=data_str))
        await self.session.commit()


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
        from sqlalchemy import delete
        import json
        
        now = clock.now()
        cache_rows = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key.like('cache_tool_%'))
        )).scalars().all()
        
        deleted = 0
        for row in cache_rows:
            try:
                if not row.value:
                    await self.session.delete(row)
                    deleted += 1
                    continue
                data = json.loads(row.value)
                cached_time = datetime.fromisoformat(data['timestamp'])
                # Hapus cache yang lebih dari 24 jam
                if (now - cached_time).total_seconds() > 86400:
                    await self.session.delete(row)
                    deleted += 1
            except Exception:
                await self.session.delete(row)
                deleted += 1
        
        if deleted:
            await self.session.commit()
            logger.debug(f'Cleaned up {deleted} stale tool cache entries')

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
                clean = clean[len(ns):].strip()

        for pfx in ("submit_", "get_", "load_", "calculate_"):
            double_pfx = pfx + pfx
            while clean.startswith(double_pfx):
                clean = clean[len(pfx):]

        if clean.startswith("tool_") and not hasattr(self, f"_tool_{clean}"):
            candidate = clean[5:]
            if hasattr(self, f"_tool_{candidate}"):
                clean = candidate

        if clean in self.TOOL_ALIASES:
            clean = self.TOOL_ALIASES[clean]

        return clean

    def get_tool_schema(self, tool_name: str) -> Optional[dict]:
        """Return tool definition schema for validation (M5 / Pi pattern)."""
        from analysis.tools.tools_definitions import ALL_TOOLS
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
            from analysis.tools.handlers.ptc_handler import PTCHandler
            ptc = PTCHandler(tool_executor=self, settings=self.settings)
            code_str = tool_input.get("code", "") if isinstance(tool_input, dict) else str(tool_input)
            return await ptc.execute(code=code_str)

        # Progressive Tool Disclosure Dispatch
        if normalized_name == "search_tools":
            from analysis.tools.tool_registry import default_registry
            query = tool_input.get("query", "") if isinstance(tool_input, dict) else str(tool_input)
            limit = int(tool_input.get("limit", 5)) if isinstance(tool_input, dict) else 5
            matches = default_registry.search_tools(query, limit=limit)
            return {"status": "success", "query": query, "matches": matches}

        if normalized_name == "describe_tool":
            from analysis.tools.tool_registry import default_registry
            name_to_desc = tool_input.get("tool_name", "") if isinstance(tool_input, dict) else str(tool_input)
            schema = default_registry.describe_tool(name_to_desc)
            if schema:
                return {"status": "success", "tool": schema}
            return {"status": "error", "message": f"Tool '{name_to_desc}' not found in registry."}

        if normalized_name == "load_tool_category":
            from analysis.tools.tool_registry import default_registry
            category = tool_input.get("category", "") if isinstance(tool_input, dict) else str(tool_input)
            schemas = default_registry.load_category(category)
            return {
                "status": "success",
                "category": category,
                "loaded_count": len(schemas),
                "tools": [s.get("name") for s in schemas],
                "schemas": schemas,
            }

        # 1. Monotonic Risk Invariant:
        # Once risk gate denies within a cycle, execution tools cannot override or escalate
        if "risk_denied" in self.monotonic_restrictions and normalized_name in ("execute_order_guard", "modify_position", "execute_market_order"):
            logger.warning(f"Monotonic guard blocked execution of '{normalized_name}' due to prior risk denial.")
            return {
                "error": "MONOTONIC GUARD ENFORCEMENT: Risk denial is monotonic and irrevocable within this cycle. Downstream execution is locked.",
                "status": "denied",
                "risk_denied": True
            }

        # 2. Read-Before-Act Invariant & Mandatory Tool Enforcement:
        if normalized_name == "submit_asset_analysis":
            DATA_READING_TOOLS = {
                "get_price_history", "get_technical_indicators", "get_price_momentum",
                "execute_price_data", "execute_technical_analysis", "get_multi_timeframe_summary",
                "get_verified_market_snapshot", "get_price_data", "get_technical_analysis",
                "get_market_quote"
            }
            if not (self.effective_called_tools & DATA_READING_TOOLS):
                return {
                    "error": (
                        "MONOTONIC GUARD ENFORCEMENT: Read-before-act policy violated. "
                        "You must read market price/technical data (e.g. via 'get_price_history' or 'get_technical_indicators') "
                        "before submitting asset analysis."
                    ),
                    "status": "blocked",
                    "error_type": "ReadBeforeActViolation"
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
                        "error_type": "MandatoryToolViolation"
                    }

        self.called_tools.add(normalized_name)

        # Primary dispatch to modular domain handlers (CRITICAL-03)
        handler = None
        domain_candidates = [
            self.execution_handlers,
            self.position_handlers,
            self.macro_handlers,
            self.sentiment_handlers,
            self.technical_handlers
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

        # Fallback to internal ToolExecutor methods (lifecycle, scratchpad, submission)
        # Avoid triggering __getattr__ infinite recursion for nonexistent tools
        if handler is None:
            if f"_tool_{normalized_name}" in self.__dict__:
                handler = self.__dict__[f"_tool_{normalized_name}"]
            elif hasattr(self.__class__, f"_tool_{normalized_name}"):
                handler = getattr(self, f"_tool_{normalized_name}")

        # Fallback to modular ToolRegistry auto-discovery (CRITICAL-01)
        if handler is None:
            try:
                from analysis.tools.registry import default_tool_registry
                reg = getattr(self, "registry", None) or default_tool_registry
                reg_handler = reg.get(normalized_name, settings=self.settings)
                if reg_handler is not None:
                    async def _reg_wrapper(inp_dict: dict, _rh=reg_handler):
                        res = await _rh.execute(inp_dict, self.session, executor=self)
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
                "suggested_action": "Verify tool name and invoke a valid registered tool."
            }

        if isinstance(tool_input, dict):
            self._resolve_symbol(tool_input)

        cacheable_tools = ["get_treasury_yields", "get_bond_yield_spreads", "get_interest_rates"]
        
        if normalized_name in cacheable_tools:
            cached_result = await self._get_cached_tool_result(normalized_name, tool_input)
            if cached_result is not None:
                logger.debug(f"Tool {normalized_name} returned from cache")
                return cached_result

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
                    "another operation is in progress" in err_text
                    or "cannot perform operation" in err_text
                )
                if is_concurrency_error and db_attempt < max_db_attempts - 1:
                    logger.warning(
                        f"Session contention on tool '{normalized_name}' (attempt {db_attempt+1}/{max_db_attempts}): {e}. "
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
            if normalized_name in ("modify_position", "close_position", "execute_order_guard") and isinstance(result, dict):
                if result.get("retcode") == 10009 or result.get("status") in ("success", "executed"):
                    try:
                        readback = await self._tool_get_open_positions({})
                        result["_readback_verified"] = True
                        result["_post_execution_positions"] = readback
                    except Exception as rb_err:
                        logger.debug(f"Write-then-readback check non-fatal error: {rb_err}")

            if self.settings.get("trading", {}).get("caveman_mode", False):
                from utils.llm.caveman_compressor import compress_tool_payload
                result = compress_tool_payload(result)
            
            if normalized_name in cacheable_tools and isinstance(result, dict) and "error" not in result:
                await self._save_tool_cache(normalized_name, tool_input, result)

            # Pi-Condense Pattern & Lossless Financial Structural Projection (LFSP)
            if normalized_name not in ("submit_asset_analysis", "submit_fundamental_brief") and isinstance(result, (dict, list)):
                try:
                    from utils.llm.tool_condenser import ToolObservationCondenser
                    condenser = ToolObservationCondenser(self.settings)
                    condensed_str = await condenser.condense_observation(
                        tool_name=normalized_name,
                        tool_output=result,
                        session=self.session,
                        symbol=self.symbol
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
                
            logger.debug(f"Tool {normalized_name} executed successfully")
            return result
        except Exception as post_err:
            logger.error(f"Post-processing for tool {normalized_name} failed: {post_err}", exc_info=True)
            return result if result is not None else {"error": str(post_err), "tool": normalized_name}

    # ------------------------------------------------------------------
    # Domain & Execution Tool handlers
    # ------------------------------------------------------------------

    async def _tool_get_verified_market_snapshot(self, inp: dict) -> dict:
        """Deterministic ground-truth market snapshot (anti-hallucination anchor)."""
        from analysis.tools.handlers.verified_snapshot import VerifiedMarketSnapshotHandler
        handler = VerifiedMarketSnapshotHandler(self.settings)
        res = await handler.execute(inp, self.session, executor=self)
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                return {"raw_snapshot": res}
        return res if isinstance(res, dict) else {"snapshot": res}

    async def _tool_execute_analysis_code(self, inp: dict) -> dict:
        """Execute sandboxed Python code with tool access (PTC)."""
        from analysis.tools.handlers.ptc_handler import PTCHandler
        ptc = PTCHandler(tool_executor=self, settings=self.settings)
        code_str = inp.get("code", "") if isinstance(inp, dict) else str(inp)
        return await ptc.execute(code=code_str)

    async def _tool_update_scratchpad(self, inp: dict) -> dict:
        """Updates active working scratchpad with intermediate calculation anchors."""
        symbol = self._resolve_symbol(inp) or self.symbol or "DEFAULT"
        from analysis.memory.working_scratchpad import WorkingScratchpad
        updated = WorkingScratchpad.update_scratchpad(symbol, inp)
        summary = WorkingScratchpad.get_summary_text(symbol)
        return {
            "status": "success",
            "message": f"Scratchpad for {symbol} updated successfully.",
            "summary": summary,
            "scratchpad": updated
        }

    async def _tool_read_scratchpad(self, inp: dict) -> dict:
        """Reads active working scratchpad anchors for the current analysis session."""
        symbol = self._resolve_symbol(inp) or self.symbol or "DEFAULT"
        from analysis.memory.working_scratchpad import WorkingScratchpad
        state = WorkingScratchpad.read_scratchpad(symbol)
        summary = WorkingScratchpad.get_summary_text(symbol)
        return {
            "status": "success",
            "symbol": symbol,
            "summary": summary,
            "scratchpad": state
        }

    async def _tool_transition_analysis_phase(self, inp: dict) -> dict:
        """Records explicit phase advancement request."""
        target_phase = int(inp.get("target_phase", 2))
        rationale = inp.get("rationale", "")
        return {
            "status": "success",
            "target_phase": target_phase,
            "rationale": rationale,
            "message": f"Phase transition to Phase {target_phase} acknowledged. Unlocking phase tools."
        }


    async def _tool_get_timesfm_forecast(self, *args, **kwargs) -> dict:
        """Forecast future price distribution using TimesFM foundation model."""
        from analysis.tools.handlers.timesfm import handle_get_timesfm_forecast
        inp = {}
        if args:
            if isinstance(args[0], dict):
                inp = dict(args[0])
            else:
                inp["symbol"] = args[0]
                if len(args) > 1:
                    inp["timeframe"] = args[1]
                if len(args) > 2:
                    inp["horizon_steps"] = args[2]
        inp.update(kwargs)
        if "horizon" in inp and "horizon_steps" not in inp:
            inp["horizon_steps"] = inp.pop("horizon")
        return await handle_get_timesfm_forecast(executor=self, session=self.session, settings=self.settings, **inp)

    async def _tool_get_paper_trading_performance(self, inp: dict) -> dict:
        from utils.analytics.paper_tracker import PaperTracker
        days_back = int(inp["days_back"]) if inp.get("days_back") is not None else None
        tracker = PaperTracker(self.settings)
        stats = await tracker.get_statistics(self.session, days_back=days_back)
        equity_curve = await tracker.simulate_equity_curve(self.session)
        suspended = await tracker.get_suspended_symbols(self.session)

        return {
            "period": f"Past {days_back} days" if days_back else "All-time",
            "total_trades": stats.get("total_trades", 0),
            "market_trades": stats.get("market_trades", 0),
            "wins": stats.get("wins", 0),
            "losses": stats.get("losses", 0),
            "win_rate_pct": stats.get("win_rate_pct", 0),
            "total_pnl_pct": stats.get("total_pnl_pct", 0),
            "avg_pnl_pct": stats.get("avg_pnl_pct", 0),
            "avg_win_pct": stats.get("avg_win_pct", 0),
            "avg_loss_pct": stats.get("avg_loss_pct", 0),
            "avg_rr_achieved": stats.get("avg_rr_achieved", 0),
            "expectancy_per_trade_R": stats.get("expectancy_per_trade_R", 0),
            "expectancy_per_trade_pct": stats.get("expectancy_per_trade_pct", 0),
            "has_positive_edge": stats.get("has_positive_edge", False),
            "suspended_symbols": suspended,
            "by_symbol": stats.get("by_symbol", {}),
            "simulated_equity": {
                "starting_equity": equity_curve.get("starting_equity", 10000.0),
                "final_equity": equity_curve.get("final_equity", 10000.0),
                "total_return_pct": equity_curve.get("total_return_pct", 0.0),
                "max_drawdown_pct": equity_curve.get("max_drawdown_pct", 0.0),
            } if equity_curve else None,
            "recent_trades": stats.get("recent_20", [])[-10:],
        }

    async def _tool_get_trade_history(self, inp: dict) -> dict:
        symbol = inp.get("symbol")
        if symbol:
            symbol = symbol.upper().replace('/', '')
        status = inp.get("status", "closed")
        mode = inp.get("mode", "all")
        limit = min(inp.get("limit", 10), 50)
        days_back = inp.get("days_back")

        trades = []

        if mode in ("all", "paper"):
            q_paper = select(PaperTradeRecord)
            if symbol:
                q_paper = q_paper.where(PaperTradeRecord.symbol == symbol)
            if status != "all":
                q_paper = q_paper.where(PaperTradeRecord.status == status)
            if days_back:
                cutoff = clock.now() - timedelta(days=days_back)
                q_paper = q_paper.where(PaperTradeRecord.closed_at >= cutoff)
            q_paper = q_paper.order_by(PaperTradeRecord.opened_at.desc()).limit(limit)

            paper_rows = (await self.session.execute(q_paper)).scalars().all()
            for r in paper_rows:
                trades.append({
                    "id": r.id,
                    "type": "paper",
                    "symbol": r.symbol,
                    "direction": r.direction,
                    "entry_price": r.entry_price,
                    "exit_price": r.exit_price,
                    "stop_loss": r.stop_loss,
                    "take_profit": r.take_profit,
                    "status": r.status,
                    "exit_reason": r.exit_reason,
                    "pnl_pct": r.pnl_pct,
                    "holding_hours": r.holding_hours,
                    "opened_at": r.opened_at.isoformat() if r.opened_at is not None else "",
                    "closed_at": r.closed_at.isoformat() if r.closed_at is not None else "",
                    "analysis_id": getattr(r, "analysis_id", None),
                })

        if mode in ("all", "live"):
            q_live = select(Position)
            if symbol:
                q_live = q_live.where(Position.symbol == symbol)
            if status != "all":
                q_live = q_live.where(Position.status == status)
            if days_back:
                cutoff = clock.now() - timedelta(days=days_back)
                q_live = q_live.where(Position.opened_at >= cutoff)
            q_live = q_live.order_by(Position.opened_at.desc()).limit(limit)

            live_rows = (await self.session.execute(q_live)).scalars().all()
            for r in live_rows:
                trades.append({
                    "id": r.id,
                    "type": "live",
                    "mt5_ticket": r.mt5_ticket,
                    "symbol": r.symbol,
                    "direction": r.direction,
                    "volume": r.volume,
                    "entry_price": r.entry_price,
                    "exit_price": getattr(r, 'exit_price', None),
                    "stop_loss": r.sl,
                    "take_profit": r.tp,
                    "status": r.status,
                    "exit_reason": getattr(r, 'close_reason', None),
                    "pnl": r.pnl,
                    "opened_at": r.opened_at.isoformat() if r.opened_at is not None else "",
                    "closed_at": r.closed_at.isoformat() if r.closed_at is not None else "",
                })

        trades.sort(key=lambda x: x.get("opened_at") or "", reverse=True)
        trades = trades[:limit]

        return {
            "count": len(trades),
            "trades": trades,
        }

    async def _tool_get_active_triggers(self, inp: dict) -> dict:
        symbol = inp.get("symbol")
        if symbol:
            symbol = symbol.upper().replace('/', '')
        status = inp.get("status", "pending")
        limit = min(inp.get("limit", 10), 50)

        q = (
            select(TradeTrigger, AssetAnalysis)
            .join(AssetAnalysis, TradeTrigger.asset_analysis_id == AssetAnalysis.id)
        )
        if symbol:
            q = q.where(AssetAnalysis.symbol == symbol)
        if status != "all":
            q = q.where(TradeTrigger.status == status)

        q = q.order_by(TradeTrigger.created_at.desc()).limit(limit)
        results = (await self.session.execute(q)).all()

        triggers = []
        for trigger, analysis in results:
            last_bar = (await self.session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == analysis.symbol)
                .where(PriceOHLCV.timestamp <= clock.now())
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            current_price = last_bar.close if last_bar else None

            import json as _j
            cond = {}
            try:
                cond = _j.loads(trigger.condition_json) if trigger.condition_json else {}
            except Exception:
                pass

            price_distance = None
            target_level = cond.get("price") or cond.get("price_level") or analysis.invalidation_price
            if current_price and target_level:
                try:
                    price_distance = round(abs(current_price - float(target_level)), 5)
                except Exception:
                    pass

            triggers.append({
                "trigger_id": trigger.id,
                "symbol": analysis.symbol,
                "trigger_type": trigger.trigger_type,
                "status": trigger.status,
                "condition": cond,
                "analysis_id": analysis.id,
                "decision": analysis.decision,
                "confidence": analysis.confidence,
                "current_price": current_price,
                "target_level": target_level,
                "price_distance": price_distance,
                "created_at": trigger.created_at.isoformat() if hasattr(trigger.created_at, "isoformat") else str(trigger.created_at or ""),
            })

        return {
            "count": len(triggers),
            "triggers": triggers,
        }

    async def _tool_get_system_health(self, inp: dict) -> dict:
        today_start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
        risk = (await self.session.execute(
            select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
        )).scalar_one_or_none()

        last_brief = (await self.session.execute(
            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
        )).scalar_one_or_none()

        cutoff_err = clock.now() - timedelta(hours=2)
        recent_errors = (await self.session.execute(
            select(ActivityLog)
            .where(ActivityLog.timestamp >= cutoff_err)
            .where(ActivityLog.category.in_(["error", "system_error", "exception"]))
            .order_by(ActivityLog.timestamp.desc())
            .limit(5)
        )).scalars().all()

        mode = "live" if not self.settings.get("paper_trading", {}).get("enabled", True) else "paper"
        trading_paused = risk.trading_paused if risk else False

        return {
            "status": "PAUSED" if trading_paused else ("DEGRADED" if recent_errors else "HEALTHY"),
            "trading_paused": trading_paused,
            "mode": mode,
            "daily_pnl": risk.daily_pnl if risk else 0.0,
            "current_drawdown": risk.current_drawdown if risk else 0.0,
            "last_brief_time": last_brief.generated_at.isoformat() if last_brief and hasattr(last_brief.generated_at, "isoformat") else (str(last_brief.generated_at) if last_brief else None),
            "recent_error_count": len(recent_errors),
        }

    async def _tool_get_open_positions(self, inp: dict) -> dict:
        mode = inp.get("mode", "all")
        symbol = inp.get("symbol")
        if symbol:
            symbol = symbol.upper().replace('/', '')

        positions = []

        if mode in ("all", "live"):
            q_pos = select(Position).where(Position.status == "open")
            if symbol:
                q_pos = q_pos.where(Position.symbol == symbol)
            live_rows = (await self.session.execute(q_pos)).scalars().all()
            for r in live_rows:
                positions.append({
                    "id": r.id,
                    "type": "live",
                    "mt5_ticket": r.mt5_ticket,
                    "symbol": r.symbol,
                    "direction": r.direction,
                    "volume": r.volume,
                    "entry_price": r.entry_price,
                    "sl": r.sl,
                    "tp": r.tp,
                    "opened_at": r.opened_at.isoformat() if hasattr(r.opened_at, "isoformat") else str(r.opened_at or ""),
                    "pnl": r.pnl,
                })

        if mode in ("all", "paper"):
            q_paper = select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
            if symbol:
                q_paper = q_paper.where(PaperTradeRecord.symbol == symbol)
            paper_rows = (await self.session.execute(q_paper)).scalars().all()
            for r in paper_rows:
                last_bar = (await self.session.execute(
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == r.symbol)
                    .where(PriceOHLCV.timestamp <= clock.now())
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(1)
                )).scalar_one_or_none()
                floating_pnl_pct = 0.0
                if last_bar and r.entry_price:
                    if r.direction == "buy":
                        floating_pnl_pct = round((last_bar.close - r.entry_price) / r.entry_price * 100, 3)
                    else:
                        floating_pnl_pct = round((r.entry_price - last_bar.close) / r.entry_price * 100, 3)
                positions.append({
                    "id": r.id,
                    "type": "paper",
                    "symbol": r.symbol,
                    "direction": r.direction,
                    "entry_price": r.entry_price,
                    "sl": r.stop_loss,
                    "tp": r.take_profit,
                    "opened_at": r.opened_at.isoformat() if hasattr(r.opened_at, "isoformat") else str(r.opened_at or ""),
                    "floating_pnl_pct": floating_pnl_pct,
                })

        return {
            "count": len(positions),
            "positions": positions,
        }

    async def _tool_get_spread_snapshot(self, inp: dict) -> dict:
        from analysis.tools.handlers.market_data_tools import handle_get_spread_snapshot
        return await handle_get_spread_snapshot(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_multi_timeframe_summary(self, inp: dict) -> dict:
        from analysis.tools.handlers.market_data_tools import handle_get_multi_timeframe_summary
        return await handle_get_multi_timeframe_summary(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_chart(self, inp: dict) -> dict:
        from analysis.tools.handlers.market_data_tools import handle_get_chart
        return await handle_get_chart(inp, session=self.session, executor=self, settings=self.settings)

    async def _tool_get_fibonacci_levels(self, inp: dict) -> dict:
        from analysis.tools.handlers.market_data_tools import handle_get_fibonacci_levels
        return await handle_get_fibonacci_levels(inp, session=self.session, executor=self, settings=self.settings)


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


    async def _validate_fundamental_brief_completeness(self, inp: dict) -> list[str]:
        """Check if fundamental brief contains all required analysis components."""
        errors = []
        narrative = inp.get('macro_narrative', '').lower()
        
        # Check DXY explicitly
        if 'dxy' not in narrative and 'dollar index' not in narrative and 'usd' not in narrative:
            errors.append("MISSING_DXY_ANALYSIS: You must explicitly mention DXY and its implications.")
        if "get_dxy" not in self.effective_called_tools:
            dxy_uncertain = "dxy uncertain" in narrative or "dxy unavailable" in narrative or "dollar uncertain" in narrative
            if not dxy_uncertain:
                errors.append("MISSING_TOOL: You MUST call 'get_dxy' before submitting the fundamental brief.")
            
        # Check VIX explicitly
        if 'vix' not in narrative and 'risk sentiment' not in narrative and 'risk-on' not in narrative and 'risk-off' not in narrative:
            errors.append("MISSING_VIX_ANALYSIS: You must explicitly mention VIX or Risk Sentiment.")
        if "get_vix" not in self.effective_called_tools:
            vix_uncertain = "vix uncertain" in narrative or "vix unavailable" in narrative or "sentiment uncertain" in narrative
            if not vix_uncertain:
                errors.append("MISSING_TOOL: You MUST call 'get_vix' before submitting the fundamental brief.")
            
        # Check Currency Bias completeness
        bias = inp.get('currency_bias', {})
        required = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'XAU']
        asset_universe = self.settings.get('trading', {}).get('asset_universe', [])
        if 'XTIUSD' in asset_universe:
            required.append('OIL')
        if 'BTCUSD' in asset_universe:
            required.append('BTC')
        missing_bias = [c for c in required if c not in bias]
        if missing_bias:
            errors.append(f"MISSING_CURRENCY_BIAS: Missing explicit bias for {', '.join(missing_bias)}.")
            
        non_neutral_currencies = [c for c, b in bias.items() if b != 'neutral']
        invalidation_map = inp.get('invalidation_conditions', {})
        missing_invalidation = [c for c in non_neutral_currencies if c not in invalidation_map]
        if missing_invalidation:
            errors.append(f"MISSING_INVALIDATION: currency dengan bias terarah (bukan neutral) WAJIB punya invalidation_conditions. Kurang untuk: {missing_invalidation}")

        weak_invalidation = []
        for c in non_neutral_currencies:
            cond_text = str(invalidation_map.get(c, ''))
            has_number = any(ch.isdigit() for ch in cond_text)
            if cond_text and (len(cond_text) < 40 or not has_number):
                weak_invalidation.append(c)
        if weak_invalidation:
            errors.append(
                f"WEAK_INVALIDATION: invalidation_conditions untuk {weak_invalidation} terlalu generik "
                f"atau tidak mengandung level harga/angka spesifik (WAJIB >= 40 karakter dan memuat angka konkret). "
                f"Contoh baik: 'Bias {weak_invalidation[0]} bearish batal jika harga break di atas level 78.50 ATAU inventory draw > 3.5M barrels'."
            )

        confidence_map = inp.get('currency_confidence', {})
        missing_conf = [c for c in non_neutral_currencies if c not in confidence_map]
        if missing_conf:
            errors.append(f"MISSING_CONFIDENCE: currency dengan bias terarah WAJIB punya currency_confidence (0.0-1.0). Kurang untuk: {missing_conf}")
            
        if not inp.get('strongest_counter_thesis'):
            errors.append("MISSING_COUNTER_THESIS: Anda WAJIB memberikan strongest_counter_thesis yang valid.")
        elif len(inp.get('strongest_counter_thesis', '')) < 50:
            errors.append("WEAK_COUNTER_THESIS: strongest_counter_thesis terlalu pendek, sebutkan data/skenario makro spesifik yang bisa membatalkan tesis Anda.")

        # NEW P2-4: Check priced_in_assessment completeness
        pi = inp.get('priced_in_assessment', {})
        if not pi:
            errors.append("MISSING_PRICED_IN: Field 'priced_in_assessment' tidak boleh kosong. Gunakan data aktual dari get_cot_report dan get_fedwatch_probabilities.")
        else:
            is_weekend = clock.now().weekday() >= 5
            has_cot = pi.get('cot_positioning_percentile') is not None
            has_retail = pi.get('retail_sentiment_percentile') is not None
            has_crypto_sentiment = (
                pi.get('funding_rate') is not None or 
                pi.get('fear_greed_score') is not None or 
                pi.get('crypto_sentiment') is not None
            )
            
            # If missing during weekday, attempt auto-fill from macro_priced_in_baseline
            if not has_cot and not has_retail and not (is_weekend and (has_crypto_sentiment or pi.get('dominant_driver'))):
                try:
                    from analysis.calculators.macro_priced_in_calculator import calculate_macro_priced_in_baseline
                    baseline = await calculate_macro_priced_in_baseline(self.session)
                    if baseline.get('cot_positioning_percentile') is not None:
                        pi['cot_positioning_percentile'] = baseline['cot_positioning_percentile']
                        has_cot = True
                        logger.info(f"Auto-filled cot_positioning_percentile={baseline['cot_positioning_percentile']} from baseline")
                except Exception as _pi_err:
                    logger.debug(f"Auto-fill baseline failed: {_pi_err}")

            if not has_cot and not has_retail and not (is_weekend and (has_crypto_sentiment or pi.get('dominant_driver'))):
                errors.append("INCOMPLETE_PRICED_IN: Harus mencantumkan metrik numerik nyata (misal cot_positioning_percentile atau retail_sentiment_percentile) hasil fetch tools.")
            if not pi.get('sell_the_news_risk'):
                errors.append("INCOMPLETE_PRICED_IN: 'sell_the_news_risk' wajib diisi (high/medium/low).")
            
            # P1: Phase 2.6 - Tempering currency_confidence saat priced-in tinggi
            if pi.get('priced_in_score', 0) >= 8:
                dominant_driver_text = (pi.get('dominant_driver') or '').upper()
                currency_conf = inp.get('currency_confidence', {})
                for cur, conf in currency_conf.items():
                    if cur in dominant_driver_text and conf > 0.65:
                        errors.append(f"PRICED_IN_CONFIDENCE_MISMATCH: priced_in_score={pi.get('priced_in_score')} (fully priced in) untuk driver yang menyebut {cur}, tapi currency_confidence[{cur}]={conf} masih tinggi. Jika mayoritas ekspektasi sudah priced-in, conviction directional seharusnya lebih rendah (turunkan ke <=0.6) KECUALI kamu punya alasan spesifik kenapa masih ada ruang gerak (state di macro_narrative).")

        return errors

    async def _check_anchoring_and_require_justification(self, current_bias: dict, justification_map: dict) -> list[str]:
        import json as _json
        # Fetch recent briefs with distinct hourly/cycle timestamps to avoid duplicate same-cycle records
        raw_briefs = (await self.session.execute(
            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(20)
        )).scalars().all()
        
        distinct_cycle_briefs = []
        last_time = None
        for b in raw_briefs:
            if b.generated_at:
                if last_time is None or (last_time - b.generated_at).total_seconds() > 1800:
                    distinct_cycle_briefs.append(b)
                    last_time = b.generated_at
            if len(distinct_cycle_briefs) == 4:
                break

        if len(distinct_cycle_briefs) < 4:
            return []
        
        parsed_biases = []
        for rb in distinct_cycle_briefs:
            cb = getattr(rb, "currency_bias", None)
            if isinstance(cb, dict) and cb:
                parsed_biases.append(cb)
            elif getattr(rb, "structured_json", None):
                try:
                    b_data = _json.loads(rb.structured_json)
                    if isinstance(b_data, dict):
                        parsed_biases.append(b_data.get("currency_bias", {}))
                except Exception:
                    pass
        if len(parsed_biases) < 4:
            return []

        is_weekend = clock.now().weekday() >= 5
        errors = []
        justification_map = justification_map or {}
        for currency, bias in current_bias.items():
            if bias == 'neutral':
                continue
            is_anchored = all(
                pb.get(currency) == bias for pb in parsed_biases
            )
            if is_anchored:
                just = justification_map.get(currency, '')
                has_number = any(ch.isdigit() for ch in just)
                weekend_ref = is_weekend and any(w in just.lower() for w in ['weekend', 'tutup', 'closed', 'jumat', 'friday'])
                if currency not in justification_map or len(just) < 40 or (not has_number and not weekend_ref):
                    errors.append(
                        f"ANCHORING_RISK: Bias {currency} ('{bias}') sama selama >=4 siklus pasar berturut-turut. "
                        f"bias_continuity_justification untuk {currency} kosong/terlalu pendek/tidak mengandung "
                        f"data numerik baru (WAJIB >= 40 karakter dengan level harga, %, tanggal, atau basis poin). "
                        f"Contoh format: bias_continuity_justification={{\"{currency}\": \"Bias {currency} {bias} dipertahankan karena data 2026-08-22 menunjukkan level 102.50 bertahan dan yield naik 5 bps\"}}."
                    )
        return errors

    async def _validate_key_data_points(self, inp: dict) -> list[str]:
        """
        Cross-check angka yang di-restate model terhadap data yang benar-benar di-fetch,
        menangkap salah baca/halusinasi data SEBELUM meracuni seluruh siklus.
        """
        errors = []
        kdp = inp.get('key_data_points_used', {})
        if not kdp:
            return ['MISSING_DATA_ANCHORS: key_data_points_used is required.']
        try:
            real_dxy = await self.execute('get_dxy', {})
            real_trend = real_dxy.get('trend_5d', 'unknown')
            claimed_trend = str(kdp.get('dxy_trend_5d', '')).lower()
            if real_trend != 'unknown' and real_trend not in claimed_trend:
                errors.append(
                    f"DATA_MISMATCH: Kamu menyatakan DXY trend='{kdp.get('dxy_trend_5d')}' tapi data tool "
                    f"aktual menunjukkan trend_5d='{real_trend}'. Cek ulang output get_dxy() sebelum resubmit."
                )
        except Exception:
            pass
        try:
            real_vix = await self.execute('get_vix', {})
            if not real_vix.get('error'):
                real_close = (real_vix.get('latest') or {}).get('close')
                claimed_close = kdp.get('vix_close')
                if real_close is not None and claimed_close is not None:
                    try:
                        rc = float(real_close)
                        cc = float(claimed_close)
                        if rc > 5.0 and abs(cc - rc) > 1.0:
                            errors.append(
                                f"DATA_MISMATCH: Kamu menyatakan VIX={claimed_close} tapi VIX close terbaru "
                                f"aktual={real_close}. Verifikasi nilai yang dibaca dari get_vix()."
                            )
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass
        try:
            if kdp.get('fedwatch_dominant_pct') is not None:
                real_fw = await self.execute('get_fedwatch_probabilities', {})
                meetings = real_fw.get('meetings', [])
                if meetings:
                    all_meeting_dominant_probs = []
                    for m in meetings:
                        probs_raw = m.get('probabilities', {})
                        if isinstance(probs_raw, dict) and 'probabilities' in probs_raw:
                            probs = probs_raw.get('probabilities', {})
                        elif isinstance(probs_raw, dict):
                            probs = probs_raw
                        else:
                            probs = {}
                        
                        m_max = max((float(v.get('probability', 0)) for v in probs.values() if isinstance(v, dict) and 'probability' in v), default=None)
                        if m_max is not None:
                            all_meeting_dominant_probs.append(m_max)
                    
                    if all_meeting_dominant_probs:
                        claimed = float(kdp.get('fedwatch_dominant_pct'))
                        min_diff = min(abs(claimed - p) for p in all_meeting_dominant_probs)
                        closest_prob = min(all_meeting_dominant_probs, key=lambda p: abs(claimed - p))
                        if min_diff > 8.0:
                            errors.append(
                                f"DATA_MISMATCH: Kamu menyatakan FedWatch dominant={claimed}% tapi data aktual "
                                f"terdekat={closest_prob}%. Verifikasi ulang output get_fedwatch_probabilities()."
                            )
        except Exception:
            pass
        try:
            tol_yield_bp = self.settings.get('data_quality', {}).get('key_data_tolerance', {}).get('treasury_10y_yield_bp', 15.0)
            if tol_yield_bp is not None and kdp.get('treasury_10y_yield_pct') is not None:
                real_yields = await self.execute('get_treasury_yields', {})
                real_10y_list = real_yields.get('yields_by_tenor', {}).get('10Y', [])
                if real_10y_list:
                    real_10y = real_10y_list[0].get('yield_pct')
                    claimed_10y = float(kdp.get('treasury_10y_yield_pct'))
                    if real_10y is not None and abs(claimed_10y - real_10y) * 100 > float(tol_yield_bp):
                        errors.append(
                            f"DATA_MISMATCH: Kamu menyatakan yield 10Y={claimed_10y}% tapi data aktual={real_10y}%. "
                            f"Verifikasi ulang output get_treasury_yields()."
                        )
        except Exception:
            pass
        try:
            tol_cot_pct = self.settings.get('data_quality', {}).get('key_data_tolerance', {}).get('cot_leveraged_pct')
            if tol_cot_pct is not None and kdp.get('cot_leveraged_long_pct') is not None:
                claimed_cot = float(kdp['cot_leveraged_long_pct'])
                CURRENCY_COT_MAP = {
                    "EUR": "099741", "GBP": "096742", "JPY": "097741", 
                    "AUD": "232741", "XAU": "088691", "OIL": "067651", "BTC": "133741", "USD": "099741"
                }
                target_code = kdp.get('cot_market_code')
                if not target_code and kdp.get('cot_currency'):
                    target_code = CURRENCY_COT_MAP.get(str(kdp['cot_currency']).upper())
                if not target_code:
                    target_code = "099741"

                cot_query = select(COTReport).where(COTReport.market_code == target_code).order_by(COTReport.report_date.desc()).limit(1)
                latest_cot = (await self.session.execute(cot_query)).scalar_one_or_none()
                if latest_cot:
                    tot = (latest_cot.leveraged_long or 0) + (latest_cot.leveraged_short or 0)
                    if tot > 0:
                        actual_long_pct = ((latest_cot.leveraged_long or 0) / tot) * 100.0
                        if abs(claimed_cot - actual_long_pct) > tol_cot_pct:
                            errors.append(
                                f"Key data point 'cot_leveraged_long_pct' claimed {claimed_cot:.1f}%, "
                                f"but latest COT report for {target_code} shows {actual_long_pct:.1f}% (diff > tolerance {tol_cot_pct}%)."
                            )
        except Exception:
            pass
        return errors

    async def _cross_check_all_currencies_priced_in(self, inp: dict) -> list[str]:
        from analysis.calculators.stage1_priced_in import calculate_stage1_priced_in_baseline
        warnings = []
        fedwatch_res = await self.execute('get_fedwatch_probabilities', {})
        fedwatch_prob = None
        if isinstance(fedwatch_res, dict) and fedwatch_res.get('meetings'):
            try:
                probs = fedwatch_res['meetings'][0]['probabilities'].get('probabilities', {})
                fedwatch_prob = max((v.get('probability', 0) for v in probs.values() if isinstance(v, dict)), default=None)
            except Exception:
                pass
        
        CURRENCY_COT_MAP = {'EUR': '099741', 'GBP': '096742', 'JPY': '097741', 'AUD': '232741', 'XAU': '088691'}
        CURRENCY_PROXY_SYMBOL = {'EUR': 'EURUSD', 'GBP': 'GBPUSD', 'JPY': 'USDJPY', 'AUD': 'AUDUSD', 'XAU': 'XAUUSD'}
        
        for ccy, cot_code in CURRENCY_COT_MAP.items():
            cot_row = (await self.session.execute(
                select(COTReport).where(COTReport.market_code == cot_code)
                .order_by(COTReport.report_date.desc()).limit(1)
            )).scalar_one_or_none()
            if not cot_row or (cot_row.leveraged_long + cot_row.leveraged_short) <= 0:
                continue
            total = cot_row.leveraged_long + cot_row.leveraged_short
            percentile = cot_row.leveraged_long / total * 100
            proxy_symbol = CURRENCY_PROXY_SYMBOL.get(ccy)
            mom_res = await self.execute('get_price_momentum', {'symbol': proxy_symbol, 'timeframe': 'H4', 'period': 20}) if proxy_symbol else {}
            run_up = mom_res.get('run_up_vs_atr') if isinstance(mom_res, dict) else None
            baseline = calculate_stage1_priced_in_baseline(ccy, percentile, fedwatch_dominant_prob=fedwatch_prob, eurusd_run_up_vs_atr=run_up)
            declared_bias = (inp.get('currency_bias', {}) or {}).get(ccy, 'neutral')
            declared_pi = (inp.get('priced_in_assessment', {}) or {}).get('priced_in_score', 5)
            if baseline['is_priced_in'] and declared_pi <= 3 and declared_bias != 'neutral':
                warnings.append(f"[{ccy}] Deterministic baseline menunjukkan priced-in ({'; '.join(baseline['reasons'])}) tapi priced_in_score={declared_pi} rendah.")
        return warnings

    async def _tool_submit_fundamental_brief(self, inp: dict) -> dict:
        """Menyimpan narasi dan bias makro ke DB (menandai berakhirnya Tahap 1)."""
        inp.pop("submit_attempts", None)  # Toleransi tambahan argumen dari LLM
        
        if isinstance(inp, dict):
            for wrapper in ("input", "brief", "data", "parameters", "args", "payload"):
                if wrapper in inp and isinstance(inp[wrapper], dict) and len(inp) == 1:
                    inp = inp[wrapper]
                    break

        # Contamination guard
        stage2_tools = {"get_smc_zones", "get_technical_indicators", "get_swing_points", "get_fvg_zones", "get_order_blocks"}
        contaminated = stage2_tools.intersection(self.called_tools)
        if contaminated:
            logger.warning(f"Stage 1 contamination detected: {contaminated}. Blocking submission.")
            return {
                "status": "rejected",
                "errors": [f"You called Stage 2 tools ({', '.join(contaminated)}) during Stage 1."],
                "error_classification": "CONTAMINATION_ERROR",
                "guidance": "Stage 1 must ONLY use macro/fundamental tools. Do NOT call technical/SMC tools. Restart your reasoning focusing purely on fundamental drivers."
            }
            
        # Deterministic priced-in check using EURUSD as a baseline proxy for USD
        try:
            warnings = await self._cross_check_all_currencies_priced_in(inp)
            if warnings:
                inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                    f"\n\n[SYSTEM WARNING: Deterministic Priced-In Check triggered.\n" +
                    "\n".join(warnings) +
                    f"\nStage 2 agents must exercise caution and increase confluence thresholds.]"
                )
        except Exception as e:
            logger.error(f"Deterministic priced-in check failed: {e}")

        try:
            validated_data = SubmitFundamentalBriefSchema.model_validate(inp)
            inp = validated_data.model_dump(exclude_unset=True, mode="json")
        except ValidationError as e:
            error_msgs = [f"Field '{'.'.join(str(x) for x in err['loc'])}': {err['msg']}" for err in e.errors()]
            logger.warning(f"Pydantic validation failed for submit_fundamental_brief: {error_msgs}")
            return {
                "status": "validation_failed",
                "errors": error_msgs,
                "error_classification": "SCHEMA_ERROR",
                "guidance": "Please fix the schema formatting errors above and call the tool again."
            }
            
        # Validate Completeness
        completeness_errors = await self._validate_fundamental_brief_completeness(inp)
        data_anchor_errors = await self._validate_key_data_points(inp)
        completeness_errors.extend(data_anchor_errors)
        
        merged_justifications = {
            **inp.get('bias_change_justification', {}),
            **inp.get('bias_continuity_justification', {})
        }
        anchoring_errors = await self._check_anchoring_and_require_justification(
            inp.get('currency_bias', {}),
            merged_justifications
        )
        if anchoring_errors:
            completeness_errors.extend(anchoring_errors)

        non_neutral_currencies = [c for c, b in inp.get('currency_bias', {}).items() if b != 'neutral']
        invalidation_map = inp.get('invalidation_conditions', {})
        missing_invalidation = [c for c in non_neutral_currencies if c not in invalidation_map or not invalidation_map.get(c, '').strip()]
        if missing_invalidation:
            completeness_errors.append(
                f"MISSING_INVALIDATION: Currency berikut punya bias non-neutral tapi tidak "
                f"punya invalidation_conditions: {missing_invalidation}. Setiap bias directional "
                f"WAJIB punya kondisi falsifiable."
            )

        # Checklist verification
        checklist = inp.get('checklist', {})
        if checklist.get('contradiction_existed'):
            counter_thesis = inp.get('strongest_counter_thesis', '')
            if not counter_thesis:
                completeness_errors.append('CONTRADICTION_UNRESOLVED: You marked contradiction_existed=True in the checklist, but did not provide the strongest_counter_thesis. You must detail the counter-thesis.')
            elif not any(ch.isdigit() for ch in counter_thesis):
                completeness_errors.append('CONTRADICTION_UNRESOLVED_NO_EVIDENCE: contradiction_existed=True tapi strongest_counter_thesis tidak mengandung bukti numerik konkret (level harga/%/tanggal/basis poin) sebagai dasar resolusi kontradiksi.')
            
        # Ceiling check
        try:
            from utils.analytics.agent_performance_monitor import get_currency_confidence_ceiling
            ceilings = await get_currency_confidence_ceiling(self.session)
            currency_conf = inp.get('currency_confidence', {})
            for cur, conf in currency_conf.items():
                ceiling = ceilings.get(cur, 0.95)
                if conf > ceiling:
                    completeness_errors.append(
                        f"CONFIDENCE_CEILING_EXCEEDED: Your confidence for {cur} ({conf}) exceeds the historical accuracy ceiling ({ceiling}). "
                        f"Please lower your confidence to max {ceiling}."
                    )
        except Exception as e:
            logger.error(f"Error checking confidence ceilings: {e}")

        if completeness_errors:
            self.submit_attempts += 1
            if self.submit_attempts <= 2:
                logger.warning(f"Brief rejected (incomplete): {completeness_errors}")
                return {
                    "status": "rejected",
                    "errors": completeness_errors,
                    "error_classification": "INCOMPLETE_ANALYSIS",
                    "guidance": "Your brief is incomplete. Fix the errors above and resubmit. Do NOT ignore this."
                }
            else:
                logger.warning(f'Brief accepted with unresolved errors after {self.submit_attempts} attempts: {completeness_errors}')
                inp['macro_narrative'] = inp.get('macro_narrative', '') + (
                    f"\n\n[SYSTEM FLAG: Brief force-accepted with unresolved errors: "
                    f"{'; '.join(completeness_errors)}. Stage 2 MUST escalate if this affects the trading decision.]"
                )
                inp['confidence'] = min(float(inp.get('confidence', 0.5)), 0.35)
                inp['_data_quality_degraded'] = True
                inp['_degradation_reasons'] = completeness_errors

        from utils.protocol.brief_contamination_guard import BriefContaminationGuard
        brief_data_for_check = {
            'currency_bias': inp.get('currency_bias', {}),
            'risk_sentiment': inp.get('risk_sentiment', 'mixed'),
            'confidence': inp.get('confidence', 0.5),
        }
        is_safe, contamination_issues, contamination_risk = await BriefContaminationGuard.validate_brief_integrity(
            self.session, brief_data_for_check, self.settings
        )
        CONTAMINATION_HARD_BLOCK_THRESHOLD = 0.4 # FIX P2-1: turunkan dari 0.5 ke 0.4

        if not is_safe and contamination_risk >= CONTAMINATION_HARD_BLOCK_THRESHOLD:
            self.submit_attempts += 1
            if self.submit_attempts <= 2:
                logger.warning(f'Brief REJECTED (contamination_risk={contamination_risk:.2f}): {contamination_issues}')
                return {
                    'status': 'rejected',
                    'errors': contamination_issues,
                    'error_classification': 'INTERNAL_CONTRADICTION',
                    'guidance': (
                        'Brief Anda mengandung kontradiksi internal yang belum diselesaikan '
                        '(lihat errors di atas). Anda WAJIB secara eksplisit menyatakan di '
                        'macro_narrative: sumber mana yang Anda percaya dan MENGAPA, sebelum '
                        'submit ulang. Jangan hanya menyebut kedua sisi tanpa memilih.'
                    ),
                }
            else:
                logger.warning(
                    f'Brief accepted despite contamination_risk={contamination_risk:.2f} '
                    f'(max retries reached): {contamination_issues}'
                )
                inp['macro_narrative'] = inp.get('macro_narrative', '') + (
                    f"\n\n[SYSTEM FLAG: Brief disimpan meski contamination_risk={contamination_risk:.2f} "
                    f"setelah {self.submit_attempts} percobaan. Isu belum terselesaikan: "
                    f"{'; '.join(contamination_issues)}. Stage 2 harus ekstra hati-hati.]"
                )
        elif not is_safe:
            inp['macro_narrative'] = inp.get('macro_narrative', '') + (
                f"\n\n[SYSTEM NOTE: contamination_risk={contamination_risk:.2f} (warning zone). "
                f"Issues: {'; '.join(contamination_issues)}]"
            )
            
        # === NEW: Enforce priced_in_assessment when major events exist ===
        priced_in = inp.get('priced_in_assessment')
        if not priced_in:
            # Check if there are major events within 48h
            now = clock.now()
            result = await self.session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact == 'high')
                .where(EconomicCalendar.event_time >= now)
                .where(EconomicCalendar.event_time <= now + timedelta(hours=48))
                .limit(1)
            )
            upcoming_major = result.scalar_one_or_none()
            
            if upcoming_major:
                logger.warning(f"Brief rejected: missing priced_in_assessment when high-impact event '{upcoming_major.event_name}' is within 48h.")
                return {
                    "status": "rejected",
                    "errors": [f"Missing 'priced_in_assessment' field."],
                    "error_classification": "INCOMPLETE_ANALYSIS",
                    "guidance": f"A high-impact event ('{upcoming_major.event_name}') is scheduled within the next 48h. You MUST provide the 'priced_in_assessment' field to evaluate how much this event is already priced in by the market."
                }
            
        # ── DETERMINISTIC CONFIDENCE CEILING (menegakkan CHECKPOINT 3 secara kode) ──
        try:
            declared_confidence = float(inp.get('confidence', 0.7))
            ceiling_reasons = []
            hard_ceiling = 1.0

            if contamination_risk >= 0.35:
                hard_ceiling = min(hard_ceiling, 0.65)
                ceiling_reasons.append(f'contamination_risk={contamination_risk:.2f}')

            vix_row = (await self.session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
            if vix_row and vix_row.close >= 28:
                hard_ceiling = min(hard_ceiling, 0.70)
                ceiling_reasons.append(f'vix={vix_row.close:.1f}>=28')

            from datetime import timedelta as _td
            upcoming_2h = (await self.session.execute(
                select(EconomicCalendar)
                .where(EconomicCalendar.impact == 'high')
                .where(EconomicCalendar.event_time >= clock.now())
                .where(EconomicCalendar.event_time <= clock.now() + _td(hours=2))
                .limit(5)
            )).scalars().all()
            if upcoming_2h:
                event_currencies = set()
                for ev in upcoming_2h:
                    if ev.currency:
                        event_currencies.add(ev.currency.upper())
                inp['_upcoming_event_currencies'] = list(event_currencies)
                hard_ceiling = min(hard_ceiling, 0.70)
                ev_names = ', '.join(str(e.event_name)[:25] for e in upcoming_2h[:3])
                ceiling_reasons.append(f'high_impact_event_within_2h({ev_names})')

            if declared_confidence > hard_ceiling:
                logger.warning(f'[ConfidenceCeiling] Stage1 confidence clamped {declared_confidence:.2f} -> {hard_ceiling:.2f}. Reasons: {ceiling_reasons}')
                inp['confidence'] = hard_ceiling
                inp['macro_narrative'] = inp.get('macro_narrative', '') + f"\n\n[SYSTEM: Confidence auto-capped to {hard_ceiling:.2f} (declared {declared_confidence:.2f}) due to: {', '.join(ceiling_reasons)}.]"
        except Exception as e:
            logger.debug(f'Deterministic confidence ceiling check failed (non-fatal): {e}')
        # ── END CONFIDENCE CEILING ──

        import json as _json
        now = clock.now()
        validity = self.settings.get("data_quality", {}).get("brief_validity_hours", 12.0)
        valid_until = now + timedelta(hours=validity)

        # Task 2.3: Validation for priced_in_assessment
        priced_in = inp.get("priced_in_assessment")
        if priced_in:
            pi_score = priced_in.get("priced_in_score")
            if pi_score is not None:
                try:
                    pi_score = int(pi_score)
                    if not 1 <= pi_score <= 10:
                        pi_score = max(1, min(10, pi_score))
                        logger.warning(f'priced_in_score {priced_in.get("priced_in_score")} out of range, clamped to {pi_score}')
                except (ValueError, TypeError):
                    logger.warning(f'priced_in_score invalid type: {type(pi_score)}, setting to 5')
                    pi_score = 5
                priced_in["priced_in_score"] = pi_score
                
                # Sanity check for priced_in_score
                if pi_score <= 3:
                    from sqlalchemy import func, or_
                    now_utc = clock.now()
                    recent_high_news = (await self.session.execute(
                        select(func.count(NewsItem.id))
                        .where(NewsItem.fetched_at >= now_utc - timedelta(hours=24))
                        .where(or_(NewsItem.title.ilike('%BREAKING%'), NewsItem.title.ilike('%URGENT%')))
                    )).scalar() or 0
                    
                    recent_high_econ = (await self.session.execute(
                        select(func.count(EconomicCalendar.id))
                        .where(EconomicCalendar.event_time >= now_utc - timedelta(hours=24))
                        .where(EconomicCalendar.event_time <= now_utc)
                        .where(EconomicCalendar.impact == 'high')
                    )).scalar() or 0
                    
                    total_high_events = recent_high_news + recent_high_econ
                    if total_high_events >= 5:
                        logger.warning(f"Sanity Check Failed: pi_score={pi_score} but {total_high_events} high/breaking news found.")
                        inp["macro_narrative"] = inp.get("macro_narrative", "") + (
                            f"\n\n[SYSTEM WARNING: priced_in_score is low ({pi_score}) despite {total_high_events} recent "
                            f"HIGH/BREAKING events. The market may have already priced these in! Stage 2 should exercise caution.]"
                        )
            
            valid_risks = ['high', 'medium', 'low', 'not_applicable']
            current_risk = priced_in.get('sell_the_news_risk')
            pi_score = priced_in.get('priced_in_score', 5)
            if pi_score >= 8:
                priced_in['sell_the_news_risk'] = 'high'
            elif pi_score in (5, 6, 7):
                if current_risk not in ('medium', 'high'):
                    priced_in['sell_the_news_risk'] = 'medium'
            elif pi_score in (3, 4):
                if current_risk not in ('low', 'medium'):
                    priced_in['sell_the_news_risk'] = 'low'
            else:
                if current_risk not in ('not_applicable', 'low'):
                    priced_in['sell_the_news_risk'] = 'not_applicable'
            inp["priced_in_assessment"] = priced_in

        brief = FundamentalBrief(
            generated_at=now,
            valid_until=valid_until,
            content_markdown=inp.get("macro_narrative", ""),
            structured_json=_json.dumps({
                "generated_at": now.isoformat(),
                "macro_narrative": inp.get("macro_narrative", ""),
                "currency_bias": inp.get("currency_bias", {}),
                "currency_confidence": inp.get("currency_confidence", {}),
                "invalidation_conditions": inp.get("invalidation_conditions", {}),
                "key_upcoming_risks": inp.get("key_upcoming_risks", []),
                "risk_sentiment": inp.get("risk_sentiment", "mixed"),
                "macro_regime": inp.get("macro_regime", "mixed"),
                "confidence": inp.get("confidence", 0.5),
                "priced_in_assessment": inp.get("priced_in_assessment", None),
                "_data_quality_degraded": inp.get("_data_quality_degraded", False),
                "_degradation_reasons": inp.get("_degradation_reasons", []),
            }),
            confidence=inp.get("confidence", 0.5),
            risk_sentiment=inp.get("risk_sentiment", "mixed")
        )
        self.session.add(brief)
        await self.session.commit()
        await self.session.refresh(brief)
        saved_brief_id = brief.id

        # Macro Regime Shift Auto-Recording to MarketChronicle
        try:
            from analysis.memory.chronicle_writer import ChronicleWriter
            prev_brief = (await self.session.execute(
                select(FundamentalBrief)
                .where(FundamentalBrief.id != brief.id)
                .order_by(FundamentalBrief.generated_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            if prev_brief:
                await ChronicleWriter(self.settings).maybe_record_regime_shift(self.session, brief, prev_brief)
        except Exception as chronicle_err:
            logger.debug(f"Failed to record chronicle regime shift (non-fatal): {chronicle_err}")

        priced_in = inp.get("priced_in_assessment")
        priced_in_summary = (
            f", priced_in_score={priced_in.get('priced_in_score')}, "
            f"sell_news_risk={priced_in.get('sell_the_news_risk')}"
        ) if priced_in else ""

        logger.info(
            f"Fundamental brief saved (id={saved_brief_id}, "
            f"sentiment={inp.get('risk_sentiment')}{priced_in_summary})"
        )

        try:
            recent_briefs = (await self.session.execute(
                select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(6)
            )).scalars().all()
            streak_warnings = []
            flip_flop_warnings = []
            new_bias = inp.get('currency_bias', {})
            for currency, bias in new_bias.items():
                if bias == 'neutral':
                    continue
                history = []
                for prev in recent_briefs[1:4]:
                    if not prev.structured_json:
                        continue
                    try:
                        pb = _json.loads(prev.structured_json).get('currency_bias', {}).get(currency, 'neutral')
                        history.append(pb)
                    except Exception:
                        pass
                
                # FIX (P1): Flip-Flop Bias Detector
                if len(history) >= 2:
                    if bias != 'neutral' and history[0] != 'neutral' and bias != history[0] and bias == history[1]:
                        flip_flop_warnings.append(f"{currency} flip-flop detected: {history[1]} -> {history[0]} -> {bias}")

                streak = 1
                for prev in recent_briefs[1:]:
                    if not prev.structured_json:
                        break
                    try:
                        prev_bias = _json.loads(prev.structured_json).get('currency_bias', {}).get(currency)
                    except Exception:
                        break
                    if prev_bias == bias:
                        streak += 1
                    else:
                        break
                if streak >= 4:
                    streak_warnings.append(f"{currency}={bias} unchanged for {streak} consecutive briefs")
            
            alerts = []
            if streak_warnings:
                alerts.extend(streak_warnings)
            if flip_flop_warnings:
                alerts.extend([f"[FLIP-FLOP WARNING] {w} — Jika bias bolak-balik tiap siklus tanpa breakout makro baru, ini akan menyebabkan whipsaw loss. WAJIB justifikasi kuat atau gunakan NEUTRAL." for w in flip_flop_warnings])
                
            if alerts:
                key = f'anchoring_streak_alert_{clock.now().strftime("%Y%m%d_%H")}'
                existing = (await self.session.execute(
                    select(SystemConfig).where(SystemConfig.key == key)
                )).scalar_one_or_none()
                if existing:
                    existing.value = _json.dumps(alerts)
                else:
                    self.session.add(SystemConfig(key=key, value=_json.dumps(alerts)))
                await self.session.commit()
        except Exception as e:
            try:
                await self.session.rollback()
            except Exception:
                pass
            logger.debug(f"Anti-anchoring streak check failed (non-fatal): {e}")

        return {
            "status": "saved",
            "brief_id": saved_brief_id,
            "valid_until": valid_until.isoformat(),
        }

    # ------------------------------------------------------------------
    # Stage 2 handlers
    # ------------------------------------------------------------------

    async def _tool_get_retail_sentiment(self, inp: dict) -> dict:
        import json as _json
        cfg = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == "binance_sentiment_latest")
        )).scalar_one_or_none()
        
        if not cfg or not cfg.value:
            return {"error": "Retail sentiment data not available. Ensure cycle scheduler has run."}
        try:
            return _json.loads(cfg.value)
        except Exception as e:
            return {"error": f"Parse error: {e}"}

    async def _tool_get_forex_sentiment(self, inp: dict) -> dict:
        import json as _json
        cfg = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == "myfxbook_sentiment_latest")
        )).scalar_one_or_none()
        
        if not cfg or not cfg.value:
            # Fallback to FXSSI sentiment if MyFxBook is not available
            fxssi_cfg = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == "fxssi_sentiment_latest")
            )).scalar_one_or_none()
            if fxssi_cfg and fxssi_cfg.value:
                try:
                    return _json.loads(fxssi_cfg.value)
                except Exception:
                    pass
            return {"error": "Forex sentiment data not available. Ensure cycle scheduler has run."}
        try:
            return _json.loads(cfg.value)
        except Exception as e:
            return {"error": f"Parse error: {e}"}

    async def _tool_get_fxssi_sentiment(self, inp: dict) -> dict:
        import json as _json
        cfg = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == "fxssi_sentiment_latest")
        )).scalar_one_or_none()
        
        if not cfg or not cfg.value:
            return {"error": "FXSSI sentiment data not available. Ensure cycle scheduler has run."}
        try:
            return _json.loads(cfg.value)
        except Exception as e:
            return {"error": f"Parse error: {e}"}

    async def _tool_get_fundamental_brief(self, inp: dict) -> dict:
        row = (await self.session.execute(
            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
        )).scalar_one_or_none()

        if row is None:
            return {"error": "No fundamental brief found. Stage 1 must run first."}

        structured = json.loads(row.structured_json) if row.structured_json else {}
        
        now = clock.now()
        age_hours = (now - row.generated_at).total_seconds() / 3600
        is_stale = row.valid_until is not None and now > row.valid_until
        
        max_critical = float(self.settings.get("data_quality", {}).get("max_brief_age_analysis_hours", 12.0))
        max_warning = float(self.settings.get("data_quality", {}).get("max_brief_age_execution_hours", 10.0))
        if max_warning >= max_critical:
            max_warning = min(10.0, max_critical - 1.0)
        
        staleness_warning = ""
        if age_hours > max_critical:
            staleness_warning = f'\n\n🚨 CRITICAL: Brief is {age_hours:.1f}h old (limit: {max_critical}h). MANDATORY WAIT for all assets. Do not submit BUY/SELL.'
        elif age_hours > max_warning:
            staleness_warning = f'\n\n⚠️ STALE: Brief is {age_hours:.1f}h old (limit: {max_warning}h). High-impact events may have occurred. Be extra cautious and do not enter on macro-dependent setups.'
        elif age_hours > 2:
            staleness_warning = f'\n\nℹ️ Brief is {age_hours:.1f}h old. Cross-validate macro assumptions with recent price action.'

        return {
            "brief_id": row.id,
            "generated_at": row.generated_at.isoformat(),
            "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            "age_hours": round(age_hours, 1),
            "is_stale": is_stale,
            "staleness_warning": staleness_warning,
            **structured,
        }

    async def _tool_get_price_history(self, inp: dict) -> dict:
        symbol = self._resolve_symbol(inp) or inp.get("symbol")
        if not symbol:
            return {"error": "Missing required parameter 'symbol'"}
        timeframe = inp["timeframe"]
        limit = min(inp.get("limit", 50), 200)

        rows = (await self.session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == timeframe)
            .where(PriceOHLCV.timestamp <= clock.now())
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(limit)
        )).scalars().all()

        rows = list(reversed(rows))  # chronological order
        
        # Optimize output tokens by returning CSV string instead of JSON array
        if not rows:
            return {"symbol": symbol, "timeframe": timeframe, "count": 0, "csv_data": ""}
            
        header = "time,open,high,low,close,volume\n"
        lines = [
            f"{r.timestamp.isoformat() if r.timestamp is not None else ''},{r.open},{r.high},{r.low},{r.close},{r.volume}"
            for r in rows
        ]
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(rows),
            "csv_data": header + "\n".join(lines),
        }

    def _format_smc_data(self, zones_data: dict, current_price: Optional[float] = None) -> dict:
        """Helper to trim SMC data to save tokens, prioritized by proximity to current price."""
        formatted = {}
        for key in ["order_blocks", "fvg_zones", "liquidity_zones", "sr_zones"]:
            items = list(zones_data.get(key, []))
            if current_price and items:
                for item in items:
                    h = item.get('price_high') or item.get('zone_high') or item.get('gap_high') or item.get('high', 0.0)
                    l = item.get('price_low') or item.get('zone_low') or item.get('gap_low') or item.get('low', 0.0)
                    mid = (h + l) / 2.0 if (h and l) else (h or l or 0.0)
                    item['_dist'] = abs(mid - current_price) if mid else float('inf')
                items.sort(key=lambda x: x.get('_dist', float('inf')))

            trimmed = []
            for item in items[:3]:  # Max 3
                # Remove verbose fields
                trimmed_item = {k: v for k, v in item.items() if k not in ("id", "symbol", "timeframe", "filled_at", "mitigated_at", "_dist")}
                trimmed.append(trimmed_item)
            formatted[key] = trimmed
        return formatted


    async def _get_precomputed_data(self, key: str) -> dict:
        cfg = (await self.session.execute(
            select(SystemConfig).where(SystemConfig.key.in_(["llm_preprocessed_latest", "gemini_preprocessed_latest"]))
        )).scalars().first()
        if not cfg or not cfg.value:
            return {"error": "No pre-computed data available"}
        import json
        try:
            data = json.loads(cfg.value)
            return data.get(key, {})
        except Exception as e:
            return {"error": f"Failed to parse pre-computed data: {e}"}

    # Backward compatibility alias
    _get_gemini_precomputed = _get_precomputed_data


    async def _validate_smc_entry_proximity(
        self, symbol: str, entry_price: float, direction: str,
        stop_loss: float, atr: float
    ) -> list[str]:
        warnings = []
        if not entry_price or not atr or atr <= 0:
            return warnings
        
        # TIGHTENED: Use 0.5x ATR instead of 2.0x ATR
        # Entry should be WITHIN or at the boundary of an FVG/OB, not just "nearby"
        proximity_threshold = atr * 0.5
        
        fvgs = (await self.session.execute(
            select(FVGZone)
            .where(FVGZone.symbol == symbol)
            .where(FVGZone.timeframe == 'H4')
            .where(FVGZone.filled_at == None)
            .order_by(FVGZone.formed_at.desc())
            .limit(10)
        )).scalars().all()
        
        near_fvg = False
        inside_fvg = False
        for fvg in fvgs:
            # Check if entry is INSIDE the FVG (ideal)
            if fvg.gap_low <= entry_price <= fvg.gap_high:
                inside_fvg = True
                near_fvg = True
                break
            # Check if entry is within 0.5 ATR of FVG boundary
            fvg_mid = (fvg.gap_high + fvg.gap_low) / 2
            if abs(entry_price - fvg_mid) <= proximity_threshold:
                near_fvg = True
                break
        
        obs = (await self.session.execute(
            select(OrderBlock)
            .where(OrderBlock.symbol == symbol)
            .where(OrderBlock.timeframe == 'H4')
            .where(OrderBlock.mitigated_at == None)
            .order_by(OrderBlock.formed_at.desc())
            .limit(5)
        )).scalars().all()
        
        near_ob = False
        inside_ob = False
        for ob in obs:
            # Check if entry is INSIDE the OB (ideal)
            if ob.price_low <= entry_price <= ob.price_high:
                inside_ob = True
                near_ob = True
                break
            ob_mid = (ob.price_high + ob.price_low) / 2
            if abs(entry_price - ob_mid) <= proximity_threshold:
                near_ob = True
                break
        
        if not near_fvg and not near_ob:
            warnings.append(
                f'SMC PROXIMITY FAIL: Entry {entry_price:.5f} is NOT within 0.5×ATR ({proximity_threshold:.5f}) of any active H4 FVG or Order Block. '
                f'Entry appears to be "chasing" price rather than waiting for pullback to institutional zone. '
                f'Consider WAIT until price returns to a zone.'
            )
        elif not inside_fvg and not inside_ob and (near_fvg or near_ob):
            warnings.append(
                f'SMC PROXIMITY NOTE: Entry is near but not inside an FVG/OB zone. '
                f'Ideal entry would be within the zone boundary itself. Confidence slightly reduced.'
            )
        
        # SL validation remains the same
        if direction == 'buy':
            swing_lows = (await self.session.execute(
                select(SwingPoint)
                .where(SwingPoint.symbol == symbol)
                .where(SwingPoint.timeframe == 'H4')
                .where(SwingPoint.type == 'low')
                .where(SwingPoint.price <= entry_price)
                .order_by(SwingPoint.price.desc())
                .limit(3)
            )).scalars().all()
            sl_beyond_swing = any(sl.price >= stop_loss for sl in swing_lows) if swing_lows else True
        else:
            swing_highs = (await self.session.execute(
                select(SwingPoint)
                .where(SwingPoint.symbol == symbol)
                .where(SwingPoint.timeframe == 'H4')
                .where(SwingPoint.type == 'high')
                .where(SwingPoint.price >= entry_price)
                .order_by(SwingPoint.price.asc())
                .limit(3)
            )).scalars().all()
            sl_beyond_swing = any(sh.price <= stop_loss for sh in swing_highs) if swing_highs else True
        
        if not sl_beyond_swing:
            warnings.append(
                f'SL STRUCTURE FAIL: Stop loss {stop_loss:.5f} does not appear to be BEYOND a significant swing point. '
                f'SL must be placed on the other side of a structural level to be valid.'
            )
        
        return warnings

    async def _validate_tp_structural_target(self, symbol: str, direction: str, tp_price: Optional[float],
                                               atr: Optional[float], adr_ctx: Optional[dict] = None) -> list[str]:
        """TP must anchor to a real structural target (SR/FVG/OB/swing/liquidity/round-number)
        AND fall inside the ADR band — mathematical band membership alone is insufficient."""
        errors = []
        if not tp_price or not atr or atr <= 0:
            return errors
        tol_mult = self.settings.get('trading', {}).get('risk', {}).get('structural_snap_tolerance_atr_mult', 0.4)
        tolerance = atr * tol_mult
        found, basis = (False, '')

        sr_zones = (await self.session.execute(select(SRZone).where(SRZone.symbol == symbol).where(SRZone.timeframe.in_(['H4', 'D1'])))).scalars().all()
        for sr in sr_zones:
            if sr.price_low - tolerance <= tp_price <= sr.price_high + tolerance:
                found, basis = True, f'SR zone {sr.price_low:.5f}-{sr.price_high:.5f}'
                break
        if not found:
            fvgs = (await self.session.execute(select(FVGZone).where(FVGZone.symbol == symbol).where(FVGZone.timeframe == 'H4').where(FVGZone.filled_at == None))).scalars().all()
            for fvg in fvgs:
                edge = fvg.gap_low if direction == 'sell' else fvg.gap_high
                if abs(tp_price - edge) <= tolerance:
                    found, basis = True, f'{fvg.direction} FVG edge {edge:.5f}'
                    break
        if not found:
            obs = (await self.session.execute(select(OrderBlock).where(OrderBlock.symbol == symbol).where(OrderBlock.timeframe == 'H4').where(OrderBlock.mitigated_at == None))).scalars().all()
            for ob in obs:
                edge = ob.price_low if direction == 'sell' else ob.price_high
                if abs(tp_price - edge) <= tolerance:
                    found, basis = True, f'{ob.direction} OB edge {edge:.5f}'
                    break
        if not found:
            swings = (await self.session.execute(select(SwingPoint).where(SwingPoint.symbol == symbol).where(SwingPoint.timeframe == 'H4').order_by(SwingPoint.timestamp.desc()).limit(10))).scalars().all()
            for sw in swings:
                if abs(tp_price - sw.price) <= tolerance:
                    found, basis = True, f'swing {sw.type} @ {sw.price:.5f}'
                    break
        if not found:
            liqs = (await self.session.execute(select(LiquidityZone).where(LiquidityZone.symbol == symbol).where(LiquidityZone.timeframe == 'H4'))).scalars().all()
            for lz in liqs:
                if lz.zone_low - tolerance <= tp_price <= lz.zone_high + tolerance:
                    found, basis = True, f'liquidity zone {lz.type}'
                    break
        if not found:
            round_increments = {'XAUUSD': 10.0, 'XTIUSD': 1.0, 'BTCUSD': 1000.0, 'USDJPY': 0.5}
            incr = round_increments.get(symbol)
            if incr:
                nearest = round(tp_price / incr) * incr
                if abs(tp_price - nearest) <= tolerance:
                    found, basis = True, f'round number {nearest}'

        if not found:
            adr_info = adr_ctx or {}
            min_dist = float(adr_info.get('target_tp_min_distance', 0) or 0)
            max_dist = float(adr_info.get('target_tp_max_distance', 0) or 0)
            adr_band_str = f"inside the ADR band [{min_dist:.5f}, {max_dist:.5f}]" if adr_ctx else "matching market structure"
            errors.append(
                f"TP STRUCTURAL MAPPING FAIL: take_profit={tp_price:.5f} is not within {tolerance:.5f} "
                f"({tol_mult}x ATR) of any known SR/FVG/OB/swing/liquidity/round-number target {adr_band_str}. "
                f"Call get_optimal_intraday_levels to find a validated structural TP, or submit WAIT.")
        else:
            logger.debug(f'[{symbol}] TP structural mapping OK: {basis}')
        return errors

    async def _get_dynamic_atr_fallback(self, symbol: str) -> Optional[float]:
        """
        ATR fallback yang market-aware, bukan hardcoded.
        Priority: 30d avg > recent range-based estimate > hardcoded minimum
        """
        try:
            # Method 1: 30-day average ATR (existing, tapi improved)
            rows = (await self.session.execute(
                select(TechnicalIndicator.value_json)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == 'H4')
                .where(TechnicalIndicator.indicator_name == 'ATR_14')
                .where(TechnicalIndicator.timestamp >= clock.now() - timedelta(days=30))
                .where(TechnicalIndicator.timestamp <= clock.now())
                .order_by(TechnicalIndicator.timestamp.desc())
                .limit(30)  # Kurangi limit, cukup 30 bars
            )).scalars().all()
            
            if len(rows) >= 5:  # Minimum 5 data points untuk average yang valid
                values = []
                for row in rows:
                    try:
                        import json
                        v = json.loads(row)
                        atr = v.get('atr', v.get('value')) if isinstance(v, dict) else float(v)
                        if atr and 0 < atr < 1000:  # Sanity check
                            values.append(float(atr))
                    except Exception:
                        pass
                
                if values:
                    # Gunakan median, bukan mean, untuk robustness terhadap outlier
                    values.sort()
                    median_atr = values[len(values) // 2]
                    return round(median_atr, 5)
            
            # Method 2: Recent candle range estimate
            last_bars = (await self.session.execute(
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == 'H4')
                .where(PriceOHLCV.timestamp <= clock.now())
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(14)
            )).scalars().all()
            
            if len(last_bars) >= 5:
                ranges = [abs(b.high - b.low) for b in last_bars]
                return round(sum(ranges) / len(ranges), 5)
            
            # Method 3: Dynamic minimum berdasarkan current price (tidak hardcoded)
            last_bar = last_bars[0] if last_bars else None
            if last_bar and last_bar.close:
                price = last_bar.close
                # ATR minimum biasanya 0.1-0.3% dari price untuk liquid instruments
                SYMBOL_MIN_ATR_PCT = {
                    'XAUUSD': 0.003,   # 0.3% - $6+ pada harga $2000
                    'BTCUSD': 0.015,   # 1.5% 
                    'EURUSD': 0.0005,  # 5 pips
                    'GBPUSD': 0.0006,
                    'USDJPY': 0.004,
                    'AUDUSD': 0.0004,
                    'XTIUSD': 0.005,   # 0.5%
                }
                pct = SYMBOL_MIN_ATR_PCT.get(symbol, 0.001)
                return round(price * pct, 5)
                
            return None
            
        except Exception as e:
            logger.debug(f'Dynamic ATR fallback failed for {symbol}: {e}')
            return None

    async def _validate_manual_order_structural(
        self,
        symbol: str,
        direction: str,
        entry_price: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
    ) -> list[str]:
        """
        Lightweight structural validation specifically for manual orders via Telegram chat.
        Checks:
        1. Required fields: symbol, direction, entry_price, stop_loss, take_profit
        2. Valid direction ('buy', 'sell')
        3. Price alignment:
           - For BUY: stop_loss < entry_price < take_profit
           - For SELL: take_profit < entry_price < stop_loss
        4. Minimum Risk-to-Reward ratio (default >= 1.3)
        5. ADR Band check: Take profit distance <= 80% ADR
        """
        errors = []
        if not symbol:
            errors.append("symbol is required")
        if direction not in ("buy", "sell"):
            errors.append(f"direction must be 'buy' or 'sell', got '{direction}'")
        if entry_price is None or entry_price <= 0:
            errors.append("entry_price must be a positive number")
        if stop_loss is None or stop_loss <= 0:
            errors.append("stop_loss must be a positive number")
        if take_profit is None or take_profit <= 0:
            errors.append("take_profit must be a positive number")

        if errors or entry_price is None or stop_loss is None or take_profit is None:
            return errors

        # Price alignment & R:R
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)

        if direction == "buy":
            if stop_loss >= entry_price:
                errors.append(f"For BUY, stop_loss ({stop_loss}) must be BELOW entry_price ({entry_price})")
            if take_profit <= entry_price:
                errors.append(f"For BUY, take_profit ({take_profit}) must be ABOVE entry_price ({entry_price})")
        elif direction == "sell":
            if stop_loss <= entry_price:
                errors.append(f"For SELL, stop_loss ({stop_loss}) must be ABOVE entry_price ({entry_price})")
            if take_profit >= entry_price:
                errors.append(f"For SELL, take_profit ({take_profit}) must be BELOW entry_price ({entry_price})")

        min_rr = self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)
        if risk > 0:
            rr_ratio = reward / risk
            if rr_ratio < min_rr:
                errors.append(f"Risk-to-Reward ratio {rr_ratio:.2f} is below minimum required {min_rr:.2f}")
        else:
            errors.append("Risk is zero (entry equals stop_loss)")

        # ADR Band check (TP distance <= 80% ADR)
        try:
            adr_res = await self.execute("get_adr", {"symbol": symbol, "lookback_days": 20})
            adr_val = adr_res.get("adr_20") or adr_res.get("adr")
            if adr_val and float(adr_val) > 0:
                max_tp_dist = float(adr_val) * 0.80
                if reward > max_tp_dist:
                    errors.append(
                        f"Take profit distance ({reward:.5f}) exceeds 80% of 20-day ADR ({max_tp_dist:.5f}). "
                        f"Intraday range strategy requires TP to stay within achievable daily range."
                    )
        except Exception as adr_err:
            logger.debug(f"ADR check in manual order validation failed (non-fatal): {adr_err}")

        return errors

    async def _tool_submit_asset_analysis(self, inp: dict) -> dict:
        """Menyimpan analisis per aset dan memicu eksekusi."""
        inp.pop("submit_attempts", None)  # Toleransi tambahan argumen dari LLM
        
        if isinstance(inp, dict):
            for wrapper in ("input", "analysis", "data", "parameters", "args", "payload", "asset_analysis"):
                if wrapper in inp and isinstance(inp[wrapper], dict) and len(inp) == 1:
                    inp = inp[wrapper]
                    break
            self._resolve_symbol(inp)
            if not inp.get("symbol") and self.symbol:
                inp["symbol"] = self.symbol

        try:
            validated_data = SubmitAssetAnalysisSchema.model_validate(inp)
            inp = validated_data.model_dump(exclude_unset=True, mode="json") # Overwrite inp with clean coerced data
        except ValidationError as e:
            self.submit_attempts += 1
            error_msgs = [f"Field '{'.'.join(str(x) for x in err['loc'])}': {err['msg']}" for err in e.errors()]
            logger.warning(f"Pydantic validation failed for submit_asset_analysis: {error_msgs}")
            return {
                "status": "validation_failed",
                "errors": error_msgs,
                "error_classification": "SCHEMA_ERROR",
                "guidance": "Please fix the schema formatting errors above and call the tool again."
            }

        symbol = str(self._resolve_symbol(inp) or inp.get("symbol") or "")
        decision = str(inp.get("decision") or "")
        confidence = float(inp.get("confidence", 0.5))
        rationale  = inp.get("rationale", "")
        reeval_trigger = inp.get("reevaluation_trigger")
        entry_price: Optional[float] = None
        sl_price: Optional[float] = None
        tp_price: Optional[float] = None
        atr_value_for_validation: Optional[float] = None
        context_snapshot_id: Optional[str] = None
        context_cds_score: Optional[float] = None

        # Validation rules per spec §7.2
        errors = []
        
        # === AUTOMATED PRICED-IN ENFORCEMENT ===
        # Retrieve automated priced-in score from SystemConfig
        try:
            auto_pi_key = f'auto_pi_score_{symbol}'
            auto_pi_cfg = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == auto_pi_key)
            )).scalar_one_or_none()
            
            if auto_pi_cfg and auto_pi_cfg.value:
                import json
                auto_pi_data = json.loads(auto_pi_cfg.value)
                auto_pi_score = auto_pi_data.get('total_auto', 0)
                pi_freshness = auto_pi_data.get('computed_at')
                
                # Check freshness (must be within 2 hours)
                if pi_freshness:
                    computed_dt = datetime.fromisoformat(pi_freshness)
                    if computed_dt.tzinfo is None:
                        computed_dt = computed_dt.replace(tzinfo=timezone.utc)
                    age_minutes = (clock.now() - computed_dt).total_seconds() / 60
                    
                    if age_minutes < 120:  # Fresh data
                        submitted_pi = inp.get('priced_in_score', 0) or 0
                        
                        # Hard block: automated >= 8 means trade blocked regardless of AI assessment
                        if auto_pi_score >= 8 and decision in ('buy', 'sell'):
                            errors.append(
                                f'AUTO-PI ENFORCEMENT BLOCK: Automated priced-in calculation '
                                f'scored {auto_pi_score}/9 (FedWatch+COT+Momentum). '
                                f'Score >= 8 indicates event is fully priced in. '
                                f'Decision must be WAIT. Cannot override without explicit '
                                f'priced_in_override_justification with all 3 fields.'
                            )
                        
                        # Soft warning: if model's score deviates > 3 from automated
                        elif abs(submitted_pi - auto_pi_score) > 3 and decision in ('buy', 'sell'):
                            logger.warning(
                                f'[{symbol}] Priced-in score discrepancy: '
                                f'AI={submitted_pi}, Automated={auto_pi_score}. '
                                f'Gap > 3 recorded for audit.'
                            )
        except Exception as pi_enforcement_err:
            logger.warning(f'Auto-PI enforcement check failed (non-fatal): {pi_enforcement_err}')


        # Require confluence_score and priced_in_score for actionable decisions
        if decision in ("buy", "sell"):
            # Enforce passing verification evidence from VerificationEvidenceLedger
            ledger = getattr(self, "verification_ledger", None)
            if ledger is not None and not ledger.has_passed_evidence(symbol):
                return {
                    "status": "rejected_verification_required",
                    "errors": [
                        f"TRADE VERIFICATION GATE BLOCKED: You recommended {decision.upper()} {symbol}, "
                        f"but no passing RiskGate or PositionSize verification evidence was recorded in this cycle. "
                        f"You MUST call 'calculate_position_size' or 'get_optimal_intraday_levels' to compute and verify "
                        f"lot sizing, stop-loss, and take-profit bounds before submitting analysis."
                    ],
                    "error_classification": "UNVERIFIED_TRADE_PROPOSAL",
                    "guidance": "Call 'calculate_position_size' now with exact parameters before calling submit_asset_analysis."
                }

            conf_score = inp.get("confluence_score")
            if conf_score is None:
                errors.append(
                    "confluence_score REQUIRED for buy/sell. "
                    "Fill the CONFLUENCE SCORECARD in your system prompt "
                    "and submit the TOTAL RAW SCORE. This field is mandatory for auto-execute."
                )
            elif conf_score < 5:
                errors.append(
                    f"confluence_score {conf_score} is impossibly low for a buy/sell decision. "
                    f"Score < 5 should result in 'avoid' decision, not 'buy'/'sell'."
                )
            if inp.get("priced_in_score") is None:
                errors.append("priced_in_score is REQUIRED for buy/sell decision. Must provide a valid 1-10 score.")
                
            # Validasi confluence_factors (Fase 6 Task 3)
            factors = inp.get("confluence_factors", [])
            valid_factors = {
                "fundamental_bias", "dxy_confirms", "d1_trend", "rsi_neutral", 
                "near_fvg", "near_order_block", "in_ote_zone", "near_sr_zone", 
                "cot_aligned", "vix_ok", "post_event_entry", "session_prime", "liquidity_sweep_confirmed"
            }
            invalid_factors = [f for f in factors if f not in valid_factors]
            if invalid_factors:
                errors.append(f"Invalid confluence_factors detected: {invalid_factors}. Only use exact IDs from the prompt.")
                
            if inp.get('confluence_factors') and inp.get('confluence_score') is not None:
                declared_factors = inp['confluence_factors']
                effective_point_map = await self._get_effective_factor_point_map()
                expected_from_factors = sum((effective_point_map.get(f, 0) for f in declared_factors))
                claimed_score = inp['confluence_score']
                gap = abs(claimed_score - expected_from_factors)
                effective_tolerance = FACTOR_CONSISTENCY_TOLERANCE
                if any(f in FACTORS_WITH_VARIABLE_WEIGHT for f in declared_factors):
                    effective_tolerance += 1
                # Widen tolerance for bonus factors that stack beyond core 14
                BONUS_FACTORS_BEYOND_CORE_14 = {'liquidity_sweep_confirmed': 2, 'session_prime': 1, 'post_event_entry': 0}
                effective_tolerance += sum(v for f, v in BONUS_FACTORS_BEYOND_CORE_14.items() if f in declared_factors)
                if gap > effective_tolerance:
                    errors.append(
                        f'FACTOR_SCORE_MISMATCH: confluence_factors {declared_factors} secara matematis '
                        f'bernilai {expected_from_factors} poin, tapi confluence_score yang disubmit={claimed_score} '
                        f'(selisih {gap} > toleransi {FACTOR_CONSISTENCY_TOLERANCE}). Periksa ulang scorecard Anda — '
                        f'daftar confluence_factors harus mencerminkan skor yang Anda klaim.'
                    )
                
        # === CONFLUENCE OVERLAP DETECTION ===
        factors = inp.get('confluence_factors', [])
        if factors and decision in ('buy', 'sell'):
            zone_factors = {'near_fvg', 'near_order_block', 'in_ote_zone', 'near_sr_zone'}
            active_zone_factors = set(factors) & zone_factors
            
            if len(active_zone_factors) >= 2:
                # Potential overlap: 2+ zone factors active simultaneously
                # These often describe the same physical zone
                zone_factor_score = sum([
                    2 if 'near_fvg' in active_zone_factors else 0,
                    2 if 'near_order_block' in active_zone_factors else 0,
                    1 if 'in_ote_zone' in active_zone_factors else 0,
                    1 if 'near_sr_zone' in active_zone_factors else 0
                ])
                
                confluence_score = inp.get('confluence_score', 0) or 0
                effective_score = confluence_score
                
                if zone_factor_score >= 3:
                    # Proporsional cap: 1st zone full points, subsequent zones heavily discounted
                    effective_zone_contribution = min(max(2, 2 + (len(active_zone_factors) - 1) * 0.5), zone_factor_score)
                    # FIX: Cap deduction at -1 point (multiple zones = genuine confluence, not pure redundancy)
                    score_reduction = min(1, int(zone_factor_score - effective_zone_contribution))
                    
                    if score_reduction > 0:
                        effective_score = confluence_score - score_reduction
                        
                        logger.warning(
                            f'[{symbol}] Zone overlap cap applied: '
                            f'claimed={confluence_score}, effective={effective_score} '
                            f'(zone factors {active_zone_factors} likely describe same area, '
                            f'zone contribution capped at {effective_zone_contribution} pts)'
                        )
                        
                        # Update the submitted score to effective score
                        inp['confluence_score'] = effective_score
                    
                    # Check if effective score still meets threshold
                    min_confluence = getattr(self, "settings", {}).get('trading', {}).get(
                        'auto_execute_min_confluence', 7
                    )
                    if effective_score < min_confluence:
                        errors.append(
                            f'Zone overlap correction: effective confluence score '
                            f'{effective_score} < threshold {min_confluence}. '
                            f'Multiple zone factors ({active_zone_factors}) likely describe '
                            f'the same price area. Capped contribution: '
                            f'{zone_factor_score} → {effective_zone_contribution} pts.'
                        )
                
        if 'fundamental_bias' in factors and decision in ('buy', 'sell'):
            try:
                from utils.protocol.context_coherence import SYMBOL_CURRENCY_MAP
                pair_info = SYMBOL_CURRENCY_MAP.get(symbol)
                if pair_info:
                    brief_row_check = (await self.session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    if brief_row_check and brief_row_check.structured_json:
                        import json
                        b_data_check = json.loads(brief_row_check.structured_json)
                        conf_map = b_data_check.get('currency_confidence', {})
                        base_conf = conf_map.get(pair_info['base'], 0.5)
                        quote_conf = conf_map.get(pair_info['quote'], 0.5)
                        relevant_conf = max(base_conf, quote_conf)
                        if relevant_conf < 0.55:
                            errors.append(
                                f"FUNDAMENTAL_BIAS_LOW_CONFIDENCE: Kamu klaim faktor 'fundamental_bias' "
                                f"(+2 poin) tapi currency_confidence Stage 1 hanya {relevant_conf:.2f} "
                                f"(< 0.55 threshold). Hapus faktor ini dari confluence_factors, atau berikan "
                                f"konfirmasi independen lain (DXY, teknikal) yang menggantikannya."
                            )
            except Exception as e:
                logger.debug(f'fundamental_bias confidence check failed (non-fatal): {e}')

        if 'cot_aligned' in factors and decision in ('buy', 'sell'):
            _SYMBOL_TO_COT_LOCAL = {'XAUUSD': '088691', 'EURUSD': '099741', 'GBPUSD': '096742', 'USDJPY': '097741', 'AUDUSD': '232741'}
            cot_code = _SYMBOL_TO_COT_LOCAL.get(symbol)
            if cot_code:
                cot_row = (await self.session.execute(
                    select(COTReport).where(COTReport.market_code == cot_code)
                    .order_by(COTReport.report_date.desc()).limit(1)
                )).scalar_one_or_none()
                if not cot_row:
                    errors.append("COT_ALIGNED_NO_DATA: factor 'cot_aligned' diklaim (+1) tapi tidak ada data COT untuk simbol ini. Hapus faktor ini.")
                else:
                    days_old = (clock.now() - (cot_row.report_date.replace(tzinfo=timezone.utc) if cot_row.report_date.tzinfo is None else cot_row.report_date)).days
                    if days_old > 10:
                        errors.append(f"COT_ALIGNED_STALE: factor 'cot_aligned' diklaim (+1) tapi data COT berumur {days_old} hari (>10 hari, dianggap tidak reliable). Hapus faktor ini dari confluence_factors.")

        if 'vix_ok' in factors and decision in ('buy', 'sell'):
            vix_row = (await self.session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
            if vix_row and vix_row.close >= 20:
                errors.append(f"VIX_OK_INVALID: factor 'vix_ok' diklaim (+1) tapi VIX aktual={vix_row.close:.1f} (>=20, bukan kondisi 'ok'). Hapus faktor ini.")

        if 'liquidity_sweep_confirmed' in factors and decision in ('buy', 'sell'):
            try:
                from analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep
                sweep_check = await detect_liquidity_sweep(self.session, symbol, self.settings)
                if not (sweep_check.get('structure_confirmed') and sweep_check.get('valid_for_direction') == decision):
                    errors.append("LIQUIDITY_SWEEP_UNCONFIRMED: factor claimed (+2) but deterministic check "
                                   "does not confirm a validated sweep+structure-shift for this direction.")
            except Exception as e:
                logger.warning(f"Liquidity sweep check failed (fail-open): {e}")

        try:
            edge_cfg = self.settings.get('trading', {}).get('edge_strategy', {})
            if edge_cfg.get('macro_bias', {}).get('enabled', True):
                from analysis.calculators.macro_bias_filter import evaluate_macro_alignment
                macro_check = await evaluate_macro_alignment(self.session, symbol, decision, self.settings)
                if macro_check.get('strong_conflict'):
                    logger.warning(f"MACRO BIAS WARNING for {symbol}: {'; '.join(macro_check['reasons'])}")
            if edge_cfg.get('volatility_regime', {}).get('enabled', True):
                from analysis.calculators.regime_classifier import compute_bollinger_donchian_chop
                chop = await compute_bollinger_donchian_chop(self.session, symbol, 'H4', self.settings)
                if chop.get('chop_block'):
                    errors.append(f"VOLATILITY REGIME GATE: {chop.get('reason')} — no confirmed breakout. Submit WAIT.")
        except Exception as e:
            logger.warning(f"Mechanical gates failed (fail-open): {e}")

        if decision in ("buy", "sell"):
            if not inp.get("entry_condition"):
                errors.append("entry_condition is required for buy/sell decision")
            if inp.get("stop_loss") is None:
                errors.append("stop_loss is required for buy/sell decision")
            if inp.get("take_profit") is None:
                errors.append("take_profit is required for buy/sell decision")
            if not inp.get("invalidation"):
                errors.append("invalidation rule is required for buy/sell decision. Must specify precise price level and direction.")
                
            # TAMBAHKAN: Sanity check jarak SL/TP
            entry_zone = inp.get("entry_condition", {})
            sl_price = inp.get("stop_loss")
            tp_price = inp.get("take_profit")
            entry_price = None

            if entry_zone:
                entry_price = entry_zone.get("price") or entry_zone.get("price_high")

            if sl_price is not None and sl_price <= 0:
                errors.append("stop_loss MUST be greater than 0.")
            if tp_price is not None and tp_price <= 0:
                errors.append("take_profit MUST be greater than 0.")

            # Jika market order (entry_price None), ambil harga terakhir dari DB
            if entry_price is None and decision in ("buy", "sell"):
                try:
                    last_bar = (await self.session.execute(
                        select(PriceOHLCV)
                        .where(PriceOHLCV.symbol == symbol)
                        .where(PriceOHLCV.timestamp <= clock.now())
                        .order_by(PriceOHLCV.timestamp.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if last_bar:
                        entry_price = last_bar.close
                except Exception:
                    pass  # Non-fatal, validasi dilewati jika tidak ada data

            if entry_price and sl_price and tp_price:
                sl_dist = abs(entry_price - sl_price)
                tp_dist = abs(entry_price - tp_price)
                
                # SL tidak boleh 0
                if sl_dist == 0:
                    errors.append("stop_loss distance cannot be 0")
                    
                # RR minimal 1.0 untuk approval awal
                if sl_dist > 0 and tp_dist > 0:
                    rr = tp_dist / sl_dist if sl_dist else 0
                    try:
                        min_rr = float(getattr(self, 'settings', {}).get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.3))
                    except Exception:
                        min_rr = 1.3
                    if rr < min_rr:
                        breakeven_wr = 100.0 / (1.0 + min_rr)
                        req_tp_dist = sl_dist * min_rr
                        errors.append(
                            f"R:R ratio {rr:.2f} is below minimum {min_rr:.1f} required for positive expected value. "
                            f"For your SL distance of {sl_dist:.5f}, minimum required TP distance is {req_tp_dist:.5f}. "
                            f"Adjust TP further (within ADR band) or tighten SL to satisfy R:R >= {min_rr:.1f} "
                            f"(requires ~{breakeven_wr:.0f}% win rate for breakeven), or submit WAIT."
                        )

                # The static MIN_SL_DISTANCE check was removed. Dynamic ATR check is performed below.

                # === SANITY CHECK: TP not unrealistically far ===
                if entry_price > 0 and tp_dist / entry_price > 0.20:
                    errors.append(
                        f"TP ({tp_price}) is more than 20% from entry ({entry_price}). "
                        f"This appears to be an error. Review TP level."
                    )

            adr_ctx_for_validation = None
            if self.settings.get('trading', {}).get('risk', {}).get('intraday_range_strategy_enabled', True) and decision in ('buy', 'sell'):
                try:
                    from analysis.calculators.daily_range_calculator import compute_daily_range_context
                    _adr_probe = await compute_daily_range_context(self.session, symbol, self.settings)
                    if 'error' in _adr_probe:
                        logger.debug(f"[{symbol}] ADR context unavailable: {_adr_probe['error']}")
                    else:
                        adr_ctx_for_validation = _adr_probe
                except Exception as adr_probe_err:
                    logger.warning(f"[{symbol}] ADR context fetch failed (non-fatal, ADR gating skipped this cycle): {adr_probe_err}")

            atr_value_for_validation = None
            try:
                atr_row = (await self.session.execute(select(TechnicalIndicator).where(TechnicalIndicator.symbol == symbol).where(TechnicalIndicator.timeframe == 'H4').where(TechnicalIndicator.indicator_name == 'ATR_14').where(TechnicalIndicator.timestamp <= clock.now()).order_by(TechnicalIndicator.timestamp.desc()).limit(1))).scalar_one_or_none()
                if atr_row:
                    import json as _json_atr
                    raw_atr = _json_atr.loads(atr_row.value_json)
                    if isinstance(raw_atr, dict):
                        atr_value_for_validation = float(raw_atr.get('atr', raw_atr.get('value', 0)) or 0)
                    else:
                        atr_value_for_validation = float(raw_atr or 0)
            except Exception as atr_err:
                logger.warning(f'ATR fetch failed for {symbol}: {atr_err}')
            if decision in ('buy', 'sell'):
                _using_atr_fallback = False
                if atr_value_for_validation is None or atr_value_for_validation <= 0:
                    dynamic_fallback = await self._get_dynamic_atr_fallback(symbol)
                    if dynamic_fallback:
                        try:
                            atr_value_for_validation = float(dynamic_fallback)
                        except (TypeError, ValueError):
                            atr_value_for_validation = None
                        if atr_value_for_validation:
                            logger.warning(f'ATR_14 data unavailable for {symbol}/H4. Using 30-day average ATR fallback: {atr_value_for_validation:.5f}.')
                            _using_atr_fallback = True
                    else:
                        errors.append(f'ATR_14 data unavailable for {symbol}/H4 and 30-day average fallback also failed. Cannot validate stop-loss distance safely. Submit WAIT instead.')
                else:
                    _using_atr_fallback = False
                if atr_value_for_validation and atr_value_for_validation > 0 and entry_price and sl_price:
                    try:
                        cfg = (await self.session.execute(select(SystemConfig).where(SystemConfig.key == 'min_sl_atr_multiplier'))).scalar_one_or_none()
                        if cfg and cfg.value:
                            import json
                            multipliers = json.loads(cfg.value)
                        else:
                            multipliers = getattr(self, 'settings', {}).get('trading', {}).get('risk', {}).get('min_sl_atr_multiplier_by_symbol', {})
                        base_multiplier = multipliers.get(symbol, multipliers.get('default', 1.0))
                    except Exception:
                        base_multiplier = 1.0
                    min_sl_multiplier = base_multiplier + 0.3 if _using_atr_fallback else base_multiplier
                    min_sl_from_atr = atr_value_for_validation * min_sl_multiplier
                    sl_dist = abs(entry_price - sl_price)

                    # Defensive reconciliation: if the ATR noise-floor for this cycle happens to
                    # exceed the ADR-based ceiling, the ATR floor alone would make EVERY trade on
                    # this symbol impossible under the intraday-range framework. Relax the floor
                    # instead of hard-blocking — the dedicated ADR ceiling check below still
                    # protects against an oversized stop.
                    if adr_ctx_for_validation is not None:
                        adr_sl_ceiling = adr_ctx_for_validation['target_sl_max_distance']
                        if min_sl_from_atr > adr_sl_ceiling:
                            logger.warning(
                                f"[{symbol}] ATR noise-floor ({min_sl_from_atr:.5f}) exceeds ADR-based SL "
                                f"ceiling ({adr_sl_ceiling:.5f}) — relaxing ATR floor for this validation. "
                                f"Consider lowering min_sl_atr_multiplier_by_symbol['{symbol}']."
                            )
                            min_sl_from_atr = min(min_sl_from_atr, adr_sl_ceiling * 0.85)

                    if sl_dist < min_sl_from_atr:
                        errors.append(f"SL distance ({sl_dist:.5f}) is less than required minimum ({min_sl_multiplier}x ATR_14 or ADR-adjusted floor). {('[FALLBACK ATR USED]' if _using_atr_fallback else '')} Minimum required SL distance: {min_sl_from_atr:.5f}.")

            # === INTRADAY RANGE (ADR) TP/SL BAND VALIDATION — HARD GATE ===
            if adr_ctx_for_validation is not None and entry_price and sl_price and tp_price:
                tol = adr_ctx_for_validation.get('band_tolerance_pct', 0.10)
                tp_dist_check = abs(tp_price - entry_price)
                sl_dist_check = abs(entry_price - sl_price)
                tp_min = adr_ctx_for_validation['target_tp_min_distance'] * (1 - tol)
                tp_max = adr_ctx_for_validation['target_tp_max_distance'] * (1 + tol)
                sl_max = adr_ctx_for_validation['target_sl_max_distance'] * (1 + tol)

                if tp_dist_check < tp_min:
                    errors.append(
                        f"TP too close for intraday-range strategy: distance={tp_dist_check:.5f} < minimum "
                        f"band {tp_min:.5f} (50% of {adr_ctx_for_validation['lookback_days']}-day "
                        f"ADR={adr_ctx_for_validation['adr']:.5f}, tolerance {tol:.0%}). Target band: "
                        f"[{adr_ctx_for_validation['target_tp_min_distance']:.5f}, "
                        f"{adr_ctx_for_validation['target_tp_max_distance']:.5f}]. Find a structural level "
                        f"further out within this band, or submit WAIT if none exists."
                    )
                elif tp_dist_check > tp_max:
                    errors.append(
                        f"TP too far for intraday-range strategy: distance={tp_dist_check:.5f} > maximum "
                        f"band {tp_max:.5f} (80% of ADR={adr_ctx_for_validation['adr']:.5f}, tolerance "
                        f"{tol:.0%}). Unlikely to resolve within one trading day. Target band: "
                        f"[{adr_ctx_for_validation['target_tp_min_distance']:.5f}, "
                        f"{adr_ctx_for_validation['target_tp_max_distance']:.5f}]. Move TP closer, or submit WAIT."
                    )

                if sl_dist_check > sl_max:
                    errors.append(f"SL too wide for intraday-range strategy: distance={sl_dist_check:.5f} > maximum allowed {sl_max:.5f} (35% of ADR={adr_ctx_for_validation['adr']:.5f}). Find a tighter structural level, or submit WAIT if no valid tight stop exists.")

                if self.settings.get('trading', {}).get('risk', {}).get('strict_structural_mapping', True):
                    errors.extend(await self._validate_tp_structural_target(
                        symbol=symbol, direction=decision, tp_price=tp_price,
                        atr=atr_value_for_validation, adr_ctx=adr_ctx_for_validation))

                if adr_ctx_for_validation.get('entry_allowed') is False:
                    room_pct = adr_ctx_for_validation.get('room_remaining_pct', 0) * 100
                    errors.append(f"ENTRY BLOCKED: only {room_pct:.0f}% of today's typical ADR range remains "
                                  f"(today_range_so_far={adr_ctx_for_validation['today_range_so_far']:.5f} of "
                                  f"ADR={adr_ctx_for_validation['adr']:.5f}). Insufficient room for a fresh "
                                  f"intraday target — submit WAIT and reassess next cycle.")
                elif adr_ctx_for_validation.get('session_recommendation') == 'reduced_target':
                    room_pct = adr_ctx_for_validation.get('room_remaining_pct', 0) * 100
                    rationale = rationale + (f"\n\n[SYSTEM: Only {room_pct:.0f}% of today's typical ADR range "
                                              f"remains. Confidence discounted for reduced room.]")
                    inp['rationale'] = rationale
                    confidence = round(min(confidence, 0.5), 3) if confidence else confidence
            # === END INTRADAY RANGE (ADR) VALIDATION ===

            # === MARKET PROXIMITY CHECK for LIMIT orders ===
            if decision in ("buy", "sell") and entry_zone:
                entry_type = entry_zone.get("type", "market")
                specified_price = entry_zone.get("price")
                
                if entry_type == "limit" and specified_price is not None:
                    # Check that limit price is within 3% of current market
                    try:
                        last_bar = (await self.session.execute(
                            select(PriceOHLCV)
                            .where(PriceOHLCV.symbol == symbol)
                            .where(PriceOHLCV.timestamp <= clock.now())
                            .order_by(PriceOHLCV.timestamp.desc())
                            .limit(1)
                        )).scalar_one_or_none()
                        
                        if last_bar and last_bar.close and last_bar.close > 0:
                            price_diff_pct = abs(specified_price - last_bar.close) / last_bar.close * 100
                            
                            # Reject if limit price is more than 3% from current price
                            # (catches hallucinated price levels or stale levels)
                            if price_diff_pct > 3.0:
                                errors.append(
                                    f"Limit entry price ({specified_price}) is {price_diff_pct:.1f}% from "
                                    f"current price ({last_bar.close}). Maximum allowed deviation is 3%. "
                                    f"Either use market order or specify a realistic limit price. "
                                    f"Note: Current D1/H4 S/R zones must have a price within 3% of current market."
                                )
                    except Exception:
                        pass
            # === H4 INDICATOR STALENESS CHECK ===
            try:
                latest_indicator_ts = (await self.session.execute(
                    select(TechnicalIndicator.timestamp)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == 'H4')
                    .where(TechnicalIndicator.timestamp <= clock.now())
                    .order_by(TechnicalIndicator.timestamp.desc())
                    .limit(1)
                )).scalar_one_or_none()
                
                if latest_indicator_ts is None:
                    errors.append(
                        f'No H4 technical indicators found for {symbol}. '
                        f'Cannot assess RSI/MACD/ATR without data. Submit WAIT instead.'
                    )
                else:
                    ind_ts = latest_indicator_ts
                    if ind_ts.tzinfo is None:
                        ind_ts = ind_ts.replace(tzinfo=timezone.utc)
                    indicator_age_hours = (clock.now() - ind_ts).total_seconds() / 3600
                    if indicator_age_hours > 5.0:
                        errors.append(
                            f'H4 technical indicators for {symbol} are {indicator_age_hours:.1f}h old '
                            f'(limit: 5.0h). RSI/MACD/ATR values are stale — MT5 may be disconnected. '
                            f'Submit WAIT until fresh data is available.'
                        )
            except Exception as e:
                logger.warning(
                    f'[{symbol}] Could not verify H4 indicator freshness: {e}. '
                    f'Proceeding with analysis as a fallback.'
                )

        elif decision == "wait":
            if not inp.get("reevaluation_trigger"):
                errors.append("reevaluation_trigger is required for wait decision")
            else:
                # === WAIT QUALITY CHECK ===
                trigger = inp.get('reevaluation_trigger', {})
                trigger_detail = trigger.get('detail', '')
                trigger_type = trigger.get('type', '')
                
                # Reject vague triggers
                vague_phrases = [
                    'in 6 hours', 'next cycle', 'tomorrow', 'later',
                    're-evaluate in', 'check later', 'wait for update'
                ]
                is_vague = (
                    len(trigger_detail) < 20 or
                    any(phrase in trigger_detail.lower() for phrase in vague_phrases) and 
                    trigger_type != 'time'
                )
                
                if is_vague and trigger_type != 'time':
                    logger.warning(
                        f'[{symbol}] Vague WAIT trigger detected: "{trigger_detail[:80]}". '
                        f'AI should specify exact price level or event for re-evaluation.'
                    )
                    # Don't block, but log for quality tracking
                    rationale = rationale + (
                        f'\n[QUALITY NOTE: Reevaluation trigger could be more specific. '
                        f'Ideal: specific price level or named event.]'
                    )
                    inp['rationale'] = rationale

        if decision in ("buy", "sell"):
            if not inp.get("confluence_score"):
                errors.append("Ditolak: Confluence score kosong. Wajib diisi untuk trade buy/sell.")



        # SPECIALIST DISAGREEMENT CHECK
        if decision in ('buy', 'sell'):
            try:
                import json as _j2
                disagreement_key = f'specialist_disagreement_{symbol}'
                disagreement_cfg = (await self.session.execute(
                    select(SystemConfig).where(SystemConfig.key == disagreement_key)
                )).scalar_one_or_none()
                if disagreement_cfg and disagreement_cfg.value:
                    dd = _j2.loads(disagreement_cfg.value)
                    flagged_at = datetime.fromisoformat(dd['flagged_at'])
                    if flagged_at.tzinfo is None:
                        flagged_at = flagged_at.replace(tzinfo=timezone.utc)
                    if (clock.now() - flagged_at).total_seconds() < 900:
                        adjudication = inp.get('specialist_adjudication')
                        if not adjudication or not adjudication.get('conflict_detected'):
                            errors.append(
                                f"SPECIALIST DISAGREEMENT UNRESOLVED: technical/sentiment/macro disagreed on "
                                f"direction ({dd['biases']}). You MUST explicitly fill the 'specialist_adjudication' "
                                f"field to resolve this conflict before submitting."
                            )
                        elif not adjudication.get('resolution_path') or not adjudication.get('resolution_justification'):
                            errors.append(
                                f"SPECIALIST DISAGREEMENT UNRESOLVED: You flagged the conflict but failed to provide "
                                f"'resolution_path' or 'resolution_justification' in 'specialist_adjudication'."
                            )
            except Exception as e:
                logger.debug(f'Specialist disagreement check failed (non-fatal): {e}')

        # UNIFIED THRESHOLD ENFORCEMENT
        try:
            from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
            final_threshold, threshold_reason = await compute_unified_confluence_threshold(self.session, symbol, self.settings)
            
            conf_score_val = inp.get("confluence_score")
            if conf_score_val is not None:
                if conf_score_val < final_threshold and decision in ["buy", "sell"]:
                    errors.append(
                        f"Confluence score ({conf_score_val}) is below the mandatory unified threshold ({final_threshold}) for {symbol}. "
                        f"You MUST change decision to 'wait'. Reason: {threshold_reason}"
                    )
        except Exception as e:
            logger.debug(f"Unified threshold enforcement failed: {e}")

        # --- NEW: Cross-validate priced-in score with Stage 1 brief ---
        brief_row = None
        try:
            brief_row = (await self.session.execute(
                select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
            )).scalar_one_or_none()
            
            if brief_row and brief_row.structured_json:
                import json as _j
                brief_data = _j.loads(brief_row.structured_json)
                brief_priced_in = brief_data.get('priced_in_assessment', {})
                brief_pi_score = brief_priced_in.get('priced_in_score') if brief_priced_in else None
                
                submitted_pi = inp.get('priced_in_score')
                
                if brief_pi_score is not None and submitted_pi is not None:
                    priced_in_override = inp.get('priced_in_override_justification')
                    
                    # Check: Stage 2 asset score jauh lebih tinggi dari Stage 1 macro score
                    if submitted_pi >= 8 and brief_pi_score <= 4 and decision in ('buy', 'sell'):
                        if not (priced_in_override and all(priced_in_override.get(k) for k in ['override_reason', 'why_stage1_wrong', 'post_event_evidence'])):
                            errors.append(
                                f'PRICED-IN CONFLICT (REVERSE): Your asset-specific score={submitted_pi} '
                                f'contradicts Stage 1 macro score={brief_pi_score}. '
                                f'Stage 1 says market not priced in, but you say asset is fully priced in. '
                                f'Provide priced_in_override_justification with all 3 required fields, '
                                f'or align your assessment with macro context.'
                            )
                            
                    if brief_pi_score >= 8 and submitted_pi <= 4 and decision in ('buy', 'sell'):
                        if priced_in_override and all(priced_in_override.get(k) for k in ['override_reason', 'why_stage1_wrong', 'post_event_evidence']):
                            # Override diterima - log untuk audit
                            rationale = rationale + f'\n\n[SYSTEM: Priced-in override accepted with explicit justification: {_j.dumps(priced_in_override)}]'
                        else:
                            errors.append(f'PRICED-IN CONFLICT HARD BLOCKED: Stage 1 priced_in_score={brief_pi_score}. To override, you must fill priced_in_override_justification with all 3 required fields. Keyword-based justification in rationale is NOT accepted.')
                            
                    # IMP-6: Tighten gap tolerance 3 → 2
                    elif abs(brief_pi_score - submitted_pi) >= 2 and decision in ('buy', 'sell'):
                        direction_of_conflict = 'underestimating' if submitted_pi < brief_pi_score else 'overestimating'
                        errors.append(
                            f'PRICED-IN ASSESSMENT CONFLICT: Stage 1 macro assessment={brief_pi_score}/10, '
                            f'your asset-specific assessment={submitted_pi}/10 (gap={abs(brief_pi_score - submitted_pi)}). '
                            f'You appear to be {direction_of_conflict} priced-in risk. '
                            f'Either explicitly justify this gap in rationale, or re-evaluate your score. '
                            f'Unresolved 2+ point gaps suggest analysis inconsistency.'
                        )
                        
                    # IMP-6: Mid-range 5-7 now a THRESHOLD warning (not just a note)
                    elif 5 <= submitted_pi <= 7 and decision in ('buy', 'sell'):
                        rationale = rationale + (
                            f'\n\n[SYSTEM: Mid-range priced-in score ({submitted_pi}/10) detected. '
                            f'If major event occurs within 12h and result meets expectations, '
                            f'consider immediate re-evaluation for potential counter-trend opportunity.]'
                        )
                    
                    # IMP-6: High score (8+) without override should force 'wait'
                    if submitted_pi >= 8 and decision in ('buy', 'sell') and not priced_in_override:
                        errors.append(
                            f'PRICED-IN HIGH SCORE BLOCK: Asset priced_in_score={submitted_pi}/10 >= 8. '
                            f'Must use priced_in_override_justification to proceed with buy/sell, '
                            f'or set decision to wait.'
                        )
        except Exception as e:
            logger.debug(f'Stage 1/2 priced-in cross-validation failed (non-fatal): {e}')
        # --- END NEW ---

        # ============================================================
        # DIRECTIONAL COHERENCE CHECK & CDS RESOLUTION VALIDATION (P0-A)
        # Flags when trade direction contradicts Stage 1 brief.
        # ============================================================
        if decision in ('buy', 'sell'):
            try:
                from utils.protocol.context_coherence import SYMBOL_CURRENCY_MAP
                from utils.market.bias_utils import normalize_bias
                import json as _json
                pair_info = SYMBOL_CURRENCY_MAP.get(symbol)
                
                # Retrieve brief if not already retrieved
                if not brief_row:
                    brief_row = (await self.session.execute(
                        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
                    )).scalar_one_or_none()
                    
                if pair_info and brief_row and brief_row.structured_json:
                    _b_data = _json.loads(brief_row.structured_json)
                    _currency_bias = _b_data.get('currency_bias', {})
                    base_curr  = pair_info['base']
                    quote_curr = pair_info['quote']
                    base_bias  = normalize_bias(_currency_bias.get(base_curr, 'neutral'))
                    quote_bias = normalize_bias(_currency_bias.get(quote_curr, 'neutral'))

                    # 1. Base & Quote Directional Coherence Check
                    contradictions = []
                    if decision == 'buy':
                        if base_bias == 'bearish':
                            contradictions.append(f"{base_curr}='{base_bias}'")
                        if quote_bias == 'bullish':
                            contradictions.append(f"{quote_curr}='{quote_bias}'")
                    elif decision == 'sell':
                        if base_bias == 'bullish':
                            contradictions.append(f"{base_curr}='{base_bias}'")
                        if quote_bias == 'bearish':
                            contradictions.append(f"{quote_curr}='{quote_bias}'")

                    _reconciliation_keywords = [
                        'trust price action', 'trust brief', 'trust the brief', 'trust macro',
                        'contradicts brief', 'despite brief', 'brief is stale',
                        'overriding brief', 'post-event', 'brief may be wrong',
                        'narrative shift', 'technical overrides macro',
                        'price action contradicts', 'macro-technical conflict',
                        'brief conflict', 'coherence warning', 'divergence closed',
                        'pre-event positioning', 'divergence', 'ssvp', 'discrepancy',
                        'unresolved'
                    ]

                    if contradictions:
                        _rationale_lower = (rationale or '').lower()
                        _has_reconciliation = any(
                            kw in _rationale_lower for kw in _reconciliation_keywords
                        )

                        if not _has_reconciliation:
                            contra_str = ", ".join(contradictions)
                            logger.warning(
                                f'[{symbol}] DIRECTIONAL COHERENCE FLAG: '
                                f'{decision.upper()} submitted but Stage 1 brief indicates {contra_str}. '
                                f'No explicit reconciliation found in rationale. Appending coherence flag.'
                            )
                            rationale = (
                                rationale + (
                                    f'\n\n[SYSTEM COHERENCE FLAG: {decision.upper()} submitted '
                                    f'despite Stage 1 brief indicating {contra_str}. '
                                    f'This creates a macro-technical conflict. '
                                    f'Human reviewer: verify that rationale above explicitly '
                                    f'addresses WHY technical analysis overrides macro bias.]'
                                )
                            )
                            inp['rationale'] = rationale
            except Exception as _dcc_err:
                logger.debug(f'Directional coherence check failed (non-fatal): {_dcc_err}')
                
            context_snapshot_id = None
            context_cds_score = None
            try:
                from utils.protocol.context_snapshot import compute_context_snapshot_id
                import json as _j
                context_snapshot_id, _ = await compute_context_snapshot_id(self.session)
                now_str = clock.now().strftime('%Y%m%d_%H')
                mon_key = f'context_drift_{symbol}_{now_str}'
                mon_cfg = (await self.session.execute(
                    select(SystemConfig).where(SystemConfig.key == mon_key)
                )).scalar_one_or_none()
                if mon_cfg and mon_cfg.value:
                    mon_data = _j.loads(mon_cfg.value)
                    context_cds_score = mon_data.get('cds_score')
                    if context_cds_score is not None:
                        cds_block_threshold = self.settings.get('ssvp', {}).get('cds_thresholds', {}).get('block_buysell', 0.65) if self.settings else 0.65
                        cds_warn_threshold = self.settings.get('ssvp', {}).get('cds_thresholds', {}).get('warning', 0.35) if self.settings else 0.35
                        if context_cds_score >= cds_block_threshold:
                            errors.append(
                                f'SSVP BLOCKED: Context Discrepancy Score ({context_cds_score:.2f}) >= {cds_block_threshold:.2f}. '
                                f'You MUST submit a "wait" decision until context drift is resolved.'
                            )
                        elif context_cds_score >= cds_warn_threshold:
                            _rationale_lower = (rationale or '').lower()
                            _reconciled = any(kw in _rationale_lower for kw in [
                                'trust price action', 'trust brief', 'trust the brief',
                                'trust macro', 'divergence', 'pre-event positioning',
                                'ssvp', 'discrepancy', 'unresolved', 'contradicts brief',
                                'despite brief', 'overriding brief', 'technical overrides macro'
                            ])
                            if not _reconciled:
                                errors.append(
                                    f'SSVP ADJUDICATION REQUIRED: CDS is {context_cds_score:.2f} (Warning Level >= {cds_warn_threshold:.2f}). '
                                    f'You must explicitly acknowledge and adjudicate the conflicting context in your '
                                    f'rationale (e.g. "I trust price action because..." or "I trust the brief because...") '
                                    f'before submitting {decision.upper()}.'
                                )
            except Exception as ssvp_err:
                logger.debug(f'SSVP data retrieval failed (non-fatal): {ssvp_err}')
        # ============================================================
        # Hard ceiling: non-deterministic uplift cap
        if decision in ('buy', 'sell') and inp.get('confluence_score'):
            submitted_score = inp['confluence_score']
            from analysis.calculators.confluence_calculator import calculate_confluence
            det_calc = await calculate_confluence(self.session, symbol, decision, entry_price, sl_price, tp_price, settings=self.settings)
            det_score = det_calc.get('computed_score', 0)
            non_det_uplift = submitted_score - det_score
            # Skor deterministik dihitung ULANG di waktu submission dengan state pasar
            # real-time (sesi, RSI, dsb) yang bisa bergeser selama model bernalar
            # (15-18 tool turns). Toleransi dipisah jadi soft-warn vs hard-block agar
            # drift wajar tidak memicu rejection palsu, tapi skor yang jelas dikarang
            # tetap diblok.
            HARD_BLOCK_UPLIFT = 5   # FIX: sebelumnya 7 (hampir separuh skala 14, terlalu longgar)
            SOFT_WARN_UPLIFT = 3    # FIX: sebelumnya 5
            if non_det_uplift > HARD_BLOCK_UPLIFT:
                errors.append(f'Non-deterministic score uplift EXTREME: reported={submitted_score}, verified_base={det_score} (recomputed at submission time), uplift={non_det_uplift} > hard-block threshold {HARD_BLOCK_UPLIFT}. This cannot be explained by normal session/indicator drift. Review each non-deterministic factor claim in your rationale.')
            elif non_det_uplift > SOFT_WARN_UPLIFT:
                effective_score = det_score + SOFT_WARN_UPLIFT
                logger.warning(f'[{symbol}] Confluence uplift soft-warning: reported={submitted_score}, verified_base={det_score}, uplift={non_det_uplift}. Capping effective_score to {effective_score} for threshold re-validation.')
                try:
                    from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
                    recheck_threshold, recheck_reason = await compute_unified_confluence_threshold(self.session, symbol, self.settings)
                    if effective_score < recheck_threshold:
                        errors.append(f'Non-deterministic score uplift ({non_det_uplift}) capped effective_score to {effective_score}/14, which is BELOW the required threshold ({recheck_threshold}). Reported score {submitted_score} cannot be trusted at face value for this decision. Submit WAIT instead, or provide additional deterministic evidence.')
                except Exception as e:
                    logger.debug(f'Unified threshold recheck for uplift cap failed (non-fatal): {e}')
                rationale = rationale + f'\n\n[SYSTEM NOTE: Deterministic re-check at submission time scored {det_score}/14 vs reported {submitted_score}/14 (delta={non_det_uplift}). Effective score capped at {effective_score}/14 for threshold validation; flagged for audit.]'
                inp['rationale'] = rationale
        if errors:
            attempts = self.submit_attempts + 1
            # Gunakan SystemConfig untuk counter persisten
            try:
                now_str = clock.now().strftime('%Y%m%d_%H')
                # Menggunakan tanggal_jam sebagai cycle proxy
                cfg_key = f"submit_attempt_{symbol}_{now_str}"
                cfg = (await self.session.execute(
                    select(SystemConfig).where(SystemConfig.key == cfg_key)
                )).scalar_one_or_none()
                
                if cfg and cfg.value is not None:
                    attempts = int(cfg.value) + 1
                    cfg.value = str(attempts)
                else:
                    attempts = 1
                    self.session.add(SystemConfig(key=cfg_key, value="1"))
                await self.session.commit()
            except Exception as e:
                logger.error(f"Failed to track submit attempts: {e}")
                self.submit_attempts += 1
                attempts = self.submit_attempts
            
            STRUCTURAL_ERRORS = [
                'stop_loss is required',
                'take_profit is required', 
                'r:r ratio',
                'sl distance',
                'invalid confluence_factors'
            ]
            
            THRESHOLD_ERRORS = [
                'confluence_score',
                'priced_in_score',
                'adaptive threshold'  
            ]

            GATE_ERRORS = [
                'volatility regime gate',
                'macro bias gate',
                'liquidity sweep',
                'ssvp blocked',
                'entry blocked: only',
                'adr range remains'
            ]
            
            def classify_errors(errs: list[str]) -> str:
                for err in errs:
                    for gate in GATE_ERRORS:
                        if gate.lower() in err.lower():
                            return 'GATE'
                for err in errs:
                    for structural in STRUCTURAL_ERRORS:
                        if structural.lower() in err.lower():
                            return 'STRUCTURAL'
                for err in errs:
                    for threshold in THRESHOLD_ERRORS:
                        if threshold.lower() in err.lower():
                            return 'THRESHOLD'
                return 'FATAL'
                
            error_class = classify_errors(errors)

            if error_class == 'GATE':
                logger.info(f"[{symbol}] Mechanical risk gate blocked entry. Gracefully forcing WAIT.")
                decision = "wait"
                confidence = 0.0
                first_err = errors[0] if errors else "rule-based filter"
                rationale = f"Mechanical Risk Gate: Entry blocked by rule-based filter.\n" + "\n".join(errors)
                
                # Synthetic Trigger: ensure asset is monitored for condition resolution
                if not reeval_trigger and entry_price:
                    direction_str = "above" if inp.get("decision") == "buy" else "below"
                    reeval_trigger = {
                        "type": "price_level",
                        "symbol": symbol,
                        "price": float(entry_price),
                        "direction": direction_str,
                        "detail": f"Mechanical gate ({first_err[:40]}...) re-evaluation upon price reaching {entry_price}"
                    }
                elif not reeval_trigger:
                    reeval_trigger = {
                        "type": "time",
                        "symbol": symbol,
                        "hours": 2,
                        "detail": "Mechanical gate auto-reevaluate after 2 hours"
                    }
                errors = []
            elif error_class == 'FATAL' or attempts >= 3:
                logger.error(f"[{symbol}] submit_asset_analysis failed validation ({error_class} or attempt {attempts}). Forcing WAIT.")
                decision = "wait"
                confidence = 0.0
                rationale = f"System override: Forced WAIT due to {error_class} error or max attempts reached.\n" + "\n".join(errors)
                if not reeval_trigger:
                    reeval_trigger = {
                        "type": "time",
                        "symbol": symbol,
                        "hours": 2,
                        "detail": "Forced WAIT auto-reevaluate after 2 hours"
                    }
                errors = []
            else:
                logger.warning(f"submit_asset_analysis validation failed for {symbol} (Attempt {attempts}): {errors}")
                return {
                    "status": "validation_failed",
                    "errors": errors,
                    "error_classification": error_class,
                    "guidance": {
                        'STRUCTURAL': 'Recalculate entry/SL/TP. Try different structural level.',
                        'THRESHOLD': 'Score insufficient. Submit WAIT with specific trigger.',
                        'GATE': 'Mechanical gate active. Submit WAIT.',
                        'FATAL': 'Submit WAIT immediately. Do not retry.'
                    }.get(error_class, ''),
                    "attempt": attempts
                }

        import json as _json

        # Get most recent brief for FK
        brief = (await self.session.execute(
            select(FundamentalBrief.id).order_by(FundamentalBrief.generated_at.desc()).limit(1)
        )).scalar_one_or_none()

        entry_cond = inp.get("entry_condition")
        reeval_trigger = reeval_trigger or inp.get("reevaluation_trigger")
        if reeval_trigger and not reeval_trigger.get("symbol"):
            reeval_trigger["symbol"] = symbol
        
        # EXTRACT NEW PRICED-IN AND NEWS FIELDS
        priced_in_score = inp.get("priced_in_score")
        priced_in_override_justification = inp.get("priced_in_override_justification")
        confluence_score = inp.get("confluence_score")
        confluence_factors = inp.get("confluence_factors")
        key_news_events_considered = inp.get("key_news_events_considered", [])
        news_impact_assessment = inp.get("news_impact_assessment", "")
        
        invalidation_price = inp.get("invalidation_price")
        invalidation_direction = inp.get("invalidation_direction")

        if decision in ('buy', 'sell') and entry_price and atr_value_for_validation:
            proximity_warnings = await self._validate_smc_entry_proximity(
                symbol=symbol,
                entry_price=entry_price,
                direction=decision,
                stop_loss=float(inp["stop_loss"]) if inp.get("stop_loss") is not None else 0.0,
                atr=atr_value_for_validation
            )
            if proximity_warnings:
                for w in proximity_warnings:
                    logger.warning(f'[{symbol}] {w}')
                rationale = rationale + '\n\n[SYSTEM VALIDATION WARNINGS]\n' + '\n'.join(proximity_warnings)

        if 'context_snapshot_id' not in locals():
            context_snapshot_id = None
            context_cds_score = None

        # Fetch specialist biases from system config (do not delete prematurely; lifecycle managed by per_asset_stage)
        specialist_biases_json = None
        try:
            key = f'pending_specialist_biases_{symbol}'
            cfg = (await self.session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
            if cfg and cfg.value:
                specialist_biases_json = cfg.value
        except Exception as e:
            logger.debug(f'Failed to fetch staged specialist biases: {e}')

        # Idempotency guard for fallback LLM retries (prevent duplicate AssetAnalysis rows within SAME execution session)
        if self._submitted_analysis_id is not None:
            existing = await self.session.get(AssetAnalysis, self._submitted_analysis_id)
            if existing:
                logger.info(f"Updating existing AssetAnalysis ID {existing.id} in current execution session for {symbol}")
                existing.generated_at = clock.now()
                existing.brief_id = brief
                existing.decision = str(decision or "wait")
                existing.confidence = confidence
                existing.entry_zone = _json.dumps(entry_cond) if entry_cond else None
                existing.stop_loss = inp.get("stop_loss")
                existing.take_profit = inp.get("take_profit")
                existing.invalidation = _json.dumps(inp.get("invalidation")) if isinstance(inp.get("invalidation"), dict) else str(inp.get("invalidation")) if inp.get("invalidation") is not None else None
                existing.invalidation_price = invalidation_price
                existing.invalidation_direction = invalidation_direction
                existing.reevaluation_trigger = _json.dumps(reeval_trigger) if reeval_trigger else None
                existing.rationale = rationale
                existing.priced_in_score = priced_in_score
                existing.priced_in_override_justification = priced_in_override_justification
                existing.confluence_score = confluence_score
                existing.confluence_factors_json = _json.dumps(confluence_factors) if confluence_factors else None
                if specialist_biases_json:
                    existing.specialist_biases_json = specialist_biases_json
                existing.context_snapshot_id = context_snapshot_id
                existing.ssvp_cds_score_at_analysis = context_cds_score
                existing.decision_source = "llm_stage2"
                existing_rationale = existing.rationale or ""
                if key_news_events_considered:
                    news_strs = [str(x).strip() for x in key_news_events_considered if str(x).strip()]
                    if news_strs:
                        existing_rationale += f"\n\nNews Events Considered: {', '.join(news_strs)}"
                if news_impact_assessment:
                    existing_rationale += f"\nNews Impact Assessment: {str(news_impact_assessment).strip()}"
                existing.rationale = existing_rationale
                await self.session.commit()
                return {
                    "status": "saved",
                    "analysis_id": existing.id,
                    "symbol": symbol,
                    "decision": existing.decision,
                    "message": "Analysis updated (idempotent retry in same session)."
                }

        analysis = AssetAnalysis(
            symbol=symbol,
            generated_at=clock.now(),
            brief_id=brief,
            decision=str(decision or "wait"),
            confidence=confidence,
            entry_zone=_json.dumps(entry_cond) if entry_cond else None,
            stop_loss=inp.get("stop_loss"),
            take_profit=inp.get("take_profit"),
            invalidation=_json.dumps(inp.get("invalidation")) if isinstance(inp.get("invalidation"), dict) else str(inp.get("invalidation")) if inp.get("invalidation") is not None else None,
            invalidation_price=invalidation_price,
            invalidation_direction=invalidation_direction,
            reevaluation_trigger=_json.dumps(reeval_trigger) if reeval_trigger else None,
            rationale=rationale,
            priced_in_score=priced_in_score,
            priced_in_override_justification=priced_in_override_justification,
            confluence_score=confluence_score,
            confluence_factors_json=_json.dumps(confluence_factors) if confluence_factors else None,
            specialist_biases_json=specialist_biases_json,
            context_snapshot_id=context_snapshot_id,
            ssvp_cds_score_at_analysis=context_cds_score,
            decision_source="llm_stage2",
        )
        
        # Ambil harga terkini saat AI menyimpan analisis
        try:
            last_bar = (await self.session.execute(
                select(PriceOHLCV).where(PriceOHLCV.symbol == symbol).where(PriceOHLCV.timestamp <= clock.now())
                .order_by(PriceOHLCV.timestamp.desc()).limit(1)
            )).scalar_one_or_none()
            if last_bar:
                analysis.price_at_analysis = last_bar.close
        except Exception as e:
            logger.warning(f"Failed to fetch price_at_analysis for {symbol}: {e}")
        
        # If DB model doesn't have key_news_events_considered, append to rationale
        analysis_rationale = analysis.rationale or ""
        if key_news_events_considered:
            news_strs = [str(x).strip() for x in key_news_events_considered if str(x).strip()]
            if news_strs:
                analysis_rationale += f"\n\nNews Events Considered: {', '.join(news_strs)}"
        if news_impact_assessment:
            analysis_rationale += f"\nNews Impact Assessment: {str(news_impact_assessment).strip()}"
        analysis.rationale = analysis_rationale
        self.session.add(analysis)
        await self.session.flush()  # get analysis.id before adding triggers
        self._submitted_analysis_id = analysis.id

        # Cancel any previous pending triggers for this symbol (superseded by new analysis)
        try:
            prev_pending_stmt = (
                select(TradeTrigger.id)
                .join(AssetAnalysis, TradeTrigger.asset_analysis_id == AssetAnalysis.id)
                .where(AssetAnalysis.symbol == symbol)
                .where(TradeTrigger.status == "pending")
                .where(TradeTrigger.asset_analysis_id != analysis.id)
            )
            prev_trigger_ids = (await self.session.execute(prev_pending_stmt)).scalars().all()
            if prev_trigger_ids:
                await self.session.execute(
                    update(TradeTrigger)
                    .where(TradeTrigger.id.in_(prev_trigger_ids))
                    .values(status="cancelled")
                )
                logger.info(f"Cancelled {len(prev_trigger_ids)} superseded pending triggers for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to cancel superseded triggers for {symbol}: {e}")

        # Save trigger
        if reeval_trigger:
            raw_type = reeval_trigger.get("type", "time")
            norm_type = "price_level" if raw_type in ("price", "price_level") else raw_type
            trigger = TradeTrigger(
                asset_analysis_id=analysis.id,
                trigger_type=norm_type,
                condition_json=_json.dumps(reeval_trigger),
                status="pending",
            )
            self.session.add(trigger)

        await self.session.commit()
        conf_display = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence)
        logger.info(f"Asset analysis saved: {symbol} → {decision} (confidence={conf_display})")

        msg = "Analysis saved successfully."
        if decision == 'wait' and "System override: Forced WAIT" in rationale:
            msg = f"Analysis FORCEFULLY saved as WAIT due to validation errors. DO NOT RETRY. Errors: {rationale}"

        return {
            "status": "saved",
            "analysis_id": analysis.id,
            "symbol": symbol,
            "decision": decision,
            "message": msg
        }

    async def _tool_propose_action(self, inp: dict) -> dict:
        """Propose manual action requiring confirmation."""
        from analysis.tools.handlers.position_mgmt import handle_propose_action
        return await handle_propose_action(inp, session=self.session, executor=self)

    async def _tool_delegate_specialist_analysis(self, inp: dict) -> dict:
        """Execute delegated specialist analysis in isolated subagent harness."""
        role = inp.get("specialist_role", "technical_specialist")
        prompt = inp.get("task_prompt", "")
        symbol = inp.get("symbol", "")

        from analysis.subagent.isolated_harness import IsolatedSubagentRunner
        from analysis.providers.llm_factory import get_client_for_task
        from analysis.tools.tools_definitions import STAGE2_ESSENTIAL_TOOLS, STAGE1_TOOLS

        runner = IsolatedSubagentRunner(settings=self.settings)
        if role == "macro_specialist":
            client = get_client_for_task("stage1_fundamental", self.settings)
            tools = STAGE1_TOOLS
            sys_prompt = "You are an institutional macro specialist. Deliver concise, evidence-grounded macro analysis."
        elif role == "sentiment_specialist":
            client = get_client_for_task("sentiment_analyst", self.settings)
            tools = STAGE1_TOOLS
            sys_prompt = "You are a market sentiment specialist. Deliver concise sentiment and positioning analysis."
        elif role == "risk_specialist":
            client = get_client_for_task("risk_gate", self.settings)
            tools = STAGE2_ESSENTIAL_TOOLS
            sys_prompt = "You are a quantitative risk specialist. Evaluate structural levels, invalidation, and R:R."
        else:
            client = get_client_for_task("stage2_per_asset_primary", self.settings)
            tools = STAGE2_ESSENTIAL_TOOLS
            sys_prompt = "You are an SMC technical specialist. Analyze market structure, order blocks, and key liquidity zones."

        user_content = f"Symbol: {symbol}\nTask: {prompt}" if symbol else prompt
        messages = [{"role": "user", "content": user_content}]

        res = await runner.run_isolated(
            role_name=role,
            llm_client=client,
            system_prompt=sys_prompt,
            messages=messages,
            tools=tools,
            stage_name="chat_delegation",
            timeout=180,
            session=self.session,
        )

        return {
            "status": "success" if res.get("success") else "error",
            "specialist_role": role,
            "summary": res.get("final_text") or res.get("error", "No output"),
            "tool_calls_made": res.get("tool_calls_made", 0),
        }




