# ==============================================================================
# File: analysis/calculators/hmm_regime.py
# ==============================================================================

"""
Hidden Markov Model (HMM) Market Regime Switching Classifier (Async & Sync).
Fits a 3-state Gaussian HMM (Bull Trend, Bear Trend, Chop/Mean-Reversion)
on multi-asset return and volatility distributions (Q137).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV
from utils import clock

logger = logging.getLogger("TradingAgent.HMMRegimeClassifier")

try:
    from hmmlearn.hmm import GaussianHMM
    HAS_HMMLEARN = True
except ImportError:
    GaussianHMM = None
    HAS_HMMLEARN = False


class HMMRegimeClassifier:
    """
    Quantitative 3-State Hidden Markov Model Classifier.
    State 0: Bullish Trend (positive drift, moderate variance)
    State 1: Bearish Trend (negative drift, elevated variance)
    State 2: Ranging / Chop (near-zero drift, lower variance)
    """

    def __init__(self, n_components: int = 3, random_state: int = 42):
        self.n_components = n_components
        self.random_state = random_state

    def fit_predict_features(self, returns: np.ndarray, ranges: np.ndarray) -> Dict[str, Any]:
        """
        Fit 3-state HMM on log returns and relative bar ranges.
        Returns regime classification, probabilities, and transition matrix.
        """
        n_samples = len(returns)
        if n_samples < 20:
            return {
                "current_regime": "CHOP_RANGING",
                "confidence": 0.5,
                "regime_probabilities": {"BULL": 0.33, "BEAR": 0.33, "CHOP": 0.34},
                "transition_matrix": [[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]],
                "expected_duration_bars": 5.0,
                "method": "insufficient_data_fallback",
            }

        X = np.column_stack([returns, ranges])

        if HAS_HMMLEARN:
            try:
                model = GaussianHMM(
                    n_components=self.n_components,
                    covariance_type="diag",
                    n_iter=100,
                    random_state=self.random_state,
                )
                model.fit(X)
                hidden_states = model.predict(X)
                posteriors = model.predict_proba(X)
                transmat = model.transmat_.tolist()
                means = model.means_[:, 0]  # mean return per state

                # Sort state labels by mean returns: lowest = Bear (1), highest = Bull (0), middle = Chop (2)
                sorted_indices = np.argsort(means)
                bear_idx = int(sorted_indices[0])
                bull_idx = int(sorted_indices[-1])
                chop_idx = int(sorted_indices[1])

                curr_state_raw = hidden_states[-1]
                curr_prob = posteriors[-1]

                if curr_state_raw == bull_idx:
                    current_regime = "BULL_TREND"
                    conf = float(curr_prob[bull_idx])
                elif curr_state_raw == bear_idx:
                    current_regime = "BEAR_TREND"
                    conf = float(curr_prob[bear_idx])
                else:
                    current_regime = "CHOP_RANGING"
                    conf = float(curr_prob[chop_idx])

                p_bull = float(curr_prob[bull_idx])
                p_bear = float(curr_prob[bear_idx])
                p_chop = float(curr_prob[chop_idx])

                # Expected duration: 1 / (1 - P_ii)
                self_prob = transmat[curr_state_raw][curr_state_raw]
                exp_duration = round(1.0 / max(0.01, 1.0 - self_prob), 1)

                return {
                    "current_regime": current_regime,
                    "confidence": round(conf, 3),
                    "regime_probabilities": {
                        "BULL": round(p_bull, 3),
                        "BEAR": round(p_bear, 3),
                        "CHOP": round(p_chop, 3),
                    },
                    "transition_matrix": transmat,
                    "expected_duration_bars": exp_duration,
                    "method": "gaussian_hmm",
                }
            except Exception as e:
                logger.debug(f"[HMM] hmmlearn fit error, falling back: {e}")

        # Statistical Gaussian Mixture / Heuristic Fallback (Zero external dependency)
        recent_ret = np.mean(returns[-5:])
        recent_vol = np.mean(ranges[-5:])
        base_vol = np.mean(ranges)

        if recent_ret > 0.002 and recent_vol >= base_vol:
            regime = "BULL_TREND"
            probs = {"BULL": 0.65, "BEAR": 0.15, "CHOP": 0.20}
        elif recent_ret < -0.002 and recent_vol >= base_vol:
            regime = "BEAR_TREND"
            probs = {"BULL": 0.15, "BEAR": 0.65, "CHOP": 0.20}
        else:
            regime = "CHOP_RANGING"
            probs = {"BULL": 0.25, "BEAR": 0.25, "CHOP": 0.50}

        return {
            "current_regime": regime,
            "confidence": round(probs[regime.split('_')[0]], 3),
            "regime_probabilities": probs,
            "transition_matrix": [[0.75, 0.10, 0.15], [0.10, 0.75, 0.15], [0.20, 0.20, 0.60]],
            "expected_duration_bars": 4.0,
            "method": "statistical_heuristic",
        }

    async def classify_from_ohlcv(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "D1",
        lookback_bars: int = 150,
    ) -> Dict[str, Any]:
        """
        Pull recent OHLCV bars from database and perform HMM regime switching inference.
        """
        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol.upper(), PriceOHLCV.timeframe == timeframe.upper())
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(lookback_bars)
        )
        bars = (await session.execute(stmt)).scalars().all()

        if len(bars) < 25:
            # Fallback to standard price query or default
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "regime": "CHOP_RANGING",
                "confidence": 0.5,
                "probabilities": {"BULL": 0.33, "BEAR": 0.33, "CHOP": 0.34},
                "expected_duration_bars": 5.0,
                "recommendation": "Maintain neutral range-trading tactics; insufficient bar history for full HMM Markov fit.",
            }

        # Chronological order
        bars.reverse()
        closes = np.array([float(b.close) for b in bars])
        highs = np.array([float(b.high) for b in bars])
        lows = np.array([float(b.low) for b in bars])

        log_returns = np.diff(np.log(closes))
        ranges = (highs[1:] - lows[1:]) / np.maximum(closes[1:], 1e-6)

        hmm_res = self.fit_predict_features(log_returns, ranges)
        regime = hmm_res["current_regime"]
        conf = hmm_res["confidence"]
        probs = hmm_res["regime_probabilities"]

        if regime == "BULL_TREND":
            rec = "Favor trend continuation longs on SMC order block pullbacks. Invalidate on CHoCH below prior swing low."
        elif regime == "BEAR_TREND":
            rec = "Favor trend continuation shorts on premium FVG retests. Tighten stops on extended downside moves."
        else:
            rec = "Market in mean-reverting chop regime. Favor liquidity sweeps at session highs/lows and range boundary fades."

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "sample_bars": len(bars),
            "regime": regime,
            "confidence": conf,
            "probabilities": probs,
            "transition_matrix": hmm_res["transition_matrix"],
            "expected_duration_bars": hmm_res["expected_duration_bars"],
            "method": hmm_res["method"],
            "recommendation": rec,
        }
