"""
NineRouterProvider — Provider untuk 9Router (NymRouter) AI Proxy & Gateway.
Mendukung routing 40+ provider AI, format translation (OpenAI-compatible),
smart auto-fallback (Subscription -> Cheap -> Free), RTK token compression,
dan dynamic model introspection via GET /v1/models.
Base URL default: http://localhost:20128/v1
"""

import logging
import os
import time
from typing import Optional, Dict, Any, List, ClassVar
from analysis.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("TradingAgent.NineRouterProvider")

# Koleksi alias model 9Router ke upstream prefix resmi
NINEROUTER_MODEL_ALIASES: Dict[str, str] = {
    # --- Kiro AI (kr/ - Free Tier 50 credits/mo + free models) ---
    "kr/claude-sonnet-4.5": "kr/claude-sonnet-4.5",
    "kr/claude-sonnet-4.5-thinking": "kr/claude-sonnet-4.5-thinking",
    "kr/claude-sonnet-4.5-agentic": "kr/claude-sonnet-4.5-agentic",
    "kr/claude-sonnet-5": "kr/claude-sonnet-5",
    "kr/claude-sonnet-5-thinking": "kr/claude-sonnet-5-thinking",
    "kr/claude-opus-5": "kr/claude-opus-5",
    "kr/claude-opus-5-thinking": "kr/claude-opus-5-thinking",
    "kr/claude-opus-4.8": "kr/claude-opus-4.8",
    "kr/claude-opus-4.7": "kr/claude-opus-4.7",
    "kr/claude-opus-4.5": "kr/claude-opus-4.5",
    "kr/claude-haiku-4.5": "kr/claude-haiku-4.5",
    "kr/claude-haiku-4.5-thinking": "kr/claude-haiku-4.5-thinking",
    "kr/glm-5": "kr/glm-5",
    "kr/minimax-m2.5": "kr/minimax-m2.5",
    "kr/deepseek-3.2": "kr/deepseek-3.2",
    "kr/qwen3-coder-next": "kr/qwen3-coder-next",
    "kr/gpt-5.6-sol": "kr/gpt-5.6-sol",
    "kr/gpt-5.6-terra": "kr/gpt-5.6-terra",
    "kr/gpt-5.6-luna": "kr/gpt-5.6-luna",

    # --- OpenCode Free (oc/ - 100% Free Tier) ---
    "oc/muse-spark-1.2-contributor-free": "oc/muse-spark-1.2-contributor-free",
    "oc/muse-spark-1.3-contributor-free": "oc/muse-spark-1.3-contributor-free",
    "oc/union-alpha": "oc/union-alpha",
    "oc/jev-1.13-free": "oc/jev-1.13-free",

    # --- OpenCode Zen Free (ocz/ - Free Tier Models) ---
    "ocz/deepseek-v4-flash-free": "ocz/deepseek-v4-flash-free",
    "ocz/mimo-v2.6-flash-free": "ocz/mimo-v2.6-flash-free",
    "ocz/mimo-v2.5-free": "ocz/mimo-v2.5-free",
    "ocz/ling-3.0-flash-fin-free": "ocz/ling-3.0-flash-fin-free",
    "ocz/nemotron-3-ultra-free": "ocz/nemotron-3-ultra-free",
    "ocz/nemotron-3.5-lightning-free": "ocz/nemotron-3.5-lightning-free",
    "ocz/muse-spark-1.3-contributor-free": "ocz/muse-spark-1.3-contributor-free",
    "ocz/muse-spark-1.2-contributor-free": "ocz/muse-spark-1.2-contributor-free",
    "ocz/jev-1.13-free": "ocz/jev-1.13-free",

    # --- iFlow AI (if/ - Free / Unlimited Tier) ---
    "if/kimi-k2": "if/kimi-k2",
    "if/qwen3-coder-plus": "if/qwen3-coder-plus",
    "if/qwen3-max": "if/qwen3-max",
    "if/qwen3-235b": "if/qwen3-235b",
    "if/deepseek-v3.2": "if/deepseek-v3.2",
    "if/deepseek-v3": "if/deepseek-v3",
    "if/deepseek-r1": "if/deepseek-r1",
    "if/glm-4.7": "if/glm-4.7",
    "if/iflow-rome-30ba3b": "if/iflow-rome-30ba3b",

    # --- MiMo Free (mmf/) ---
    "mmf/mimo-auto": "mmf/mimo-auto",

    # --- Gemini CLI Free (gc/) ---
    "gc/gemini-2.5-flash": "gc/gemini-2.5-flash",
    "gc/gemini-2.5-pro": "gc/gemini-2.5-pro",
    "gc/gemini-3-flash-preview": "gc/gemini-3-flash-preview",
    "gc/gemini-3.1-pro-preview": "gc/gemini-3.1-pro-preview",

    # --- API Airforce Free (af/) ---
    "af/gpt-oss-120b": "af/gpt-oss-120b",
    "af/gpt-oss-20b": "af/gpt-oss-20b",
    "af/kimi-k2.7-code": "af/kimi-k2.7-code",

    # --- Antigravity OAuth (ag/) ---
    "ag/gemini-3.8-flash-high": "ag/gemini-3.8-flash-high",
    "ag/gemini-3.8-flash-medium": "ag/gemini-3.8-flash-medium",
    "ag/gemini-3.8-flash": "ag/gemini-3.8-flash",
    "ag/gemini-3.7-flash-high": "ag/gemini-3.7-flash-high",
    "ag/gemini-3.6-flash-high": "ag/gemini-3.6-flash-high",
    "ag/gemini-3.5-flash-high": "ag/gemini-3.5-flash-high",
    "ag/claude-sonnet-4-6": "ag/claude-sonnet-4-6",
    "ag/claude-opus-4-6-thinking": "ag/claude-opus-4-6-thinking",
    "ag/gpt-oss-120b-medium": "ag/gpt-oss-120b-medium",

    # --- Codex OAuth (cx/) ---
    "cx/gpt-6-astra": "cx/gpt-6-astra",
    "cx/gpt-5.6-sol": "cx/gpt-5.6-sol",
    "cx/gpt-5.6-terra": "cx/gpt-5.6-terra",
    "cx/gpt-5.6-luna": "cx/gpt-5.6-luna",
    "cx/gpt-5.5": "cx/gpt-5.5",
    "cx/gpt-5.4": "cx/gpt-5.4",
    "cx/gpt-5.4-mini": "cx/gpt-5.4-mini",
    "cx/gpt-5.3-codex-spark": "cx/gpt-5.3-codex-spark",

    # --- Claude Code OAuth (cc/) ---
    "cc/claude-opus-5": "cc/claude-opus-5",
    "cc/claude-opus-5-5": "cc/claude-opus-5-5",
    "cc/claude-fable-5": "cc/claude-fable-5",
    "cc/claude-sonnet-5": "cc/claude-sonnet-5",
    "cc/claude-haiku-4-5-20251001": "cc/claude-haiku-4-5-20251001",

    # --- GitHub Copilot (gh/) ---
    "gh/claude-sonnet-4.6": "gh/claude-sonnet-4.6",
    "gh/claude-opus-4.6": "gh/claude-opus-4.6",
    "gh/claude-opus-4.7": "gh/claude-opus-4.7",
    "gh/gpt-5.4": "gh/gpt-5.4",
    "gh/gpt-5.4-mini": "gh/gpt-5.4-mini",
    "gh/gpt-5.2": "gh/gpt-5.2",
    "gh/gemini-2.5-pro": "gh/gemini-2.5-pro",

    # --- Virtual Combos (combo/) ---
    "combo/free-fallback": "combo/free-fallback",
    "combo/smart-code": "combo/smart-code",
}

# Daftar model Free Tier ($0 biaya API) di 9Router
FREE_TIER_MODELS_9ROUTER: set[str] = {
    # Kiro AI Free Models
    "kr/claude-sonnet-4.5", "kr/claude-sonnet-4.5-thinking", "kr/claude-sonnet-4.5-agentic",
    "kr/claude-sonnet-5", "kr/claude-sonnet-5-thinking",
    "kr/claude-opus-5", "kr/claude-opus-5-thinking", "kr/claude-opus-5-agentic",
    "kr/claude-opus-4.8", "kr/claude-opus-4.7", "kr/claude-opus-4.5",
    "kr/claude-haiku-4.5", "kr/claude-haiku-4.5-thinking",
    "kr/glm-5", "kr/minimax-m2.5", "kr/deepseek-3.2", "kr/qwen3-coder-next",
    "kr/gpt-5.6-sol", "kr/gpt-5.6-terra", "kr/gpt-5.6-luna",

    # OpenCode Free
    "oc/muse-spark-1.2-contributor-free", "oc/muse-spark-1.3-contributor-free",
    "oc/union-alpha", "oc/jev-1.13-free",

    # OpenCode Zen Free
    "ocz/deepseek-v4-flash-free", "ocz/mimo-v2.6-flash-free", "ocz/mimo-v2.5-free",
    "ocz/ling-3.0-flash-fin-free", "ocz/nemotron-3-ultra-free", "ocz/nemotron-3.5-lightning-free",
    "ocz/muse-spark-1.3-contributor-free", "ocz/muse-spark-1.2-contributor-free",
    "ocz/jev-1.13-free",

    # iFlow AI Free Tier
    "if/kimi-k2", "if/qwen3-coder-plus", "if/qwen3-max", "if/qwen3-235b",
    "if/deepseek-v3.2", "if/deepseek-v3", "if/deepseek-r1", "if/glm-4.7",
    "if/iflow-rome-30ba3b",

    # MiMo Free
    "mmf/mimo-auto",

    # Gemini CLI Free
    "gc/gemini-2.5-flash", "gc/gemini-2.5-pro", "gc/gemini-3-flash-preview", "gc/gemini-3.1-pro-preview",

    # API Airforce Free
    "af/gpt-oss-120b", "af/gpt-oss-20b", "af/kimi-k2.7-code",

    # Virtual Combos Free
    "combo/free-fallback",
}


def normalize_9router_model_name(model_name: str) -> str:
    """
    Normalisasi identifier model untuk 9Router:
    1. Menghilangkan prefix '9router/' atau '9r/' jika ada.
    2. Mencari di NINEROUTER_MODEL_ALIASES.
    3. Mengembalikan format standar upstream 9Router (misal 'kr/claude-sonnet-4.5').
    """
    if not model_name:
        return ""
    clean = str(model_name).strip()
    if clean.lower().startswith("9router/"):
        clean = clean[8:].strip()
    elif clean.lower().startswith("9r/"):
        clean = clean[3:].strip()

    # Cek alias terdaftar
    if clean in NINEROUTER_MODEL_ALIASES:
        return NINEROUTER_MODEL_ALIASES[clean]
    if clean.lower() in NINEROUTER_MODEL_ALIASES:
        return NINEROUTER_MODEL_ALIASES[clean.lower()]

    return clean


class NineRouterProvider(OpenAIProvider):
    """
    Provider untuk 9Router (NymRouter) Local/Remote AI Gateway.
    Menggunakan OpenAI-compatible API endpoint (default: http://localhost:20128/v1).
    Mendukung dynamic model discovery, multi-vendor prefix routing, dan free-tier tracking.
    """
    _client_pool: ClassVar[Dict[str, Any]] = {}

    def __init__(
        self,
        model: str,
        max_tokens: int = 8192,
        max_tool_turns: int = 15,
        thinking_level: str = "none",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        settings: Optional[dict] = None,
        temperature: float = 0.0,
        **kwargs
    ):
        resolved_model = normalize_9router_model_name(model)
        self.raw_model_name = model

        # Resolusi Base URL
        provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get("ninerouter", {})
        resolved_base_url = (
            base_url
            or os.getenv("NINEROUTER_BASE_URL")
            or os.getenv("NINEROUTER_URL")
            or provider_cfg.get("base_url")
            or "http://localhost:20128/v1"
        ).rstrip("/")

        # Resolusi API Key (default sk-9router-local jika tidak diatur)
        resolved_api_key = (
            api_key
            or os.getenv("NINEROUTER_API_KEY")
            or os.getenv("NINEROUTER_KEY")
            or provider_cfg.get("api_key")
            or "sk-9router-local"
        )

        super().__init__(
            model=resolved_model,
            max_tokens=max_tokens,
            api_key=resolved_api_key,
            settings=settings,
            temperature=temperature,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            **kwargs
        )

        self.provider_name = "9router"
        self.model = resolved_model
        self.temperature = temperature
        self.base_url = resolved_base_url
        self.api_key = resolved_api_key
        self.is_free = self.is_model_free(resolved_model) or self.is_model_free(model)

        # Inisialisasi client khusus untuk 9Router endpoint
        self.client = self._get_client(self.api_key, self.base_url)

    def _get_provider_name(self) -> str:
        return "9router"

    def is_model_free(self, model_name: Optional[str] = None) -> bool:
        """Cek apakah model termasuk free-tier 9Router."""
        target = normalize_9router_model_name(model_name or self.model).lower()
        if target in FREE_TIER_MODELS_9ROUTER:
            return True
        if target.endswith(":free") or ":free" in target:
            return True
        return False

    def _get_client(self, api_key: str, base_url: str):
        """Membuat atau menggunakan kembali cached client AsyncOpenAI untuk endpoint 9Router."""
        cache_key = f"{base_url}::{api_key}"
        if cache_key not in self.__class__._client_pool:
            try:
                from openai import AsyncOpenAI
                provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("ninerouter", {})
                timeout_sec = float(provider_cfg.get("timeout_seconds", 180.0))
                max_retries = int(provider_cfg.get("max_retries", 3))

                self.__class__._client_pool[cache_key] = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=timeout_sec,
                    max_retries=max_retries,
                    default_headers={
                        "HTTP-Referer": "https://monika.local",
                        "X-Title": "Monika MT5 Trading Agent (9Router Gateway)",
                        "X-Session-ID": "monika_9router_session",
                    }
                )
            except ImportError:
                logger.warning("OpenAI package not installed. Run `pip install openai`.")
                return None
        return self.__class__._client_pool[cache_key]

    async def fetch_available_models(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """
        Dynamic Model Introspection:
        Mengambil daftar model real-time dari 9Router instance via GET /v1/models.
        """
        if not self.client:
            return []
        try:
            import asyncio
            coro = self.client.models.list()
            response = await asyncio.wait_for(coro, timeout=timeout)
            models = []
            for m in getattr(response, "data", []):
                model_id = getattr(m, "id", None)
                if model_id:
                    models.append({
                        "id": model_id,
                        "owned_by": getattr(m, "owned_by", "9router"),
                        "is_free": self.is_model_free(model_id),
                    })
            logger.info(f"[9Router] Introspected {len(models)} active models from {self.base_url}")
            return models
        except Exception as e:
            logger.debug(f"[9Router] Failed to fetch live models from {self.base_url}: {e}")
            return []

    @classmethod
    def is_alive(cls, host: str = "127.0.0.1", port: int = 20128) -> bool:
        """Cek apakah 9Router gateway aktif di localhost/remote port."""
        return is_9router_alive(host, port)

    @classmethod
    def ensure_running(cls, host: str = "127.0.0.1", port: int = 20128, wait_seconds: float = 3.0) -> bool:
        """Pastikan 9Router aktif, atau otomatis spawn jika offline."""
        return try_auto_spawn_9router(host, port, wait_seconds)


def is_9router_alive(host: str = "127.0.0.1", port: int = 20128, timeout: float = 1.0) -> bool:
    """Cek apakah 9Router gateway aktif dan merespon port TCP."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def try_auto_spawn_9router(host: str = "127.0.0.1", port: int = 20128, wait_seconds: float = 3.0) -> bool:
    """
    Mencoba menyalakan 9Router AI Gateway secara otomatis di background
    jika belum aktif. Mendukung binary `9router` atau `npx -y 9router`.
    """
    if is_9router_alive(host, port):
        return True

    import shutil
    import subprocess

    cmd = None
    if shutil.which("9router"):
        cmd = ["9router", "--no-browser", "--skip-update"]
    elif shutil.which("npx"):
        cmd = ["npx", "-y", "9router", "--no-browser", "--skip-update"]
    elif shutil.which("npx.cmd"):
        cmd = ["npx.cmd", "-y", "9router", "--no-browser", "--skip-update"]

    if not cmd:
        logger.warning("[9Router] Gateway offline dan tidak ditemukan binary '9router' atau 'npx'.")
        return False

    try:
        logger.info(f"[9Router] Menyalakan 9Router AI Gateway otomatis: {' '.join(cmd)}...")
        if os.name == "nt":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                cmd,
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                shell=True
            )
        else:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )

        start_time = time.time()
        while time.time() - start_time < wait_seconds:
            time.sleep(0.3)
            if is_9router_alive(host, port):
                logger.info(f"[9Router] Berhasil dinyalakan dan listening di port {port}.")
                return True
    except Exception as e:
        logger.warning(f"[9Router] Gagal menyalakan 9Router otomatis: {e}")

    return is_9router_alive(host, port)

