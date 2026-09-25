"""Daftar model kandidat dan konfigurasi tier benchmark.
Mendukung pemuatan dinamis dari settings.yaml (benchmark.tiers, benchmark.candidates, benchmark.router_matrix).
"""
from typing import Optional, Dict, List, Any

CANDIDATE_MODELS: list[str] = [
    # Anthropic
    "claude-opus-5", "claude-sonnet-5", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    # Google
    "gemini-3.1-pro-preview", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
    # OpenAI
    "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
    # DeepSeek
    "deepseek-v4-pro", "deepseek-v4-flash",
    # TypeSafe System One
    "jev-latest", "jev-1.13",
    # Stealth & OpenRouter Free Tier
    "ox-alpha", "z-ai/glm-5.2:free", "google/gemma-4-31b:free", "nvidia/nemotron-3-ultra:free",
    "meta-llama/north-mini-code:free", "cohere/laguna-xs-2.1:free", "openrouter/free",
    # Groq (gratis)
    "groq-compound", "groq-compound-mini", "groq-gpt-oss-120b", "groq-gpt-oss-20b",
    "groq-qwen3.6-27b", "groq-qwen3.8-27b",
]


def get_candidate_models(settings: Optional[dict] = None, tier: Optional[str] = None) -> list[str]:
    """Mengambil daftar model kandidat aktif berdasarkan tier atau config settings.yaml."""
    if not settings:
        return CANDIDATE_MODELS

    bench_cfg = settings.get("benchmark", {})
    if tier and "tiers" in bench_cfg and tier in bench_cfg["tiers"]:
        tier_cfg = bench_cfg["tiers"][tier]
        if isinstance(tier_cfg, dict) and "models" in tier_cfg:
            return list(tier_cfg["models"])

    if "candidates" in bench_cfg and bench_cfg["candidates"]:
        models = []
        for cand in bench_cfg["candidates"]:
            if isinstance(cand, dict) and cand.get("enabled", True):
                name = cand.get("id") or cand.get("name") or cand.get("model_id")
                if name:
                    models.append(name)
        if models:
            return models

    return CANDIDATE_MODELS


def get_tier_models(tier_name: str, settings: Optional[dict] = None) -> list[str]:
    """Mengambil daftar model untuk tier spesifik (system_one, cheap_smart, cheap_efficient, high_intelligence)."""
    return get_candidate_models(settings, tier=tier_name)


def get_router_matrix(settings: Optional[dict] = None) -> dict[str, list[str]]:
    """Mengambil matriks perbandingan model yang sama lewat berbagai router (mis. direct vs openrouter vs 9router)."""
    if settings:
        matrix = settings.get("benchmark", {}).get("router_matrix")
        if matrix and isinstance(matrix, dict):
            return matrix
    return {
        "claude-3.5-sonnet": [
            "anthropic:claude-3-5-sonnet-20241022",
            "openrouter:anthropic/claude-3.5-sonnet",
            "9router:anthropic/claude-3.5-sonnet",
        ],
        "gemini-flash": [
            "gemini:gemini-3.5-flash-lite",
            "openrouter:google/gemini-2.5-flash",
            "9router:google/gemini-2.5-flash",
        ],
        "qwen-27b": [
            "groq:groq-qwen3.8-27b",
            "openrouter:qwen/qwen-2.5-72b-instruct",
            "9router:qwen/qwen-2.5-72b-instruct",
        ]
    }


def make_role_config(max_tokens: int = 8192, max_tool_turns: int = 10,
                      temperature: float = 0.0, thinking: str = "medium",
                      seed: int = 42) -> dict:
    """role_config generik yang diterima create_client() -> _create_client_instance()."""
    providers = (
        "anthropic", "gemini", "openai", "deepseek", "groq",
        "ollama", "openai_compatible", "openrouter", "typesafe",
        "9router", "ninerouter", "nine_router", "vertex",
    )
    return {
        "max_tokens": max_tokens,
        "max_tool_turns": max_tool_turns,
        "temperature": temperature,
        "seed": seed,
        "thinking": {p: thinking for p in providers},
    }
