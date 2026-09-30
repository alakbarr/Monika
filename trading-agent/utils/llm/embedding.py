"""
Gemini Embedding Generation Service.
Generates dense vector embeddings using Google Gemini Embedding API (Gemini Embedding 2: gemini-embedding-2).
"""
import logging
import os
from typing import Optional, List
from utils.api.http_retry import fetch_with_retry

logger = logging.getLogger("TradingAgent.Embedding")

GEMINI_EMBEDDING_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
LEGACY_MODEL_MIGRATIONS = {
    "text-embedding-004": "gemini-embedding-2",
    "gemini-embedding-2-preview": "gemini-embedding-2",
}

async def generate_gemini_embedding(
    text: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    settings: Optional[dict] = None,
    api_key: Optional[str] = None,
    output_dimensionality: Optional[int] = 768,
) -> Optional[List[float]]:
    """
    Generate dense vector embedding using Gemini Embedding API (Gemini Embedding 2).
    Returns list of floats (typically 768 dimensions with output_dimensionality=768), or None if unavailable.
    """
    if not text or not text.strip():
        return None

    resolved_key = api_key
    if not resolved_key:
        try:
            from utils.api.credential_pool import get_credential_pool
            pool = get_credential_pool()
            resolved_key = pool.get_key("gemini")
        except Exception:
            pass

    if not resolved_key:
        resolved_key = os.getenv("GEMINI_PAID_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not resolved_key:
        logger.debug("[Embedding] No Gemini API key available for embedding.")
        return None

    target_model = model or (settings and settings.get("embedding_model")) or os.getenv("GEMINI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL

    # Strip model prefix if passed like models/gemini-embedding-001
    clean_model = target_model.split("/")[-1]

    # Auto-migrate deprecated/retired models (e.g. text-embedding-004 -> gemini-embedding-001)
    if clean_model in LEGACY_MODEL_MIGRATIONS:
        migrated_model = LEGACY_MODEL_MIGRATIONS[clean_model]
        logger.debug(f"[Embedding] Migrating deprecated model '{clean_model}' to '{migrated_model}'")
        clean_model = migrated_model

    url = f"{GEMINI_EMBEDDING_BASE_URL}/{clean_model}:embedContent?key={resolved_key}"

    # Truncate text to reasonable length (e.g. 8000 chars)
    payload = {
        "content": {
            "parts": [{"text": text[:8000].strip()}]
        }
    }
    effective_dim = output_dimensionality if output_dimensionality is not None else (settings and settings.get("embedding_dimensions"))
    if effective_dim is not None:
        payload["outputDimensionality"] = int(effective_dim)

    try:
        data = await fetch_with_retry(
            url=url,
            method="POST",
            json=payload,
            max_retries=2,
            base_delay=1.0,
            timeout=15,
        )
        if isinstance(data, dict):
            values = data.get("embedding", {}).get("values")
            if values and isinstance(values, list):
                return [float(v) for v in values]
            if "error" in data:
                logger.warning(f"[Embedding] Gemini embedding API error: {data['error']}")
    except Exception as e:
        logger.warning(f"[Embedding] Failed to generate embedding: {e}")

    return None
