# ==============================================================================
# File: analysis/strategies/hypothesis_registry.py
# Monika Durable Strategy Hypothesis Lifecycle & Deduplication Registry
# ==============================================================================

"""
Durable Strategy Hypothesis Lifecycle Registry.

Tracks the full lifecycle of alpha concepts and strategy hypotheses:
EXPLORING -> TESTING -> VALIDATED -> REJECTED -> INCUBATING -> ACTIVE -> DECAYED.
Provides deduplication to prevent re-testing failed ideas and manages
parent-child lineage with mandatory 15-trade paper incubation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Strategies.HypothesisRegistry")

DEFAULT_STORAGE_FILE = Path("data/strategy_hypotheses.json")


class HypothesisStatus(str, Enum):
    EXPLORING = "EXPLORING"
    TESTING = "TESTING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    INCUBATING = "INCUBATING"
    ACTIVE = "ACTIVE"
    DECAYED = "DECAYED"


@dataclass
class StrategyHypothesis:
    hypothesis_id: str
    thesis: str
    signal_definition: str
    target_universe: list[str]
    timeframe: str = "H1"
    status: HypothesisStatus = HypothesisStatus.EXPLORING
    invalidation_notes: Optional[str] = None
    backtest_run_id: Optional[str] = None
    derived_from: Optional[str] = None
    generation: int = 0
    paper_trades_count: int = 0
    paper_wins_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, HypothesisStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyHypothesis:
        raw_status = data.get("status", HypothesisStatus.EXPLORING.value)
        try:
            status = HypothesisStatus(raw_status)
        except ValueError:
            status = HypothesisStatus.EXPLORING
        return cls(
            hypothesis_id=data.get("hypothesis_id", ""),
            thesis=data.get("thesis", ""),
            signal_definition=data.get("signal_definition", ""),
            target_universe=list(data.get("target_universe", [])),
            timeframe=data.get("timeframe", "H1"),
            status=status,
            invalidation_notes=data.get("invalidation_notes"),
            backtest_run_id=data.get("backtest_run_id"),
            derived_from=data.get("derived_from"),
            generation=int(data.get("generation", 0)),
            paper_trades_count=int(data.get("paper_trades_count", 0)),
            paper_wins_count=int(data.get("paper_wins_count", 0)),
            metrics=dict(data.get("metrics", {})),
            created_at=float(data.get("created_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
        )


def _tokenize_concept(text: str) -> Set[str]:
    """Extracts normalized alphanumeric word tokens for concept similarity matching."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = {w for w in clean.split() if len(w) > 2}
    return tokens


def _concept_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """
    Computes concept similarity using max of Jaccard and containment overlap.
    Detects when a proposed strategy embeds a previously rejected core thesis.
    """
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    jaccard = float(inter / union) if union > 0 else 0.0
    containment = float(inter / min(len(set_a), len(set_b))) if min(len(set_a), len(set_b)) > 0 else 0.0
    return max(jaccard, containment)


class HypothesisRegistry:
    """Persistent storage and lifecycle manager for quantitative hypotheses."""

    def __init__(self, storage_path: Path | str = DEFAULT_STORAGE_FILE) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._hypotheses: dict[str, StrategyHypothesis] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.is_file():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                hyp = StrategyHypothesis.from_dict(item)
                self._hypotheses[hyp.hypothesis_id] = hyp
        except Exception as e:
            logger.error(f"Failed loading hypotheses from {self.storage_path}: {e}")

    def _save(self) -> None:
        try:
            payload = [h.to_dict() for h in self._hypotheses.values()]
            tmp_path = self.storage_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp_path.replace(self.storage_path)
        except Exception as e:
            logger.error(f"Failed saving hypotheses to {self.storage_path}: {e}")

    def generate_id(self, thesis: str, signal_def: str, universe: list[str]) -> str:
        """Deterministic SHA-256 ID based on thesis, signal logic, and target universe."""
        raw = f"{thesis.strip().lower()}|{signal_def.strip().lower()}|{sorted(universe)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def register(
        self,
        thesis: str,
        signal_definition: str,
        target_universe: list[str],
        timeframe: str = "H1",
        derived_from: Optional[str] = None,
        generation: int = 0,
    ) -> StrategyHypothesis:
        """Registers a new hypothesis into the registry with EXPLORING status."""
        hyp_id = self.generate_id(thesis, signal_definition, target_universe)
        now = time.time()

        if hyp_id in self._hypotheses:
            logger.info(f"Hypothesis {hyp_id} already exists in registry.")
            return self._hypotheses[hyp_id]

        hyp = StrategyHypothesis(
            hypothesis_id=hyp_id,
            thesis=thesis,
            signal_definition=signal_definition,
            target_universe=target_universe,
            timeframe=timeframe,
            status=HypothesisStatus.EXPLORING,
            derived_from=derived_from,
            generation=generation,
            created_at=now,
            updated_at=now,
        )
        self._hypotheses[hyp_id] = hyp
        self._save()
        logger.info(f"Registered new hypothesis [{hyp_id}] (Gen {generation}): {thesis[:60]}...")
        return hyp

    def update_status(
        self,
        hypothesis_id: str,
        new_status: HypothesisStatus,
        invalidation_notes: Optional[str] = None,
        metrics: Optional[dict[str, Any]] = None,
        backtest_run_id: Optional[str] = None,
    ) -> Optional[StrategyHypothesis]:
        """Updates hypothesis status and records performance or invalidation details."""
        hyp = self._hypotheses.get(hypothesis_id)
        if not hyp:
            logger.warning(f"Hypothesis {hypothesis_id} not found for status update")
            return None

        hyp.status = new_status
        hyp.updated_at = time.time()
        if invalidation_notes:
            hyp.invalidation_notes = invalidation_notes
        if metrics:
            hyp.metrics.update(metrics)
        if backtest_run_id:
            hyp.backtest_run_id = backtest_run_id

        self._save()
        logger.info(f"Hypothesis [{hypothesis_id}] transitioned to {new_status.value}")
        return hyp

    def is_duplicate_or_rejected(
        self,
        concept_text: str,
        similarity_threshold: float = 0.70,
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks whether concept_text substantially matches a previously REJECTED hypothesis.
        Prevents repeating failed backtests and wasting compute cycles.
        """
        tokens_query = _tokenize_concept(concept_text)
        if not tokens_query:
            return False, None

        for hyp in self._hypotheses.values():
            if hyp.status == HypothesisStatus.REJECTED:
                hyp_tokens = _tokenize_concept(f"{hyp.thesis} {hyp.signal_definition}")
                sim = _concept_similarity(tokens_query, hyp_tokens)
                if sim >= similarity_threshold:
                    reason = (
                        f"Matches rejected hypothesis [{hyp.hypothesis_id}] (similarity={sim:.2f}): "
                        f"{hyp.invalidation_notes or 'Failed historical criteria'}"
                    )
                    return True, reason

        return False, None

    def record_paper_trade(
        self,
        hypothesis_id: str,
        is_win: bool,
        required_incubation_trades: int = 15,
        min_incubation_win_rate: float = 0.50,
    ) -> Optional[StrategyHypothesis]:
        """
        Records a paper trade outcome during INCUBATING phase.
        Automatically promotes to ACTIVE if 15+ paper trades are verified and win rate meets target.
        """
        hyp = self._hypotheses.get(hypothesis_id)
        if not hyp:
            return None

        hyp.paper_trades_count += 1
        if is_win:
            hyp.paper_wins_count += 1
        hyp.updated_at = time.time()

        if hyp.status == HypothesisStatus.INCUBATING:
            win_rate = hyp.paper_wins_count / hyp.paper_trades_count
            if hyp.paper_trades_count >= required_incubation_trades:
                if win_rate >= min_incubation_win_rate:
                    hyp.status = HypothesisStatus.ACTIVE
                    logger.info(
                        f"PROMOTED hypothesis [{hypothesis_id}] to ACTIVE after {hyp.paper_trades_count} "
                        f"paper trades (WinRate={win_rate * 100:.1f}%)"
                    )
                else:
                    hyp.status = HypothesisStatus.REJECTED
                    hyp.invalidation_notes = f"Failed incubation stage: WinRate={win_rate * 100:.1f}% < {min_incubation_win_rate * 100:.1f}%"
                    logger.warning(
                        f"REJECTED hypothesis [{hypothesis_id}] during incubation: {hyp.invalidation_notes}"
                    )

        self._save()
        return hyp

    def get_by_status(self, status: HypothesisStatus) -> list[StrategyHypothesis]:
        return [h for h in self._hypotheses.values() if h.status == status]
