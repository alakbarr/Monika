from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
from typing import Optional, List, Dict, Literal, Any
import copy

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
    RISK_ON = 'risk_on'
    RISK_OFF = 'risk_off'
    STAGFLATION = 'stagflation'
    DISINFLATION = 'disinflation'
    TRANSITION = 'transition'
    MIXED = 'mixed'



class FundamentalBriefSchema(BaseModel):
    macro_bias: str = Field(default="neutral")
    macro_narrative: Optional[str] = Field(default=None, description="Clear narrative summary of macro conditions")
    key_drivers: list[str] = Field(default_factory=list)
    risk_events: list[str] = Field(default_factory=list)
    narrative_shift: bool = Field(default=False)
    shift_explanation: str | None = None
    
    macro_regime: MacroRegime = Field(default=MacroRegime.MIXED, description='Klasifikasi regime makro eksplisit — lebih luas dari risk_sentiment (mis. mendeteksi stagflasi).')
    
    # Kept for backward compatibility
    currency_bias: Dict[str, Literal["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]] = Field(
        default_factory=dict, description="Directional bias for each major currency (USD, EUR, GBP, etc.)"
    )
    currency_confidence: Dict[str, float] = Field(
        default_factory=dict, description="Confidence per currency"
    )
    invalidation_conditions: Dict[str, str] = Field(
        default_factory=dict, description="Invalidation conditions per asset"
    )
    risk_sentiment: Literal["risk-on", "risk-off", "mixed"] = Field(
        default="mixed", description="Overall market risk sentiment"
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Confidence in this brief (0.0 to 1.0)"
    )
    priced_in_assessment: Optional[Dict] = Field(None, description="Structured assessment of priced-in factors")
    strongest_counter_thesis: Optional[str] = Field(default='', description="Counter thesis argument")

    @model_validator(mode='before')
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
                    data["risk_events"] = [
                        r.get("event", str(r)) if isinstance(r, dict) else str(r)
                        for r in risks
                    ]
        return data

    @field_validator('macro_regime', mode='before')
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

    @field_validator('risk_sentiment', mode='before')
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

    @field_validator('currency_bias', mode='before')
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

    @field_validator('key_drivers', 'risk_events', mode='before')
    @classmethod
    def validate_brief_string_lists(cls, v):
        return coerce_string_list(v, default=[]) or []

    @field_validator('macro_bias', mode='before')
    @classmethod
    def validate_macro_bias(cls, v):
        return coerce_str(v, default="neutral")


class SentimentAnalysisSchema(BaseModel):
    overall_band: SentimentBand  # Bullish/Mildly Bullish/Neutral/Mixed/Mildly Bearish/Bearish
    overall_score: float = Field(ge=0.0, le=10.0)  # 0=bearish, 5=neutral, 10=bullish
    confidence: ConfidenceLevel
    narrative: str
    retail_vs_institutional: str

# =============================================================================
# Sub-Schemas (Migrated from schemas.py)
# =============================================================================

class SpecialistAdjudication(BaseModel):
    conflict_detected: bool = Field(..., description="Did the technical/SMC setup conflict with the macro fundamental bias?")
    conflict_reason: Optional[str] = Field(None, description="If conflict exists, what is the exact nature of the divergence?")
    resolution_path: Optional[Literal["override_macro", "cancel_setup", "scale_out", "hedged_entry"]] = Field(None, description="How the conflict is resolved by the specialist agent.")
    resolution_justification: Optional[str] = Field(None, description="Why this resolution was chosen over the others.")

    @model_validator(mode='before')
    @classmethod
    def coerce_specialist_adjudication(cls, data: Any) -> Any:
        if isinstance(data, str):
            s = data.strip()
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
        return data

class EntryCondition(BaseModel):
    type: Literal["market", "limit", "trigger"]
    price: Optional[float] = Field(None, description="Specific price level (null for 'market').")
    detail: str = Field(..., description="Detailed entry condition description.")

class ReevaluationTrigger(BaseModel):
    type: Literal["price_level", "indicator", "time", "news"]
    detail: str = Field(..., description="Specific trigger condition.")
    price: Optional[float] = Field(None, description="Required if type is 'price_level'. The target price.")
    direction: Optional[Literal["above", "below"]] = Field(None, description="Required if type is 'price_level'.")
    symbol: Optional[str] = Field(None, description="Optional. The symbol this trigger applies to. Defaults to current asset.")

    @model_validator(mode='after')
    def validate_and_extract_price_level(self) -> 'ReevaluationTrigger':
        if self.type == 'price_level':
            import re
            if (self.price is None or not self.direction) and self.detail:
                text = self.detail.lower()
                above_m = re.search(r'(?:above|break[s]?\s+above|over|reache[s]?|hit[s]?)\s+([\d,]+(?:\.\d+)?)', text)
                below_m = re.search(r'(?:below|break[s]?\s+below|under|drop[s]?\s+to)\s+([\d,]+(?:\.\d+)?)', text)
                
                if above_m and not self.price:
                    try:
                        self.price = float(above_m.group(1).replace(',', ''))
                        self.direction = 'above'
                    except ValueError:
                        pass
                elif below_m and not self.price:
                    try:
                        self.price = float(below_m.group(1).replace(',', ''))
                        self.direction = 'below'
                    except ValueError:
                        pass
                        
            # If price or direction is still missing after extraction, fallback to type='time'
            if self.price is None or not self.direction:
                self.type = 'time'
                
        return self

class PricedInOverrideJustification(BaseModel):
    override_reason: str
    why_stage1_wrong: str
    post_event_evidence: str

    @model_validator(mode='before')
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
        for field in ('condition', 'detail', 'summary', 'event', 'event_name', 'title', 'headline', 'name', 'reason', 'justification', 'narrative', 'text'):
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
            items = [item.strip().lstrip("-*•0123456789. ") for item in re.split(r"[\n,]+", s)]
            return [item for item in items if item]
        return [s]
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
                name = item.get('event_name') or item.get('event') or item.get('title') or item.get('headline') or item.get('name') or item.get('driver') or ''
                impact = item.get('impact') or item.get('expected_impact') or ''
                currency = item.get('currency') or ''
                time_val = item.get('time') or item.get('event_time') or ''
                
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
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("none", "null", "n/a", "na", "nan", "nil", "unknown", "not_applicable", "not applicable", "not quoted", "not_quoted", "-", "--"):
            return default
        clean_s = re.sub(r'^[~><$€£¥\s]+|(?:%|\s+|pts|bps|pips|long|short)+$', '', s, flags=re.IGNORECASE).strip()
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", clean_s):
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
    if v is None:
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("none", "null", "n/a", "na", "nan", "nil", "unknown", "not_applicable", "-", "--"):
            return default
        # Strip score denominator like '/10' or '/ 10' or '%', 'pts'
        clean_s = re.sub(r"/\s*\d+$", "", s).strip()
        clean_s = re.sub(r'^[~><$€£¥\s]+|(?:%|\s+|pts|bps|pips)+$', '', clean_s, flags=re.IGNORECASE).strip()
        if re.fullmatch(r"[-+]?\d+", clean_s):
            try:
                return int(clean_s)
            except ValueError:
                return default
        if re.fullmatch(r"[-+]?\d+\.0+", clean_s):
            try:
                return int(float(clean_s))
            except ValueError:
                return default
    return default

class UpcomingRiskEvent(BaseModel):
    event: str
    time: str
    expected_impact: Literal["high", "medium", "low"]

    @model_validator(mode='before')
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
                data["event"] = coerce_str(data.get("name") or data.get("event_name") or data.get("title") or "Upcoming Event")
            if not data.get("time"):
                data["time"] = coerce_str(data.get("event_time") or data.get("date") or "upcoming")
            if not data.get("expected_impact"):
                impact_raw = str(data.get("impact") or data.get("severity") or "medium").lower()
                data["expected_impact"] = impact_raw if impact_raw in ("high", "medium", "low") else "medium"
        return data

class PricedInAssessment(BaseModel):
    dominant_driver: str = Field(..., description="The main driver/narrative currently being priced in by the market (e.g., 'Fed rate cut expectations for Dec FOMC meeting').")
    priced_in_score: int = Field(..., ge=1, le=10, description="Composite priced-in score (1-10). Sum of scores from FedWatch (0-3), COT extreme (0-3), price run-up (0-3), news saturation (0-2). 1=nothing priced in, 10=fully priced in.")
    sell_the_news_risk: Literal["high", "medium", "low", "not_applicable"] = Field(..., description="Risk of counter-trend 'sell the news' reaction if expected event materializes as expected.")
    key_unpriced_drivers: Optional[List[str]] = Field(None, description="Drivers that are NOT yet priced in and could cause surprise moves (upside or downside).")
    cot_positioning_percentile: Optional[float] = Field(
        None, 
        description="Nilai persentil numerik COT (0-100) dari get_cot_report atau macro_priced_in_baseline. WAJIB diisi pada hari kerja jika tidak ada retail_sentiment_percentile."
    )
    retail_sentiment_percentile: Optional[float] = Field(
        None, 
        description="Nilai sentimen retail numerik (0-100) dari get_retail_sentiment jika ada. WAJIB diisi pada hari kerja jika tidak ada cot_positioning_percentile."
    )

    @field_validator('key_unpriced_drivers', mode='before')
    @classmethod
    def validate_unpriced_drivers(cls, v):
        return coerce_string_list(v)

    @field_validator('dominant_driver', mode='before')
    @classmethod
    def validate_dominant_driver(cls, v):
        return coerce_str(v, default="Macro drivers")

    @field_validator('priced_in_score', mode='before')
    @classmethod
    def validate_priced_in_score(cls, v):
        res = coerce_int(v)
        if res is None:
            raise ValueError(f"priced_in_score must be a valid integer, got '{v}'")
        return max(1, min(10, res))

    @field_validator('cot_positioning_percentile', 'retail_sentiment_percentile', mode='before')
    @classmethod
    def validate_percentiles(cls, v):
        return coerce_float(v)

# =============================================================================
# Tool Input Schemas
# =============================================================================

class SubmitAssetAnalysisSchema(BaseModel):
    symbol: str = Field(..., description="Trading symbol this analysis is for (e.g. 'EURUSD', 'XAUUSD', 'BTCUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XTIUSD'). REQUIRED.")
    decision: Literal["buy", "sell", "avoid", "wait"] = Field(..., description="'buy'/'sell' = set up a trade. 'wait' = thesis valid but entry not ready yet. 'avoid' = do not trade this asset this cycle.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this decision (0.0 to 1.0).")
    rationale: str = Field(..., description="Concise reasoning for the decision. Must be auditable by a human. Include key confluence factors.")
    
    specialist_adjudication: Optional[SpecialistAdjudication] = Field(None, description="Structured conflict resolution if SMC setup diverges from Stage 1 Fundamental Brief macro bias.")
    
    entry_condition: Optional[EntryCondition] = Field(None, description="Entry condition. Required if decision is 'buy' or 'sell'.")
    priced_in_override_justification: Optional[PricedInOverrideJustification] = Field(None, description="ONLY fill if you are overriding a priced_in_score >= 8 guard. Must provide: override_reason (string), why_stage1_wrong (string), post_event_evidence (string). If null, standard rules apply.")
    
    stop_loss: Optional[float] = Field(None, description="Stop loss price level. Required if decision is 'buy' or 'sell'.")
    take_profit: Optional[float] = Field(None, description="Take profit price level. Required if decision is 'buy' or 'sell'.")
    
    invalidation: str = Field(
        ...,
        description=(
            "REQUIRED: Specific condition that completely invalidates this thesis. "
            "MUST include a specific price level and direction. "
            "EXAMPLE GOOD: 'Thesis invalid if XAUUSD D1 closes above 2420 (breaks bullish structure)'. "
            "EXAMPLE BAD: 'If market changes direction'. "
            "DO NOT submit a dict or list — must be a plain string. "
            "Also fill invalidation_price and invalidation_direction fields separately for monitoring."
        )
    )
    
    @field_validator('invalidation', 'news_impact_assessment', 'rationale', mode='before')
    @classmethod
    def coerce_string_fields(cls, v):
        """Coerce dict/list/non-string to string for LLMs that return structured data."""
        return coerce_str(v)

    @field_validator('key_news_events_considered', 'confluence_factors', mode='before')
    @classmethod
    def coerce_string_lists(cls, v):
        """Coerce list of mixed dicts/strings/numbers into a clean list of strings."""
        return coerce_string_list(v)

    @field_validator('confidence', mode='before')
    @classmethod
    def validate_asset_confidence(cls, v):
        val = coerce_float(v, None)
        if val is not None:
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        raise ValueError("Asset analysis confidence must be an explicit numeric float between 0.0 and 1.0")

    @field_validator('stop_loss', 'take_profit', 'invalidation_price', mode='before')
    @classmethod
    def validate_prices(cls, v):
        import math
        val = coerce_float(v)
        if val is not None and (val <= 0 or math.isnan(val) or math.isinf(val)):
            return None
        return val

    @field_validator('confluence_score', 'priced_in_score', mode='before')
    @classmethod
    def validate_scores(cls, v):
        return coerce_int(v)

    invalidation_price: Optional[float] = Field(None, description="Optional but STRONGLY RECOMMENDED: The specific price level that invalidates your thesis. Example: if BUY and thesis invalid above 2420, set invalidation_price=2420, invalidation_direction=\"above\". Used for automated monitoring of open positions.")
    invalidation_direction: Optional[Literal["above", "below"]] = Field(None, description="\"above\" = thesis invalid if price closes ABOVE invalidation_price. \"below\" = thesis invalid if price closes BELOW invalidation_price.")
    
    reevaluation_trigger: Optional[ReevaluationTrigger] = Field(None, description="Condition that should trigger re-analysis. Required if decision is 'buy', 'sell', or 'wait'.")
    
    priced_in_score: Optional[int] = Field(None, ge=1, le=10, description="REQUIRED for buy/sell decisions: Asset-specific priced-in score (1-10 scale). Sum of applicable sub-scores: FedWatch (0-3) + COT extreme positioning (0-3) + price run-up vs ATR from get_price_momentum (0-3) + news saturation (0-1). 1=not priced in, 10=fully priced in. Score >= 8 with major event within 12h: MANDATORY WAIT. Score 5-7: increase confluence threshold +2, reduce lot size 30-50%. Score <= 4: standard thresholds apply.")
    confluence_score: Optional[int] = Field(None, description="REQUIRED for buy/sell decisions: Total confluence score (integer 0-14) based on SMC/ICT framework.")
    confluence_factors: Optional[List[str]] = Field(None, description="REQUIRED for buy/sell: List of confluence factor IDs that are ACTIVE (scoring points) for this setup. Use these exact IDs: \"fundamental_bias\", \"dxy_confirms\", \"d1_trend\", \"rsi_neutral\", \"near_fvg\", \"near_order_block\", \"in_ote_zone\", \"near_sr_zone\", \"cot_aligned\", \"vix_ok\", \"post_event_entry\", \"session_prime\", \"liquidity_sweep_confirmed\". Example: [\"fundamental_bias\", \"d1_trend\", \"near_fvg\", \"near_order_block\"]")
    
    key_news_events_considered: Optional[List[str]] = Field(None, description="Optional list of news events considered in this analysis (e.g. ['US CPI 3.1%', 'FOMC Rate Decision']). Must be a list of plain strings.")
    news_impact_assessment: Optional[str] = Field(None, description="Optional assessment of how the news impacts the setup.")

    @model_validator(mode='before')
    @classmethod
    def normalize_and_alias_fields(cls, data: Any) -> Any:
        """Resolve symbol aliases and normalize symbol casing/formatting before validation."""
        if not isinstance(data, dict):
            return data
        
        # 1. Alias resolution for symbol
        if not data.get('symbol'):
            for alias in ('asset', 'pair', 'ticker', 'instrument', 'symbol_name', 'target_asset', 'currency_pair'):
                if data.get(alias):
                    data['symbol'] = data[alias]
                    break
                    
        # 2. Normalisasi string symbol
        if data.get('symbol') and isinstance(data['symbol'], str):
            data['symbol'] = data['symbol'].strip().upper().replace('/', '')
            
        return data

    @model_validator(mode='after')
    def validate_trade_parameters(self):
        """Enforce SL/TP/entry_condition presence when decision is buy or sell."""
        if self.decision in ('buy', 'sell'):
            missing = []
            if self.stop_loss is None:
                missing.append('stop_loss')
            if self.take_profit is None:
                missing.append('take_profit')
            if self.entry_condition is None:
                missing.append('entry_condition')
            if self.reevaluation_trigger is None:
                missing.append('reevaluation_trigger')
            if self.confluence_score is None:
                missing.append('confluence_score')
            if self.priced_in_score is None:
                missing.append('priced_in_score')
            if self.invalidation_price is None:
                missing.append('invalidation_price')
            if self.invalidation_direction is None:
                missing.append('invalidation_direction')
            if not self.invalidation or not str(self.invalidation).strip():
                missing.append('invalidation')
            if missing:
                raise ValueError(
                    f"decision='{self.decision}' requires parameters: {', '.join(missing)}. "
                    f"All trade risk parameters must be explicitly defined."
                )
        return self

class ChecklistVerification(BaseModel):
    bias_vs_narrative_match: bool = Field(..., description="True if the currency bias aligns with the narrative.")
    contradiction_existed: bool = Field(..., description="True if a contradiction was found and resolved.")

class KeyDataPointsUsed(BaseModel):
    dxy_trend_5d: str = Field(..., description="e.g. 'strengthening +0.8%' or 'weakening -0.4%', persis seperti dibaca dari get_dxy()")
    vix_close: float = Field(..., description="Nilai VIX close terbaru, persis seperti dibaca dari get_vix()")
    fedwatch_dominant_pct: Optional[float] = Field(None, description="Probabilitas dominan FedWatch jika ada meeting dalam window analisis")
    treasury_10y_yield_pct: Optional[float] = Field(None, description="Nilai yield 10Y terbaru (%), persis seperti dibaca dari get_treasury_yields()")
    cot_leveraged_long_pct: Optional[float] = Field(None, description="Persentase leveraged funds net-long terbaru untuk driver COT utama yang dikutip di narasi, persis seperti dibaca dari get_cot_report()/get_precomputed_cot_signals()")

    @field_validator('vix_close', mode='before')
    @classmethod
    def validate_vix_close(cls, v):
        res = coerce_float(v)
        if res is None:
            raise ValueError(f"vix_close must be a valid number, got '{v}'")
        return res

    @field_validator('fedwatch_dominant_pct', 'treasury_10y_yield_pct', 'cot_leveraged_long_pct', mode='before')
    @classmethod
    def validate_optional_pcts(cls, v):
        return coerce_float(v)

class SubmitFundamentalBriefSchema(BaseModel):
    checklist: ChecklistVerification = Field(..., description="Wajib diisi sebelum submit. Verifikasi kelengkapan dan konsistensi internal.")
    key_data_points_used: KeyDataPointsUsed = Field(..., description=(
        "WAJIB: restate nilai numerik kunci yang BENAR-BENAR kamu baca dari tools "
        "sebelum menulis narasi. Field ini di-cross-check backend terhadap data riil "
        "yang sudah di-fetch untuk mendeteksi salah baca/halusinasi angka."
    ))
    macro_narrative: str = Field(..., description="A clear narrative summary of current macro conditions (2-4 paragraphs). Include key drivers, trends, and risks.")
    currency_bias: Dict[str, Literal["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]] = Field(
        ...,
        description=(
            "Directional bias for each major currency/asset. "
            "REQUIRED keys: USD, EUR, GBP, JPY, AUD, XAU. "
            "STRONGLY RECOMMENDED additional keys: OIL (for WTI crude analysis), BTC (for Bitcoin). "
            "Values: 'bullish', 'bearish', or 'neutral'. "
            "Example: {'USD': 'bullish', 'EUR': 'bearish', 'XAU': 'bullish', 'OIL': 'bearish', 'BTC': 'neutral'}"
        )
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
                    "ke Stage 2 untuk menimbang input makro currency tsb lebih ringan."
    )
    key_upcoming_risks: Optional[List[UpcomingRiskEvent]] = Field(None, description="List of key upcoming risk events that could invalidate or amplify your thesis.")
    risk_sentiment: Literal["risk-on", "risk-off", "mixed"] = Field(..., description="Overall market risk sentiment.")
    macro_regime: MacroRegime = Field(..., description='Klasifikasi regime makro eksplisit — lebih luas dari risk_sentiment (mis. mendeteksi stagflasi).')
    confidence: float = Field(..., ge=0.0, le=1.0, description="Your confidence in this brief (0.0 to 1.0). Be honest - lower confidence if data is sparse or contradictory.")
    priced_in_assessment: PricedInAssessment = Field(..., description="WAJIB DIISI. Structured assessment of what is currently priced in to market levels. Use data from get_fedwatch_probabilities, get_cot_report, and get_price_momentum.")
    strongest_counter_thesis: str = Field(
        default='',
        description="WAJIB: Argumen TERKUAT yang berlawanan dengan tesis makro utama Anda saat ini. "
                    "Harus mengutip data/faktor konkret yang jika benar akan membalikkan bias Anda. "
                    "Contoh: 'Jika NFP Jumat >250k, tesis USD bearish saya batal karena Fed hawkish "
                    "repricing akan terjadi cepat.' Bukan pernyataan generik seperti 'pasar bisa berubah.'"
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

    @field_validator('macro_regime', mode='before')
    @classmethod
    def validate_macro_regime_sfbs(cls, v):
        if isinstance(v, MacroRegime):
            return v
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_")
            for m in MacroRegime:
                if clean == m.value or clean == m.name.lower():
                    return m
        return MacroRegime.MIXED

    @field_validator('risk_sentiment', mode='before')
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

    @field_validator('currency_bias', mode='before')
    @classmethod
    def validate_currency_bias_sfbs(cls, v):
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

    @field_validator('confidence', mode='before')
    @classmethod
    def validate_confidence(cls, v):
        val = coerce_float(v, None)
        if val is not None:
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        raise ValueError("Confidence must be an explicit numeric float between 0.0 and 1.0")

    @field_validator('currency_confidence', mode='before')
    @classmethod
    def validate_currency_confidence(cls, v):
        if not isinstance(v, dict):
            return {}
        res = {}
        for ccy, conf in v.items():
            val = coerce_float(conf, None)
            if val is not None:
                if val > 1.0 and val <= 100.0:
                    val = val / 100.0
                res[str(ccy).upper()] = max(0.0, min(1.0, val))
            else:
                raise ValueError(f"Currency confidence for '{ccy}' must be an explicit numeric float between 0.0 and 1.0")
        return res

    @field_validator('key_upcoming_risks', mode='before')
    @classmethod
    def validate_upcoming_risks(cls, v):
        if v is None:
            return None
        if isinstance(v, (list, tuple, set)):
            return [item for item in v if item is not None]
        if isinstance(v, (str, dict)):
            return [v]
        return None

    @field_validator('invalidation_conditions', 'bias_continuity_justification', 'bias_change_justification', mode='before')
    @classmethod
    def validate_string_dicts(cls, v):
        if not isinstance(v, dict):
            return {}
        return {str(k).upper(): coerce_str(val) for k, val in v.items() if val is not None and str(val).strip()}

    @field_validator('macro_narrative', 'strongest_counter_thesis', mode='before')
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


