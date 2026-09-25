"""Check objektif & reproducible -- independen dari LLM judge -- dihitung
terhadap snapshot pasar REAL yang sama yang dilihat setiap model kandidat."""
from analysis.calculators.daily_range_calculator import compute_daily_range_context


async def score_trade_payload(session, settings, symbol: str, payload: dict) -> dict:
    checks: dict[str, bool] = {}
    payload = payload or {}
    decision = payload.get("decision")
    checks["has_decision"] = decision in ("buy", "sell", "wait", "avoid")

    if decision in ("wait", "avoid"):
        rationale = str(payload.get("rationale") or payload.get("reasoning") or "").strip()
        risk_factors = payload.get("risk_factors") or payload.get("key_risks") or []
        checks["has_substantive_rationale"] = len(rationale) >= 25
        checks["cites_specific_reason"] = bool(risk_factors) or any(
            kw in rationale.lower()
            for kw in [
                "vix", "spread", "drawdown", "correlation", "session",
                "volatility", "liquidity", "news", "range", "consolidat",
                "inside bar", "no displacement", "choppy", "low adr",
                "uncertainty", "fvg", "ob", "order block", "resistance",
                "support", "trend", "risk", "hazard", "event",
            ]
        )
        checks["not_lazy_generic"] = not any(
            lazy in rationale.lower()
            for lazy in [
                "no opportunity", "nothing to do", "market closed", "n/a",
                "not sure", "skip", "pass", "idk",
            ]
        )
    elif decision in ("buy", "sell"):
        entry_cond = payload.get("entry_condition")
        entry = (entry_cond.get("price") if isinstance(entry_cond, dict) else None) or payload.get("entry_price") or payload.get("entry")
        sl = payload.get("stop_loss")
        tp = payload.get("take_profit")
        checks["has_sl_tp"] = sl is not None and tp is not None
        checks["sl_tp_correct_side"] = False
        checks["rr_meets_minimum"] = False

        if sl and tp and entry:
            correct_side = (decision == "buy" and sl < entry < tp) or (decision == "sell" and tp < entry < sl)
            checks["sl_tp_correct_side"] = bool(correct_side)
            sl_d, tp_d = abs(entry - sl), abs(entry - tp)
            rr = (tp_d / sl_d) if sl_d else 0
            min_rr = settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)
            checks["rr_meets_minimum"] = rr >= min_rr

            adr = await compute_daily_range_context(session, symbol, settings)
            if "error" not in adr and "target_tp_min_distance" in adr and "target_sl_max_distance" in adr:
                checks["tp_within_adr_band"] = adr["target_tp_min_distance"] * 0.85 <= tp_d <= adr["target_tp_max_distance"] * 1.15
                checks["sl_within_adr_ceiling"] = sl_d <= adr["target_sl_max_distance"] * 1.15

        checks["has_invalidation"] = bool(payload.get("invalidation"))
        checks["has_confluence_score"] = payload.get("confluence_score") is not None
        checks["has_priced_in_score"] = payload.get("priced_in_score") is not None

    passed = sum(1 for v in checks.values() if v is True)
    total = len(checks) or 1
    return {"checks": checks, "pass_rate": passed / total}


def verify_invariant_compliance(prompt: str) -> tuple[bool, list[str]]:
    """
    Memvalidasi kepatuhan invariant dasar pada varian prompt hasil mutasi evolusi.
    Memastikan tidak ada aturan inti, batasan numerik, atau constraint keamanan yang hilang.
    """
    reasons = []
    if not prompt or len(prompt.strip()) < 50:
        reasons.append("Prompt too short or empty")

    required_keywords = ["decision", "stop_loss", "take_profit", "risk"]
    prompt_lower = (prompt or "").lower()
    for kw in required_keywords:
        if kw not in prompt_lower:
            reasons.append(f"Missing core keyword: {kw}")

    return (len(reasons) == 0, reasons)
