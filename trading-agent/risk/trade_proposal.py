"""
File: risk/trade_proposal.py
PR-14: TradeProposal Schema & Financial Fortress Plane Boundary.
Defines the strictly-typed, immutable contract between Plane 1 (Analysis Playground)
and Plane 2 (Financial Fortress: RiskGate, Invariants, and Execution).
"""

import hashlib
import uuid
import math
from datetime import datetime, timezone
from typing import Literal, Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, field_validator, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradeProposal(BaseModel):
    """
    Immutable proposal contract emitted by Plane 1 (AI Analysis Playground)
    and validated independently by Plane 2 (Financial Fortress).
    """
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    symbol: str
    direction: Literal["BUY", "SELL", "WAIT"]
    entry_price: float = Field(default=0.0)
    stop_loss: float = Field(default=0.0)
    take_profit: float = Field(default=0.0)
    lot_size: float = Field(default=0.0)
    confluence_score: float = Field(default=50.0, ge=0.0, le=100.0)
    reasoning_hash: str = Field(default="")
    provenance_verified: bool = Field(default=False)
    account_equity: Optional[float] = None
    free_margin: Optional[float] = None
    spread_pips: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

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
    def validate_geometry_and_numerics(self) -> "TradeProposal":
        # Check for NaN / Inf
        for f_name in ("entry_price", "stop_loss", "take_profit", "lot_size", "confluence_score"):
            val = getattr(self, f_name)
            if val is not None and (math.isnan(val) or math.isinf(val)):
                raise ValueError(f"Field '{f_name}' cannot be NaN or Infinite: {val}")

        if self.direction in ("BUY", "SELL"):
            if self.entry_price <= 0.0:
                raise ValueError(f"Active trade ({self.direction}) requires entry_price > 0, got {self.entry_price}")
            if self.stop_loss <= 0.0:
                raise ValueError(f"Active trade ({self.direction}) requires stop_loss > 0, got {self.stop_loss}")
            if self.take_profit <= 0.0:
                raise ValueError(f"Active trade ({self.direction}) requires take_profit > 0, got {self.take_profit}")

            # Directional geometric sanity
            if self.direction == "BUY":
                if not (self.stop_loss < self.entry_price < self.take_profit):
                    raise ValueError(
                        f"BUY geometry violation: SL ({self.stop_loss}) must be < Entry ({self.entry_price}) < TP ({self.take_profit})"
                    )
            elif self.direction == "SELL":
                if not (self.take_profit < self.entry_price < self.stop_loss):
                    raise ValueError(
                        f"SELL geometry violation: TP ({self.take_profit}) must be < Entry ({self.entry_price}) < SL ({self.stop_loss})"
                    )

        return self

    @classmethod
    def compute_reasoning_hash(cls, reasoning_text: str) -> str:
        """Computes SHA-256 hash of reasoning text."""
        return hashlib.sha256((reasoning_text or "").strip().encode("utf-8")).hexdigest()

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
        reasoning_text: str = "",
        provenance_verified: bool = False,
        account_equity: Optional[float] = None,
        free_margin: Optional[float] = None,
        spread_pips: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TradeProposal":
        """Factory helper creating a validated TradeProposal with automated reasoning hash."""
        r_hash = cls.compute_reasoning_hash(reasoning_text)
        return cls(
            symbol=symbol,
            direction=decision.upper(),  # type: ignore[arg-type]
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            lot_size=lot_size,
            confluence_score=confluence_score,
            reasoning_hash=r_hash,
            provenance_verified=provenance_verified,
            account_equity=account_equity,
            free_margin=free_margin,
            spread_pips=spread_pips,
            metadata=metadata or {},
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
    ) -> tuple[bool, List[str]]:
        """
        Validates that a proposal satisfies Financial Fortress admission rules:
        1. Proposal timestamp freshness (anti-replay / anti-staleness).
        2. Numeric sanity of lot sizes.
        3. Mandatory provenance verification (if required by security settings).
        4. Geometry and risk-reward ratio sanity.
        """
        rejections: List[str] = []

        # 1. Staleness check
        now = _utcnow()
        proposal_time = proposal.timestamp
        if proposal_time.tzinfo is None:
            proposal_time = proposal_time.replace(tzinfo=timezone.utc)
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

            # R:R ratio check
            risk = abs(proposal.entry_price - proposal.stop_loss)
            reward = abs(proposal.take_profit - proposal.entry_price)
            if risk > 0:
                rr = reward / risk
                if rr < 0.8:
                    rejections.append(f"Unacceptable Risk:Reward ratio {rr:.2f} (< 0.8)")

        admitted = len(rejections) == 0
        return admitted, rejections
