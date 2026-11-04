# ==============================================================================
# File: application/analysis/schemas/analysis_schemas.py
# ==============================================================================

"""
Submit Asset Analysis Schema Definition and Multi-layer Validators.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import math
import re
import json
import copy

from monika.application.analysis.schemas.common import (
    ConfidenceLevel,
    TradeDirection,
    coerce_float,
    coerce_int,
    coerce_str,
    coerce_string_list,
)
from monika.application.analysis.schemas.sub_models import (
    EntryCondition,
    PricedInAssessment,
    PricedInOverrideJustification,
    ReevaluationTrigger,
    SpecialistAdjudication,
    UpcomingRiskEvent,
)

logger = logging.getLogger("TradingAgent.Schemas")


class SubmitAssetAnalysisSchema(BaseModel):
    symbol: str = Field(
        ...,
        description="Trading symbol this analysis is for (e.g. 'EURUSD', 'XAUUSD', 'BTCUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XTIUSD'). REQUIRED.",
    )
    decision: Literal["buy", "sell", "avoid", "wait"] = Field(
        ...,
        description="'buy'/'sell' = set up a trade. 'wait' = thesis valid but entry not ready yet. 'avoid' = do not trade this asset this cycle.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this decision (0.0 to 1.0).")
    rationale: str = Field(
        ...,
        description=(
            "Top-down structured reasoning for the decision: "
            "(1) Macro & Sentiment alignment with Stage 1 brief, "
            "(2) Technical & SMC trigger levels (exact numerical anchors, ATR multiples, R:R), "
            "(3) Confluence factors, historical pattern similarity, and quantitative edge."
        ),
    )

    specialist_adjudication: Optional[SpecialistAdjudication] = Field(
        None,
        description="Structured conflict resolution. MANDATORY if technical, sentiment, and macro specialists disagree on direction, or if SMC setup diverges from Stage 1 Fundamental Brief macro bias. Must include conflict_detected=true, resolution_path, and resolution_justification.",
    )

    entry_condition: Optional[EntryCondition] = Field(
        None, description="Entry condition. Required if decision is 'buy' or 'sell'."
    )
    priced_in_override_justification: Optional[PricedInOverrideJustification] = Field(
        None,
        description="ONLY fill if you are overriding a priced_in_score >= 8 guard. Must provide: override_reason (string), why_stage1_wrong (string), post_event_evidence (string). If null, standard rules apply.",
    )

    stop_loss: Optional[float] = Field(
        None, description="Stop loss price level. Required if decision is 'buy' or 'sell'."
    )
    take_profit: Optional[float] = Field(
        None, description="Take profit price level. Required if decision is 'buy' or 'sell'."
    )

    playbook_id: Optional[str] = Field(
        None,
        description=(
            "OPTIONAL / RECOMMENDED: The specific empirical playbook ID triggered and validated for this trade setup, "
            "e.g. 'xauusd_london_expansion_playbook' or 'eurusd_asian_range_breakout_playbook'. "
            "If specified, order invariants and performance attribution are linked directly to this empirical playbook."
        ),
    )
    adopted_bracket: Optional[str] = Field(
        None,
        description=(
            "OPTIONAL / RECOMMENDED: Verified bracket option adopted from pre-computed invariants, "
            "e.g. 'LONG_OPTION_A' or 'SHORT_OPTION_B'. Eliminates manual mental arithmetic errors "
            "and automatically populates entry, stop_loss, and take_profit."
        ),
    )

    invalidation: str = Field(
        ...,
        description=(
            "REQUIRED: Specific condition that completely invalidates this thesis. "
            "MUST include a specific price level and direction. "
            "EXAMPLE GOOD: 'Thesis invalid if XAUUSD D1 closes above 2420 (breaks bullish structure)'. "
            "EXAMPLE BAD: 'If market changes direction'. "
            "DO NOT submit a dict or list â€” must be a plain string. "
            "Also fill invalidation_price and invalidation_direction fields separately for monitoring."
        ),
    )

    @field_validator("playbook_id", mode="before")
    @classmethod
    def validate_playbook_id_field(cls, v):
        if v is None:
            return None
        if isinstance(v, dict):
            name = v.get("name") or v.get("playbook_id") or v.get("id")
            if not name:
                return None
            v = str(name).strip()
        if isinstance(v, str):
            clean = v.strip()
            if not clean or clean.lower() in ("none", "null", "n/a", "no", "false"):
                return None
            if clean.lower().startswith(("none_", "none ", "no_")):
                return None
            import re

            m = re.match(r"^([a-zA-Z0-9_-]+)", clean)
            if m:
                return m.group(1).strip()[:50]
            return clean[:50]
        return str(v).strip()[:50]

    @field_validator("invalidation", "news_impact_assessment", "rationale", mode="before")
    @classmethod
    def coerce_string_fields(cls, v):
        """Coerce dict/list/non-string to string for LLMs that return structured data."""
        return coerce_str(v)

    @field_validator("key_news_events_considered", "confluence_factors", mode="before")
    @classmethod
    def coerce_string_lists(cls, v):
        """Coerce list of mixed dicts/strings/numbers into a clean list of strings."""
        return coerce_string_list(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_asset_confidence(cls, v):
        val = coerce_float(v, None)
        if val is not None:
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        raise ValueError("Asset analysis confidence must be an explicit numeric float between 0.0 and 1.0")

    @field_validator("stop_loss", "take_profit", "invalidation_price", mode="before")
    @classmethod
    def validate_prices(cls, v):
        import math

        val = coerce_float(v)
        if val is not None and (val <= 0 or math.isnan(val) or math.isinf(val)):
            return None
        return val

    @field_validator("confluence_score", "priced_in_score", mode="before")
    @classmethod
    def validate_scores(cls, v):
        return coerce_int(v)

    @field_validator("invalidation_direction", mode="before")
    @classmethod
    def validate_invalidation_direction(cls, v):
        if v is None:
            return None
        s = str(v).strip().lower()
        if s in ("above", "below"):
            return s
        if "above" in s or "over" in s or "up" in s:
            return "above"
        if "below" in s or "under" in s or "down" in s:
            return "below"
        return None

    @field_validator("specialist_adjudication", mode="before")
    @classmethod
    def validate_specialist_adjudication_field(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if (
                not s
                or s
                in (
                    "none",
                    "null",
                    "n/a",
                    "no",
                    "false",
                    "{}",
                    "-",
                    "no conflict",
                    "not applicable",
                    "none needed",
                    "no disagreement",
                )
                or any(term in s for term in ("no conflict", "no disagreement", "not applicable", "none needed"))
            ):
                return None
        if isinstance(v, dict) and not v:
            return None
        return v

    @field_validator("priced_in_override_justification", mode="before")
    @classmethod
    def validate_override_justification_field(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if (
                not s
                or s
                in (
                    "none",
                    "null",
                    "n/a",
                    "na",
                    "no",
                    "false",
                    "{}",
                    "-",
                    "not applicable",
                    "n/a - wait",
                    "no override",
                    "not required",
                    "none needed",
                    "not needed",
                )
                or s.startswith(("not applicable", "no override", "none needed", "not required", "not needed"))
            ):
                return None
            return v
        if isinstance(v, dict):
            if not v:
                return None
            if (
                v.get("not_applicable") is True
                or v.get("applicable") is False
                or v.get("override_needed") is False
                or v.get("is_override") is False
                or v.get("override") is False
                or v.get("required") is False
                or str(v.get("status", "")).strip().lower()
                in ("not applicable", "none", "n/a", "na", "false", "no", "disabled", "inactive")
            ):
                return None
            all_trivial = True
            for val in v.values():
                if val is not None:
                    s_val = str(val).strip().lower()
                    if s_val not in ("", "none", "null", "n/a", "na", "false", "no", "{}"):
                        all_trivial = False
                        break
            if all_trivial:
                return None
            return v
        return v

    invalidation_price: Optional[float] = Field(
        None,
        description='REQUIRED for buy/sell decisions: The specific price level that invalidates your thesis. Example: if BUY and thesis invalid below 2420, set invalidation_price=2420, invalidation_direction="below". Used for automated monitoring of open positions.',
    )
    invalidation_direction: Optional[Literal["above", "below"]] = Field(
        None,
        description='REQUIRED for buy/sell decisions: "above" = thesis invalid if price closes ABOVE invalidation_price. "below" = thesis invalid if price closes BELOW invalidation_price.',
    )

    reevaluation_trigger: Optional[ReevaluationTrigger] = Field(
        None, description="Condition that should trigger re-analysis. Required if decision is 'buy', 'sell', or 'wait'."
    )

    priced_in_score: Optional[int] = Field(
        None,
        ge=1,
        le=10,
        description="REQUIRED for buy/sell decisions: Asset-specific priced-in score (1-10 scale). Sum of applicable sub-scores: FedWatch (0-3) + COT extreme positioning (0-3) + price run-up vs ATR from get_price_momentum (0-3) + news saturation (0-1). 1=not priced in, 10=fully priced in. Score >= 8 with major event within 12h: MANDATORY WAIT. Score 5-7: increase confluence threshold +2, reduce lot size 30-50%. Score <= 4: standard thresholds apply.",
    )
    confluence_score: Optional[int] = Field(
        None,
        ge=0,
        le=20,
        description="REQUIRED for buy/sell decisions: Total confluence score (integer 0-20) based on SMC/ICT framework (core 14 points + valid bonus factors up to 20).",
    )
    confluence_factors: Optional[List[str]] = Field(
        None,
        description='REQUIRED for buy/sell: List of confluence factor IDs that are ACTIVE (scoring points) for this setup. Use these exact IDs: "fundamental_bias", "dxy_confirms", "d1_trend", "rsi_neutral", "near_fvg", "near_order_block", "in_ote_zone", "near_sr_zone", "cot_aligned", "vix_ok", "post_event_entry", "session_prime", "liquidity_sweep_confirmed", "microstructure_ok", "microstructure_confirmed", "historical_pattern_consensus", "pattern_consensus", "quant_strategy_edge", "rr_ratio_bonus", "adr_target_bonus". Example: ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"]',
    )

    key_news_events_considered: Optional[List[str]] = Field(
        None,
        description="Optional list of news events considered in this analysis (e.g. ['US CPI 3.1%', 'FOMC Rate Decision']). Must be a list of plain strings.",
    )
    news_impact_assessment: Optional[str] = Field(
        None, description="Optional assessment of how the news impacts the setup."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_and_alias_fields(cls, data: Any) -> Any:
        """Resolve symbol aliases and normalize symbol casing/formatting before validation."""
        if not isinstance(data, dict):
            return data

        # 1. Alias resolution for symbol
        if not data.get("symbol"):
            for alias in ("asset", "pair", "ticker", "instrument", "symbol_name", "target_asset", "currency_pair"):
                if data.get(alias):
                    data["symbol"] = data[alias]
                    break

        # 2. Normalisasi string symbol
        if data.get("symbol") and isinstance(data["symbol"], str):
            data["symbol"] = data["symbol"].strip().upper().replace("/", "")

        # 2b. Alias resolution for trade levels
        if data.get("sl") is not None and data.get("stop_loss") is None:
            data["stop_loss"] = data["sl"]
        if data.get("tp") is not None and data.get("take_profit") is None:
            data["take_profit"] = data["tp"]
        if data.get("entry") is not None and not data.get("entry_condition"):
            data["entry_condition"] = {
                "type": "limit",
                "price": data["entry"],
                "detail": f"Entry level at {data['entry']}",
            }
        elif (
            (data.get("stop_loss") is not None or data.get("adopted_bracket") is not None)
            and not data.get("entry_condition")
            and str(data.get("decision") or "").lower() in ("buy", "sell")
        ):
            data["entry_condition"] = {
                "type": "market",
                "detail": "Market order execution",
            }

        # 3. Auto-populate fallback reevaluation_trigger if missing
        decision = str(data.get("decision") or "").lower()
        if data.get("decision"):
            data["decision"] = decision
        if not data.get("reevaluation_trigger"):
            sym = data.get("symbol", "")
            if decision in ("buy", "sell"):
                inv_price = data.get("invalidation_price") or data.get("stop_loss")
                if inv_price is not None:
                    data["reevaluation_trigger"] = {
                        "type": "price_level",
                        "symbol": sym,
                        "price": float(inv_price),
                        "detail": f"Auto re-evaluate thesis if price reaches invalidation/SL level {inv_price}",
                    }
                else:
                    data["reevaluation_trigger"] = {
                        "type": "time",
                        "symbol": sym,
                        "hours": 4,
                        "detail": "Auto re-evaluate position on 4-hour cycle or upon structural shift",
                    }
            elif decision == "wait":
                data["reevaluation_trigger"] = {
                    "type": "time",
                    "symbol": sym,
                    "hours": 4,
                    "detail": "Standard wait: re-evaluate on next 4-hour cycle or when key level is tested",
                }

        # 4. Normalisasi invalidation_direction jika ada
        if data.get("invalidation_direction"):
            raw_dir = str(data["invalidation_direction"]).lower().strip()
            if raw_dir in ("up", "above", "long", "bull", "bullish", "higher", "top"):
                data["invalidation_direction"] = "above"
            elif raw_dir in ("down", "below", "short", "bear", "bearish", "lower", "bottom"):
                data["invalidation_direction"] = "below"

        # 5. Auto-populate fallback invalidation if missing
        if not data.get("invalidation"):
            if decision == "avoid":
                data["invalidation"] = "Not applicable: asset avoided this cycle."
            elif decision == "wait":
                data["invalidation"] = (
                    f"Wait thesis invalid if {data.get('symbol', 'asset')} structure breaks or upon 4h cycle timeout."
                )
            elif decision in ("buy", "sell"):
                inv_p = data.get("invalidation_price") or data.get("stop_loss")
                data["invalidation"] = f"Thesis invalid if price breaches invalidation/SL level {inv_p}"

        if decision in ("buy", "sell"):
            if data.get("invalidation_price") is None and data.get("stop_loss") is not None:
                data["invalidation_price"] = data["stop_loss"]
            if not data.get("invalidation_direction"):
                data["invalidation_direction"] = "below" if decision == "buy" else "above"

        # 6. Clean priced_in_override_justification for non-directional decisions if non-substantive
        if decision in ("wait", "avoid"):
            pi_val = data.get("priced_in_override_justification")
            if isinstance(pi_val, str):
                s_pi = pi_val.strip().lower()
                if len(s_pi) < 15 or any(
                    term in s_pi
                    for term in (
                        "not applicable",
                        "n/a",
                        "no override",
                        "none needed",
                        "not needed",
                        "not required",
                        "no trade",
                        "wait",
                    )
                ):
                    data["priced_in_override_justification"] = None

        return data

    @model_validator(mode="after")
    def validate_trade_parameters(self):
        """Enforce SL/TP/entry_condition presence when decision is buy or sell."""
        if self.decision in ("buy", "sell"):
            missing = []
            if self.stop_loss is None:
                missing.append("stop_loss")
            if self.take_profit is None:
                missing.append("take_profit")
            if self.entry_condition is None:
                missing.append("entry_condition")
            if self.reevaluation_trigger is None:
                missing.append("reevaluation_trigger")
            if self.confluence_score is None:
                missing.append("confluence_score")
            if self.priced_in_score is None:
                missing.append("priced_in_score")
            if self.invalidation_price is None:
                missing.append("invalidation_price")
            if self.invalidation_direction is None:
                missing.append("invalidation_direction")
            if not self.invalidation or not str(self.invalidation).strip():
                missing.append("invalidation")
            if self.priced_in_score is not None and self.priced_in_score >= 8:
                if self.priced_in_override_justification is None:
                    missing.append("priced_in_override_justification (required when priced_in_score >= 8)")
            if missing:
                raise ValueError(
                    f"decision='{self.decision}' requires parameters: {', '.join(missing)}. "
                    f"All trade risk parameters must be explicitly defined."
                )
        return self
