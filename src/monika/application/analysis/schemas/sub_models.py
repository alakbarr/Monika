# ==============================================================================
# File: application/analysis/schemas/sub_models.py
# ==============================================================================

"""
Supporting Value Objects and Sub-Schemas for Asset Analysis & Fundamental Briefs.
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
    MacroRegime,
    SentimentBand,
    TradeDirection,
    coerce_float,
    coerce_int,
    coerce_str,
    coerce_string_list,
)

logger = logging.getLogger("TradingAgent.Schemas")


class FundamentalBriefSchema(BaseModel):
    macro_bias: str = Field(default="neutral")
    macro_narrative: Optional[str] = Field(default=None, description="Clear narrative summary of macro conditions")
    key_drivers: list[str] = Field(default_factory=list)
    risk_events: list[str] = Field(default_factory=list)
    narrative_shift: bool = Field(default=False)
    shift_explanation: str | None = None

    macro_regime: MacroRegime = Field(
        default=MacroRegime.MIXED,
        description="Klasifikasi regime makro eksplisit â€” lebih luas dari risk_sentiment (mis. mendeteksi stagflasi).",
    )

    # Kept for backward compatibility
    currency_bias: Dict[str, Literal["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]] = Field(
        default_factory=dict, description="Directional bias for each major currency (USD, EUR, GBP, etc.)"
    )
    currency_confidence: Dict[str, float] = Field(default_factory=dict, description="Confidence per currency")
    invalidation_conditions: Dict[str, str] = Field(
        default_factory=dict, description="Invalidation conditions per asset"
    )
    risk_sentiment: Literal["risk-on", "risk-off", "mixed"] = Field(
        default="mixed", description="Overall market risk sentiment"
    )
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence in this brief (0.0 to 1.0)")
    priced_in_assessment: Optional[Dict] = Field(None, description="Structured assessment of priced-in factors")
    strongest_counter_thesis: Optional[str] = Field(default="", description="Counter thesis argument")

    @model_validator(mode="before")
    @classmethod
    def harmonize_from_submit_brief(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "macro_bias" not in data or not data["macro_bias"]:
                data["macro_bias"] = data.get("risk_sentiment") or "neutral"
            if "macro_narrative" not in data and "macro_bias" in data:
                data["macro_narrative"] = str(data["macro_bias"])
            if "key_drivers" not in data and "key_data_points_used" in data:
                kdp = data["key_data_points_used"]
                if isinstance(kdp, dict):
                    data["key_drivers"] = [f"{k}: {v}" for k, v in kdp.items()]
            if "risk_events" not in data and "key_upcoming_risks" in data:
                risks = data["key_upcoming_risks"]
                if isinstance(risks, list):
                    data["risk_events"] = [r.get("event", str(r)) if isinstance(r, dict) else str(r) for r in risks]
        return data

    @field_validator("macro_regime", mode="before")
    @classmethod
    def validate_macro_regime_fbs(cls, v):
        if isinstance(v, MacroRegime):
            return v
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_")
            for m in MacroRegime:
                if clean == m.value or clean == m.name.lower():
                    return m
        return MacroRegime.MIXED

    @field_validator("risk_sentiment", mode="before")
    @classmethod
    def validate_risk_sentiment_fbs(cls, v):
        if isinstance(v, str):
            clean = v.lower().strip().replace("_", "-")
            if clean in ["risk-on", "risk-off", "mixed"]:
                return clean
            if "on" in clean:
                return "risk-on"
            if "off" in clean:
                return "risk-off"
        return "mixed"

    @field_validator("currency_bias", mode="before")
    @classmethod
    def validate_currency_bias_fbs(cls, v):
        if not isinstance(v, dict):
            return {}
        res = {}
        for ccy, bias in v.items():
            ccy_up = str(ccy).upper().strip()
            if isinstance(bias, str):
                b_clean = bias.lower().strip().replace("-", "_").replace(" ", "_")
                if b_clean in ["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]:
                    res[ccy_up] = b_clean
                elif "bull" in b_clean:
                    res[ccy_up] = "bullish"
                elif "bear" in b_clean:
                    res[ccy_up] = "bearish"
                else:
                    res[ccy_up] = "neutral"
            else:
                res[ccy_up] = "neutral"
        return res

    @field_validator("key_drivers", "risk_events", mode="before")
    @classmethod
    def validate_brief_string_lists(cls, v):
        return coerce_string_list(v, default=[]) or []

    @field_validator("macro_bias", mode="before")
    @classmethod
    def validate_macro_bias(cls, v):
        return coerce_str(v, default="neutral")


class SentimentAnalysisSchema(BaseModel):
    overall_band: SentimentBand  # Bullish/Mildly Bullish/Neutral/Mixed/Mildly Bearish/Bearish
    overall_score: float = Field(ge=0.0, le=10.0)  # 0=bearish, 5=neutral, 10=bullish
    confidence: ConfidenceLevel
    narrative: str
    retail_vs_institutional: str

    @field_validator("overall_band", mode="before")
    @classmethod
    def validate_overall_band(cls, v):
        if isinstance(v, SentimentBand):
            return v
        if isinstance(v, str):
            clean = v.strip().lower().replace("_", " ").replace("-", " ")
            mapping = {
                "bullish": SentimentBand.BULLISH,
                "strong bullish": SentimentBand.BULLISH,
                "mildly bullish": SentimentBand.MILDLY_BULLISH,
                "mild bullish": SentimentBand.MILDLY_BULLISH,
                "neutral": SentimentBand.NEUTRAL,
                "mixed": SentimentBand.MIXED,
                "mildly bearish": SentimentBand.MILDLY_BEARISH,
                "mild bearish": SentimentBand.MILDLY_BEARISH,
                "bearish": SentimentBand.BEARISH,
                "strong bearish": SentimentBand.BEARISH,
            }
            if clean in mapping:
                return mapping[clean]
            if "bull" in clean:
                return SentimentBand.BULLISH
            if "bear" in clean:
                return SentimentBand.BEARISH
        return SentimentBand.NEUTRAL

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v):
        if isinstance(v, ConfidenceLevel):
            return v
        if isinstance(v, str):
            clean = v.strip().lower()
            for c in ConfidenceLevel:
                if clean == c.value or clean == c.name.lower():
                    return c
        return ConfidenceLevel.MEDIUM

    @field_validator("overall_score", mode="before")
    @classmethod
    def validate_overall_score(cls, v):
        res = coerce_float(v)
        if res is not None:
            return max(0.0, min(10.0, res))
        return 5.0

    @field_validator("narrative", "retail_vs_institutional", mode="before")
    @classmethod
    def validate_strings(cls, v):
        return coerce_str(v)


# =============================================================================
# Sub-Schemas (Migrated from schemas.py)
# =============================================================================


class SpecialistAdjudication(BaseModel):
    conflict_detected: bool = Field(
        ..., description="Did the technical/SMC setup conflict with the macro fundamental bias?"
    )
    conflict_reason: Optional[str] = Field(
        None, description="If conflict exists, what is the exact nature of the divergence?"
    )
    resolution_path: Optional[Literal["override_macro", "cancel_setup", "scale_out", "hedged_entry"]] = Field(
        None, description="How the conflict is resolved by the specialist agent."
    )
    resolution_justification: Optional[str] = Field(None, description="Why this resolution was chosen over the others.")

    @model_validator(mode="before")
    @classmethod
    def coerce_specialist_adjudication(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
            if (
                not s
                or s.lower()
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
                or any(
                    term in s.lower() for term in ("no conflict", "no disagreement", "not applicable", "none needed")
                )
            ):
                return {
                    "conflict_detected": False,
                    "conflict_reason": None,
                    "resolution_path": None,
                    "resolution_justification": None,
                }
            return {
                "conflict_detected": True,
                "conflict_reason": s,
                "resolution_path": "cancel_setup",
                "resolution_justification": s,
            }
        if isinstance(data, dict):
            cd = data.get("conflict_detected")
            if isinstance(cd, str):
                data["conflict_detected"] = cd.lower() in ("true", "1", "yes", "y")
            elif cd is None:
                data["conflict_detected"] = bool(data.get("conflict_reason"))
            if data.get("resolution_path"):
                rp = str(data["resolution_path"]).strip().lower()
                data["resolution_path"] = (
                    rp if rp in ("override_macro", "cancel_setup", "scale_out", "hedged_entry") else None
                )
            if data.get("conflict_detected") and not data.get("resolution_path"):
                data["resolution_path"] = "cancel_setup"
        return data


class EntryCondition(BaseModel):
    type: Literal["market", "limit", "trigger"]
    price: Optional[float] = Field(default=None, description="Specific price level (null for 'market').")
    detail: str = Field(..., description="Detailed entry condition description.")

    @model_validator(mode="before")
    @classmethod
    def coerce_entry_condition(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
            from monika.application.agent.harness.tool_repair import _parse_xml_parameters

            xml_dict = _parse_xml_parameters(s)
            if xml_dict:
                data = xml_dict
                if "detail" not in data or not data.get("detail"):
                    data["detail"] = s
                if "type" not in data or not data.get("type"):
                    data["type"] = "market"
            else:
                data = {"type": "market", "detail": s}
        if isinstance(data, dict):
            if "price" not in data or data.get("price") is None:
                for k in ("price_low", "price_high", "level", "entry_price", "target_price"):
                    if data.get(k) is not None:
                        try:
                            data["price"] = float(data[k])
                            break
                        except ValueError, TypeError:
                            pass
            if "detail" not in data or not data.get("detail"):
                data["detail"] = str(data.get("price") or data.get("type") or "Market entry")
            raw_type = str(data.get("type", "")).strip().lower()
            if raw_type in ("market", "instant", "market_order", "now"):
                data["type"] = "market"
            elif raw_type in (
                "limit",
                "pending",
                "limit_order",
                "fvg_entry",
                "ob_entry",
                "order_block",
                "fvg",
                "pullback",
                "ob",
            ):
                data["type"] = "limit"
            elif raw_type in ("trigger", "stop", "stop_order", "breakout"):
                data["type"] = "trigger"
            elif not raw_type:
                data["type"] = "market"
        return data


class ReevaluationTrigger(BaseModel):
    type: Literal["price_level", "indicator", "time", "news"]
    detail: str = Field(..., description="Specific trigger condition.")
    price: Optional[float] = Field(None, description="Required if type is 'price_level'. The target price.")
    direction: Optional[Literal["above", "below"]] = Field(None, description="Required if type is 'price_level'.")
    symbol: Optional[str] = Field(
        None, description="Optional. The symbol this trigger applies to. Defaults to current asset."
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_reevaluation_trigger(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
            from monika.application.agent.harness.tool_repair import _parse_xml_parameters

            xml_dict = _parse_xml_parameters(s)
            if xml_dict:
                data = xml_dict
                if "detail" not in data or not data.get("detail"):
                    data["detail"] = s
            else:
                data = {"type": "time", "detail": s}
        if isinstance(data, dict):
            if "detail" not in data or not data.get("detail"):
                data["detail"] = str(data.get("price") or data.get("type") or "Re-evaluate")
            raw_t = str(data.get("type", "")).strip().lower()
            if raw_t in ("price", "level", "price_level", "price_action", "sl", "tp"):
                data["type"] = "price_level"
            elif raw_t in ("time", "date", "timer", "schedule", "review", "periodic"):
                data["type"] = "time"
            elif raw_t in ("indicator", "rsi", "adx", "ema", "fvg", "ob", "structure"):
                data["type"] = "indicator"
            elif raw_t in ("news", "event", "nfp", "cpi", "fomc", "catalyst"):
                data["type"] = "news"
            elif not raw_t:
                data["type"] = "time"

            if "direction" in data and data["direction"]:
                dir_raw = str(data["direction"]).strip().lower()
                data["direction"] = (
                    dir_raw
                    if dir_raw in ("above", "below")
                    else ("above" if "above" in dir_raw else ("below" if "below" in dir_raw else None))
                )
            if "price" in data and data["price"] is not None:
                data["price"] = coerce_float(data["price"])
        return data

    @model_validator(mode="after")
    def validate_and_extract_price_level(self) -> "ReevaluationTrigger":
        if self.type == "price_level":
            import re

            if (self.price is None or not self.direction) and self.detail:
                text = self.detail.lower()
                above_m = re.search(r"(?:above|break[s]?\s+above|over|reache[s]?|hit[s]?)\s+([\d,]+(?:\.\d+)?)", text)
                below_m = re.search(r"(?:below|break[s]?\s+below|under|drop[s]?\s+to)\s+([\d,]+(?:\.\d+)?)", text)

                if above_m and not self.price:
                    try:
                        self.price = float(above_m.group(1).replace(",", ""))
                        self.direction = "above"
                    except ValueError:
                        pass
                elif below_m and not self.price:
                    try:
                        self.price = float(below_m.group(1).replace(",", ""))
                        self.direction = "below"
                    except ValueError:
                        pass

            # If price or direction is still missing after extraction, fallback to type='time'
            if self.price is None or not self.direction:
                self.type = "time"

        return self


class PricedInOverrideJustification(BaseModel):
    override_reason: str
    why_stage1_wrong: str
    post_event_evidence: str

    @model_validator(mode="before")
    @classmethod
    def coerce_override_justification(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
            if len(s) < 15:
                raise ValueError("Priced-in override justification string is too short/trivial (<15 chars)")
            return {
                "override_reason": s,
                "why_stage1_wrong": f"Stage 1 analysis superseded: {s}",
                "post_event_evidence": f"Substantive market evidence: {s}",
            }
        if isinstance(data, dict):
            reason = coerce_str(
                data.get("override_reason")
                or data.get("reason")
                or data.get("justification")
                or data.get("override_justification")
                or data.get("detail")
                or data.get("explanation")
                or data.get("rationale")
                or data.get("override")
                or data.get("notes")
                or data.get("comment")
                or data.get("why_stage1_wrong")
                or data.get("post_event_evidence")
            )
            why_wrong = coerce_str(data.get("why_stage1_wrong"))
            evidence = coerce_str(data.get("post_event_evidence"))
            if not reason:
                raise ValueError("Priced-in override missing required 'override_reason'")
            data["override_reason"] = reason
            data["why_stage1_wrong"] = why_wrong or f"Stage 1 thesis reassessed: {reason}"
            data["post_event_evidence"] = evidence or f"New price action/volume confirmation: {reason}"
        return data


import re


class UpcomingRiskEvent(BaseModel):
    event: str
    time: str
    expected_impact: Literal["high", "medium", "low"]

    @model_validator(mode="before")
    @classmethod
    def coerce_risk_event(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
            impact = "medium"
            if "high" in s.lower():
                impact = "high"
            elif "low" in s.lower():
                impact = "low"
            return {"event": s, "time": "upcoming", "expected_impact": impact}
        if isinstance(data, dict):
            if not data.get("event"):
                data["event"] = coerce_str(
                    data.get("name") or data.get("event_name") or data.get("title") or "Upcoming Event"
                )
            if not data.get("time"):
                data["time"] = coerce_str(data.get("event_time") or data.get("date") or "upcoming")
            impact_raw = (
                str(data.get("expected_impact") or data.get("impact") or data.get("severity") or "medium")
                .strip()
                .lower()
            )
            data["expected_impact"] = (
                impact_raw
                if impact_raw in ("high", "medium", "low")
                else ("high" if "high" in impact_raw else ("low" if "low" in impact_raw else "medium"))
            )
        return data


class PricedInAssessment(BaseModel):
    dominant_driver: str = Field(
        ...,
        description="The main driver/narrative currently being priced in by the market (e.g., 'Fed rate cut expectations for Dec FOMC meeting').",
    )
    priced_in_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="Composite priced-in score (1-10). Sum of scores from FedWatch (0-3), COT extreme (0-3), price run-up (0-3), news saturation (0-2). 1=nothing priced in, 10=fully priced in.",
    )
    sell_the_news_risk: Literal["high", "medium", "low", "not_applicable"] = Field(
        ..., description="Risk of counter-trend 'sell the news' reaction if expected event materializes as expected."
    )
    key_unpriced_drivers: Optional[List[str]] = Field(
        None, description="Drivers that are NOT yet priced in and could cause surprise moves (upside or downside)."
    )
    cot_positioning_percentile: Optional[float] = Field(
        None,
        description="Nilai persentil numerik COT (0-100) dari get_cot_report atau macro_priced_in_baseline. WAJIB diisi pada hari kerja jika tidak ada retail_sentiment_percentile.",
    )
    retail_sentiment_percentile: Optional[float] = Field(
        None,
        description="Nilai sentimen retail numerik (0-100) dari get_retail_sentiment jika ada. WAJIB diisi pada hari kerja jika tidak ada cot_positioning_percentile.",
    )
    fedwatch_shift_summary: Optional[str] = Field(
        None,
        description="Ringkasan pergeseran ekspektasi FedWatch sebelum vs sesudah rilis data atau 24h shift (mis. 'Hike odds 37.1% vs 45.0% pre-event (-7.9%)')",
    )

    @field_validator("sell_the_news_risk", mode="before")
    @classmethod
    def validate_sell_the_news_risk(cls, v):
        if not v:
            return "not_applicable"
        s = str(v).strip().lower()
        if s in ("high", "medium", "low", "not_applicable"):
            return s
        if s in ("n/a", "na", "none", "not applicable", "not-applicable", "no"):
            return "not_applicable"
        if "high" in s:
            return "high"
        if "low" in s:
            return "low"
        if "med" in s:
            return "medium"
        return "not_applicable"

    @field_validator("key_unpriced_drivers", mode="before")
    @classmethod
    def validate_unpriced_drivers(cls, v):
        return coerce_string_list(v)

    @field_validator("dominant_driver", mode="before")
    @classmethod
    def validate_dominant_driver(cls, v):
        return coerce_str(v, default="Macro drivers")

    @field_validator("priced_in_score", mode="before")
    @classmethod
    def validate_priced_in_score(cls, v):
        res = coerce_int(v)
        if res is None:
            raise ValueError(f"priced_in_score must be a valid integer, got '{v}'")
        return max(1, min(10, res))

    @field_validator("cot_positioning_percentile", "retail_sentiment_percentile", mode="before")
    @classmethod
    def validate_percentiles(cls, v):
        return coerce_float(v)


# =============================================================================
# Tool Input Schemas
# =============================================================================


class ChecklistVerification(BaseModel):
    bias_vs_narrative_match: bool = Field(
        default=True, description="True if the currency bias aligns with the narrative."
    )
    contradiction_existed: bool = Field(default=False, description="True if a contradiction was found and resolved.")

    @field_validator("bias_vs_narrative_match", "contradiction_existed", mode="before")
    @classmethod
    def coerce_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "t")
        return bool(v)


class KeyDataPointsUsed(BaseModel):
    dxy_trend_5d: str = Field(
        default="strengthening",
        description="e.g. 'strengthening +0.8%' or 'weakening -0.4%', persis seperti dibaca dari get_dxy()",
    )
    vix_close: float = Field(default=16.7, description="Nilai VIX close terbaru, persis seperti dibaca dari get_vix()")
    fedwatch_dominant_pct: Optional[float] = Field(
        None, description="Probabilitas dominan FedWatch jika ada meeting dalam window analisis"
    )
    fedwatch_repricing_delta_pct: Optional[float] = Field(
        None,
        description="Pergeseran probabilitas dominan FedWatch (%) sebelum vs sesudah rilis data USD terkini atau pergeseran 24 jam",
    )
    treasury_10y_yield_pct: Optional[float] = Field(
        None, description="Nilai yield 10Y terbaru (%), persis seperti dibaca dari get_treasury_yields()"
    )
    cot_leveraged_long_pct: Optional[float] = Field(
        None,
        description="Persentase leveraged funds net-long terbaru untuk driver COT utama yang dikutip di narasi, persis seperti dibaca dari get_cot_report()/get_precomputed_cot_signals()",
    )

    @field_validator("vix_close", mode="before")
    @classmethod
    def validate_vix_close(cls, v):
        res = coerce_float(v)
        if res is None:
            return 16.7
        return res

    @field_validator(
        "fedwatch_dominant_pct",
        "fedwatch_repricing_delta_pct",
        "treasury_10y_yield_pct",
        "cot_leveraged_long_pct",
        mode="before",
    )
    @classmethod
    def validate_optional_pcts(cls, v):
        return coerce_float(v)


class AssetMacroContext(BaseModel):
    directional_bias: Literal["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"] = Field(
        ..., description="Directional bias spesifik untuk aset ini."
    )
    time_horizon: Literal["intraday_tactical", "swing_structural", "multi_week"] = Field(
        default="swing_structural", description="Horizon waktu dominan tesis."
    )
    structural_driver: str = Field(
        ..., description="Pendorong struktural utama (mis. diferensial yield, de-dollarization, OPEC quota)."
    )
    tactical_catalyst: str = Field(
        ..., description="Katalis jangka pendek sesi ini (mis. reaksi post-NFP, inventory EIA, data PPI)."
    )
    net_yield_differential_bps: Optional[float] = Field(
        default=None, description="Estimasi diferensial spread imbal hasil (bps) jika relevan."
    )
    invalidation_level: str = Field(
        ..., description="Level harga atau peristiwa spesifik yang membatalkan bias pada aset ini (min 20 char)."
    )
    confidence: float = Field(
        default=0.70, ge=0.0, le=1.0, description="Tingkat keyakinan bias pada aset ini (0.0 - 1.0)."
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_asset_confidence(cls, v):
        val = coerce_float(v, None)
        if val is not None:
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        return 0.70

    @field_validator("directional_bias", mode="before")
    @classmethod
    def validate_asset_bias(cls, v):
        if isinstance(v, str):
            b_clean = v.lower().strip().replace("-", "_").replace(" ", "_")
            if b_clean in ["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]:
                return b_clean
            if "bull" in b_clean:
                return "bullish"
            if "bear" in b_clean:
                return "bearish"
        return "neutral"

    @field_validator("structural_driver", "tactical_catalyst", "invalidation_level", mode="before")
    @classmethod
    def coerce_context_strings(cls, v):
        return coerce_str(v, default="Not specified")
