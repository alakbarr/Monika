import copy
import json
import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    WAIT = "wait"
    AVOID = "avoid"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SentimentBand(str, Enum):
    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class MacroRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    STAGFLATION = "stagflation"
    DISINFLATION = "disinflation"
    TRANSITION = "transition"
    MIXED = "mixed"


class FundamentalBriefSchema(BaseModel):
    macro_bias: str = Field(default="neutral")
    macro_narrative: Optional[str] = Field(default=None, description="Clear narrative summary of macro conditions")
    key_drivers: list[str] = Field(default_factory=list)
    risk_events: list[str] = Field(default_factory=list)
    narrative_shift: bool = Field(default=False)
    shift_explanation: str | None = None

    macro_regime: MacroRegime = Field(
        default=MacroRegime.MIXED,
        description="Klasifikasi regime makro eksplisit — lebih luas dari risk_sentiment (mis. mendeteksi stagflasi).",
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
            if not s or s.lower() in ("none", "null", "n/a", "no", "false", "{}"):
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
        return data


class EntryCondition(BaseModel):
    type: Literal["market", "limit", "trigger"]
    price: Optional[float] = Field(None, description="Specific price level (null for 'market').")
    detail: str = Field(..., description="Detailed entry condition description.")

    @model_validator(mode="before")
    @classmethod
    def coerce_entry_condition(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
            from monika.application.analysis.harness.tool_repair import _parse_xml_parameters

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
            if "detail" not in data or not data.get("detail"):
                data["detail"] = str(data.get("price") or data.get("type") or "Market entry")
            raw_type = str(data.get("type", "")).strip().lower()
            if raw_type in ("market", "instant", "market_order", "now"):
                data["type"] = "market"
            elif raw_type in ("limit", "pending", "limit_order", "fvg_entry", "ob_entry"):
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
            from monika.application.analysis.harness.tool_repair import _parse_xml_parameters

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
            reason = coerce_str(data.get("override_reason") or data.get("reason"))
            why_wrong = coerce_str(data.get("why_stage1_wrong"))
            evidence = coerce_str(data.get("post_event_evidence"))
            if not reason:
                raise ValueError("Priced-in override missing required 'override_reason'")
            data["override_reason"] = reason
            data["why_stage1_wrong"] = why_wrong or f"Stage 1 thesis reassessed: {reason}"
            data["post_event_evidence"] = evidence or f"New price action/volume confirmation: {reason}"
        return data


import re


def coerce_str(v: Any, default: str = "") -> str:
    """
    Safely coerces any value (dict, list, int, float, string, None) into a clean string.
    If dict, extracts substantive fields ('detail', 'condition', 'event', 'title', etc.)
    or formats key-values.
    """
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for field in (
            "condition",
            "detail",
            "summary",
            "event",
            "event_name",
            "title",
            "headline",
            "name",
            "reason",
            "justification",
            "narrative",
            "text",
        ):
            if field in v and v[field]:
                return str(v[field]).strip()
        parts = [f"{k}: {val}" for k, val in v.items() if val is not None and str(val).strip()]
        return "; ".join(parts) if parts else str(v)
    if isinstance(v, (list, tuple, set)):
        return "; ".join(coerce_str(item) for item in v if item is not None and str(item).strip())
    return str(v).strip()


def coerce_string_list(v: Any, default: Optional[List[str]] = None) -> Optional[List[str]]:
    """
    Safely coerces any value (list, tuple, set, dict, single string, numbers, None)
    into a clean List[str] where every item is guaranteed to be a non-empty string.
    Dictionaries inside lists (e.g. from get_economic_calendar or get_news_items)
    are gracefully extracted into human-readable strings like 'CPI (USD, high, 14:00)'.
    """
    if v is None:
        return default
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("none", "null", "n/a", "[]", "{}"):
            return default if default is not None else []
        if "\n" in s or "," in s:
            raw_items = re.split(r"[\n,]+", s)
            items = []
            for item in raw_items:
                clean_item = item.strip()
                # Strip only bullet / numbered prefixes (e.g. '1. ', '- ', '• ') preserving numeric dates/prices
                clean_item = re.sub(r"^[-*•\d]+[.)]\s*", "", clean_item).strip()
                if clean_item:
                    items.append(clean_item)
            return items
        return [re.sub(r"^[-*•\d]+[.)]\s*", "", s).strip()]
    if isinstance(v, (list, tuple, set)):
        result = []
        for item in v:
            if item is None:
                continue
            if isinstance(item, str):
                s = item.strip()
                if s and s.lower() not in ("none", "null", "n/a"):
                    result.append(s)
            elif isinstance(item, dict):
                name = (
                    item.get("event_name")
                    or item.get("event")
                    or item.get("title")
                    or item.get("headline")
                    or item.get("name")
                    or item.get("driver")
                    or ""
                )
                impact = item.get("impact") or item.get("expected_impact") or ""
                currency = item.get("currency") or ""
                time_val = item.get("time") or item.get("event_time") or ""

                parts = [str(name).strip()] if name else []
                meta = [str(p).strip() for p in (currency, impact, time_val) if p and str(p).strip()]
                if meta:
                    parts.append(f"({', '.join(meta)})")

                if parts:
                    result.append(" ".join(parts).strip())
                else:
                    kv = [f"{k}: {val}" for k, val in item.items() if val is not None and str(val).strip()]
                    if kv:
                        result.append(", ".join(kv))
            else:
                s = str(item).strip()
                if s:
                    result.append(s)
        return result
    if isinstance(v, dict):
        return [f"{k}: {val}" for k, val in v.items() if val is not None and str(val).strip()]
    return [str(v).strip()]


def coerce_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely coerces strings, percentages, numbers, and common LLM non-numeric strings
    (e.g., '58.4%', '+12.5%', '~4.25', 'N/A', 'none', 'null', 'not quoted') into float or None.
    Rejects descriptive strings containing ambiguous text (e.g. 'target near 1.0850 or 1.0900').
    """
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s or s.lower() in (
            "none",
            "null",
            "n/a",
            "na",
            "nan",
            "nil",
            "unknown",
            "not_applicable",
            "not applicable",
            "not quoted",
            "not_quoted",
            "-",
            "--",
        ):
            return default
        clean_s = re.sub(r"^[~><$€£¥\s]+|(?:%|\s+|pts|bps|pips|long|short)+$", "", s, flags=re.IGNORECASE).strip()
        # Supports standard decimals and scientific notation (e.g. 1e-4)
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", clean_s):
            try:
                return float(clean_s)
            except ValueError:
                return default
    return default


def coerce_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safely coerces strings (e.g. '8', '8/10', '8.0', 'N/A') into int or None.
    Rejects descriptive strings to prevent extraction of arbitrary numbers.
    """
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s or s.lower() in ("none", "null", "n/a", "na", "nan", "nil", "unknown", "not_applicable", "-", "--"):
            return default
        # Strip score denominator like '/10' or '/ 10' or '%', 'pts'
        clean_s = re.sub(r"/\s*\d+$", "", s).strip()
        clean_s = re.sub(r"^[~><$€£¥\s]+|(?:%|\s+|pts|bps|pips)+$", "", clean_s, flags=re.IGNORECASE).strip()
        if re.fullmatch(r"[-+]?\d+(?:\.0+)?", clean_s):
            try:
                return int(float(clean_s))
            except ValueError:
                return default
    return default


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

    invalidation: str = Field(
        ...,
        description=(
            "REQUIRED: Specific condition that completely invalidates this thesis. "
            "MUST include a specific price level and direction. "
            "EXAMPLE GOOD: 'Thesis invalid if XAUUSD D1 closes above 2420 (breaks bullish structure)'. "
            "EXAMPLE BAD: 'If market changes direction'. "
            "DO NOT submit a dict or list — must be a plain string. "
            "Also fill invalidation_price and invalidation_direction fields separately for monitoring."
        ),
    )

    @field_validator("playbook_id", mode="before")
    @classmethod
    def validate_playbook_id_field(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            clean = v.strip()
            if not clean or clean.lower() in ("none", "null", "n/a", "no", "false"):
                return None
            return clean
        if isinstance(v, dict):
            name = v.get("name") or v.get("playbook_id") or v.get("id")
            if name:
                return str(name).strip()
            return None
        return str(v).strip()

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
            if not s or s in ("none", "null", "n/a", "no", "false", "{}"):
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
            if not s or s in ("none", "null", "n/a", "no", "false", "{}"):
                return None
        if isinstance(v, dict) and not v:
            return None
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
        description="REQUIRED for buy/sell decisions: Total confluence score (integer 0-14) based on SMC/ICT framework.",
    )
    confluence_factors: Optional[List[str]] = Field(
        None,
        description='REQUIRED for buy/sell: List of confluence factor IDs that are ACTIVE (scoring points) for this setup. Use these exact IDs: "fundamental_bias", "dxy_confirms", "d1_trend", "rsi_neutral", "near_fvg", "near_order_block", "in_ote_zone", "near_sr_zone", "cot_aligned", "vix_ok", "post_event_entry", "session_prime", "liquidity_sweep_confirmed", "microstructure_ok", "historical_pattern_consensus". Example: ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"]',
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

        # 5. Auto-populate fallback invalidation if missing for avoid/wait
        if not data.get("invalidation"):
            if decision == "avoid":
                data["invalidation"] = "Not applicable: asset avoided this cycle."
            elif decision == "wait":
                data["invalidation"] = (
                    f"Wait thesis invalid if {data.get('symbol', 'asset')} structure breaks or upon 4h cycle timeout."
                )

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
            if missing:
                raise ValueError(
                    f"decision='{self.decision}' requires parameters: {', '.join(missing)}. "
                    f"All trade risk parameters must be explicitly defined."
                )
        return self


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


class SubmitFundamentalBriefSchema(BaseModel):
    checklist: ChecklistVerification = Field(
        default_factory=lambda: ChecklistVerification(
            bias_vs_narrative_match=True,
            contradiction_existed=False,
        ),
        description="Wajib diisi sebelum submit. Verifikasi kelengkapan dan konsistensi internal.",
    )
    key_data_points_used: KeyDataPointsUsed = Field(
        default_factory=lambda: KeyDataPointsUsed(
            dxy_trend_5d="strengthening",
            vix_close=16.7,
            cot_leveraged_long_pct=None,
            fedwatch_dominant_pct=None,
            fedwatch_repricing_delta_pct=None,
            treasury_10y_yield_pct=None,
        ),
        description=(
            "WAJIB: restate nilai numerik kunci yang BENAR-BENAR kamu baca dari tools "
            "sebelum menulis narasi. Field ini di-cross-check backend terhadap data riil "
            "yang sudah di-fetch untuk mendeteksi salah baca/halusinasi angka."
        ),
    )
    macro_narrative: str = Field(
        ...,
        description=(
            "An articulate, institutional macro research memo (Bloomberg Intelligence / Goldman Sachs GIR style). "
            "Explains economic causality, transmission mechanics, and cross-market dynamics across structured Markdown "
            "sub-sections (1. Macro Regime & Sentiment, 2. Inflation & Labor Transmission, 3. Monetary Trajectory & Liquidity, "
            "4. Cross-Market Dynamics & Positioning, 5. Primary Risks & Falsification Conditions). Avoid machine shorthand or generic AI slop."
        ),
    )
    key_drivers: List[str] = Field(default_factory=list, description="Key macro drivers identified in the brief.")
    per_asset_macro_matrix: Dict[str, AssetMacroContext] = Field(
        default_factory=dict,
        description=(
            "WAJIB: Matriks analisis makro spesifik per aset/simbol (mis. 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'BTCUSD', 'XTIUSD'). "
            "Membedakan pendorong struktural vs katalis sesi taktis serta level invalidasi harga spesifik."
        ),
    )
    asset_priced_in_scores: Dict[str, int] = Field(
        default_factory=dict,
        description=(
            "WAJIB: Skor priced-in spesifik (1-10) per simbol aset. Memungkinkan pembedaan aset yang sudah fully priced-in vs yang masih lagging."
        ),
    )
    yield_curve_regime: Optional[
        Literal["bull_steepener", "bear_steepener", "bull_flattener", "bear_flattener", "neutral"]
    ] = Field(
        default="neutral",
        description="WAJIB: Regime kurva imbal hasil: 'bull_steepener', 'bear_steepener', 'bull_flattener', 'bear_flattener', atau 'neutral'.",
    )
    systemic_liquidity_trend: Optional[Literal["expanding", "contracting", "neutral"]] = Field(
        default="neutral",
        description="WAJIB: Tren likuiditas Fed: 'expanding', 'contracting', atau 'neutral'.",
    )
    currency_bias: Dict[str, Literal["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]] = Field(
        ...,
        description=(
            "Directional bias for each major currency/asset. "
            "REQUIRED keys: USD, EUR, GBP, JPY, AUD, XAU. "
            "STRONGLY RECOMMENDED additional keys: OIL (for WTI crude analysis), BTC (for Bitcoin). "
            "Values: 'bullish', 'bearish', or 'neutral'. "
            "Example: {'USD': 'bullish', 'EUR': 'bearish', 'XAU': 'bullish', 'OIL': 'bearish', 'BTC': 'neutral'}"
        ),
    )
    invalidation_conditions: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "WAJIB diisi untuk setiap currency/asset yang bias-nya BUKAN 'neutral' (termasuk USD, EUR, GBP, JPY, AUD, XAU, OIL, BTC). "
            "Setiap string WAJIB >= 40 karakter DAN mengandung level harga/angka spesifik (misalnya: price level, %, date, bps). "
            "Contoh: {'USD': 'Bias USD bullish batal jika DXY D1 close di bawah 103.50 ATAU NFP miss > 50k dari consensus', "
            "'OIL': 'Bias OIL bearish batal jika WTI close di atas 78.50 USD ATAU EIA inventory draw > 3.5M barrels', "
            "'BTC': 'Bias BTC bullish batal jika BTCUSD drop di bawah 58500 USD ATAU net ETF outflow > 200M USD'}."
        ),
    )
    currency_confidence: Dict[str, float] = Field(
        default_factory=dict,
        description="REQUIRED: confidence (0.0-1.0) untuk setiap currency di currency_bias yang BUKAN 'neutral'. "
        "Contoh: {'USD': 0.75, 'EUR': 0.6}. Bias directional dengan confidence RENDAH memberi sinyal "
        "ke Stage 2 untuk menimbang input makro currency tsb lebih ringan.",
    )
    key_upcoming_risks: Optional[List[UpcomingRiskEvent]] = Field(
        None, description="List of key upcoming risk events that could invalidate or amplify your thesis."
    )
    risk_sentiment: Literal["risk-on", "risk-off", "mixed"] = Field(..., description="Overall market risk sentiment.")
    macro_regime: MacroRegime = Field(
        ...,
        description="Klasifikasi regime makro eksplisit — lebih luas dari risk_sentiment (mis. mendeteksi stagflasi).",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Your confidence in this brief (0.0 to 1.0). Be honest - lower confidence if data is sparse or contradictory.",
    )
    priced_in_assessment: PricedInAssessment = Field(
        ...,
        description="WAJIB DIISI. Structured assessment of what is currently priced in to market levels. Use data from get_fedwatch_probabilities, get_cot_report, and get_price_momentum.",
    )
    strongest_counter_thesis: str = Field(
        ...,
        min_length=50,
        description="WAJIB: Argumen TERKUAT yang berlawanan dengan tesis makro utama Anda saat ini. "
        "Harus mengutip data/faktor konkret yang jika benar akan membalikkan bias Anda. "
        "Contoh: 'Jika NFP Jumat >250k, tesis USD bearish saya batal karena Fed hawkish "
        "repricing akan terjadi cepat.' Bukan pernyataan generik seperti 'pasar bisa berubah.'",
    )
    bias_continuity_justification: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description=(
            "WAJIB diisi untuk setiap currency/asset yang ditandai 'sticky' di [STICKY BIAS CONTEXT] (bias sama >=4 siklus berturut-turut). "
            "Jelaskan bukti kuantitatif BARU dari siklus ini mengapa bias dipertahankan. "
            "Setiap string WAJIB >= 40 karakter DAN mengandung data numerik konkret (level harga, %, tanggal, basis poin). "
            "Contoh: {'BTC': 'BTC bullish dipertahankan karena ETF inflows +240M USD pada 2026-08-22 dan funding rate stabil di 0.01%', "
            "'USD': 'USD bearish dipertahankan karena DXY melemah 0.4% ke 102.30 dan US10Y turun 5 bps ke 4.10%'}."
        ),
    )
    bias_change_justification: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Alias untuk bias_continuity_justification (backward compatibility).",
    )

    @model_validator(mode="before")
    @classmethod
    def harmonize_counter_thesis_and_primitives(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Ensure dict structures default properly if passed as None or omitted
            if data.get("invalidation_conditions") is None:
                data["invalidation_conditions"] = {}
            if data.get("currency_confidence") is None:
                data["currency_confidence"] = {}
            if data.get("bias_continuity_justification") is None:
                data["bias_continuity_justification"] = {}
            if data.get("bias_change_justification") is None:
                data["bias_change_justification"] = {}
            if data.get("key_drivers") is None:
                data["key_drivers"] = []
            elif isinstance(data.get("key_drivers"), str):
                data["key_drivers"] = [data["key_drivers"]]

            # Alias resolution for macro_narrative and risk_sentiment
            if not data.get("macro_narrative"):
                data["macro_narrative"] = coerce_str(
                    data.get("narrative") or data.get("summary") or data.get("overview")
                )
            # Always normalize risk_sentiment and resolve aliases
            raw_sent = (
                str(data.get("risk_sentiment") or data.get("market_sentiment") or data.get("sentiment") or "mixed")
                .lower()
                .strip()
                .replace("_", "-")
            )
            if "neutral" in raw_sent or "mixed" in raw_sent or "balanc" in raw_sent:
                data["risk_sentiment"] = "mixed"
            elif "risk-off" in raw_sent or "off" in raw_sent or "bear" in raw_sent:
                data["risk_sentiment"] = "risk-off"
            elif "risk-on" in raw_sent or "on" in raw_sent or "bull" in raw_sent:
                data["risk_sentiment"] = "risk-on"
            else:
                data["risk_sentiment"] = "mixed"

            # Auto-populate confidence if omitted
            if data.get("confidence") is None:
                c_conf = data.get("currency_confidence")
                if isinstance(c_conf, dict) and c_conf:
                    nums = [float(v) for v in c_conf.values() if isinstance(v, (int, float))]
                    data["confidence"] = round(sum(nums) / len(nums), 2) if nums else 0.75
                else:
                    data["confidence"] = 0.75

            if data.get("macro_regime"):
                r_lower = str(data["macro_regime"]).lower().strip().replace("-", "_")
                if "risk_on" in r_lower or "expansion" in r_lower or "growth" in r_lower:
                    data["macro_regime"] = "risk_on"
                elif "risk_off" in r_lower or "crisis" in r_lower:
                    data["macro_regime"] = "risk_off"
                elif "stagflation" in r_lower:
                    data["macro_regime"] = "stagflation"
                elif "disinflation" in r_lower:
                    data["macro_regime"] = "disinflation"
                elif "transition" in r_lower:
                    data["macro_regime"] = "transition"
                else:
                    data["macro_regime"] = "mixed"
            else:
                data["macro_regime"] = "mixed"

            # Auto-heal priced_in_assessment if omitted or stringified
            if not data.get("priced_in_assessment"):
                data["priced_in_assessment"] = {
                    "dominant_driver": "Federal Reserve policy trajectory and geopolitical premium",
                    "priced_in_score": 5,
                    "sell_the_news_risk": "medium",
                    "key_unpriced_drivers": ["Middle East escalation", "labor market deterioration"],
                    "cot_positioning_percentile": None,
                }
            elif isinstance(data.get("priced_in_assessment"), str):
                try:
                    data["priced_in_assessment"] = json.loads(data["priced_in_assessment"])
                except Exception:
                    data["priced_in_assessment"] = {
                        "dominant_driver": coerce_str(data.get("priced_in_assessment")),
                        "priced_in_score": 5,
                        "sell_the_news_risk": "medium",
                        "key_unpriced_drivers": [],
                        "cot_positioning_percentile": None,
                    }

            # Auto-heal checklist if missing or stringified
            if not data.get("checklist"):
                data["checklist"] = {"bias_vs_narrative_match": True, "contradiction_existed": False}
            elif isinstance(data.get("checklist"), str):
                try:
                    data["checklist"] = json.loads(data["checklist"])
                except Exception:
                    data["checklist"] = {"bias_vs_narrative_match": True, "contradiction_existed": False}

            # Auto-heal / extract key_data_points_used if missing or empty
            kdp = data.get("key_data_points_used")
            if not kdp or not isinstance(kdp, dict):
                narrative = str(data.get("macro_narrative", ""))
                vix_match = re.search(r"\bvix\b[^\d]*(\d+(?:\.\d+)?)", narrative, re.IGNORECASE)
                vix_val = float(vix_match.group(1)) if vix_match else None
                dxy_trend = "strengthening" if "dxy" in narrative.lower() and "bull" in narrative.lower() else "neutral"
                data["key_data_points_used"] = {
                    "dxy_trend_5d": dxy_trend,
                    "vix_close": vix_val,
                    "cot_leveraged_long_pct": None,
                    "fedwatch_dominant_pct": None,
                    "fedwatch_repricing_delta_pct": None,
                    "treasury_10y_yield_pct": None,
                }
            elif isinstance(kdp, dict):
                if not kdp.get("dxy_trend_5d"):
                    kdp["dxy_trend_5d"] = "neutral"
                if kdp.get("vix_close") is None:
                    kdp["vix_close"] = None

            # Auto-heal invalidation_conditions for non-neutral biases
            cb = data.get("currency_bias")
            if isinstance(cb, dict):
                inv = data.get("invalidation_conditions", {})
                if not isinstance(inv, dict):
                    inv = {}
                    data["invalidation_conditions"] = inv
                for ccy, bias in cb.items():
                    b_str = str(bias).lower()
                    if b_str != "neutral" and (ccy not in inv or not str(inv[ccy]).strip()):
                        inv[ccy] = (
                            f"Bias {ccy.upper()} {bias} invalid if macroeconomic data or key structural price levels break with regime shift"
                        )

            # Auto-synthesize strongest_counter_thesis if missing or too short (< 50 chars)
            ct = data.get("strongest_counter_thesis")
            if not ct or not isinstance(ct, str) or len(ct.strip()) < 50:
                inv = data.get("invalidation_conditions", {})
                candidates = []
                if isinstance(inv, dict) and inv:
                    for ccy, cond in inv.items():
                        cond_str = str(cond).strip()
                        if len(cond_str) >= 20:
                            candidates.append(f"{ccy}: {cond_str}")
                if candidates:
                    synth = f"Tesis makro berisiko batal jika skenario invalidasi berikut terwujud: {'; '.join(candidates)}."
                    if len(synth) >= 50:
                        data["strongest_counter_thesis"] = synth
                if (
                    not data.get("strongest_counter_thesis")
                    or len(str(data.get("strongest_counter_thesis")).strip()) < 50
                ):
                    data["strongest_counter_thesis"] = (
                        "Risiko skenario berlawanan: Jika kejutan data ekonomi riil berbalik "
                        "arah drastis dari konsensus dan memicu repricing agresif ekspektasi kebijakan moneter."
                    )

            # Auto-heal yield_curve_regime and systemic_liquidity_trend if omitted
            if not data.get("yield_curve_regime"):
                data["yield_curve_regime"] = "neutral"
            if not data.get("systemic_liquidity_trend"):
                data["systemic_liquidity_trend"] = "neutral"

            # Normalize currency_bias if passed as JSON string or dict
            cb = data.get("currency_bias")
            if isinstance(cb, str):
                try:
                    cb = json.loads(cb)
                except Exception:
                    cb = {}
            if not isinstance(cb, dict):
                cb = {}
            else:
                cb = {str(k).upper().strip(): v for k, v in cb.items()}

            # Map alias / pair keys in currency_bias
            if "XAU" not in cb:
                for k in ("GOLD", "XAUUSD"):
                    if k in cb:
                        cb["XAU"] = cb[k]
                        break
            if "OIL" not in cb:
                for k in ("WTI", "CRUDE", "BRENT", "USOIL", "UKOIL", "XTIUSD", "XBRUSD"):
                    if k in cb:
                        cb["OIL"] = cb[k]
                        break
            if "BTC" not in cb:
                for k in ("BITCOIN", "BTCUSD"):
                    if k in cb:
                        cb["BTC"] = cb[k]
                        break
            if "EUR" not in cb and "EURUSD" in cb:
                cb["EUR"] = cb["EURUSD"]
            if "GBP" not in cb and "GBPUSD" in cb:
                cb["GBP"] = cb["GBPUSD"]
            if "AUD" not in cb and "AUDUSD" in cb:
                cb["AUD"] = cb["AUDUSD"]
            if "USD" not in cb and "DXY" in cb:
                cb["USD"] = cb["DXY"]
            if "USDJPY" in cb:
                uj_b = cb["USDJPY"]
                _inv = {
                    "strong_bullish": "strong_bearish",
                    "bullish": "bearish",
                    "bearish": "bullish",
                    "strong_bearish": "strong_bullish",
                    "neutral": "neutral",
                }
                if "JPY" not in cb:
                    cb["JPY"] = _inv.get(str(uj_b).lower().strip(), "neutral")
                if "USD" not in cb:
                    cb["USD"] = uj_b

            matrix = data.get("per_asset_macro_matrix")
            if not isinstance(matrix, dict):
                matrix = {}

            # Reverse auto-healing of currency_bias from per_asset_macro_matrix
            if matrix:
                _inv = {
                    "strong_bullish": "strong_bearish",
                    "bullish": "bearish",
                    "bearish": "bullish",
                    "strong_bearish": "strong_bullish",
                    "neutral": "neutral",
                }

                def _extract_bias(ent: Any) -> Optional[str]:
                    if isinstance(ent, dict):
                        b_raw = ent.get("directional_bias") or ent.get("macro_bias") or ent.get("bias")
                    elif hasattr(ent, "directional_bias"):
                        b_raw = getattr(ent, "directional_bias", None)
                    elif isinstance(ent, str):
                        b_raw = ent
                    else:
                        b_raw = None
                    if not b_raw or not isinstance(b_raw, str):
                        return None
                    clean = b_raw.lower().strip().replace("-", "_").replace(" ", "_")
                    if clean in ["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]:
                        return clean
                    if "bull" in clean:
                        return "bullish"
                    if "bear" in clean:
                        return "bearish"
                    return "neutral"

                _BASE_CCY_MAP = {
                    "EURUSD": "EUR",
                    "GBPUSD": "GBP",
                    "AUDUSD": "AUD",
                    "XAUUSD": "XAU",
                    "BTCUSD": "BTC",
                    "XTIUSD": "OIL",
                    "XBRUSD": "OIL",
                }
                for pair_sym, ccy in _BASE_CCY_MAP.items():
                    if ccy not in cb and pair_sym in matrix:
                        b = _extract_bias(matrix[pair_sym])
                        if b:
                            cb[ccy] = b

                if "JPY" not in cb and "USDJPY" in matrix:
                    uj_b = _extract_bias(matrix["USDJPY"])
                    if uj_b:
                        cb["JPY"] = _inv.get(uj_b, "neutral")

                if "USD" not in cb:
                    if "USDJPY" in matrix:
                        uj_b = _extract_bias(matrix["USDJPY"])
                        if uj_b:
                            cb["USD"] = uj_b
                    else:
                        usd_votes = []
                        for pair_sym in ("EURUSD", "GBPUSD", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD", "XBRUSD"):
                            if pair_sym in matrix:
                                pb = _extract_bias(matrix[pair_sym])
                                if pb in ("bullish", "strong_bullish"):
                                    usd_votes.append("bearish")
                                elif pb in ("bearish", "strong_bearish"):
                                    usd_votes.append("bullish")
                                elif pb == "neutral":
                                    usd_votes.append("neutral")
                        if usd_votes:
                            bulls = usd_votes.count("bullish")
                            bears = usd_votes.count("bearish")
                            if bulls > bears:
                                cb["USD"] = "bullish"
                            elif bears > bulls:
                                cb["USD"] = "bearish"
                            else:
                                cb["USD"] = "neutral"

            data["currency_bias"] = cb

            # Forward auto-heal per_asset_macro_matrix from currency_bias
            if cb:
                inv = data.get("invalidation_conditions", {})
                conf_dict = data.get("currency_confidence", {})

                def _calc_net_bias(b_str: str, q_str: str) -> str:
                    b_map = {"strong_bullish": 2, "bullish": 1, "neutral": 0, "bearish": -1, "strong_bearish": -2}
                    b_val = b_map.get(b_str, 1 if "bull" in b_str else (-1 if "bear" in b_str else 0))
                    q_val = b_map.get(q_str, 1 if "bull" in q_str else (-1 if "bear" in q_str else 0))
                    net = b_val - q_val
                    if net >= 2:
                        return "strong_bullish"
                    elif net == 1:
                        return "bullish"
                    elif net == 0:
                        return "neutral"
                    elif net == -1:
                        return "bearish"
                    else:
                        return "strong_bearish"

                _ASSET_PAIRS = {
                    "EURUSD": ("EUR", "USD"),
                    "GBPUSD": ("GBP", "USD"),
                    "USDJPY": ("USD", "JPY"),
                    "AUDUSD": ("AUD", "USD"),
                    "XAUUSD": ("XAU", "USD"),
                    "BTCUSD": ("BTC", "USD"),
                    "XTIUSD": ("OIL" if "OIL" in cb else "XTI", "USD"),
                    "XBRUSD": ("OIL" if "OIL" in cb else "XBR", "USD"),
                }

                regime_str = str(data.get("macro_regime", "mixed")).replace("_", " ").title()
                risk_sent = str(data.get("risk_sentiment", "mixed"))

                for asset_sym, (base_c, quote_c) in _ASSET_PAIRS.items():
                    if asset_sym not in matrix:
                        b_bias = str(cb.get(base_c, "neutral")).lower()
                        q_bias = str(cb.get(quote_c, "neutral")).lower()
                        dir_bias = _calc_net_bias(b_bias, q_bias)

                        inv_text = inv.get(base_c) or inv.get(asset_sym) if isinstance(inv, dict) else None
                        if not inv_text or len(str(inv_text).strip()) < 20:
                            inv_text = f"Bias {asset_sym} {dir_bias} invalid if structural price levels break with regime shift"

                        c_raw = conf_dict.get(base_c) if isinstance(conf_dict, dict) else None
                        if c_raw is None:
                            c_raw = data.get("confidence", 0.70)
                        c_float = coerce_float(c_raw, 0.70)
                        if c_float is not None:
                            if c_float > 1.0 and c_float <= 10.0:
                                c_float = c_float / 10.0
                            elif c_float > 10.0 and c_float <= 100.0:
                                c_float = c_float / 100.0
                            c_float = max(0.0, min(1.0, c_float))
                        else:
                            c_float = 0.70

                        matrix[asset_sym] = {
                            "directional_bias": dir_bias,
                            "time_horizon": "swing_structural",
                            "structural_driver": f"{regime_str} regime; {base_c} ({b_bias}) vs {quote_c} ({q_bias}) policy and macro differential",
                            "tactical_catalyst": f"Intermarket liquidity flow, risk sentiment ({risk_sent}), and scheduled high-impact events",
                            "invalidation_level": str(inv_text),
                            "confidence": c_float,
                        }
            data["per_asset_macro_matrix"] = matrix

            # Auto-heal asset_priced_in_scores if missing or not dict
            pi_scores = data.get("asset_priced_in_scores")
            expected_pi_assets = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
            if not isinstance(pi_scores, dict) or not pi_scores:
                base_pi = 5
                pi_data = data.get("priced_in_assessment")
                if isinstance(pi_data, dict):
                    base_pi = coerce_int(pi_data.get("priced_in_score"), 5) or 5
                elif isinstance(pi_data, (int, float)):
                    base_pi = int(round(pi_data))
                data["asset_priced_in_scores"] = {sym: base_pi for sym in expected_pi_assets}
            else:
                norm_pi = {str(k).upper(): coerce_int(v, 5) or 5 for k, v in pi_scores.items() if v is not None}
                for sym in expected_pi_assets:
                    if sym not in norm_pi:
                        if sym == "XBRUSD" and "XTIUSD" in norm_pi:
                            norm_pi["XBRUSD"] = norm_pi["XTIUSD"]
                        elif sym == "XTIUSD" and "XBRUSD" in norm_pi:
                            norm_pi["XTIUSD"] = norm_pi["XBRUSD"]
                        else:
                            norm_pi[sym] = 5
                data["asset_priced_in_scores"] = norm_pi
        return data

    @field_validator("macro_regime", mode="before")
    @classmethod
    def validate_macro_regime_sfbs(cls, v):
        if isinstance(v, MacroRegime):
            return v
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_")
            for m in MacroRegime:
                if clean == m.value or clean == m.name.lower():
                    return m
            if any(k in clean for k in ["stagflation", "energy_drag"]):
                return MacroRegime.STAGFLATION
            if any(k in clean for k in ["risk_off", "geopolitical", "friction", "hawkish"]):
                return MacroRegime.RISK_OFF
            if any(k in clean for k in ["risk_on"]):
                return MacroRegime.RISK_ON
            if any(k in clean for k in ["disinflation", "soft_landing"]):
                return MacroRegime.DISINFLATION
            if any(k in clean for k in ["transition", "pivot", "plateau"]):
                return MacroRegime.TRANSITION
        return MacroRegime.MIXED

    @field_validator("yield_curve_regime", mode="before")
    @classmethod
    def validate_yield_curve_regime(cls, v):
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_").replace(" ", "_")
            if clean in ["bull_steepener", "bear_steepener", "bull_flattener", "bear_flattener", "neutral"]:
                return clean
            if "steep" in clean:
                return "bull_steepener" if "bull" in clean else "bear_steepener"
            if "flat" in clean:
                return "bull_flattener" if "bull" in clean else "bear_flattener"
        return "neutral"

    @field_validator("systemic_liquidity_trend", mode="before")
    @classmethod
    def validate_systemic_liquidity_trend(cls, v):
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_").replace(" ", "_")
            if clean in ["expanding", "contracting", "neutral"]:
                return clean
            if any(k in clean for k in ["expand", "growth", "loose", "positive"]):
                return "expanding"
            if any(k in clean for k in ["contract", "drain", "tight", "negative"]):
                return "contracting"
        return "neutral"

    @field_validator("risk_sentiment", mode="before")
    @classmethod
    def validate_risk_sentiment_sfbs(cls, v):
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
    def validate_currency_bias_sfbs(cls, v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                return {}
        if not isinstance(v, dict):
            return {}
        res = {}
        for ccy, bias in v.items():
            ccy_up = str(ccy).upper().strip()
            if isinstance(bias, str):
                b_clean = bias.lower().strip().replace("-", "_").replace(" ", "_")
                if b_clean in ["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]:
                    val = b_clean
                elif "bull" in b_clean:
                    val = "bullish"
                elif "bear" in b_clean:
                    val = "bearish"
                else:
                    val = "neutral"
            else:
                val = "neutral"
            res[ccy_up] = val

        # Map common alias/pair keys when direct single-currency keys are missing
        if "XAU" not in res:
            for k in ("GOLD", "XAUUSD"):
                if k in res:
                    res["XAU"] = res[k]
                    break

        if "OIL" not in res:
            for k in ("WTI", "CRUDE", "BRENT", "USOIL", "UKOIL", "XTIUSD", "XBRUSD"):
                if k in res:
                    res["OIL"] = res[k]
                    break

        if "BTC" not in res:
            for k in ("BITCOIN", "BTCUSD"):
                if k in res:
                    res["BTC"] = res[k]
                    break

        if "EUR" not in res and "EURUSD" in res:
            res["EUR"] = res["EURUSD"]

        if "GBP" not in res and "GBPUSD" in res:
            res["GBP"] = res["GBPUSD"]

        if "AUD" not in res and "AUDUSD" in res:
            res["AUD"] = res["AUDUSD"]

        if "USD" not in res and "DXY" in res:
            res["USD"] = res["DXY"]

        if "USDJPY" in res:
            uj_bias = res["USDJPY"]
            inv_map = {
                "strong_bullish": "strong_bearish",
                "bullish": "bearish",
                "bearish": "bullish",
                "strong_bearish": "strong_bullish",
                "neutral": "neutral",
            }
            if "JPY" not in res:
                res["JPY"] = inv_map.get(uj_bias, "neutral")
            if "USD" not in res:
                res["USD"] = uj_bias

        return res

    @field_validator("asset_priced_in_scores", mode="before")
    @classmethod
    def validate_asset_pi_scores(cls, v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                v = {}
        if not isinstance(v, dict):
            v = {}
        res = {str(k).upper(): coerce_int(val, 5) or 5 for k, val in v.items() if val is not None}
        expected_assets = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
        for asset in expected_assets:
            if asset not in res:
                if asset == "XBRUSD" and "XTIUSD" in res:
                    res["XBRUSD"] = res["XTIUSD"]
                elif asset == "XTIUSD" and "XBRUSD" in res:
                    res["XTIUSD"] = res["XBRUSD"]
                else:
                    res[asset] = 5
        return res

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v):
        val = coerce_float(v, None)
        if val is not None:
            if val > 1.0 and val <= 10.0:
                val = val / 10.0
            elif val > 10.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        raise ValueError("Confidence must be an explicit numeric float between 0.0 and 1.0")

    @field_validator("currency_confidence", mode="before")
    @classmethod
    def validate_currency_confidence(cls, v):
        if not isinstance(v, dict):
            return {}
        res = {}
        for ccy, conf in v.items():
            val = coerce_float(conf, None)
            if val is not None:
                if val > 1.0 and val <= 10.0:
                    val = val / 10.0
                elif val > 10.0 and val <= 100.0:
                    val = val / 100.0
                res[str(ccy).upper()] = max(0.0, min(1.0, val))
            else:
                raise ValueError(
                    f"Currency confidence for '{ccy}' must be an explicit numeric float between 0.0 and 1.0"
                )
        return res

    @field_validator("key_upcoming_risks", mode="before")
    @classmethod
    def validate_upcoming_risks(cls, v):
        if v is None:
            return None
        if isinstance(v, (list, tuple, set)):
            return [item for item in v if item is not None]
        if isinstance(v, (str, dict)):
            return [v]
        return None

    @field_validator(
        "invalidation_conditions", "bias_continuity_justification", "bias_change_justification", mode="before"
    )
    @classmethod
    def validate_string_dicts(cls, v):
        if not isinstance(v, dict):
            return {}
        return {str(k).upper(): coerce_str(val) for k, val in v.items() if val is not None and str(val).strip()}

    @field_validator("macro_narrative", "strongest_counter_thesis", mode="before")
    @classmethod
    def validate_brief_narratives(cls, v):
        return coerce_str(v)


def make_openai_strict_schema(schema_dict: dict) -> dict:
    """
    Transforms standard Pydantic JSON schema into OpenAI strict: true compliant schema.
    Requirements for OpenAI Structured Outputs (strict: true):
    1. 'additionalProperties': False on all object schemas.
    2. Every property in 'properties' MUST be listed in 'required'.
    3. Fields optional in domain logic are made nullable via anyOf: [orig, {"type": "null"}].
    """
    if not isinstance(schema_dict, dict):
        return schema_dict

    s = copy.deepcopy(schema_dict)

    def _patch_object(obj: dict):
        if not isinstance(obj, dict):
            return

        obj.pop("default", None)

        if obj.get("type") == "object" or "properties" in obj:
            obj["additionalProperties"] = False
            props = obj.get("properties", {})
            orig_req = set(obj.get("required", []))
            obj["required"] = list(props.keys())

            for key, prop in props.items():
                if key not in orig_req:
                    if "anyOf" in prop:
                        if not any(item.get("type") == "null" for item in prop["anyOf"]):
                            prop["anyOf"].append({"type": "null"})
                    elif "type" in prop:
                        t = prop["type"]
                        if isinstance(t, str) and t != "null":
                            prop["anyOf"] = [{"type": t}, {"type": "null"}]
                            del prop["type"]
                        elif isinstance(t, list) and "null" not in t:
                            t.append("null")
                    elif "$ref" in prop:
                        ref = prop.pop("$ref")
                        prop["anyOf"] = [{"$ref": ref}, {"type": "null"}]
                _patch_object(prop)

        for k, v in list(obj.items()):
            if k == "properties":
                continue
            if isinstance(v, dict):
                _patch_object(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _patch_object(item)

    _patch_object(s)
    return s
