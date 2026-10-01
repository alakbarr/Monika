# ==============================================================================
# File: analysis/research/macro_playbook_runner.py
# Monika Scheduled Macro Research Playbook Runner & Verdict Delta Engine
# ==============================================================================

"""
Scheduled Macro Research Playbook Runner.

Executes markdown research playbooks with YAML frontmatter, coordinates
real-time data ingestion across quantitative and prediction market feeds,
synthesizes standardized symbol verdicts dynamically via LLM reasoning,
and tracks historical state deltas in PostgreSQL.
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

VALID_VERDICT_STATES = {
    "HOT_BULLISH",
    "BULLISH",
    "NEUTRAL",
    "BEARISH",
    "HOT_BEARISH",
    "RISK_OFF",
}

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
        ## Verdict: / ## Verdict Format:
        - EURUSD: HOT_BULLISH - reason text
        - XAUUSD: RISK_OFF - reason text
        """
        verdicts: dict[str, SymbolVerdict] = {}
        if not text:
            return verdicts

        # Locate ## Verdict or ## Verdict Format section if present
        verdict_section_match = re.search(r"##\s*Verdict(?:\s*Format)?\s*:?\s*([\s\S]+)", text, re.IGNORECASE)
        target_text = verdict_section_match.group(1) if verdict_section_match else text

        for match in VERDICT_PATTERN.finditer(target_text):
            sym = match.group(1).upper().strip()
            state = match.group(2).upper().strip()
            reason = match.group(3).strip()

            # Skip template variable markers e.g. {SYMBOL}, {BIAS}
            if sym.startswith("{") or state.startswith("{"):
                continue

            if state not in VALID_VERDICT_STATES:
                logger.warning(f"Unrecognized verdict state '{state}' for {sym}, defaulting to NEUTRAL")
                state = "NEUTRAL"

            verdicts[sym] = SymbolVerdict(symbol=sym, state=state, reason=reason)

        return verdicts

    async def _fetch_playbook_data(self, meta: PlaybookMetadata) -> dict[str, Any]:
        """Fetch real-time market data based on playbook's declared data_capabilities."""
        data_bundle: dict[str, Any] = {}
        if not meta.data_capabilities:
            return data_bundle

        try:
            from analysis.tools.domain.macro_handlers import MacroToolHandlers
            from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers

            macro_h = MacroToolHandlers(self.settings)
            sent_h = SentimentToolHandlers(self.settings)

            capability_map = {
                "economic_calendar": lambda: macro_h.get_economic_calendar(session=self.session),
                "treasury_yields": lambda: macro_h.get_treasury_yields(session=self.session),
                "bond_yield_spreads": lambda: macro_h.get_bond_yield_spreads(session=self.session),
                "vix": lambda: macro_h.get_vix(session=self.session),
                "dxy": lambda: macro_h.get_dxy(session=self.session),
                "cot_report": lambda: macro_h.get_cot_report(session=self.session),
                "cot_signals": lambda: macro_h.get_precomputed_cot_signals(session=self.session),
                "fedwatch": lambda: macro_h.get_fedwatch_probabilities(session=self.session),
                "fear_greed": lambda: sent_h.get_fear_greed(session=self.session),
                "retail_sentiment": lambda: sent_h.get_retail_sentiment(session=self.session),
                "news_digest": lambda: sent_h.get_news_digest(session=self.session),
            }

            for cap in meta.data_capabilities:
                handler = capability_map.get(cap)
                if handler:
                    try:
                        res = await handler()
                        data_bundle[cap] = res
                    except Exception as err:
                        logger.debug(f"[MacroPlaybookRunner] Fetch capability '{cap}' failed: {err}")
        except Exception as e:
            logger.debug(f"[MacroPlaybookRunner] Domain handlers init non-fatal error: {e}")

        return data_bundle

    async def _generate_verdicts_via_llm(
        self,
        meta: PlaybookMetadata,
        template_body: str,
        data_bundle: dict[str, Any],
    ) -> str:
        """Use LLM to generate verdicts based on playbook structure + real-time data."""
        from analysis.providers.llm_factory import get_client_for_task

        symbols_str = ", ".join(meta.target_symbols) if meta.target_symbols else "EURUSD, GBPUSD, XAUUSD, USDJPY"
        valid_states_str = ", ".join(sorted(VALID_VERDICT_STATES))

        system_prompt = (
            "You are a Senior Macro Research Strategist generating decisive, high-conviction trading verdicts.\n"
            "Analyze the provided real-time market data through the lens of the macro playbook framework.\n"
            "RULES:\n"
            "- Each verdict MUST be on its own line formatted exactly as: - {SYMBOL}: {BIAS} - {1-sentence rationale}\n"
            f"- Allowed biases: {valid_states_str}\n"
            "- Rationales must cite concrete market levels, spreads, or economic datapoints\n"
            "- Be decisive: avoid NEUTRAL unless macroeconomic evidence is genuinely contradictory\n"
            "- Output ONLY the verdict lines under '## Verdict:' heading."
        )

        user_prompt = (
            f"## Playbook: {meta.title}\n\n"
            f"## Target Symbols: {symbols_str}\n\n"
            f"## Framework Guidelines:\n{template_body}\n\n"
            f"## Live Market Data Snapshot:\n```json\n{json.dumps(data_bundle, default=str, indent=2)[:8000]}\n```\n\n"
            f"Generate structured verdicts for all target symbols ({symbols_str}):"
        )

        client = get_client_for_task("stage1_fundamental", settings=self.settings)
        response = await client.generate(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.2,
            max_tokens=600,
        )
        return response or ""

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
        High-level pipeline: loads playbook template, fetches real-time data,
        generates verdicts via LLM reasoning with graceful fallback, and computes state deltas.
        """
        path = Path(playbook_path)
        meta, body = self.parse_playbook_file(path)

        # 1. Fetch real-time market data based on playbook capabilities
        data_bundle = await self._fetch_playbook_data(meta)

        # 2. Generate verdicts dynamically via LLM with fallback to template parsing
        verdicts: dict[str, SymbolVerdict] = {}
        generation_method = "llm"

        try:
            llm_text = await self._generate_verdicts_via_llm(meta, body, data_bundle)
            verdicts = self.parse_verdicts_from_text(llm_text)
        except Exception as e:
            logger.debug(f"[MacroPlaybookRunner] Dynamic LLM generation fallback triggered for {path.name}: {e}")

        if not verdicts:
            verdicts = self.parse_verdicts_from_text(body)
            generation_method = "static_fallback"

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
            "data_sources": list(data_bundle.keys()),
            "generation_method": generation_method,
        }
