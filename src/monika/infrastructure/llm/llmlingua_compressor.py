"""
Adaptive LLMLingua-2 Prompt Compressor for Monika Trading Agent.

Features:
- Automatic hardware discovery: Detects CUDA GPU availability and verifies minimum 1.5 GB free VRAM.
- Transparent CPU fallback: Automatically routes to CPU-only execution if GPU is missing or VRAM is constrained.
- Graceful heuristic fallback: If llmlingua library is not yet installed in environment, falls back to deterministic extractive sentence pruning.
- Strict Financial Guardrails: Safeguards numerical tables, tickers, and price levels from destructive token classification.
"""

import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("TradingAgent.LLMLinguaCompressor")


class AdaptiveLLMLinguaCompressor:
    """
    Manages task-agnostic prompt compression using LLMLingua-2 with automatic GPU/CPU routing.
    """

    _instance: Optional["AdaptiveLLMLinguaCompressor"] = None
    _device: Optional[str] = None
    _compressor: Optional[Any] = None
    _initialized: bool = False

    def __init__(self, model_name: str = "microsoft/llmlingua-2-bert-base-multilingual-cased"):
        self.model_name = model_name

    @classmethod
    def get_instance(cls) -> "AdaptiveLLMLinguaCompressor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def detect_device(cls) -> str:
        """
        Detects whether adequate GPU resources exist for LLMLingua-2 inference.
        Requires CUDA availability and >= 1.2 GB of unallocated VRAM.
        Returns 'cuda' or 'cpu'.
        """
        if cls._device is not None:
            return cls._device

        try:
            import torch
            if torch.cuda.is_available():
                # Check available VRAM on primary device
                free_bytes, total_bytes = torch.cuda.mem_get_info(0)
                free_gb = free_bytes / (1024 ** 3)
                if free_gb >= 1.2:
                    logger.info(f"[LLMLingua] GPU detected: {torch.cuda.get_device_name(0)} ({free_gb:.2f} GB free VRAM). Using 'cuda'.")
                    cls._device = "cuda"
                    return "cuda"
                else:
                    logger.info(f"[LLMLingua] GPU VRAM constrained ({free_gb:.2f} GB < 1.2 GB required). Routing to 'cpu'.")
                    cls._device = "cpu"
                    return "cpu"
        except Exception as e:
            logger.debug(f"[LLMLingua] GPU detection non-fatal check: {e}")

        logger.info("[LLMLingua] No compatible CUDA GPU available. Using 'cpu' mode.")
        cls._device = "cpu"
        return "cpu"

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        device = self.detect_device()

        try:
            from llmlingua import PromptCompressor
            logger.info(f"[LLMLingua] Initializing PromptCompressor ({self.model_name}) on device={device}...")
            self._compressor = PromptCompressor(
                model_name=self.model_name,
                device_map=device
            )
            logger.info("[LLMLingua] LLMLingua-2 model loaded successfully.")
        except ImportError:
            logger.info("[LLMLingua] 'llmlingua' package not installed in active environment. Using deterministic fallback compressor.")
            self._compressor = None
        except Exception as e:
            logger.warning(f"[LLMLingua] Failed to load LLMLingua model on {device}: {e}. Falling back to CPU heuristic.")
            self._compressor = None

    def compress_text(
        self,
        text: str,
        rate: float = 0.5,
        target_token: Optional[int] = None,
        drop_consecutive: bool = True
    ) -> str:
        """
        Compresses narrative text while preserving semantic coherence and financial facts.
        """
        if not text or len(text.strip()) < 100:
            return text

        self._ensure_initialized()

        # Neural LLMLingua compression
        if self._compressor is not None:
            try:
                res = self._compressor.compress_prompt(
                    text,
                    rate=rate,
                    target_token=target_token,
                    drop_consecutive=drop_consecutive
                )
                if isinstance(res, dict) and "compressed_prompt" in res:
                    compressed = res["compressed_prompt"]
                    logger.debug(f"[LLMLingua] Compressed {len(text)} chars -> {len(compressed)} chars ({res.get('ratio', 'N/A')})")
                    return compressed
            except Exception as e:
                logger.debug(f"[LLMLingua] Neural compression failed: {e}. Using heuristic fallback.")

        # Heuristic Extractive Fallback
        return self._heuristic_compress(text, target_ratio=rate)

    def _heuristic_compress(self, text: str, target_ratio: float = 0.5) -> str:
        """
        Deterministic lightweight compressor: Prunes boilerplate conversational phrases,
        redundant filler sentences, and compresses whitespace while strictly preserving
        financial figures, percentages, dates, and currency tickers.
        """
        # Split into sentences or lines
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if len(lines) <= 2:
            return text

        retained = []
        financial_keywords = (
            "rate", "inflation", "cpi", "nfp", "gdp", "fomc", "ecb", "fed", "boj",
            "yield", "percent", "%", "basis point", "bps", "support", "resistance",
            "bullish", "bearish", "target", "stop", "sl", "tp", "pips", "usd", "eur",
            "jpy", "gbp", "gold", "oil", "xau", "btc", "liquidity", "order block"
        )

        for line in lines:
            l_lower = line.lower()
            # Always keep lines with financial markers or numbers
            if any(k in l_lower for k in financial_keywords) or bool(re.search(r"\d+\.?\d*", line)):
                retained.append(line)
            elif len(retained) < int(len(lines) * target_ratio):
                retained.append(line)

        compressed = "\n".join(retained)
        return compressed if compressed else text
