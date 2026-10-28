# ==============================================================================
# File: application/agent/chat/tiers.py
# ==============================================================================

"""
Execution tier runners (lite, medium, deep, research) and model provider adapters.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from monika.application.analysis.tools.tools_definitions import (
    OPERATOR_INTERACTIVE_TOOLS,
    PROPOSE_ACTION,
    SAVE_MARKET_INTELLIGENCE,
)
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import UserMarketIntel

from monika.application.agent.chat.base import _ChatAgentMixinBase, logger

TIER_LITE_TOOL_NAMES: tuple[str, ...] = (
    "get_account_info",
    "get_market_quote",
    "get_market_session",
    "get_open_positions",
    "get_paper_trading_performance",
    "get_system_health",
)

TIER_MEDIUM_TOOL_NAMES: tuple[str, ...] = (
    "calculate_position_size",
    "get_account_info",
    "get_asset_analysis",
    "get_atr",
    "get_chart",
    "get_economic_calendar",
    "get_fundamental_brief",
    "get_market_quote",
    "get_market_regime",
    "get_market_session",
    "get_multi_timeframe_summary",
    "get_news_digest",
    "get_open_positions",
    "get_paper_trading_performance",
    "get_price_history",
    "get_risk_state",
    "get_smc_zones",
    "get_technical_indicators",
)

TIER_DEEP_TOOL_NAMES: tuple[str, ...] = (
    "calculate_confluence",
    "calculate_position_size",
    "detect_candlestick_patterns",
    "get_account_info",
    "get_asset_analysis",
    "get_atr",
    "get_central_bank_expectations",
    "get_chart",
    "get_cot_report",
    "get_daily_range_context",
    "get_debate_statistics",
    "get_dxy",
    "get_economic_calendar",
    "get_fibonacci_levels",
    "get_fundamental_brief",
    "get_market_chronicle",
    "get_market_quote",
    "get_market_regime",
    "get_market_session",
    "get_multi_timeframe_summary",
    "get_news_digest",
    "get_open_positions",
    "get_order_blocks",
    "get_paper_trading_performance",
    "get_pnl_summary",
    "get_price_history",
    "get_price_momentum",
    "get_risk_state",
    "get_smc_zones",
    "get_spread_snapshot",
    "get_structure_breaks",
    "get_swing_points",
    "get_system_health",
    "get_technical_indicators",
    "get_timesfm_forecast",
    "propose_action",
)

_INTERACTIVE_MAP = {t.get("name"): t for t in OPERATOR_INTERACTIVE_TOOLS if t.get("name")}


def _build_tier_tools(names: tuple[str, ...]) -> list[dict[str, Any]]:
    matched = [_INTERACTIVE_MAP[n] for n in names if n in _INTERACTIVE_MAP]
    return sorted(matched, key=lambda t: str(t.get("name", "")))


TIER_LITE_TOOLS: list[dict[str, Any]] = _build_tier_tools(TIER_LITE_TOOL_NAMES)
TIER_MEDIUM_TOOLS: list[dict[str, Any]] = _build_tier_tools(TIER_MEDIUM_TOOL_NAMES)
TIER_DEEP_TOOLS: list[dict[str, Any]] = _build_tier_tools(TIER_DEEP_TOOL_NAMES)


class ExecutionTiersMixin(_ChatAgentMixinBase):
    """Mixin providing multi-tier model execution strategies."""

    async def _run_tier_deep_research(
        self, system_prompt, history, message, tool_executor=None, status_callback=None
    ) -> dict:
        """
        SOTA 2026 Coordinator-Worker Dynamic Deep Research:
        1. Decomposes query dynamically into domain-specific specialist subagents via DynamicSubagentPool.
        2. Spawns specialist workers concurrently with isolated context sandboxes & execution timeouts.
        3. Synthesizes all specialist intelligence reports into an authoritative Executive Brief.
        """
        from monika.application.analysis.subagent_spawner import DynamicSubagentPool

        system_prompt = self._inject_macro_playbooks(system_prompt, user_query=message)

        all_mapped = {t.get("name"): t for t in OPERATOR_INTERACTIVE_TOOLS if t.get("name")}
        all_tools = sorted(all_mapped.values(), key=lambda t: str(t.get("name", "")))

        async def _notify_progress(text: str):
            if status_callback:
                try:
                    cb = status_callback(text)
                    if asyncio.iscoroutine(cb):
                        await cb
                except Exception:
                    pass

        pool = DynamicSubagentPool(
            settings=self.settings,
            max_concurrency=4,
            default_timeout=75.0,
        )

        prompt_for_subagents = (
            f"{system_prompt[0]}\n\n{system_prompt[1]}"
            if isinstance(system_prompt, tuple) and system_prompt[1]
            else (system_prompt[0] if isinstance(system_prompt, tuple) else system_prompt)
        )

        specs = pool.decompose_research_query(
            query=message,
            base_system_prompt=prompt_for_subagents,
            available_tools=all_tools,
            tool_executor=tool_executor,
        )

        roles_list = ", ".join(s.role for s in specs)
        logger.info(f"[DeepResearch] DynamicSubagentPool spawned {len(specs)} specialists: {roles_list}")
        await _notify_progress(f" Menjalankan riset paralel ({len(specs)} spesialis: {roles_list})...")

        # Asymmetric Tiering: Fast subagent execution workers + Flagship Chief Synthesizer
        worker_client = self._client_medium or self._client_lite or self._client_research

        results = await pool.run_parallel(
            specs=specs,
            client=worker_client,
            progress_callback=_notify_progress,
        )

        # Build dynamic synthesis prompt from all subagent outputs
        logger.info("[DeepResearch] All specialists completed. Synthesizing Executive Intelligence Brief...")
        await _notify_progress(" Mensintesis Ringkasan Eksekutif Terkonsolidasi...")

        sections = []
        total_in = 0
        total_out = 0
        total_tools = 0

        for idx, res in enumerate(results, 1):
            total_in += res.input_tokens
            total_out += res.output_tokens
            total_tools += res.tool_calls_made
            content = res.content if res.success else f"[{res.role} mengalami kendala: {res.error}]"
            sections.append(f"=== {idx}. {res.role.upper()} REPORT ===\n{content}")

        synthesis_input = (
            f"User Query: {message}\n\n"
            + "\n\n".join(sections)
            + "\n\nProduce the final consolidated executive intelligence brief."
        )

        synthesizer_sys = (
            f"{prompt_for_subagents}\n\n"
            "[SYNTHESIZER ROLE]: You are the Chief Market Strategist & Synthesizer Agent. "
            f"{len(results)} specialist research subagents have investigated the user's query in parallel across "
            "multiple market domains. "
            "Synthesize their findings into an authoritative, cohesive Executive Intelligence Brief matching the user's language (Indonesian or English).\n\n"
            "CRITICAL DIRECTIVE ON DIRECT ANSWER:\n"
            "In your opening paragraph, deliver a direct, concise, and definitive answer to the user's specific question "
            "(especially exact figures, probabilities, pre vs post news deltas, or direct yes/no conclusions). "
            "Never omit or bury the direct answer beneath generic institutional commentary.\n\n"
            "Structure your report clearly answering the specific questions asked (mirroring the depth of institutional macro notes):\n"
            "1. Current Data Snapshot & Market Expectation Trajectory\n"
            "2. Certainty Analysis & Degree of Market Pricing (Priced-In Score vs Risk Asymmetry)\n"
            "3. Historical Precedents: Central Bank Surprises & Market Failure Mechanisms\n"
            "4. Contextual Comparison: Current Setup vs Historical Analogues\n"
            "5. Press Conference Predictions & Forward Guidance Signals (Hawkish vs Dovish, Dot Plot / SEP Projections)\n"
            "6. Multi-Asset Macro Transmission Summary (DXY, Yields, Gold, Major FX, Crypto/Risk Assets)\n\n"
            "IMPORTANT TRADING PLAN DIRECTIVE: If the user did NOT explicitly ask for a technical trading plan (SL/TP/entry levels), "
            "do NOT invent or force a technical trading plan with entry/SL/TP levels in this chat response. Focus 100% on the rigorous analytical "
            "and probabilistic reasoning requested. The system will automatically persist your synthesized intelligence in the background to "
            "user_market_intel so that downstream Stage 1 (Macro) and Stage 2 (Per-Asset Trading Plan) cycles in LangGraph can utilize it."
        )

        synth_client = self._client_research or self._client_deep
        synth_tools = [PROPOSE_ACTION, SAVE_MARKET_INTELLIGENCE]
        synth_response = await synth_client.run_chat_loop(
            system_prompt=synthesizer_sys,
            conversation_history=history,
            new_user_message=synthesis_input,
            tools=synth_tools,
            tool_executor=tool_executor,
        )

        total_in += synth_response.get("input_tokens", 0)
        total_out += synth_response.get("output_tokens", 0)
        total_tools += synth_response.get("tool_calls_made", 0)

        # Background persistence: automatically persist synthesized research into user_market_intel
        # so Stage 1 (Macro) and Stage 2 (Per-Asset Trading Plan) in LangGraph absorb it seamlessly
        # without polluting the chat turn with unprompted action confirmation buttons.
        if self._is_macro_event_query(message):
            try:
                from datetime import datetime, timedelta, timezone

                from monika.infrastructure.database.models import UserMarketIntel

                clean_title = message.strip().replace("\n", " ")[:120]
                reply_raw = synth_response.get("reply", "")
                summary_text = reply_raw[:600] if len(reply_raw) > 600 else reply_raw
                async with get_session() as intel_session:
                    intel_record = UserMarketIntel(
                        telegram_user_id=str(self.user_id),
                        intel_type="deep_research",
                        title=f"Macro Event Analysis: {clean_title}",
                        summary=summary_text,
                        full_content=reply_raw,
                        affected_symbols="ALL",
                        directive="scenario_watch",
                        target_cycle="next_cycle_only",
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                    )
                    intel_session.add(intel_record)
                    await intel_session.commit()
                    logger.info(
                        f"[DeepResearch] Background auto-saved research to user_market_intel #{intel_record.id}"
                    )
            except Exception as persist_err:
                logger.debug(f"[DeepResearch] Background persistence error: {persist_err}")

        reply_final = synth_response.get("reply", "Riset selesai namun sintesis tidak menghasilkan output.")
        if self._is_macro_event_query(message):
            reply_final += (
                "\n\n[INFO] _Hasil riset telah disimpan otomatis ke memori sistem (user_market_intel) "
                "sebagai bahan pertimbangan siklus Analisis Makro (Stage 1) dan Pembuatan Trading Plan (Stage 2) berikutnya._"
            )

        return {
            "reply": reply_final,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "tool_calls_made": total_tools,
            "proposed_action": synth_response.get("proposed_action"),
        }

    async def _run_tier_lite(
        self, system_prompt, history, message, tool_executor=None, image_bytes: Optional[bytes] = None
    ) -> dict:
        """Lite tier path untuk query sederhana menggunakan lean prompt yang di-anchor (~1024 token)."""
        from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

        selected_tools = TIER_LITE_TOOLS
        lean_sys = self._build_lean_system_prompt()
        lean_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
            lean_sys, task_role="chat_telegram", force=True
        )
        payload = self._format_user_message_payload(message, image_bytes)
        response = await self._client_lite.run_chat_loop(
            system_prompt=lean_sys,
            conversation_history=history,
            new_user_message=payload,
            tools=selected_tools,
            tool_executor=tool_executor,
        )
        return response

    async def _run_tier_medium(
        self, system_prompt, history, message, tool_executor=None, image_bytes: Optional[bytes] = None
    ) -> dict:
        """Medium tier path untuk query menengah dengan tools analitis statis terurut."""
        selected_tools = TIER_MEDIUM_TOOLS
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        payload = self._format_user_message_payload(user_msg, image_bytes)
        response = await self._client_medium.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=payload,
            tools=selected_tools,
            tool_executor=tool_executor,
        )
        return response

    async def _run_tier_deep(
        self, system_prompt, history, message, tool_executor=None, image_bytes: Optional[bytes] = None
    ) -> dict:
        """Deep tier path untuk analisis mendalam dengan tools institusional statis terurut."""
        system_prompt = self._inject_macro_playbooks(system_prompt, user_query=message)
        selected_tools = TIER_DEEP_TOOLS
        sys_prompt, user_msg = self._prepare_cache_invariant_prompt(system_prompt, message)
        payload = self._format_user_message_payload(user_msg, image_bytes)
        response = await self._client_deep.run_chat_loop(
            system_prompt=sys_prompt,
            conversation_history=history,
            new_user_message=payload,
            tools=selected_tools,
            tool_executor=tool_executor,
        )
        return response

    async def _run_tier_lite_stream(
        self, system_prompt, history, message, tool_executor=None
    ) -> AsyncGenerator[str, None]:
        """Run tier_lite; yields streaming tokens."""
        client = self._client_lite
        gen_stream = getattr(client, "generate_stream", None)
        if callable(getattr(client, "generate_content_stream", None)):
            async for chunk in client.generate_content_stream(
                system_prompt=system_prompt, user_message=message, conversation_history=history
            ):
                yield chunk if isinstance(chunk, str) else getattr(chunk, "text", str(chunk))
        elif callable(gen_stream):
            stream_call: Any = gen_stream
            async for chunk in stream_call(message, system=system_prompt):
                yield chunk
        else:
            resp = await self._run_tier_lite(system_prompt, history, message, tool_executor=tool_executor)
            reply = resp.get("reply", "")
            if reply:
                yield reply

    async def _run_tier_deep_stream(
        self, system_prompt, history, message, tool_executor=None
    ) -> AsyncGenerator[str, None]:
        """Run tier_deep; yields streaming tokens."""
        client = self._client_deep
        gen_stream = getattr(client, "generate_stream", None)
        if callable(getattr(client, "generate_content_stream", None)):
            async for chunk in client.generate_content_stream(
                system_prompt=system_prompt, user_message=message, conversation_history=history
            ):
                yield chunk if isinstance(chunk, str) else getattr(chunk, "text", str(chunk))
        elif callable(gen_stream):
            stream_call: Any = gen_stream
            async for chunk in stream_call(message, system=system_prompt):
                yield chunk
        else:
            resp = await self._run_tier_deep(system_prompt, history, message, tool_executor=tool_executor)
            reply = resp.get("reply", "")
            if reply:
                yield reply

    async def _run_with_gemini(self, system_prompt, history, message, tool_executor=None, stream: bool = False):
        """Run tier_lite; yields tokens if stream=True."""
        if stream:
            return self._run_tier_lite_stream(system_prompt, history, message, tool_executor=tool_executor)
        return await self._run_tier_lite(system_prompt, history, message, tool_executor=tool_executor)

    async def _run_with_claude(self, system_prompt, history, message, tool_executor=None, stream: bool = False):
        """Run tier_deep; yields tokens if stream=True."""
        if stream:
            return self._run_tier_deep_stream(system_prompt, history, message, tool_executor=tool_executor)
        return await self._run_tier_deep(system_prompt, history, message, tool_executor=tool_executor)
