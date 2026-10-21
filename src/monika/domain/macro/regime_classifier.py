"""
Macro Regime Classification and Sovereign Flow Adjudication Engine.

Deterministic domain component that evaluates macro-environmental indicators
(Dollar Index / DXY and US 10-Year Real Yields) to categorize market conditions
into systemic regimes (Strong Dollar Expansion, Liquidity Contraction, Risk-On Expansion, Neutral)
and enforce deterministic cross-asset trade admissibility.
"""

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.RegimeClassifier")


class MacroRegime(str, Enum):
    """Systemic macro regimes affecting asset cross-correlations."""

    STRONG_DOLLAR_EXPANSION = "STRONG_DOLLAR_EXPANSION"
    LIQUIDITY_CONTRACTION = "LIQUIDITY_CONTRACTION"
    RISK_ON_EXPANSION = "RISK_ON_EXPANSION"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class MacroEnvironment:
    """Immutable representation of classified macro environment."""

    dxy_value: float
    us10y_yield: Optional[float]
    regime: MacroRegime
    allowed_commodity_longs: bool
    allowed_crypto_longs: bool
    reasoning: str


class RegimeClassifier:
    """
    Deterministic Macro Regime Classifier.

    Rules derived from empirical cross-asset validation:
    1. DXY >= 101.0 and US 10Y Yield >= 1.50%: Extreme liquidity contraction; commodity and crypto longs prohibited.
    2. DXY >= 101.0: Strong Dollar regime; commodity longs prohibited.
    3. DXY < 99.5: Risk-on expansion; dollar weakness enables commodity & crypto tailwinds.
    4. Otherwise: Neutral regime; standard confluence requirements apply.
    """

    @classmethod
    def classify(
        cls,
        dxy: float,
        us10y_yield: Optional[float] = None,
    ) -> MacroEnvironment:
        """Classify macro environment from point-in-time DXY and US 10Y yield."""
        dxy_val = float(dxy) if dxy > 0 else 100.0
        y_val = float(us10y_yield) if (us10y_yield is not None and us10y_yield > 0) else None

        if dxy_val >= 101.0:
            if y_val is not None and y_val >= 1.50:
                return MacroEnvironment(
                    dxy_value=dxy_val,
                    us10y_yield=y_val,
                    regime=MacroRegime.LIQUIDITY_CONTRACTION,
                    allowed_commodity_longs=False,
                    allowed_crypto_longs=False,
                    reasoning=(
                        f"Liquidity contraction regime: DXY={dxy_val:.2f} >= 101.0 and US 10Y Real Yield={y_val:.2f}% >= 1.50%. "
                        "Long positions in commodities and crypto are strictly prohibited."
                    ),
                )
            return MacroEnvironment(
                dxy_value=dxy_val,
                us10y_yield=y_val,
                regime=MacroRegime.STRONG_DOLLAR_EXPANSION,
                allowed_commodity_longs=False,
                allowed_crypto_longs=False,
                reasoning=(
                    f"Strong Dollar regime: DXY={dxy_val:.2f} >= 101.0 creates persistent headwinds. "
                    "Long positions in commodities and crypto are prohibited without structural H4 shift."
                ),
            )

        if dxy_val < 99.5:
            return MacroEnvironment(
                dxy_value=dxy_val,
                us10y_yield=y_val,
                regime=MacroRegime.RISK_ON_EXPANSION,
                allowed_commodity_longs=True,
                allowed_crypto_longs=True,
                reasoning=(
                    f"Risk-on expansion regime: DXY={dxy_val:.2f} < 99.5 reflects softening dollar. "
                    "Tailwinds active for commodities and risk assets."
                ),
            )

        return MacroEnvironment(
            dxy_value=dxy_val,
            us10y_yield=y_val,
            regime=MacroRegime.NEUTRAL,
            allowed_commodity_longs=True,
            allowed_crypto_longs=True,
            reasoning=f"Neutral macro regime (DXY={dxy_val:.2f}). Standard technical/macro confluence applies.",
        )

    @classmethod
    def is_trade_allowed(
        cls,
        symbol: str,
        direction: str,
        dxy: float,
        us10y_yield: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Validates whether a proposed trade direction is permitted under current macro regime.
        Returns (is_allowed, reason).
        """
        dir_clean = str(direction).lower().strip()
        if dir_clean != "buy":
            # Shorting or waiting is always permissible under strong dollar regimes
            return True, "Direction aligns with or is unaffected by macro regime"

        env = cls.classify(dxy=dxy, us10y_yield=us10y_yield)
        sym_upper = symbol.upper()

        is_commodity = any(k in sym_upper for k in ("XAU", "XTI", "XBR", "GOLD", "OIL"))
        is_crypto = any(k in sym_upper for k in ("BTC", "ETH", "SOL"))

        if is_commodity and not env.allowed_commodity_longs:
            msg = f"Macro Filter Blocked: BUY on commodity {symbol} rejected under {env.regime.value}. {env.reasoning}"
            logger.info(f"[{symbol}] {msg}")
            return False, msg

        if is_crypto and not env.allowed_crypto_longs:
            msg = f"Macro Filter Blocked: BUY on crypto {symbol} rejected under {env.regime.value}. {env.reasoning}"
            logger.info(f"[{symbol}] {msg}")
            return False, msg

        return True, f"Trade permitted under {env.regime.value}"
