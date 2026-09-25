"""Benchmark configuration constants — single source of truth for magic numbers."""

# Score blending weights (System Two: LLM Judge + Deterministic)
SCORE_BLEND_JUDGE_WEIGHT = 0.6
SCORE_BLEND_DETERMINISTIC_WEIGHT = 0.4

# System One scoring weights (Latency-Critical & Deterministic)
S1_WEIGHT_ACCURACY = 0.40
S1_WEIGHT_LATENCY = 0.35
S1_WEIGHT_CALIBRATION = 0.15
S1_WEIGHT_SCHEMA = 0.10
S1_LATENCY_TARGET_MS = 100.0
S1_LATENCY_CEILING_MS = 1000.0

# Truncation limits
MAX_RAW_OUTPUT_STORAGE = 8000
MAX_CONTEXT_CHARS_FOR_JUDGE = 32000
MAX_PROMPT_TRUNCATE = 6000

# Hallucination penalties
HALLUCINATION_PENALTIES = {"none": 0.0, "low": 0.5, "medium": 1.5, "high": 3.5}

# Execution Defaults
DEFAULT_TEMPERATURE = 0.0
DEFAULT_CONCURRENCY = 4
DEFAULT_SEED = 42
