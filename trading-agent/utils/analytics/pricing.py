"""
Production Pricing Engine — Sumber Tunggal Kebenaran (Single Source of Truth)
untuk kalkulasi biaya token USD seluruh model AI yang didukung.

Mendukung model dari Anthropic, Google Gemini, OpenAI, DeepSeek, Groq, OpenRouter, dan Ollama.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger("TradingAgent.Pricing")


@dataclass(frozen=True)
class PricingTier:
    """Tiered pricing definition for models with threshold-based rates.
    Adopted from Pi's ModelCostTier pattern.
    """
    threshold_tokens: int       # Threshold token count (e.g. 200_000 tokens)
    input_rate: float           # $ / 1M input token beyond threshold
    cached_input_rate: float    # $ / 1M cached input token beyond threshold
    output_rate: float          # $ / 1M output token beyond threshold


@dataclass(frozen=True)
class Price:
    input: float          # $ / 1M input token
    cached_input: float   # $ / 1M cached input token (prompt caching)
    output: float         # $ / 1M output token
    note: str = ""
    tier: Optional[PricingTier] = None


# Harga resmi USD per 1.000.000 token
PRICING: Dict[str, Price] = {
    # --- Anthropic Claude Models ---
    "claude-opus-5": Price(5.00, 0.50, 25.00),
    "opus-5": Price(5.00, 0.50, 25.00),
    "claude-opus-4.8": Price(5.00, 0.50, 25.00),
    "opus-4.8": Price(5.00, 0.50, 25.00),
    "claude-opus-4.7": Price(5.00, 0.50, 25.00),
    "opus-4.7": Price(5.00, 0.50, 25.00),
    "claude-opus-4.6": Price(5.00, 0.50, 25.00),
    "opus-4.6": Price(5.00, 0.50, 25.00),
    "claude-opus-4.5": Price(5.00, 0.50, 25.00),
    "opus-4.5": Price(5.00, 0.50, 25.00),
    "claude-sonnet-5": Price(2.00, 0.20, 10.00),
    "sonnet-5": Price(2.00, 0.20, 10.00),
    "claude-sonnet-4.6": Price(3.00, 0.30, 15.00),
    "claude-sonnet-4-6": Price(3.00, 0.30, 15.00),
    "sonnet-4.6": Price(3.00, 0.30, 15.00),
    "claude-sonnet-4.5": Price(3.00, 0.30, 15.00),
    "sonnet-4.5": Price(3.00, 0.30, 15.00),
    "claude-haiku-4.5": Price(1.00, 0.10, 5.00),
    "haiku-4.5": Price(1.00, 0.10, 5.00),
    "claude-haiku-4-5-20251001": Price(1.00, 0.10, 5.00),
    "claude-fable-5": Price(10.00, 1.00, 50.00),
    "claude-3-7-sonnet": Price(3.00, 0.30, 15.00),
    "claude-3-7-sonnet-20250219": Price(3.00, 0.30, 15.00),
    "claude-3-5-sonnet": Price(3.00, 0.30, 15.00),
    "claude-3-5-sonnet-20241022": Price(3.00, 0.30, 15.00),
    "claude-3-5-haiku": Price(0.80, 0.08, 4.00),
    "claude-3-5-haiku-20241022": Price(0.80, 0.08, 4.00),

    # --- Google Gemini Models ---
    "gemini-3.7-flash": Price(1.50, 0.15, 7.50, "Free tier direct / Paid tier rate"),
    "gemini-3.6-flash": Price(1.50, 0.15, 7.50),
    "gemini-3.5-flash": Price(1.50, 0.15, 9.00),
    "gemini-3.5-flash-lite": Price(0.30, 0.03, 2.50),
    "gemini-3.1-flash-lite": Price(0.25, 0.025, 1.50),
    "gemini-3.0-flash-preview": Price(0.50, 0.05, 3.00),
    "gemini-3.1-pro-preview": Price(2.00, 0.20, 12.00, "tier <=200K ctx; >200K = 4.00/0.40/18.00"),
    "gemini-2.5-pro": Price(1.25, 0.125, 10.00),
    "gemini-2.5-flash": Price(0.15, 0.0375, 0.60),
    "gemini-2.0-flash": Price(0.10, 0.025, 0.40),

    # --- OpenAI Models ---
    "gpt-5.6-sol": Price(5.00, 0.50, 30.00),
    "gpt-5.6-terra": Price(2.00, 0.20, 12.00),
    "gpt-5.6-luna": Price(0.20, 0.02, 1.20),
    "gpt-5.5": Price(5.00, 0.50, 30.00),
    "gpt-5.4": Price(2.50, 0.25, 15.00),
    "gpt-5.4-mini": Price(0.75, 0.075, 4.50),
    "gpt-5.4-nano": Price(0.20, 0.02, 1.25),
    "gpt-5.1": Price(1.25, 0.125, 10.00),
    "gpt-4o": Price(2.50, 1.25, 10.00),
    "gpt-4o-mini": Price(0.15, 0.075, 0.60),
    "o1": Price(15.00, 7.50, 60.00),
    "o3-mini": Price(1.10, 0.55, 4.40),

    # --- DeepSeek Models ---
    "deepseek-v4-pro": Price(0.66, 0.022, 1.98, "off-peak; peak=1.32/0.044/3.96"),
    "deepseek-v4-pro-0813": Price(0.66, 0.022, 1.98),
    "deepseek-v4-flash": Price(0.22, 0.007, 0.66, "off-peak; peak=0.44/0.014/1.32"),
    "deepseek-v4-flash-0731": Price(0.22, 0.007, 0.66),
    "deepseek-chat": Price(0.14, 0.014, 0.28),
    # --- TypeSafe Models ---
    "jev-latest": Price(0.042, 0.042, 0.0, "TypeSafe Jev System One - output free"),
    "jev-1.13.0": Price(0.042, 0.042, 0.0, "TypeSafe Jev 1.13 - output free"),
    "jev-1.13": Price(0.042, 0.042, 0.0, "TypeSafe Jev 1.13 - output free"),
    "jev-preview": Price(0.042, 0.042, 0.0, "TypeSafe Jev Preview - output free"),

    # --- OpenRouter Third-Party Paid Models ---
    "kimi-k3": Price(3.00, 0.30, 15.00),
    "qwen3.8-max": Price(1.60, 0.16, 6.40),
    "qwen3.8-2.4t-a95b": Price(0.60, 0.06, 2.40),
    "qwen3.8-27b": Price(0.35, 0.035, 2.75),
    "grok-4.6": Price(3.00, 0.30, 15.00),
    "grok-4.5": Price(3.00, 0.30, 15.00),
    "grok-4.3": Price(0.50, 0.05, 2.50),
    "mimo-v2.5-pro": Price(0.50, 0.05, 2.00),
    "mimo-v2.5": Price(0.20, 0.02, 1.00),
    "glm-5.3": Price(0.075, 0.0075, 0.25),
    "glm-5.2": Price(0.20, 0.02, 1.00),
    "glm-5.1": Price(0.20, 0.02, 1.00),
    "minimax-m3": Price(0.20, 0.02, 1.00),
    "muse-spark-1.2": Price(0.20, 0.02, 1.00),
}

_FREE = Price(0.0, 0.0, 0.0, "Free tier / Local execution ($0)")

# Pemetaan alias dan format OpenRouter (e.g. org/model -> model_key)
OPENROUTER_PRICING_MAP: Dict[str, str] = {
    # Anthropic
    "anthropic/claude-opus-5": "claude-opus-5",
    "anthropic/claude-sonnet-5": "claude-sonnet-5",
    "anthropic/claude-sonnet-4.6": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4-6": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4.5": "claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5-20251001": "claude-haiku-4-5-20251001",
    "anthropic/claude-haiku-4.5": "claude-haiku-4.5",
    "anthropic/claude-fable-5": "claude-fable-5",
    "anthropic/claude-3.7-sonnet": "claude-3-7-sonnet",
    "anthropic/claude-3-7-sonnet": "claude-3-7-sonnet",
    "anthropic/claude-3.5-sonnet": "claude-3-5-sonnet",

    # DeepSeek
    "deepseek/deepseek-v4-pro": "deepseek-v4-pro",
    "deepseek/deepseek-v4-pro-0813": "deepseek-v4-pro-0813",
    "deepseek/deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek/deepseek-v4-flash-0731": "deepseek-v4-flash-0731",
    "deepseek/deepseek-chat": "deepseek-chat",
    "deepseek/deepseek-r1": "deepseek-reasoner",
    "deepseek/deepseek-reasoner": "deepseek-reasoner",

    # OpenAI
    "openai/gpt-5.6-sol": "gpt-5.6-sol",
    "openai/gpt-5.6-terra": "gpt-5.6-terra",
    "openai/gpt-5.6-luna": "gpt-5.6-luna",
    "openai/gpt-5.4-nano": "gpt-5.4-nano",
    "openai/gpt-5.4-mini": "gpt-5.4-mini",
    "openai/gpt-5.4": "gpt-5.4",
    "openai/gpt-5.5": "gpt-5.5",
    "openai/gpt-5.1": "gpt-5.1",
    "openai/gpt-5-mini": "gpt-5.6-luna",
    "openai/gpt-4o": "gpt-4o",
    "openai/gpt-4o-mini": "gpt-4o-mini",
    "openai/o1": "o1",
    "openai/o3-mini": "o3-mini",

    # Google
    "google/gemini-3.7-flash": "gemini-3.7-flash",
    "google/gemini-3.6-flash": "gemini-3.6-flash",
    "google/gemini-3.5-flash": "gemini-3.5-flash",
    "google/gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "google/gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "google/gemini-3.0-flash-preview": "gemini-3.0-flash-preview",
    "google/gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
    "google/gemini-2.5-pro": "gemini-2.5-pro",
    "google/gemini-2.5-flash": "gemini-2.5-flash",
    "google/gemini-2.0-flash": "gemini-2.0-flash",

    # Moonshot Kimi
    "moonshotai/kimi-k3": "kimi-k3",
    "moonshot/kimi-k3": "kimi-k3",

    # Qwen
    "qwen/qwen3.8-max": "qwen3.8-max",
    "qwen/qwen3.8-2.4t-a95b": "qwen3.8-2.4t-a95b",
    "qwen/qwen3.8-27b": "qwen3.8-27b",
    "qwen/qwen3.6-27b": "qwen3.8-27b",

    # X-AI Grok
    "x-ai/grok-4.6": "grok-4.6",
    "x-ai/grok-4.5": "grok-4.5",
    "x-ai/grok-4.3": "grok-4.3",

    # Xiaomi MiMo
    "xiaomi/mimo-v2.5-pro": "mimo-v2.5-pro",
    "xiaomi/mimo-v2.5": "mimo-v2.5",

    # Zhipu GLM
    "z-ai/glm-5.3": "glm-5.3",
    "z-ai/glm-5.2": "glm-5.2",
    "z-ai/glm-5.1": "glm-5.1",

    # MiniMax
    "minimax/minimax-m3": "minimax-m3",

    # Meta
    "meta-llama/muse-spark-1.2": "muse-spark-1.2",
}

# Daftar eksplisit model Free Tier ($0)
FREE_TIER_MODELS = {
    # Stealth
    "ox-alpha", "stealth/ox-alpha", "openrouter/free", "openrouter-free",

    # OpenRouter Free Tier
    "glm-5.2:free", "z-ai/glm-5.2:free",
    "minimax-m3:free", "minimax/minimax-m3:free",
    "gemma-4-31b:free", "google/gemma-4-31b-it:free",
    "gemma-4-26b:free", "google/gemma-4-26b-a4b-it:free",
    "nemotron-3-ultra:free", "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nemotron-3.5-lightning:free", "nvidia/nemotron-3.5-lightning:free",
    "nemotron-3-super:free", "nvidia/nemotron-3-super-120b-a12b:free",
    "nemotron-3-nano:free", "nvidia/nemotron-3-nano-30b-a3b:free",
    "nemotron-3-nano-omni:free", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nemotron-nano-12b-vl:free", "nvidia/nemotron-nano-12b-v2-vl:free",
    "nemotron-nano-9b:free", "nvidia/nemotron-nano-9b-v2:free",
    "nemotron-3.5-safety:free", "nvidia/nemotron-3.5-content-safety:free",
    "north-mini-code:free", "cohere/north-mini-code:free",
    "laguna-s-2.1:free", "poolside/laguna-s-2.1:free",
    "laguna-xs-2.1:free", "poolside/laguna-xs-2.1:free",
    "inkling:free", "thinkingmachines/inkling:free",
    "inkling-small:free", "thinkingmachines/inkling-small:free",
    "dots-3-note:free", "dots-studio/dots-3-note-preview:free",
    "lfm-2.5-2.6b:free", "liquid/lfm-2.5-2.6b:free",

    # Groq Developer Free Tier
    "groq-compound", "groq-compound-mini", "groq-gpt-oss-120b", "groq-gpt-oss-20b",
    "qwen3.6-27b", "groq-qwen3.6-27b", "groq-qwen3.8-27b",

    # Ollama Local
    "llama3.2", "ollama", "local"
}


def infer_provider_from_model(model_name: str) -> str:
    """Inferensi otomatis provider berdasarkan nama model jika provider tidak diberikan."""
    if not model_name:
        return "unknown"
    clean = str(model_name).strip().lower()
    if clean.startswith("vertex/"):
        return "vertex"
    if clean.startswith(("gemini-", "models/gemini", "google/gemini-")):
        return "gemini"
    if clean.startswith(("groq-", "groq/")):
        return "groq"
    if clean.startswith(("anthropic/", "claude-", "opus-", "sonnet-", "haiku-")):
        return "anthropic"
    if clean.startswith(("deepseek/", "deepseek-")):
        return "deepseek"
    if clean.startswith(("typesafe/", "typesafe-", "jev-", "jev")):
        return "typesafe"
    if clean.startswith(("openai/", "gpt-", "o1", "o3")):
        return "openai"
    if clean.startswith(("ollama", "llama3.2", "local")):
        return "ollama"
    if clean.startswith("openrouter/"):
        return "openrouter"
    return "unknown"


def is_free_tier(
    model_name: str,
    provider: Optional[str] = None,
    is_direct_free_tier: Optional[bool] = None
) -> bool:
    """
    Evaluasi apakah pemanggilan model masuk kategori Free Tier ($0).
    Mendukung Gemini (GEMINI_API_KEYS), Groq Developer Tier, OpenRouter :free & openrouter/free, dan Ollama.
    """
    if is_direct_free_tier is True:
        return True
    if is_direct_free_tier is False:
        return False

    clean_name = str(model_name).strip().lower()
    prov = (provider or "").strip().lower()
    if not prov:
        prov = infer_provider_from_model(model_name)

    # 1. OpenRouter free models & endpoint suffix :free
    if clean_name.endswith(":free") or ":free" in clean_name:
        return True
    if clean_name in FREE_TIER_MODELS or clean_name == "openrouter/free" or clean_name.startswith("stealth/"):
        return True

    # 2. Provider Free Tiers
    if prov in ("groq", "ollama"):
        return True
    if prov == "gemini" and not clean_name.startswith("vertex/"):
        return True

    return False


def get_price(model_name: str) -> Price:
    """Mengembalikan objek Price untuk model yang diberikan."""
    if not model_name:
        return _FREE
    
    clean_name = str(model_name).strip().lower()
    
    # 1. Cek langsung model Free Tier
    if clean_name in FREE_TIER_MODELS or clean_name.endswith(":free") or ":free" in clean_name:
        return _FREE
    
    # 2. Cek tabel PRICING langsung
    if clean_name in PRICING:
        return PRICING[clean_name]
    
    # 3. Cek OPENROUTER_PRICING_MAP
    if clean_name in OPENROUTER_PRICING_MAP:
        mapped = OPENROUTER_PRICING_MAP[clean_name]
        return PRICING.get(mapped, _FREE)
    
    # 4. Cek stripping provider prefix (e.g. 'anthropic/claude-sonnet-5' -> 'claude-sonnet-5')
    if "/" in clean_name:
        suffix = clean_name.split("/", 1)[1]
        if suffix in FREE_TIER_MODELS or suffix.endswith(":free") or ":free" in suffix:
            return _FREE
        if suffix in PRICING:
            return PRICING[suffix]
        if suffix in OPENROUTER_PRICING_MAP:
            mapped = OPENROUTER_PRICING_MAP[suffix]
            return PRICING.get(mapped, _FREE)
    
    # 5. Fuzzy match prefix/substring
    for k, price_obj in PRICING.items():
        if k in clean_name or clean_name in k:
            return price_obj
            
    return _FREE


def cost_usd(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    provider: Optional[str] = None,
    is_direct_free_tier: Optional[bool] = None
) -> float:
    """
    Menghitung estimasi biaya pemanggilan API dalam USD.
    
    Rumus:
      Cost = (Input_Non_Cached * Rate_In) + (Cached_Tokens * Rate_Cache) + (Output_Tokens * Rate_Out)
    """
    if is_free_tier(model_name, provider=provider, is_direct_free_tier=is_direct_free_tier):
        return 0.0

    p = get_price(model_name)
    if p.input == 0.0 and p.output == 0.0:
        return 0.0
        
    uncached_input = max(0, input_tokens - cached_tokens)
    
    if p.tier and uncached_input > p.tier.threshold_tokens:
        base_tokens = p.tier.threshold_tokens
        tier_tokens = uncached_input - base_tokens
        cost_in = (base_tokens / 1_000_000.0) * p.input + (tier_tokens / 1_000_000.0) * p.tier.input_rate
    else:
        cost_in = (uncached_input / 1_000_000.0) * p.input

    if p.tier and cached_tokens > p.tier.threshold_tokens:
        base_cached = p.tier.threshold_tokens
        tier_cached = cached_tokens - base_cached
        cost_cache = (base_cached / 1_000_000.0) * p.cached_input + (tier_cached / 1_000_000.0) * p.tier.cached_input_rate
    else:
        cost_cache = (cached_tokens / 1_000_000.0) * p.cached_input

    if p.tier and output_tokens > p.tier.threshold_tokens:
        base_out = p.tier.threshold_tokens
        tier_out = output_tokens - base_out
        cost_out = (base_out / 1_000_000.0) * p.output + (tier_out / 1_000_000.0) * p.tier.output_rate
    else:
        cost_out = (output_tokens / 1_000_000.0) * p.output
    
    return round(cost_in + cost_cache + cost_out, 6)


# Alias for backward compatibility
estimate_cost = cost_usd

