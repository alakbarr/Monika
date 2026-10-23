from pathlib import Path

from monika.core.paths import get_skills_dir

# ==============================================================================
# File: analysis/memory/skill_curator.py
# ==============================================================================

"""
Autonomous Background Skill Curator (MEDIUM-2).
Manages playbook lifecycle in the background during idle periods:
1. Stale Flagging: Marks playbooks inactive/untriggered for >30 days as stale.
2. Archiving: Moves playbooks inactive for >90 days to archive/.
3. Deduplication: Detects setup condition similarity (>85%) and consolidates playbooks.
"""

import asyncio
import difflib
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock

logger = logging.getLogger("TradingAgent.Memory.SkillCurator")


class SkillCurator:
    """Autonomous idle playbook curator managing Active -> Stale -> Archived lifecycle."""

    def __init__(self, settings: Optional[dict] = None, playbooks_dir: Optional[str] = None):
        self.settings = settings or {}
        if playbooks_dir:
            self.playbooks_dir = playbooks_dir
        else:
            self.playbooks_dir = str(get_skills_dir() / "trading" / "playbooks")
        self.archive_dir = os.path.join(self.playbooks_dir, "archive")
        os.makedirs(self.playbooks_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)

    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """Calculate normalized similarity ratio between two playbook condition texts."""
        if not text1 or not text2:
            return 0.0
        # Normalize whitespace and lowercase
        norm1 = " ".join(text1.lower().split())
        norm2 = " ".join(text2.lower().split())
        return difflib.SequenceMatcher(None, norm1, norm2).ratio()

    async def curate_db_rules(self, session: AsyncSession) -> dict:
        """Curate playbook_rule_attributions stored in the database."""
        from monika.infrastructure.database.models import PlaybookRuleAttribution

        now = clock.now()
        stale_threshold = now - timedelta(days=30)
        archive_threshold = now - timedelta(days=90)

        # 1. Stale Flagging: Active rules with last_triggered_at > 30 days ago or promoted > 30 days ago without trigger
        stale_stmt = (
            update(PlaybookRuleAttribution)
            .where(PlaybookRuleAttribution.status == "active")
            .where(
                (PlaybookRuleAttribution.last_triggered_at < stale_threshold)
                | (
                    (PlaybookRuleAttribution.last_triggered_at.is_(None))
                    & (PlaybookRuleAttribution.promoted_at < stale_threshold)
                )
            )
            .values(status="stale")
        )
        stale_res = await session.execute(stale_stmt)
        stale_count = int(getattr(stale_res, "rowcount", 0) or 0)

        # 2. Archiving: Stale rules that have been inactive for > 90 days
        archive_stmt = (
            update(PlaybookRuleAttribution)
            .where(PlaybookRuleAttribution.status.in_(["stale", "active"]))
            .where(
                (PlaybookRuleAttribution.last_triggered_at < archive_threshold)
                | (
                    (PlaybookRuleAttribution.last_triggered_at.is_(None))
                    & (PlaybookRuleAttribution.promoted_at < archive_threshold)
                )
            )
            .values(status="archived", deprecated_at=now, deprecation_reason="Inactive for >90 days")
        )
        archive_res = await session.execute(archive_stmt)
        archive_count = int(getattr(archive_res, "rowcount", 0) or 0)

        # 3. Deduplication: Active/stale rules with >85% condition similarity
        rules_stmt = (
            select(PlaybookRuleAttribution)
            .where(PlaybookRuleAttribution.status.in_(["active", "stale"]))
            .order_by(PlaybookRuleAttribution.times_triggered.desc())
        )
        active_rules = (await session.execute(rules_stmt)).scalars().all()

        dedup_count = 0
        seen_indices = set()
        for i in range(len(active_rules)):
            if i in seen_indices:
                continue
            r1 = active_rules[i]
            for j in range(i + 1, len(active_rules)):
                if j in seen_indices:
                    continue
                r2 = active_rules[j]
                if r1.symbol == r2.symbol:
                    sim = self.calculate_similarity(r1.rule_text, r2.rule_text)
                    if sim >= 0.85:
                        # Consolidate r2 into r1
                        r1.times_triggered += r2.times_triggered
                        r1.wins_count += r2.wins_count
                        r1.losses_count += r2.losses_count
                        r1.total_pnl += r2.total_pnl
                        r2.status = "archived"
                        r2.deprecated_at = now
                        r2.deprecation_reason = f"Deduplicated into rule {r1.rule_hash[:8]} (similarity={sim:.2f})"
                        seen_indices.add(j)
                        dedup_count += 1

        await session.commit()
        logger.info(
            f"[SkillCurator] DB curation complete: {stale_count} stale, "
            f"{archive_count} archived, {dedup_count} deduplicated."
        )
        return {
            "stale_count": stale_count,
            "archive_count": archive_count,
            "dedup_count": dedup_count,
        }

    @staticmethod
    def extract_playbook_spec(content: str, filename: str = "") -> Tuple[str, str, str]:
        """
        Extract (symbol, playbook_name, rule_text) from playbook content.
        Isolates the actual trading logic and setup trigger conditions
        from markdown template scaffolding and metadata boilerplate.
        """
        import re

        # 1. Symbol extraction
        symbol = ""
        sym_match = re.search(r"^symbol:\s*([A-Za-z0-9_]+)", content, re.MULTILINE)
        if sym_match:
            symbol = sym_match.group(1).upper()
        elif filename:
            prefix = filename.split("_")[0].upper()
            if prefix in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "XTIUSD", "XBRUSD", "BTCUSD", "AUDUSD"):
                symbol = prefix

        # 2. Playbook name / identifier
        name = ""
        name_match = re.search(r"^name:\s*([^\n]+)", content, re.MULTILINE)
        if name_match:
            name = name_match.group(1).strip()

        # 3. Rule / Condition text extraction
        trig_match = re.search(
            r"##\s*Trigger Conditions[^\n]*\n(.*?)(?=\n##|\Z)",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if trig_match:
            rule_text = trig_match.group(1).strip()
        else:
            lines = [
                line.strip()
                for line in content.splitlines()
                if line.strip().startswith(("- Long Trigger", "- Short Trigger", "Condition:", "- Trigger", "Trigger:"))
            ]
            if lines:
                rule_text = " ".join(lines)
            else:
                rule_text = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL).strip()

        if not rule_text:
            rule_text = content

        return symbol, name, rule_text

    def curate_files(self) -> dict:
        """Curate playbook markdown files in playbooks_dir."""
        now = clock.now()
        stale_threshold = now - timedelta(days=30)
        archive_threshold = now - timedelta(days=90)

        stale_files = []
        archived_files = []
        dedup_files = []

        if not os.path.exists(self.playbooks_dir):
            return {"stale": 0, "archived": 0, "deduplicated": 0}

        entries = []
        for fname in os.listdir(self.playbooks_dir):
            if not fname.endswith(".md") or fname.startswith("."):
                continue
            if ".." in fname or "/" in fname or "\\" in fname:
                logger.warning(f"[SkillCurator] Skipping suspicious filename: '{fname}'")
                continue
            fpath = os.path.join(self.playbooks_dir, fname)
            if not os.path.abspath(fpath).startswith(os.path.abspath(self.playbooks_dir)):
                logger.warning(f"[SkillCurator] Path traversal attempt detected: '{fpath}'")
                continue
            if os.path.isdir(fpath):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            symbol, pname, rule_text = self.extract_playbook_spec(content, fname)
            entries.append(
                {
                    "name": fname,
                    "path": fpath,
                    "mtime": mtime,
                    "content": content,
                    "symbol": symbol,
                    "pname": pname,
                    "rule_text": rule_text,
                }
            )

        # Check stale and archiving
        for item in entries:
            # Check for archive (>90 days)
            if item["mtime"] < archive_threshold:
                target_path = os.path.join(self.archive_dir, os.path.basename(item["name"]))
                if os.path.abspath(target_path).startswith(os.path.abspath(self.archive_dir)):
                    shutil.move(item["path"], target_path)
                    archived_files.append(item["name"])
            elif item["mtime"] < stale_threshold:
                orig_mtime = item["mtime"]
                content = item["content"]
                if "status: stale" not in content and "# [STATUS: STALE]" not in content:
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            fm = parts[1]
                            updated_fm = f"{fm.rstrip()}\nstatus: stale\n"
                            updated = f"---{updated_fm}---{parts[2]}"
                        else:
                            updated = f"{content}\n\n# [STATUS: STALE]"
                    else:
                        updated = f"{content}\n\n# [STATUS: STALE]"
                    with open(item["path"], "w", encoding="utf-8") as f:
                        f.write(updated)
                    os.utime(item["path"], (orig_mtime.timestamp(), orig_mtime.timestamp()))
                stale_files.append(item["name"])

        # Check deduplication (>85% similarity on rule text for matching symbol)
        remaining = [e for e in entries if e["name"] not in archived_files]
        seen = set()
        for i in range(len(remaining)):
            if i in seen:
                continue
            e1 = remaining[i]
            for j in range(i + 1, len(remaining)):
                if j in seen:
                    continue
                e2 = remaining[j]

                # Deduplication invariant: Only compare rules belonging to the same symbol
                if e1["symbol"] and e2["symbol"] and e1["symbol"] != e2["symbol"]:
                    continue

                # If both files have formal distinct playbook specifications with different names,
                # they represent calibrated distinct strategies and must not be collapsed
                if e1["pname"] and e2["pname"] and e1["pname"] != e2["pname"]:
                    continue

                sim = self.calculate_similarity(e1["rule_text"], e2["rule_text"])
                if sim >= 0.85:
                    # Move duplicate e2 to archive
                    target_path = os.path.join(self.archive_dir, f"dedup_{e2['name']}")
                    if os.path.exists(e2["path"]):
                        shutil.move(e2["path"], target_path)
                    seen.add(j)
                    dedup_files.append(e2["name"])

        logger.info(
            f"[SkillCurator] File curation complete: {len(stale_files)} stale, "
            f"{len(archived_files)} archived, {len(dedup_files)} deduplicated."
        )
        return {
            "stale": len(stale_files),
            "archived": len(archived_files),
            "deduplicated": len(dedup_files),
        }

    async def run_once(self, session: Optional[AsyncSession] = None) -> dict:
        """Perform a single complete curation cycle on both DB and files asynchronously."""
        file_res = await asyncio.to_thread(self.curate_files)
        db_res = {}
        if session:
            try:
                db_res = await self.curate_db_rules(session)
            except Exception as e:
                logger.warning(f"[SkillCurator] DB curation failed (non-fatal): {e}")
        return {"files": file_res, "database": db_res}

    async def run_background_loop(self, interval_seconds: int = 86400, session_factory: Optional[Any] = None):
        """Periodic background task (every 24 hours)."""
        logger.info(f"[SkillCurator] Background loop started (interval={interval_seconds}s)")
        while True:
            try:
                if session_factory:
                    async with session_factory() as session:
                        await self.run_once(session)
                else:
                    await self.run_once(None)
            except asyncio.CancelledError:
                logger.info("[SkillCurator] Background loop cancelled.")
                break
            except Exception as e:
                logger.error(f"[SkillCurator] Error in background loop: {e}", exc_info=True)
            await asyncio.sleep(interval_seconds)


# Canonical alias to disambiguate from monika.application.skills.curator.SkillCurator
PlaybookCurator = SkillCurator

__all__ = ["SkillCurator", "PlaybookCurator"]
