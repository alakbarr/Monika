"""
Dynamic Subagent Spawner Pool (Autonomous High-Concurrency Architecture).

Orchestrates ad-hoc, task-specific child subagents with:
- Isolated context sandboxes (zero context pollution from parent or sibling workers)
- Specialized, domain-filtered toolsets
- Strict execution timeouts (asyncio.wait_for)
- Distillation token contract enforcement
- Dynamic query decomposition into targeted research specialists
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Set

from analysis.providers.llm_factory import get_client_for_task
from utils.llm.prompt_compressor import estimate_tokens, truncate_to_budget

logger = logging.getLogger("TradingAgent.SubagentSpawner")


@dataclass
class SubagentSpec:
    """Specification for an ad-hoc subagent worker."""
    worker_id: str
    role: str
    system_prompt: str
    query: str
    tools: List[Dict[str, Any]] = field(default_factory=list)
    task_role: str = "deep_research"
    timeout_seconds: float = 60.0
    max_distilled_tokens: int = 1500
    tool_executor: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    spawn_depth: int = 0
    can_spawn: bool = True


@dataclass
class SubagentResult:
    """Standardized result returned by a SubagentWorker."""
    worker_id: str
    role: str
    success: bool
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls_made: int = 0
    elapsed_seconds: float = 0.0
    error: Optional[str] = None
    raw_result: Optional[Dict[str, Any]] = None


class SubagentWorker:
    """
    Dedicated worker executing a single specialized subtask in an isolated sandbox.
    Prevents context bleeding and enforces strict token & timeout boundaries.
    """

    def __init__(
        self,
        spec: SubagentSpec,
        client: Optional[Any] = None,
        settings: Optional[dict] = None,
    ):
        self.spec = spec
        self.settings = settings or {}
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            return get_client_for_task(self.spec.task_role, self.settings)
        except Exception as e:
            logger.warning(
                f"SubagentWorker [{self.spec.worker_id}]: Failed resolving client for role "
                f"'{self.spec.task_role}': {e}. Falling back to default deep_research."
            )
            try:
                return get_client_for_task("deep_research", self.settings)
            except Exception:
                return None

    async def run(self) -> SubagentResult:
        """
        Executes the subagent task within an isolated context sandbox and strict timeout.
        """
        start_t = time.monotonic()
        client = self._get_client()

        if not client:
            return SubagentResult(
                worker_id=self.spec.worker_id,
                role=self.spec.role,
                success=False,
                content="",
                elapsed_seconds=0.0,
                error=f"No LLM client available for task role '{self.spec.task_role}'",
            )

        logger.info(
            f"SubagentWorker [{self.spec.worker_id} - {self.spec.role}] starting. "
            f"Tools: {len(self.spec.tools)}, Timeout: {self.spec.timeout_seconds}s"
        )

        try:
            # Isolated context execution: empty conversation history
            # Ensures zero context pollution
            async def _execute():
                if hasattr(client, "run_chat_loop"):
                    return await client.run_chat_loop(
                        system_prompt=self.spec.system_prompt,
                        conversation_history=[],
                        new_user_message=self.spec.query,
                        tools=self.spec.tools,
                        tool_executor=self.spec.tool_executor,
                    )
                elif hasattr(client, "generate_content"):
                    return await client.generate_content(
                        system_prompt=self.spec.system_prompt,
                        user_message=self.spec.query,
                        tools=self.spec.tools,
                    )
                else:
                    raw_text = await client.generate(
                        prompt=f"{self.spec.system_prompt}\n\n{self.spec.query}"
                    )
                    return {"reply": raw_text}

            # Enforce strict execution timeout
            raw_res = await asyncio.wait_for(
                _execute(),
                timeout=self.spec.timeout_seconds,
            )

            elapsed = time.monotonic() - start_t

            # Extract content and token metadata
            if isinstance(raw_res, dict):
                content = raw_res.get("reply") or raw_res.get("content") or ""
                in_tok = raw_res.get("input_tokens", 0)
                out_tok = raw_res.get("output_tokens", 0)
                tool_calls = raw_res.get("tool_calls_made", 0)
            else:
                content = str(raw_res)
                in_tok = estimate_tokens(self.spec.system_prompt + self.spec.query)
                out_tok = estimate_tokens(content)
                tool_calls = 0

            # Distillation contract enforcement
            content_tok = estimate_tokens(content)
            if content_tok > self.spec.max_distilled_tokens:
                logger.info(
                    f"SubagentWorker [{self.spec.worker_id}] output ({content_tok} tok) "
                    f"exceeded contract ({self.spec.max_distilled_tokens} tok). Distilling."
                )
                content = truncate_to_budget(content, max_tokens=self.spec.max_distilled_tokens)

            return SubagentResult(
                worker_id=self.spec.worker_id,
                role=self.spec.role,
                success=True,
                content=content,
                input_tokens=in_tok,
                output_tokens=out_tok,
                tool_calls_made=tool_calls,
                elapsed_seconds=round(elapsed, 2),
                raw_result=raw_res if isinstance(raw_res, dict) else {"reply": content},
            )

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_t
            logger.warning(
                f"SubagentWorker [{self.spec.worker_id} - {self.spec.role}] "
                f"TIMED OUT after {self.spec.timeout_seconds}s"
            )
            return SubagentResult(
                worker_id=self.spec.worker_id,
                role=self.spec.role,
                success=False,
                content=f"[Timeout] Analisis {self.spec.role} melampaui batas waktu ({self.spec.timeout_seconds}s).",
                elapsed_seconds=round(elapsed, 2),
                error=f"Timeout after {self.spec.timeout_seconds}s",
            )
        except Exception as e:
            elapsed = time.monotonic() - start_t
            logger.error(
                f"SubagentWorker [{self.spec.worker_id} - {self.spec.role}] execution failed: {e}",
                exc_info=True,
            )
            return SubagentResult(
                worker_id=self.spec.worker_id,
                role=self.spec.role,
                success=False,
                content=f"[Error] Analisis {self.spec.role} mengalami kesalahan: {e}",
                elapsed_seconds=round(elapsed, 2),
                error=str(e),
            )


class DynamicSubagentPool:
    """
    Dynamic Subagent Pool.
    Manages pool lifecycle, parallel execution, semaphore throttling,
    and intelligent query decomposition.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        max_concurrency: int = 4,
        default_timeout: float = 75.0,
        max_spawn_depth: int = 2,
    ):
        self.settings = settings or {}
        self.max_concurrency = max_concurrency
        self.default_timeout = default_timeout
        self.max_spawn_depth = max_spawn_depth
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def spawn_worker(
        self,
        spec: SubagentSpec,
        client: Optional[Any] = None,
        progress_callback: Optional[Callable[[str], Any]] = None,
    ) -> SubagentResult:
        """Runs a single worker within semaphore throttling and depth control."""
        if spec.spawn_depth >= self.max_spawn_depth:
            logger.warning(
                f"[SubagentPool] Blocked worker {spec.worker_id} ({spec.role}): "
                f"spawn depth {spec.spawn_depth} >= max_spawn_depth {self.max_spawn_depth}"
            )
            return SubagentResult(
                worker_id=spec.worker_id,
                role=spec.role,
                success=False,
                content="",
                error=f"Max spawn depth {self.max_spawn_depth} exceeded (depth={spec.spawn_depth})",
            )

        if not spec.can_spawn and spec.spawn_depth > 0:
            logger.warning(
                f"[SubagentPool] Blocked worker {spec.worker_id} ({spec.role}): "
                f"leaf role restriction (can_spawn=False)"
            )
            return SubagentResult(
                worker_id=spec.worker_id,
                role=spec.role,
                success=False,
                content="",
                error="Role is restricted from spawning further subagents",
            )

        async with self._semaphore:
            if progress_callback:
                try:
                    cb = progress_callback(f"⏳ Subagent aktif: {spec.role}...")
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception:
                    pass

            worker = SubagentWorker(spec=spec, client=client, settings=self.settings)
            res = await worker.run()

            if progress_callback:
                status_icon = "✅" if res.success else "⚠️"
                try:
                    cb = progress_callback(f"{status_icon} Subagent selesai: {spec.role}")
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception:
                    pass

            return res

    async def run_parallel(
        self,
        specs: List[SubagentSpec],
        client: Optional[Any] = None,
        progress_callback: Optional[Callable[[str], Any]] = None,
    ) -> List[SubagentResult]:
        """
        Executes a roster of SubagentWorkers in parallel with semaphore concurrency guarding.
        """
        if not specs:
            return []

        logger.info(
            f"DynamicSubagentPool: Launching {len(specs)} workers "
            f"(max concurrency: {self.max_concurrency})..."
        )

        tasks = [
            self.spawn_worker(spec, client=client, progress_callback=progress_callback)
            for spec in specs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    def decompose_research_query(
        self,
        query: str,
        base_system_prompt: str,
        available_tools: List[Dict[str, Any]],
        tool_executor: Optional[Any] = None,
    ) -> List[SubagentSpec]:
        """
        Dynamically analyzes user research query and decomposes it into a tailored roster
        of specialist subagents with specialized prompts and domain-isolated toolsets.
        """
        q_lower = query.lower()
        tools_by_name = {t.get("name"): t for t in available_tools if t.get("name")}

        # 1. Macro & Rates toolset
        macro_names = {
            "get_market_session", "get_fundamental_brief", "get_economic_calendar",
            "get_news_items", "get_news_digest", "get_vix", "get_dxy",
            "get_cot_report", "get_bond_yield_spreads", "get_spread_snapshot", "web_search",
            "get_fedwatch_probabilities", "get_treasury_yields", "get_interest_rates",
            "get_eia_oil_inventory"
        }
        # 2. Technical & SMC toolset
        tech_names = {
            "get_chart", "get_price_history", "get_technical_indicators",
            "get_multi_timeframe_summary", "get_atr", "get_swing_points",
            "get_structure_breaks", "get_smc_zones", "get_fibonacci_levels",
            "get_price_momentum", "get_daily_range_context", "get_optimal_intraday_levels",
            "get_market_regime", "get_timesfm_forecast"
        }
        # 3. Sentiment & Positioning toolset
        sent_names = {
            "get_retail_sentiment", "get_forex_sentiment", "get_fxssi_sentiment",
            "get_funding_rate", "get_fear_greed", "get_structured_sentiment",
            "get_cot_report", "save_market_intelligence", "list_active_intelligence"
        }
        # 4. Cross-Asset & Correlation toolset
        cross_asset_names = {
            "get_dxy", "get_vix", "get_bond_yield_spreads", "get_spread_snapshot",
            "get_multi_timeframe_summary", "get_chart", "get_technical_indicators",
            "web_search", "get_treasury_yields"
        }
        # 5. Order Flow & Liquidity Sweep toolset
        order_flow_names = {
            "get_smc_zones", "get_structure_breaks", "get_swing_points",
            "get_technical_indicators", "get_chart", "get_price_momentum"
        }
        # 6. Geopolitical & News Drift toolset
        news_drift_names = {
            "get_news_items", "get_news_digest", "get_economic_calendar",
            "get_vix", "web_search", "save_market_intelligence"
        }

        def _filter_tools(names: Set[str]) -> List[Dict[str, Any]]:
            return [tools_by_name[n] for n in names if n in tools_by_name]

        specs: List[SubagentSpec] = []

        # --- Base Specialist 1: Macro & Rates ---
        cb_framework_text = ""
        try:
            from skills.loader import load_skill
            cb_skill = load_skill("central_banks_framework")
            if cb_skill:
                cb_framework_text = f"\n\n[AUTHORITATIVE CENTRAL BANK KNOWLEDGE]\n{cb_skill}\n"
        except Exception:
            pass

        specs.append(
            SubagentSpec(
                worker_id="worker_macro",
                role="Macro & Central Bank Specialist",
                system_prompt=(
                    f"{base_system_prompt}{cb_framework_text}\n\n"
                    "[SPECIALIST ROLE]: You are the Macro & Rates Specialist. "
                    "Conduct an exhaustive deep dive on macroeconomic fundamentals, yield curves, "
                    "central bank interest rate trajectory, inflation, and growth dynamics. "
                    "Provide concrete data, yields, and policy expectations across all 5 central banks.\n\n"
                    "MANDATORY MACRO SEARCH CHECKLIST:\n"
                    "1. [ ] Rate Probabilities: Call `get_fedwatch_probabilities` for CME FedWatch detail, and `get_central_bank_expectations` (for FED, ECB, BOE, BOJ, RBA). (If empty/unavailable, call `web_search`).\n"
                    "2. [ ] Yield Curve & Spreads: Call `get_treasury_yields` (2Y, 10Y, inversion status) and `get_bond_yield_spreads` (both 2Y short-end policy spreads and 10Y benchmark spreads for US-DE, US-UK, US-JP, US-AU).\n"
                    "3. [ ] Central Bank Baseline Rates: Call `get_interest_rates` for official benchmark rates and mandate profiles (FED dual, ECB single, BOE tiered, BOJ deflation exit, RBA triple).\n"
                    "4. [ ] Energy / Inventory: Call `get_eia_oil_inventory` if investigating crude oil or energy inflation.\n"
                    "5. [ ] Calendar & Volatility: Call `get_economic_calendar`, `get_news_digest`, and `get_vix` / `get_dxy`."
                ),
                query=f"Riset makroekonomi, suku bunga, yield spreads, DXY/VIX, dan katalis ekonomi: {query}",
                tools=_filter_tools(macro_names),
                timeout_seconds=self.default_timeout,
                tool_executor=tool_executor,
            )
        )

        # --- Base Specialist 2: Technical SMC & Quant Forecast ---
        specs.append(
            SubagentSpec(
                worker_id="worker_tech",
                role="Technical & SMC Liquidity Specialist",
                system_prompt=(
                    f"{base_system_prompt}\n\n"
                    "[SPECIALIST ROLE]: You are the Technical & SMC Liquidity Specialist. "
                    "Analyze market structure (BOS/CHoCH), Order Blocks, Fair Value Gaps (FVG), "
                    "liquidity sweeps, Fibonacci retracements, and TimesFM quantile forecasts. "
                    "Highlight exact invalidation and key reaction levels."
                ),
                query=f"Riset struktur teknikal, zona SMC, likuiditas, dan proyeksi TimesFM: {query}",
                tools=_filter_tools(tech_names),
                timeout_seconds=self.default_timeout,
                tool_executor=tool_executor,
            )
        )

        # --- Base Specialist 3: Institutional & Retail Sentiment ---
        specs.append(
            SubagentSpec(
                worker_id="worker_sent",
                role="Institutional & Retail Sentiment Specialist",
                system_prompt=(
                    f"{base_system_prompt}\n\n"
                    "[SPECIALIST ROLE]: You are the Institutional & Sentiment Specialist. "
                    "Analyze CFTC COT institutional positioning, retail positioning bias (long/short skew), "
                    "funding rates, and market sentiment extremes (Fear & Greed). "
                    "Identify asymmetric crowded trade risks."
                ),
                query=f"Riset sentimen institusi (COT), posisi ritel, funding rates, dan skew pasar: {query}",
                tools=_filter_tools(sent_names),
                timeout_seconds=self.default_timeout,
                tool_executor=tool_executor,
            )
        )

        # --- Dynamic Specialist 4 (Context-Triggered) ---
        has_cross_asset = any(k in q_lower for k in [
            "korelasi", "correlation", "cross-asset", "intermarket", "dxy", "yield",
            "emas vs", "gold vs", "btc vs", "oil vs", "hubungan"
        ])
        has_order_flow = any(k in q_lower for k in [
            "order flow", "orderflow", "dom", "depth", "cvd", "absorpsi", "absorption",
            "sweep", "liquidity sweep", "stop hunt"
        ])
        has_news_drift = any(k in q_lower for k in [
            "breaking", "geopolitik", "perang", "konflik", "tarif", "drift", "whisper",
            "konsensus", "bocor", "kejutan", "pre-event", "nfp", "fomc", "cpi"
        ])

        if has_order_flow:
            specs.append(
                SubagentSpec(
                    worker_id="worker_orderflow",
                    role="Order Flow & Liquidity Sweep Specialist",
                    system_prompt=(
                        f"{base_system_prompt}\n\n"
                        "[SPECIALIST ROLE]: You are the Order Flow & Liquidity Sweep Specialist. "
                        "Investigate institutional liquidity pools, buy-side/sell-side liquidity sweeps, "
                        "tick volume delta absorptions, and hidden stop hunts around critical highs/lows."
                    ),
                    query=f"Investigasi order flow, penyerapan likuiditas, dan sweeping level: {query}",
                    tools=_filter_tools(order_flow_names),
                    timeout_seconds=self.default_timeout,
                    tool_executor=tool_executor,
                )
            )
        elif has_cross_asset:
            specs.append(
                SubagentSpec(
                    worker_id="worker_cross_asset",
                    role="Cross-Asset Macro Correlation Specialist",
                    system_prompt=(
                        f"{base_system_prompt}\n\n"
                        "[SPECIALIST ROLE]: You are the Cross-Asset & Macro Correlation Specialist. "
                        "Investigate intermarket spillover effects, US Treasury yield spreads vs DXY, "
                        "commodity terms of trade, and cross-asset beta."
                    ),
                    query=f"Investigasi korelasi lintas aset, yield spreads, dan transmisi pasar: {query}",
                    tools=_filter_tools(cross_asset_names),
                    timeout_seconds=self.default_timeout,
                    tool_executor=tool_executor,
                )
            )
        elif has_news_drift:
            specs.append(
                SubagentSpec(
                    worker_id="worker_news_drift",
                    role="Geopolitical & News Drift Specialist",
                    system_prompt=(
                        f"{base_system_prompt}\n\n"
                        "[SPECIALIST ROLE]: You are the Geopolitical & News Drift Specialist. "
                        "Investigate breaking headline risks, geopolitical escalation/de-escalation, "
                        "consensus whisper deviations, and post-news price narrative drift."
                    ),
                    query=f"Investigasi dinamika berita terkini, risiko geopolitik, dan ekspektasi whisper: {query}",
                    tools=_filter_tools(news_drift_names),
                    timeout_seconds=self.default_timeout,
                    tool_executor=tool_executor,
                )
            )

        return specs
