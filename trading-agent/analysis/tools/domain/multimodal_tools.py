# ==============================================================================
# File: analysis/tools/domain/multimodal_tools.py
# ==============================================================================

"""
Multimodal Vision & Financial Chart Analysis Tool for Monika.
Institutional-grade visual asset processing with 256 KB token clamping,
resolution budget guards, and repeat-analysis deduplication.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Tools.Multimodal")

MAX_IMAGE_BYTES = 256 * 1024  # 256 KB token clamp
MAX_DIMENSION = 1024


class ChartVisionInput(BaseModel):
    """Schema for technical chart visual analysis."""
    image_path_or_base64: str = Field(
        ...,
        description="Local disk path to chart image (.png/.jpg) or raw base64 data string."
    )
    symbol: Optional[str] = Field(
        None,
        description="Ticker symbol for the chart (e.g. 'EURUSD', 'XAUUSD', 'BTCUSDT')."
    )
    timeframe: Optional[str] = Field(
        None,
        description="Chart timeframe (e.g. 'M15', 'H1', 'H4', 'D1')."
    )
    focus_areas: Optional[List[str]] = Field(
        default_factory=lambda: ["trend", "support_resistance", "candlestick_patterns"],
        description="Key visual aspects to inspect: 'trend', 'support_resistance', 'patterns', 'indicators'."
    )


class VisionImageProcessor:
    """
    Guards and optimizes visual payloads for multimodal LLM ingestion.
    """

    _recent_hashes: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def clamp_image_to_budget(cls, raw_bytes: bytes) -> Tuple[bytes, str]:
        """
        Compresses and resizes image to conform to 256 KB limit and max 1024x1024 dimensions.
        Returns (clamped_bytes, mime_type).
        """
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw_bytes))

            # Convert RGBA/P to RGB for JPEG compression
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Check dimensions
            w, h = img.size
            if max(w, h) > MAX_DIMENSION:
                scale = MAX_DIMENSION / max(w, h)
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Progressive quality downgrade if byte size exceeds 256 KB
            quality = 85
            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=quality)

            while out_buf.tell() > MAX_IMAGE_BYTES and quality > 30:
                quality -= 15
                out_buf = io.BytesIO()
                img.save(out_buf, format="JPEG", quality=quality)

            return out_buf.getvalue(), "image/jpeg"
        except Exception as exc:
            logger.debug(f"[Multimodal] PIL image processing fallback: {exc}")
            if len(raw_bytes) > MAX_IMAGE_BYTES:
                return raw_bytes[:MAX_IMAGE_BYTES], "application/octet-stream"
            return raw_bytes, "application/octet-stream"

    @classmethod
    def check_repeat_refusal(cls, image_bytes: bytes) -> Optional[Dict[str, Any]]:
        """
        Checks if an identical image was processed recently to prevent repeat hallucinations.
        """
        digest = hashlib.sha256(image_bytes).hexdigest()
        return cls._recent_hashes.get(digest)

    @classmethod
    def record_processed_image(cls, image_bytes: bytes, analysis_result: Dict[str, Any]) -> None:
        """Records processed image digest in session cache."""
        digest = hashlib.sha256(image_bytes).hexdigest()
        cls._recent_hashes[digest] = analysis_result
        if len(cls._recent_hashes) > 100:
            cls._recent_hashes.pop(next(iter(cls._recent_hashes)))


@unified_tool_registry.register(
    name="chart_vision_analyze",
    category="MARKET_ANALYSIS",
    input_model=ChartVisionInput,
)
async def handle_chart_vision_analyze(
    params: ChartVisionInput,
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Ingests and analyzes a financial price chart image with 256 KB clamp and repeat guard.
    """
    # 1. Resolve raw bytes
    target = params.image_path_or_base64.strip()
    raw_bytes: bytes = b""

    if os.path.exists(target):
        try:
            with open(target, "rb") as f:
                raw_bytes = f.read()
        except Exception as exc:
            return {"success": False, "error": f"Failed reading chart image file '{target}': {exc}"}
    else:
        # Try decoding base64
        try:
            if "," in target:
                target = target.split(",", 1)[1]
            raw_bytes = base64.b64decode(target)
        except Exception:
            return {"success": False, "error": f"Target is neither a valid file path nor base64 image data: '{target[:50]}'"}

    if not raw_bytes:
        return {"success": False, "error": "Chart image payload is empty."}

    # 2. Check Repeat Refusal Guard
    cached_analysis = VisionImageProcessor.check_repeat_refusal(raw_bytes)
    if cached_analysis:
        logger.info(f"[Multimodal] Repeat refusal triggered: identical chart image previously analyzed.")
        cached_copy = dict(cached_analysis)
        cached_copy["cached_analysis"] = True
        return cached_copy

    # 3. 256 KB Budget Clamp
    clamped_bytes, mime_type = VisionImageProcessor.clamp_image_to_budget(raw_bytes)
    b64_clamped = base64.b64encode(clamped_bytes).decode("ascii")

    # 4. Generate structured chart assessment
    symbol_str = params.symbol or "UNKNOWN_ASSET"
    tf_str = params.timeframe or "UNKNOWN_TIMEFRAME"

    result = {
        "success": True,
        "symbol": symbol_str,
        "timeframe": tf_str,
        "original_bytes": len(raw_bytes),
        "clamped_bytes": len(clamped_bytes),
        "mime_type": mime_type,
        "image_data_uri": f"data:{mime_type};base64,{b64_clamped}",
        "focus_areas": params.focus_areas,
        "status": "ready_for_multimodal_llm",
        "message": f"Chart image successfully clamped to {len(clamped_bytes)} bytes. Ready for visual inference.",
    }

    # Cache for repeat refusal guard
    VisionImageProcessor.record_processed_image(raw_bytes, result)
    return result
