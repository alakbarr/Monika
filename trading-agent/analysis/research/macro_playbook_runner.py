# ==============================================================================
# File: analysis/research/macro_playbook_runner.py
# Monika Scheduled Macro Research Playbook Runner & Verdict Delta Engine
# ==============================================================================

"""
Scheduled Macro Research Playbook Runner.

Executes markdown research playbooks with YAML frontmatter, coordinates
real-time data ingestion across quantitative and prediction market feeds,
parses standardized symbol verdicts, and tracks historical state deltas.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SystemConfig
from database.safe_ops import safe_commit

logger = logging.getLogger("TradingAgent.Analysis.MacroPlaybookRunner")

VALID_VERDICT_STATES = {"HOT_BULLISH", "HOT_BEARISH", "NEUTRAL", "RISK_OFF"}

VERDICT_PATTERN = re.compile(
    r"^-\s*([A-Za-z0-9_]+)\s*:\s*([A-Z_]+)\s*-\s*(.+)$",
    re.MULTILINE,
)


@dataclass
class PlaybookMetadata:
    title: str
    suggested_schedule: str = ""
    timezone: str = "UTC"
    target_symbols: list[str] = None
    data_capabilities: list[str] = None

    def __post_init__(self):
        if self.target_symbols is None:
            self.target_symbols = []
        if self.data_capabilities is None:
            self.data_capabilities = []


@dataclass
class SymbolVerdict:
    symbol: str
    state: str
    reason: str


@dataclass
class VerdictDelta:
    symbol: str
    previous_state: Optional[str]
    current_state: str
    reason: str
    changed: bool


class MacroPlaybookRunner:
    """Loads, executes, and parses structured verdicts from macro playbooks."""

    def __init__(self, session: Optional[AsyncSession] = None, settings: Optional[dict] = None) -> None:
        self.session = session
        self.settings = settings or {}

    def parse_playbook_file(self, file_path: Path | str) -> tuple[PlaybookMetadata, str]:
        """Reads a markdown playbook, extracts YAML frontmatter and template body."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Playbook file not found: {path}")

        raw_content = path.read_text(encoding="utf-8")
        if not raw_content.startswith("---"):
            raise ValueError(f"Playbook {path.name} missing YAML frontmatter opening '---'")

        parts = raw_content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Playbook {path.name} has malformed YAML frontmatter boundaries")

        frontmatter_raw = parts[1]
        body = parts[2].strip()

        try:
            fm_data = yaml.safe_load(frontmatter_raw) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Failed parsing YAML frontmatter in {path.name}: {e}")

        meta = PlaybookMetadata(
            title=fm_data.get("title", path.stem),
            suggested_schedule=fm_data.get("suggested_schedule", ""),
            timezone=fm_data.get("timezone", "UTC"),
            target_symbols=fm_data.get("target_symbols", []),
            data_capabilities=fm_data.get("data_capabilities", []),
        )
        return meta, body

    def parse_verdicts_from_text(self, text: str) -> dict[str, SymbolVerdict]:
        """
        Parses verdicts formatted as:
        ## Verdict:
        - EURUSD: HOT_BULLISH - reason text
        - XAUUSD: RISK_OFF - reason text
        """
        verdicts: dict[str, SymbolVerdict] = {}
        # Locate ## Verdict section
        verdict_section_match = re.search(r"##\s*Verdict\s*:?\s*([\s\S]+)", text, re.IGNORECASE)
        target_text = verdict_section_match.group(1) if verdict_section_match else text

        for match in VERDICT_PATTERN.finditer(target_text):
            sym = match.group(1).upper().strip()
            state = match.group(2).upper().strip()
            reason = match.group(3).strip()

            if state not in VALID_VERDICT_STATES:
                logger.warning(f"Unrecognized verdict state '{state}' for {sym}, defaulting to NEUTRAL")
                state = "NEUTRAL"

            verdicts[sym] = SymbolVerdict(symbol=sym, state=state, reason=reason)

        return verdicts

    async def compute_and_persist_deltas(
        self,
        playbook_name: str,
        current_verdicts: dict[str, SymbolVerdict],
    ) -> list[VerdictDelta]:
        """
        Compares new verdicts with previous snapshot in DB and saves deltas.
        """
        deltas: list[VerdictDelta] = []
        cfg_key = f"macro_verdicts_{playbook_name.lower()}"
        previous_data: dict[str, Any] = {}

        if self.session is not None:
            row = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key).limit(1)
            )).scalar_one_or_none()
            if row and row.value:
                try:
                    previous_data = json.loads(row.value)
                except Exception:
                    previous_data = {}

        prev_symbols = previous_data.get("verdicts", {})

        for sym, v in current_verdicts.items():
            prev_state = prev_symbols.get(sym, {}).get("state")
            changed = prev_state != v.state
            deltas.append(VerdictDelta(
                symbol=sym,
                previous_state=prev_state,
                current_state=v.state,
                reason=v.reason,
                changed=changed,
            ))

        # Save new snapshot
        new_payload = {
            "playbook": playbook_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "verdicts": {
                sym: {"state": v.state, "reason": v.reason}
                for sym, v in current_verdicts.items()
            },
            "deltas_detected": sum(1 for d in deltas if d.changed),
        }

        if self.session is not None:
            existing = (await self.session.execute(
                select(SystemConfig).where(SystemConfig.key == cfg_key).limit(1)
            )).scalar_one_or_none()

            val_str = json.dumps(new_payload)
            if existing:
                existing.value = val_str
            else:
                self.session.add(SystemConfig(key=cfg_key, value=val_str))

            await safe_commit(self.session, label=f"MacroPlaybook_{playbook_name}")
            logger.info(f"Persisted macro verdicts for {playbook_name} ({new_payload['deltas_detected']} delta(s) detected)")

        return deltas

    async def execute_playbook(self, playbook_path: Path | str) -> dict[str, Any]:
        """
        High-level pipeline: loads playbook, verifies frontmatter, parses verdicts,
        and computes state deltas.
        """
        path = Path(playbook_path)
        meta, body = self.parse_playbook_file(path)
        verdicts = self.parse_verdicts_from_text(body)
        deltas = await self.compute_and_persist_deltas(path.stem, verdicts)

        return {
            "title": meta.title,
            "playbook_file": path.name,
            "schedule": meta.suggested_schedule,
            "timezone": meta.timezone,
            "target_symbols": meta.target_symbols,
            "verdicts": {s: asdict(v) for s, v in verdicts.items()},
            "deltas": [asdict(d) for d in deltas],
            "execution_time": datetime.now(timezone.utc).isoformat(),
        }
