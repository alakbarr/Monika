# ==============================================================================
# File: application/analysis/prefetch/news_digest/constants.py
# ==============================================================================

"""
Constants, taxonomy, regular expressions, and JSON schemas for news digest processing.
"""

import re
import re as _re

NON_BREAKING_TITLE_PATTERN = _re.compile(
    r"\b(opinion|analysis|analyst view|outlook|preview|recap|explainer|explained|"
    r"here'?s why|what to (watch|expect)|\d+ things|top \d+|op-ed|commentary)\b",
    _re.IGNORECASE,
)

_FINANCIAL_SHORT_TOKENS = {
    "fed",
    "boe",
    "ecb",
    "boj",
    "rba",
    "snb",
    "cpi",
    "ppi",
    "pce",
    "gdp",
    "pmi",
    "oil",
    "gas",
    "cut",
    "wti",
    "btc",
    "xau",
    "usd",
    "eur",
    "gbp",
    "jpy",
    "aud",
    "cad",
    "chf",
    "nzd",
    "jobs",
    "war",
}

_POLARITY_GROUPS = {
    "dovish_down": {
        "cut",
        "cuts",
        "cutting",
        "falls",
        "fell",
        "drop",
        "drops",
        "dropping",
        "plunge",
        "plunges",
        "slump",
        "slumps",
    },
    "hawkish_up": {
        "hike",
        "hikes",
        "hiking",
        "rise",
        "rises",
        "rising",
        "rose",
        "jump",
        "jumps",
        "jumping",
        "surge",
        "surges",
        "surging",
    },
    "neutral_hold": {"hold", "holds", "holding", "pause", "pauses", "pausing"},
}

_STRUCTURAL_NUMBERS = {
    # Small counting integers / list indices / day ranges
    0.0,
    1.0,
    2.0,
    3.0,
    4.0,
    5.0,
    6.0,
    7.0,
    8.0,
    9.0,
    10.0,
    # Common financial horizon hours / round anchors (25, 50, 75 removed to enforce monetary grounding)
    12.0,
    24.0,
    48.0,
    72.0,
    100.0,
    # Historical years & horizons (1980 - 2035)
    *set(float(y) for y in range(1980, 2036)),
}

_NUMERIC_TOKEN_PATTERN = _re.compile(
    r"(?<![A-Za-z0-9_])"
    r"[+\-±~><$€£¥₣₩₹]*"
    r"\d+(?:,\d{3})*(?:\.\d+)?%?"
    r"(?:\s*(?:"
    r"trillions?|tril|\u5146|tn|"
    r"billions?|bil|blns?|bns?|"
    r"millions?|mlns?|mios?|mm|mn|"
    r"thousands?|thou|kilo|"
    r"basis\s*points?|bps?|bp|"
    r"percentage\s*points?|percent|percentage|pct|pp|%|"
    r"pips?|points?|pts?|"
    r"years?|yrs?|months?|weeks?|days?|hours?|hrs?|"
    r"[xX]|sigma|"
    r"[kKmMbBtT]|\u5104"
    r"))?"
    r"(?![A-Za-z0-9_])",
    _re.IGNORECASE,
)

SENTIMENT_TAXONOMY = [
    "BULLISH_USD",
    "BEARISH_USD",
    "BULLISH_EUR",
    "BEARISH_EUR",
    "BULLISH_GBP",
    "BEARISH_GBP",
    "BULLISH_JPY",
    "BEARISH_JPY",
    "BULLISH_AUD",
    "BEARISH_AUD",
    "BULLISH_XAU",
    "BEARISH_XAU",
    "BULLISH_XTI",
    "BEARISH_XTI",
    "BULLISH_BTC",
    "BEARISH_BTC",
    "RISK_ON",
    "RISK_OFF",
    "HAWKISH",
    "DOVISH",
    "INFLATIONARY",
    "DISINFLATIONARY",
    "GEOPOLITICAL_RISK",
    "NEUTRAL",
    # 5-Day Multi-Day Nuance & Narrative Tags
    "FRESH_CATALYST",
    "NARRATIVE_EXHAUSTION",
    "DEESCALATION_RELIEF",
    "HAWKISH_PRICED_IN",
    "DOVISH_PRICED_IN",
]
_SENTIMENT_SET = set(SENTIMENT_TAXONOMY)

NEWS_CLASSIFICATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "news_id": {"type": "integer", "description": "ID of the news item being classified"},
            "reasoning": {
                "type": "string",
                "description": "Chain of thought explaining the impact, surprise magnitude, and sentiment classification.",
            },
            "key_data_point": {
                "type": "string",
                "description": "For DATA RELEASES only: extract actual vs forecast figures verbatim from title/summary if available (e.g. 'CPI actual 3.8% vs forecast 3.1%'). Empty string for non-data releases.",
            },
            "surprise_magnitude": {
                "type": "string",
                "enum": ["none", "small", "moderate", "large"],
                "description": "For DATA RELEASES only: how far actual differs from consensus/forecast. "
                '"none" for non-data news (speeches, geopolitical, opinion). '
                'BREAKING requires "large". A data release matching consensus is "none" '
                "even if the topic itself sounds important.",
            },
            "currencies": {
                "type": "array",
                "items": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "AUD", "XAU", "XTI", "BTC", "NON"]},
            },
            "sentiments": {"type": "array", "items": {"type": "string", "enum": SENTIMENT_TAXONOMY}},
            "impact": {"type": "string", "enum": ["BREAKING", "HIGH", "MEDIUM", "LOW", "NONE"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Confidence score 0.0-1.0"},
        },
        "required": [
            "index",
            "reasoning",
            "key_data_point",
            "surprise_magnitude",
            "currencies",
            "sentiments",
            "impact",
            "confidence",
        ],
    },
}

DIGEST_CONSISTENCY_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_a": {"type": "string"},
                    "section_b": {"type": "string"},
                    "claim_a": {"type": "string"},
                    "claim_b": {"type": "string"},
                    "severity": {"type": "string", "enum": ["minor", "material"]},
                },
                "required": ["section_a", "section_b", "claim_a", "claim_b", "severity"],
            },
        },
        "has_contradictions": {"type": "boolean"},
    },
    "required": ["contradictions", "has_contradictions"],
}

CLASSIFICATION_FEW_SHOT_EXAMPLES = """
CALIBRATED FEW-SHOT EXAMPLES (Study this reasoning pattern; do not merely memorize outputs):

Example 1 — Valid BREAKING:
  Title: "US CPI comes in at 4.2% vs 3.1% forecast, biggest miss in 2 years"
  TIME-IN-SYSTEM: 12 min | CALENDAR_IMPACT_RATING=HIGH
  -> impact=BREAKING, surprise_magnitude=large. Reason: Official hard data release, fresh (<90min),
 large deviation from consensus forecast, strongly supported by CALENDAR_IMPACT_RATING=HIGH.

Example 2 — Appears important but is actually HIGH, not BREAKING:
  Title: "Fed's Williams says rate path remains data dependent"
  TIME-IN-SYSTEM: 30 min | CALENDAR_IMPACT_RATING=(none)
  -> impact=HIGH, surprise_magnitude=none. Reason: Routine policymaker speech without new policy guidance,
 not a quantitative data release, no shock/surprise element.

Example 3 — HIGH incorrectly classified as MEDIUM by weaker models:
  Title: "Eurozone flash PMI beats expectations, signals expansion"
  TIME-IN-SYSTEM: 45 min | CALENDAR_IMPACT_RATING=HIGH
  -> impact=HIGH (not MEDIUM!). Reason: Flash PMI is a tier-1 forward-looking data release (confirmed by
 CALENDAR_IMPACT_RATING=HIGH). Even though not NFP/CPI tier, beating expectations provides a meaningful
 cyclical surprise for EUR currency pairs.

Example 4 — Genuine MEDIUM (Do NOT promote to HIGH):
  Title: "German consumer confidence index inches up slightly"
  TIME-IN-SYSTEM: 20 min | CALENDAR_IMPACT_RATING=MEDIUM
  -> impact=MEDIUM. Reason: Routine tier-2 data release, "inches up slightly" indicates no material surprise,
 calendar rating MEDIUM confirms routine nature.

Example 5 — Market Reaction / Derivative Reporting (NOT BREAKING despite dramatic headline):
  Title: "Gold surges past $2400 as dollar weakens"
  TIME-IN-SYSTEM: 25 min
  -> impact=HIGH (not BREAKING). Reason: Word "surges" indicates price action has ALREADY occurred —
 this reports market price reaction, not the original catalyst event. Violates Rule (4).

Example 6 — Secondary / Derivative Coverage of Same Event (Not BREAKING a second time):
  Title: "Analysts react to surprise BOJ rate hike" (after 3 other BOJ articles already exist)
  TIME-IN-SYSTEM: 40 min
  -> impact=MEDIUM (not BREAKING). Reason: Secondary commentary/analysis, not original breaking event.
 Violates Rule (5) — 3+ articles already cover the event.

Example 7 — Genuine BREAKING Bitcoin/Crypto Event (Directly relevant to BTCUSD):
  Title: "SEC approves first spot Bitcoin ETF applications in historic ruling"
  TIME-IN-SYSTEM: 15 min
  -> impact=BREAKING, surprise_magnitude=large, currencies=["BTC", "USD"], sentiments=["BULLISH_BTC", "RISK_ON"].
 Reason: Historic landmark regulatory decision, fresh (<90min), directly and immediately impacts BTCUSD liquidity.

Example 8 — LOW Speculative Altcoin / Minor Token Noise (Not Bitcoin/Macro):
  Title: "New dog-themed meme coin surges 300% on Solana decentralized exchange"
  TIME-IN-SYSTEM: 20 min
  -> impact=LOW, currencies=["NON"], sentiments=["NEUTRAL"].
 Reason: Minor speculative meme token has zero structural impact on institutional BTC liquidity or global macro markets.
"""
