"""Daftar model kandidat -- HANYA model yang harganya diketahui (dari
pricing.py), supaya sumbu perbandingan biaya selalu valid untuk semua model
yang diuji. Groq gratis, jadi otomatis termasuk."""

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
    # Stealth & OpenRouter Free Tier
    "ox-alpha", "glm-5.2:free", "gemma-4-31b:free", "nemotron-3-ultra:free",
    "north-mini-code:free", "laguna-xs-2.1:free", "openrouter/free",
    # Groq (gratis)
    "groq-compound", "groq-compound-mini", "groq-gpt-oss-120b", "groq-gpt-oss-20b",
    "groq-qwen3.6-27b", "groq-qwen3.8-27b",
]


def make_role_config(max_tokens: int = 8192, max_tool_turns: int = 10,
                      temperature: float = 0.0, thinking: str = "medium") -> dict:
    """role_config generik yang diterima create_client() -> _create_client_instance()."""
    providers = ("anthropic", "gemini", "openai", "deepseek", "groq", "ollama", "openai_compatible", "openrouter")
    return {
        "max_tokens": max_tokens,
        "max_tool_turns": max_tool_turns,
        "temperature": temperature,
        "thinking": {p: thinking for p in providers},
    }
