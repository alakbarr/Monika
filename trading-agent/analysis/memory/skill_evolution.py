"""
Autonomous Micro-Playbook Compiler.

Evaluates post-trade reflections and execution records from DecisionMemory:
1. Clusters trade reflections by (symbol, regime).
2. Calculates empirical win rate, profit factor, and winning streaks per cluster.
3. Automatically synthesizes and promotes condition-specific micro-playbooks when
   performance criteria are satisfied (>= 3 consecutive wins OR >= 65% win rate on >= 5 trades).
4. Emits structured playbooks to `skills/trading/playbooks/{symbol}_{regime}.md`.

Transforms passive reflections into active procedural memory.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
from collections import defaultdict
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock
from skills.loader import invalidate_cache
from analysis.memory.playbook_linter import PlaybookLinter
from analysis.memory.playbook_ledger import PlaybookLedger

logger = logging.getLogger("TradingAgent.SkillEvolution")

PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "trading" / "playbooks"


class MicroPlaybookCompiler:
    """Compiles empirical trade reflections into executable micro-playbooks."""

    _default_settings: dict = {}

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        MicroPlaybookCompiler._default_settings = self.settings

    @classmethod
    def ensure_playbooks_dir(cls) -> Path:
        """Ensures playbooks directory exists."""
        PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
        return PLAYBOOKS_DIR

    @classmethod
    async def evaluate_and_compile(
        cls,
        session: AsyncSession,
        settings: Optional[dict] = None,
        min_sample_size: int = 5,
        min_win_rate: float = 0.65,
        min_consecutive_wins: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Scans DecisionReflection and PaperTradeRecord to compile qualifying micro-playbooks.
        
        Returns:
            List of compiled playbook metadata dicts.
        """
        from database.models import DecisionReflection, PaperTradeRecord, ActivityLog

        cls.ensure_playbooks_dir()
        cfg = settings or getattr(cls, "_default_settings", {}) or {}
        symbols = cfg.get("trading", {}).get("asset_universe", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"])

        compiled_playbooks: List[Dict[str, Any]] = []

        for sym in symbols:
            # Query resolved reflections with specific lessons
            reflections = (await session.execute(
                select(DecisionReflection)
                .where(DecisionReflection.symbol == sym)
                .where(DecisionReflection.status == "resolved")
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(50)
            )).scalars().all()

            if not reflections:
                continue

            # Group reflections by market regime
            regime_clusters: Dict[str, List[DecisionReflection]] = defaultdict(list)
            for r in reflections:
                regime = (getattr(r, "market_regime", "") or "BALANCED").upper().strip()
                regime_clusters[regime].append(r)

            for regime, cluster in regime_clusters.items():
                if len(cluster) < 3:
                    continue

                # Analyze trade outcomes
                def _extract_pnl(item: Any) -> Optional[float]:
                    val = getattr(item, "outcome_pnl_usd", None)
                    if val is None:
                        val = getattr(item, "pnl", None)
                    return float(val) if val is not None else None

                trades = [r for r in cluster if _extract_pnl(r) is not None]
                if not trades:
                    continue

                wins = [t for t in trades if (_extract_pnl(t) or 0.0) > 0]
                win_rate = len(wins) / len(trades) if trades else 0.0

                # Check consecutive wins
                consecutive_wins = 0
                for t in trades:
                    if (_extract_pnl(t) or 0.0) > 0:
                        consecutive_wins += 1
                    else:
                        break

                # Qualification check
                qualifies_by_streak = consecutive_wins >= min_consecutive_wins
                qualifies_by_rate = len(trades) >= min_sample_size and win_rate >= min_win_rate

                if qualifies_by_streak or qualifies_by_rate:
                    playbook_name = f"{sym.lower()}_{regime.lower()}_playbook"
                    playbook_path = PLAYBOOKS_DIR / f"{playbook_name}.md"

                    # Synthesize playbook content
                    top_lessons = []
                    for t in cluster:
                        lesson_txt = getattr(t, "specific_lesson", None) or getattr(t, "alpha_lesson", None)
                        adj = getattr(t, "next_trade_adjustment", None)
                        if lesson_txt:
                            top_lessons.append(f"- **Lesson**: {lesson_txt}" + (f" -> *Adjustment*: {adj}" if adj else ""))

                    distinct_lessons = list(dict.fromkeys(top_lessons))[:5]
                    lessons_block = "\n".join(distinct_lessons) if distinct_lessons else "- Follow baseline SMC structure."

                    linter_regime = regime if regime in PlaybookLinter.VALID_REGIMES else "ANY"

                    content = f"""---
symbol: {sym}
regime: {linter_regime}
timeframe: H4
min_rr: 1.3
win_rate: {win_rate:.2f}
sample_size: {len(trades)}
---
# Micro-Playbook: {sym} in {regime} Regime
*Compiled autonomously by SkillEvolutionCompiler on {clock.now().strftime('%Y-%m-%d %H:%M UTC')}*

## Entry Conditions & Triggers
{lessons_block}
- Enter when higher timeframe trend aligns with multi-timeframe D1 and H4 structure.
- Wait for liquidity sweep and displacement confirmation before triggering market entry.

## Invalidation & Stop Loss Rules
- Invalidate thesis immediately on break of swing high/low prior to entry block.
- Enforce Stop Loss >= 1.0x verified ATR 14 buffer.
- Ensure Take Profit satisfies minimum 1.3:1 Reward-to-Risk within ADR bounds.
"""
                    linter = PlaybookLinter(min_rr_threshold=1.3)
                    lint_res = linter.lint(content)
                    if not lint_res.is_valid:
                        logger.warning(f"MicroPlaybookCompiler: Lint failed for '{playbook_name}': {lint_res.errors}")
                        continue

                    ledger = PlaybookLedger(str(PLAYBOOKS_DIR))
                    action = "update" if playbook_path.exists() else "create"
                    blob_hash = ledger.record_mutation(
                        playbook_name=playbook_name,
                        content=content,
                        action=action,
                        reason=f"Empirical compilation ({len(trades)} trades, {win_rate*100:.1f}% WR)",
                        author="micro_playbook_compiler",
                    )

                    playbook_path.write_text(content, encoding="utf-8")
                    invalidate_cache()
                    logger.info(f"MicroPlaybookCompiler: Compiled & promoted '{playbook_name}.md' (hash={blob_hash[:8]}, {win_rate*100:.0f}% WR).")

                    # Log to activity log
                    session.add(ActivityLog(
                        timestamp=clock.now(),
                        category="learning",
                        description=f"Autonomous Skill Compiler: Promoted micro-playbook '{playbook_name}.md' ({len(trades)} trades, {win_rate*100:.1f}% WR, hash={blob_hash[:8]})",
                        actor="skill_compiler"
                    ))
                    await session.commit()

                    compiled_playbooks.append({
                        "symbol": sym,
                        "regime": regime,
                        "filename": f"{playbook_name}.md",
                        "win_rate": win_rate,
                        "trades": len(trades),
                        "streak": consecutive_wins,
                        "blob_hash": blob_hash,
                    })

        return compiled_playbooks
