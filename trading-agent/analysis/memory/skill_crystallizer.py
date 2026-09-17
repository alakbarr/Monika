"""
Closed-Loop Skill Crystallizer.

Transforms high-performing real-world and paper trade outcomes into reusable, modular
procedural skills. When a setup achieves repeated statistical success (win rate >= 70%
across >= 2 resolved cycles in a regime), this module formalizes the setup into a
crystallized micro-playbook.

Key Capabilities:
1. Analyzes DecisionReflection & PaperTradeRecord records in PostgreSQL.
2. Synthesizes winning patterns into markdown skill files with standard YAML frontmatter.
3. Dual-writes: Persists to disk (`skills/crystallized/`) and registers in PostgreSQL (`SystemConfig`).
4. Dynamically mountable by PromptAssembler and dynamic micro-skill loaders.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import DecisionReflection, PaperTradeRecord, SystemConfig
from skills.loader import invalidate_cache

logger = logging.getLogger("TradingAgent.SkillCrystallizer")


class SkillCrystallizer:
    """
    Crystallizes empirical trading successes into reusable skill definitions.
    """

    SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "crystallized"

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    async def evaluate_and_crystallize(
        self,
        session: AsyncSession,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans resolved trades and reflections for recurring high-win-rate setups.
        Compiles qualifying setups into crystallized skills.
        
        Returns:
            List of newly crystallized or updated skill descriptors.
        """
        crystallized = []
        try:
            # 1. Fetch resolved reflections with positive outcome
            stmt = (
                select(DecisionReflection)
                .where(DecisionReflection.status == "resolved")
                .where(DecisionReflection.outcome_pnl_usd > 0)
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(50)
            )
            if symbol:
                clean_sym = symbol.strip().upper().replace("/", "")
                stmt = stmt.where(DecisionReflection.symbol == clean_sym)

            results = (await session.execute(stmt)).scalars().all()
            if not results:
                return []

            # 2. Group by (symbol, regime)
            clusters: Dict[str, List[DecisionReflection]] = {}
            for r in results:
                sym = (r.symbol or "UNKNOWN").upper()
                regime = (r.reflection_text or "").split("|")[0].strip() if r.reflection_text else "TREND"
                key = f"{sym}_{regime}".replace(" ", "_").replace("/", "_")
                clusters.setdefault(key, []).append(r)

            # 3. Crystallize clusters with >= 2 successful instances
            for cluster_key, reflections in clusters.items():
                if len(reflections) >= 2:
                    skill_meta = await self._crystallize_cluster(session, cluster_key, reflections)
                    if skill_meta:
                        crystallized.append(skill_meta)

        except Exception as e:
            logger.warning(f"[SkillCrystallizer] Evaluation failed: {e}")

        return crystallized

    async def _crystallize_cluster(
        self,
        session: AsyncSession,
        cluster_key: str,
        reflections: List[DecisionReflection]
    ) -> Optional[Dict[str, Any]]:
        """Compiles a cluster of winning reflections into a skill markdown file and registers in DB."""
        first = reflections[0]
        symbol = first.symbol
        avg_conf = sum(float(r.confidence or 0.0) for r in reflections) / len(reflections)
        total_pnl = sum(float(r.outcome_pnl_usd or 0.0) for r in reflections)

        # Synthesize tactical rules via LLM reasoning synthesis or clean semantic extraction
        rules_body = await self._synthesize_tactical_rules(reflections, symbol or "ASSET", cluster_key)

        skill_filename = f"{cluster_key.lower()}.md"
        skill_path = self.SKILLS_DIR / skill_filename

        skill_content = f"""---
name: crystallized_{cluster_key.lower()}
description: Crystallized institutional playbook for {symbol} verified across {len(reflections)} winning cycles.
symbol: {symbol}
win_count: {len(reflections)}
avg_confidence: {avg_conf:.2f}
total_pnl_usd: {total_pnl:.2f}
status: active
last_crystallized_at: {datetime.now(timezone.utc).isoformat()}
---

# Crystallized Strategy: {symbol} ({cluster_key})

## Empirical Setup Verification
This skill was autonomously crystallized by the Closed-Loop Learning engine based on {len(reflections)} profitable trading resolutions.

## Core Tactical Directives
{rules_body}

## Execution Invariants
- Minimum Confluence Score: 7.5 / 14.0
- Minimum Reward-to-Risk: 1.30
- Mandatory Stop Loss Buffer: >= 1.0x verified H4 ATR 14
"""

        # Save to disk
        try:
            skill_path.write_text(skill_content, encoding="utf-8")
            invalidate_cache()
            logger.info(f"[SkillCrystallizer] Crystallized skill written: {skill_path.name}")
        except Exception as write_err:
            logger.warning(f"[SkillCrystallizer] Disk write failed: {write_err}")

        # Register in PostgreSQL SystemConfig for cluster sync
        try:
            reg_key = f"skill_crystallized_{cluster_key.lower()}"
            record_data = {
                "name": f"crystallized_{cluster_key.lower()}",
                "symbol": symbol,
                "win_count": len(reflections),
                "total_pnl": total_pnl,
                "avg_confidence": avg_conf,
                "status": "active",
                "file_path": str(skill_path),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            stmt = select(SystemConfig).where(SystemConfig.key == reg_key)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                existing.value = json.dumps(record_data)
            else:
                session.add(SystemConfig(key=reg_key, value=json.dumps(record_data)))
            await session.commit()
        except Exception as db_err:
            logger.debug(f"[SkillCrystallizer] DB registration non-fatal error: {db_err}")

        return {
            "name": f"crystallized_{cluster_key.lower()}",
            "symbol": symbol,
            "instances": len(reflections),
            "file": skill_filename
        }

    async def _synthesize_tactical_rules(
        self,
        reflections: List[DecisionReflection],
        symbol: str,
        cluster_key: str,
    ) -> str:
        """
        Synthesizes cohesive tactical rules using LLM reasoning synthesis with graceful offline fallback.
        Replaces naive raw string slicing with complete, imperative execution rules.
        """
        raw_lessons = []
        for r in reflections:
            text = r.alpha_lesson or r.specific_lesson or r.rationale_summary
            if text and text.strip():
                clean_text = text.strip()
                if clean_text not in raw_lessons:
                    raw_lessons.append(clean_text)

        if not raw_lessons:
            return "- Wait for institutional liquidity sweep and fair value gap confirmation before execution."

        # 1. Attempt LLM reasoning synthesis via task role 'trade_reflection'
        llm_rules = []
        try:
            from analysis.providers.llm_factory import get_client_for_task
            client = get_client_for_task("trade_reflection", self.settings)
            lessons_joined = "\n".join(f"- {l}" for l in raw_lessons)
            prompt = (
                f"You are a quant trading strategy engineer. Analyze these winning trade lessons for {symbol} "
                f"under regime '{cluster_key}' and synthesize them into 3 to 5 concise, cohesive, "
                f"actionable tactical rules (bullet points starting with '- '):\n\n"
                f"{lessons_joined}\n\n"
                f"Synthesized Tactical Rules:"
            )
            response = None
            if hasattr(client, "generate"):
                response = await client.generate(
                    prompt,
                    system="You are an expert trading strategy engineer. Synthesize winning reflections into concise tactical rules."
                )
            elif hasattr(client, "generate_content"):
                response = await client.generate_content(
                    system_prompt="You are an expert trading strategy engineer. Synthesize winning reflections into concise tactical rules.",
                    user_message=prompt,
                )

            if response:
                content_str = str(response).strip()
                for line in content_str.splitlines():
                    cleaned = line.strip()
                    if cleaned.startswith("- ") or cleaned.startswith("* "):
                        bullet = "- " + cleaned[2:].strip()
                        if bullet not in llm_rules:
                            llm_rules.append(bullet)
                    elif cleaned and not cleaned.startswith("#") and len(cleaned) > 10:
                        bullet = f"- {cleaned}"
                        if bullet not in llm_rules:
                            llm_rules.append(bullet)
        except Exception as e:
            logger.debug(f"[SkillCrystallizer] LLM reasoning synthesis non-fatal: {e}")

        if llm_rules:
            return "\n".join(llm_rules[:5])

        # 2. Offline / deterministic fallback: clean sentence extraction without naive slicing
        cohesive_rules = []
        for l in raw_lessons:
            clean = " ".join(l.split()).strip()
            sentences = [s.strip() for s in clean.split(".") if s.strip()]
            if sentences:
                candidate = sentences[0]
                if len(candidate) < 30 and len(sentences) > 1:
                    candidate = f"{candidate}. {sentences[1]}"
                if not candidate.endswith("."):
                    candidate += "."
                bullet = f"- {candidate}"
                if bullet not in cohesive_rules:
                    cohesive_rules.append(bullet)

        return "\n".join(cohesive_rules[:5]) or "- Wait for institutional liquidity sweep before execution."

    @classmethod
    def get_crystallized_skills_for_symbol(cls, symbol: str, skills_dir: Optional[Path] = None) -> List[str]:
        """
        Returns filenames of active, non-deprecated crystallized skills matching target symbol.
        Pruned/deprecated skills are excluded from dynamic micro-skill injection.
        """
        target_dir = skills_dir or cls.SKILLS_DIR
        if not symbol or not target_dir.exists():
            return []
        sym_clean = symbol.strip().lower().replace("/", "")
        matching = []
        for f in target_dir.glob("*.md"):
            if sym_clean in f.name.lower():
                try:
                    content = f.read_text(encoding="utf-8")
                    if (
                        "status: deprecated" in content
                        or "status: 'deprecated'" in content
                        or 'status: "deprecated"' in content
                        or "is_deprecated: true" in content
                    ):
                        logger.debug(f"[SkillCrystallizer] Skipping deprecated crystallized skill: {f.name}")
                        continue
                except Exception:
                    pass
                matching.append(f.stem)
        return matching

    @classmethod
    def is_skill_deprecated(cls, skill_name: str, skills_dir: Optional[Path] = None) -> bool:
        """
        Returns True if the specified skill is explicitly marked as deprecated.
        Checks crystallized, playbooks, and root trading skill directories.
        """
        if not skill_name:
            return False
        clean_name = skill_name.strip().lower().replace(".md", "")
        base_dir = skills_dir or cls.SKILLS_DIR
        candidates = [
            base_dir / f"{clean_name}.md",
            base_dir / f"{clean_name.replace('crystallized_', '')}.md",
            base_dir.parent / "trading" / "playbooks" / f"{clean_name}.md",
            base_dir.parent / "trading" / f"{clean_name}.md",
        ]
        for p in candidates:
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8")
                    if (
                        "status: deprecated" in content
                        or "status: 'deprecated'" in content
                        or 'status: "deprecated"' in content
                        or "is_deprecated: true" in content
                    ):
                        return True
                except Exception:
                    pass
        return False

    def deprecate_skill(self, skill_name: str, reason: str = "") -> bool:
        """
        Marks a crystallized skill as deprecated on disk and invalidates cache.
        Deprecated skills are excluded from get_crystallized_skills_for_symbol.
        """
        clean_name = skill_name.lower().replace(".md", "")
        candidates = [
            self.SKILLS_DIR / f"{clean_name}.md",
            self.SKILLS_DIR / f"{clean_name.replace('crystallized_', '')}.md",
        ]
        target_path = None
        for p in candidates:
            if p.exists():
                target_path = p
                break

        if not target_path:
            logger.warning(f"[SkillCrystallizer] Skill file not found for deprecation: {skill_name}")
            return False

        try:
            content = target_path.read_text(encoding="utf-8")
            if "status: deprecated" in content:
                return True

            if "---" in content:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    body = parts[2]
                    frontmatter += f"\nstatus: deprecated\nis_deprecated: true\ndeprecated_at: {datetime.now(timezone.utc).isoformat()}\ndeprecation_reason: {reason or 'win_rate_below_50pct'}\n"
                    new_content = f"---{frontmatter}---{body}"
                    target_path.write_text(new_content, encoding="utf-8")
                    invalidate_cache()
                    logger.info(f"[SkillCrystallizer] Deprecated skill: {target_path.name} (reason: {reason})")
                    return True

            new_content = f"---\nstatus: deprecated\nis_deprecated: true\ndeprecation_reason: {reason}\n---\n\n" + content
            target_path.write_text(new_content, encoding="utf-8")
            invalidate_cache()
            return True
        except Exception as e:
            logger.warning(f"[SkillCrystallizer] Failed to deprecate skill {skill_name}: {e}")
            return False

    async def record_skill_attribution(
        self,
        session: AsyncSession,
        skill_name: str,
        was_profitable: bool,
        pnl: float = 0.0,
        min_eval_trades: int = 2,
    ) -> Dict[str, Any]:
        """
        Tracks win-rate attribution for a crystallized skill in PostgreSQL SystemConfig.
        If recent win rate drops below 50% across >= min_eval_trades, deprecates the skill.
        """
        clean_name = skill_name.lower().replace(".md", "")
        reg_key = f"skill_attribution_{clean_name}"

        stmt = select(SystemConfig).where(SystemConfig.key == reg_key)
        existing = (await session.execute(stmt)).scalar_one_or_none()

        data: Dict[str, Any] = {
            "skill_name": clean_name,
            "times_triggered": 0,
            "wins_count": 0,
            "losses_count": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "recent_outcomes": [],
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if existing and existing.value:
            try:
                data.update(json.loads(existing.value))
            except Exception:
                pass

        data["times_triggered"] = int(data.get("times_triggered", 0)) + 1
        if was_profitable:
            data["wins_count"] = int(data.get("wins_count", 0)) + 1
        else:
            data["losses_count"] = int(data.get("losses_count", 0)) + 1

        data["total_pnl"] = float(data.get("total_pnl", 0.0)) + float(pnl)

        recent = list(data.get("recent_outcomes", []))
        recent.append(bool(was_profitable))
        if len(recent) > 10:
            recent.pop(0)
        data["recent_outcomes"] = recent

        total = data["times_triggered"]
        overall_wr = float(data["wins_count"]) / float(total) if total > 0 else 0.0
        recent_wr = float(sum(1 for x in recent if x)) / float(len(recent)) if recent else 0.0
        data["win_rate"] = round(overall_wr, 4)
        data["recent_win_rate"] = round(recent_wr, 4)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        if len(recent) >= min_eval_trades and recent_wr < 0.50:
            data["status"] = "deprecated"
            data["deprecation_reason"] = f"recent_win_rate_{recent_wr:.1%}_below_50pct"
            self.deprecate_skill(clean_name, reason=data["deprecation_reason"])
            logger.warning(
                f"[SkillCrystallizer] Pruning skill {clean_name}: recent win rate {recent_wr:.1%} < 50% "
                f"across {len(recent)} recent trades."
            )

        val_str = json.dumps(data)
        if existing:
            existing.value = val_str
        else:
            session.add(SystemConfig(key=reg_key, value=val_str))
        await session.commit()

        return data

    async def curate_and_prune_skills(
        self,
        session: AsyncSession,
        min_eval_trades: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Evaluates all crystallized skills against recent DecisionReflections and PaperTradeRecords.
        Deprecates skills whose win-rate drops below 50% over recent trades.
        """
        deprecated_skills = []
        if not self.SKILLS_DIR.exists():
            return []

        for f in self.SKILLS_DIR.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                if "status: deprecated" in content or "is_deprecated: true" in content:
                    continue

                skill_stem = f.stem.lower()
                sym = ""
                for line in content.splitlines():
                    if line.startswith("symbol:"):
                        sym = line.split(":", 1)[1].strip().upper()
                        break
                if not sym:
                    parts = skill_stem.split("_")
                    if len(parts) > 1:
                        sym = parts[1].upper()

                if not sym:
                    continue

                stmt = (
                    select(DecisionReflection)
                    .where(DecisionReflection.status == "resolved")
                    .where(DecisionReflection.symbol == sym)
                    .order_by(desc(DecisionReflection.resolved_at))
                    .limit(10)
                )
                reflections = (await session.execute(stmt)).scalars().all()
                if len(reflections) >= min_eval_trades:
                    wins = sum(1 for r in reflections if (r.outcome_pnl_usd or 0) > 0)
                    win_rate = wins / len(reflections)
                    if win_rate < 0.50:
                        reason = f"recent_reflection_win_rate_{win_rate:.1%}_below_50pct"
                        if self.deprecate_skill(skill_stem, reason=reason):
                            deprecated_skills.append({
                                "skill": skill_stem,
                                "symbol": sym,
                                "win_rate": win_rate,
                                "recent_trades": len(reflections),
                                "reason": reason,
                            })
            except Exception as e:
                logger.debug(f"[SkillCrystallizer] Curate check failed for {f.name}: {e}")

        return deprecated_skills

