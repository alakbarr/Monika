"""
File: risk/trade_proposal.py
PR-14: TradeProposal Schema & Financial Fortress Plane Boundary.
Defines the strictly-typed, immutable contract between Plane 1 (Analysis Playground)
and Plane 2 (Financial Fortress: RiskGate, Invariants, and Execution).
"""

import hashlib
import math
import uuid
from datetime import datetime, timezone, UTC
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TradeProposal(BaseModel):
    """
    Immutable proposal contract emitted by Plane 1 (AI Analysis Playground)
    and validated independently by Plane 2 (Financial Fortress).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    symbol: str
    direction: Literal["BUY", "SELL", "WAIT"]
    entry_price: float = Field(default=0.0)
    stop_loss: float = Field(default=0.0)
    take_profit: float = Field(default=0.0)
    lot_size: float = Field(default=0.0)
    confluence_score: float = Field(default=50.0, ge=0.0, le=100.0)
    confidence_override: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning_hash: str = Field(default="")
    provenance_verified: bool = Field(default=False)
    account_equity: float | None = None
    free_margin: float | None = None
    spread_pips: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    analysis: Any | None = Field(default=None, exclude=True)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("Symbol cannot be empty")
        return s

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, v: Any) -> str:
        s = str(v).strip().upper()
        if s not in ("BUY", "SELL", "WAIT"):
            raise ValueError(f"Invalid direction: {s}")
        return s

    @model_validator(mode="after")
    def validate_geometry_and_numerics(self) -> TradeProposal:
        # Check for NaN / Inf
        for f_name in ("entry_price", "stop_loss", "take_profit", "lot_size", "confluence_score"):
            val = getattr(self, f_name)
            if val is not None and (math.isnan(val) or math.isinf(val)):
                raise ValueError(f"Field '{f_name}' cannot be NaN or Infinite: {val}")

        is_trailing = bool(
            self.metadata.get("is_trailing") or self.metadata.get("trailing_stop") or self.metadata.get("runner")
        )
        if self.direction in ("BUY", "SELL"):
            if self.entry_price <= 0.0:
                raise ValueError(f"Active trade ({self.direction}) requires entry_price > 0, got {self.entry_price}")
            if self.stop_loss <= 0.0:
                raise ValueError(f"Active trade ({self.direction}) requires stop_loss > 0, got {self.stop_loss}")
            if not is_trailing and self.take_profit <= 0.0:
                raise ValueError(f"Active trade ({self.direction}) requires take_profit > 0, got {self.take_profit}")

            # Directional geometric sanity
            if self.direction == "BUY":
                if not is_trailing:
                    if not (self.stop_loss < self.entry_price < self.take_profit):
                        raise ValueError(
                            f"BUY geometry violation: SL ({self.stop_loss}) must be < Entry ({self.entry_price}) < TP ({self.take_profit})"
                        )
                else:
                    if self.stop_loss >= self.entry_price:
                        raise ValueError(
                            f"BUY geometry violation: SL ({self.stop_loss}) must be < Entry ({self.entry_price})"
                        )
            elif self.direction == "SELL":
                if not is_trailing:
                    if not (self.take_profit < self.entry_price < self.stop_loss):
                        raise ValueError(
                            f"SELL geometry violation: TP ({self.take_profit}) must be < Entry ({self.entry_price}) < SL ({self.stop_loss})"
                        )
                else:
                    if self.stop_loss <= self.entry_price:
                        raise ValueError(
                            f"SELL geometry violation: SL ({self.stop_loss}) must be > Entry ({self.entry_price})"
                        )

        return self

    @classmethod
    def compute_reasoning_hash(cls, reasoning_text: Any) -> str:
        """Computes SHA-256 hash of reasoning text."""
        if isinstance(reasoning_text, str):
            encoded = reasoning_text.strip().encode("utf-8")
        elif isinstance(reasoning_text, (bytes, bytearray)):
            encoded = bytes(reasoning_text)
        else:
            encoded = str(reasoning_text or "").strip().encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_analysis(
        cls,
        symbol: str,
        decision: str,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        lot_size: float = 0.0,
        confluence_score: float = 50.0,
        confidence_override: float | None = None,
        reasoning_text: str = "",
        provenance_verified: bool = False,
        account_equity: float | None = None,
        free_margin: float | None = None,
        spread_pips: float | None = None,
        metadata: dict[str, Any] | None = None,
        analysis: Any | None = None,
    ) -> TradeProposal:
        """Factory helper creating a validated TradeProposal with automated reasoning hash."""
        r_hash = cls.compute_reasoning_hash(reasoning_text)
        norm_dir = decision.strip().upper()
        dir_val: Literal["BUY", "SELL", "WAIT"] = (
            "BUY" if norm_dir == "BUY" else ("SELL" if norm_dir == "SELL" else "WAIT")
        )
        meta = dict(metadata or {})
        if analysis is not None:
            if "analysis_id" not in meta and getattr(analysis, "id", None) is not None:
                meta["analysis_id"] = analysis.id
            if "priced_in_score" not in meta and getattr(analysis, "priced_in_score", None) is not None:
                meta["priced_in_score"] = analysis.priced_in_score
            if "confluence_score" not in meta and getattr(analysis, "confluence_score", None) is not None:
                meta["confluence_score"] = analysis.confluence_score
            if "pair_group_id" not in meta and getattr(analysis, "pair_group_id", None) is not None:
                meta["pair_group_id"] = analysis.pair_group_id

        return cls(
            symbol=symbol,
            direction=dir_val,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            lot_size=lot_size,
            confluence_score=confluence_score,
            confidence_override=confidence_override,
            reasoning_hash=r_hash,
            provenance_verified=provenance_verified,
            account_equity=account_equity,
            free_margin=free_margin,
            spread_pips=spread_pips,
            metadata=meta,
            analysis=analysis,
        )


class FortressAdmissionValidator:
    """
    Independent Financial Fortress Gatekeeper.
    Performs boundary checks on incoming TradeProposals before RiskGate execution.
    """

    MAX_PROPOSAL_AGE_SECONDS = 300.0  # 5 minutes staleness limit for live order admission

    @classmethod
    def validate_proposal(
        cls,
        proposal: TradeProposal,
        max_age_seconds: float = MAX_PROPOSAL_AGE_SECONDS,
        require_provenance: bool = False,
        is_backtest: bool = False,
        min_rr_ratio: float = 1.5,
    ) -> tuple[bool, list[str]]:
        """
        Validates that a proposal satisfies Financial Fortress admission rules:
        1. Proposal timestamp freshness (anti-replay / anti-staleness).
        2. Numeric sanity of lot sizes.
        3. Mandatory provenance verification (if required by security settings).
        4. Geometry and risk-reward ratio sanity.
        """
        rejections: list[str] = []

        # 1. Staleness check (skip in backtest)
        is_bt = is_backtest or bool(proposal.metadata.get("is_backtest"))
        if not is_bt:
            now = _utcnow()
            proposal_time = proposal.timestamp
            if proposal_time.tzinfo is None:
                proposal_time = proposal_time.replace(tzinfo=UTC)
            age = (now - proposal_time).total_seconds()
            if age > max_age_seconds:
                rejections.append(f"Proposal expired: age {age:.1f}s exceeds limit {max_age_seconds:.1f}s")
            elif age < -30.0:
                rejections.append(f"Proposal timestamp in future: {age:.1f}s drift")

        # 2. Provenance check
        if require_provenance and not proposal.provenance_verified:
            rejections.append("Proposal rejected: provenance_verified flag is False")

        # 3. Active direction checks
        if proposal.direction in ("BUY", "SELL"):
            if proposal.lot_size <= 0.0:
                rejections.append(f"Lot size must be positive, got {proposal.lot_size}")
            elif proposal.lot_size > 50.0:  # Absolute safety ceiling
                rejections.append(f"Lot size exceeds absolute fortress ceiling (50.0 lots): {proposal.lot_size}")

            # R:R ratio check (skip for trailing stop / runner strategies)
            is_trailing = bool(
                proposal.metadata.get("is_trailing")
                or proposal.metadata.get("trailing_stop")
                or proposal.metadata.get("runner")
            )
            if not is_trailing:
                risk = abs(proposal.entry_price - proposal.stop_loss)
                reward = abs(proposal.take_profit - proposal.entry_price)
                if risk > 0:
                    rr = reward / risk
                    if rr < min_rr_ratio:
                        rejections.append(f"Unacceptable Risk:Reward ratio {rr:.2f} (< {min_rr_ratio})")

        admitted = len(rejections) == 0
        return admitted, rejections
