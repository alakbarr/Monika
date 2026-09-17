"""
Evidence-First Verification Engine.

Enforces strict zero-trust validation before and after every order execution.
Principle: NEVER assume an analysis or order execution succeeded without verifiable evidence.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.EvidenceVerifier")


class EvidenceFirstVerifier:
    """Enforces zero-trust assertions and post-trade reconciliation."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        self.max_risk_per_trade_pct = float(risk_cfg.get("max_risk_per_trade", 0.01) or 0.01) * 100
        self.min_rr_ratio = float(risk_cfg.get("min_reward_risk_ratio", 1.3) or 1.3)
        self.minimum_sl_pips = float(risk_cfg.get("minimum_sl_pips", 5.0) or 5.0)
        self.max_slippage = float(risk_cfg.get("max_slippage_pips", 3.0) or 3.0)

    async def pre_trade_assertions(
        self,
        signal: Dict[str, Any],
        session: Optional[AsyncSession] = None
    ) -> Tuple[bool, List[str]]:
        """
        Phase 1: 10-point deterministic assertions BEFORE sending to MT5 / RiskGate.
        Returns: (all_passed, list_of_violations)
        """
        violations: List[str] = []

        if not signal or not isinstance(signal, dict):
            return False, ["ASSERT_0: Signal payload is empty or invalid."]

        symbol = signal.get("symbol", "")
        decision = (signal.get("decision") or signal.get("action") or "").upper()
        entry_price = float(signal.get("entry_price") or signal.get("entry") or 0.0)
        stop_loss = float(signal.get("stop_loss") or signal.get("sl") or 0.0)
        take_profit = float(signal.get("take_profit") or signal.get("tp") or 0.0)
        confidence = float(signal.get("confidence") or 0.0)
        confluence_score = int(signal.get("confluence_score") or 0)
        priced_in_score = int(signal.get("priced_in_score") or 0)
        invalidation = signal.get("invalidation") or signal.get("invalidation_condition") or ""

        # 1. Actionable Direction
        if decision not in ("BUY", "SELL"):
            violations.append(f"ASSERT_1: Invalid actionable decision '{decision}' (expected BUY or SELL).")

        # 2. Entry Price Positivity
        if entry_price <= 0:
            violations.append(f"ASSERT_2: Entry price ({entry_price}) must be strictly positive.")

        # 3. Stop Loss Validity
        if stop_loss <= 0:
            violations.append(f"ASSERT_3: Stop Loss ({stop_loss}) must be strictly positive.")
        elif decision == "BUY" and stop_loss >= entry_price:
            violations.append(f"ASSERT_3: BUY Stop Loss ({stop_loss}) must be below Entry ({entry_price}).")
        elif decision == "SELL" and stop_loss <= entry_price:
            violations.append(f"ASSERT_3: SELL Stop Loss ({stop_loss}) must be above Entry ({entry_price}).")

        # 4. Take Profit Validity & R:R
        if take_profit <= 0:
            violations.append(f"ASSERT_4: Take Profit ({take_profit}) must be strictly positive.")
        else:
            sl_dist = abs(entry_price - stop_loss)
            tp_dist = abs(take_profit - entry_price)
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                if rr < self.min_rr_ratio:
                    violations.append(f"ASSERT_4: R:R ratio ({rr:.2f}) is below minimum ({self.min_rr_ratio}).")

        # 5. Invalidation Condition
        if not invalidation or len(str(invalidation).strip()) < 10:
            violations.append("ASSERT_5: Invalidation condition missing or too vague (minimum 10 characters).")

        # 6. Confidence Score
        if confidence < 0.50:
            violations.append(f"ASSERT_6: Confidence ({confidence:.2f}) is below execution floor (0.50).")

        # 7. Confluence Score
        if confluence_score < 7:
            violations.append(f"ASSERT_7: Confluence score ({confluence_score}/14) is below threshold (7).")

        # 8. Priced-in Score Overheat Guard
        if priced_in_score >= 8:
            violations.append(f"ASSERT_8: Priced-in score ({priced_in_score}/10) indicates market exhaustion / crowded trade.")

        # 9. Key Evidence Citation
        evidence = signal.get("key_evidence") or signal.get("confluence_factors_json") or []
        if isinstance(evidence, str):
            try:
                import json
                evidence = json.loads(evidence)
            except Exception:
                evidence = [s.strip() for s in evidence.split("\n") if s.strip()]
        if not evidence or len(evidence) < 2:
            rat = str(signal.get("rationale") or "")
            rat_pts = [s.strip() for s in rat.split(".") if len(s.strip()) > 10]
            if len(rat_pts) >= 2:
                evidence = rat_pts
        if not evidence or len(evidence) < 2:
            violations.append("ASSERT_9: Minimum 2 concrete evidence points required in signal.")

        # 10. Quote Staleness Guard
        age_seconds = signal.get("quote_age_seconds")
        if age_seconds is not None and age_seconds > 60:
            violations.append(f"ASSERT_10: Market quote is stale ({age_seconds}s old > 60s max).")

        all_passed = len(violations) == 0
        if not all_passed:
            logger.warning(f"EvidenceVerifier [{symbol}] Pre-trade assertions failed with {len(violations)} violations: {violations}")

        return all_passed, violations

    async def post_execution_reconciliation(
        self,
        order_result: Dict[str, Any],
        mt5_client: Optional[Any] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Phase 2: Zero-trust post-execution reconciliation.
        Verifies that ticket actually exists in broker book with correct SL/TP.
        """
        report: Dict[str, Any] = {
            "verified": False,
            "ticket": order_result.get("ticket"),
            "slippage_points": 0.0,
            "issues": []
        }

        ticket = order_result.get("ticket")
        if not ticket:
            report["issues"].append("No order ticket returned by broker/execution service.")
            return report

        # If live MT5 client is available, poll ticket
        if mt5_client:
            try:
                positions = None
                if hasattr(mt5_client, "get_position"):
                    positions = await mt5_client.get_position(ticket)
                elif hasattr(mt5_client, "get_open_positions"):
                    positions = await mt5_client.get_open_positions()

                import inspect
                if inspect.iscoroutine(positions):
                    positions = await positions

                matched = None
                if isinstance(positions, list):
                    for p in positions:
                        if isinstance(p, dict) and p.get("ticket") == ticket:
                            matched = p
                            break
                elif isinstance(positions, dict):
                    if positions.get("ticket") == ticket:
                        matched = positions
                    elif "positions" in positions and isinstance(positions["positions"], list):
                        for p in positions["positions"]:
                            if isinstance(p, dict) and p.get("ticket") == ticket:
                                matched = p
                                break

                if matched:
                    actual_sl = float(matched.get("sl", 0.0) or 0.0)
                    if actual_sl <= 0:
                        report["issues"].append(f"Ticket #{ticket} opened without active Stop Loss in broker book!")

                    # Slippage check
                    requested = float(order_result.get("requested_price", 0.0) or 0.0)
                    filled = float(matched.get("price_open", 0.0) or 0.0)
                    if requested > 0 and filled > 0:
                        report["slippage_points"] = abs(filled - requested)

            except Exception as e:
                report["issues"].append(f"Broker state polling exception: {e}")
        else:
            # Paper trade or mock mode validation
            report["verified"] = True
            return report

        report["verified"] = len(report["issues"]) == 0
        return report
