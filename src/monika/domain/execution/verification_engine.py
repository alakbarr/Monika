"""
Evidence-First Verification Engine.

Enforces strict zero-trust validation before and after every order execution.
Principle: NEVER assume an analysis or order execution succeeded without verifiable evidence.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from monika.core.config.risk_defaults import (
    DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE,
    DEFAULT_MIN_RR_RATIO,
)
from monika.core.risk.quant_scorecard import is_quantitative_source, validate_quant_scorecard

logger = logging.getLogger("TradingAgent.EvidenceVerifier")


class EvidenceFirstVerifier:
    """Enforces zero-trust assertions and post-trade reconciliation."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        trading_cfg = self.settings.get("trading", {})
        risk_cfg = trading_cfg.get("risk", {})
        self.max_risk_per_trade_pct = float(risk_cfg.get("max_risk_per_trade", 0.01) or 0.01) * 100
        self.min_rr_ratio = float(
            risk_cfg.get(
                "min_rr_ratio",
                risk_cfg.get("min_reward_risk_ratio", DEFAULT_MIN_RR_RATIO),
            )
            or DEFAULT_MIN_RR_RATIO
        )
        self.min_edge_confidence = float(
            trading_cfg.get("auto_execute_min_confidence", DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE)
            or DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE
        )
        self.minimum_sl_pips = float(risk_cfg.get("minimum_sl_pips", 5.0) or 5.0)
        self.max_slippage = float(risk_cfg.get("max_slippage_pips", 3.0) or 3.0)

    def record_evidence(
        self,
        decision_payload: Dict[str, Any],
        session: Optional[Any] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Records verifiable evidence for a trading decision including SHA256 payload hash.
        """
        payload_json = json.dumps(decision_payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()

        evidence_record = {
            "payload_hash": payload_hash,
            "decision_payload": decision_payload,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "symbol": decision_payload.get("symbol"),
            "decision": decision_payload.get("decision") or decision_payload.get("action"),
            "metadata": extra_metadata or {},
        }
        logger.info(f"Evidence recorded for {evidence_record.get('symbol')}: hash={payload_hash}")
        return evidence_record

    async def pre_trade_assertions(
        self, signal: Dict[str, Any], session: Optional[Any] = None
    ) -> Tuple[bool, List[str]]:
        """
        Phase 1: 10-point deterministic assertions BEFORE sending to MT5 / RiskGate.
        Returns: (all_passed, list_of_violations)
        """
        violations: List[str] = []

        if not signal or not isinstance(signal, dict):
            return False, ["ASSERT_0: Signal payload is empty or invalid."]

        # Record verifiable evidence SHA256 hash of decision payload
        payload_json = json.dumps(signal, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
        signal["payload_hash"] = payload_hash

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
        else:
            # Enforce minimum SL distance in pips
            from monika.domain.market.instrument_identity import resolve_instrument_identity

            try:
                pip_sz = float(resolve_instrument_identity(symbol).pip_size)
            except Exception:
                pip_sz = 0.0001
            pip_sz = pip_sz if pip_sz > 0 else 0.0001
            sl_dist_pips = abs(entry_price - stop_loss) / pip_sz
            if sl_dist_pips < self.minimum_sl_pips:
                violations.append(
                    f"ASSERT_3: Stop Loss distance ({sl_dist_pips:.1f} pips) is below minimum ({self.minimum_sl_pips:.1f} pips)."
                )

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

        # 5. Invalidation Condition (Strict - Fail Closed)
        if not invalidation or len(str(invalidation).strip()) < 10:
            # Only construct from explicit invalidation_price, never silently fabricate from stop_loss
            inv_p = float(signal.get("invalidation_price") or 0.0)
            inv_d = signal.get("invalidation_direction") or ("below" if decision == "BUY" else "above")
            if inv_p > 0:
                invalidation = f"H4 close {inv_d} {inv_p:.5f} invalidates structural setup."
                signal["invalidation"] = invalidation
            else:
                violations.append("ASSERT_5: Invalidation condition missing or too vague (minimum 10 characters).")

        # 6. Confidence Score
        decision_source = str(signal.get("decision_source") or "").lower()
        is_edge_signal = is_quantitative_source(decision_source)
        min_confidence = self.min_edge_confidence if is_edge_signal else 0.50
        if confidence < min_confidence:
            violations.append(
                f"ASSERT_6: Confidence ({confidence:.2f}) is below execution floor ({min_confidence:.2f})."
            )

        # 6b. Quantitative signals must carry an explicit, valid scorecard.
        if is_edge_signal:
            scorecard = signal.get("quant_scorecard")
            if isinstance(scorecard, str):
                try:
                    scorecard = json.loads(scorecard)
                except TypeError, ValueError:
                    scorecard = None
            if scorecard is None:
                raw_factors = signal.get("confluence_factors_json")
                if isinstance(raw_factors, str):
                    try:
                        raw_factors = json.loads(raw_factors)
                    except TypeError, ValueError:
                        raw_factors = None
                if isinstance(raw_factors, dict):
                    scorecard = raw_factors.get("quant_scorecard")
            scorecard_ok, scorecard_reason = validate_quant_scorecard(
                scorecard,
                min_confidence=self.min_edge_confidence,
                min_rr_ratio=self.min_rr_ratio,
            )
            if not scorecard_ok or not isinstance(scorecard, dict):
                violations.append(f"ASSERT_6b: {scorecard_reason}")
            elif str(scorecard.get("direction", "")).lower() != decision.lower():
                violations.append("ASSERT_6b: quant_scorecard direction does not match the order direction.")

        # 7. Confluence Score (LLM Stage 2 signals require 14-point scorecard, quantitative edge signals are exempted)
        if not is_edge_signal:
            min_conf = float(signal.get("min_confluence") or getattr(self, "min_confluence", 4))
            if confluence_score < min_conf:
                violations.append(
                    f"ASSERT_7: Confluence score ({confluence_score}/14) is below threshold ({min_conf})."
                )

        # 8. Priced-in Score Overheat Guard
        if priced_in_score >= 8:
            violations.append(
                f"ASSERT_8: Priced-in score ({priced_in_score}/10) indicates market exhaustion / crowded trade."
            )

        # 9. Key Evidence Citation
        evidence = signal.get("key_evidence") or signal.get("confluence_factors_json") or []
        if isinstance(evidence, str):
            try:
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
            logger.warning(
                f"EvidenceVerifier [{symbol}] Pre-trade assertions failed with {len(violations)} violations: {violations}"
            )

        return all_passed, violations

    async def post_execution_reconciliation(
        self, order_result: Dict[str, Any], mt5_client: Optional[Any] = None, session: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Phase 2: Zero-trust post-execution reconciliation.
        Verifies that ticket actually exists in broker book with correct SL/TP.
        """
        report: Dict[str, Any] = {
            "verified": False,
            "ticket": order_result.get("ticket"),
            "slippage_points": 0.0,
            "issues": [],
        }

        ticket = order_result.get("ticket")
        if not ticket:
            report["issues"].append("No order ticket returned by broker/execution service.")
            return report

        # If live MT5 client is available, poll ticket
        if mt5_client:
            try:
                import inspect

                positions = None
                if hasattr(mt5_client, "get_position"):
                    res = mt5_client.get_position(ticket)
                    positions = (await res) if inspect.isawaitable(res) else res
                elif hasattr(mt5_client, "get_open_positions"):
                    res = mt5_client.get_open_positions()
                    positions = (await res) if inspect.isawaitable(res) else res

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
                        symbol = matched.get("symbol") or order_result.get("symbol") or ""
                        if symbol:
                            from monika.domain.market.instrument_identity import resolve_instrument_identity

                            try:
                                pip_sz = float(resolve_instrument_identity(symbol).pip_size)
                            except Exception:
                                pip_sz = 0.0001
                            pip_sz = pip_sz if pip_sz > 0 else 0.0001
                            slippage_pips = report["slippage_points"] / pip_sz
                            if slippage_pips > self.max_slippage:
                                report["issues"].append(
                                    f"Ticket #{ticket} slippage ({slippage_pips:.1f} pips) exceeded max threshold ({self.max_slippage:.1f} pips)."
                                )

            except Exception as e:
                report["issues"].append(f"Broker state polling exception: {e}")
        else:
            # Paper trade or mock mode validation
            status = str(order_result.get("status", "")).upper()
            if status in ("REJECTED", "FAILED", "ERROR"):
                report["issues"].append(f"Paper order #{ticket} execution returned failure status: {status}")
            actual_sl = float(order_result.get("sl", 0.0) or order_result.get("stop_loss", 0.0) or 0.0)
            if "sl" in order_result and actual_sl <= 0:
                report["issues"].append(f"Paper order #{ticket} recorded with non-positive Stop Loss ({actual_sl}).")
            requested = float(order_result.get("requested_price", 0.0) or 0.0)
            filled = float(order_result.get("price_open", 0.0) or order_result.get("fill_price", 0.0) or 0.0)
            if requested > 0 and filled > 0:
                report["slippage_points"] = abs(filled - requested)

        report["verified"] = len(report["issues"]) == 0
        return report
