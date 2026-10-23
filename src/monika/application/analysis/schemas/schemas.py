"""Deprecated module: import directly from monika.application.analysis.schemas instead."""

import warnings

warnings.warn(
    "monika.application.analysis.schemas.schemas is deprecated; import from monika.application.analysis.schemas instead",
    DeprecationWarning,
    stacklevel=2,
)

from monika.application.analysis.schemas import (
    AssetMacroContext,
    ConfidenceLevel,
    EntryCondition,
    KeyDataPointsUsed,
    MacroRegime,
    PricedInAssessment,
    PricedInOverrideJustification,
    ReevaluationTrigger,
    SentimentAnalysisSchema,
    SentimentBand,
    SpecialistAdjudication,
    SubmitAssetAnalysisSchema,
    SubmitFundamentalBriefSchema,
    TradeDirection,
    UpcomingRiskEvent,
    _inline_refs,
    coerce_float,
    coerce_int,
    coerce_str,
    coerce_string_list,
    get_tool_schema,
    make_openai_strict_schema,
)

__all__ = [
    "AssetMacroContext",
    "ConfidenceLevel",
    "EntryCondition",
    "KeyDataPointsUsed",
    "MacroRegime",
    "PricedInAssessment",
    "PricedInOverrideJustification",
    "ReevaluationTrigger",
    "SentimentAnalysisSchema",
    "SentimentBand",
    "SpecialistAdjudication",
    "SubmitAssetAnalysisSchema",
    "SubmitFundamentalBriefSchema",
    "TradeDirection",
    "UpcomingRiskEvent",
    "_inline_refs",
    "coerce_float",
    "coerce_int",
    "coerce_str",
    "coerce_string_list",
    "get_tool_schema",
    "make_openai_strict_schema",
]
