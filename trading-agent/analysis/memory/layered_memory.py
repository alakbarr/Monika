"""
4-Layer Memory System.

Layer 0 - IDENTITY (Permanent TRADING_SOUL.md, <=300 tok):
  Immutable core philosophy, risk tolerance, and invariant trading rules
Layer 1 - CURATED CORE (always in prompt, <=800 tok):
  Active market regime, top lessons, portfolio heat, model biases
Layer 2 - EPISODIC RETRIEVAL & FTS5 PRECEDENTS (on-demand):
  Past reflections, debate verdicts, performance patterns, SQLite FTS5 session search
Layer 3 - VOLATILE CONTEXT (per-invocation, never persisted):
  Current data bundle, conversation history
"""

import logging
import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from utils.llm.prompt_compressor import estimate_tokens, truncate_to_budget
from analysis.memory.session_search import SessionSearchEngine

logger = logging.getLogger("TradingAgent.LayeredMemory")

MAX_CORE_TOKENS = 800  # Hard token budget cap


def compute_ebbinghaus_retention(
    timestamp: Optional[datetime],
    stability_days: float = 14.0,
    now_dt: Optional[datetime] = None,
) -> float:
    """
    Subsystem 6: Computes memory retention using the Ebbinghaus forgetting curve:
    R = exp(-delta_t / S)
    where delta_t is elapsed time in days and S is memory stability.
    """
    if timestamp is None:
        return 0.50
    now = now_dt or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    elapsed_days = max(0.0, (now - timestamp).total_seconds() / 86400.0)
    retention = math.exp(-elapsed_days / max(1.0, stability_days))
    return float(retention)


def _wrap_market_memory(content: str, max_tokens: int = 400) -> str:
    """Isolate dynamic/retrieved market memory in XML tags to prevent prompt injection."""
    if not content or not content.strip():
        return ""
    truncated = truncate_to_budget(content.strip(), max(50, max_tokens - 10))
    return f"<market-memory-context>\n{truncated}\n</market-memory-context>"


class LayeredMemoryManager:
    """Manages 4-layer memory hierarchy for optimal context efficiency."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._soul_cache: Optional[str] = None
        self.session_search = SessionSearchEngine()

    async def get_frozen_snapshot(self, session: Optional[AsyncSession] = None):
        """Retrieve frozen memory snapshot for prompt cache preservation."""
        from analysis.memory.frozen_snapshot import get_frozen_snapshot_manager
        return await get_frozen_snapshot_manager(self.settings).get_snapshot(session=session)

    def get_identity(self) -> str:
        """Layer 0: Permanent trading soul identity (100% cacheable)."""
        if self._soul_cache is None:
            soul_path = Path(__file__).resolve().parent.parent.parent / "config" / "TRADING_SOUL.md"
            if soul_path.exists():
                try:
                    self._soul_cache = soul_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Failed to read TRADING_SOUL.md: {e}")
                    self._soul_cache = ""
            else:
                self._soul_cache = ""
        return self._soul_cache

    async def get_stable_core_memory(self, session: Optional[AsyncSession] = None) -> str:
        """Layer 1A: Stable curated memory (<=600 tok), invariant within cycle. 100% System Prompt cache-safe."""
        parts = []

        # 1. Market regime
        regime = await self._detect_regime(session)
        parts.append(f"REGIME: {regime}")

        # 2. Top 3 lessons from recent reflections
        lessons = await self._get_top_lessons(session, n=3)
        if lessons:
            parts.append("LESSONS:\n" + "\n".join(f"- {l}" for l in lessons))

        # 3. Model performance biases
        biases = await self._get_model_biases()
        if biases:
            parts.append(f"PERF_NOTES: {biases}")

        # 4. Active Structural Macro Reality & Ongoing Chronicles
        if session:
            try:
                from analysis.memory.chronicle_writer import ChronicleWriter
                c_writer = ChronicleWriter(self.settings)
                c_bullets = await c_writer.get_condensed_chronicle_bullets(session, limit=3)
                if c_bullets:
                    parts.append(f"ACTIVE_MACRO_REALITY:\n{c_bullets}")
            except Exception as e:
                logger.debug(f"Failed to load active macro reality for stable core memory: {e}")

        composed = "\n".join(parts)
        return truncate_to_budget(composed, 600)

    async def get_volatile_portfolio_memory(self, session: Optional[AsyncSession] = None) -> str:
        """Layer 1B: Volatile portfolio heat & equity state (<=200 tok). Injected into User Message tail to protect Prefix Cache."""
        heat = await self._get_portfolio_heat(session)
        return f"PORTFOLIO_HEAT: {heat}"

    async def get_core_memory(self, session: Optional[AsyncSession] = None) -> str:
        """Layer 1: Combined curated memory (<=800 tok). Maintained for backward compatibility."""
        stable = await self.get_stable_core_memory(session)
        volatile = await self.get_volatile_portfolio_memory(session)
        composed = f"{stable}\n{volatile}".strip()
        return truncate_to_budget(composed, MAX_CORE_TOKENS)

    async def get_symbol_memory(self, session: Optional[AsyncSession], symbol: str, regime: Optional[str] = None) -> str:
        """Per-symbol episodic recall for Stage 2 (Layer 2 DB + FTS5 precedents)."""
        parts = []

        # Auto-detect market regime if session is available and regime was not explicitly provided
        if regime is None and session is not None:
            try:
                regime = await self._detect_regime(session)
            except Exception:
                pass

        # 1. Historical precedents from PostgreSQL (Phase 2: Hybrid RRF)
        try:
            precedents = []
            if hasattr(self.session_search, "get_symbol_precedents_hybrid"):
                precedents = await self.session_search.get_symbol_precedents_hybrid(
                    symbol, current_regime=regime, setup_text=f"{symbol} {regime or ''}", limit=2, session=session
                )
            if not precedents and hasattr(self.session_search, "get_symbol_precedents"):
                import inspect
                fallback_res = self.session_search.get_symbol_precedents(symbol, limit=2, session=session, regime=regime)
                fallback_p = await fallback_res if inspect.isawaitable(fallback_res) else fallback_res
                if isinstance(fallback_p, list):
                    precedents = fallback_p

            if precedents:
                parts.append("PRECEDENTS:")
                for p in precedents:
                    pnl_str = f" PnL:{p['pnl']:+.2f}%" if p.get('pnl') is not None else ""
                    stage_prefix = "[WHATIF] " if p.get('stage') == 'whatif' else ""
                    parts.append(f"- {p['timestamp'][:10]} {stage_prefix}{p['decision']} (conf={p['confidence']:.2f}{pnl_str}): {p['content'][:85]}")
        except Exception:
            pass

        if not session:
            composed = "\n".join(parts) if parts else ""
            return _wrap_market_memory(composed, 400)

        try:
            from database.models import DecisionReflection, PaperTradeRecord

            # 2. Recent reflections for this symbol
            reflections = (await session.execute(
                select(DecisionReflection)
                .where(DecisionReflection.symbol == symbol)
                .where(DecisionReflection.status == 'resolved')
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(3)
            )).scalars().all()

            if reflections:
                for r in reflections:
                    tag = getattr(r, 'lesson_tags', None) or getattr(r, 'lesson_tag', 'Alpha')
                    text = getattr(r, 'specific_lesson', None) or getattr(r, 'alpha_lesson', None) or getattr(r, 'reflection_text', '') or ''
                    adj = getattr(r, 'next_trade_adjustment', None)
                    if adj and adj not in text:
                        text = f"{text} (Adj: {adj})" if text else f"Adj: {adj}"
                    if text:
                        parts.append(f"- {tag}: {text[:120]}")

            # 3. Win rate for this symbol
            trades = (await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.symbol == symbol)
                .where(PaperTradeRecord.status == 'closed')
            )).scalars().all()

            if trades:
                wins = sum(1 for t in trades if (t.pnl_pct or 0.0) > 0)
                wr = wins / len(trades) * 100
                parts.append(f"- Win rate: {wr:.0f}% ({len(trades)} trades)")

            # 4. Systematic Negative Constraints based on past failure modes (PR-13)
            try:
                from analysis.memory.negative_constraint_generator import NegativeConstraintGenerator
                neg_constraints = await NegativeConstraintGenerator.generate_negative_constraints_from_losses(
                    session=session,
                    symbol=symbol,
                    current_regime=regime,
                    max_constraints=3,
                )
                if neg_constraints:
                    parts.append("NEGATIVE_CONSTRAINTS:")
                    parts.extend(neg_constraints)
            except Exception as e:
                logger.debug(f"[{symbol}] Failed to generate negative constraints: {e}")

            # 5. Pattern similarity consensus (if available in cache)
            try:
                from database.models import PatternScreeningCache
                p_entry = (await session.execute(
                    select(PatternScreeningCache)
                    .where(PatternScreeningCache.symbol == symbol)
                    .order_by(desc(PatternScreeningCache.screened_at))
                    .limit(1)
                )).scalar_one_or_none()
                if p_entry and p_entry.confidence in ('high', 'medium'):
                    parts.append(f"- Pattern Consensus: {p_entry.overall_bias.upper()} ({p_entry.confidence.upper()} confidence)")
            except Exception:
                pass

            composed = "\n".join(parts) if parts else ""
            return _wrap_market_memory(composed, 400)
        except Exception as e:
            logger.debug(f"[{symbol}] Symbol memory fetch non-fatal error: {e}")
            composed = "\n".join(parts) if parts else ""
            return _wrap_market_memory(composed, 400)

    async def get_macro_regime_memory(self, session: Optional[AsyncSession] = None) -> str:
        """Dynamic macro regime state wrapped in isolated memory tags."""
        regime = await self._detect_regime(session)
        return _wrap_market_memory(f"MACRO_REGIME: {regime}", 150)

    async def get_playbook_memory(self, symbol: str) -> str:
        """
        Retrieve crystallized tactical playbook for symbol wrapped in isolated memory tags.
        Enforces lifecycle gating: only ACTIVE playbooks are injected into prompt context.
        STALE and ARCHIVED playbooks are strictly excluded.
        """
        try:
            from analysis.memory.progressive_loader import ProgressiveMemoryLoader
            from analysis.memory.playbook_lifecycle import PlaybookLifecycleFSM, PlaybookState

            clean_sym = symbol.strip().upper()
            fsm = PlaybookLifecycleFSM()

            # Check if there is a tracked status for this symbol's playbook
            candidates = [
                clean_sym,
                clean_sym.lower(),
                f"{clean_sym.lower()}_playbook",
                f"{clean_sym}_playbook",
                f"{clean_sym.lower()}_breakout",
                f"{clean_sym}_breakout",
            ]
            status = None
            for cand in candidates:
                st = fsm.get_status(cand)
                if st is not None:
                    status = st
                    break

            # Strictly exclude STALE, ARCHIVED, or un-promoted CANDIDATE playbooks if tracked
            if status is not None and status != PlaybookState.ACTIVE:
                logger.info(
                    f"[{symbol}] Skipping playbook memory injection: status is '{status.value}' (only ACTIVE allowed)"
                )
                return ""

            loader = ProgressiveMemoryLoader()
            playbook = loader.get_level1_playbook(symbol)
            if playbook:
                return _wrap_market_memory(playbook, 600)
        except Exception as e:
            logger.debug(f"Failed to fetch playbook memory for {symbol}: {e}")
        return ""

    async def _detect_regime(self, session: Optional[AsyncSession]) -> str:
        """Detect comprehensive market state from VIX, DXY trend, Macro Brief, and active geopolitics."""
        if not session:
            return "USD_NEUTRAL | VIX_NORMAL"
        try:
            from database.models import DXYData, VIXData, FundamentalBrief

            # 1. DXY trend
            dxy_rows = (await session.execute(
                select(DXYData).order_by(desc(DXYData.date)).limit(5)
            )).scalars().all()
            if len(dxy_rows) >= 3:
                dxy_trend = "USD_STRENGTHENING" if dxy_rows[0].close > dxy_rows[-1].close else "USD_WEAKENING"
            else:
                dxy_trend = "USD_NEUTRAL"

            # 2. VIX Volatility Level
            vix_row = (await session.execute(
                select(VIXData).order_by(desc(VIXData.date)).limit(1)
            )).scalar_one_or_none()
            if vix_row and vix_row.close is not None:
                v_val = float(vix_row.close)
                v_zone = "CRISIS" if v_val >= 30 else ("DEFENSIVE" if v_val >= 25 else ("CAUTION" if v_val >= 20 else "NORMAL"))
                vix_str = f"VIX_{v_zone}({v_val:.1f})"
            else:
                vix_str = "VIX_NORMAL"

            # 3. Macro Regime & Sentiment from latest FundamentalBrief
            brief = (await session.execute(
                select(FundamentalBrief).order_by(desc(FundamentalBrief.generated_at)).limit(1)
            )).scalar_one_or_none()
            macro_regime = (getattr(brief, "macro_regime", "") or "BALANCED").upper() if brief else "BALANCED"
            risk_sent = (getattr(brief, "risk_sentiment", "") or "MIXED").upper() if brief else "MIXED"

            # 4. Active Geopolitical/Structural tags from Chronicle
            geo_tag = ""
            try:
                from analysis.memory.chronicle_writer import ChronicleWriter
                geo_tag = await ChronicleWriter(self.settings).get_macro_state_summary(session)
            except Exception:
                pass

            regime_parts = [f"{macro_regime}", f"RISK_{risk_sent}", f"{dxy_trend}", f"{vix_str}"]
            if geo_tag:
                regime_parts.append(geo_tag)

            return " | ".join(regime_parts)
        except Exception as e:
            logger.debug(f"Regime detection error (non-fatal): {e}")
            return "USD_NEUTRAL"

    async def _get_top_lessons(self, session: Optional[AsyncSession], n: int = 3) -> List[str]:
        """Top N most relevant lessons ranked by Ebbinghaus retention decay and empirical stability."""
        if not session:
            return ["No revenge trade within 4h of SL", "Priced-in score >=8 requires WAIT"]
        try:
            from database.models import DecisionReflection, CandidateLesson
            seen_texts = set()
            scored_lessons: List[tuple[float, str]] = []

            now_utc = datetime.now(timezone.utc)

            # 1. Promoted lessons (high stability S = 60 days)
            promoted = (await session.execute(
                select(CandidateLesson)
                .where(CandidateLesson.status == 'promoted')
                .order_by(desc(CandidateLesson.promoted_at))
                .limit(n * 2)
            )).scalars().all()
            for pl in promoted:
                if pl.lesson_text and pl.lesson_text not in seen_texts:
                    ret = compute_ebbinghaus_retention(pl.promoted_at, stability_days=60.0, now_dt=now_utc)
                    if ret >= 0.10:  # Exclude decayed memories
                        prefix = f"[{pl.symbol}] " if pl.symbol and pl.symbol != "ALL" else ""
                        scored_lessons.append((ret * 1.5, f"{prefix}{pl.lesson_text[:90]}"))
                        seen_texts.add(pl.lesson_text)

            # 2. Recent reflections (standard stability S = 14 days)
            results = (await session.execute(
                select(DecisionReflection)
                .where(
                    or_(
                        DecisionReflection.alpha_lesson != None,
                        DecisionReflection.specific_lesson != None
                    )
                )
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(n * 3)
            )).scalars().all()
            for r in results:
                txt = getattr(r, 'specific_lesson', None) or getattr(r, 'alpha_lesson', None)
                adj = getattr(r, 'next_trade_adjustment', None)
                if txt and adj and adj not in txt:
                    txt = f"{txt} -> {adj}"
                if txt and txt not in seen_texts:
                    ret = compute_ebbinghaus_retention(r.resolved_at, stability_days=14.0, now_dt=now_utc)
                    if ret >= 0.10:
                        scored_lessons.append((ret, txt[:100]))
                        seen_texts.add(txt)

            scored_lessons.sort(key=lambda x: x[0], reverse=True)
            top = [item[1] for item in scored_lessons[:n]]
            return top if top else ["No revenge trade within 4h of SL", "Priced-in score >=8 requires WAIT"]
        except Exception:
            return ["No revenge trade within 4h of SL", "Priced-in score >=8 requires WAIT"]

    async def _get_portfolio_heat(self, session: Optional[AsyncSession]) -> str:
        """Current open positions summary (both live and paper)."""
        if not session:
            return "0 open positions"
        try:
            from database.models import PaperTradeRecord, Position
            live_positions = (await session.execute(
                select(Position).where(Position.status == 'open')
            )).scalars().all()
            paper_trades = (await session.execute(
                select(PaperTradeRecord).where(PaperTradeRecord.status == 'open')
            )).scalars().all()

            all_symbols = [p.symbol for p in live_positions if getattr(p, 'symbol', None)] + [t.symbol for t in paper_trades if getattr(t, 'symbol', None)]
            if not all_symbols:
                return "0 open positions"
            return f"{len(all_symbols)} open: {', '.join(all_symbols)}"
        except Exception:
            return "0 open positions"

    async def _get_model_biases(self) -> str:
        """Performance notes from benchmark/skill files."""
        try:
            from skills.loader import load_skill
            notes = load_skill("fundamental_performance_notes")
            for line in notes.split('\n'):
                if 'Accuracy' in line:
                    return line.strip()
        except Exception:
            pass
        return "Baseline active"
