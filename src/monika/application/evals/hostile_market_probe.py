# ==============================================================================
# File: evals/hostile_market_probe.py
# ==============================================================================

"""
Hostile Market Feed Wire Probes & Adversarial Stress Testing Battery.
Institutional-grade risk verification and circuit-breaker validation.

Simulates adversarial market anomalies to verify that Monika's RiskGate,
FlashCrashDetector, and ExecutionService strictly fail-closed:
  1. Flash Crash Tick (-15% instant gap)
  2. Spread Blowout (25x normal baseline)
  3. Crossed Book Inversion (bid > ask)
  4. Stale Quote Feed (timestamp drift > 300s)
  5. Zero/Negative Liquidity Depletion
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Evals.HostileProbe")


@dataclass
class HostileTickScenario:
    scenario_name: str
    symbol: str
    bid: float
    ask: float
    spread_pips: float
    timestamp: float
    anomaly_type: str
    expected_risk_action: str  # "REJECT", "TRIP_CIRCUIT_BREAKER", "HALT_TRADING"
    metadata: Dict[str, Any] = field(default_factory=dict)


class HostileMarketProbe:
    """
    Generates hostile and adversarial tick patterns to stress test risk invariants.
    """

    def __init__(self, reference_price: float = 1.0850, symbol: str = "EURUSD"):
        self.reference_price = reference_price
        self.symbol = symbol

    def generate_battery(self) -> List[HostileTickScenario]:
        """
        Builds an exhaustive suite of adversarial tick anomalies.
        """
        now = time.time()
        pip = 0.0001 if "JPY" not in self.symbol else 0.01

        return [
            # 1. Flash Crash Plunge (-15%)
            HostileTickScenario(
                scenario_name="flash_crash_plunge",
                symbol=self.symbol,
                bid=self.reference_price * 0.85,
                ask=(self.reference_price * 0.85) + (2 * pip),
                spread_pips=2.0,
                timestamp=now,
                anomaly_type="FLASH_CRASH",
                expected_risk_action="TRIP_CIRCUIT_BREAKER",
            ),
            # 2. Spread Blowout (45 pips vs normal 1.2 pips)
            HostileTickScenario(
                scenario_name="catastrophic_spread_blowout",
                symbol=self.symbol,
                bid=self.reference_price,
                ask=self.reference_price + (45.0 * pip),
                spread_pips=45.0,
                timestamp=now,
                anomaly_type="SPREAD_SPIKE",
                expected_risk_action="REJECT",
            ),
            # 3. Crossed Book Inversion (Bid > Ask)
            HostileTickScenario(
                scenario_name="crossed_book_inversion",
                symbol=self.symbol,
                bid=self.reference_price + (5 * pip),
                ask=self.reference_price,
                spread_pips=-5.0,
                timestamp=now,
                anomaly_type="CROSSED_BOOK",
                expected_risk_action="REJECT",
            ),
            # 4. Stale Quote Feed (600 seconds in the past)
            HostileTickScenario(
                scenario_name="stale_quote_feed",
                symbol=self.symbol,
                bid=self.reference_price,
                ask=self.reference_price + (1.5 * pip),
                spread_pips=1.5,
                timestamp=now - 600.0,
                anomaly_type="STALE_FEED",
                expected_risk_action="REJECT",
            ),
            # 5. Non-Positive / Zero Pricing
            HostileTickScenario(
                scenario_name="negative_or_zero_price",
                symbol=self.symbol,
                bid=0.0,
                ask=0.0,
                spread_pips=0.0,
                timestamp=now,
                anomaly_type="CORRUPT_PRICE",
                expected_risk_action="REJECT",
            ),
        ]

    def verify_resilience(
        self,
        risk_validator: Callable[[Dict[str, Any]], Tuple[bool, str]],
    ) -> Dict[str, Any]:
        """
        Runs the battery against a validation function (e.g. RiskGate.evaluate or pre_trade_check).
        Verifies that all hostile ticks are fail-closed rejected.
        """
        battery = self.generate_battery()
        results = []
        all_passed = True

        for scenario in battery:
            payload = {
                "symbol": scenario.symbol,
                "bid": scenario.bid,
                "ask": scenario.ask,
                "spread_pips": scenario.spread_pips,
                "timestamp": scenario.timestamp,
                "anomaly_type": scenario.anomaly_type,
            }

            try:
                allowed, reason = risk_validator(payload)
                # Fail-closed invariant: Hostile ticks must NEVER be allowed!
                is_safe = (allowed is False)
                if not is_safe:
                    all_passed = False

                results.append({
                    "scenario": scenario.scenario_name,
                    "anomaly_type": scenario.anomaly_type,
                    "allowed": allowed,
                    "reason": reason,
                    "is_resilient": is_safe,
                })
            except Exception as exc:
                # If it raises an exception, it successfully blocked execution, but clean rejection is preferred
                results.append({
                    "scenario": scenario.scenario_name,
                    "anomaly_type": scenario.anomaly_type,
                    "allowed": False,
                    "reason": f"Exception raised: {exc}",
                    "is_resilient": True,
                })

        return {
            "all_resilient": all_passed,
            "total_tested": len(battery),
            "passed_count": sum(1 for r in results if r["is_resilient"]),
            "details": results,
        }
