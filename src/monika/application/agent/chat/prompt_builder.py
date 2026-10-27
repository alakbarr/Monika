# ==============================================================================
# File: application/agent/chat/prompt_builder.py
# ==============================================================================

"""
Dynamic system prompt assembly, query complexity classification, and playbook injection.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from datetime import datetime, timezone
from sqlalchemy import select
from monika.infrastructure.database.models import Position, RiskState
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.agent.chat.base import _ChatAgentMixinBase, logger


class PromptBuilderMixin(_ChatAgentMixinBase):
    """Mixin handling system prompt construction, playbooks, and intent heuristics."""

    def _detect_model_preference(self, msg: str) -> str:
        """Returns: 'tier_lite', 'tier_medium', 'tier_deep', 'deep_research', atau 'auto'"""
        import re

        msg_lower = msg.lower().strip()

        # Manual override via prefix
        if re.match(r"^/(research|pro)\b", msg_lower):
            return "deep_research"
        if re.match(r"^/(fast|quick|lite|tier1)\b", msg_lower):
            return "tier_lite"
        if re.match(r"^/(medium|mid|balanced|tier2)\b", msg_lower):
            return "tier_medium"
        if re.match(r"^/(analyze|analisis|deep|reasoning|complex|tier3)\b", msg_lower):
            return "tier_deep"

        return "auto"

    def _is_macro_event_query(self, text: str) -> bool:
        """Deteksi apakah kueri memerlukan analisis mendalam probabilitas event makro/bank sentral."""
        if not text or not isinstance(text, str):
            return False
        import re

        msg_lower = text.lower().strip()

        # Compound self-sufficient triggers that inherently signify macro event / probability analysis
        compound_triggers = (
            r"\b(market\s*surprise|kejutan\s*pasar|keputusan\s*(?:suku\s*)?bunga|rate\s*decision|"
            r"probabilitas\s*(?:hike|cut|hold)|probabilitasnya\s*sebelum|odds\s*(?:hike|cut|hold))\b"
        )
        if re.search(compound_triggers, msg_lower):
            return True

        # Macro event entities and central bank concepts
        macro_event_patterns = (
            r"\b(fedwatch|cme\s*fedwatch|cme|fomc|(?:the\s+)?fed\b|"
            r"fed\s*(?:hike|cut|hold|pause|pivot|decision)|"
            r"suku\s*bunga|interest\s*rate|"
            r"(?:rate\s*)?(?:hike|cut|hold)|decision|keputusan\s*(?:bunga|rate|suku\s*bunga)|"
            r"bank\s*sentral|central\s*bank|press\s*conference|presser|konferensi\s*pers|"
            r"dot\s*plot|sep\b|kebijakan\s*moneter|monetary\s*policy|"
            r"greenspan|alan\s*greenspan|bernanke|ben\s*bernanke|yellen|janet\s*yellen|"
            r"warsh|kevin\s*warsh|powell|jerome\s*powell|lagarde|ueda|bailey|ecb|boj|boe|"
            r"taper|tapering|no-taper|quantitative\s*easing|qe\b|"
            r"kejutan\s*pasar|market\s*surprise|searah\s*dengan\s*harapan|mengecoh\s*pasar)\b"
        )
        # Macro analytical / probability intent
        macro_intent_patterns = (
            r"\b(peluang|kemungkinan|probabilitas|probability|odds|prospek|proyeksi|"
            r"prediksi|outlook|preview|forecast|skenario|scenario|analisis|analisa|analysis|"
            r"komprehensif|comprehensive|hawkish|dovish|hike|cut|hold|history|historis|"
            r"precedent|preseden|dampak|impact|reaksi|reaction|"
            r"surprise|kejutan|keputusan|decision)\b"
        )
        return bool(re.search(macro_event_patterns, msg_lower) and re.search(macro_intent_patterns, msg_lower))

    _MACRO_PLAYBOOK_HEADERS = (
        ("event_probability_playbook", "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK"),
        ("central_banks_framework", "## AUTHORITATIVE CENTRAL BANKS FRAMEWORK"),
        ("market_dynamics_framework", "## AUTHORITATIVE MARKET DYNAMICS FRAMEWORK"),
    )
    _PROMPT_SKILL_EXCLUSIONS = frozenset(
        {
            "event-probability-playbook",
            "central-banks-framework",
            "market-dynamics-framework",
            "telegram-persona",
            "intent-resolution",
            "prompt-intent-disambiguation",
        }
    )
    _INJECTION_MARKER = "<!-- MONIKA_DYNAMIC_SKILLS_INJECTED -->"

    def _inject_macro_playbooks(
        self, system_prompt: Union[str, tuple[str, str]], user_query: str = ""
    ) -> Union[str, tuple[str, str]]:
        """Inject macro playbooks and matched skills without mutating a static prefix."""
        from monika.application.skills.loader import load_skill

        playbook_sections: list[str] = []
        loaded_skills: set[str] = set()

        # 1. Macro playbooks for macro-relevant queries.
        if not user_query or self._is_macro_event_query(user_query):
            for raw_name, header in self._MACRO_PLAYBOOK_HEADERS:
                loaded_skills.add(raw_name.replace("_", "-"))
                try:
                    content = load_skill(raw_name)
                    if content:
                        playbook_sections.append(f"{header}\n{content}")
                except Exception as e:
                    logger.warning(f"[ChatAgent] Failed to load {raw_name}: {e}")

        # 2. Dynamic skill matching for domain-specific requests (up to 3 skills).
        if user_query:
            try:
                from monika.application.skills.unified_runtime import get_skills_runtime

                runtime = get_skills_runtime()
                matched = runtime.match_skills_for_prompt(user_query)
                activated = 0
                for s_name in matched:
                    if activated >= 3:
                        break
                    canonical = str(s_name).strip().lower().replace("_", "-")
                    if not canonical or canonical in loaded_skills or canonical in self._PROMPT_SKILL_EXCLUSIONS:
                        continue
                    loaded_skills.add(canonical)
                    try:
                        instr = runtime.load_skill_instructions(s_name)
                        if instr:
                            playbook_sections.append(f"## ACTIVATED SPECIALIZATION SKILL: {canonical.upper()}\n{instr}")
                            activated += 1
                    except Exception as s_err:
                        logger.debug(f"[ChatAgent] Could not load matched skill '{s_name}': {s_err}")
            except Exception as match_err:
                logger.debug(f"[ChatAgent] Dynamic skill matching failed: {match_err}")

        if not playbook_sections:
            return system_prompt

        injected_block = f"\n\n---\n\n{self._INJECTION_MARKER}\n\n" + "\n\n---\n\n".join(playbook_sections)

        def _already_injected(text: str) -> bool:
            return self._INJECTION_MARKER in text or "## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK" in text

        if isinstance(system_prompt, tuple):
            static_prompt, dynamic_snapshot = system_prompt
            if _already_injected(static_prompt) or _already_injected(dynamic_snapshot or ""):
                return system_prompt
            dynamic_tail = f"{dynamic_snapshot}{injected_block}" if dynamic_snapshot else injected_block
            return (static_prompt, dynamic_tail)

        if _already_injected(system_prompt):
            return system_prompt
        return f"{system_prompt}{injected_block}"

    async def _classify_query_complexity(self, msg: str) -> str:
        """Use heuristics to classify query complexity reliably."""
        if not msg or not isinstance(msg, str) or not msg.strip():
            return "simple"

        import re

        msg_lower = msg.lower().strip()

        # Ad-hoc Deep Research & Market Intelligence patterns (highest priority)
        RESEARCH_PATTERNS = r"\b(deep-research|deep\s*research|riset\s*mendalam|investigasi\s*pasar|konsensus|whisper|saturasi\s*posisi|skenario\s*hit/miss|pre-event|bedah\s*peristiwa|analisis\s*mendalam|bedah\s*makro)\b"
        if re.search(RESEARCH_PATTERNS, msg_lower):
            return "deep_research"

        # Macro Event & Central Bank Probability patterns (Deep Research)
        if self._is_macro_event_query(msg_lower):
            return "deep_research"

        # Action verbs always require complex / medium deep reasoning
        ACTION_VERBS = r"\b(close|tutup|modify|ubah|override|batalkan|cancel|adjust|geser)\b"
        if re.search(ACTION_VERBS, msg_lower):
            return "complex"

        # Super short greetings/thanks
        if len(msg) < 15 and any(
            w in msg_lower
            for w in ["halo", "hai", "hi", "hello", "tes", "ping", "makasih", "terima kasih", "thanks", "ok", "siap"]
        ):
            return "simple"

        # Exact match or starts with a simple command (even if > 200 chars)
        if re.match(
            r"^(status|posisi|positions|vix|balance|equity|pnl|drawdown|stats|performa|triggers?|history|riwayat|health|kesehatan|biaya|token)\b",
            msg_lower,
        ):
            return "simple"

        if len(msg) > 300:
            return "complex"

        # Jev System One Intent & Model Tier Routing
        try:
            from monika.core.primitives.jev_primitives import build_telegram_intent_questions

            jev_client = getattr(self, "_client_intent", None) or self._client_lite
            if hasattr(jev_client, "classify_json"):
                jev_res = await jev_client.classify_json(
                    prompt="",
                    state={"user_message": msg[:500]},
                    jev_questions=build_telegram_intent_questions(),
                    timeout=2.0,
                )
                if jev_res and isinstance(jev_res, dict):
                    tier = jev_res.get("model_tier")
                    choice_val = tier.get("choice") if isinstance(tier, dict) else tier
                    tier_str = str(choice_val or "").lower()
                    if tier_str in ("none", "light"):
                        return "simple"
                    elif tier_str == "medium":
                        return "medium"
                    elif tier_str == "heavy":
                        return "complex"
        except Exception as jev_intent_err:
            logger.debug(f"[ChatAgent] Jev intent routing fallback to heuristics: {jev_intent_err}")

        if len(msg) > 150:
            return "medium"

        # Common simple patterns
        if re.search(
            r"\b(berapa|cek|tampilkan|lihat|ada apa)\b.*\b(saldo|vix|pnl|profit|loss|posisi|positions?|paper|win rate|triggers?|kesehatan|health|biaya|tokens?|histori|riwayat|chart|grafik)\b",
            msg_lower,
        ):
            return "simple"

        # Common complex patterns
        if re.search(
            r"\b(kenapa|mengapa|analisa|evaluasi|analisis|review|bagaimana|setup|entry|prediksi|prospek)\b", msg_lower
        ):
            return "complex"

        # Common medium patterns
        if re.search(r"\b(berita|news|ringkasan|summary|apa|kapan|jadwal)\b", msg_lower):
            return "medium"

        return "medium"

    def _prepare_cache_invariant_prompt(self, system_prompt: Any, message: str) -> tuple[str, str]:
        """Separate static prefix system prompt from volatile session data, injecting volatile snapshot to user message."""
        if isinstance(system_prompt, tuple):
            static_sys, dynamic_sys = system_prompt
            user_msg = (
                f"<volatile_overlay>\n{dynamic_sys}\n</volatile_overlay>\n\n{message}" if dynamic_sys else message
            )
            return static_sys, user_msg
        return system_prompt, message

    def _format_user_message_payload(self, user_msg: str, image_bytes: Optional[bytes] = None) -> Any:
        if not image_bytes:
            return user_msg
        import base64

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return [
            {"type": "text", "text": user_msg},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        ]

    async def _build_system_prompt(self, session: AsyncSession) -> str | tuple[str, str]:
        """Construct complete system prompt with immutable static prefix for optimal KV-cache hits."""
        from monika.core.platform import get_platform_info
        from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

        platform_info = get_platform_info()
        anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
        lines = [
            anchor,
            "",
            "You are Monika, an autonomous MT5 Trading Agent assistant.",
            "",
            "## Your Role",
            "You assist the system operator in understanding market conditions, analyzing positions, and answering queries.",
            "You CAN access real-time data using the available tools.",
            "You CAN inspect the full database schema via inspect_database_schema and query table records via read_database_records (Admin only).",
            "You CAN propose trading actions and database mutations (insert, update, delete) via the PROPOSE_ACTION tool.",
            "You CANNOT directly execute orders or database changes — all actions require explicit operator confirmation.",
            "",
            "## Tool Usage Policy",
            "Perform all tool interactions, calculations, and internal analytical reasoning in English.",
            "Always ground analytical answers in fresh data from tools rather than assumptions.",
            "",
            "## Host Environment & Shell Execution Policy",
            f"- Active Host Operating System: {platform_info['os_name']}",
            f"- Active Terminal Shell: {platform_info['shell_name']}",
            "- When executing terminal commands or scripts, ALWAYS format commands strictly compatible with the active shell.",
            '- On Windows: NEVER use Linux-specific shell pipeline idioms (e.g. `cat file | head` or `grep`). Use PowerShell cmdlets (`Get-Content`, `Select-Object`) or python one-liners (`python -c "..."`) which are 100% portable.',
            "- For inspecting or reading files, ALWAYS use dedicated tools (`read_file`, `mcp_filesystem_workspace_fs_read_file`, or `retrieve_spilled_context`) rather than spawning a terminal command.",
            "",
            "## STRICT COMMUNICATION & FORMATTING RULES (MANDATORY)",
            "- FLEXIBLE BILINGUAL MATCHING: ALWAYS mirror the user's language dynamically. If the user communicates in Bahasa Indonesia, respond in articulate, natural, polite, and professional Bahasa Indonesia. If the user communicates in English, respond in articulate, natural, clear, and professional English.",
            "- NATURAL HUMAN TONE: Use conversational, human-like language that is pleasant and easy to read. Avoid stiff robotic phrasing, meaningless jargon, or raw unformatted data dumps.",
            "- ABSOLUTE ZERO EMOTICON POLICY: NEVER use any Unicode emojis (symbols, pictographs, charts, rockets, flags, etc.) or text-based ASCII emoticons (like :), :D, ;), ^^, -_-, <3, etc.). Keep 100% of all generated text pristine, clean, and elegant in all languages.",
            "- STRUCTURED VISUAL HIERARCHY: Organize answers with clear sections, airy paragraph spacing, crisp bullet points ('•'), bold emphasis for key numbers/assets, and clean data tables where comparison is helpful.",
            "- For standard conversational turns, keep response length concise (<= 3000 characters). For deep research, comprehensive macro event probability analyses, or complex strategic investigations, provide exhaustive institutional-grade briefs without arbitrary character limits, utilizing multi-chunk message delivery.",
            "",
            "## Anti-Hallucination Rules (MANDATORY)",
            "- When asked about past trade rationale/decisions, you MUST call get_asset_analysis or get_fundamental_brief to fetch the ORIGINAL recorded rationale before answering. Never reconstruct from generic memory.",
            "- When asked about PnL, paper trading performance, trade history, active triggers, open positions, account balance, win rate, or statistical edge, you MUST call the appropriate tool (get_paper_trading_performance, get_trade_history, get_open_positions, get_account_info, get_active_triggers, get_edge_tracker_status) before answering. Never guess numbers or claim that tools are unavailable.",
            "- If a tool returns an error or empty data, state transparently to the user that data is unavailable. Never guess numbers.",
            "",
            "## Workspace & Second-Brain Integration (Obsidian, Excel, Notion)",
            "- You have direct MCP tool access to user files, notes, and spreadsheets across local drives.",
            "- To inspect or read Obsidian notes, markdown documents, or trading plans: use 'mcp_filesystem_workspace_fs_read_file' or search notes via 'mcp_filesystem_workspace_fs_search_files'.",
            "- To create or update notes and trading journals in Obsidian: use 'mcp_filesystem_workspace_fs_write_file'. Format entries with YAML frontmatter compatible with Obsidian Dataview.",
            "- To inspect, read, or append to Excel (.xlsx) and CSV spreadsheets: use 'mcp_excel_tabular_excel_read_sheet', 'mcp_excel_tabular_excel_append_row', 'mcp_excel_tabular_excel_list_sheets'.",
            "",
            "Language Reminder: Reason internally in English, present final response to operator in the exact language used by the user (Bahasa Indonesia or English).",
            "",
            "## 6-Pillar SOP for Asset Inquiries (e.g. 'gold gimana?', 'eu bisa buy gak?')",
            "When the user asks short or ambiguous questions about an instrument, you MUST formulate a structured 6-pillar institutional briefing:",
            "1. Current Price & Market Session: Live quote (bid/ask/spread) and active session (Jakarta WIB / London / NY).",
            "2. Multi-Timeframe Trend Alignment: H4 & H1 trend alignment and market regime (trending/ranging).",
            "3. Key SMC & SnR Structure: Immediate Order Blocks, FVG zones, swing highs/lows, and liquidity pools.",
            "4. Macro & News Window Risk: Upcoming high-impact economic releases affecting the asset and risk window.",
            "5. Calibrated Bias: Clear directional bias (Bullish/Bearish/Neutral) with confluence rationale and confidence.",
            "6. Actionable Invalidation Level: Exact price level that invalidates the proposed setup or bias.",
            "",
            "## Available Slash Commands",
            "If the user inquires about direct operations or fast commands, guide them to:",
            "- /trade [symbol] [buy/sell] [lots] — Propose formal order execution with risk fortress validation.",
            "- /chart [symbol] [timeframe] — Render and deliver SMC overlaid candlestick chart to chat.",
            "- /positions — Show active open positions, entry, SL, TP, and current floating PnL.",
            "- /macro [currency] — Show economic calendar, central bank expectations, and surprise scores.",
            "- /status — System health check, MT5 connection status, and daily risk metrics.",
            "- /research [topic] — Run institutional multi-source web and academic market research.",
            "- /help — Show comprehensive help and operational guide.",
        ]

        # Append trading persona skill (immutable communication style)
        try:
            from monika.application.skills.loader import load_skill

            persona = load_skill("telegram_persona")
            lines.append("\n---\n")
            lines.append(persona)
        except Exception:
            pass

        # Append prompt-intent-disambiguation skill (intent decomposition & anti-slop guidelines)
        try:
            from monika.application.skills.loader import load_skill

            intent_res = load_skill("prompt-intent-disambiguation") or load_skill("intent-resolution")
            if intent_res:
                lines.append("\n---\n")
                lines.append(intent_res)
        except Exception:
            pass

        # Append compact index of available specialization skills
        try:
            from monika.application.skills.unified_runtime import get_skills_runtime

            runtime = get_skills_runtime()
            compact_index = runtime.get_compact_prompt_index(max_skills=15)
            if compact_index:
                lines.append("\n---\n")
                lines.append(compact_index)
        except Exception:
            pass

        if self.settings.get("trading", {}).get("caveman_mode", False):
            lines.append("\n---\n")
            lines.append("# CAVEMAN MODE — SCOPE-LIMITED COMPRESSION")
            lines.append(
                "Compress ONLY non-analytical conversational prose (pleasantries, filler, conversational hedging). "
                "NEVER compress: numerical price levels, SL/TP bounds, trading rationale, data quotations from tools, or analytical arguments. "
                "If uncertain whether a sentence is analytical, treat it as analytical and write it in full — compressing analytical content is far more costly than writing conversational prose in full."
            )

        # DYNAMIC TAIL: Current portfolio & time snapshot placed strictly in separate block to preserve static prefix cache
        dynamic_lines = []
        now_dt = datetime.now(timezone.utc)
        quantized_minute = (now_dt.minute // 10) * 10
        now_quantized = now_dt.replace(minute=quantized_minute, second=0, microsecond=0)
        now = now_quantized.strftime("%Y-%m-%d %H:%M UTC")
        dynamic_lines.append(f"## Current Session Snapshot ({now})")

        try:
            open_pos = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
            if open_pos:
                dynamic_lines.append("## Current Open Live Positions (MT5)")
                for p in open_pos:
                    dynamic_lines.append(
                        f"- {p.symbol} {p.direction.upper()} {p.volume}lots "
                        f"@ {p.entry_price} | SL={p.sl} | TP={p.tp} | ticket={p.mt5_ticket}"
                    )
            else:
                dynamic_lines.append("## Current Open Live Positions (MT5): None.")

            # Paper Trading status snapshot
            from monika.core.analytics.paper_tracker import PaperTracker
            from monika.infrastructure.database.models import PaperTradeRecord, TradeTrigger, UserPreference

            tracker = PaperTracker(self.settings)
            p_stats = await tracker.get_statistics(session)
            open_paper = (
                (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open")))
                .scalars()
                .all()
            )

            dynamic_lines.append("\n## Paper Trading & Portfolio Snapshot")
            mode_label = (
                "PAPER / DRY-RUN" if self.settings.get("paper_trading", {}).get("enabled", True) else "LIVE MT5"
            )
            dynamic_lines.append(f"- Mode: {mode_label}")
            dynamic_lines.append(
                f"- Total Paper Trades: {p_stats.get('total_trades', 0)} | Win Rate: {p_stats.get('win_rate_pct', 0):.1f}% | Total PnL: {p_stats.get('total_pnl_pct', 0):+.2f}%"
            )
            if open_paper:
                dynamic_lines.append(f"- Active Open Paper Trades ({len(open_paper)}):")
                for op in open_paper:
                    dynamic_lines.append(
                        f"  * #{op.id} {op.symbol} {op.direction.upper()} @ {op.entry_price} | SL={op.stop_loss} | TP={op.take_profit}"
                    )
            else:
                dynamic_lines.append("- Active Open Paper Trades: None")

            # Pending triggers
            pending_triggers = (
                (await session.execute(select(TradeTrigger).where(TradeTrigger.status == "pending"))).scalars().all()
            )
            dynamic_lines.append(f"- Pending Market Triggers: {len(pending_triggers)} active")

            # Risk state
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            risk = (
                await session.execute(
                    select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if risk:
                status = "PAUSED" if risk.trading_paused else "ACTIVE"
                dynamic_lines.append(
                    f"\n## Risk State: {status} | Daily PnL: ${risk.daily_pnl:.2f} | Drawdown: ${risk.current_drawdown:.2f}"
                )

            # Active Market Chronicle (ongoing macro/geopolitical events)
            try:
                from monika.application.analysis.memory.chronicle_writer import ChronicleWriter

                c_writer = ChronicleWriter(self.settings)
                c_ctx = await c_writer.get_chronicle_context(session, days_back=30, limit=4)
                if c_ctx:
                    dynamic_lines.append(f"\n{c_ctx}")
            except Exception as e:
                logger.debug(f"Chronicle context injection in Telegram Chat failed: {e}")

            # Active Operator Preferences from UserPreference table
            try:
                prefs = (
                    (await session.execute(select(UserPreference).where(UserPreference.is_active == True)))
                    .scalars()
                    .all()
                )
                if prefs:
                    dynamic_lines.append("\n## Active Operator Preferences & Constraints (MANDATORY)")
                    for pr in prefs:
                        pref_key = getattr(pr, "key", getattr(pr, "preference_key", "preference"))
                        dynamic_lines.append(f"- [{pr.category.upper()}] {pref_key}: {pr.value_json}")
            except Exception as e:
                logger.debug(f"UserPreference injection failed: {e}")

        except Exception as e:
            logger.debug(f"System prompt dynamic tail enrichment failed: {e}")

        static_prompt = "\n".join(lines)
        dynamic_snapshot = "\n".join(dynamic_lines) if dynamic_lines else ""
        return (static_prompt, dynamic_snapshot) if dynamic_snapshot else static_prompt

    def _build_lean_system_prompt(self) -> str:
        """Construct a lightweight, highly responsive prompt for quick data and status queries (~150 tokens)."""
        return (
            "You are Monika, an autonomous MT5 Trading Agent assistant.\n"
            "Your role in this turn is to provide fast, direct, and accurate answers to operator queries.\n"
            "Use the provided tools to retrieve real-time facts whenever needed. Keep answers concise, factual, and formatted with clean Markdown.\n"
            "Answer in the user's language (Indonesian or English)."
        )
