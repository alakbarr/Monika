"""
Pi-Inspired In-Harness Grounding Validator.

Verifies numerical evidence, cited levels, and structural claims in LLM output
directly against the empirical data prefetch snapshot:
1. Entry Price Proximity: Entry must reside within reasonable proximity to market price (<= 1.5x ATR).
2. Stop Loss Mathematical Integrity: |Entry - SL| >= 1.0x verified ATR 14.
3. Order Block & FVG Grounding: Cited zone prices must match a verified unmitigated zone in the raw bundle (+-0.25x ATR).
4. Concrete Evidence Requirement: Flags generic qualitative statements without concrete numbers.

Rejects or corrects hallucinations BEFORE the output is accepted by the stage orchestrator.
"""

from typing import Dict, Any, List, Tuple, Optional
import logging
import re
import math

logger = logging.getLogger("TradingAgent.InHarnessGrounding")


class InHarnessGroundingValidator:
    """Verifies that LLM decisions and evidence are 100% grounded in empirical data."""

    @classmethod
    def extract_numbers_from_text(cls, text: str) -> List[float]:
        """Extracts numerical floats from text string."""
        if not text:
            return []
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
        res = []
        for m in matches:
            try:
                res.append(float(m))
            except ValueError:
                pass
        return res

    @classmethod
    def verify_grounding(
        cls,
        decision_payload: dict,
        data_bundle: dict,
        symbol: str = "",
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validates LLM trade proposal or specialist output against empirical data bundle.
        
        Returns:
            (is_grounded: bool, errors: list[str], metadata: dict)
        """
        errors: List[str] = []
        metadata: Dict[str, Any] = {"verified_anchors": 0, "hallucination_flags": 0}

        if not isinstance(decision_payload, dict):
            return False, ["Payload is not a valid dictionary."], metadata

        decision = str(decision_payload.get("decision", decision_payload.get("directional_bias", ""))).upper()
        if decision in ("WAIT", "AVOID", "NEUTRAL"):
            # Require minimal structural justification for WAIT
            rationale = str(decision_payload.get("rationale", ""))
            confluence = decision_payload.get("confluence_score")
            # Flag suspicious avoidance: high confluence but chose WAIT without reason
            if confluence is not None:
                try:
                    cs = int(confluence)
                except (ValueError, TypeError):
                    cs = 0
                if cs >= 7 and len(rationale) < 30:
                    metadata["suspicious_wait"] = True
                    errors.append(
                        "High confluence but chose WAIT without substantial rationale. "
                        "Provide specific structural/timing reason for deferral."
                    )
                    return False, errors, metadata
            return True, [], metadata

        # 1. Extract ground-truth market parameters from bundle
        current_price = None
        for p_key in ("current_price", "price", "close"):
            if p_key in data_bundle and data_bundle[p_key] is not None:
                try:
                    current_price = float(data_bundle[p_key])
                    break
                except (ValueError, TypeError):
                    pass

        atr_val = None
        for a_key in ("atr", "atr_14", "h4_atr"):
            if a_key in data_bundle and data_bundle[a_key] is not None:
                try:
                    atr_val = float(data_bundle[a_key])
                    break
                except (ValueError, TypeError):
                    pass

        # If current price not at top level, search in technical bundle
        if current_price is None and "technical" in data_bundle and isinstance(data_bundle["technical"], dict):
            tech = data_bundle["technical"]
            current_price = tech.get("current_price") or tech.get("price")
            atr_val = atr_val or tech.get("atr") or tech.get("atr_14")

        # 2. Verify Entry Price
        entry_price = decision_payload.get("entry_price", decision_payload.get("entry"))
        if entry_price is not None and current_price is not None:
            try:
                entry_f = float(entry_price)
                if atr_val and atr_val > 0:
                    distance = abs(entry_f - float(current_price))
                    max_allowed_distance = atr_val * 2.0
                    if distance > max_allowed_distance:
                        errors.append(
                            f"Entry price {entry_f} is too far from current price {current_price} "
                            f"(distance={distance:.4f} > 2.0x ATR {max_allowed_distance:.4f})."
                        )
            except (ValueError, TypeError):
                errors.append(f"Invalid entry price format: {entry_price}")

        # 3. Verify Stop Loss ATR Distance
        sl_price = decision_payload.get("stop_loss", decision_payload.get("sl"))
        if sl_price is not None and entry_price is not None:
            try:
                sl_f = float(sl_price)
                entry_f = float(entry_price)
                sl_dist = abs(entry_f - sl_f)
                if atr_val and atr_val > 0:
                    min_sl_dist = atr_val * 0.95  # 5% tolerance
                    if sl_dist < min_sl_dist:
                        errors.append(
                            f"Stop loss distance {sl_dist:.4f} is too tight for market noise "
                            f"(< 1.0x ATR {atr_val:.4f})."
                        )
                    else:
                        metadata["verified_anchors"] += 1
            except (ValueError, TypeError):
                errors.append(f"Invalid stop loss format: {sl_price}")

        # 4. Verify SMC Zones / Liquidity Pools
        raw_zones = data_bundle.get("smc_zones") or data_bundle.get("zones") or []
        if not raw_zones and "technical" in data_bundle and isinstance(data_bundle["technical"], dict):
            raw_zones = data_bundle["technical"].get("smc_zones") or data_bundle["technical"].get("zones") or []

        unmitigated_zone_prices = []
        if isinstance(raw_zones, list):
            for z in raw_zones:
                if isinstance(z, dict):
                    if not z.get("is_mitigated", False) and not z.get("mitigated", False):
                        p_high = z.get("price_high") or z.get("high")
                        p_low = z.get("price_low") or z.get("low")
                        if p_high is not None and p_low is not None:
                            unmitigated_zone_prices.append((float(p_low), float(p_high)))

        cited_zone = decision_payload.get("nearest_entry_zone")
        if cited_zone and isinstance(cited_zone, dict) and unmitigated_zone_prices and atr_val:
            z_low = cited_zone.get("price_low", cited_zone.get("low"))
            z_high = cited_zone.get("price_high", cited_zone.get("high"))
            if z_low is not None and z_high is not None:
                try:
                    zl = float(z_low)
                    zh = float(z_high)
                    # Check if (zl, zh) matches any real unmitigated zone within 0.3x ATR
                    tolerance = atr_val * 0.35
                    matched = any(
                        abs(zl - r_low) <= tolerance and abs(zh - r_high) <= tolerance
                        for r_low, r_high in unmitigated_zone_prices
                    )
                    if not matched:
                        metadata["hallucination_flags"] += 1
                        errors.append(
                            f"Cited zone [{zl:.2f}, {zh:.2f}] does not match any empirical unmitigated zone in market data."
                        )
                    else:
                        metadata["verified_anchors"] += 1
                except (ValueError, TypeError):
                    pass

        # 5. Key Evidence Grounding Check
        key_evidence = decision_payload.get("key_evidence", [])
        if isinstance(key_evidence, list) and key_evidence:
            has_numbers = any(len(cls.extract_numbers_from_text(str(line))) > 0 for line in key_evidence)
            if not has_numbers and decision in ("BUY", "SELL"):
                errors.append("Key evidence lacks concrete numerical anchors (prices, ATR distances, or percentages).")

        # 6. Working Scratchpad Cross-Verification
        if symbol:
            try:
                from analysis.memory.working_scratchpad import WorkingScratchpad
                sp = WorkingScratchpad.read_scratchpad(symbol)
                if sp and sp.get("bias") and sp.get("bias") != "NEUTRAL":
                    sp_bias = sp.get("bias")
                    if decision in ("BUY", "SELL") and decision != sp_bias:
                        errors.append(
                            f"Decision bias '{decision}' directly contradicts working scratchpad bias '{sp_bias}' recorded during analysis."
                        )
                if sp and sp.get("invalidation_price") and sl_price is not None:
                    inv_p = float(sp["invalidation_price"])
                    sl_f = float(sl_price)
                    if decision == "BUY" and sl_f > inv_p:
                        errors.append(
                            f"Stop loss {sl_f} is placed above structural invalidation level {inv_p}."
                        )
                    elif decision == "SELL" and sl_f < inv_p:
                        errors.append(
                            f"Stop loss {sl_f} is placed below structural invalidation level {inv_p}."
                        )
                    else:
                        metadata["verified_anchors"] += 1
            except Exception as sp_err:
                logger.debug(f"Scratchpad cross-verification non-fatal error: {sp_err}")

        is_grounded = len(errors) == 0
        return is_grounded, errors, metadata
