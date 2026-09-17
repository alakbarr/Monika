"""
TimesFM Quantile Asymmetry Skew Alpha Calculator.
Computes directional expansion probability and risk sizing multipliers from TimesFM 3.0 probability density.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import logging
import numpy as np

logger = logging.getLogger("TradingAgent.TimesFMAlpha")


class TimesFMAlphaCalculator:
    """
    Kalkulator Alpha Mikrostruktur berbasis Quantile Asymmetry dari Google TimesFM 3.0.
    
    Formula:
      Upper Expansion = Q90 - Q50
      Lower Expansion = Q50 - Q10
      Skew Ratio = Upper Expansion / Lower Expansion
    
    Interpretasi:
      - Skew Ratio >= 1.35: Probabilitas ekspansi condong ke atas (BULLISH_EXPANSION)
      - Skew Ratio <= 0.75: Probabilitas ekspansi condong ke bawah (BEARISH_EXPANSION)
      - 0.75 < Skew Ratio < 1.35: Distribusi probabilistik seimbang (SYMMETRIC_NEUTRAL)
    """

    BULLISH_THRESHOLD: float = 1.35
    BEARISH_THRESHOLD: float = 0.75

    @classmethod
    def calculate_skew_from_quantiles(
        cls,
        quantiles: Dict[str, Union[List[float], float]],
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Hitung skew ratio dari kamus kuantil TimesFM.
        
        Args:
            quantiles: Dict berisi key 'q10', 'q50', 'q90' (baik float tunggal atau list sepanjang horizon).
            current_price: Harga penutupan terkini (opsional) untuk validasi drift.
            
        Returns:
            Dict hasil analisis skewness kuantil TimesFM.
        """
        if not quantiles:
            return cls._empty_result("No quantiles provided")

        try:
            # Ambil nilai kuantil horizon terjauh (terminal horizon step)
            q10_raw = quantiles.get("q10")
            q50_raw = quantiles.get("q50")
            q90_raw = quantiles.get("q90")

            if q10_raw is None or q50_raw is None or q90_raw is None:
                return cls._empty_result("Missing required quantiles (q10, q50, q90)")

            q10 = float(q10_raw[-1] if isinstance(q10_raw, (list, tuple, np.ndarray)) else q10_raw)
            q50 = float(q50_raw[-1] if isinstance(q50_raw, (list, tuple, np.ndarray)) else q50_raw)
            q90 = float(q90_raw[-1] if isinstance(q90_raw, (list, tuple, np.ndarray)) else q90_raw)

            # Validasi monotonisitas kuantil
            if not (q10 <= q50 <= q90):
                return cls._empty_result(f"Non-monotonic quantiles: q10={q10}, q50={q50}, q90={q90}")

            upper_expansion = max(0.0, q90 - q50)
            lower_expansion = max(0.0, q50 - q10)

            # Hitung rasio kemiringan (skew ratio)
            if lower_expansion < 1e-8:
                skew_ratio = 2.5 if upper_expansion > 1e-8 else 1.0
            else:
                skew_ratio = float(upper_expansion / lower_expansion)

            # Tentukan bias arah
            if skew_ratio >= cls.BULLISH_THRESHOLD:
                bias = "BULLISH_EXPANSION"
                confidence = min(0.95, 0.50 + (skew_ratio - cls.BULLISH_THRESHOLD) * 0.3)
            elif skew_ratio <= cls.BEARISH_THRESHOLD:
                bias = "BEARISH_EXPANSION"
                confidence = min(0.95, 0.50 + (cls.BEARISH_THRESHOLD - skew_ratio) * 0.5)
            else:
                bias = "SYMMETRIC_NEUTRAL"
                confidence = 0.50

            # Median drift terhadap current price
            drift_pct = 0.0
            if current_price and current_price > 0:
                drift_pct = float((q50 - current_price) / current_price) * 100.0

            return {
                "valid": True,
                "skew_ratio": round(skew_ratio, 3),
                "bias": bias,
                "confidence": round(confidence, 2),
                "q10": round(q10, 5),
                "q50": round(q50, 5),
                "q90": round(q90, 5),
                "upper_expansion": round(upper_expansion, 5),
                "lower_expansion": round(lower_expansion, 5),
                "drift_pct": round(drift_pct, 3),
            }

        except Exception as e:
            logger.debug(f"TimesFM skew calculation error: {e}")
            return cls._empty_result(str(e))

    @classmethod
    def get_sizing_multiplier(cls, alpha_result: Dict[str, Any], direction: str) -> float:
        """
        Hitung pengali ukuran posisi (sizing multiplier) berdasarkan konfluensi arah trade vs skewness TimesFM.
        """
        if not alpha_result or not alpha_result.get("valid"):
            return 1.0

        bias = alpha_result.get("bias", "SYMMETRIC_NEUTRAL")
        dir_clean = (direction or "").strip().upper()

        if dir_clean == "BUY":
            if bias == "BULLISH_EXPANSION":
                return 1.15  # Upward tail expansion boosts buy size
            elif bias == "BEARISH_EXPANSION":
                return 0.80  # Downward tail expansion penalizes buy size
        elif dir_clean == "SELL":
            if bias == "BEARISH_EXPANSION":
                return 1.15  # Downward tail expansion boosts sell size
            elif bias == "BULLISH_EXPANSION":
                return 0.80  # Upward tail expansion penalizes sell size

        return 1.0

    @classmethod
    def format_for_prompt(cls, alpha_result: Dict[str, Any]) -> str:
        """Format hasil kalkulasi TimesFM alpha untuk diinjeksi ke prompt Stage 2."""
        if not alpha_result or not alpha_result.get("valid"):
            return "TimesFM Quantile Alpha: Not available."

        return (
            f"=== TIMESFM 3.0 PROBABILISTIC SKEW ALPHA ===\n"
            f"Quantile Asymmetry Skew Ratio: {alpha_result['skew_ratio']:.2f}\n"
            f"Directional Tail Bias: {alpha_result['bias']} (Confidence: {alpha_result['confidence']:.2f})\n"
            f"Distribution Bands (Horizon End): Q10={alpha_result['q10']}, Q50 (Median)={alpha_result['q50']}, Q90={alpha_result['q90']}\n"
            f"Expected Median Drift: {alpha_result['drift_pct']:+.2f}%\n"
            f"Guidance: If planning {alpha_result['bias'].split('_')[0]} trade, probability distribution offers tail confluence."
        )

    @classmethod
    def _empty_result(cls, reason: str) -> Dict[str, Any]:
        return {
            "valid": False,
            "skew_ratio": 1.0,
            "bias": "UNKNOWN",
            "confidence": 0.0,
            "reason": reason,
        }
