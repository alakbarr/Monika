"""
Post-Decision Output Verifier — Closed-loop verification & self-correction.

Validates trade proposals with deterministic constraints before entering the debate pipeline:
- Mathematical integrity (SL/TP sides, minimum R:R ratio)
- Price staleness and threshold bounds
- Synchronous error feedback injection for self-correction (up to max_retries).
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context

logger = logging.getLogger("TradingAgent.OutputVerifier")


class OutputVerifier:
    """Verify trade decisions before they enter the debate pipeline."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    async def verify_and_correct(
        self, session, settings: dict, symbol: str, raw_output: dict, context_data: dict, client, max_retries: int = 2
    ) -> Tuple[dict, List[str]]:
        """
        Verify output. If fails, inject error -> LLM self-corrects.
        Returns: (verified_output, corrections_log)
        """
        corrections = []
        output = raw_output or {}
        failures: List[str] = []

        for attempt in range(max_retries + 1):
            failures = await self._run_all_checks(session, settings, symbol, output, context_data)
            if not failures:
                return output, corrections

            # Deterministic Snapping Pass (0 token): Fix arithmetic/ratio deviations without LLM
            if attempt == 0:
                output, snaps = self._apply_deterministic_math_snapping(
                    output, failures, settings, symbol, context_data
                )
                if snaps:
                    corrections.extend(snaps)
                    failures = await self._run_all_checks(session, settings, symbol, output, context_data)
                    if not failures:
                        return output, corrections

            if attempt < max_retries:
                logger.info(
                    f"[{symbol}] Verification failed ({len(failures)} issues), "
                    f"self-correcting attempt {attempt + 1}/{max_retries}"
                )
                correction_prompt = self._build_correction_prompt(symbol, output, failures)
                from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

                prov_name = getattr(client, "provider_name", "") or getattr(client, "_get_provider_name", lambda: "")()
                model_name = getattr(client, "model", "")

                raw_verifier_sys = (
                    "=== CLOSED-LOOP QUANTITATIVE RISK & VERIFICATION AUDITOR ===\n"
                    "You are a senior quantitative risk and trade auditor. "
                    "Review the trading decision, fix all detected verification failures, "
                    "and emit a strictly compliant JSON trading decision conforming to the schema."
                )
                static_verifier_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
                    raw_verifier_sys,
                    model_name=model_name,
                    provider_name=prov_name,
                    force=True,
                    task_role="output_verifier",
                    settings=getattr(self, "settings", None),
                )
                error_context = f"[TARGET SYMBOL]: {symbol}\n[VERIFICATION FAILURES]:\n" + "\n".join(
                    f"- {f}" for f in failures
                )
                full_user_correction = f"{error_context}\n\n{correction_prompt}"
                try:
                    from monika.infrastructure.providers.base_provider import extract_and_parse_json

                    corrected = None
                    if hasattr(client, "classify_json"):
                        corrected = await client.classify_json(full_user_correction, system_prompt=static_verifier_sys)
                    elif hasattr(client, "generate_content"):
                        resp_str = await client.generate_content(
                            system_prompt=static_verifier_sys, user_message=full_user_correction, temperature=0.0
                        )
                        corrected = extract_and_parse_json(resp_str) if resp_str else None
                    elif hasattr(client, "generate"):
                        resp_str = await client.generate(
                            prompt=full_user_correction, system=static_verifier_sys, temperature=0.0
                        )
                        corrected = extract_and_parse_json(resp_str) if resp_str else None
                    elif hasattr(client, "generate_text"):
                        resp_str = await client.generate_text(
                            prompt=full_user_correction, system_prompt=static_verifier_sys, temperature=0.0
                        )
                        corrected = extract_and_parse_json(resp_str) if resp_str else None

                    if isinstance(corrected, dict) and corrected:
                        output = corrected
                        corrections.append(f"Attempt {attempt + 1}: Fixed {len(failures)} issues")
                except Exception as e:
                    logger.warning(f"[{symbol}] Self-correction attempt {attempt + 1} failed: {e}")
                    break

        critical_failures = list(failures)

        if critical_failures:
            logger.warning(
                f"[{symbol}] {len(critical_failures)} critical verification issues remain after {max_retries} retries. "
                f"Demoting decision to WAIT (Fail-Closed)."
            )
            output["decision"] = "wait"
            output["is_verified"] = False
            output["verification_failures"] = critical_failures
        else:
            output["is_verified"] = True

        return output, corrections

    def _apply_deterministic_math_snapping(
        self, output: dict, failures: List[str], settings: dict, symbol: str, context_data: Optional[dict] = None
    ) -> Tuple[dict, List[str]]:
        """
        Deterministic Snapping Pass:
        Fixes mathematical, ratio deviations (R:R ratio), and structural anchor deviations
        in 0ms with 0 tokens, eliminating token-wasting LLM self-correction retries for arithmetic.
        """
        decision = output.get("decision", "").lower()
        if decision not in ("buy", "sell"):
            return output, []

        entry_cond = output.get("entry_condition")
        entry = entry_cond.get("price") if isinstance(entry_cond, dict) else None
        if entry is None:
            entry = (
                output.get("price_at_analysis")
                or output.get("current_price")
                or output.get("entry_price")
                or (context_data.get("current_price") if isinstance(context_data, dict) else None)
                or (context_data.get("price_at_analysis") if isinstance(context_data, dict) else None)
            )
        sl = output.get("stop_loss")
        tp = output.get("take_profit")
        if entry is None or sl is None or tp is None:
            return output, []

        digits = 5
        try:
            from monika.domain.risk.position_sizing import get_instrument_spec

            spec = get_instrument_spec(symbol)
            if spec and spec.digits:
                digits = int(spec.digits)
        except Exception:
            digits = 5

        try:
            entry = round(float(entry), digits)
            sl = round(float(sl), digits)
            tp = round(float(tp), digits)
        except TypeError, ValueError:
            return output, []

        initial_sl_valid = (decision == "buy" and sl < entry) or (decision == "sell" and sl > entry)
        sl_dist = abs(entry - sl)
        tp_dist = abs(entry - tp)
        snaps = []

        # Anchor Snapping Pass (SOTA Grounding): Snap entry to nearest verified structural level if within 0.25x ATR or 0.3%
        adopted_bracket_name = (
            str(
                output.get("adopted_bracket")
                or (entry_cond.get("adopted_bracket") if isinstance(entry_cond, dict) else "")
                or ""
            )
            .strip()
            .upper()
        )
        atr_val = None
        if context_data and isinstance(context_data, dict):
            price_levels = self._extract_price_levels(context_data)
            atr_val = self._extract_atr(context_data)
            has_bracket = adopted_bracket_name in (
                "LONG_OPTION_A",
                "SHORT_OPTION_B",
                "OPTION_A",
                "OPTION_B",
            ) or bool(output.get("bracket_adopted"))
            if price_levels and not has_bracket:
                entry_val = float(entry)
                nearest_anchor = min(price_levels, key=lambda l: abs(entry_val - l))
                anchor_dist = abs(entry - nearest_anchor)
                max_snap_dist = (0.25 * atr_val) if (atr_val and atr_val > 0) else (0.003 * entry)
                if 0 < anchor_dist <= max_snap_dist:
                    cand_entry = round(nearest_anchor, digits)
                    # Prevent anchor snapping from inverting SL
                    if (decision == "buy" and cand_entry > sl) or (decision == "sell" and cand_entry < sl):
                        old_entry = entry
                        entry = cand_entry
                        sl_dist = abs(entry - sl)
                        output["entry_price"] = entry
                        if isinstance(output.get("entry_condition"), dict):
                            output["entry_condition"]["price"] = entry
                        snaps.append(f"Deterministic snap: anchored Entry from {old_entry} to structural level {entry}")

        if sl_dist <= 0 or entry == sl:
            return output, []

        # SL Distance Snapping (SOTA Invariant Enforcement): ensure SL is at least 1.0x ATR away
        if atr_val and atr_val > 0:
            min_sl_dist = 1.0 * atr_val
            if sl_dist < (min_sl_dist * 0.95):  # allow 5% rounding leeway
                old_sl = sl
                if decision == "buy":
                    sl = round(entry - min_sl_dist, digits)
                    output["stop_loss"] = sl
                    sl_dist = abs(entry - sl)
                    snaps.append(f"Deterministic snap: widened BUY SL from {old_sl} to 1.0x ATR ({sl})")
                elif decision == "sell":
                    sl = round(entry + min_sl_dist, digits)
                    output["stop_loss"] = sl
                    sl_dist = abs(entry - sl)
                    snaps.append(f"Deterministic snap: widened SELL SL from {old_sl} to 1.0x ATR ({sl})")

        min_rr = (settings or {}).get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.5)
        sl_dist = abs(entry - sl)
        tp_dist = abs(entry - tp)

        if sl_dist <= 0:
            return output, []

        # Fix R:R ratio deterministically
        has_rr_issue = any("R:R" in f and "minimum" in f for f in failures)
        if has_rr_issue or (tp_dist / sl_dist < min_rr - 0.05):
            target_tp_dist = round(sl_dist * min_rr, digits)
            if decision == "buy" and sl < entry:
                tp = round(entry + target_tp_dist, digits)
                output["take_profit"] = tp
                snaps.append(f"Deterministic snap: adjusted TP to {output['take_profit']} (R:R={min_rr})")
            elif decision == "sell" and sl > entry:
                tp = round(entry - target_tp_dist, digits)
                output["take_profit"] = tp
                snaps.append(f"Deterministic snap: adjusted TP to {output['take_profit']} (R:R={min_rr})")

        # Fix TimesFM Q90/Q10 overextension deterministically
        for f in failures:
            if "TimesFM 3.0 Q90 ceiling" in f:
                import re

                m = re.search(r"ceiling \(([0-9.]+)\)", f)
                if m and decision == "buy":
                    cand_tp = round(float(m.group(1)), digits)
                    if cand_tp > entry:
                        tp = cand_tp
                        output["take_profit"] = tp
                    snaps.append(f"Deterministic snap: capped BUY TP to TimesFM Q90 ceiling ({output['take_profit']})")
                    new_tp_dist = abs(entry - output["take_profit"])
                    if sl_dist > 0 and (new_tp_dist / sl_dist) < (min_rr - 0.05):
                        # Ensure SL does NOT breach 1.0x ATR minimum invariant (Fix 6.4)
                        min_allowed_sl_dist = (1.0 * atr_val) if (atr_val and atr_val > 0) else sl_dist
                        safe_sl_dist = max(round(new_tp_dist / min_rr, digits), min_allowed_sl_dist)
                        sl = round(entry - safe_sl_dist, digits)
                        output["stop_loss"] = sl
                        sl_dist = safe_sl_dist
                        snaps.append(
                            f"Deterministic snap: harmonized SL to {sl} preserving min 1.0x ATR under TimesFM cap"
                        )
            elif "TimesFM 3.0 Q10 floor" in f:
                import re

                m = re.search(r"floor \(([0-9.]+)\)", f)
                if m and decision == "sell":
                    cand_tp = round(float(m.group(1)), digits)
                    if cand_tp < entry:
                        tp = cand_tp
                        output["take_profit"] = tp
                    snaps.append(f"Deterministic snap: capped SELL TP to TimesFM Q10 floor ({output['take_profit']})")
                    new_tp_dist = abs(entry - output["take_profit"])
                    if sl_dist > 0 and (new_tp_dist / sl_dist) < (min_rr - 0.05):
                        # Ensure SL does NOT breach 1.0x ATR minimum invariant (Fix 6.4)
                        min_allowed_sl_dist = (1.0 * atr_val) if (atr_val and atr_val > 0) else sl_dist
                        safe_sl_dist = max(round(new_tp_dist / min_rr, digits), min_allowed_sl_dist)
                        sl = round(entry + safe_sl_dist, digits)
                        output["stop_loss"] = sl
                        sl_dist = safe_sl_dist
                        snaps.append(
                            f"Deterministic snap: harmonized SL to {sl} preserving min 1.0x ATR under TimesFM cap"
                        )

        # Direction invariant check post-snapping (prevent snapping from inverting SL / TP)
        if initial_sl_valid:
            if decision == "buy":
                if sl >= entry:
                    fallback_dist = atr_val if (atr_val and atr_val > 0) else (entry * 0.005)
                    sl = round(entry - fallback_dist, digits)
                    output["stop_loss"] = sl
                    snaps.append(f"Deterministic snap: corrected inverted BUY SL to {sl}")
                if tp <= entry:
                    fallback_tp_dist = abs(entry - sl) * min_rr
                    tp = round(entry + fallback_tp_dist, digits)
                    output["take_profit"] = tp
                    snaps.append(f"Deterministic snap: corrected inverted BUY TP to {tp}")
            elif decision == "sell":
                if sl <= entry:
                    fallback_dist = atr_val if (atr_val and atr_val > 0) else (entry * 0.005)
                    sl = round(entry + fallback_dist, digits)
                    output["stop_loss"] = sl
                    snaps.append(f"Deterministic snap: corrected inverted SELL SL to {sl}")
                if tp >= entry:
                    fallback_tp_dist = abs(sl - entry) * min_rr
                    tp = round(entry - fallback_tp_dist, digits)
                    output["take_profit"] = tp
                    snaps.append(f"Deterministic snap: corrected inverted SELL TP to {tp}")

        # Recalculate final sl_dist and tp_dist and synchronize output
        sl_dist = abs(entry - sl)
        tp_dist = abs(entry - tp)
        output["stop_loss"] = round(sl, digits)
        output["take_profit"] = round(tp, digits)
        if isinstance(output.get("entry_condition"), dict):
            output["entry_condition"]["price"] = round(entry, digits)

        return output, snaps

    async def _run_all_checks(
        self, session, settings: dict, symbol: str, output: dict, context_data: dict
    ) -> List[str]:
        """Run all 7 verification checks. Return list of failure descriptions."""
        failures = []
        if not isinstance(output, dict):
            return ["Output is not a valid dictionary payload."]

        decision = str(output.get("decision", "")).lower()

        if decision not in ("buy", "sell", "wait", "avoid"):
            failures.append(f"Invalid decision: '{decision}'. Must be buy/sell/wait/avoid.")
            return failures

        if decision in ("wait", "avoid"):
            if decision == "wait" and not output.get("reevaluation_trigger"):
                output["reevaluation_trigger"] = {
                    "type": "time",
                    "timeframe": "H4",
                    "condition": "Default re-evaluation after 4 hours for WAIT stance",
                    "reevaluate_after_hours": 4,
                }
            return failures  # Only validate trade parameters for buy/sell

        # BUY / SELL Validation
        entry_cond = output.get("entry_condition")
        entry = entry_cond.get("price") if isinstance(entry_cond, dict) else None
        adopted_bracket_name = (
            str(
                output.get("adopted_bracket")
                or (entry_cond.get("adopted_bracket") if isinstance(entry_cond, dict) else "")
                or ""
            )
            .strip()
            .upper()
        )
        if entry is None and adopted_bracket_name and isinstance(context_data, dict):
            from monika.application.analysis.calculators.invariant_calculator import resolve_bracket_choice

            pre_inv = context_data.get("precomputed_invariants")
            b_opts = (pre_inv.get("bracket_options") if isinstance(pre_inv, dict) else None) or context_data.get(
                "bracket_options"
            )
            if isinstance(b_opts, dict):
                resolved_b = resolve_bracket_choice(adopted_bracket_name, b_opts)
                if resolved_b and resolved_b.get("entry") is not None:
                    entry = resolved_b.get("entry")
        if entry is None:
            entry = (
                output.get("price_at_analysis")
                or output.get("current_price")
                or output.get("entry_price")
                or (context_data.get("current_price") if isinstance(context_data, dict) else None)
                or (context_data.get("price_at_analysis") if isinstance(context_data, dict) else None)
            )
        sl = output.get("stop_loss")
        tp = output.get("take_profit")

        # Check 1: Structural validity
        if entry is None or sl is None or tp is None:
            failures.append(f"Missing mandatory level: entry={entry}, sl={sl}, tp={tp}")

        atr_val = self._extract_atr(context_data) if context_data else None

        if entry is not None and sl is not None and tp is not None:
            try:
                entry = float(entry)
                sl = float(sl)
                tp = float(tp)
            except TypeError, ValueError:
                failures.append("Entry, SL, and TP must be numerical float values.")
                return failures

            # Check 2: Direction sanity
            if decision == "buy" and not (sl < entry < tp):
                failures.append(f"BUY direction error: SL({sl}) must be < Entry({entry}) < TP({tp})")
            elif decision == "sell" and not (tp < entry < sl):
                failures.append(f"SELL direction error: TP({tp}) must be < Entry({entry}) < SL({sl})")

            # Check 3: R:R minimum
            sl_dist = abs(entry - sl)
            tp_dist = abs(entry - tp)
            min_rr = (settings or {}).get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.5)
            if sl_dist > 0:
                rr = tp_dist / sl_dist
                if rr < (min_rr - 0.05):  # allow tiny tolerance for rounding
                    failures.append(f"R:R = {rr:.2f} < minimum {min_rr}. Extend TP or tighten SL.")
            else:
                failures.append("SL distance cannot be 0.")

            # Check 4: ADR band compliance
            if session:
                try:
                    try:
                        adr = await compute_daily_range_context(session, symbol, settings, atr_h4=atr_val)
                    except TypeError:
                        adr = await compute_daily_range_context(session, symbol, settings)
                    if "error" not in adr:
                        tp_min = adr.get("target_tp_min_distance", 0) * 0.85
                        tp_max = adr.get("target_tp_max_distance", float("inf")) * 1.15
                        sl_min = adr.get("target_sl_min_distance", 0) * 0.85
                        target_sl_max = adr.get("target_sl_max_distance", float("inf"))
                        sl_max = target_sl_max * 1.15
                        effective_atr = atr_val
                        if (not effective_atr or effective_atr <= 0) and adopted_bracket_name and sl_dist > 0:
                            effective_atr = sl_dist
                        if effective_atr and effective_atr > 0:
                            sl_min = min(sl_min, 0.95 * effective_atr)
                            sl_max = max(sl_max, 1.45 * effective_atr)
                            tp_min = min(tp_min, 1.40 * effective_atr)
                            tp_max = max(tp_max, 2.50 * effective_atr, 1.85 * sl_dist, 1.65 * sl_max)
                        if not (tp_min <= tp_dist <= tp_max):
                            failures.append(f"TP dist {tp_dist:.5f} outside ADR band [{tp_min:.5f}, {tp_max:.5f}]")
                        if sl_min > 0 and sl_dist < sl_min:
                            failures.append(
                                f"SL dist {sl_dist:.5f} is below ADR minimum distance {sl_min:.5f} (too tight, risk of noise stopout)"
                            )
                        if sl_dist > sl_max:
                            failures.append(f"SL dist {sl_dist:.5f} exceeds ADR ceiling {sl_max:.5f}")
                except Exception as e:
                    logger.debug(f"ADR check non-fatal skip: {e}")

            # Check 4b: TimesFM 3.0 Reachability Envelope Compliance
            if session:
                try:
                    from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

                    tfm_engine = TimesFMEngine(settings)
                    tfm_fc = await tfm_engine.get_latest_forecast(session, symbol, timeframe="H1", max_age_hours=8.0)
                    if tfm_fc and "quantiles" in tfm_fc:
                        q_dict = tfm_fc["quantiles"]
                        if decision == "buy" and "q90" in q_dict and q_dict["q90"]:
                            q90 = float(q_dict["q90"][-1])
                            if tp > (q90 * 1.01):  # 1% tolerance
                                failures.append(
                                    f"BUY TP {tp:.5f} exceeds TimesFM 3.0 Q90 ceiling ({q90:.5f}). Statistically ungrounded target."
                                )
                        elif decision == "sell" and "q10" in q_dict and q_dict["q10"]:
                            q10 = float(q_dict["q10"][-1])
                            if tp < (q10 * 0.99):  # 1% tolerance
                                failures.append(
                                    f"SELL TP {tp:.5f} falls below TimesFM 3.0 Q10 floor ({q10:.5f}). Statistically ungrounded target."
                                )
                except Exception as tfm_err:
                    logger.debug(f"TimesFM check in OutputVerifier non-fatal skip: {tfm_err}")

        # Check 5: Anti-hallucination (price near valid levels if context available)
        if entry is not None and context_data and adopted_bracket_name not in ("LONG_OPTION_A", "SHORT_OPTION_B"):
            price_levels = self._extract_price_levels(context_data)
            atr_val = self._extract_atr(context_data)
            if price_levels and not self._near_any_level(entry, price_levels, atr=atr_val, tolerance_pct=0.008):
                nearest = self._find_nearest(entry, price_levels, n=3)
                tol_desc = f"0.5x ATR ({0.5 * atr_val:.5f})" if atr_val else "0.8%"
                failures.append(
                    f"Entry {entry} is far (>{tol_desc}) from any structural level in context. Nearest: {nearest}"
                )

        # Check 6: Confluence score present
        confluence_score = output.get("confluence_score")
        if confluence_score is None:
            failures.append("confluence_score REQUIRED for buy/sell")

        # Check 7: Priced-in score present
        priced_in_score = output.get("priced_in_score")
        if priced_in_score is None:
            failures.append("priced_in_score REQUIRED for buy/sell")

        return failures

    def _build_correction_prompt(self, symbol: str, output: dict, failures: List[str]) -> str:
        """Build prompt asking LLM to fix specific issues."""
        return (
            f"Your trading decision for {symbol} has {len(failures)} verification errors:\n"
            + "\n".join(f"  {i + 1}. {f}" for i, f in enumerate(failures))
            + f"\n\nOriginal Output:\n{json.dumps(output, indent=2, default=str)}"
            + "\n\nFix ALL errors and resubmit the corrected JSON."
        )

    def _extract_price_levels(self, context_data: dict) -> List[float]:
        """Extract all price levels from context data for anti-hallucination."""
        levels = []
        if not isinstance(context_data, dict):
            return levels

        price_keys = [
            "price",
            "price_high",
            "price_low",
            "gap_high",
            "gap_low",
            "level",
            "high",
            "low",
            "close",
            "open",
        ]

        def _extract_from_item(item):
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                try:
                    val = float(item)
                    if val > 0:
                        levels.append(val)
                except TypeError, ValueError:
                    pass
            elif isinstance(item, dict):
                for pk in price_keys:
                    if pk in item and item[pk] is not None:
                        try:
                            val = float(item[pk])
                            if val > 0:
                                levels.append(val)
                        except TypeError, ValueError:
                            pass

        # FIX 6.4: Only snap to genuine structural levels (exclude noisy raw price_history bars)
        target_prefixes = [
            "swing",
            "sr_",
            "support_resistance",
            "order_block",
            "fvg",
            "fair_value_gap",
            "fibonacci",
            "liquidity",
            "smc",
            "zones",
            "levels",
        ]
        for k, v in context_data.items():
            k_lower = str(k).lower()
            if any(tp in k_lower for tp in target_prefixes):
                if isinstance(v, list):
                    for item in v:
                        _extract_from_item(item)
                elif isinstance(v, dict):
                    for sub_k in [
                        "bars",
                        "zones",
                        "points",
                        "breaks",
                        "levels",
                        "items",
                        "swing_points",
                        "swing_highs",
                        "swing_lows",
                        "fvg_zones",
                        "fair_value_gaps",
                        "order_blocks",
                        "sr_zones",
                    ]:
                        sub_v = v.get(sub_k)
                        if isinstance(sub_v, list):
                            for item in sub_v:
                                _extract_from_item(item)
                    _extract_from_item(v)

        return levels

    def _extract_atr(self, context_data: dict) -> Optional[float]:
        """Extract ATR from context data if available."""
        if not isinstance(context_data, dict):
            return None
        direct_h4_atr = (
            (context_data.get("get_atr_H4") or {}).get("atr")
            if isinstance(context_data.get("get_atr_H4"), dict)
            else None
        )
        if direct_h4_atr is not None:
            try:
                f_h4 = float(direct_h4_atr)
                if f_h4 > 0:
                    return f_h4
            except ValueError, TypeError:
                pass
        for atr_key in ("get_atr_H4", "get_atr", "get_atr_H1", "atr", "atr_14", "ATR_14"):
            atr_data = context_data.get(atr_key)
            if isinstance(atr_data, (int, float)) and not isinstance(atr_data, bool):
                f_val = float(atr_data)
                if f_val > 0:
                    return f_val
            elif isinstance(atr_data, dict):
                val = atr_data.get("atr") or atr_data.get("value")
                if isinstance(val, dict):
                    val = val.get("value") or val.get("atr")
                if val is not None:
                    try:
                        f_val = float(val)
                        if f_val > 0:
                            return f_val
                    except ValueError, TypeError:
                        pass
        for nested_k in ("bundle_data", "raw_bundle_data"):
            nested_d = context_data.get(nested_k)
            if isinstance(nested_d, dict) and nested_d is not context_data:
                nested_atr = self._extract_atr(nested_d)
                if nested_atr and nested_atr > 0:
                    return nested_atr
        for inv_key, sub_key in (("precomputed_invariants", "atr_14"), ("daily_range_context", "atr_h4")):
            sub_ctx = context_data.get(inv_key)
            if isinstance(sub_ctx, dict):
                val = sub_ctx.get(sub_key) or sub_ctx.get("atr")
                if val is not None:
                    try:
                        f_val = float(val)
                        if f_val > 0:
                            return f_val
                    except ValueError, TypeError:
                        pass
        for k in ("get_technical_indicators_H4", "get_technical_indicators", "get_technical_indicators_H1"):
            ti = context_data.get(k)
            if isinstance(ti, dict):
                raw_ind = ti.get("indicators")
                ind = raw_ind if isinstance(raw_ind, dict) else ti
                if isinstance(ind, dict):
                    val = ind.get("atr") or ind.get("ATR_14")
                    if isinstance(val, dict):
                        val = val.get("value") or val.get("atr")
                    if val is not None:
                        try:
                            f_val = float(val)
                            if f_val > 0:
                                return f_val
                        except ValueError, TypeError:
                            pass
        return None

    def _near_any_level(
        self, price: float, levels: List[float], tolerance_pct: float = 0.03, atr: Optional[float] = None
    ) -> bool:
        if not levels:
            return True
        if atr and atr > 0:
            max_dist = 0.5 * atr
            return any(abs(price - l) <= max_dist for l in levels)
        return any(abs(price - l) / max(l, 0.0001) <= tolerance_pct for l in levels)

    def _find_nearest(self, price: float, levels: List[float], n: int = 3) -> List[float]:
        if not levels:
            return []
        sorted_levels = sorted(levels, key=lambda l: abs(price - l))
        return sorted_levels[:n]
